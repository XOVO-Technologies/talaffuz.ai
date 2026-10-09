import json
from types import SimpleNamespace

from app import config
from app.pipeline import romanize


class FakeMessages:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="text", text=json.dumps({"items": self.rows}))
        return SimpleNamespace(stop_reason="end_turn", content=[block])


class FakeClient:
    def __init__(self, rows):
        self.messages = FakeMessages(rows)


def test_batch_uses_short_ids_and_maps_them_back(monkeypatch):
    monkeypatch.setattr(config, "ROMANIZE_MODEL", "claude-haiku-5-5")
    client = FakeClient([{"id": "1", "roman": "Aaj mausam achha hai."}, {"id": "2", "roman": "Kal milte hain."}])
    got = romanize.romanize_batch(client, {"abc12345": "آج موسم اچھا ہے۔", "def67890": "کل ملتے ہیں۔"})
    assert got == {"abc12345": "Aaj mausam achha hai.", "def67890": "Kal milte hain."}
    call = client.messages.calls[0]
    assert [row["id"] for row in json.loads(call["messages"][0]["content"])] == ["1", "2"]
    assert call["model"] == "claude-haiku-5-5" and call["output_config"]["effort"] == "low"
    assert call["max_tokens"] <= 16000


def test_thinking_is_only_turned_off_for_haiku():
    assert romanize._request_options("claude-haiku-5-5")["thinking"] == {"type": "disabled"}
    for model in ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"):
        assert "thinking" not in romanize._request_options(model)


def test_the_selected_model_is_the_one_that_gets_called(monkeypatch):
    monkeypatch.setattr(config, "ROMANIZE_MODEL", "claude-sonnet-5-5")
    client = FakeClient([{"id": "1", "roman": "Aaj."}])
    romanize.romanize_batch(client, {"a": "آج"})
    assert client.messages.calls[0]["model"] == "claude-sonnet-5-5"


def fake_api(monkeypatch, models):
    api = SimpleNamespace(models=SimpleNamespace(list=lambda limit: models))
    monkeypatch.setattr(romanize, "is_available", lambda: True)
    monkeypatch.setattr(romanize.anthropic, "Anthropic", lambda **kwargs: api)


def test_models_come_from_the_api_and_are_sorted_by_price(monkeypatch):
    fake_api(monkeypatch, [
        SimpleNamespace(id="claude-opus-5-5", display_name="Claude Opus 5.5"),
        SimpleNamespace(id="claude-haiku-5-5", display_name="Claude Haiku 5.5"),
        SimpleNamespace(id="claude-haiku-4-5", display_name="Claude Haiku 4.5"),  # older family: not offered
        SimpleNamespace(id="claude-sonnet-5-5-20260101", display_name="dated copy"),  # dated id: not offered
    ])
    monkeypatch.setattr(config, "ROMANIZE_MODEL", "claude-haiku-5-5")
    result = romanize.list_models()
    assert result["source"] == "api"
    assert [m["id"] for m in result["models"]] == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert result["cheapest"] == "claude-haiku-5-5"
    assert [m["cheapest"] for m in result["models"]] == [True, False]
    assert result["models"][0]["input_per_mtok"] == 0.10 and result["models"][0]["output_per_mtok"] == 0.50


def test_models_fall_back_to_the_built_in_list_without_a_key_or_when_the_api_fails(monkeypatch):
    monkeypatch.setattr(config, "ROMANIZE_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(romanize, "is_available", lambda: False)
    offline = romanize.list_models()
    assert offline["source"] == "builtin" and offline["cheapest"] == "claude-haiku-5-5"
    assert [m["id"] for m in offline["models"]] == ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]

    def boom(limit):
        raise RuntimeError("no network")

    monkeypatch.setattr(romanize, "is_available", lambda: True)
    monkeypatch.setattr(romanize.anthropic, "Anthropic", lambda **kwargs: SimpleNamespace(models=SimpleNamespace(list=boom)))
    assert romanize.list_models()["source"] == "builtin"


def test_a_model_chosen_in_the_env_file_stays_in_the_list(monkeypatch):
    monkeypatch.setattr(config, "ROMANIZE_MODEL", "claude-opus-5")
    monkeypatch.setattr(romanize, "is_available", lambda: False)
    ids = [m["id"] for m in romanize.list_models()["models"]]
    assert "claude-opus-5" in ids


def test_estimate_is_small_for_haiku_and_scales_with_the_price(monkeypatch):
    items = {f"c{i}": "آج موسم بہت اچھا ہے اور ہم باہر جا رہے ہیں۔" for i in range(500)}
    cheap = romanize.estimate(items, "claude-haiku-5-5")
    big = romanize.estimate(items, "claude-opus-5-5")
    assert cheap["rows"] == 500 and cheap["batches"] == 10
    assert cheap["cost_usd"] < 0.10  # about a few cents for 500 clips
    assert round(big["cost_usd"] / cheap["cost_usd"]) == 40  # Opus 5.5 costs 40 times more per token
    assert romanize.estimate({}, "claude-haiku-5-5")["cost_usd"] == 0
    assert romanize.estimate(items, "claude-future-9")["cost_usd"] is None
