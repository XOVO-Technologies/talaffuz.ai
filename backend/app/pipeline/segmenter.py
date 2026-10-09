"""Speech detection (Silero VAD) and packing of speech spans into TTS-sized clips."""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from ..models import ProcessingSettings

BLOCK_S = 600.0  # VAD runs on 10-minute blocks so multi-hour files never sit in RAM at once
VAD_SR = 16000

_vad_model = None


def _get_vad():
    global _vad_model
    if _vad_model is None:
        from silero_vad import load_silero_vad

        _vad_model = load_silero_vad()
    return _vad_model


def detect_speech(
    wav_path,
    settings: ProcessingSettings,
    progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[tuple[float, float]]:
    """Return speech spans (start_s, end_s) for a mono wav, with no padding applied."""
    import torch
    from silero_vad import get_speech_timestamps

    model = _get_vad()
    spans: list[tuple[float, float]] = []
    with sf.SoundFile(str(wav_path)) as f:
        sr = f.samplerate
        total_s = f.frames / sr
        pos = 0.0
        while pos < total_s - 0.05:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("cancelled")
            f.seek(int(pos * sr))
            block = f.read(int(BLOCK_S * sr), dtype="float32")
            if block.ndim > 1:
                block = block.mean(axis=1)
            block_s = len(block) / sr
            if sr != VAD_SR:
                g = np.gcd(sr, VAD_SR)
                block = resample_poly(block, VAD_SR // g, sr // g).astype("float32")
            found = get_speech_timestamps(
                torch.from_numpy(block),
                model,
                threshold=settings.vad_threshold,
                sampling_rate=VAD_SR,
                min_speech_duration_ms=250,
                max_speech_duration_s=max(2.0, settings.max_clip_s - 1.0),
                min_silence_duration_ms=settings.vad_min_silence_ms,
                speech_pad_ms=0,
                return_seconds=True,
            )
            at_end = pos + block_s >= total_s - 0.05
            next_pos = pos + block_s
            if found and not at_end and found[-1]["end"] >= block_s - 0.2:
                # Speech runs into the block edge: redo it at the start of the next block.
                cut = found.pop()
                if cut["start"] > 0.5:
                    next_pos = pos + cut["start"]
            spans.extend((pos + s["start"], pos + s["end"]) for s in found)
            pos = next_pos
            if progress:
                progress(min(1.0, pos / total_s))
    return spans


CONTEXT_S = 0.6  # matches enhance.CONTEXT_S; a fixed window must leave this much room before EOF


def _fixed_clips(spans: list[tuple[float, float]], clip_s: float, total_s: float) -> list[tuple[float, float]]:
    """Cut the whole recording into strict clip_s-length windows, on the clock (ignoring pauses).

    A window is kept only if it overlaps some detected speech; windows of pure silence (titles,
    music-only intros/outros) are dropped. The final, possibly short, remainder is always dropped:
    every kept clip is exactly clip_s seconds, never shorter.
    """
    n = int((total_s - CONTEXT_S) // clip_s)
    clips = []
    for k in range(n):
        lo, hi = k * clip_s, (k + 1) * clip_s
        if any(sp[0] < hi and sp[1] > lo for sp in spans):
            clips.append((round(lo, 3), round(hi, 3)))
    return clips


def pack_clips(
    spans: list[tuple[float, float]], settings: ProcessingSettings, total_s: float
) -> list[tuple[float, float]]:
    """Greedily merge neighbouring speech spans into clips of min_clip_s..max_clip_s, then pad them.

    Cuts always fall in pauses, so each clip is whole phrases, never a word cut in half. The one
    exception is min_clip_s == max_clip_s, which asks for strict fixed-length clips instead; see
    `_fixed_clips`.
    """
    min_s, max_s, gap_s = settings.min_clip_s, settings.max_clip_s, settings.merge_gap_s
    if min_s == max_s:
        return _fixed_clips(spans, min_s, total_s)
    pad = settings.pad_ms / 1000.0
    speech: list[tuple[float, float]] = []
    i = 0
    while i < len(spans):
        start, end = spans[i]
        j = i + 1
        while j < len(spans):
            gap = spans[j][0] - end
            new_end = spans[j][1]
            fits = (new_end - start) <= max_s
            if fits and gap <= gap_s:
                end = new_end
            elif fits and (end - start) < min_s and gap <= 2 * gap_s:
                end = new_end
            else:
                break
            j += 1
        speech.append((start, end))
        i = j
    speech = [(s, e) for s, e in speech if (e - s) >= min_s]

    clips = []
    for k, (s, e) in enumerate(speech):
        prev_end = speech[k - 1][1] if k > 0 else None
        next_start = speech[k + 1][0] if k + 1 < len(speech) else None
        lo = max(0.0, s - pad)
        hi = min(total_s, e + pad)
        if prev_end is not None:
            lo = max(lo, (prev_end + s) / 2)  # never reach into the neighbour's speech
        if next_start is not None:
            hi = min(hi, (e + next_start) / 2)
        clips.append((round(lo, 3), round(hi, 3)))
    return clips
