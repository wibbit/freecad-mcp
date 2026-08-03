# In-Server Vision Summarisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Summarise FreeCAD viewport screenshots into short text descriptions inside the server, replacing the standalone proxy script.

**Architecture:** A new pure module (`vision.py`) turns a base64 PNG into a description via Ollama. The two same-named `add_screenshot_if_available` helpers are consolidated into one implementation in `responses.py` that all screenshot paths route through — including `get_view_operation`, which currently bypasses them. `server.py` keeps a thin wrapper supplying module state, so its ~60 call sites are untouched.

**Tech Stack:** Python 3.12, `urllib` (no new dependencies), pytest via `./check`, Ollama with a vision model at runtime (optional — off by default).

**Spec:** `docs/superpowers/specs/2026-08-03-in-server-vision-summarisation-design.md`
**Issue:** [#1](https://codeberg.org/wibbit/freecad-mcp/issues/1)

## Global Constraints

Every task's requirements implicitly include this section.

- **Default behaviour must not change.** With `--vision-summary` absent, every response must be byte-for-byte what it is today. This is the primary safety property — the server has 79 working tools and CAD work depends on them.
- **`--only-text-feedback` always wins.** If both it and `--vision-summary` are set, no description is produced and no Ollama call is made.
- **No new runtime dependencies.** Use `urllib.request` from the standard library, as the proxy does. Do not add `requests`, `httpx`, or an Ollama client library.
- **`summarise()` must never raise.** Every failure path returns a bracketed message string. An unreachable Ollama must never break a CAD tool call.
- **Never fall back to the raw image on failure.** If summarisation fails, emit the error text. Silently returning 5,000 tokens of base64 when the user asked for descriptions is a worse surprise than a visible error.
- **No project-specific prompt text.** The default prompt must be generic to FreeCAD viewports. The proxy's parasol-holder prompt must not survive anywhere.
- Test command: `./check tests/test_vision.py -v`. **Always pass a test path** — a bare `./check` runs the integration suite against a live FreeCAD over RPC and creates scratch documents in the maintainer's running session.
- **Never prefix commands with `timeout N`** — it breaks permission prefix-matching and forces an approval prompt for every variant.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  ```

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/freecad_mcp/vision.py` | **New.** Base64 PNG + prompt → description. Knows nothing of MCP or FreeCAD. | 1 |
| `tests/test_vision.py` | **New.** Unit tests for the above and for the screenshot branching. | 1, 2, 3 |
| `src/freecad_mcp/server_state.py` | Three new fields | 2 |
| `src/freecad_mcp/responses.py` | The consolidated screenshot choke point | 2 |
| `src/freecad_mcp/server.py` | Flags, thin wrapper, two tool parameters | 3, 4 |
| `src/freecad_mcp/operations/core.py` | `get_view_operation` routed through the choke point | 4 |
| `README.md`, `docs/API_REFERENCE.md`, `CHANGELOG.md` | Documentation | 5 |
| `freecad-mcp-proxy.py`, `freecad-mcp-proxy.TODO.md` | **Deleted** | 6 |

`vision.py` is separate from `responses.py` because it is the only part that talks to the network. Keeping it standalone means the branching logic can be tested without any HTTP seam at all.

---

### Task 1: The vision module

A pure module: given an image and a prompt, return a description. No MCP, no FreeCAD, no server state.

**Files:**
- Create: `src/freecad_mcp/vision.py`
- Create: `tests/test_vision.py`

**Interfaces:**
- Consumes: nothing
- Produces — later tasks depend on these exact names:
  - `DEFAULT_VISION_PROMPT: str`
  - `DEFAULT_OLLAMA_URL: str` = `"http://localhost:11434"`
  - `DEFAULT_OLLAMA_MODEL: str` = `"llava:7b"`
  - `summarise(image_b64: str, prompt: str, *, url: str, model: str, timeout: int = 60) -> str`
  - `_post_json(url: str, payload: dict, timeout: int) -> dict` — the network seam tests monkeypatch

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vision.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_vision.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'freecad_mcp.vision'`.

- [ ] **Step 3: Write the implementation**

Create `src/freecad_mcp/vision.py`:

```python
"""Summarise FreeCAD viewport screenshots into text via a local Ollama model.

This module deliberately knows nothing about MCP, FreeCAD, or server state: it
takes an image and a prompt and returns a description. That keeps it testable
without a network, a CAD application, or a running model.
"""

import json
import logging
import urllib.request

logger = logging.getLogger("FreeCADMCPserver")

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llava:7b"

DEFAULT_VISION_PROMPT = (
    "This is a screenshot of a FreeCAD 3D viewport. Describe it in 3-5 sentences: "
    "which objects are visible and their overall shapes, how they are positioned "
    "relative to one another, any visible gaps, intersections or misalignments, "
    "and any obvious geometry problems such as missing faces or wrong proportions. "
    "Be specific about spatial relationships."
)


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    """POST JSON and return the decoded response.

    Isolated so tests can replace the network without an HTTP server.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def summarise(
    image_b64: str,
    prompt: str,
    *,
    url: str,
    model: str,
    timeout: int = 60,
) -> str:
    """Return a text description of a base64 PNG, or a bracketed failure message.

    Never raises. A broken or absent Ollama must not break a CAD tool call, so
    every failure is reported in-band as text the model can read.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    try:
        data = _post_json(f"{url}/api/generate", payload, timeout)
        description = data.get("response", "")
        if not description:
            return (
                f"[FreeCAD viewport — {model} returned an empty response; "
                "image suppressed]"
            )
        return f"[FreeCAD viewport — {model}]: {description}"
    except Exception as exc:
        logger.error("Vision summarisation failed: %s", exc)
        return (
            f"[FreeCAD viewport — vision model unavailable ({exc}); image suppressed. "
            f"Check Ollama at {url}]"
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./check tests/test_vision.py -v
```

Expected: **8 passed.**



- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/vision.py tests/test_vision.py
git commit -m "$(cat <<'EOF'
feat(vision): add Ollama-backed screenshot summariser

Pure module with no MCP, FreeCAD or server-state knowledge, so it is
unit-testable without a network or a running model. Never raises: an
unreachable Ollama must not break a CAD tool call, so failures are
reported in-band as text.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Consolidate the screenshot choke point

`responses.py` gains the vision branch and becomes the single implementation. Nothing calls the new behaviour yet — the parameters default to off, so this task changes no observable behaviour.

**Files:**
- Modify: `src/freecad_mcp/server_state.py`
- Modify: `src/freecad_mcp/responses.py:36-43`
- Modify: `tests/test_vision.py` (append)

**Interfaces:**
- Consumes: `vision.summarise`, `vision.DEFAULT_VISION_PROMPT` from Task 1
- Produces:
  - `ServerState.vision_summary: bool = False`, `ServerState.vision_model: str`, `ServerState.vision_url: str`
  - `responses.add_screenshot_if_available(response, screenshot, only_text_feedback, *, vision_summary=False, vision_model=DEFAULT_OLLAMA_MODEL, vision_url=DEFAULT_OLLAMA_URL, vision_prompt=None) -> ToolResponse`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vision.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_vision.py -v
```

Expected: the 8 tests from Task 1 still pass; the new `TestScreenshotBranching` tests that use
`vision_summary` fail with `TypeError: add_screenshot_if_available() got an unexpected keyword
argument`, and `TestServerStateDefaults` fails with `AttributeError`. The three tests covering
existing behaviour (`test_image_by_default`, `test_only_text_feedback_suppresses_image`,
`test_no_screenshot_appends_nothing`) should **pass immediately** — they characterise behaviour
that must not change.

- [ ] **Step 3: Add the state fields**

In `src/freecad_mcp/server_state.py`, add three fields to `ServerState` alongside the existing
`only_text_feedback` and `rpc_host`:

```python
    vision_summary: bool = False
    vision_model: str = "llava:7b"
    vision_url: str = "http://localhost:11434"
```

Use the literal strings rather than importing from `vision`, to avoid an import cycle —
`server_state.py` is imported early and must stay dependency-free. Task 2's
`TestServerStateDefaults` asserts they equal the `vision` constants, which pins them together.

- [ ] **Step 4: Rewrite the helper**

Replace the whole of `add_screenshot_if_available` in `src/freecad_mcp/responses.py` with:

```python
def add_screenshot_if_available(
    response: ToolResponse,
    screenshot: str | None,
    only_text_feedback: bool,
    *,
    vision_summary: bool = False,
    vision_model: str = vision.DEFAULT_OLLAMA_MODEL,
    vision_url: str = vision.DEFAULT_OLLAMA_URL,
    vision_prompt: str | None = None,
) -> ToolResponse:
    """Append a screenshot to a response, as an image or as a text description.

    `only_text_feedback` is checked first and wins: it means "no visual content
    at all", so no description is produced and no vision call is made.
    """
    if only_text_feedback or screenshot is None:
        return response
    if vision_summary:
        description = vision.summarise(
            screenshot,
            vision_prompt or vision.DEFAULT_VISION_PROMPT,
            url=vision_url,
            model=vision_model,
        )
        return [*response, TextContent(type="text", text=description)]
    return [*response, ImageContent(type="image", data=screenshot, mimeType="image/png")]
```

Add `from . import vision` to the imports at the top of `responses.py`, and make sure
`TextContent` is imported there — check the existing imports and add it if absent.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
./check tests/test_vision.py -v
```

Expected: **18 passed.**

- [ ] **Step 6: Confirm the default path is untouched**

```bash
./check tests/test_project_metadata.py -q
uv run --extra dev python -c "import freecad_mcp.server; print('server imports OK')"
```

Expected: 36 passed, and `server imports OK`. The second guards against an import cycle from the
new `from . import vision`.

- [ ] **Step 7: Commit**

```bash
git add src/freecad_mcp/server_state.py src/freecad_mcp/responses.py tests/test_vision.py
git commit -m "$(cat <<'EOF'
feat(vision): add summarisation branch to the screenshot helper

responses.add_screenshot_if_available gains optional vision settings and
becomes the single place a screenshot turns into response content. Off by
default, so behaviour is unchanged. only_text_feedback is checked first
and short-circuits before any vision call.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire the flags and the server-side wrapper

**Files:**
- Modify: `src/freecad_mcp/server.py:148-156` (the duplicate helper), `:3055-3065` (argparse)
- Modify: `tests/test_vision.py` (append)

**Interfaces:**
- Consumes: `ServerState` fields and the `responses` helper from Task 2
- Produces: `server.add_screenshot_if_available(response, screenshot, vision_prompt=None)` — a thin wrapper. Its ~60 existing call sites keep working unchanged because both new parameters are optional.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vision.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_vision.py -v
```

Expected: 18 pass; the five new tests fail — `AttributeError: module 'freecad_mcp.server' has no
attribute '_add_screenshot'` and `ImportError: cannot import name '_build_arg_parser'`.

- [ ] **Step 3: Replace the duplicate helper with a wrapper**

In `src/freecad_mcp/server.py`, replace the whole existing `add_screenshot_if_available` function
(currently at lines 148-156) with:

```python
def add_screenshot_if_available(
    response: list,
    screenshot,
    vision_prompt: str | None = None,
) -> list:
    """Append a screenshot to a response, using the server's configured mode.

    A thin wrapper over the shared implementation so the ~60 call sites in this
    module do not each need to know about server state.
    """
    if not screenshot and not state.only_text_feedback:
        response.append(TextContent(
            type="text",
            text="Note: Visual preview unavailable in this view type (e.g. TechDraw or Spreadsheet). Switch to a 3D view for screenshots.",
        ))
        return response
    return list(_add_screenshot(
        response,
        screenshot,
        state.only_text_feedback,
        vision_summary=state.vision_summary,
        vision_model=state.vision_model,
        vision_url=state.vision_url,
        vision_prompt=vision_prompt,
    ))
```

Add this import near the top of `server.py`, aliased so the test can monkeypatch the seam:

```python
from .responses import add_screenshot_if_available as _add_screenshot
```

The "Visual preview unavailable" note is kept in the wrapper rather than moved into `responses.py`
because only the `server.py` path emits it today, and moving it would change what the eight
`operations/core.py` call sites return.

- [ ] **Step 4: Extract the argument parser**

In `src/freecad_mcp/server.py`, at module level (above `main()`), add:

```python
def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    parser.add_argument("--host", type=_validate_host, default="localhost", help="Host address of the FreeCAD RPC server to connect to (default: localhost)")
    parser.add_argument("--vision-summary", action="store_true", help="Replace viewport screenshots with a text description from a local vision model (requires Ollama)")
    parser.add_argument("--vision-model", default="llava:7b", help="Ollama vision model to use (default: llava:7b)")
    parser.add_argument("--vision-url", default="http://localhost:11434", help="Ollama base URL (default: http://localhost:11434)")
    return parser
```

Then in `main()`, replace the inline parser construction and `args = parser.parse_args()` with:

```python
    args = _build_arg_parser().parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    state.vision_summary = args.vision_summary
    state.vision_model = args.vision_model
    state.vision_url = args.vision_url
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(f"Connecting to FreeCAD RPC server at: {state.rpc_host}")
    if state.vision_summary:
        logger.info(f"Vision summary enabled: {state.vision_model} at {state.vision_url}")
```

Keep `import sys` in `main()` and leave the rest of `main()` unchanged.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
./check tests/test_vision.py -v
```

Expected: **23 passed.**

- [ ] **Step 6: Verify the CLI and that the default path is unchanged**

```bash
uv run --extra dev python -c "
from freecad_mcp.server import _build_arg_parser
p = _build_arg_parser()
print(p.parse_args([]))
print(p.parse_args(['--vision-summary']))
"
./check tests/test_project_metadata.py -q
```

Expected: both parse cleanly with `vision_summary=False` then `True`, and 36 passed.

- [ ] **Step 7: Commit**

```bash
git add src/freecad_mcp/server.py tests/test_vision.py
git commit -m "$(cat <<'EOF'
feat(vision): add --vision-summary, --vision-model and --vision-url

The server's duplicate screenshot helper becomes a thin wrapper over the
shared implementation, so its ~60 call sites are untouched. The argument
parser moves to a module-level function so flag parsing is testable
without invoking main().

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Per-call prompts, and route `get_view` through the choke point

This task also fixes the pre-existing bug where `get_view` ignores `--only-text-feedback`.

**Files:**
- Modify: `src/freecad_mcp/operations/core.py:113-123`
- Modify: `src/freecad_mcp/server.py` — `execute_code` (~line 591) and `get_view` (~line 616)
- Modify: `tests/test_vision.py` (append)

**Interfaces:**
- Consumes: the consolidated helper from Task 2, the wrapper from Task 3
- Produces: `get_view_operation(freecad, view_name, width, height, focus_object, only_text_feedback, *, vision_summary, vision_model, vision_url, vision_prompt)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vision.py`:

```python
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
        assert all(getattr(item, "type", None) != "image" for item in out)

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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_vision.py -v
```

Expected: 23 pass; `test_returns_image_by_default` and `test_focus_object_is_passed_through_verbatim`
and `test_no_screenshot_returns_explanatory_text` fail with `TypeError` (too many arguments), and
`test_honours_only_text_feedback`, `test_vision_summary_replaces_the_image` and both
`TestToolSignatures` tests fail.

- [ ] **Step 3: Route `get_view_operation` through the shared helper**

In `src/freecad_mcp/operations/core.py`, replace `get_view_operation` (lines 113-123) with:

```python
def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
    only_text_feedback: bool = False,
    *,
    vision_summary: bool = False,
    vision_model: str = vision.DEFAULT_OLLAMA_MODEL,
    vision_url: str = vision.DEFAULT_OLLAMA_URL,
    vision_prompt: str | None = None,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
    if screenshot is None:
        return text_response("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")
    return add_screenshot_if_available(
        [],
        screenshot,
        only_text_feedback,
        vision_summary=vision_summary,
        vision_model=vision_model,
        vision_url=vision_url,
        vision_prompt=vision_prompt,
    )
```

Add `from .. import vision` to the imports at the top of `operations/core.py`. `ImageContent` may
now be unused in that file — check and remove it from the imports if so.

- [ ] **Step 4: Add the tool parameters**

In `src/freecad_mcp/server.py`, change `execute_code`'s signature and its screenshot call:

```python
def execute_code(ctx: Context, code: str, vision_prompt: str | None = None) -> list[TextContent | ImageContent]:
```

and add to its docstring `Args:` block, after the `code:` line:

```
        vision_prompt: Optional question to ask the vision model about the resulting
            screenshot. Only used when the server runs with --vision-summary.
```

and change the return line from `return add_screenshot_if_available(response, screenshot)` to:

```python
            return add_screenshot_if_available(response, screenshot, vision_prompt)
```

Then change `get_view`: add `vision_prompt: str | None = None` as the last parameter, add the same
docstring line to its `Args:` block, and replace its return with:

```python
    return get_view_operation(
        get_freecad_connection(),
        view_name,
        width,
        height,
        focus_object,
        state.only_text_feedback,
        vision_summary=state.vision_summary,
        vision_model=state.vision_model,
        vision_url=state.vision_url,
        vision_prompt=vision_prompt,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
./check tests/test_vision.py -v
```

Expected: **30 passed.**

- [ ] **Step 6: Verify nothing else regressed**

```bash
./check tests/test_project_metadata.py -q
uv run --extra dev python -c "import freecad_mcp.server; print('server imports OK')"
grep -rn 'ImageContent(type="image"' src/freecad_mcp/
```

Expected: 36 passed, `server imports OK`, and the grep returns **exactly one** line —
`src/freecad_mcp/responses.py`. That single result is the proof that the choke point is now real.

- [ ] **Step 7: Commit**

```bash
git add src/freecad_mcp/operations/core.py src/freecad_mcp/server.py tests/test_vision.py
git commit -m "$(cat <<'EOF'
feat(vision): add vision_prompt to execute_code and get_view

get_view_operation built ImageContent directly, bypassing the shared
helper and never consulting only_text_feedback — so get_view returned a
full screenshot even when the user asked for text only. It now routes
through the helper, fixing that and bringing the last bypass onto the
choke point.

The per-call prompt is a real parameter rather than the proxy's
`# __vision__:` comment and `focus_object="Name|prompt"` overload, both
of which existed only because a proxy cannot change tool schemas.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`, `docs/API_REFERENCE.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: everything from Tasks 1-4
- Produces: nothing

- [ ] **Step 1: Document the flags in the README**

In `README.md`, immediately after the `--host` / Remote Connections material and before the
`## Features` section, add:

```markdown
## Vision summary (optional)

Viewport screenshots cost roughly 2,000-5,000 tokens each. If you run
[Ollama](https://ollama.com/) locally with a vision model, the server can replace each screenshot
with a short text description instead:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "--from", "git+https://codeberg.org/wibbit/freecad-mcp", "freecad-mcp",
        "--vision-summary"
      ]
    }
  }
}
```

| Flag | Default | Meaning |
|---|---|---|
| `--vision-summary` | off | Replace screenshots with a text description |
| `--vision-model` | `llava:7b` | Ollama model to use |
| `--vision-url` | `http://localhost:11434` | Ollama base URL |

`execute_code` and `get_view` accept a `vision_prompt` argument to ask something specific about
that particular screenshot, for example *"Is there a gap between the sleeve and the bore?"*.

If Ollama is unreachable the response says so — the screenshot is not sent instead, since that
would silently undo the token saving. `--only-text-feedback` takes precedence over this feature and
suppresses descriptions as well as images.
```

- [ ] **Step 2: Document the parameter in the API reference**

In `docs/API_REFERENCE.md`, find the `execute_code` and `get_view` entries and add `vision_prompt`
to each parameter list:

```markdown
- `vision_prompt` (str, optional): Question to ask the vision model about the resulting screenshot. Only used when the server runs with `--vision-summary`; ignored otherwise.
```

- [ ] **Step 3: Add CHANGELOG entries**

In `CHANGELOG.md`, in the `## [Unreleased] - 2026-08-02` entry, add to `### ✨ Added`:

```markdown
- **In-server vision summary** — `--vision-summary` replaces viewport screenshots with a short text
  description from a local Ollama vision model, saving roughly 2,000-5,000 tokens per call.
  `--vision-model` and `--vision-url` configure it; `execute_code` and `get_view` take an optional
  `vision_prompt` for per-call questions. Off by default. Replaces the standalone
  `freecad-mcp-proxy.py`, which is removed.
```

and to `### 🐛 Fixed`:

```markdown
- **`get_view` ignored `--only-text-feedback`** — it constructed its image response directly rather
  than going through the shared screenshot helper, so it returned a full base64 screenshot even when
  the user had asked for text-only output. All screenshot paths now route through one place.
```

- [ ] **Step 4: Verify**

```bash
./check tests/test_project_metadata.py -q
grep -c "vision" README.md docs/API_REFERENCE.md CHANGELOG.md
```

Expected: 36 passed, and all three files return a non-zero count.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/API_REFERENCE.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: document the vision summary flags and vision_prompt

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Migrate the live setup, then delete the proxy — GATED

> **STOP.** Step 2 changes the maintainer's live MCP configuration and Step 5 deletes files.
> Present the verification result from Step 3 and obtain explicit approval before Step 4.
> The proxy is the maintainer's working FreeCAD tooling; deleting it before the replacement is
> proven leaves them without CAD tools.

**Files:**
- Modify: `~/.claude.json` (outside the repository)
- Delete: `freecad-mcp-proxy.py`, `freecad-mcp-proxy.TODO.md`

**Interfaces:**
- Consumes: everything from Tasks 1-5
- Produces: nothing

- [ ] **Step 1: Record the current configuration**

```bash
python3 -c "
import json, os
p = os.path.expanduser('~/.claude.json')
d = json.load(open(p))
print(json.dumps(d['mcpServers']['freecad'], indent=2))
" | tee /home/dfurlong/git/freecad-mcp/.superpowers/sdd/freecad-mcp-config-before.json
```

Expected: the current entry, running `python3 /home/dfurlong/git/freecad-mcp/freecad-mcp-proxy.py`.
Keep this file — it is the rollback.

- [ ] **Step 2: Repoint the configuration at the server**

Edit `~/.claude.json` so the `freecad` MCP server entry becomes:

```json
{
  "type": "stdio",
  "command": "uv",
  "args": [
    "--directory", "/home/dfurlong/git/freecad-mcp",
    "run", "freecad-mcp",
    "--vision-summary"
  ],
  "env": {}
}
```

- [ ] **Step 3: Verify the replacement works before deleting anything**

The MCP server is launched by the client, so it must be restarted to pick this up. Report to the
maintainer that they need to restart their Claude Code session, then confirm:

1. `get_freecad_status` returns the active document — the server is running through the new path.
2. `get_view` with `--vision-summary` active returns a **text description**, not an image.
3. `get_view(view_name="Isometric", vision_prompt="How many distinct objects are visible?")`
   returns a description that answers that question.

If Ollama is not running, expect the bracketed "vision model unavailable" text rather than an
error — that is correct behaviour and still proves the path works.

- [ ] **Step 4: GATE — obtain explicit approval**

Present the Step 3 results and ask whether to delete the proxy. **Wait for an explicit yes.**
Do not infer approval from earlier instructions.

- [ ] **Step 5: Delete the proxy**

```bash
git rm freecad-mcp-proxy.py freecad-mcp-proxy.TODO.md
grep -rn "freecad-mcp-proxy" --include="*.md" --include="*.py" --include="*.toml" . | grep -v '.venv/' | grep -v 'docs/superpowers/' | grep -v '.superpowers/'
```

Expected: both files removed, and the grep returns **no output** apart from `CHANGELOG.md`
references, which are historical and correct.

- [ ] **Step 6: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore: remove the standalone vision proxy

Superseded by in-server summarisation. The script hardcoded an absolute
path, a project-specific default prompt, and the Ollama endpoint, and
carried a bug where the get_view per-call prompt was extracted but the
argument forwarded unmodified, so the object name never matched.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Close the issue**

```bash
curl -s -X PATCH -H "Authorization: token $CODEBERG_RW_TOKEN" \
  -H "Content-Type: application/json" \
  https://codeberg.org/api/v1/repos/wibbit/freecad-mcp/issues/1 \
  -d '{"state": "closed"}' | python3 -c "import json,sys; d=json.load(sys.stdin); print('issue #%s is now %s' % (d['number'], d['state']))"
```

Expected: `issue #1 is now closed`. Never echo the token.

---

## Post-implementation verification

- [ ] **Full suite passes**

```bash
./check tests/test_vision.py tests/test_project_metadata.py -q
```

Expected: 66 passed (30 vision + 36 metadata).

- [ ] **Exactly one place constructs an image response**

```bash
grep -rn 'ImageContent(type="image"' src/freecad_mcp/
```

Expected: one line, in `src/freecad_mcp/responses.py`.

- [ ] **No project-specific prompt text survives**

```bash
grep -rni "parasol\|stabiliser" src/ README.md docs/API_REFERENCE.md
```

Expected: no output. The check is scoped to `src/` and user-facing docs deliberately —
`tests/test_vision.py` contains those words legitimately, in the list of terms it forbids the
default prompt from using.

- [ ] **Default behaviour is unchanged.** With `--vision-summary` absent, `get_view` returns an
image and `execute_code` returns text plus an image, exactly as before.
