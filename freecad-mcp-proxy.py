#!/usr/bin/env python3
"""
freecad-mcp-proxy.py

MCP stdio proxy that sits between Claude Code and freecad-mcp.
Intercepts tool responses containing base64 FreeCAD screenshots,
sends them to a local Ollama llava:7b instance for summarisation,
and replaces the raw image blob with a short text description.

Net effect: removes ~2000-5000 tokens of base64 per execute_code call.

Per-call custom vision prompts:
- execute_code: add a comment at the top of the code block:
    # __vision__: Describe whether the sleeve outer wall is flush with the holder bore...
- get_view: append |PROMPT to focus_object:
    focus_object="SleeveDrainHoles|Is there a gap between sleeve and holder bore?"

Usage (via ~/.claude.json mcpServers):
  "command": "python3",
  "args": ["/home/dfurlong/git/freecad-mcp-proxy.py"]
"""

import json
import logging
import re
import subprocess
import sys
import threading
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OLLAMA_BASE   = "http://localhost:11434"
OLLAMA_MODEL  = "llava:7b"
LOG_FILE      = "/tmp/freecad-mcp-proxy.log"

DEFAULT_VISION_PROMPT = (
    "This is a FreeCAD 3D model viewport screenshot of a parasol holder assembly. "
    "The assembly has three main parts: (1) a rectangular holder body with a central cylindrical bore, "
    "(2) a cylindrical sleeve that sits inside the bore, and (3) a stepped cylindrical table stabiliser. "
    "Describe in 4-6 sentences: which parts are visible, their overall shape, "
    "the fit between the sleeve outer wall and the holder bore (snug or visible gap?), "
    "any geometry problems (missing faces, wrong proportions), "
    "and any chamfers or fillets at bore entries. Be specific about gaps."
)

UPSTREAM_CMD = [
    "uv", "--directory", "/home/dfurlong/git/freecad-mcp",
    "run", "freecad-mcp"
]

# ---------------------------------------------------------------------------
# Logging — file only (stdout/stderr are the MCP pipe)
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("proxy")
log.info("freecad-mcp-proxy starting")

# ---------------------------------------------------------------------------
# Per-request vision prompt state  {request_id: prompt_string}
# ---------------------------------------------------------------------------
_pending_prompts: dict = {}
_pending_lock = threading.Lock()


def _store_prompt(req_id, prompt: str):
    with _pending_lock:
        _pending_prompts[req_id] = prompt


def _pop_prompt(req_id) -> str:
    with _pending_lock:
        return _pending_prompts.pop(req_id, DEFAULT_VISION_PROMPT)


# ---------------------------------------------------------------------------
# Extract custom vision prompt from an inbound tool-call message
# ---------------------------------------------------------------------------
def _extract_vision_prompt(msg: dict) -> str | None:
    """Return a custom vision prompt if the tool call contains one, else None."""
    try:
        method = msg.get("method", "")
        if method != "tools/call":
            return None
        args = msg.get("params", {}).get("arguments", {})
        name = msg.get("params", {}).get("name", "")

        if name == "execute_code":
            code = args.get("code", "")
            # Look for  # __vision__: <prompt>  on its own line
            m = re.search(r"#\s*__vision__:\s*(.+)", code)
            if m:
                return m.group(1).strip()

        if name == "get_view":
            focus = args.get("focus_object") or ""
            if "|" in focus:
                return focus.split("|", 1)[1].strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Ollama helper
# ---------------------------------------------------------------------------
def ask_llava(base64_data: str, prompt: str) -> str:
    payload = json.dumps({
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "images": [base64_data],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    log.debug("Sending image to llava (%d b64 chars)", len(base64_data))
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read()).get("response", "")
        if not result:
            raise ValueError("llava returned empty response")
        log.debug("llava replied: %s", result[:500])
        return result


# ---------------------------------------------------------------------------
# Response processor — always replaces images; never passes base64 through
# ---------------------------------------------------------------------------
def _replace_images_in_content(content: list, prompt: str) -> list:
    new_content = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image":
            b64 = item.get("data", "")
            log.info("Image found (%d b64 chars) — calling llava", len(b64))
            if not b64:
                new_content.append({"type": "text", "text": "[FreeCAD viewport: no image data]"})
                continue
            try:
                description = ask_llava(b64, prompt)
                new_content.append({
                    "type": "text",
                    "text": f"[FreeCAD viewport — {OLLAMA_MODEL}]: {description}",
                })
            except Exception as exc:
                log.error("llava FAILED: %s", exc)
                new_content.append({
                    "type": "text",
                    "text": (
                        f"[FreeCAD viewport — llava UNAVAILABLE ({exc}): "
                        "image suppressed. Check Ollama: curl http://localhost:11434/api/tags]"
                    ),
                })
        else:
            new_content.append(item)
    return new_content


def process_response(obj: dict, prompt: str) -> dict:
    """Replace every image content item with an Ollama text description."""
    for key in ("result", "params"):
        val = obj.get(key)
        if isinstance(val, dict) and isinstance(val.get("content"), list):
            val["content"] = _replace_images_in_content(val["content"], prompt)
    return obj


# ---------------------------------------------------------------------------
# Proxy — uses threads for stdin/stdout to avoid epoll permission issues
# on systems where Claude Code's pipe fds are not epollable (Python 3.14+)
# ---------------------------------------------------------------------------
def run_proxy():
    proc = subprocess.Popen(
        UPSTREAM_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr.buffer,
    )
    log.info("Upstream started (pid %d)", proc.pid)

    def stdin_to_upstream():
        """Forward Claude → freecad-mcp, extracting per-call vision prompts."""
        try:
            for line in sys.stdin.buffer:
                log.debug("→ upstream: %s", line[:120])
                try:
                    msg = json.loads(line.rstrip(b"\r\n"))
                    req_id = msg.get("id")
                    custom = _extract_vision_prompt(msg)
                    if req_id is not None and custom:
                        _store_prompt(req_id, custom)
                        log.debug("Custom vision prompt stored for id=%s: %s", req_id, custom[:80])
                except (json.JSONDecodeError, Exception):
                    pass
                proc.stdin.write(line)
                proc.stdin.flush()
        except Exception as exc:
            log.error("stdin_to_upstream error: %s", exc)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    def upstream_to_stdout():
        """Forward freecad-mcp → Claude, replacing images with llava descriptions."""
        try:
            for line in proc.stdout:
                stripped = line.rstrip(b"\r\n")
                if not stripped:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
                    continue
                try:
                    obj = json.loads(stripped)
                    req_id = obj.get("id")
                    prompt = _pop_prompt(req_id) if req_id is not None else DEFAULT_VISION_PROMPT
                    obj = process_response(obj, prompt)
                    out = json.dumps(obj).encode() + b"\n"
                except (json.JSONDecodeError, UnicodeDecodeError):
                    out = line
                log.debug("← Claude: %s", out[:120])
                sys.stdout.buffer.write(out)
                sys.stdout.buffer.flush()
        except Exception as exc:
            log.error("upstream_to_stdout error: %s", exc)

    t_in  = threading.Thread(target=stdin_to_upstream,  daemon=True)
    t_out = threading.Thread(target=upstream_to_stdout, daemon=True)
    t_in.start()
    t_out.start()

    # Block until the upstream process exits
    proc.wait()
    log.info("Upstream exited (code %d)", proc.returncode)


if __name__ == "__main__":
    run_proxy()
