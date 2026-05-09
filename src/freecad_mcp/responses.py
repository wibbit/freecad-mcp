import json

from mcp.types import ImageContent, TextContent

type ToolResponse = list[TextContent | ImageContent]


def parse_execute_result(res: dict) -> tuple[bool, str]:
    """Parse an execute_code RPC response into (success, message).

    execute_code returns {"success": bool, "data": {"output": str, "stderr": str}, "error": str|None}.
    The executed script signals FreeCAD-level outcomes by printing "SUCCESS: ..." or "ERROR: ..."
    to stdout. This helper reads that output rather than the Python-level "success" flag, which
    only reflects whether exec() ran without raising — not whether the FreeCAD operation worked.
    """
    output = (res.get("data") or {}).get("output", "")
    if res.get("success") and "SUCCESS" in output:
        return True, output.strip()
    if not res.get("success"):
        # Python-level exception: prefer the traceback summary, fall back to stdout
        err = res.get("error") or output or "Unknown error"
    else:
        # Python ran but FreeCAD operation failed (printed ERROR:)
        err = output or "Unknown error"
    return False, err.strip()


def text_response(message: str) -> ToolResponse:
    return [TextContent(type="text", text=message)]


def json_response(data: object) -> ToolResponse:
    return text_response(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def add_screenshot_if_available(
    response: ToolResponse,
    screenshot: str | None,
    only_text_feedback: bool,
) -> ToolResponse:
    if only_text_feedback or screenshot is None:
        return response
    return [*response, ImageContent(type="image", data=screenshot, mimeType="image/png")]
