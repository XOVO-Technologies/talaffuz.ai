from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from ..pipeline.text_ur import normalize_urdu

UR_END = re.compile(r"(?<=[۔؟!])\s+")
RO_END = re.compile(r"(?<=[.?!])\s+")
LONG_DASHES = chr(0x2013) + chr(0x2014)
UR_STRIP = re.compile(r"[۔؟!،؛:\"'“”‘’«»()\[\]{}…\-/\\|*_.,?;" + LONG_DASHES + "]")
RO_DASH = re.compile("[-/_" + LONG_DASHES + "]+")
RO_KEEP = re.compile(r"[^A-Za-z0-9]")
MAX_WORDS = 99
MAX_SENTENCES = 99
CHECK_SCORE = 0.3
INITIALS = {
    "ب": "b", "پ": "p", "ت": "t", "ٹ": "t", "ث": "s", "ج": "jgz", "چ": "c", "ح": "h", "خ": "k",
    "د": "d", "ڈ": "d", "ذ": "z", "ر": "r", "ڑ": "r", "ز": "z", "ژ": "zj", "س": "sc", "ش": "s",
    "ص": "s", "ض": "zd", "ط": "t", "ظ": "z", "غ": "g", "ف": "fp", "ق": "qk", "ک": "kcq",
    "گ": "g", "ل": "l", "م": "m", "ن": "n", "ں": "n", "ہ": "h", "ھ": "h", "و": "wvaou",
    "ی": "yaei", "ے": "aei", "ئ": "yaei", "ا": "aeiou", "آ": "aeiou", "ع": "aeiouy",
}
INITIAL_PENALTY = 1.0
SURPRISE_SEEN = 8
BAD_SCORE = 1.0
LETTER_NAMES = {
    "اے": "a", "بی": "b", "سی": "c", "ڈی": "d", "ای": "e", "ایف": "f", "جی": "g", "ایچ": "h", "آئی": "i",
    "جے": "j", "کے": "k", "ایل": "l", "ایم": "m", "این": "n", "او": "o", "پی": "p", "کیو": "q", "آر": "r",
    "ایس": "s", "ٹی": "t", "یو": "u", "وی": "v", "ڈبلیو": "w", "ایکس": "x", "وائی": "y", "زیڈ": "z",
}


@dataclass(frozen=True)
class Atom:
    text: str
    cuts: tuple[int, ...] = ()


@dataclass
class SentencePair:
    urdu: list[str]
    roman: list[str]
    status: str
    score: float
    source_urdu: str
    source_roman: str


@dataclass
class RecordingPair:
    sentences: list[SentencePair] = field(default_factory=list)
    problem: str = ""
    source_urdu: str = ""
    source_roman: str = ""


def split_urdu_sentences(text: str) -> list[str]:
    cleaned = normalize_urdu(text, ensure_terminal=False)
    return [part.strip() for part in UR_END.split(cleaned) if part.strip()]


def split_roman_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return [part.strip() for part in RO_END.split(cleaned) if part.strip()]


def urdu_words(sentence: str) -> list[str]:
    return UR_STRIP.sub(" ", normalize_urdu(sentence, ensure_terminal=False)).split()


def roman_atoms(sentence: str, lower: bool) -> list[Atom]:
    text = unicodedata.normalize("NFKD", sentence or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "").replace("'", "")
    if lower:
        text = text.lower()
    atoms: list[Atom] = []
    for token in text.split():
        parts = [RO_KEEP.sub("", part) for part in RO_DASH.split(token)]
        parts = [part for part in parts if part]
        if not parts:
            continue
        cuts: list[int] = []
        position = 0
        for index, part in enumerate(parts[:-1]):
            position += len(part)
            if len(parts[index + 1]) == 1 and parts[index + 1] in "eoi" and index + 2 < len(parts):
                continue
            cuts.append(position)
        atoms.append(Atom("".join(parts), tuple(cuts)))
    return atoms


def within_one_edit(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


class Lexicon:
    def __init__(self) -> None:
        self.words: dict[str, Counter[str]] = defaultdict(Counter)
        self.urdu_letters = 0
        self.roman_letters = 0
        self.memo: dict[tuple[str, str], float] = {}

    def learn(self, urdu: list[str], roman: list[str]) -> None:
        self.memo.clear()
        for u, r in zip(urdu, roman):
            if u and r:
                self.words[u][r] += 1
                self.urdu_letters += len(u)
                self.roman_letters += len(r)

    def surprising(self, urdu: str, piece: str) -> bool:
        known = self.words.get(urdu)
        return bool(known) and sum(known.values()) >= SURPRISE_SEEN and self.cost(urdu, piece) >= 1.0

    @property
    def ratio(self) -> float:
        return self.roman_letters / self.urdu_letters if self.urdu_letters else 1.3

    def cost(self, urdu: str, piece: str) -> float:
        key = (urdu, piece)
        cached = self.memo.get(key)
        if cached is None:
            cached = self.memo[key] = self.score(urdu, piece)
        return cached

    def score(self, urdu: str, piece: str) -> float:
        if LETTER_NAMES.get(urdu) == piece:
            return 0.05
        expected = max(2.0, self.ratio * len(urdu))
        spread = abs(len(piece) - expected) / max(expected, 3.0)
        known = self.words.get(urdu)
        if known:
            if piece in known:
                return 0.0
            for word in known:
                if len(piece) == len(word) + 1 and piece.startswith(word) and piece[-1] in "eoi":
                    return 0.2
                if within_one_edit(piece, word):
                    return 0.35
        base = 1.0 if known else 0.55
        allowed = INITIALS.get(urdu[:1])
        penalty = INITIAL_PENALTY if allowed and piece[:1] not in allowed else 0.0
        return base + spread + penalty


def split_options(text: str, cuts: tuple[int, ...], k: int):
    for points in combinations(range(1, len(text)), k - 1):
        edges = (0, *points, len(text))
        pieces = [text[edges[t]:edges[t + 1]] for t in range(k)]
        penalty = 0.35 * sum(1 for p in points if p not in cuts)
        yield pieces, penalty


def align_words(urdu: list[str], atoms: list[Atom], lex: Lexicon) -> tuple[list[str], float] | None:
    n, m = len(urdu), len(atoms)
    if n == 0 or m == 0 or sum(len(a.text) for a in atoms) < n:
        return None
    band = max(6, abs(n - m) + 4)
    max_split = min(4, n - m + 1) if n > m else 2
    max_merge = min(4, m - n + 1) if m > n else 2
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None, list[str]]] = {(0, 0): (0.0, None, [])}

    def relax(i2: int, j2: int, cost: float, origin: tuple[int, int], pieces: list[str]) -> None:
        current = best.get((i2, j2))
        if current is None or cost < current[0]:
            best[(i2, j2)] = (cost, origin, pieces)

    for i in range(m):
        centre = i * n / m
        for j in range(max(0, int(centre - band)), min(n, int(centre + band) + 1)):
            state = best.get((i, j))
            if state is None:
                continue
            base = state[0]
            atom = atoms[i]
            relax(i + 1, j + 1, base + lex.cost(urdu[j], atom.text), (i, j), [atom.text])
            if len(atom.text) >= 3:
                for k in range(2, max_split + 1):
                    if j + k > n or len(atom.text) < k:
                        break
                    top = None
                    for pieces, penalty in split_options(atom.text, atom.cuts, k):
                        cost = penalty + sum(lex.cost(urdu[j + t], pieces[t]) for t in range(k))
                        if top is None or cost < top[0]:
                            top = (cost, pieces)
                    relax(i + 1, j + k, base + top[0] + 0.5 * (k - 1), (i, j), top[1])
            for a in range(2, max_merge + 1):
                if i + a > m:
                    break
                joined = "".join(x.text for x in atoms[i:i + a])
                relax(i + a, j + 1, base + lex.cost(urdu[j], joined) + 0.5 * (a - 1), (i, j), [joined])
    end = best.get((m, n))
    if end is None:
        return None
    words: list[str] = []
    node: tuple[int, int] | None = (m, n)
    while node is not None and node != (0, 0):
        _cost, origin, pieces = best[node]
        words = pieces + words
        node = origin
    return words, end[0] / n


def pair_sentence(source_urdu: str, source_roman: str, lex: Lexicon, lower: bool) -> SentencePair:
    urdu = urdu_words(source_urdu)
    atoms = roman_atoms(source_roman, lower)
    plain = [a.text for a in atoms]
    if urdu and len(urdu) == len(plain) and not any(a.cuts for a in atoms):
        return SentencePair(urdu, plain, "ok", 0.0, source_urdu, source_roman)
    result = align_words(urdu, atoms, lex)
    if result is None or len(result[0]) != len(urdu):
        return SentencePair(urdu, plain, "bad", 1.0, source_urdu, source_roman)
    words, score = result
    if score > BAD_SCORE:
        return SentencePair(urdu, plain, "bad", score, source_urdu, source_roman)
    surprised = any(lex.surprising(u, r) for u, r in zip(urdu, words))
    status = "check" if score > CHECK_SCORE or surprised else "fixed"
    if words == plain:
        status = "ok"
    return SentencePair(urdu, words, status, score, source_urdu, source_roman)


def apply_edits(urdu_parts: list[str], roman_parts: list[str], edits: dict | None) -> tuple[list[str], list[str]]:
    if not edits:
        return urdu_parts, roman_parts
    whole = edits.get("whole")
    if whole:
        urdu_parts = split_urdu_sentences(whole.get("urdu", "")) or urdu_parts
        roman_parts = split_roman_sentences(whole.get("roman", "")) or roman_parts
    urdu_parts, roman_parts = list(urdu_parts), list(roman_parts)
    for index, replacement in (edits.get("sentences") or {}).items():
        k = int(index)
        if 0 <= k < len(urdu_parts) and k < len(roman_parts):
            urdu_parts[k] = replacement.get("urdu", urdu_parts[k])
            roman_parts[k] = replacement.get("roman", roman_parts[k])
    return urdu_parts, roman_parts


def pair_recording(urdu_text: str, roman_text: str, lex: Lexicon, lower: bool, edits: dict | None = None) -> RecordingPair:
    urdu_parts, roman_parts = apply_edits(split_urdu_sentences(urdu_text), split_roman_sentences(roman_text), edits)
    result = RecordingPair(source_urdu=urdu_text, source_roman=roman_text)
    if not urdu_parts or not roman_parts:
        result.problem = "empty"
        return result
    if len(urdu_parts) != len(roman_parts):
        result.problem = "sentence_count"
        return result
    if len(urdu_parts) > MAX_SENTENCES:
        result.problem = "too_many_sentences"
        return result
    result.sentences = [pair_sentence(u, r, lex, lower) for u, r in zip(urdu_parts, roman_parts)]
    if any(len(s.urdu) > MAX_WORDS for s in result.sentences):
        result.problem = "too_many_words"
    return result


def plausible(urdu: str, roman: str) -> bool:
    if not urdu or not roman:
        return False
    if not 0.6 <= len(roman) / len(urdu) <= 2.8:
        return False
    allowed = INITIALS.get(urdu[0])
    return allowed is None or roman[0] in allowed


def build_lexicon(texts: list[tuple[str, str]], lower: bool) -> Lexicon:
    lex = Lexicon()
    for urdu_text, roman_text in texts:
        urdu_parts, roman_parts = split_urdu_sentences(urdu_text), split_roman_sentences(roman_text)
        if len(urdu_parts) != len(roman_parts):
            continue
        for u_part, r_part in zip(urdu_parts, roman_parts):
            urdu, atoms = urdu_words(u_part), roman_atoms(r_part, lower)
            if not urdu or len(urdu) != len(atoms) or any(a.cuts for a in atoms):
                continue
            roman = [a.text for a in atoms]
            good = [plausible(u, r) for u, r in zip(urdu, roman)]
            if good.count(False) > 0.15 * len(good):
                continue
            lex.learn([u for u, ok in zip(urdu, good) if ok], [r for r, ok in zip(roman, good) if ok])
    return lex


def sentence_bad(pair: SentencePair) -> bool:
    return pair.status == "bad" or not pair.urdu or len(pair.urdu) != len(pair.roman)


def recording_status(pair: RecordingPair) -> str:
    if pair.problem or not pair.sentences or any(sentence_bad(s) for s in pair.sentences):
        return "bad"
    if any(s.status == "check" for s in pair.sentences):
        return "check"
    if any(s.status == "fixed" for s in pair.sentences):
        return "fixed"
    return "ok"


def render_sentence(pair: SentencePair) -> tuple[str, str]:
    return " ".join(pair.urdu), " ".join(pair.roman)


def render_recording(pair: RecordingPair) -> tuple[str, str]:
    urdu = " ".join(" ".join(s.urdu) + "۔" for s in pair.sentences)
    roman = " ".join(" ".join(s.roman) + "." for s in pair.sentences)
    return urdu, roman
