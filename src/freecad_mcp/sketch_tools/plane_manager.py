import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from ..responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.plane_manager")


def create_datum_plane(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    plane_name: str,
    alignment: str = "xy",
    offset: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Create a datum plane in FreeCAD aligned with the specified orientation.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        plane_name: Name for the datum plane
        alignment: Plane alignment ('xy', 'xz', 'yz')
        offset: Offset distance from origin
        
    Returns:
        List of text/image content with result
    """
    try:
        alignment_map = {"xy": "xy", "xz": "xz", "yz": "yz"}
        mapmode_map = {"xy": "ObjectXY", "xz": "ObjectXZ", "yz": "ObjectYZ"}
        
        if alignment.lower() not in alignment_map:
            return [
                TextContent(
                    type="text",
                    text=f"Invalid alignment '{alignment}'. Must be one of: xy, xz, yz"
                )
            ]
        
        al = alignment.upper()
        code = f"""
import FreeCAD as App
import math
doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    body = doc.addObject('PartDesign::Body', '{plane_name}')
    plane = doc.addObject('PartDesign::Plane', '{plane_name}_Datum')
    body.addObject(plane)
    plane.MapMode = 'Deactivated'
    _placements = {{
        'XY': App.Placement(App.Vector(0, 0, {offset}), App.Rotation(0, 0, 0)),
        'XZ': App.Placement(App.Vector(0, {offset}, 0), App.Rotation(App.Vector(1, 0, 0), 90)),
        'YZ': App.Placement(App.Vector({offset}, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90)),
    }}
    plane.Placement = _placements.get('{al}', _placements['XY'])
    doc.recompute()
    print("SUCCESS: Datum plane '{plane_name}_Datum' created with alignment '{alignment}'")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()

        ok, msg = parse_execute_result(res)
        if ok:
            response = [
                TextContent(
                    type="text",
                    text=f"Datum plane '{plane_name}' created successfully with alignment '{alignment}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create datum plane: {msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)

    except Exception as e:
        logger.error(f"Failed to create datum plane: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create datum plane: {str(e)}")
        ]


def add_datum_plane_to_body(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    body_name: str,
    plane_name: str,
    alignment: str = "xy",
    offset: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Add a datum plane to an existing PartDesign Body.

    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        body_name: Name of the existing PartDesign::Body to add the plane to
        plane_name: Name for the new datum plane
        alignment: Plane orientation ('xy', 'xz', 'yz')
        offset: Offset distance from origin along the normal axis

    Returns:
        List of text/image content with result
    """
    try:
        if alignment.lower() not in ("xy", "xz", "yz"):
            return [TextContent(type="text", text=f"Invalid alignment '{alignment}'. Must be one of: xy, xz, yz")]

        al = alignment.upper()
        code = f"""
import FreeCAD as App
import math
doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    body = doc.getObject('{body_name}')
    if not body:
        print("ERROR: Body '{body_name}' not found")
    elif 'Body' not in body.TypeId:
        print("ERROR: '{body_name}' is not a PartDesign::Body")
    else:
        plane = body.newObject('PartDesign::Plane', '{plane_name}')
        plane.MapMode = 'Deactivated'
        _placements = {{
            'XY': App.Placement(App.Vector(0, 0, {offset}), App.Rotation(0, 0, 0)),
            'XZ': App.Placement(App.Vector(0, {offset}, 0), App.Rotation(App.Vector(1, 0, 0), 90)),
            'YZ': App.Placement(App.Vector({offset}, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90)),
        }}
        plane.Placement = _placements.get('{al}', _placements['XY'])
        doc.recompute()
        print("SUCCESS: Datum plane '{plane_name}' added to body '{body_name}' with alignment '{alignment}'")
"""
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()

        ok, msg = parse_execute_result(res)
        if ok:
            response = [TextContent(type="text", text=f"Datum plane '{plane_name}' added to body '{body_name}' with alignment '{alignment}'")]
            return add_screenshot_helper(response, screenshot)
        else:
            response = [TextContent(type="text", text=f"Failed to add datum plane: {msg}")]
            return add_screenshot_helper(response, screenshot)

    except Exception as e:
        logger.error(f"Failed to add datum plane to body: {str(e)}")
        return [TextContent(type="text", text=f"Failed to add datum plane to body: {str(e)}")]


