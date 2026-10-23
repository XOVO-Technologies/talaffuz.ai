from __future__ import annotations

from .ids import LEVELS
from .models import Profile

QUESTION_TITLES = (
    "## 1. Kul kitna waqt laga? (ghanton mein, andaza)",
    "## 2. Mushkil kitni lagi? (1 = bohat aasan, 5 = bohat mushkil)",
    "## 3. Sab se mushkil hissa kaun sa tha aur kyun?",
    "## 4. Kaun si cheez ya tareeqa sab se zyada kaam aaya?",
    "## 5. Aap ke dataset mein koi kami ya masla? (jaise background noise, kuch words saaf nahi, spelling mein farq)",
    "## 6. Agar dobara banana ho to kya mukhtalif karenge?",
    "## 7. Is assignment se aap ne kya seekha?",
)


def experience_text(profile: Profile) -> str:
    exp = profile.experience
    difficulty = f"{exp.difficulty}" + (f". {exp.difficulty_note}" if exp.difficulty_note else "")
    lines = [
        f"# Experience Form - {profile.sid}",
        "",
        "> Har sawal ka jawab 1-3 lines mein, Roman Urdu ya English mein. Koi jawab ghalat nahi hota, bas sach aur poora likhein.",
        "",
        f"**Naam:** {profile.name}",
        f"**Speaker ID:** {profile.sid}",
        "",
        QUESTION_TITLES[0],
        "",
        f"- Recording: {exp.hours_recording}",
        f"- Audio kaatna (sentences + words): {exp.hours_cutting}",
        f"- Text likhna aur metadata banana: {exp.hours_text}",
        "",
        QUESTION_TITLES[1],
        "",
        difficulty,
        "",
        QUESTION_TITLES[2],
        "",
        exp.hardest,
        "",
        QUESTION_TITLES[3],
        "",
        exp.helpful,
        "",
        QUESTION_TITLES[4],
        "",
        exp.issues,
        "",
        QUESTION_TITLES[5],
        "",
        exp.redo,
        "",
        QUESTION_TITLES[6],
        "",
        exp.learned,
        "",
    ]
    return "\n".join(lines)


def readme_text(profile: Profile, counts: dict[str, dict[str, int]]) -> str:
    sid = profile.sid
    train = counts["recordings"]["train"]
    total = train + counts["recordings"]["test"]
    configs = [
        "- config_name: recordings",
        "  data_dir: recordings",
        "- config_name: sentences",
        "  data_dir: sentences",
        "  default: true",
        "- config_name: words",
        "  data_dir: words",
    ]
    front = [
        "---",
        "language:",
        "- ur",
        f'pretty_name: "Urdu Speech Dataset - {sid}"',
        "task_categories:",
        "- automatic-speech-recognition",
        "configs:",
        *configs,
        "---",
    ]
    rows = [f"| {level} | {counts[level]['train']} | {counts[level]['test']} | {counts[level]['train'] + counts[level]['test']} |" for level in LEVELS]
    body = [
        "",
        f"# Urdu Speech Dataset - {sid}",
        "",
        "## Speaker",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| speaker_id | {sid} |",
        f"| name | {profile.name} |",
        f"| section | {profile.section} |",
        f"| roll_no | {profile.roll} |",
        f"| gender | {profile.gender} |",
        "| language | Urdu (ur), Urdu script + Roman Urdu |",
        f"| recording_device | {profile.phone_model} |",
        f"| recording_place | {profile.location} |",
        f"| recording_dates | {profile.dates} |",
        "| audio_format | WAV, 16000 Hz, mono, 16-bit PCM |",
        "",
        "## Counts",
        "",
        "| Level | train | test | total |",
        "|---|---|---|---|",
        *rows,
        "",
        "## Split",
        "",
        f"Recordings R001-R{train:03d} are in train, R{train + 1:03d}-R{total:03d} in test. A recording's sentences and words are always in the same split as the recording.",
        "",
        "## Notes",
        "",
        "- Sentence start_sec/end_sec are measured in the recording file.",
        "- Word start_sec/end_sec are also measured in the recording file.",
        "",
    ]
    return "\n".join(front + body)
