import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from ..responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.face_sketch_manager")


def create_sketch_on_face(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    body_name: str,
    obj_name: str,
    face_name: str,
    sketch_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Create a sketch attached directly to a named face of an existing solid.

    The face must be planar. Use get_shape_topology to discover valid face names
    before calling this tool — face names like 'Face1' are dynamic and depend on
    geometry creation order.

    The sketch is created inside the specified Body so subsequent extrude /
    pocket operations remain in the same PartDesign feature tree.

    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        body_name: Name of the PartDesign::Body to create the sketch inside
        obj_name: Name of the object whose face to sketch on
        face_name: Face name (e.g. 'Face3') — get from get_shape_topology
        sketch_name: Optional explicit sketch name (default: '{obj_name}_{face_name}_sketch')

    Returns:
        List of text/image content with result
    """
    try:
        auto_name = sketch_name or f"{obj_name}_{face_name}_sketch"

        code = f"""
import FreeCAD as App
import Sketcher

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
        obj = doc.getObject('{obj_name}')
        if not obj:
            print("ERROR: Object '{obj_name}' not found")
        elif not hasattr(obj, 'Shape'):
            print("ERROR: '{obj_name}' has no Shape — cannot attach sketch to face")
        else:
            face_index = int('{face_name}'.replace('Face', '')) - 1
            if face_index < 0 or face_index >= len(obj.Shape.Faces):
                print("ERROR: '{face_name}' is out of range — object has {{len(obj.Shape.Faces)}} face(s)")
            else:
                face = obj.Shape.Faces[face_index]
                if not hasattr(face.Surface, 'Axis'):
                    # Check if planar by testing surface type
                    surface_type = type(face.Surface).__name__
                    if surface_type not in ('Plane',):
                        print(f"WARNING: '{face_name}' surface type is {{surface_type}} — may not be planar; attempting anyway")
                sketch = body.newObject('Sketcher::SketchObject', '{auto_name}')
                sketch.AttachmentSupport = [(obj, '{face_name}')]
                sketch.MapMode = 'FlatFace'
                doc.recompute()
                print(f"SUCCESS: Sketch '{{sketch.Name}}' created on '{face_name}' of '{obj_name}' in body '{body_name}'")
"""
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()

        ok, msg = parse_execute_result(res)
        if ok:
            response = [TextContent(type="text", text=f"Sketch '{auto_name}' created on {face_name} of '{obj_name}' in body '{body_name}'")]
            return add_screenshot_helper(response, screenshot)
        else:
            response = [TextContent(type="text", text=f"Failed to create sketch on face: {msg}")]
            return add_screenshot_helper(response, screenshot)

    except Exception as e:
        logger.error(f"Failed to create sketch on face: {str(e)}")
        return [TextContent(type="text", text=f"Failed to create sketch on face: {str(e)}")]
