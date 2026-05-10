import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from ..responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.pocket_manager")


def pocket_sketch(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    sketch_name: str,
    depth: float,
    depth2: float = 0.0,
    through_all: bool = False,
    symmetric: bool = False,
) -> list[TextContent | ImageContent]:
    """Cut a pocket into a PartDesign Body using a sketch profile.

    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        sketch_name: Sketch name defining the pocket profile
        depth: Depth of the pocket in mm
        depth2: Second depth for two-sided pockets (default 0.0)
        through_all: If True, cut through the entire solid (depth is ignored)
        symmetric: If True, cut symmetrically about the sketch plane

    Returns:
        List of text/image content with result
    """
    try:
        if "_sketch" in sketch_name:
            pocket_name = sketch_name.replace("_sketch", "_pocket")
        else:
            pocket_name = f"{sketch_name}_pocket"

        code = f"""
import FreeCAD as App
import PartDesign

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
            print("ERROR: Sketch '{sketch_name}' is not in a Body")
        else:
            pocket = body.newObject('PartDesign::Pocket', '{pocket_name}')
            pocket.Profile = (sketch, [''])
            pocket.ReferenceAxis = (sketch, ['N_Axis'])

            if {through_all}:
                pocket.Type = 1  # ThroughAll
            elif {symmetric}:
                pocket.Midplane = True
                pocket.Type = 0
                pocket.Length = {depth}
            elif {depth2} > 0:
                pocket.Type = 3  # TwoSides
                pocket.Length = {depth}
                pocket.Length2 = {depth2}
            else:
                pocket.Type = 0  # Dimension
                pocket.Length = {depth}

            sketch.ViewObject.Visibility = False
            doc.recompute()
            print(f"SUCCESS: Pocket '{{pocket.Name}}' created from '{sketch_name}' (depth: {depth}mm)")
"""

        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()

        ok, msg = parse_execute_result(res)
        if ok:
            response = [TextContent(type="text", text=f"Pocket '{pocket_name}' created successfully (depth: {depth}mm)")]
            return add_screenshot_helper(response, screenshot)
        else:
            response = [TextContent(type="text", text=f"Failed to create pocket: {msg}")]
            return add_screenshot_helper(response, screenshot)

    except Exception as e:
        logger.error(f"Failed to create pocket: {str(e)}")
        return [TextContent(type="text", text=f"Failed to create pocket: {str(e)}")]
