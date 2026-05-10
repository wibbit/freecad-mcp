import pytest
from mcp.types import TextContent

from freecad_mcp.sketch_tools.plane_manager import create_datum_plane, add_datum_plane_to_body
from freecad_mcp.sketch_tools.sketch_manager import create_sketch_on_plane, create_sketch_in_body
from freecad_mcp.sketch_tools.extrude_manager import extrude_sketch_bidirectional
from freecad_mcp.sketch_tools.pocket_manager import pocket_sketch
from freecad_mcp.sketch_tools.groove_manager import groove


def ok(result):
    return (
        result
        and isinstance(result[0], TextContent)
        and (
            "successfully" in result[0].text.lower()
            or "SUCCESS" in result[0].text
        )
    )


def _add_rect(conn, doc, sketch_name, x0=0, y0=0, x1=80, y1=60):
    res = conn.execute_code(f"""
import FreeCAD as App, Part, Sketcher
doc = App.getDocument('{doc}')
sketch = doc.getObject('{sketch_name}')
v = [App.Vector(x, y, 0) for x, y in [({x0},{y0}),({x1},{y0}),({x1},{y1}),({x0},{y1})]]
sketch.addGeometry([Part.LineSegment(v[i], v[(i+1)%4]) for i in range(4)], False)
doc.recompute()
print('SUCCESS: geometry added')
""")
    assert res.get("success") and "SUCCESS" in res["data"]["output"], \
        f"Failed to add rect geometry: {res}"


def test_create_datum_plane_xy(conn, doc, mock_ctx, no_screenshot):
    result = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "base_plane", "xy", 0.0)
    assert ok(result), f"create_datum_plane xy failed: {result}"


def test_create_datum_plane_xz(conn, doc, mock_ctx, no_screenshot):
    result = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "top_plane", "xz", 10.0)
    assert ok(result), f"create_datum_plane xz failed: {result}"


def test_full_sketch_extrude_workflow(conn, doc, mock_ctx, no_screenshot):
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "base_plane", "xy", 0.0)
    assert ok(r), f"plane: {r}"

    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, "base_plane")
    assert ok(r), f"sketch: {r}"

    _add_rect(conn, doc, "base_plane_sketch")

    r = extrude_sketch_bidirectional(mock_ctx, conn, no_screenshot, doc, "base_plane_sketch", 20.0)
    assert ok(r), f"extrude: {r}"

    meas = conn.measure_object(doc, "base_plane_solid")
    assert meas.get("success"), meas.get("error")
    data = meas.get("data", {})
    volume = data.get("volume", data.get("Volume", 0.0))
    expected = 80.0 * 60.0 * 20.0
    assert abs(volume - expected) < 10.0, f"Volume {volume} != {expected}"


def test_extrude_taper_angle(conn, doc, mock_ctx, no_screenshot):
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "taper_plane", "xy", 0.0)
    assert ok(r)

    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, "taper_plane")
    assert ok(r)

    _add_rect(conn, doc, "taper_plane_sketch")

    r = extrude_sketch_bidirectional(
        mock_ctx, conn, no_screenshot, doc, "taper_plane_sketch",
        length_forward=20.0, taper_angle=-1.5
    )
    assert ok(r), f"taper extrude failed: {r}"


def test_extrude_reversed(conn, doc, mock_ctx, no_screenshot):
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "rev_plane", "xy", 0.0)
    assert ok(r)

    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, "rev_plane")
    assert ok(r)

    _add_rect(conn, doc, "rev_plane_sketch")

    r = extrude_sketch_bidirectional(
        mock_ctx, conn, no_screenshot, doc, "rev_plane_sketch",
        length_forward=20.0, reversed=True
    )
    assert ok(r), f"reversed extrude failed: {r}"


def test_pocket_sketch(conn, doc, mock_ctx, no_screenshot):
    # Build base solid
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "base_plane", "xy", 0.0)
    assert ok(r)
    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, "base_plane")
    assert ok(r)
    _add_rect(conn, doc, "base_plane_sketch", 0, 0, 100, 100)
    r = extrude_sketch_bidirectional(mock_ctx, conn, no_screenshot, doc, "base_plane_sketch", 50.0)
    assert ok(r)

    base_meas = conn.measure_object(doc, "base_plane_solid")
    base_vol = base_meas["data"].get("volume", base_meas["data"].get("Volume", 0))

    # Add a second datum plane for pocket sketch (coincident with XY) inside the same body
    r = add_datum_plane_to_body(mock_ctx, conn, no_screenshot, doc, "base_plane", "pocket_plane", "xy", 0.0)
    assert ok(r), f"add_datum_plane_to_body failed: {r}"

    # create_sketch_in_body names sketch as '{plane_name}_sketch' automatically
    r = create_sketch_in_body(mock_ctx, conn, no_screenshot, doc, "base_plane", "pocket_plane")
    assert ok(r), f"create_sketch_in_body failed: {r}"

    _add_rect(conn, doc, "pocket_plane_sketch", 20, 20, 60, 60)

    r = pocket_sketch(mock_ctx, conn, no_screenshot, doc, "pocket_plane_sketch", depth=20.0)
    assert ok(r), f"pocket failed: {r}"

    after = conn.measure_object(doc, "pocket_plane_sketch_pocket")
    if after.get("success"):
        pocket_vol = after["data"].get("volume", after["data"].get("Volume", 0))
        assert pocket_vol < base_vol, f"Pocket volume {pocket_vol} not less than base {base_vol}"


def test_add_datum_plane_to_body(conn, doc, mock_ctx, no_screenshot):
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "main_plane", "xy", 0.0)
    assert ok(r)

    r = add_datum_plane_to_body(mock_ctx, conn, no_screenshot, doc, "main_plane", "second_plane", "xz", 5.0)
    assert ok(r), f"add_datum_plane_to_body failed: {r}"


def test_create_sketch_in_body(conn, doc, mock_ctx, no_screenshot):
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "host_plane", "xy", 0.0)
    assert ok(r)

    r = add_datum_plane_to_body(mock_ctx, conn, no_screenshot, doc, "host_plane", "extra_plane", "xy", 0.0)
    assert ok(r)

    # sketch is named '{plane_name}_sketch' = 'extra_plane_sketch'
    r = create_sketch_in_body(mock_ctx, conn, no_screenshot, doc, "host_plane", "extra_plane")
    assert ok(r), f"create_sketch_in_body failed: {r}"

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "extra_plane_sketch" in names, f"extra_plane_sketch not in {names}"


def test_groove(conn, doc, mock_ctx, no_screenshot):
    # Build a base solid (disc-like: small square extruded)
    r = create_datum_plane(mock_ctx, conn, no_screenshot, doc, "groove_plane", "xy", 0.0)
    assert ok(r)
    r = create_sketch_on_plane(mock_ctx, conn, no_screenshot, doc, "groove_plane")
    assert ok(r)
    # Rectangle offset from axis so groove cuts into it
    _add_rect(conn, doc, "groove_plane_sketch", 10, 0, 60, 40)
    r = extrude_sketch_bidirectional(mock_ctx, conn, no_screenshot, doc, "groove_plane_sketch", 20.0)
    assert ok(r)

    base_meas = conn.measure_object(doc, "groove_plane_solid")
    base_vol = base_meas["data"].get("volume", base_meas["data"].get("Volume", 0))

    # Add a groove sketch inside the same body
    r = add_datum_plane_to_body(mock_ctx, conn, no_screenshot, doc, "groove_plane", "groove_cut_plane", "xy", 0.0)
    assert ok(r)
    # sketch named 'groove_cut_plane_sketch'
    r = create_sketch_in_body(mock_ctx, conn, no_screenshot, doc, "groove_plane", "groove_cut_plane")
    assert ok(r)
    # Small rectangle for the groove profile (revolved around V_Axis)
    _add_rect(conn, doc, "groove_cut_plane_sketch", 15, 0, 30, 10)

    r = groove(mock_ctx, conn, no_screenshot, doc, "groove_cut_plane_sketch", axis="V_Axis", angle=360.0)
    assert ok(r), f"groove failed: {r}"

    after = conn.measure_object(doc, "groove_cut_plane_sketch_groove")
    if after.get("success"):
        after_vol = after["data"].get("volume", after["data"].get("Volume", 0))
        assert after_vol < base_vol, f"Groove volume {after_vol} not less than base {base_vol}"
