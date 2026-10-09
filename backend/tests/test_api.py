import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DATA_DIR", str(tmp_path))
    import importlib

    from app import config, main

    importlib.reload(config)
    main = importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def wav_bytes(seconds=2.0, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, (0.1 * np.sin(np.arange(int(seconds * sr)) / 8)).astype("float32"), sr, format="WAV")
    return buf.getvalue()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["ffmpeg"]


def test_project_upload_and_settings_roundtrip(client):
    pid = client.post("/api/projects", json={"name": "demo"}).json()["id"]
    up = client.put(f"/api/projects/{pid}/sources", params={"filename": "talk one.wav"}, content=wav_bytes())
    assert up.status_code == 200 and up.json()["size_bytes"] > 1000
    project = client.get(f"/api/projects/{pid}").json()
    assert project["settings"]["start_index"] == 1 and project["settings"]["end_index"] is None
    assert len(project["sources"]) == 1

    new = dict(project["settings"], start_index=31, end_index=500)
    assert client.put(f"/api/projects/{pid}/settings", json=new).json()["settings"]["end_index"] == 500
    unlimited = dict(new, end_index=None)
    assert client.put(f"/api/projects/{pid}/settings", json=unlimited).json()["settings"]["end_index"] is None
    assert client.put(f"/api/projects/{pid}/settings", json=dict(new, end_index=0)).status_code == 422
    assert client.put(f"/api/projects/{pid}/settings", json=dict(new, end_index=5)).status_code == 422


def test_process_requires_a_source_and_empty_upload_is_rejected(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    assert client.post(f"/api/projects/{pid}/process").status_code == 400
    assert client.put(f"/api/projects/{pid}/sources", params={"filename": "x.wav"}, content=b"").status_code == 400


def test_import_sources_from_a_file_and_a_folder(client, tmp_path):
    pid = client.post("/api/projects", json={}).json()["id"]
    audio = tmp_path / "incoming"
    audio.mkdir()
    (audio / "one.wav").write_bytes(wav_bytes())
    (audio / "two.wav").write_bytes(wav_bytes())
    (audio / "notes.txt").write_text("not audio")

    one = client.post(f"/api/projects/{pid}/sources/import", json={"path": str(audio / "one.wav")})
    assert one.status_code == 200 and [s["name"] for s in one.json()] == ["one.wav"]

    many = client.post(f"/api/projects/{pid}/sources/import", json={"path": f'"{audio}"'})
    assert many.status_code == 200 and sorted(s["name"] for s in many.json()) == ["one.wav", "two.wav"]

    project = client.get(f"/api/projects/{pid}").json()
    assert len(project["sources"]) == 3 and all(s["size_bytes"] > 1000 for s in project["sources"])
    # the original is copied, not moved
    assert (audio / "one.wav").exists()


def test_import_sources_rejects_bad_paths(client, tmp_path):
    pid = client.post("/api/projects", json={}).json()["id"]
    url = f"/api/projects/{pid}/sources/import"
    assert client.post(url, json={"path": str(tmp_path / "missing.wav")}).status_code == 404
    (tmp_path / "notes.txt").write_text("hello")
    assert client.post(url, json={"path": str(tmp_path / "notes.txt")}).status_code == 400
    empty = tmp_path / "empty"
    empty.mkdir()
    assert client.post(url, json={"path": str(empty)}).status_code == 400
    assert client.post("/api/projects/nope/sources/import", json={"path": str(tmp_path)}).status_code == 404


@pytest.fixture()
def key_client(tmp_path, monkeypatch):
    """A client whose .env file lives in tmp_path and whose key check never touches the network."""
    monkeypatch.setenv("URDU_ENV_FILE", str(tmp_path / "test.env"))
    for name in ("ANTHROPIC_API_KEY", "ROMANIZE_MODEL"):
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)  # leaves the variable unset now and restores "unset" afterwards
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("DATASET_DATA_DIR", str(tmp_path))
    import importlib

    from app import config, main

    importlib.reload(config)
    main = importlib.reload(main)
    monkeypatch.setattr(main.romanize, "verify_key", lambda key: True)
    with TestClient(main.app) as c:
        yield c, tmp_path / "test.env", config


KEY = "sk-ant-api03-" + "x" * 30


def test_api_key_for_this_session_only(key_client):
    client, env_file, _ = key_client
    assert client.get("/api/anthropic-key").json()["configured"] is False
    saved = client.put("/api/anthropic-key", json={"key": KEY, "remember": False})
    assert saved.status_code == 200 and saved.json()["configured"] and saved.json()["verified"]
    assert not saved.json()["saved"] and not env_file.exists()
    assert KEY not in saved.text and KEY not in client.get("/api/anthropic-key").text
    assert client.get("/api/health").json()["romanize_available"] is True
    removed = client.delete("/api/anthropic-key").json()
    assert removed["configured"] is False


def test_api_key_can_be_remembered_in_the_env_file_and_removed(key_client):
    client, env_file, _ = key_client
    env_file.write_text("MAX_UPLOAD_GB=4\nANTHROPIC_API_KEY=\n", encoding="utf-8")
    saved = client.put("/api/anthropic-key", json={"key": f"  {KEY}  ", "remember": True}).json()
    assert saved["configured"] and saved["saved"]
    assert env_file.read_text(encoding="utf-8").splitlines() == ["MAX_UPLOAD_GB=4", f"ANTHROPIC_API_KEY={KEY}"]
    removed = client.delete("/api/anthropic-key").json()
    assert not removed["configured"] and not removed["saved"]
    assert env_file.read_text(encoding="utf-8").splitlines() == ["MAX_UPLOAD_GB=4", "ANTHROPIC_API_KEY="]


def test_bad_api_keys_are_refused_without_being_stored(key_client, monkeypatch):
    client, env_file, _ = key_client
    assert client.put("/api/anthropic-key", json={"key": "short"}).status_code == 400
    injected = KEY + "\nOTHER=1"
    assert client.put("/api/anthropic-key", json={"key": injected, "remember": True}).status_code == 400
    monkeypatch.setattr("app.main.romanize.verify_key", lambda key: False)
    rejected = client.put("/api/anthropic-key", json={"key": KEY, "remember": True})
    assert rejected.status_code == 400 and KEY not in rejected.text
    assert client.get("/api/anthropic-key").json()["configured"] is False and not env_file.exists()


def test_model_choice_and_cost_estimate(key_client):
    from app import main
    from app.models import Clip

    client, env_file, config = key_client
    listing = client.get("/api/anthropic-models").json()  # no key set here, so this is the built-in list
    assert listing["cheapest"] == "claude-haiku-5-5" and listing["current"] == "claude-haiku-5-5"

    assert client.put("/api/anthropic-model", json={"model": "gpt-4"}).status_code == 400
    assert client.put("/api/anthropic-model", json={"model": "claude-opus-5-5-20260101"}).status_code == 400
    picked = client.put("/api/anthropic-model", json={"model": "claude-sonnet-5-5", "remember": True}).json()
    assert picked["model"] == "claude-sonnet-5-5"
    assert "ROMANIZE_MODEL=claude-sonnet-5-5" in env_file.read_text(encoding="utf-8")

    pid = client.post("/api/projects", json={}).json()["id"]
    with main.store.edit(pid) as live:
        live.clips = [
            Clip(id="a", source_id="s", order=0, start_s=0, end_s=3, status="processed", urdu="آج موسم اچھا ہے۔", wav="x.wav"),
            Clip(id="b", source_id="s", order=1, start_s=3, end_s=6, status="processed", urdu="کل ملتے ہیں۔", roman="Kal milte hain.", wav="y.wav"),
        ]
    estimate = client.get(f"/api/projects/{pid}/romanize-estimate").json()
    assert estimate["rows"] == 1 and estimate["model"] == "claude-sonnet-5-5" and estimate["cost_usd"] > 0
    assert client.get("/api/projects/nope/romanize-estimate").status_code == 404


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope").status_code == 404
