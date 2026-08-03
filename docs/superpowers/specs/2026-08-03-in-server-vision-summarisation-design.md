# Design: in-server vision summarisation

**Date:** 2026-08-03
**Status:** Approved for planning
**Issue:** [#1 — Integrate the vision proxy into the package](https://codeberg.org/wibbit/freecad-mcp/issues/1)

## Problem

`freecad-mcp-proxy.py` is an MCP stdio proxy that sits between the editor and the server. It
intercepts base64 viewport screenshots in tool responses, sends them to a local Ollama vision
model, and replaces the image blob with a short text description — saving roughly 2,000-5,000
tokens per `execute_code` or `get_view` call.

It works and is in production use, but it is not part of the package:

- It hardcodes the Ollama base URL, the model, the log path, a **project-specific** default
  prompt (describing a parasol holder assembly), and the absolute path
  `/home/dfurlong/git/freecad-mcp` in `UPSTREAM_CMD`. As committed it cannot run for anyone else.
- Its usage docstring hardcodes `/home/dfurlong/git/freecad-mcp-proxy.py`, a path that no longer
  exists since the file moved into the repository.
- It carries a latent bug (see below).

## The `focus_object` bug

The proxy supports a per-call prompt via `focus_object="Name|prompt"`. `stdin_to_upstream`
extracts the prompt, then forwards the message **unchanged**:

```python
custom = _extract_vision_prompt(msg)      # reads "Name|prompt"
...
proc.stdin.write(line)                    # writes the ORIGINAL line
```

So the server receives `focus_object="SleeveDrainHoles|Is there a gap…"` as an object *name* and
cannot find it. The `execute_code` form is harmless — a `# __vision__:` comment is valid Python —
but the `get_view` form is broken. This design removes the bug structurally rather than patching it.

## Decisions

### 1. Summarise in the server, not in a proxy

The proxy's own TODO recommended keeping it a separate process ("option (a)"), reasoning that
folding it into the server would be the bigger change. Reading the code shows the opposite.

The server has a **single choke point**: `add_screenshot_if_available` is a 9-line function called
from 61 places, and every screenshot in the server passes through one `response.append(ImageContent(...))`
line. Summarising there means changing that line; only two call sites (`execute_code` and
`get_view`, which gain a prompt parameter) change at all, and the other 59 need nothing. The
adjacent `state.only_text_feedback` check already proves the pattern.

Most of the proxy's 245 lines exist *only because it is a separate process*:

| Machinery | Why it exists | Needed in-server |
|---|---|---|
| `subprocess.Popen` + `UPSTREAM_CMD` | must launch the server | No |
| Two pump threads + epoll workaround | must relay stdio both ways | No |
| `json.loads`/`dumps` per message | must re-parse a protocol the server already speaks | No |
| `_pending_prompts` + lock + `_pop_prompt` | cannot tell which prompt belongs to which screenshot, so correlates by request id | No |
| Forwarding args it also wants to modify | — | No (this is the bug above) |

The correlation map is the tell: it solves a problem the architecture creates. In `get_view`, the
prompt and the screenshot are in the same function call.

**Rejected: packaged proxy.** Its real advantage is generality — it strips images from *any* MCP
response, including tools added later, and could front other servers entirely. That is a genuine
argument, but for a general-purpose tool rather than for this repository. It also leaves the
`focus_object` bug to be fixed separately.

**Accepted risk:** this edits a working 79-tool server, where a bad change breaks CAD work rather
than only vision. Mitigated by the change being confined to one function plus one new module, and
by the new module being unit-testable without FreeCAD.

### 2. Configuration: three CLI flags

```
--vision-summary              enable; off by default
--vision-model  llava:7b      Ollama model
--vision-url    http://localhost:11434
```

Flags match the server's existing idiom (`--only-text-feedback`, `--host` via argparse). No config
file and no environment variables: an MCP client passes `args` directly, so flags are both
sufficient and discoverable via `--help`.

**Off by default** because the feature requires a running Ollama with a vision model, which almost
no user will have. Enabling it is an explicit choice.

The default prompt is **baked in and generic**, not configurable. The current project-specific
default only ever made sense for one model; per-call prompts cover specific questions. A
configurable default was considered and rejected as unnecessary.

The log path is not configurable either — the server already has logging; the proxy's separate
`/tmp/freecad-mcp-proxy.log` disappears with the proxy.

### 3. `--only-text-feedback` takes precedence

If both flags are set, `only_text_feedback` wins and no description is produced. It reads as "send
me no visual content at all", and the more restrictive flag winning is predictable. Someone who set
it to save tokens should not then pay for an Ollama round trip.

### 4. Per-call prompts become a real parameter

`execute_code` and `get_view` gain an optional `vision_prompt: str | None = None`.

This replaces both existing conventions: the `# __vision__: <prompt>` comment and the
`focus_object="Name|prompt"` overload. Both were workarounds for a proxy that could not change tool
schemas. In-server, a real parameter is discoverable in the MCP tool schema, needs no string
parsing, and removes the `focus_object` bug by construction.

Adding an optional parameter is backward compatible. The old conventions are **not** retained —
keeping them would mean two documented ways to do one thing, and the `focus_object` form is the bug.

### 5. The proxy is deleted

`freecad-mcp-proxy.py` and `freecad-mcp-proxy.TODO.md` are removed once in-server summarisation is
verified working. Nothing else in the repository references them.

`~/.claude.json` currently runs the proxy script and is the maintainer's live FreeCAD tooling. It is
repointed at the server with `--vision-summary`, and **that must be verified working before the files
are deleted**.

## Components

### `src/freecad_mcp/vision.py` (new)

One responsibility: turn a base64 PNG into a text description. Knows nothing about MCP, tools, or
FreeCAD.

- `DEFAULT_VISION_PROMPT` — a generic FreeCAD viewport prompt: which objects are visible and their
  shapes, how they are positioned relative to one another, visible gaps, intersections or
  misalignments, and obvious geometry problems.
- `summarise(image_b64, prompt, *, url, model, timeout=60) -> str` — returns the description, or a
  bracketed failure string. Never raises.

Injectable for testing: the HTTP call goes through a module-level seam a test can replace, so no
network is needed.

### `server.py` (modified)

- `main()` — three new argparse flags stored on `state`.
- `add_screenshot_if_available(response, screenshot, vision_prompt=None)` — one new branch.
- `execute_code` and `get_view` — new optional `vision_prompt` parameter, passed through.

No other tool signature changes.

## Data flow

1. A tool runs and obtains a screenshot (base64 PNG).
2. It calls `add_screenshot_if_available(response, screenshot, vision_prompt)`.
3. The function decides:

| Condition | Appended to the response |
|---|---|
| `state.only_text_feedback` | the existing "visual preview unavailable" note — unchanged |
| `state.vision_summary` and a screenshot exists | `TextContent` holding the description |
| neither | `ImageContent` — unchanged |

Order matters: `only_text_feedback` is tested first (decision 3).

When `vision_summary` is on, **every** tool's screenshot is summarised — matching the proxy, which
replaced every image in every response. Only `execute_code` and `get_view` accept a custom prompt;
the rest use the default.

## Error handling

If Ollama is unreachable, times out, or returns an empty response, the response gets a text item
naming the failure and the URL to check. The raw image is **not** substituted back.

This is deliberate and is the one choice worth revisiting in review: a broken Ollama silently costs
all visual feedback rather than degrading to normal screenshots. Falling back to the image would
undo the token saving the flag was enabled for, and would do so invisibly — the user asked for
descriptions, and quietly returning 5,000 tokens of base64 instead is a worse surprise than a
visible error. This matches the proxy's current behaviour.

The timeout stays a constant 60 seconds, as in the proxy.

## Testing

`tests/test_vision.py` (new), requiring neither FreeCAD nor Ollama:

- `summarise` on success returns the model's text.
- Empty model response, HTTP error, and timeout each produce the bracketed failure string, and
  none raise.
- The three-way branch in `add_screenshot_if_available`: image mode, summary mode, and
  `only_text_feedback` precedence when both flags are set.

This is the repository's first behavioural test coverage — the existing suites either need a live
FreeCAD or assert on project metadata.

## Documentation

Per `CLAUDE.md`, in the same commits as the code:

- `docs/API_REFERENCE.md` — the `vision_prompt` parameter on both tools.
- `README.md` — the three flags and the Ollama prerequisite.
- `CHANGELOG.md` — `[Unreleased]` entries for the feature, the removed proxy, and the fixed
  `focus_object` bug.

## Success criteria

1. `--vision-summary` replaces screenshots with descriptions across all tools that return them.
2. `--vision-model` and `--vision-url` are honoured; defaults are `llava:7b` and
   `http://localhost:11434`.
3. With `--vision-summary` absent, behaviour is byte-for-byte what it is today.
4. `--only-text-feedback` suppresses descriptions as well as images.
5. `vision_prompt` on `execute_code` and `get_view` overrides the default prompt.
6. `get_view(focus_object="Name")` finds the object — no `|` parsing anywhere.
7. Ollama being down produces a visible error, never a crash and never a silent image fallback.
8. `tests/test_vision.py` passes without FreeCAD or Ollama running.
9. `freecad-mcp-proxy.py` and its TODO are gone, and no project-specific prompt text survives.
10. The maintainer's live setup runs the server directly and is verified working before removal.

## Out of scope

- Any change to the 59 call sites that pass no `vision_prompt`.
- Configurable log paths, timeouts, or default prompt.
- Vision providers other than Ollama.
- Summarising anything other than screenshots.
