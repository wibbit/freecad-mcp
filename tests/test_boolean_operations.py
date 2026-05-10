import pytest
from mcp.types import TextContent

from freecad_mcp.sketch_tools.boolean_operations import (
    boolean_union,
    boolean_cut,
    boolean_intersection,
)


def ok(result):
    return (
        result
        and isinstance(result[0], TextContent)
        and (
            "successfully" in result[0].text.lower()
            or "SUCCESS" in result[0].text
            or "union" in result[0].text.lower()
            or "cut" in result[0].text.lower()
            or "intersection" in result[0].text.lower()
            or "created" in result[0].text.lower()
        )
    )


def _create_box(conn, doc, name, L, W, H, x=0, y=0, z=0):
    res = conn.execute_code(f"""
import FreeCAD as App, Part
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


def _volume(conn, doc, name):
    meas = conn.measure_object(doc, name)
    if not meas.get("success"):
        return None
    data = meas.get("data", {})
    return data.get("volume", data.get("Volume", None))


def test_boolean_union(conn, doc, mock_ctx, no_screenshot):
    _create_box(conn, doc, "BoxA", 50, 50, 50, 0, 0, 0)
    _create_box(conn, doc, "BoxB", 50, 50, 50, 25, 0, 0)  # overlapping

    vol_a = _volume(conn, doc, "BoxA")
    vol_b = _volume(conn, doc, "BoxB")

    result = boolean_union(mock_ctx, conn, no_screenshot, doc, "BoxA", ["BoxB"], "UnionResult")
    assert ok(result), f"boolean_union failed: {result}"

    union_vol = _volume(conn, doc, "UnionResult")
    if union_vol is not None and vol_a is not None and vol_b is not None:
        assert union_vol < vol_a + vol_b, \
            f"Union volume {union_vol} should be < {vol_a + vol_b}"
        assert union_vol > 0


def test_boolean_cut(conn, doc, mock_ctx, no_screenshot):
    _create_box(conn, doc, "BigBox", 100, 100, 100, 0, 0, 0)
    _create_box(conn, doc, "SmallBox", 30, 30, 30, 10, 10, 10)  # inside big box

    vol_big = _volume(conn, doc, "BigBox")

    # boolean_cut takes a single tool name string, not a list
    result = boolean_cut(mock_ctx, conn, no_screenshot, doc, "BigBox", "SmallBox", "CutResult")
    assert ok(result), f"boolean_cut failed: {result}"

    cut_vol = _volume(conn, doc, "CutResult")
    if cut_vol is not None and vol_big is not None:
        assert cut_vol < vol_big, f"Cut volume {cut_vol} should be < {vol_big}"
        assert cut_vol > 0


def test_boolean_intersection(conn, doc, mock_ctx, no_screenshot):
    _create_box(conn, doc, "BoxX", 60, 60, 60, 0, 0, 0)
    _create_box(conn, doc, "BoxY", 60, 60, 60, 30, 30, 30)  # overlapping corner

    vol_x = _volume(conn, doc, "BoxX")
    vol_y = _volume(conn, doc, "BoxY")

    # boolean_intersection takes two object names, not base + list
    result = boolean_intersection(mock_ctx, conn, no_screenshot, doc, "BoxX", "BoxY", "IntersectResult")
    assert ok(result), f"boolean_intersection failed: {result}"

    inter_vol = _volume(conn, doc, "IntersectResult")
    if inter_vol is not None and vol_x is not None:
        assert inter_vol > 0, "Intersection volume must be > 0"
        assert inter_vol < vol_x, f"Intersection {inter_vol} should be < {vol_x}"
        assert inter_vol < vol_y, f"Intersection {inter_vol} should be < {vol_y}"
