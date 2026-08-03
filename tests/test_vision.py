"""Unit tests for vision summarisation. Needs neither FreeCAD nor Ollama."""

import pytest

from freecad_mcp import vision


class TestSummarise:
    def test_returns_model_text_on_success(self, monkeypatch):
        captured = {}

        def fake_post(url, payload, timeout):
            captured["url"] = url
            captured["payload"] = payload
            return {"response": "A grey cube sits above a cylinder."}

        monkeypatch.setattr(vision, "_post_json", fake_post)
        out = vision.summarise(
            "aGVsbG8=", "Describe it", url="http://ollama:11434", model="llava:7b"
        )
        assert out == "[FreeCAD viewport — llava:7b]: A grey cube sits above a cylinder."
        assert captured["url"] == "http://ollama:11434/api/generate"
        assert captured["payload"]["model"] == "llava:7b"
        assert captured["payload"]["prompt"] == "Describe it"
        assert captured["payload"]["images"] == ["aGVsbG8="]
        assert captured["payload"]["stream"] is False

    def test_empty_response_reports_failure(self, monkeypatch):
        monkeypatch.setattr(vision, "_post_json", lambda url, payload, timeout: {"response": ""})
        out = vision.summarise("aGVsbG8=", "p", url="http://x", model="m")
        assert out.startswith("[")
        assert "empty" in out.lower()

    def test_missing_response_key_reports_failure(self, monkeypatch):
        monkeypatch.setattr(vision, "_post_json", lambda url, payload, timeout: {})
        out = vision.summarise("aGVsbG8=", "p", url="http://x", model="m")
        assert out.startswith("[")

    def test_network_error_reports_failure_and_names_the_url(self, monkeypatch):
        def boom(url, payload, timeout):
            raise OSError("connection refused")

        monkeypatch.setattr(vision, "_post_json", boom)
        out = vision.summarise("aGVsbG8=", "p", url="http://ollama:11434", model="m")
        assert out.startswith("[")
        assert "http://ollama:11434" in out
        assert "connection refused" in out

    def test_never_raises(self, monkeypatch):
        def boom(url, payload, timeout):
            raise RuntimeError("anything at all")

        monkeypatch.setattr(vision, "_post_json", boom)
        # Must return a string rather than propagating.
        assert isinstance(vision.summarise("x", "p", url="u", model="m"), str)


class TestDefaults:
    def test_default_prompt_is_generic(self):
        """The proxy's default described one specific model. This one must not."""
        lowered = vision.DEFAULT_VISION_PROMPT.lower()
        for word in ("parasol", "holder", "sleeve", "stabiliser"):
            assert word not in lowered

    def test_default_prompt_mentions_freecad_viewport(self):
        assert "freecad" in vision.DEFAULT_VISION_PROMPT.lower()

    def test_default_endpoints(self):
        assert vision.DEFAULT_OLLAMA_URL == "http://localhost:11434"
        assert vision.DEFAULT_OLLAMA_MODEL == "llava:7b"
