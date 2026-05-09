# modeling_tools.py: advanced modeling operations for FreeCAD MCP
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

from .responses import parse_execute_result


def create_loft(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, sketch_names: list[str], result_name: str, solid: bool = True, ruled: bool = False) -> list[TextContent | ImageContent]:
    """Create a loft between multiple sketches"""
    sketches_list = ", ".join([f"doc.getObject('{name}')" for name in sketch_names])
    solid_flag = 'True' if solid else 'False'
    ruled_flag = 'True' if ruled else 'False'
    code = f"""
import FreeCAD as App
import Part
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    sections = [{sketches_list}]
    missing = [n for n, o in zip({sketch_names!r}, sections) if o is None]
    if missing:
        print(f'ERROR: Sketches not found: {{missing}}')
    else:
        loft = doc.addObject('Part::Loft', '{result_name}')
        loft.Sections = sections
        loft.Solid = {solid_flag}
        loft.Ruled = {ruled_flag}
        doc.recompute()
        print('SUCCESS: Loft {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create loft: {msg}')], screenshot)


def create_revolve(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, sketch_name: str, axis: dict[str, dict[str, float]], angle: float, result_name: str) -> list[TextContent | ImageContent]:
    """Create a revolve of a sketch around a given axis"""
    px, py, pz = axis['point']['x'], axis['point']['y'], axis['point']['z']
    dx, dy, dz = axis['direction']['x'], axis['direction']['y'], axis['direction']['z']
    code = f"""
import FreeCAD as App
import Part
from FreeCAD import Base
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    profile = doc.getObject('{sketch_name}')
    if not profile:
        print('ERROR: Sketch {sketch_name} not found')
    else:
        rev = doc.addObject('Part::Revolution', '{result_name}')
        rev.Source = profile
        rev.Axis = Base.Vector({dx},{dy},{dz})
        rev.Base = Base.Vector({px},{py},{pz})
        rev.Angle = {angle}
        rev.Symmetric = False
        doc.recompute()
        print('SUCCESS: Revolve {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create revolve: {msg}')], screenshot)


def create_sweep(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, profile_sketch: str, path_sketch: str, result_name: str) -> list[TextContent | ImageContent]:
    """Sweep a profile along a path"""
    code = f"""
import FreeCAD as App
import Part
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    profile = doc.getObject('{profile_sketch}')
    path = doc.getObject('{path_sketch}')
    if not profile:
        print('ERROR: Profile sketch {profile_sketch} not found')
    elif not path:
        print('ERROR: Path sketch {path_sketch} not found')
    else:
        sweep = doc.addObject('Part::Sweep', '{result_name}')
        sweep.Spine = (path, [""])
        sweep.Sections = [profile]
        sweep.Solid = True
        sweep.Frenet = False
        doc.recompute()
        print('SUCCESS: Sweep {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create sweep: {msg}')], screenshot)


def create_spline_3d(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, points: list[dict[str, float]], spline_name: str, closed: bool = False) -> list[TextContent | ImageContent]:
    """Create a 3D spline through control points"""
    vecs = ', '.join([f'App.Vector({pt["x"]},{pt["y"]},{pt["z"]})' for pt in points])
    close_flag = 'True' if closed else 'False'
    code = f"""
import FreeCAD as App
import Part
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    pts = [{vecs}]
    curve = Part.BSplineCurve()
    curve.interpolate(pts, PeriodicFlag={close_flag})
    spline = doc.addObject('Part::Feature', '{spline_name}')
    spline.Shape = curve.toShape()
    doc.recompute()
    print('SUCCESS: Spline {spline_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create spline: {msg}')], screenshot)
