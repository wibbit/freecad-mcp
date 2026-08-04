"""Real integration tests for vision summarisation.

tests/test_vision.py is entirely mocked: 5 tests monkeypatch vision._post_json
(no real HTTP), 10 monkeypatch vision.summarise (no real summarisation). Nothing
in that file ever sends an image to a real Ollama and checks what comes back.
The fake _post_json returns {"response": "..."} because that is what we
*believe* Ollama's /api/generate returns — this file exists to verify that
belief against a real endpoint.

Mirrors the skip style of tests/conftest.py's `conn` fixture: probe the real
dependency once per session, and if it is not reachable, skip with a message
that names exactly where we looked and how to point elsewhere.
"""

import base64
import os
import struct
import urllib.request
import zlib

import pytest

from freecad_mcp import responses, vision

OLLAMA_URL = os.environ.get("FREECAD_MCP_TEST_OLLAMA_URL", vision.DEFAULT_OLLAMA_URL)
OLLAMA_MODEL = os.environ.get("FREECAD_MCP_TEST_OLLAMA_MODEL", vision.DEFAULT_OLLAMA_MODEL)

# Vision models can take tens of seconds per call, especially cold.
VISION_TIMEOUT = 120

FAILURE_STRINGS = ("unavailable", "empty response")


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Build a minimal real PNG from stdlib only (no Pillow dependency)."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture(scope="session")
def ollama():
    """Skip the module's tests unless a real, model-equipped Ollama answers.

    Probes the *configured* endpoint (FREECAD_MCP_TEST_OLLAMA_URL, defaulting
    to vision.DEFAULT_OLLAMA_URL) rather than assuming localhost, since the
    machine running these tests may not run Ollama itself.
    """
    req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json

            data = json.loads(resp.read())
    except Exception as exc:
        pytest.skip(
            f"Ollama not reachable at {OLLAMA_URL} ({exc}). "
            "Set FREECAD_MCP_TEST_OLLAMA_URL to point at a running instance."
        )

    installed = [m.get("name", "") for m in data.get("models", [])]
    if OLLAMA_MODEL not in installed:
        pytest.skip(
            f"Model {OLLAMA_MODEL!r} not installed on Ollama at {OLLAMA_URL}. "
            f"Installed models: {installed}. "
            "Set FREECAD_MCP_TEST_OLLAMA_MODEL to point at an installed one."
        )
    return True


@pytest.fixture(scope="session")
def sample_png_b64():
    png_bytes = _png(64, 64, (200, 40, 40))
    return base64.b64encode(png_bytes).decode()


class TestRealSummarise:
    def test_summarise_returns_real_description(self, ollama, sample_png_b64):
        out = vision.summarise(
            sample_png_b64,
            "Describe this image in one sentence.",
            url=OLLAMA_URL,
            model=OLLAMA_MODEL,
            timeout=VISION_TIMEOUT,
        )
        assert isinstance(out, str)
        assert out.strip() != ""
        assert out.startswith(f"[FreeCAD viewport — {OLLAMA_MODEL}]:")
        lowered = out.lower()
        for failure in FAILURE_STRINGS:
            assert failure not in lowered, (
                f"summarise() fell into its error path instead of returning a real "
                f"description: {out!r}"
            )


class TestRealChain:
    def test_chain_replaces_image_with_description(self, ollama, sample_png_b64):
        out = responses.add_screenshot_if_available(
            [],
            sample_png_b64,
            False,
            vision_summary=True,
            vision_url=OLLAMA_URL,
            vision_model=OLLAMA_MODEL,
        )
        assert len(out) == 1
        item = out[0]
        assert item.type == "text"
        assert item.type != "image"
        lowered = item.text.lower()
        for failure in FAILURE_STRINGS:
            assert failure not in lowered, f"Got a failure string instead of a description: {item.text!r}"

    def test_custom_vision_prompt_reaches_the_model(self, ollama, sample_png_b64):
        colour_prompt = (
            "Reply with exactly one word: the single dominant colour you see in this image."
        )
        count_prompt = (
            "Count the distinct geometric shapes visible in this image and reply with "
            "just the number, as a word or digit."
        )

        colour_out = responses.add_screenshot_if_available(
            [],
            sample_png_b64,
            False,
            vision_summary=True,
            vision_url=OLLAMA_URL,
            vision_model=OLLAMA_MODEL,
            vision_prompt=colour_prompt,
        )
        count_out = responses.add_screenshot_if_available(
            [],
            sample_png_b64,
            False,
            vision_summary=True,
            vision_url=OLLAMA_URL,
            vision_model=OLLAMA_MODEL,
            vision_prompt=count_prompt,
        )

        assert len(colour_out) == 1 and len(count_out) == 1
        colour_text = colour_out[0].text
        count_text = count_out[0].text

        for text in (colour_text, count_text):
            lowered = text.lower()
            for failure in FAILURE_STRINGS:
                assert failure not in lowered, f"Got a failure string: {text!r}"

        # Not asserting on specific model output (flaky) — only that two clearly
        # different prompts against the same image produce different answers,
        # which proves the prompt is actually delivered over the wire.
        assert colour_text != count_text
