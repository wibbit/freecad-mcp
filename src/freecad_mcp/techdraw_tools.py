import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context
from .responses import parse_execute_result

logger = logging.getLogger("FreeCADMCPserver.techdraw_tools")

_DIMENSION_TYPES = {"DistanceX", "DistanceY", "Distance", "Radius", "Diameter", "Angle"}


def add_techdraw_dimension(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    page_name: str,
    view_name: str,
    dimension_type: str,
    references: list[str],
    x: float = 0.0,
    y: float = 0.0,
    dimension_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a dimension annotation to a TechDraw view.

    Call get_shape_topology on the source object to discover edge/vertex names, then
    use get_objects to find the projected view name on the page. References are edge
    or vertex names from the projected 2D view (e.g. 'Edge1', 'Vertex2').

    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        page_name: Name of the TechDraw page
        view_name: Name of the DrawViewPart on the page
        dimension_type: One of 'DistanceX', 'DistanceY', 'Distance', 'Radius', 'Diameter', 'Angle'
        references: List of edge or vertex names from the projected view (e.g. ['Edge1', 'Edge3'])
        x: Horizontal position of the dimension label on the page (mm, default 0)
        y: Vertical position of the dimension label on the page (mm, default 0)
        dimension_name: Optional name for the dimension object

    Returns:
        List of text/image content with result
    """
    if dimension_type not in _DIMENSION_TYPES:
        return [TextContent(type="text", text=f"Invalid dimension_type '{dimension_type}'. Choose from: {sorted(_DIMENSION_TYPES)}")]

    dim_name = dimension_name or f"{view_name}_{dimension_type}"
    refs_str = str(references)

    code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    page = doc.getObject('{page_name}')
    view = doc.getObject('{view_name}')
    if not page:
        print("ERROR: Page '{page_name}' not found")
    elif not view:
        print("ERROR: View '{view_name}' not found")
    else:
        dim = doc.addObject('TechDraw::DrawViewDimension', '{dim_name}')
        dim.Type = '{dimension_type}'
        dim.References2D = [(view, {refs_str})]
        dim.X = {x}
        dim.Y = {y}
        page.addView(dim)
        doc.recompute()
        print(f"SUCCESS: Dimension '{{dim.Name}}' ({dimension_type}) added to '{view_name}' on page '{page_name}'")
"""

    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()

    ok, msg = parse_execute_result(res)
    if ok:
        response = [TextContent(type="text", text=f"Dimension '{dim_name}' ({dimension_type}) added to view '{view_name}'")]
        return add_screenshot_helper(response, screenshot)
    else:
        response = [TextContent(type="text", text=f"Failed to add dimension: {msg}")]
        return add_screenshot_helper(response, screenshot)
