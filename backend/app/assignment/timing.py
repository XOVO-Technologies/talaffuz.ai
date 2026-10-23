from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SR = 16000
MIN_WORD = 0.06
MIN_SPAN = 0.05
SENTENCE_PAD = 0.15
HOP = 80
WINDOW = 320


@dataclass
class Timing:
    sentences: list[tuple[float, float]]
    words: list[list[tuple[float, float]]]
    duration: float


def load_audio(path: Path) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != TARGET_SR:
        g = math.gcd(sr, TARGET_SR)
        mono = resample_poly(mono, TARGET_SR // g, sr // g)
    return np.ascontiguousarray(np.clip(mono, -1.0, 1.0), dtype=np.float32)


def envelope(audio: np.ndarray) -> np.ndarray:
    squares = np.concatenate(([0.0], np.cumsum(audio.astype(np.float64) ** 2)))
    centres = np.arange(0, len(audio), HOP)
    lo = np.clip(centres - WINDOW // 2, 0, len(audio))
    hi = np.clip(centres + WINDOW // 2, 0, len(audio))
    mean = (squares[hi] - squares[lo]) / np.maximum(hi - lo, 1)
    return 10.0 * np.log10(mean + 1e-10)


def valley(env: np.ndarray, low: float, high: float) -> float | None:
    first = int(max(0.0, low) * TARGET_SR / HOP)
    last = int(high * TARGET_SR / HOP)
    if last <= first or first >= len(env):
        return None
    segment = env[first:min(last, len(env))]
    if not len(segment):
        return None
    return (first + int(np.argmin(segment))) * HOP / TARGET_SR


def refine(spans: list[tuple[float, float]], audio: np.ndarray, duration: float) -> list[tuple[float, float]]:
    env = envelope(audio)
    out = [[s, max(e, s + MIN_WORD)] for s, e in spans]
    for k in range(len(out) - 1):
        a, b = out[k], out[k + 1]
        if b[0] < a[1]:
            a[1] = b[0] = (a[1] + b[0]) / 2
        gap = b[0] - a[1]
        if gap >= 0.12:
            a[1] += min(0.08, gap * 0.4)
            b[0] -= min(0.05, gap * 0.3)
            continue
        low = max(a[0] + MIN_WORD, a[1] - 0.06)
        high = min(b[1] - MIN_WORD, b[0] + 0.06)
        cut = valley(env, low, high) if high > low else None
        if cut is None:
            cut = (a[1] + b[0]) / 2
        a[1] = b[0] = cut
    first, last = out[0], out[-1]
    first[0] = max(0.0, first[0] - 0.05)
    last[1] = min(duration, last[1] + 0.08)
    return [(s, e) for s, e in out]


def quantise(words: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    previous = 0.0
    for start, end in words:
        s = max(round(start, 2), previous)
        e = max(round(end, 2), round(s + MIN_SPAN, 2))
        result.append((s, e))
        previous = e
    ceiling = round(duration, 2)
    if result[-1][1] > ceiling:
        shifted: list[tuple[float, float]] = []
        for s, e in reversed(result):
            e2 = min(e, ceiling)
            s2 = min(s, round(e2 - MIN_SPAN, 2))
            shifted.append((max(0.0, s2), e2))
            ceiling = s2
        result = list(reversed(shifted))
    return result


def lay_out(counts: list[int], words: list[tuple[float, float]], duration: float) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    flat = quantise(words, duration)
    nested: list[list[tuple[float, float]]] = []
    cursor = 0
    for n in counts:
        nested.append(flat[cursor:cursor + n])
        cursor += n
    ceiling = round(duration, 2)
    bounds: list[list[float]] = []
    for k, group in enumerate(nested):
        first, last = group[0][0], group[-1][1]
        before = nested[k - 1][-1][1] if k > 0 else None
        after = nested[k + 1][0][0] if k + 1 < len(nested) else None
        left = min(SENTENCE_PAD, (first - before) / 2) if before is not None else min(SENTENCE_PAD, first)
        right = min(SENTENCE_PAD, (after - last) / 2) if after is not None else min(SENTENCE_PAD, ceiling - last)
        bounds.append([first - max(0.0, left), last + max(0.0, right)])
    sentences: list[tuple[float, float]] = []
    previous_end = 0.0
    for k, (start, end) in enumerate(bounds):
        s = min(max(round(start, 2), previous_end), nested[k][0][0])
        e = min(max(round(end, 2), nested[k][-1][1]), ceiling)
        sentences.append((s, e))
        previous_end = e
    return sentences, nested


def time_recording(final: list[list[str]], spans: list[tuple[float, float]], audio: np.ndarray) -> Timing:
    duration = len(audio) / TARGET_SR
    refined = refine(spans, audio, duration)
    sentences, words = lay_out([len(s) for s in final], refined, duration)
    return Timing(sentences, words, duration)
