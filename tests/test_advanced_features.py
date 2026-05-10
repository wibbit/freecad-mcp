import pytest
from mcp.types import TextContent

from freecad_mcp.modeling_tools_advanced import (
    add_fillet,
    add_chamfer,
    mirror_object,
    circular_pattern,
    linear_pattern,
)
from freecad_mcp.modeling_tools import create_loft
from freecad_mcp.sketch_tools.plane_manager import create_datum_plane
from freecad_mcp.sketch_tools.sketch_manager import create_sketch_on_plane
from freecad_mcp.sketch_tools.extrude_manager import extrude_sketch_bidirectional


def ok(result):
    return (
        result
        and isinstance(result[0], TextContent)
        and (
            "successfully" in result[0].text.lower()
            or "SUCCESS" in result[0].text
            or "created" in result[0].text.lower()
            or "added" in result[0].text.lower()
            or "fillet" in result[0].text.lower()
            or "chamfer" in result[0].text.lower()
            or "mirror" in result[0].text.lower()
            or "pattern" in result[0].text.lower()
        )
    )


def _build_partdesign_solid(conn, doc, mock_ctx, no_screenshot, prefix="pd"):
    """Helper: create datum plane + sketch + rectangle + extrude inside a Body."""
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, f"{prefix}_plane", "xy", 0.0)
    assert r and isinstance(r[0], TextContent) and "successfully" in r[0].text.lower(), \
        f"plane failed: {r}"

    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, f"{prefix}_plane")
    assert r and isinstance(r[0], TextContent) and "successfully" in r[0].text.lower(), \
        f"sketch failed: {r}"

    res = conn.execute_code(f"""
import FreeCAD as App, Part, Sketcher
doc = App.getDocument('{doc}')
sketch = doc.getObject('{prefix}_plane_sketch')
v = [App.Vector(x, y, 0) for x, y in [(0,0),(80,0),(80,60),(0,60)]]
sketch.addGeometry([Part.LineSegment(v[i], v[(i+1)%4]) for i in range(4)], False)
doc.recompute()
print('SUCCESS: geometry added')
""")
    assert res.get("success") and "SUCCESS" in res["data"]["output"], f"rect failed: {res}"

    r = extrude_sketch_bidirectional(mock_ctx, conn, no_screenshot, doc, f"{prefix}_plane_sketch", 30.0)
    assert r and isinstance(r[0], TextContent), f"extrude failed: {r}"
    return f"{prefix}_plane_solid"


def _create_box(conn, doc, name, L, W, H, x=0, y=0, z=0):
    res = conn.execute_code(f"""
import FreeCAD as App
doc = App.getDocument('{doc}')
box = doc.addObject('Part::Box', '{name}')
box.Length = {L}
box.Width = {W}
box.Height = {H}
box.Placement = App.Placement(App.Vector({x}, {y}, {z}), App.Rotation())
doc.recompute()
print('SUCCESS: box created')
""")
    assert res.get("success") and "SUCCESS" in res["data"]["output"], \
        f"Failed to create box {name}: {res}"


def _create_cylinder(conn, doc, name, R, H, x=0, y=0, z=0):
    res = conn.execute_code(f"""
import FreeCAD as App
doc = App.getDocument('{doc}')
cyl = doc.addObject('Part::Cylinder', '{name}')
cyl.Radius = {R}
cyl.Height = {H}
cyl.Placement = App.Placement(App.Vector({x}, {y}, {z}), App.Rotation())
doc.recompute()
print('SUCCESS: cylinder created')
""")
    assert res.get("success") and "SUCCESS" in res["data"]["output"], \
        f"Failed to create cylinder {name}: {res}"


def _volume(conn, doc, name):
    meas = conn.measure_object(doc, name)
    if not meas.get("success"):
        return None
    data = meas.get("data", {})
    return data.get("volume", data.get("Volume", None))


def test_add_fillet_on_partdesign_body(conn, doc, mock_ctx, no_screenshot):
    solid_name = _build_partdesign_solid(conn, doc, mock_ctx, no_screenshot, "fillet_pd")
    orig_vol = _volume(conn, doc, solid_name)

    result = add_fillet(mock_ctx, conn, no_screenshot, doc, solid_name, ["Edge1", "Edge2", "Edge3"], 3.0)
    assert ok(result), f"add_fillet failed: {result}"

    # Verify the result is a PartDesign fillet, not Part::Fillet
    objects = conn.get_objects(doc)
    type_map = {o["Name"]: o.get("TypeId", "") for o in objects}
    fillet_names = [n for n, t in type_map.items() if "Fillet" in n or "fillet" in n.lower()]
    assert any("PartDesign" in type_map.get(n, "") for n in fillet_names), \
        f"Expected PartDesign::Fillet, found: {[(n, type_map[n]) for n in fillet_names]}"

    # PartDesign fillet object is the active solid in the body — measure the body tip
    fillet_obj_names = [n for n, t in type_map.items() if t == "PartDesign::Fillet"]
    if fillet_obj_names:
        fillet_vol = _volume(conn, doc, fillet_obj_names[0])
        if fillet_vol is not None and orig_vol is not None:
            assert fillet_vol < orig_vol, \
                f"Filleted volume {fillet_vol} should be < original {orig_vol}"


def test_add_chamfer_on_partdesign_body(conn, doc, mock_ctx, no_screenshot):
    solid_name = _build_partdesign_solid(conn, doc, mock_ctx, no_screenshot, "chamfer_pd")
    orig_vol = _volume(conn, doc, solid_name)

    result = add_chamfer(mock_ctx, conn, no_screenshot, doc, solid_name, ["Edge1", "Edge2"], 2.0)
    assert ok(result), f"add_chamfer failed: {result}"

    objects = conn.get_objects(doc)
    type_map = {o["Name"]: o.get("TypeId", "") for o in objects}
    chamfer_obj_names = [n for n, t in type_map.items() if t == "PartDesign::Chamfer"]
    assert chamfer_obj_names, \
        f"Expected PartDesign::Chamfer in objects, found types: {set(type_map.values())}"

    if chamfer_obj_names:
        chamfer_vol = _volume(conn, doc, chamfer_obj_names[0])
        if chamfer_vol is not None and orig_vol is not None:
            assert chamfer_vol < orig_vol, \
                f"Chamfered volume {chamfer_vol} should be < original {orig_vol}"


def test_mirror_object(conn, doc, mock_ctx, no_screenshot):
    _create_box(conn, doc, "MirrorSrc", 30, 20, 20, 10, 0, 0)

    mirror_plane = {
        "base": {"x": 0, "y": 0, "z": 0},
        "normal": {"x": 1, "y": 0, "z": 0},
    }
    result = mirror_object(mock_ctx, conn, no_screenshot, doc, "MirrorSrc", mirror_plane, "MirrorResult", merge=False)
    assert ok(result), f"mirror_object failed: {result}"

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "MirrorResult" in names, f"MirrorResult not in {names}"


def test_circular_pattern(conn, doc, mock_ctx, no_screenshot):
    _create_cylinder(conn, doc, "PatCyl", 5, 20, 30, 0, 0)

    axis = {
        "point": {"x": 0, "y": 0, "z": 0},
        "direction": {"x": 0, "y": 0, "z": 1},
    }
    result = circular_pattern(mock_ctx, conn, no_screenshot, doc, "PatCyl", axis, count=4, angle=360.0, result_name="CircPattern")
    assert ok(result), f"circular_pattern failed: {result}"

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "CircPattern" in names, f"CircPattern not in {names}"


def test_linear_pattern(conn, doc, mock_ctx, no_screenshot):
    _create_box(conn, doc, "LinBox", 10, 10, 10, 0, 0, 0)

    direction = {"x": 1, "y": 0, "z": 0}
    result = linear_pattern(mock_ctx, conn, no_screenshot, doc, "LinBox", direction, spacing=20.0, count=3, result_name="LinPattern")
    assert ok(result), f"linear_pattern failed: {result}"

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "LinPattern" in names, f"LinPattern not in {names}"


def test_shell_object(conn, doc, mock_ctx, no_screenshot):
    from freecad_mcp.modeling_tools_advanced import shell_object

    _create_box(conn, doc, "ShellBox", 60, 60, 60)

    topo = conn.get_shape_topology(doc, "ShellBox")
    assert topo.get("success"), f"get_shape_topology failed: {topo.get('error')}"

    orig_vol = _volume(conn, doc, "ShellBox")

    result = shell_object(mock_ctx, conn, no_screenshot, doc, "ShellBox", thickness=4.0, faces_to_remove=["Face6"], result_name="ShellResult")
    assert ok(result), f"shell_object failed: {result}"

    shell_vol = _volume(conn, doc, "ShellResult")
    if shell_vol is not None and orig_vol is not None:
        assert shell_vol < orig_vol, f"Shell volume {shell_vol} should be < box {orig_vol}"
        assert shell_vol > 0
