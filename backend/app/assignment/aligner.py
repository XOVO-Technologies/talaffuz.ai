from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

import numpy as np

_lock = threading.Lock()
_loaded: dict = {}
_romanised: dict[str, str] = {}


def load() -> dict:
    with _lock:
        if not _loaded:
            import torch
            import torchaudio
            import uroman

            bundle = torchaudio.pipelines.MMS_FA
            device = "cuda" if torch.cuda.is_available() else "cpu"
            _loaded.update(
                torch=torch,
                device=device,
                model=bundle.get_model(with_star=False).to(device).eval(),
                tokenizer=bundle.get_tokenizer(),
                aligner=bundle.get_aligner(),
                roman=uroman.Uroman(),
            )
    return _loaded


def romanize(word: str) -> str:
    cached = _romanised.get(word)
    if cached is None:
        raw = load()["roman"].romanize_string(word, lcode="urd").lower()
        cached = _romanised[word] = re.sub(r"[^a-z]", "", raw) or "a"
    return cached


def align(audio: np.ndarray, words: list[str], sample_rate: int = 16000) -> tuple[list[tuple[float, float]], float]:
    ctx = load()
    torch = ctx["torch"]
    wave = torch.from_numpy(audio).unsqueeze(0).to(ctx["device"])
    with torch.inference_mode():
        emission, _ = ctx["model"](wave)
    emission = emission[0].float().cpu()
    spans = ctx["aligner"](emission, ctx["tokenizer"]([romanize(w) for w in words]))
    scale = len(audio) / sample_rate / emission.size(0)
    placed = [(word[0].start * scale, word[-1].end * scale) for word in spans]
    scores = [float(np.mean([t.score for t in word])) for word in spans]
    return placed, float(np.mean(scores)) if scores else 0.0


def words_hash(words: list[str]) -> str:
    return hashlib.sha1("\n".join(words).encode("utf-8")).hexdigest()[:16]


def cache_file(folder: Path, key: str) -> Path:
    return folder / f"{key}.json"


def load_cached(folder: Path, key: str, words: list[str]) -> tuple[list[tuple[float, float]], float] | None:
    path = cache_file(folder, key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("hash") != words_hash(words) or len(data.get("spans", [])) != len(words):
        return None
    return [(s, e) for s, e in data["spans"]], float(data.get("score", 0.0))


def save_cached(folder: Path, key: str, words: list[str], spans: list[tuple[float, float]], score: float) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"hash": words_hash(words), "score": round(score, 4), "spans": [[round(s, 4), round(e, 4)] for s, e in spans]}
    path = cache_file(folder, key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
