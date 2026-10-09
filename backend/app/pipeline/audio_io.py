"""ffmpeg decoding and wav helpers."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

WORK_SR = 44100  # working copy is 44.1 kHz mono: exact 441:160 ratio to the 16 kHz VAD/ASR rate
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def ffmpeg_exe() -> str:
    override = os.environ.get("FFMPEG_PATH")
    if override:
        return override
    import imageio_ffmpeg  # bundled static binary, so no system ffmpeg install is needed

    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_to_wav(
    src: Path, dst: Path, sr: int = WORK_SR, cancel: threading.Event | None = None
) -> None:
    """Decode any audio/video container to mono 16-bit PCM wav (RF64 if > 4 GB)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".part.wav")
    err_path = dst.with_name(dst.stem + ".ffmpeg.log")
    cmd = [
        ffmpeg_exe(), "-nostdin", "-y", "-v", "error",
        "-i", str(src), "-vn", "-map", "0:a:0",
        "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", "-rf64", "auto",
        str(tmp),
    ]
    with open(err_path, "w", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(cmd, stderr=err, stdout=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        while proc.poll() is None:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.wait()
                tmp.unlink(missing_ok=True)
                raise InterruptedError("cancelled")
            time.sleep(0.25)
    if proc.returncode != 0:
        message = err_path.read_text(encoding="utf-8", errors="replace")[-600:]
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg could not decode this file: {message.strip() or 'unknown error'}")
    err_path.unlink(missing_ok=True)
    os.replace(tmp, dst)


def wav_duration(path: Path) -> float:
    info = sf.info(str(path))
    return info.frames / info.samplerate


def read_span(path: Path, start_s: float, end_s: float) -> tuple[np.ndarray, int]:
    """Read [start_s, end_s) of a mono wav as float32."""
    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        f.seek(max(0, int(start_s * sr)))
        data = f.read(max(0, int((end_s - start_s) * sr)), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(audio, -1.0, 1.0), sr, subtype="PCM_16")
