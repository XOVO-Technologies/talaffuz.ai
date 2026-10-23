from __future__ import annotations

import re

SECTIONS = ("7C", "7D", "7F", "7G", "7J")
GENDERS = ("M", "F")
SPLITS = ("train", "test")
LEVELS = ("recordings", "sentences", "words")

ID_PATTERN = re.compile(r"^(7[CDFGJ])_(\d{3})_([MF])$")
RECORDING_FILE = re.compile(r"^(?P<id>7[CDFGJ]_\d{3}_[MF])_R(?P<r>\d{3})\.wav$")
SENTENCE_FILE = re.compile(r"^(?P<id>7[CDFGJ]_\d{3}_[MF])_R(?P<r>\d{3})_S(?P<s>\d{2})\.wav$")
WORD_FILE = re.compile(r"^(?P<id>7[CDFGJ]_\d{3}_[MF])_R(?P<r>\d{3})_S(?P<s>\d{2})_W(?P<w>\d{2})\.wav$")


def roll_text(roll_no: int) -> str:
    return f"{roll_no:03d}"


def speaker_id(section: str, roll_no: int, gender: str) -> str:
    return f"{section}_{roll_text(roll_no)}_{gender}"


def recording_id(n: int) -> str:
    return f"R{n:03d}"


def sentence_id(n: int) -> str:
    return f"S{n:02d}"


def word_id(n: int) -> str:
    return f"W{n:02d}"


def recording_file(sid: str, r: int) -> str:
    return f"{sid}_{recording_id(r)}.wav"


def sentence_file(sid: str, r: int, s: int) -> str:
    return f"{sid}_{recording_id(r)}_{sentence_id(s)}.wav"


def word_file(sid: str, r: int, s: int, w: int) -> str:
    return f"{sid}_{recording_id(r)}_{sentence_id(s)}_{word_id(w)}.wav"


def split_of(r: int, train: int) -> str:
    return "train" if r <= train else "test"
