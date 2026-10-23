from __future__ import annotations

import json
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from .. import config
from ..pipeline import transcribe
from . import aligner, check, source, text, timing
from .build import WEAK_SCORE, BuildItem, build_dataset
from .models import Profile
from .source import SourceError, SourceScan

Emit = Callable[..., None]
KINDS = ("ok", "fixed", "check", "bad")


class TextState:
    def __init__(self, scan: SourceScan, lower: bool, edits: Callable[[], dict]) -> None:
        self.scan = scan
        self.lower = lower
        self.edits = edits
        self.lexicon = text.build_lexicon([(r.urdu, r.roman) for r in scan.recordings], lower)
        self.pairs: dict[str, text.RecordingPair] = {}

    def pair(self, rec: source.SourceRecording) -> text.RecordingPair:
        cached = self.pairs.get(rec.key)
        if cached is None:
            cached = self.pairs[rec.key] = text.pair_recording(rec.urdu, rec.roman, self.lexicon, self.lower, self.edits().get(rec.key))
        return cached

    def forget(self, key: str) -> None:
        self.pairs.pop(key, None)


class AssignmentService:
    def __init__(self, root: Path, store) -> None:
        self.root = root
        self.store = store
        self.lock = threading.RLock()
        self.scan_cache: tuple[str, SourceScan] | None = None
        self.text_cache: tuple[tuple[str, bool], TextState] | None = None
        self.source_error: str | None = None

    @property
    def profile_path(self) -> Path:
        return self.root / "profile.json"

    @property
    def edits_path(self) -> Path:
        return self.root / "edits.json"

    @property
    def align_dir(self) -> Path:
        return self.root / "align"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def report_path(self) -> Path:
        return self.root / "report.json"

    def profile(self) -> Profile:
        if self.profile_path.is_file():
            try:
                return Profile.model_validate_json(self.profile_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return Profile()

    def save_profile(self, profile: Profile) -> Profile:
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            self.profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            if self.text_cache and (self.text_cache[0][1] != profile.lowercase_roman):
                self.text_cache = None
            if self.scan_cache and self.scan_cache[0] != str(self.folder(profile)):
                self.scan_cache = None
                self.text_cache = None
                self.source_error = None
        return profile

    def edits(self) -> dict:
        if self.edits_path.is_file():
            try:
                return json.loads(self.edits_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        return {}

    def choices(self) -> list[dict]:
        found: list[dict] = []
        default = source.default_folder()
        if default.is_dir():
            found.append({"label": "The dataset folder in the app folder", "path": str(default)})
        for project in self.store.list():
            export = self.store.project_dir(project.id) / "output" / "dataset"
            if (export / "wavs").is_dir():
                found.append({"label": f"Export of the project {project.name}", "path": str(export)})
        return found

    def folder(self, profile: Profile) -> Path:
        if profile.source_path.strip():
            return source.resolve_folder(profile.source_path)
        choices = self.choices()
        return Path(choices[0]["path"]) if choices else source.default_folder()

    def scan(self, profile: Profile, force: bool = False) -> SourceScan:
        with self.lock:
            folder = self.folder(profile)
            if not force and self.scan_cache and self.scan_cache[0] == str(folder):
                return self.scan_cache[1]
            try:
                result = source.scan(folder)
            except SourceError as exc:
                self.scan_cache = None
                self.text_cache = None
                self.source_error = str(exc)
                raise
            self.source_error = None
            self.scan_cache = (str(folder), result)
            self.text_cache = None
            return result

    def texts(self, profile: Profile) -> TextState:
        with self.lock:
            scan = self.scan(profile)
            key = (str(scan.folder), profile.lowercase_roman)
            if self.text_cache is None or self.text_cache[0] != key:
                self.text_cache = (key, TextState(scan, profile.lowercase_roman, self.edits))
            return self.text_cache[1]

    def used(self, profile: Profile) -> list[tuple[int, source.SourceRecording]]:
        scan = self.scan(profile)
        return list(enumerate(scan.recordings[: profile.total], start=1))

    def summary(self, profile: Profile) -> dict | None:
        if self.text_cache is None and self.scan_cache is None:
            return None
        state = self.texts(profile)
        recordings: Counter[str] = Counter()
        sentences: Counter[str] = Counter()
        words = 0
        for _number, rec in self.used(profile):
            pair = state.pair(rec)
            recordings[text.recording_status(pair)] += 1
            if pair.problem:
                sentences["bad"] += 1
            for sentence in pair.sentences:
                sentences["bad" if text.sentence_bad(sentence) else sentence.status] += 1
                words += len(sentence.urdu)
        return {
            "recordings": {k: recordings[k] for k in KINDS},
            "sentences": {k: sentences[k] for k in KINDS},
            "words": words,
        }

    def source_info(self, profile: Profile) -> dict | None:
        if self.scan_cache is None:
            return None
        scan = self.scan_cache[1]
        used = min(len(scan.recordings), profile.total)
        return {
            "folder": str(scan.folder),
            "found": len(scan.recordings),
            "used": used,
            "short_by": max(0, profile.total - len(scan.recordings)),
            "sample_rates": scan.sample_rates,
            "min_seconds": round(min(scan.durations), 2),
            "max_seconds": round(max(scan.durations), 2),
            "missing_audio": len(scan.missing_audio),
            "empty_text": len(scan.empty_text),
            "metadata_file": scan.metadata_file,
        }

    def words_of(self, pair: text.RecordingPair) -> list[str]:
        return [w for sentence in pair.sentences for w in sentence.urdu]

    def timing_state(self, profile: Profile) -> dict:
        if self.scan_cache is None:
            return {"done": 0, "total": 0, "weak": 0}
        state = self.texts(profile)
        done = weak = 0
        used = self.used(profile)
        for _number, rec in used:
            pair = state.pair(rec)
            if pair.problem or not pair.sentences:
                continue
            cached = aligner.load_cached(self.align_dir, rec.key, self.words_of(pair))
            if cached is not None:
                done += 1
                weak += cached[1] < WEAK_SCORE
        return {"done": done, "total": len(used), "weak": int(weak)}

    def reports(self) -> dict:
        if self.report_path.is_file():
            try:
                return json.loads(self.report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        return {}

    def save_reports(self, **updates) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = self.reports()
        data.update(updates)
        self.report_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def zip_info(self, profile: Profile) -> dict | None:
        if profile.roll_no is None:
            return None
        path = self.output_dir / f"{profile.sid}.zip"
        if not path.is_file():
            return None
        return {"name": path.name, "size_mb": round(path.stat().st_size / 1e6, 1)}

    def official_script(self) -> Path | None:
        return check.find_official([self.root, config.ROOT_DIR, config.DATA_DIR])

    def state(self, running: str | None) -> dict:
        profile = self.profile()
        info = self.source_info(profile)
        try:
            summary = self.summary(profile)
        except SourceError:
            summary = None
        reports = self.reports()
        device = transcribe.device_info()
        return {
            "profile": json.loads(profile.model_dump_json()),
            "id": profile.sid if profile.roll_no is not None else None,
            "missing": profile.missing(),
            "device": device["device"],
            "device_name": device["name"],
            "running": running,
            "source": info,
            "source_error": self.source_error,
            "text": summary,
            "timing": self.timing_state(profile) if info else {"done": 0, "total": 0, "weak": 0},
            "build": reports.get("build"),
            "check": reports.get("check"),
            "zip": self.zip_info(profile),
            "choices": self.choices(),
            "official_checker": self.official_script() is not None,
        }

    def rescan(self) -> dict:
        profile = self.profile()
        self.scan(profile, force=True)
        self.texts(profile)
        return {}

    def item(self, profile: Profile, rec: source.SourceRecording, number: int, index: int | None, pair: text.RecordingPair) -> dict | None:
        edits = self.edits().get(rec.key) or {}
        if index is None:
            if not pair.problem:
                return None
            u_text = (edits.get("whole") or {}).get("urdu", rec.urdu)
            r_text = (edits.get("whole") or {}).get("roman", rec.roman)
            return {
                "key": rec.key, "number": number, "scope": "recording", "sentence": None, "status": "bad", "reason": pair.problem,
                "urdu": u_text, "roman": r_text, "pairs": [],
                "urdu_count": len(text.urdu_words(u_text)), "roman_count": sum(len(a.text) > 0 for a in text.roman_atoms(r_text, False)),
            }
        sentence = pair.sentences[index]
        bad = text.sentence_bad(sentence)
        if not bad and sentence.status != "check":
            return None
        reason = "too_many" if len(sentence.urdu) > text.MAX_WORDS else "counts"
        roman_text = sentence.source_roman if bad else " ".join(sentence.roman)
        return {
            "key": rec.key, "number": number, "scope": "sentence", "sentence": index, "status": "bad" if bad else "check", "reason": reason,
            "urdu": sentence.source_urdu, "roman": roman_text, "pairs": [] if bad else [[u, r] for u, r in zip(sentence.urdu, sentence.roman)],
            "urdu_count": len(sentence.urdu), "roman_count": len(text.roman_atoms(sentence.source_roman, False)),
        }

    def problems(self, kind: str, offset: int, limit: int) -> dict:
        profile = self.profile()
        state = self.texts(profile)
        items: list[dict] = []
        for number, rec in self.used(profile):
            pair = state.pair(rec)
            if pair.problem:
                if kind == "bad":
                    items.append(self.item(profile, rec, number, None, pair))
                continue
            for index in range(len(pair.sentences)):
                entry = self.item(profile, rec, number, index, pair)
                if entry and entry["status"] == kind:
                    items.append(entry)
        return {"total": len(items), "items": items[offset: offset + limit]}

    def edit(self, key: str, sentence: int | None, urdu: str, roman: str) -> dict:
        profile = self.profile()
        state = self.texts(profile)
        found = next(((n, r) for n, r in self.used(profile) if r.key == key), None)
        if found is None:
            raise KeyError(key)
        number, rec = found
        with self.lock:
            data = self.edits()
            entry = data.setdefault(key, {})
            if sentence is None:
                entry["whole"] = {"urdu": urdu, "roman": roman}
                entry.pop("sentences", None)
            else:
                entry.setdefault("sentences", {})[str(sentence)] = {"urdu": urdu, "roman": roman}
            self.root.mkdir(parents=True, exist_ok=True)
            self.edits_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            state.forget(key)
        pair = state.pair(rec)
        if sentence is None or pair.problem:
            return self.item(profile, rec, number, None, pair) or {"removed": True}
        if sentence >= len(pair.sentences):
            return {"removed": True}
        return self.item(profile, rec, number, sentence, pair) or {"removed": True}

    def prepared(self, profile: Profile, emit: Emit, cancel: threading.Event, start: float, span: float, redo: bool) -> list[BuildItem]:
        state = self.texts(profile)
        used = self.used(profile)
        items: list[BuildItem] = []
        todo = []
        for number, rec in used:
            pair = state.pair(rec)
            if pair.problem or not pair.sentences or any(text.sentence_bad(s) for s in pair.sentences):
                raise RuntimeError(f"Recording R{number:03d} still has a sentence that needs a fix.")
            words = self.words_of(pair)
            cached = None if redo else aligner.load_cached(self.align_dir, rec.key, words)
            todo.append((number, rec, pair, words, cached))
        missing = sum(1 for t in todo if t[4] is None)
        finished = 0
        for number, rec, pair, words, cached in todo:
            if cancel.is_set():
                raise InterruptedError("cancelled")
            if cached is None:
                emit("timing", f"Finding word timings: recording {number} of {len(todo)}", start + span * finished / max(1, missing), done=finished, total=missing)
                audio = timing.load_audio(rec.wav)
                spans, score = aligner.align(audio, words)
                aligner.save_cached(self.align_dir, rec.key, words, spans, score)
                cached = (spans, score)
                finished += 1
            items.append(BuildItem(number, rec.key, rec.wav, pair, cached[0], cached[1]))
        return items

    def run_timing(self, emit: Emit, cancel: threading.Event, redo: bool = False) -> None:
        profile = self.profile()
        self.prepared(profile, emit, cancel, 0.0, 1.0, redo)
        emit("done", "Word timings are ready.", 1.0)

    def run_build(self, emit: Emit, cancel: threading.Event) -> None:
        profile = self.profile()
        gaps = profile.missing()
        if gaps:
            raise RuntimeError("Finish these first: " + ", ".join(gaps) + ".")
        pending = self.timing_state(profile)
        needs_timing = pending["done"] < pending["total"]
        share = 0.55 if needs_timing else 0.0
        items = self.prepared(profile, emit, cancel, 0.0, share, False)

        def progress(done: int, total: int) -> None:
            emit("build", f"Writing recording {done} of {total}", share + (0.9 - share) * done / total, done=done, total=total)

        result = build_dataset(profile, items, self.output_dir, progress, cancel)
        self.save_reports(build={
            "seconds": {k: round(v, 1) for k, v in result.seconds.items()},
            "counts": result.counts,
            "weak": result.weak,
            "finished": int(time.time()),
        })
        emit("check", "Checking the finished dataset", 0.92)
        self.save_reports(check=self.check_now(profile))
        emit("done", "The dataset is built and checked.", 1.0)

    def check_now(self, profile: Profile) -> dict:
        folder = self.output_dir / profile.sid
        if not folder.is_dir():
            raise RuntimeError("Build the dataset first.")
        report = check.validate_folder(folder, profile.total, profile.train)
        official = None
        script = self.official_script()
        zip_path = self.output_dir / f"{profile.sid}.zip"
        if script is not None and zip_path.is_file():
            try:
                official = check.run_official(script, zip_path, profile.total)
            except Exception as exc:
                official = {"script": str(script), "output": f"The official checker could not run: {exc}", "ok": False}
        report["official"] = official
        return report

    def run_check(self, emit: Emit, cancel: threading.Event) -> None:
        profile = self.profile()
        emit("check", "Checking the finished dataset", 0.1)
        self.save_reports(check=self.check_now(profile))
        emit("done", "The check is finished.", 1.0)
