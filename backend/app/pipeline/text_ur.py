"""Urdu text normalisation and light quality heuristics for ASR output."""
from __future__ import annotations

import re
import unicodedata
import zlib

_ZERO_WIDTH = re.compile("[​-‏‪-‮⁠﻿]")
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭ]")
_ARABIC_SCRIPT = re.compile("[؀-ۿݐ-ݿ]")
_LATIN = re.compile("[A-Za-z]")
_DIGITS = re.compile("[0-9٠-٩۰-۹]")

_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",  # Arabic yeh        -> Farsi/Urdu yeh
        "ى": "ی",  # alef maksura      -> Urdu yeh
        "ك": "ک",  # Arabic kaf        -> Urdu kaf
        "ه": "ہ",  # Arabic heh        -> Urdu heh goal
        "?": "؟",
        ",": "،",
        ";": "؛",
        **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits  -> ASCII
        **{chr(0x06F0 + i): str(i) for i in range(10)},  # Extended Arabic-Indic -> ASCII
    }
)
_END_MARKS = "۔؟!"  # ۔ ؟ !


def normalize_urdu(text: str, ensure_terminal: bool = True) -> str:
    """Canonical Urdu form used for the dataset: one line, Urdu punctuation, no diacritics."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _ZERO_WIDTH.sub("", t).translate(_CHAR_MAP)
    t = _DIACRITICS.sub("", t).replace("ـ", "")  # diacritics and tatweel
    t = t.replace("|", " ")  # the pipe is the field separator in metadata.csv
    t = re.sub(r"(?<=[؀-ۿ])\s*\.(?!\d)", "۔", t)  # Latin full stop -> ۔
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([۔؟!،؛:])", r"\1", t)
    t = re.sub(r"([۔؟!،؛])(?=[^\s۔؟!،؛\"'”’)\]])", r"\1 ", t)
    if ensure_terminal and t:
        if t[-1] == "،":
            t = t[:-1] + "۔"
        elif t[-1] not in _END_MARKS + ".":
            t += "۔"
    return t


def clean_roman(text: str) -> str:
    """Single-line Roman Urdu with no pipe characters."""
    return re.sub(r"\s+", " ", (text or "").replace("|", " ")).strip()


def has_repetition(text: str) -> bool:
    """True for loops like 'شکریہ شکریہ شکریہ شکریہ' that Whisper emits on silence/noise."""
    if re.search(r"(\S+)(?:\s+\1){3,}", text):
        return True
    if len(text) >= 24:  # zlib ratio is meaningless on very short strings
        raw = text.encode("utf-8")
        return len(raw) / max(1, len(zlib.compress(raw))) > 2.4
    return False


def assess_transcript(
    text: str, duration_s: float, avg_logprob: float | None, no_speech_prob: float | None
) -> tuple[list[str], bool]:
    """Return (flags, auto_reject). Flags are shown in the UI so a human can double check."""
    flags: list[str] = []
    reject = False
    letters = len(_ARABIC_SCRIPT.findall(text)) + len(_LATIN.findall(text))
    if not text.strip():
        return ["empty"], True
    if has_repetition(text):
        flags.append("repetition")
        reject = True
    if letters and len(_ARABIC_SCRIPT.findall(text)) / letters < 0.6:
        flags.append("not_urdu_script")
    if _DIGITS.search(text):
        flags.append("digits")  # TTS text should spell numbers out in words
    cps = len(re.sub(r"[\s۔؟!،؛]", "", text)) / max(duration_s, 0.1)
    if cps < 2.5:
        flags.append("too_little_text")
    elif cps > 22:
        flags.append("too_much_text")
    if avg_logprob is not None and avg_logprob < -1.0:
        flags.append("low_confidence")
    if no_speech_prob is not None and no_speech_prob > 0.6:
        flags.append("maybe_not_speech")
        if "low_confidence" in flags:
            reject = True
    return flags, reject
