"""Unit tests for vision summarisation. Needs neither FreeCAD nor Ollama."""

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


class TestServerWrapper:
    def test_wrapper_delegates_with_state(self, monkeypatch):
        """server's helper must read module state, not take flags itself."""
        from freecad_mcp import server

        seen = {}

        def fake(response, screenshot, only_text_feedback, **kw):
            seen["only_text_feedback"] = only_text_feedback
            seen.update(kw)
            return response

        monkeypatch.setattr(server, "_add_screenshot", fake)
        monkeypatch.setattr(server.state, "only_text_feedback", False)
        monkeypatch.setattr(server.state, "vision_summary", True)
        monkeypatch.setattr(server.state, "vision_model", "llava:13b")
        monkeypatch.setattr(server.state, "vision_url", "http://box:1234")

        server.add_screenshot_if_available([], "B64", vision_prompt="Is it flush?")

        assert seen["only_text_feedback"] is False
        assert seen["vision_summary"] is True
        assert seen["vision_model"] == "llava:13b"
        assert seen["vision_url"] == "http://box:1234"
        assert seen["vision_prompt"] == "Is it flush?"

    def test_wrapper_works_without_a_prompt(self, monkeypatch):
        """The ~60 existing call sites pass two arguments and must keep working."""
        from freecad_mcp import server

        monkeypatch.setattr(server.state, "only_text_feedback", False)
        monkeypatch.setattr(server.state, "vision_summary", False)
        out = server.add_screenshot_if_available([], "B64")
        assert len(out) == 1
        assert out[0].type == "image"


class TestFlagParsing:
    def test_flags_default_off(self):
        from freecad_mcp.server import _build_arg_parser

        args = _build_arg_parser().parse_args([])
        assert args.vision_summary is False
        assert args.vision_model == "llava:7b"
        assert args.vision_url == "http://localhost:11434"

    def test_flags_can_be_set(self):
        from freecad_mcp.server import _build_arg_parser

        args = _build_arg_parser().parse_args(
            ["--vision-summary", "--vision-model", "llava:13b",
             "--vision-url", "http://box:1234"]
        )
        assert args.vision_summary is True
        assert args.vision_model == "llava:13b"
        assert args.vision_url == "http://box:1234"

    def test_existing_flags_still_parse(self):
        from freecad_mcp.server import _build_arg_parser

        args = _build_arg_parser().parse_args(["--only-text-feedback", "--host", "1.2.3.4"])
        assert args.only_text_feedback is True
        assert args.host == "1.2.3.4"


class TestGetViewOperation:
    """get_view previously built ImageContent directly, ignoring only_text_feedback."""

    class _FakeConn:
        def __init__(self, screenshot="B64DATA"):
            self._screenshot = screenshot
            self.focus_object_seen = "unset"

        def get_active_screenshot(self, view_name=None, width=None, height=None, focus_object=None):
            self.focus_object_seen = focus_object
            return self._screenshot

    def test_returns_image_by_default(self):
        from freecad_mcp.operations.core import get_view_operation

        out = get_view_operation(self._FakeConn(), "Isometric", None, None, None, False)
        assert len(out) == 1
        assert out[0].type == "image"

    def test_honours_only_text_feedback(self):
        """The bug: this previously returned an image regardless."""
        from freecad_mcp.operations.core import get_view_operation

        out = get_view_operation(self._FakeConn(), "Isometric", None, None, None, True)
        assert len(out) == 1
        assert out[0].type == "text"
        assert "only-text-feedback" in out[0].text.lower() or "only_text_feedback" in out[0].text.lower()

    def test_vision_summary_replaces_the_image(self, monkeypatch):
        from freecad_mcp.operations.core import get_view_operation

        monkeypatch.setattr(
            responses.vision, "summarise",
            lambda image_b64, prompt, *, url, model, timeout=60: "DESCRIPTION",
        )
        out = get_view_operation(
            self._FakeConn(), "Isometric", None, None, None, False, vision_summary=True
        )
        assert len(out) == 1
        assert out[0].type == "text"
        assert out[0].text == "DESCRIPTION"

    def test_focus_object_is_passed_through_verbatim(self):
        """No pipe-splitting anywhere: the object name reaches FreeCAD intact."""
        from freecad_mcp.operations.core import get_view_operation

        conn = self._FakeConn()
        get_view_operation(conn, "Isometric", None, None, "Sleeve|weird", False)
        assert conn.focus_object_seen == "Sleeve|weird"

    def test_no_screenshot_returns_explanatory_text(self):
        from freecad_mcp.operations.core import get_view_operation

        out = get_view_operation(self._FakeConn(screenshot=None), "Isometric", None, None, None, False)
        assert len(out) == 1
        assert out[0].type == "text"
        assert "Cannot get screenshot" in out[0].text


class TestToolSignatures:
    def test_execute_code_accepts_vision_prompt(self):
        import inspect
        from freecad_mcp.server import execute_code

        assert "vision_prompt" in inspect.signature(execute_code).parameters

    def test_get_view_accepts_vision_prompt(self):
        import inspect
        from freecad_mcp.server import get_view

        assert "vision_prompt" in inspect.signature(get_view).parameters
