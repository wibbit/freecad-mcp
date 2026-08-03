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


from freecad_mcp import responses


def _fake_summarise(monkeypatch, text="DESCRIPTION"):
    """Replace vision.summarise and record the prompt it was given."""
    seen = {}

    def fake(image_b64, prompt, *, url, model, timeout=60):
        seen["prompt"] = prompt
        seen["url"] = url
        seen["model"] = model
        return text

    monkeypatch.setattr(responses.vision, "summarise", fake)
    return seen


class TestScreenshotBranching:
    def test_image_by_default(self):
        out = responses.add_screenshot_if_available([], "B64DATA", False)
        assert len(out) == 1
        assert out[0].type == "image"
        assert out[0].data == "B64DATA"

    def test_only_text_feedback_suppresses_image(self):
        assert responses.add_screenshot_if_available([], "B64DATA", True) == []

    def test_no_screenshot_appends_nothing(self):
        assert responses.add_screenshot_if_available([], None, False) == []

    def test_vision_summary_replaces_image_with_text(self, monkeypatch):
        _fake_summarise(monkeypatch)
        out = responses.add_screenshot_if_available(
            [], "B64DATA", False, vision_summary=True
        )
        assert len(out) == 1
        assert out[0].type == "text"
        assert out[0].text == "DESCRIPTION"

    def test_only_text_feedback_beats_vision_summary(self, monkeypatch):
        """The more restrictive flag wins, and no Ollama call is made."""
        called = {"yes": False}

        def boom(*a, **k):
            called["yes"] = True
            return "should not happen"

        monkeypatch.setattr(responses.vision, "summarise", boom)
        out = responses.add_screenshot_if_available(
            [], "B64DATA", True, vision_summary=True
        )
        assert out == []
        assert called["yes"] is False

    def test_default_prompt_used_when_none_given(self, monkeypatch):
        seen = _fake_summarise(monkeypatch)
        responses.add_screenshot_if_available([], "B64DATA", False, vision_summary=True)
        assert seen["prompt"] == vision.DEFAULT_VISION_PROMPT

    def test_custom_prompt_overrides_default(self, monkeypatch):
        seen = _fake_summarise(monkeypatch)
        responses.add_screenshot_if_available(
            [], "B64DATA", False, vision_summary=True, vision_prompt="Is it flush?"
        )
        assert seen["prompt"] == "Is it flush?"

    def test_model_and_url_are_passed_through(self, monkeypatch):
        seen = _fake_summarise(monkeypatch)
        responses.add_screenshot_if_available(
            [], "B64DATA", False,
            vision_summary=True, vision_model="llava:13b", vision_url="http://box:1234",
        )
        assert seen["model"] == "llava:13b"
        assert seen["url"] == "http://box:1234"

    def test_existing_response_items_are_preserved(self, monkeypatch):
        _fake_summarise(monkeypatch)
        existing = responses.text_response("hello")
        out = responses.add_screenshot_if_available(
            existing, "B64DATA", False, vision_summary=True
        )
        assert len(out) == 2
        assert out[0].text == "hello"
        assert out[1].text == "DESCRIPTION"


class TestServerStateDefaults:
    def test_vision_is_off_by_default(self):
        from freecad_mcp.server_state import ServerState

        s = ServerState()
        assert s.vision_summary is False
        assert s.vision_model == vision.DEFAULT_OLLAMA_MODEL
        assert s.vision_url == vision.DEFAULT_OLLAMA_URL
