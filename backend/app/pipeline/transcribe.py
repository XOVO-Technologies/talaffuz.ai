"""Urdu speech-to-text with faster-whisper (CTranslate2)."""
from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass

import numpy as np
from scipy.signal import resample_poly

_models: dict[str, object] = {}
_lock = threading.Lock()


@dataclass
class Transcript:
    text: str
    avg_logprob: float | None
    no_speech_prob: float | None


def device_info() -> dict:
    try:
        import torch

        if torch.cuda.is_available():
            return {"device": "cuda", "name": torch.cuda.get_device_name(0)}
    except Exception:
        pass
    return {"device": "cpu", "name": f"{os.cpu_count()} CPU threads"}


def get_model(name: str):
    with _lock:
        if name not in _models:
            from faster_whisper import WhisperModel

            cuda = device_info()["device"] == "cuda"
            _models[name] = WhisperModel(
                name,
                device="cuda" if cuda else "cpu",
                compute_type="float16" if cuda else "int8",
                # Measured on an 8-thread laptop: 6 threads beat 4 and 8 (hyper-threads contend).
                cpu_threads=max(2, int((os.cpu_count() or 4) * 0.75)),
            )
        return _models[name]


def transcribe(audio: np.ndarray, sr: int, model_name: str, beam_size: int = 3) -> Transcript:
    """Transcribe one already-segmented clip. VAD is off because clips are pre-segmented."""
    if sr != 16000:
        g = math.gcd(sr, 16000)
        audio = resample_poly(audio, 16000 // g, sr // g).astype("float32")
    model = get_model(model_name)
    segments, _info = model.transcribe(
        audio,
        language="ur",
        task="transcribe",
        beam_size=beam_size,
        condition_on_previous_text=False,
        vad_filter=False,
        without_timestamps=True,
        # Cap generation per internal ~30 s decode window (faster-whisper slides a 30 s window over
        # longer clips): enough budget for a full window of dense speech, short of the pathological
        # ~448-token runaway loop on silence/noise (very slow on CPU).
        max_new_tokens=int(min(440, 14 * min(len(audio) / 16000, 30.0) + 24)),
        temperature=[0.0, 0.3],
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
    )
    parts, logprobs, no_speech = [], [], []
    for seg in segments:
        parts.append(seg.text.strip())
        logprobs.append(seg.avg_logprob)
        no_speech.append(seg.no_speech_prob)
    return Transcript(
        text=" ".join(p for p in parts if p),
        avg_logprob=float(np.mean(logprobs)) if logprobs else None,
        no_speech_prob=float(max(no_speech)) if no_speech else None,
    )
