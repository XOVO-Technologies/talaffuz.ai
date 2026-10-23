import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.assignment import aligner, check, text, timing
from app.assignment.build import BuildItem, build_dataset
from app.assignment.ids import ID_PATTERN, recording_file, sentence_file, speaker_id, word_file
from app.assignment.models import Experience, Profile

CORPUS = [
    ("آج موسم بہت اچھا ہے۔ ہم کل جائیں گے۔", "Aaj mausam bohat acha hai. Hum kal jayenge."),
    ("وہ کتاب پڑھیں گے۔ ہم گھر جائیں گے۔", "Woh kitab parhenge. Hum ghar jayenge."),
    ("میں کل آؤں گا۔ آپ بھی آئیں گے۔", "Main kal aaonga. Aap bhi aayenge."),
    ("ہم کل جائیں گے۔ آج موسم بہت اچھا ہے۔", "Hum kal jaayen ge. Aaj mausam bohat acha hai."),
    ("کیا آپ جائیں گے۔ وہ کتاب پڑھیں گے۔", "Kya aap jaayen ge. Woh kitab parhen ge."),
    ("آج ہم گھر جائیں گے۔ آپ کل آئیں گے۔", "Aaj hum ghar jaayen ge. Aap kal aayen ge."),
]


def experience():
    return Experience(
        hours_recording="6 hours",
        hours_cutting="4 hours",
        hours_text="5 hours",
        difficulty=3,
        difficulty_note="Cutting words took time",
        hardest="Matching words",
        helpful="The app",
        issues="Some noise",
        redo="Record in a quieter room",
        learned="How datasets are built",
    )


def profile(**changes):
    base = dict(
        name="Ali Khan",
        section="7C",
        roll_no=42,
        gender="M",
        phone_model="Pixel 7",
        location="Lahore",
        date_from="2026-10-01",
        date_to="2026-10-05",
        total=6,
        train=4,
        experience=experience(),
    )
    base.update(changes)
    return Profile(**base)


def make_source(folder, seconds=4.0):
    wavs = folder / "wavs"
    wavs.mkdir(parents=True)
    lines = []
    rng = np.random.default_rng(1)
    for i, (urdu, roman) in enumerate(CORPUS, start=1):
        name = f"urdu_{i:06d}.wav"
        audio = (0.2 * rng.standard_normal(int(seconds * 22050))).astype("float32")
        sf.write(str(wavs / name), audio, 22050, subtype="PCM_16")
        lines.append(f"{name}|{urdu}|{roman}")
    (folder / "metadata.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def fake_align(audio, words, sample_rate=16000):
    seconds = len(audio) / sample_rate
    step = (seconds - 0.8) / len(words)
    return [(0.4 + k * step, 0.4 + (k + 0.8) * step) for k in range(len(words))], 0.9


def test_ids_and_missing_details():
    assert speaker_id("7C", 42, "M") == "7C_042_M"
    assert speaker_id("7J", 7, "F") == "7J_007_F"
    assert ID_PATTERN.match("7C_042_M")
    assert recording_file("7C_042_M", 1) == "7C_042_M_R001.wav"
    assert sentence_file("7C_042_M", 1, 2) == "7C_042_M_R001_S02.wav"
    assert word_file("7C_042_M", 237, 2, 5) == "7C_042_M_R237_S02_W05.wav"
    assert Profile().missing()
    assert profile().missing() == []
    assert "Train count must be smaller than the total" in profile(train=6).missing()


def test_roman_atoms_keep_hyphen_cut_points():
    atoms = text.roman_atoms("Jang-e-azeem aur wazeer-e-daakhila", True)
    assert [a.text for a in atoms] == ["jangeazeem", "aur", "wazeeredaakhila"]
    assert atoms[0].cuts == (5,)
    assert atoms[2].cuts == (7,)


def test_fused_future_tense_is_split_into_urdu_word_pairs():
    lex = text.build_lexicon(CORPUS, True)
    pair = text.pair_sentence("ہم کل جائیں گے", "Hum kal jayenge", lex, True)
    assert len(pair.urdu) == len(pair.roman) == 4
    assert pair.roman[:2] == ["hum", "kal"]
    assert pair.roman[3] == "ge"
    assert pair.status in ("fixed", "check")


def test_hyphenated_ezafe_goes_to_the_first_word():
    lex = text.build_lexicon(CORPUS, True)
    pair = text.pair_sentence("جنگ عظیم", "jang-e-azeem", lex, True)
    assert pair.roman == ["jange", "azeem"]


def test_sentence_count_mismatch_is_reported_for_the_recording():
    lex = text.build_lexicon(CORPUS, True)
    pair = text.pair_recording("آج موسم بہت اچھا ہے۔ ہم کل جائیں گے۔", "Aaj mausam bohat acha hai.", lex, True)
    assert pair.problem == "sentence_count"
    assert text.recording_status(pair) == "bad"


def test_edit_overrides_a_sentence():
    lex = text.build_lexicon(CORPUS, True)
    edits = {"sentences": {"1": {"urdu": "ہم کل جائیں گے", "roman": "hum kal jayen ge"}}}
    pair = text.pair_recording(CORPUS[0][0], "Aaj mausam bohat acha hai. Hum.", lex, True, edits)
    assert [s.status for s in pair.sentences] == ["ok", "ok"]


def test_render_adds_urdu_and_roman_stops_to_recordings_only():
    lex = text.build_lexicon(CORPUS, True)
    pair = text.pair_recording(*CORPUS[0], lex, True)
    urdu, roman = text.render_recording(pair)
    assert urdu.endswith("۔") and roman.endswith(".")
    assert text.render_sentence(pair.sentences[0]) == ("آج موسم بہت اچھا ہے", "aaj mausam bohat acha hai")


def test_lay_out_is_ordered_inside_and_rounded():
    spans = [(0.5, 0.9), (0.92, 1.3), (1.31, 1.7), (2.4, 2.9), (2.9, 3.3)]
    sentences, words = timing.lay_out([3, 2], spans, 4.0)
    assert len(sentences) == 2 and [len(w) for w in words] == [3, 2]
    flat = [w for group in words for w in group]
    for (s0, e0), (s1, e1) in zip(flat, flat[1:]):
        assert e0 <= s1 and e0 > s0
    for (start, end), group in zip(sentences, words):
        assert start <= group[0][0] and group[-1][1] <= end
    assert sentences[0][1] <= sentences[1][0]
    assert all(round(v, 2) == v for pair in flat for v in pair)


def build_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(aligner, "align", fake_align)
    src = make_source(tmp_path / "src")
    prof = profile()
    lex = text.build_lexicon(CORPUS, True)
    items = []
    for number, (urdu, roman) in enumerate(CORPUS, start=1):
        pair = text.pair_recording(urdu, roman, lex, True)
        wav = src / "wavs" / f"urdu_{number:06d}.wav"
        words = [w for s in pair.sentences for w in s.urdu]
        spans, score = fake_align(timing.load_audio(wav), words)
        items.append(BuildItem(number, f"urdu_{number:06d}", wav, pair, spans, score))
    result = build_dataset(prof, items, tmp_path / "out")
    return prof, result


def test_build_writes_the_required_structure_and_passes_the_check(tmp_path, monkeypatch):
    prof, result = build_fixture(tmp_path, monkeypatch)
    folder = result.folder
    assert folder.name == "7C_042_M"
    for level in ("recordings", "sentences", "words"):
        for split in ("train", "test"):
            assert (folder / level / split / "metadata.csv").is_file()
    assert (folder / "README.md").is_file() and (folder / "EXPERIENCE.md").is_file()
    assert result.counts["recordings"] == {"train": 4, "test": 2}
    assert (folder / "recordings" / "train" / "7C_042_M_R004.wav").is_file()
    assert (folder / "recordings" / "test" / "7C_042_M_R005.wav").is_file()
    info = sf.info(str(folder / "words" / "test" / "7C_042_M_R006_S01_W01.wav"))
    assert (info.samplerate, info.channels, info.subtype) == (16000, 1, "PCM_16")
    report = check.validate_folder(folder, 6, 4)
    assert report["errors"] == []
    assert report["ok"]
    assert result.zip_path and result.zip_path.is_file()
    import zipfile

    names = zipfile.ZipFile(result.zip_path).namelist()
    assert names and all(n.startswith("7C_042_M/") for n in names)


def test_metadata_has_the_documented_columns_and_two_decimals(tmp_path, monkeypatch):
    import csv

    prof, result = build_fixture(tmp_path, monkeypatch)
    with open(result.folder / "words" / "train" / "metadata.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["file_name", "speaker_id", "section", "roll_no", "gender", "recording_id", "sentence_id", "word_id", "start_sec", "end_sec", "duration_sec", "urdu_word", "roman_urdu_word"]
    assert rows[0]["roll_no"] == "042" and rows[0]["file_name"] == "7C_042_M_R001_S01_W01.wav"
    assert all(len(r["start_sec"].split(".")[1]) == 2 for r in rows)
    raw = (result.folder / "words" / "train" / "metadata.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_check_reports_a_wrong_split_a_bad_sample_rate_and_a_word_count(tmp_path, monkeypatch):
    prof, result = build_fixture(tmp_path, monkeypatch)
    folder = result.folder
    moved = folder / "recordings" / "train" / "7C_042_M_R004.wav"
    moved.rename(folder / "recordings" / "test" / moved.name)
    sf.write(str(folder / "words" / "train" / "7C_042_M_R001_S01_W01.wav"), np.zeros(1600, dtype="float32"), 8000, subtype="PCM_16")
    meta = folder / "sentences" / "train" / "metadata.csv"
    meta.write_text(meta.read_text(encoding="utf-8").replace("aaj mausam bohat acha hai", "aaj mausam bohatacha hai", 1), encoding="utf-8")
    errors = " ".join(check.validate_folder(folder, 6, 4)["errors"])
    assert "7C_042_M_R004.wav" in errors
    assert "16000 Hz" in errors
    assert "word counts differ" in errors


def test_check_flags_an_empty_experience_answer(tmp_path, monkeypatch):
    prof, result = build_fixture(tmp_path, monkeypatch)
    path = result.folder / "EXPERIENCE.md"
    path.write_text(path.read_text(encoding="utf-8").replace("The app", "", 1), encoding="utf-8")
    assert any("question 4" in e for e in check.validate_folder(result.folder, 6, 4)["errors"])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DATA_DIR", str(tmp_path / "data"))
    import importlib

    from app import config, main

    importlib.reload(config)
    main = importlib.reload(main)
    monkeypatch.setattr(aligner, "align", fake_align)
    with TestClient(main.app) as c:
        yield c


def wait_idle(client, seconds=60):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = client.get("/api/assignment/state").json()
        if state["running"] is None:
            return state
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_api_flow_from_details_to_a_checked_zip(client, tmp_path):
    src = make_source(tmp_path / "src")
    state = client.get("/api/assignment/state").json()
    assert state["id"] is None and state["source"] is None
    body = profile(source_path=str(src)).model_dump()
    saved = client.put("/api/assignment/profile", json=body).json()
    assert saved["id"] == "7C_042_M" and saved["missing"] == []

    scanned = client.post("/api/assignment/scan").json()
    assert scanned["source"]["found"] == 6 and scanned["source"]["short_by"] == 0
    assert scanned["text"]["sentences"]["bad"] == 0
    assert scanned["text"]["sentences"]["fixed"] + scanned["text"]["sentences"]["check"] >= 1

    listing = client.get("/api/assignment/problems", params={"kind": "check"}).json()
    assert listing["total"] == len(listing["items"]) or listing["total"] > 0

    assert client.post("/api/assignment/build").json() == {"started": True}
    done = wait_idle(client)
    assert done["check"]["ok"], done["check"]
    assert done["zip"]["name"] == "7C_042_M.zip"
    assert done["build"]["counts"]["recordings"] == {"train": 4, "test": 2}
    assert done["timing"]["done"] == 6
    download = client.get("/api/assignment/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"


def test_api_blocks_the_build_until_details_are_complete(client, tmp_path):
    src = make_source(tmp_path / "src")
    body = profile(source_path=str(src), name="").model_dump()
    client.put("/api/assignment/profile", json=body)
    client.post("/api/assignment/scan")
    client.post("/api/assignment/build")
    state = wait_idle(client)
    assert state["zip"] is None and state["build"] is None


def test_edit_a_broken_sentence_through_the_api(client, tmp_path):
    src = tmp_path / "src"
    make_source(src)
    lines = (src / "metadata.csv").read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].split("|")[0] + "|آج موسم بہت اچھا ہے۔ ہم کل جائیں گے۔|Aaj mausam bohat. Hum kal jayenge."
    (src / "metadata.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    client.put("/api/assignment/profile", json=profile(source_path=str(src)).model_dump())
    state = client.post("/api/assignment/scan").json()
    assert state["text"]["sentences"]["bad"] == 1
    bad = client.get("/api/assignment/problems", params={"kind": "bad"}).json()["items"][0]
    assert bad["sentence"] == 0 and bad["urdu_count"] == 5 and bad["roman_count"] == 3
    fixed = client.put("/api/assignment/edit", json={"key": bad["key"], "sentence": 0, "urdu": bad["urdu"], "roman": "aaj mausam bohat acha hai"}).json()
    assert fixed.get("removed") or fixed["status"] != "bad"
    assert client.post("/api/assignment/scan").json()["text"]["sentences"]["bad"] == 0


def test_official_checker_runs_next_to_the_zip_and_is_cleaned_up(tmp_path, monkeypatch):
    prof, result = build_fixture(tmp_path, monkeypatch)
    script = tmp_path / "teacher" / "check_dataset.py"
    script.parent.mkdir()
    script.write_text(
        "import sys\n"
        "print('checking', sys.argv[1:])\n"
        "print('OK - koi ghalti nahi mili')\n",
        encoding="utf-8",
    )
    outcome = check.run_official(script, result.zip_path, 6)
    assert outcome["ok"] and "--expect" in outcome["output"]
    assert not (result.zip_path.parent / "check_dataset.py").exists()


def test_readme_and_experience_follow_the_teacher_sample_layout(tmp_path, monkeypatch):
    prof, result = build_fixture(tmp_path, monkeypatch)
    readme = (result.folder / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("---\nlanguage:\n- ur\npretty_name: \"Urdu Speech Dataset - 7C_042_M\"\n")
    assert "  data_dir: sentences\n  default: true\n" in readme
    for row in ("| speaker_id | 7C_042_M |", "| roll_no | 042 |", "| recording_device | Pixel 7 |", "| recording_place | Lahore |"):
        assert row in readme
    assert "| Level | train | test | total |" in readme and "| recordings | 4 | 2 | 6 |" in readme
    experience = (result.folder / "EXPERIENCE.md").read_text(encoding="utf-8")
    assert experience.startswith("# Experience Form - 7C_042_M\n\n> Har sawal")
    assert "## 1. Kul kitna waqt laga? (ghanton mein, andaza)\n\n- Recording: 6 hours\n" in experience
    assert "## 2. Mushkil kitni lagi? (1 = bohat aasan, 5 = bohat mushkil)\n\n3. Cutting words took time\n" in experience


def test_a_drive_web_link_gets_a_clear_message(client, tmp_path):
    link = "https://drive.google.com/drive/folders/1Ji4E8c5OK_xVZ8NDfEm9qygGz9nUrQT9"
    client.put("/api/assignment/profile", json=profile(source_path=link).model_dump())
    state = client.post("/api/assignment/scan").json()
    assert state["source"] is None
    assert "web link" in state["source_error"] and "/content/drive/MyDrive" in state["source_error"]
