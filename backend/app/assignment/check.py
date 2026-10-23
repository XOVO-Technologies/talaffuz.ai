from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf

from .ids import ID_PATTERN, LEVELS, RECORDING_FILE, SENTENCE_FILE, SPLITS, WORD_FILE
from .build import COLUMNS

NUMBER = re.compile(r"^\d+(\.\d{1,2})?$")
ROMAN_WORD = re.compile(r"^[A-Za-z]+$")
DIGITS = re.compile("[0-9٠-٩۰-۹]")
TOLERANCE = 0.021
PER_KIND = 4
OFFICIAL_OK = "OK - koi ghalti nahi mili"


class Collector:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.seen: Counter[str] = Counter()

    def error(self, kind: str, message: str) -> None:
        self.seen[kind] += 1
        if self.seen[kind] <= PER_KIND:
            self.errors.append(message)
        elif self.seen[kind] == PER_KIND + 1:
            self.errors.append(f"More problems of this kind were found: {kind}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def urdu_clean(text: str) -> bool:
    body = text.replace("۔", "").replace(" ", "")
    return bool(body) and all(unicodedata.category(ch)[0] in "LM" for ch in body) and not DIGITS.search(body)


def roman_clean(text: str) -> bool:
    body = text.replace(".", " ")
    words = body.split()
    return bool(words) and all(ROMAN_WORD.match(w) for w in words) and not re.search(r"\.\S", text) and not re.search(r"(^|\s)\.", text)


def read_rows(path: Path, level: str, c: Collector) -> list[dict[str, str]]:
    if not path.is_file():
        c.error("missing", f"Missing file: {path.parent.parent.name}/{path.parent.name}/metadata.csv")
        return []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        c.error("bom", f"{path.parent.parent.name}/{path.parent.name}/metadata.csv starts with a byte order mark.")
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS[level]:
            c.error("columns", f"{level}/{path.parent.name}/metadata.csv has the wrong columns.")
        return list(reader)


def check_audio(folder: Path, level: str, split: str, rows: list[dict[str, str]], c: Collector) -> dict[str, float]:
    lengths: dict[str, float] = {}
    on_disk = {p.name for p in (folder / level / split).glob("*") if p.is_file() and p.name != "metadata.csv"}
    named = [r["file_name"] for r in rows]
    for name in sorted(on_disk - set(named)):
        c.error("orphan", f"{level}/{split}/{name} is not listed in metadata.csv.")
    for name, count in Counter(named).items():
        if count > 1:
            c.error("duplicate", f"{level}/{split}/metadata.csv lists {name} {count} times.")
    for name in named:
        path = folder / level / split / name
        if not path.is_file():
            c.error("missing", f"{level}/{split}/{name} is listed in metadata.csv but the file is missing.")
            continue
        if not name.endswith(".wav"):
            c.error("extension", f"{level}/{split}/{name} does not end with .wav.")
        try:
            info = sf.info(str(path))
        except Exception:
            c.error("audio", f"{level}/{split}/{name} is not a readable audio file.")
            continue
        if info.format != "WAV" or info.samplerate != 16000 or info.channels != 1 or info.subtype != "PCM_16":
            c.error("audio", f"{level}/{split}/{name} is not WAV, 16000 Hz, mono, 16-bit PCM.")
        lengths[name] = info.frames / info.samplerate
    return lengths


def number_ok(value: str) -> bool:
    return bool(NUMBER.match(value or ""))


def validate_folder(folder: Path, expect_total: int, expect_train: int) -> dict:
    c = Collector()
    sid = folder.name
    match = ID_PATTERN.match(sid)
    if not match:
        c.error("id", f"The folder name {sid} is not a valid ID such as 7C_042_M.")
        return {"ok": False, "errors": c.errors, "warnings": c.warnings, "counts": {}}
    section, roll, gender = match.groups()
    for name in ("README.md", "EXPERIENCE.md"):
        if not (folder / name).is_file():
            c.error("missing", f"Missing file: {name}")
    for extra in sorted(p.name for p in folder.iterdir()):
        if extra not in ("README.md", "EXPERIENCE.md", *LEVELS):
            c.error("extra", f"Unexpected item in the dataset folder: {extra}")

    rows: dict[str, dict[str, list[dict[str, str]]]] = {}
    lengths: dict[str, dict[str, dict[str, float]]] = {}
    for level in LEVELS:
        rows[level], lengths[level] = {}, {}
        for split in SPLITS:
            rows[level][split] = read_rows(folder / level / split / "metadata.csv", level, c)
            lengths[level][split] = check_audio(folder, level, split, rows[level][split], c)

    counts = {level: {split: len(rows[level][split]) for split in SPLITS} for level in LEVELS}
    total = counts["recordings"]["train"] + counts["recordings"]["test"]
    if total != expect_total:
        c.error("count", f"Expected {expect_total} recordings but found {total}.")
    if counts["recordings"]["train"] != expect_train:
        c.error("count", f"Expected {expect_train} recordings in train but found {counts['recordings']['train']}.")

    rec_info: dict[int, tuple[str, float]] = {}
    rec_text: dict[int, tuple[str, str]] = {}
    for split in SPLITS:
        for row in rows["recordings"][split]:
            name = row["file_name"]
            m = RECORDING_FILE.match(name)
            if not m or m["id"] != sid:
                c.error("name", f"Bad recording file name: {name}")
                continue
            r = int(m["r"])
            expected = "train" if r <= expect_train else "test"
            if split != expected:
                c.error("split", f"{name} is in {split} but belongs in {expected}.")
            duration = lengths["recordings"][split].get(name)
            rec_info[r] = (split, duration if duration is not None else 0.0)
            rec_text[r] = (row["urdu_text"], row["roman_urdu_text"])
            check_common(row, sid, section, roll, gender, f"R{r:03d}", name, c)
            if not number_ok(row["duration_sec"]):
                c.error("number", f"{name}: duration_sec is not a number with 2 decimals.")
            elif duration is not None and abs(float(row["duration_sec"]) - duration) > TOLERANCE:
                c.error("duration", f"{name}: duration_sec does not match the audio length.")
            u, ro = row["urdu_text"], row["roman_urdu_text"]
            if not urdu_clean(u):
                c.error("urdu", f"{name}: the Urdu text has digits, punctuation or other symbols.")
            if not roman_clean(ro):
                c.error("roman", f"{name}: the Roman Urdu text must use English letters only.")
            if len(u.replace("۔", " ").split()) != len(ro.replace(".", " ").split()):
                c.error("words", f"{name}: Urdu and Roman Urdu word counts differ.")
    expected_numbers = set(range(1, total + 1))
    if set(rec_info) != expected_numbers and total:
        c.error("numbering", "Recording numbers are not R001 up to the last recording without gaps.")

    sentences: dict[tuple[int, int], tuple[float, float, str, str]] = {}
    per_recording: dict[int, list[int]] = defaultdict(list)
    for split in SPLITS:
        for row in rows["sentences"][split]:
            name = row["file_name"]
            m = SENTENCE_FILE.match(name)
            if not m or m["id"] != sid:
                c.error("name", f"Bad sentence file name: {name}")
                continue
            r, s = int(m["r"]), int(m["s"])
            if r not in rec_info:
                c.error("parent", f"{name} has no recording {r:03d}.")
                continue
            if rec_info[r][0] != split:
                c.error("split", f"{name} is in {split} but its recording is in {rec_info[r][0]}.")
            check_common(row, sid, section, roll, gender, f"R{r:03d}", name, c)
            if row["sentence_id"] != f"S{s:02d}":
                c.error("ids", f"{name}: sentence_id does not match the file name.")
            if not all(number_ok(row[k]) for k in ("start_sec", "end_sec", "duration_sec")):
                c.error("number", f"{name}: times must be numbers with 2 decimals.")
                continue
            start, end, dur = float(row["start_sec"]), float(row["end_sec"]), float(row["duration_sec"])
            if end <= start or abs(dur - (end - start)) > 0.011:
                c.error("times", f"{name}: duration_sec must equal end_sec minus start_sec.")
            if end > rec_info[r][1] + 0.011:
                c.error("times", f"{name}: ends after the recording does.")
            length = lengths["sentences"][split].get(name)
            if length is not None and abs(length - dur) > TOLERANCE:
                c.error("duration", f"{name}: duration_sec does not match the audio length.")
            u, ro = row["urdu_text"], row["roman_urdu_text"]
            if not urdu_clean(u) or not roman_clean(ro):
                c.error("text", f"{name}: the text has symbols that are not allowed.")
            if len(u.split()) != len(ro.split()):
                c.error("words", f"{name}: Urdu and Roman Urdu word counts differ.")
            sentences[(r, s)] = (start, end, u, ro)
            per_recording[r].append(s)
    for r, numbers in per_recording.items():
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            c.error("numbering", f"Recording R{r:03d} sentences are not S01 up to the last one without gaps.")
        ordered = sorted(numbers)
        for a, b in zip(ordered, ordered[1:]):
            if sentences[(r, b)][0] < sentences[(r, a)][1] - 0.011:
                c.error("overlap", f"R{r:03d}: sentence S{b:02d} starts before S{a:02d} ends.")
        joined_u = " ".join(sentences[(r, s)][2] for s in ordered)
        joined_r = " ".join(sentences[(r, s)][3] for s in ordered)
        text_u, text_r = rec_text.get(r, ("", ""))
        if joined_u != " ".join(text_u.replace("۔", " ").split()) or joined_r.lower() != " ".join(text_r.replace(".", " ").split()).lower():
            c.error("consistency", f"R{r:03d}: the recording text is not the sentence texts joined together.")
    for r in rec_info:
        if r not in per_recording:
            c.error("numbering", f"Recording R{r:03d} has no sentences.")

    words_by_sentence: dict[tuple[int, int], list[tuple[int, str, str]]] = defaultdict(list)
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for split in SPLITS:
        for row in rows["words"][split]:
            name = row["file_name"]
            m = WORD_FILE.match(name)
            if not m or m["id"] != sid:
                c.error("name", f"Bad word file name: {name}")
                continue
            r, s, w = int(m["r"]), int(m["s"]), int(m["w"])
            if r not in rec_info or (r, s) not in sentences:
                c.error("parent", f"{name} has no parent sentence.")
                continue
            if rec_info[r][0] != split:
                c.error("split", f"{name} is in {split} but its recording is in {rec_info[r][0]}.")
            check_common(row, sid, section, roll, gender, f"R{r:03d}", name, c)
            if row["sentence_id"] != f"S{s:02d}" or row["word_id"] != f"W{w:02d}":
                c.error("ids", f"{name}: sentence_id or word_id does not match the file name.")
            if not all(number_ok(row[k]) for k in ("start_sec", "end_sec", "duration_sec")):
                c.error("number", f"{name}: times must be numbers with 2 decimals.")
                continue
            start, end, dur = float(row["start_sec"]), float(row["end_sec"]), float(row["duration_sec"])
            s_start, s_end = sentences[(r, s)][0], sentences[(r, s)][1]
            if end <= start or abs(dur - (end - start)) > 0.011:
                c.error("times", f"{name}: duration_sec must equal end_sec minus start_sec.")
            if start < s_start - 0.011 or end > s_end + 0.011:
                c.error("times", f"{name}: the word is not inside its sentence.")
            length = lengths["words"][split].get(name)
            if length is not None and abs(length - dur) > TOLERANCE:
                c.error("duration", f"{name}: duration_sec does not match the audio length.")
            uw, rw = row["urdu_word"], row["roman_urdu_word"]
            if not urdu_clean(uw) or " " in uw or not ROMAN_WORD.match(rw):
                c.error("text", f"{name}: a word must be one Urdu word and one Roman Urdu word with no punctuation.")
            words_by_sentence[(r, s)].append((w, uw, rw))
            spellings[uw][rw.lower()] += 1
    for (r, s), items in words_by_sentence.items():
        items.sort()
        if [w for w, _, _ in items] != list(range(1, len(items) + 1)):
            c.error("numbering", f"R{r:03d} S{s:02d}: word numbers are not W01 up to the last one without gaps.")
        if " ".join(u for _, u, _ in items) != sentences[(r, s)][2] or " ".join(x for _, _, x in items).lower() != sentences[(r, s)][3].lower():
            c.error("consistency", f"R{r:03d} S{s:02d}: the sentence text is not the word texts joined together.")
    for key in sentences:
        if key not in words_by_sentence:
            c.error("numbering", f"R{key[0]:03d} S{key[1]:02d} has no words.")

    check_word_overlap(rows["words"], c)
    check_readme(folder, sid, counts, c)
    check_experience(folder, sid, c)
    variants = [(u, v) for u, v in spellings.items() if len(v) > 1 and v.most_common(2)[1][1] >= 3]
    variants.sort(key=lambda item: -sum(item[1].values()))
    for u, v in variants[:6]:
        c.warn("Spelling varies for " + u + ": " + ", ".join(f"{k} ({n})" for k, n in v.most_common(3)))
    return {"ok": not c.errors, "errors": c.errors, "warnings": c.warnings, "counts": counts}


def check_common(row: dict[str, str], sid: str, section: str, roll: str, gender: str, rid: str, name: str, c: Collector) -> None:
    expected = {"speaker_id": sid, "section": section, "roll_no": roll, "gender": gender, "recording_id": rid}
    for key, value in expected.items():
        if row.get(key) != value:
            c.error("columns", f"{name}: {key} should be {value} but is {row.get(key)}.")


def check_word_overlap(words: dict[str, list[dict[str, str]]], c: Collector) -> None:
    by_recording: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for split in SPLITS:
        for row in words[split]:
            if number_ok(row["start_sec"]) and number_ok(row["end_sec"]):
                by_recording[row["recording_id"]].append((float(row["start_sec"]), float(row["end_sec"]), row["file_name"]))
    for rid, spans in by_recording.items():
        spans.sort()
        for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
            if b0 < a1 - 0.011:
                c.error("overlap", f"{an} and {bn} overlap in time.")


def check_readme(folder: Path, sid: str, counts: dict[str, dict[str, int]], c: Collector) -> None:
    path = folder / "README.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    front = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not front:
        c.error("readme", "README.md must start with a front matter block between --- lines.")
        return
    if not re.search(rf"^pretty_name:.*{re.escape(sid)}", front.group(1), re.M):
        c.error("readme", f"README.md pretty_name must contain {sid}.")
    for level in LEVELS:
        if f"config_name: {level}" not in front.group(1):
            c.error("readme", f"README.md has no config for {level}.")
        if f"data_dir: {level}" not in front.group(1):
            c.error("readme", f"README.md config {level} must point to data_dir: {level}.")
    for level in LEVELS:
        found = re.search(rf"^\|\s*{level}\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text, re.M)
        if not found or (int(found.group(1)), int(found.group(2))) != (counts[level]["train"], counts[level]["test"]):
            c.error("readme", f"The README counts table does not match the files for {level}.")
    for label in ("speaker_id", "name", "section", "roll_no", "gender", "recording_device", "recording_place", "recording_dates"):
        cell = re.search(rf"^\|\s*{label}\s*\|(.*)\|\s*$", text, re.M)
        if not cell or not cell.group(1).strip():
            c.error("readme", f"README.md speaker table: {label} is empty.")


def check_experience(folder: Path, sid: str, c: Collector) -> None:
    path = folder / "EXPERIENCE.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if sid not in text.splitlines()[0]:
        c.error("experience", f"EXPERIENCE.md must start with the heading for {sid}.")
    name = re.search(r"^\*\*Naam:\*\*[ \t]*(.*)$", text, re.M)
    if not name or not name.group(1).strip():
        c.error("experience", "EXPERIENCE.md: Naam is empty.")
    sections = re.split(r"^## (?=\d\.)", text, flags=re.M)[1:]
    if len(sections) != 7:
        c.error("experience", "EXPERIENCE.md must have the 7 numbered questions.")
        return
    for number, body in enumerate(sections, start=1):
        answer = body.split("\n", 1)[1] if "\n" in body else ""
        if number == 1:
            parts = re.findall(r"^- [^:]+:[ \t]*(.*)$", answer, re.M)
            if len(parts) != 3 or not all(p.strip() for p in parts):
                c.error("experience", "EXPERIENCE.md question 1: fill in all three times.")
        elif not answer.strip():
            c.error("experience", f"EXPERIENCE.md question {number} has no answer.")


def find_official(candidates: list[Path]) -> Path | None:
    for folder in candidates:
        path = folder / "check_dataset.py"
        if path.is_file():
            return path
    return None


def run_official(script: Path, zip_path: Path, expect: int | None) -> dict:
    local = zip_path.parent / "check_dataset.py"
    copied = script.resolve() != local.resolve()
    if copied:
        shutil.copyfile(script, local)
    command = [sys.executable, "-X", "utf8", local.name, zip_path.name]
    if expect is not None and expect != 500:
        command += ["--expect", str(expect)]
    try:
        done = subprocess.run(command, cwd=str(zip_path.parent), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    finally:
        if copied:
            local.unlink(missing_ok=True)
    output = (done.stdout or "") + (done.stderr or "")
    return {"script": str(script), "output": output.strip()[-6000:], "ok": OFFICIAL_OK in output and done.returncode == 0}
