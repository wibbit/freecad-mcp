import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from ..responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.sketch_manager")


def create_sketch_on_plane(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    plane_name: str,
) -> list[TextContent | ImageContent]:
    """Create a sketch on the specified datum plane.
    
    The sketch will be automatically named as '{plane_name}_sketch'.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        plane_name: Name of the datum plane (Body) to attach the sketch to
        
    Returns:
        List of text/image content with result
    """
    try:
        sketch_name = f"{plane_name}_sketch"
        
        code = f"""
import FreeCAD as App
import Sketcher

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    body = doc.getObject('{plane_name}')
    if not body:
        print("ERROR: Datum plane (Body) '{plane_name}' not found")
    else:
        datum_plane = doc.getObject('{plane_name}_Datum')
        if not datum_plane:
            print("ERROR: Datum plane object '{plane_name}_Datum' not found")
        else:
            sketch = body.newObject('Sketcher::SketchObject', '{sketch_name}')

            sketch.AttachmentSupport = [(datum_plane, '')]
            sketch.MapMode = 'FlatFace'

            doc.recompute()
            print(f"SUCCESS: Sketch '{{sketch.Name}}' created on plane '{plane_name}'")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()

        ok, msg = parse_execute_result(res)
        if ok:
            response = [
                TextContent(
                    type="text",
                    text=f"Sketch '{sketch_name}' created successfully on plane '{plane_name}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create sketch: {msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create sketch: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create sketch: {str(e)}")
        ]


