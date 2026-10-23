from __future__ import annotations

import csv
import shutil
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .docs import experience_text, readme_text
from .ids import LEVELS, SPLITS, recording_file, recording_id, sentence_file, sentence_id, split_of, word_file, word_id
from .models import Profile
from .text import RecordingPair, render_recording
from .timing import TARGET_SR, Timing, load_audio, time_recording

RECORDING_COLUMNS = ["file_name", "speaker_id", "section", "roll_no", "gender", "recording_id", "duration_sec", "urdu_text", "roman_urdu_text"]
SENTENCE_COLUMNS = ["file_name", "speaker_id", "section", "roll_no", "gender", "recording_id", "sentence_id", "start_sec", "end_sec", "duration_sec", "urdu_text", "roman_urdu_text"]
WORD_COLUMNS = ["file_name", "speaker_id", "section", "roll_no", "gender", "recording_id", "sentence_id", "word_id", "start_sec", "end_sec", "duration_sec", "urdu_word", "roman_urdu_word"]
WEAK_SCORE = 0.35
COLUMNS = {"recordings": RECORDING_COLUMNS, "sentences": SENTENCE_COLUMNS, "words": WORD_COLUMNS}


@dataclass
class BuildItem:
    number: int
    key: str
    wav: Path
    pair: RecordingPair
    spans: list[tuple[float, float]]
    score: float


@dataclass
class BuildResult:
    folder: Path
    zip_path: Path | None
    counts: dict[str, dict[str, int]]
    seconds: dict[str, float]
    weak: list[int] = field(default_factory=list)


def sec(value: float) -> str:
    return f"{value:.2f}"


def write_pcm(path: Path, audio: np.ndarray) -> None:
    sf.write(str(path), audio, TARGET_SR, subtype="PCM_16")


def cut(audio: np.ndarray, start: float, end: float) -> np.ndarray:
    return audio[int(round(start * TARGET_SR)):int(round(end * TARGET_SR))]


def write_csv(path: Path, columns: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def write_recording(profile: Profile, root: Path, item: BuildItem, audio: np.ndarray, timing: Timing, rows: dict[str, dict[str, list[list[str]]]], seconds: dict[str, float]) -> None:
    sid, r = profile.sid, item.number
    split = split_of(r, profile.train)
    base = [sid, profile.section, profile.roll, profile.gender, recording_id(r)]
    urdu_text, roman_text = render_recording(item.pair)
    name = recording_file(sid, r)
    write_pcm(root / "recordings" / split / name, audio)
    duration = round(len(audio) / TARGET_SR, 2)
    seconds["recordings"] += duration
    rows["recordings"][split].append([name, *base, sec(duration), urdu_text, roman_text])
    for s, sentence in enumerate(item.pair.sentences, start=1):
        start, end = timing.sentences[s - 1]
        sentence_name = sentence_file(sid, r, s)
        write_pcm(root / "sentences" / split / sentence_name, cut(audio, start, end))
        seconds["sentences"] += end - start
        rows["sentences"][split].append([sentence_name, *base, sentence_id(s), sec(start), sec(end), sec(round(end - start, 2)), " ".join(sentence.urdu), " ".join(sentence.roman)])
        for w, (u, ro) in enumerate(zip(sentence.urdu, sentence.roman), start=1):
            w_start, w_end = timing.words[s - 1][w - 1]
            word_name = word_file(sid, r, s, w)
            write_pcm(root / "words" / split / word_name, cut(audio, w_start, w_end))
            seconds["words"] += w_end - w_start
            rows["words"][split].append([word_name, *base, sentence_id(s), word_id(w), sec(w_start), sec(w_end), sec(round(w_end - w_start, 2)), u, ro])


def zip_folder(folder: Path, zip_path: Path) -> None:
    tmp = zip_path.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                kind = zipfile.ZIP_STORED if path.suffix == ".wav" else zipfile.ZIP_DEFLATED
                archive.write(path, f"{folder.name}/{path.relative_to(folder).as_posix()}", compress_type=kind)
    tmp.replace(zip_path)


def build_dataset(
    profile: Profile,
    items: list[BuildItem],
    out_root: Path,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    make_zip: bool = True,
) -> BuildResult:
    sid = profile.sid
    out_root.mkdir(parents=True, exist_ok=True)
    work = out_root / f".build_{sid}"
    if work.exists():
        shutil.rmtree(work)
    root = work / sid
    for level in LEVELS:
        for split in SPLITS:
            (root / level / split).mkdir(parents=True)
    rows: dict[str, dict[str, list[list[str]]]] = {level: {split: [] for split in SPLITS} for level in LEVELS}
    seconds = {level: 0.0 for level in LEVELS}
    weak: list[int] = []
    for index, item in enumerate(items):
        if cancel is not None and cancel.is_set():
            shutil.rmtree(work, ignore_errors=True)
            raise InterruptedError("cancelled")
        audio = load_audio(item.wav)
        final = [s.urdu for s in item.pair.sentences]
        timing = time_recording(final, item.spans, audio)
        if item.score < WEAK_SCORE:
            weak.append(item.number)
        write_recording(profile, root, item, audio, timing, rows, seconds)
        if progress is not None:
            progress(index + 1, len(items))
    for level in LEVELS:
        for split in SPLITS:
            write_csv(root / level / split / "metadata.csv", COLUMNS[level], rows[level][split])
    counts = {level: {split: len(rows[level][split]) for split in SPLITS} for level in LEVELS}
    (root / "README.md").write_text(readme_text(profile, counts), encoding="utf-8", newline="\n")
    (root / "EXPERIENCE.md").write_text(experience_text(profile), encoding="utf-8", newline="\n")
    final_folder = out_root / sid
    if final_folder.exists():
        shutil.rmtree(final_folder)
    root.replace(final_folder)
    shutil.rmtree(work, ignore_errors=True)
    zip_path = None
    if make_zip:
        zip_path = out_root / f"{sid}.zip"
        zip_folder(final_folder, zip_path)
    return BuildResult(final_folder, zip_path, counts, seconds, weak)
