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
