"""Per-clip cleanup: music removal, mild denoise, edge trim, loudness, resample."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from ..models import ProcessingSettings
from .audio_io import read_span

CONTEXT_S = 0.6  # extra audio read around the clip so the separator/denoiser have context
_demucs = None


@dataclass
class Processed:
    audio: np.ndarray  # float32 mono at settings.sample_rate
    sr: int
    snr_db: float
    flags: list[str]
    music_db: float | None = None  # level of what the separator removed, relative to the voice (None = not run)


def _get_demucs():
    global _demucs
    if _demucs is None:
        import torch
        from demucs.pretrained import get_model

        model = get_model("htdemucs")
        model.eval()
        _demucs = (model, torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        model.to(_demucs[1])
    return _demucs


def separate_vocals(x: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """Return (vocals stem, residual_db) for a mono mixture using HTDemucs.

    residual_db is the level of everything the separator took out, relative to the voice
    (about -10 dB for speech over music, below -25 dB for a clean recording).
    """
    import torch
    from demucs.apply import apply_model

    model, device = _get_demucs()
    wav = torch.from_numpy(x).float()[None, :].repeat(2, 1)  # (2, n) fake-stereo
    if sr != model.samplerate:
        g = math.gcd(sr, model.samplerate)
        wav = torch.from_numpy(
            resample_poly(wav.numpy(), model.samplerate // g, sr // g, axis=1).astype("float32")
        )
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)  # same normalisation demucs' own CLI uses
    with torch.no_grad():
        # shifts=0 / small overlap: roughly 2x faster than the defaults, which matters on CPU.
        out = apply_model(model, wav[None].to(device), device=device, split=True, overlap=0.1,
                          shifts=0, progress=False)[0]
    vocals = out[model.sources.index("vocals")].cpu()
    vocals = vocals * (ref.std() + 1e-8) + ref.mean()
    mono = vocals.mean(0).numpy().astype("float32")
    if model.samplerate != sr:
        g = math.gcd(sr, model.samplerate)
        mono = resample_poly(mono, sr // g, model.samplerate // g).astype("float32")
    mono = mono[: len(x)]
    rms = lambda a: float(np.sqrt(np.mean(np.square(a)) + 1e-12))
    residual_db = 20 * math.log10(rms(x[: len(mono)] - mono) / rms(mono))
    return mono, residual_db


def denoise(x: np.ndarray, sr: int, strength: float) -> np.ndarray:
    import noisereduce as nr

    return nr.reduce_noise(y=x, sr=sr, stationary=False, prop_decrease=float(strength)).astype("float32")


def _frame_db(x: np.ndarray, frame: int) -> np.ndarray:
    n = len(x) // frame
    if n == 0:
        return np.array([-120.0])
    rms = np.sqrt((x[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms)


def trim_edges(x: np.ndarray, sr: int, keep_ms: int = 150) -> np.ndarray:
    """Cut leading/trailing low-energy audio but leave keep_ms of room on each side."""
    frame = int(0.02 * sr)
    db = _frame_db(x, frame)
    threshold = max(db.max() - 35.0, -60.0)
    voiced = np.where(db > threshold)[0]
    if len(voiced) == 0:
        return x
    keep = int(keep_ms / 1000 * sr)
    start = max(0, voiced[0] * frame - keep)
    end = min(len(x), (voiced[-1] + 1) * frame + keep)
    return x[start:end]


def estimate_snr_db(x: np.ndarray, sr: int) -> float:
    db = _frame_db(x, int(0.03 * sr))
    return float(np.percentile(db, 90) - np.percentile(db, 10))


def normalize_loudness(x: np.ndarray, sr: int, target_lufs: float, peak_db: float = -1.0) -> np.ndarray:
    import pyloudnorm as pyln

    loudness = pyln.Meter(sr).integrated_loudness(x)
    if not np.isfinite(loudness):
        return x
    y = x * 10 ** ((target_lufs - loudness) / 20)
    peak = float(np.abs(y).max())
    limit = 10 ** (peak_db / 20)
    if peak > limit:  # lower the gain rather than clip
        y = y * (limit / peak)
    return y.astype("float32")


def process_clip(
    work_wav: Path, start_s: float, end_s: float, s: ProcessingSettings, use_separator: bool
) -> Processed:
    ctx_start = max(0.0, start_s - CONTEXT_S)
    x, sr = read_span(work_wav, ctx_start, end_s + CONTEXT_S)
    lead = int((start_s - ctx_start) * sr)
    flags: list[str] = []
    music_db = None

    if len(x) == 0 or float(np.abs(x).max()) < 1e-4:
        raise ValueError("clip is silent")

    if use_separator:
        x, music_db = separate_vocals(x, sr)
    if s.denoise_strength > 0:
        x = denoise(x, sr, s.denoise_strength)

    x = x[lead : lead + int((end_s - start_s) * sr)]  # drop the context
    clipped = float((np.abs(x) >= 0.999).mean())
    if clipped > 0.001:
        flags.append("clipping")

    if s.min_clip_s != s.max_clip_s:  # fixed-length clips must keep their exact duration
        x = trim_edges(x, sr, keep_ms=min(150, s.pad_ms))
    fade = int(0.01 * sr)
    if len(x) > 2 * fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype="float32")
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]

    snr = estimate_snr_db(x, sr)
    if snr < 15:
        flags.append("noisy")

    x = normalize_loudness(x, sr, s.target_lufs)
    if sr != s.sample_rate:
        g = math.gcd(sr, s.sample_rate)
        x = resample_poly(x, s.sample_rate // g, sr // g).astype("float32")
    return Processed(audio=np.clip(x, -1.0, 1.0), sr=s.sample_rate, snr_db=round(snr, 1), flags=flags,
                     music_db=music_db)
