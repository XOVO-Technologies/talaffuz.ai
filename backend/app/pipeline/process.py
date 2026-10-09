"""Job bodies: analyse sources into clips, process clips, romanize."""
from __future__ import annotations

import math
import threading
import uuid
from typing import Callable

from ..models import Clip
from ..store import ProjectStore
from . import enhance, romanize, segmenter, transcribe
from .audio_io import decode_to_wav, wav_duration, write_wav
from .text_ur import assess_transcript, normalize_urdu

Emit = Callable[..., None]  # emit(stage, message=None, progress=None, **extra)


def _analyze_source(store: ProjectStore, pid: str, src_id: str, emit: Emit, cancel: threading.Event) -> None:
    project = store.get(pid)
    src = next(x for x in project.sources if x.id == src_id)
    s = project.settings
    pdir = store.project_dir(pid)
    with store.edit(pid) as live:
        next(x for x in live.sources if x.id == src_id).status = "analyzing"
    try:
        work = pdir / "work" / f"{src.id}.wav"
        if not work.exists():
            emit("decode", f"Decoding {src.name} …")
            decode_to_wav(pdir / src.path, work, cancel=cancel)
        duration = wav_duration(work)
        emit("segment", f"Finding speech in {src.name} ({duration / 60:.1f} min) …", progress=0.0)
        spans = segmenter.detect_speech(work, s, progress=lambda f: emit("segment", progress=f), cancel=cancel)
        packed = segmenter.pack_clips(spans, s, duration)
        with store.edit(pid) as live:
            base = max((c.order for c in live.clips), default=-1) + 1
            live.clips.extend(
                Clip(id=uuid.uuid4().hex[:8], source_id=src_id, order=base + i,
                     start_s=a, end_s=b, duration_s=round(b - a, 2))
                for i, (a, b) in enumerate(packed)
            )
            live_src = next(x for x in live.sources if x.id == src_id)
            live_src.status, live_src.duration_s, live_src.work_wav, live_src.error = "analyzed", duration, f"work/{src.id}.wav", None
        emit("segment", f"{src.name}: {len(packed)} candidate clips from {duration / 60:.1f} min of audio", progress=1.0)
    except InterruptedError:
        with store.edit(pid) as live:
            next(x for x in live.sources if x.id == src_id).status = "uploaded"
        raise
    except Exception as exc:
        with store.edit(pid) as live:
            live_src = next(x for x in live.sources if x.id == src_id)
            live_src.status, live_src.error = "error", str(exc)[:400]
        emit("warning", f"{src.name} failed: {exc}")


MUSIC_PROBES = 3  # clips per recording that run the separator before "auto" decides
MUSIC_THRESHOLD_DB = -16.0  # separator removed more than this (relative to the voice) => music is present


class _MusicProbe:
    """Per-recording decision for remove_music == "auto": the separator costs ~3x real time on CPU,
    so run it on a few clips, measure what it removes, and skip it for the rest if that is negligible."""

    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = {}
        self.decided: dict[str, bool] = {}

    def use_separator(self, mode: str, src_id: str) -> bool:
        if mode != "auto":
            return mode == "on"
        return self.decided.get(src_id, True)  # undecided: run it and measure

    def record(self, mode: str, src_id: str, music_db: float | None, name: str, emit: Emit) -> None:
        if mode != "auto" or music_db is None or src_id in self.decided:
            return
        samples = self.samples.setdefault(src_id, [])
        samples.append(music_db)
        if len(samples) >= MUSIC_PROBES:
            median = sorted(samples)[len(samples) // 2]
            self.decided[src_id] = median > MUSIC_THRESHOLD_DB
            emit("process", f"{name}: " + (
                f"background music found ({median:.0f} dB), removing it from every clip" if self.decided[src_id]
                else f"no background music found ({median:.0f} dB), skipping the slow separator"))


def _process_clip(store: ProjectStore, pid: str, clip: Clip, use_separator: bool) -> float | None:
    project = store.get(pid)
    s = project.settings
    pdir = store.project_dir(pid)
    src = next(x for x in project.sources if x.id == clip.source_id)
    try:
        proc = enhance.process_clip(pdir / src.work_wav, clip.start_s, clip.end_s, s, use_separator)
        rel = f"clips/{clip.id}.wav"
        write_wav(pdir / rel, proc.audio, proc.sr)
        duration = len(proc.audio) / proc.sr
        heard = transcribe.transcribe(proc.audio, proc.sr, s.whisper_model, s.whisper_beam)
        urdu = normalize_urdu(heard.text)
        flags, reject = assess_transcript(urdu, duration, heard.avg_logprob, heard.no_speech_prob)
        with store.edit(pid) as live:
            c = next(x for x in live.clips if x.id == clip.id)
            c.status, c.wav, c.duration_s, c.snr_db = "processed", rel, round(duration, 2), proc.snr_db
            c.asr_confidence = round(math.exp(heard.avg_logprob), 3) if heard.avg_logprob is not None else None
            c.flags = proc.flags + flags
            if not c.edited and not c.urdu:
                c.urdu = urdu
            c.keep = not reject
        return proc.music_db
    except InterruptedError:
        raise
    except Exception as exc:
        with store.edit(pid) as live:
            c = next(x for x in live.clips if x.id == clip.id)
            c.status, c.keep, c.error = "error", False, str(exc)[:300]
        return None


def run_process(store: ProjectStore, pid: str, emit: Emit, cancel: threading.Event, extra: int = 0) -> None:
    for src in [x for x in store.get(pid).sources if x.status in ("uploaded", "error")]:
        _analyze_source(store, pid, src.id, emit, cancel)

    project = store.get(pid)
    s = project.settings
    good = sum(1 for c in project.clips if c.status == "processed" and c.keep)
    # With a last file number: enough good clips for every slot plus a buffer ("process more" adds `extra`).
    # Without one there is no target, so every candidate clip is processed.
    goal: int | None
    if extra:
        goal = good + extra
    elif s.capacity is not None:
        goal = math.ceil(s.capacity * (1 + s.buffer_pct / 100))
    else:
        goal = None
    emit("process", "Loading models (the first run downloads them) …", progress=0.0)
    probe = _MusicProbe()
    while True:
        if cancel.is_set():
            raise InterruptedError("cancelled")
        project = store.get(pid)
        good = sum(1 for c in project.clips if c.status == "processed" and c.keep)
        if goal is not None and good >= goal:
            break
        nxt = next((c for c in sorted(project.clips, key=lambda c: c.order) if c.status == "pending"), None)
        if nxt is None:
            break
        music_db = _process_clip(store, pid, nxt, probe.use_separator(s.remove_music, nxt.source_id))
        src_name = next(x.name for x in project.sources if x.id == nxt.source_id)
        probe.record(s.remove_music, nxt.source_id, music_db, src_name, emit)
        clips_now = store.get(pid).clips
        if goal is not None:
            done = sum(1 for c in clips_now if c.status == "processed" and c.keep)
            emit("process", f"Cleaned and transcribed {done} of {goal} good clips", progress=min(1.0, done / goal),
                 done=done, total=goal)
        else:
            done = sum(1 for c in clips_now if c.status != "pending")
            total = len(clips_now)
            emit("process", f"Cleaned and transcribed {done} of {total} clips", progress=min(1.0, done / total),
                 done=done, total=total)

    project = store.get(pid)
    ready = sum(1 for c in project.clips if c.status == "processed" and c.keep)
    pending = sum(1 for c in project.clips if c.status == "pending")
    if s.auto_romanize and romanize.is_available() and ready:
        run_romanize(store, pid, emit, cancel, only_missing=True)
    else:
        emit("done", f"{ready} clips ready for review ({pending} more candidates not processed yet)."
             + ("" if romanize.is_available() else " Next: type /romanize in Claude Code or $romanize in Codex to write the Roman Urdu column."),
             ready=ready, pending=pending)


def run_romanize(store: ProjectStore, pid: str, emit: Emit, cancel: threading.Event, only_missing: bool = True) -> None:
    if not romanize.is_available():
        raise RuntimeError("No Anthropic API key is configured. Use /romanize in Claude Code or $romanize in Codex instead.")
    project = store.get(pid)
    todo = {
        c.id: c.urdu
        for c in project.clips
        if c.keep and c.status == "processed" and c.urdu.strip() and (not only_missing or not c.roman.strip())
    }
    emit("romanize", f"Converting {len(todo)} sentences to Roman Urdu …", progress=0.0)
    results, failed = romanize.romanize_all(
        todo,
        progress=lambda d, t: emit("romanize", f"Roman Urdu {d} of {t}", progress=d / t, done=d, total=t),
        cancelled=cancel.is_set,
    )
    with store.edit(pid) as live:
        for c in live.clips:
            if c.id in results and not (only_missing and c.roman.strip()):
                c.roman = results[c.id]
    ready = sum(1 for c in store.get(pid).clips if c.status == "processed" and c.keep)
    note = f" {len(failed)} sentences could not be converted; retry or type them in." if failed else ""
    emit("done", f"{ready} clips ready for review.{note}", ready=ready, failed=len(failed))
