import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from ..responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.groove_manager")

_AXIS_CHOICES = {"H_Axis", "V_Axis", "X_Axis", "Y_Axis", "Z_Axis"}


def groove(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    sketch_name: str,
    axis: str = "V_Axis",
    angle: float = 360.0,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Create a PartDesign::Groove (subtractive revolve) from a sketch inside a Body.

    The sketch must already exist inside a PartDesign::Body. The groove cuts by
    revolving the sketch profile around the chosen axis.

    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        sketch_name: Sketch inside a Body whose profile will be revolved
        axis: Axis of revolution — one of 'H_Axis' (sketch horizontal),
              'V_Axis' (sketch vertical), 'X_Axis', 'Y_Axis', 'Z_Axis' (default: 'V_Axis')
        angle: Angle of rotation in degrees (default: 360.0 for full groove)
        result_name: Optional name for the groove object (default: '{sketch_name}_groove')

    Returns:
        List of text/image content with result
    """
    if axis not in _AXIS_CHOICES:
        return [TextContent(type="text", text=f"Invalid axis '{axis}'. Choose from: {sorted(_AXIS_CHOICES)}")]

    groove_name = result_name or (
        sketch_name.replace("_sketch", "_groove") if "_sketch" in sketch_name else f"{sketch_name}_groove"
    )

    code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    sketch = doc.getObject('{sketch_name}')
    if not sketch:
        print("ERROR: Sketch '{sketch_name}' not found")
    else:
        body = sketch.getParentGroup()
        if not body or 'Body' not in body.TypeId:
            for obj in doc.Objects:
                if 'Body' in obj.TypeId and hasattr(obj, 'Group') and sketch in obj.Group:
                    body = obj
                    break
        if not body:
            print("ERROR: Sketch '{sketch_name}' is not in a Body — groove requires PartDesign workflow")
        else:
            gr = body.newObject('PartDesign::Groove', '{groove_name}')
            gr.Profile = (sketch, [''])
            gr.Angle = {angle}
            gr.ReferenceAxis = (sketch, ['{axis}'])
            gr.Midplane = False
            gr.Reversed = False
            sketch.ViewObject.Visibility = False
            doc.recompute()
            print(f"SUCCESS: Groove '{{gr.Name}}' created from '{sketch_name}' (axis: {axis}, angle: {angle}°)")
"""

    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()

    ok, msg = parse_execute_result(res)
    if ok:
        response = [TextContent(type="text", text=f"Groove '{groove_name}' created (axis: {axis}, angle: {angle}°)")]
        return add_screenshot_helper(response, screenshot)
    else:
        response = [TextContent(type="text", text=f"Failed to create groove: {msg}")]
        return add_screenshot_helper(response, screenshot)
