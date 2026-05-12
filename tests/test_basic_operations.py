import pytest
from freecad_mcp.freecad_client import FreeCADConnection


def test_ping(conn):
    assert conn.ping() is True


def test_create_and_list_documents(conn, doc):
    docs = conn.list_documents()
    assert doc in docs


def test_create_object_box(conn, doc):
    result = conn.create_object(doc, {
        "Name": "MyBox",
        "Type": "Part::Box",
        "Properties": {"Length": 50.0, "Width": 30.0, "Height": 20.0},
    })
    assert result.get("success"), result.get("error")


def test_create_object_cylinder(conn, doc):
    result = conn.create_object(doc, {
        "Name": "MyCylinder",
        "Type": "Part::Cylinder",
        "Properties": {"Radius": 15.0, "Height": 40.0},
    })
    assert result.get("success"), result.get("error")


def test_get_objects(conn, doc):
    conn.create_object(doc, {
        "Name": "BoxA",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    conn.create_object(doc, {
        "Name": "CylA",
        "Type": "Part::Cylinder",
        "Properties": {"Radius": 5.0, "Height": 10.0},
    })
    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "BoxA" in names
    assert "CylA" in names


def test_get_object(conn, doc):
    conn.create_object(doc, {
        "Name": "InfoBox",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    result = conn.get_object(doc, "InfoBox")
    assert result.get("success"), result.get("error")
    data = result.get("data", {})
    assert "Name" in data
    assert "TypeId" in data
    assert "State" in data
    assert "HasError" in data


def test_edit_object(conn, doc):
    conn.create_object(doc, {
        "Name": "EditBox",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    edit_result = conn.edit_object(doc, "EditBox", {"Properties": {"Length": 99.0}})
    assert edit_result.get("success"), edit_result.get("error")

    info = conn.get_object(doc, "EditBox")
    assert info.get("success")
    props = info.get("data", {}).get("Properties", {})
    assert abs(props.get("Length", 0) - 99.0) < 0.01


def test_delete_object(conn, doc):
    conn.create_object(doc, {
        "Name": "DelBox",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    del_result = conn.delete_object(doc, "DelBox")
    assert del_result.get("success"), del_result.get("error")

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "DelBox" not in names


def test_execute_code(conn, doc):
    res = conn.execute_code(f"""
import FreeCAD as App
doc = App.getDocument('{doc}')
print('SUCCESS: doc has ' + str(len(doc.Objects)) + ' objects')
""")
    assert res.get("success"), res.get("error")
    assert "SUCCESS" in res["data"]["output"]


def test_copy_object(conn, doc):
    conn.create_object(doc, {
        "Name": "OrigBox",
        "Type": "Part::Box",
        "Properties": {"Length": 20.0, "Width": 20.0, "Height": 20.0},
    })
    copy_result = conn.copy_object(doc, "OrigBox", "CopiedBox")
    assert copy_result.get("success"), copy_result.get("error")

    objects = conn.get_objects(doc)
    names = [o["Name"] for o in objects]
    assert "CopiedBox" in names


def test_measure_object(conn, doc):
    L, W, H = 50.0, 30.0, 20.0
    conn.create_object(doc, {
        "Name": "MeasBox",
        "Type": "Part::Box",
        "Properties": {"Length": L, "Width": W, "Height": H},
    })
    result = conn.measure_object(doc, "MeasBox")
    assert result.get("success"), result.get("error")
    data = result.get("data", {})
    volume = data.get("volume", data.get("Volume", 0.0))
    expected = L * W * H
    assert abs(volume - expected) < 1.0, f"Volume {volume} != {expected}"


def test_get_shape_topology(conn, doc):
    conn.create_object(doc, {
        "Name": "TopoBox",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    result = conn.get_shape_topology(doc, "TopoBox")
    assert result.get("success"), result.get("error")
    data = result.get("data", {})
    # A box has 12 edges and 6 faces
    assert data.get("edges", 0) == 12
    assert data.get("faces", 0) == 6


def test_set_object_visibility(conn, doc):
    conn.create_object(doc, {
        "Name": "VisBox",
        "Type": "Part::Box",
        "Properties": {"Length": 10.0, "Width": 10.0, "Height": 10.0},
    })
    result = conn.set_object_visibility(doc, "VisBox", False)
    assert result.get("success"), result.get("error")

    info = conn.get_object(doc, "VisBox")
    assert info.get("success")
    view = info.get("data", {}).get("ViewObject", {})
    assert view.get("Visibility") is False


def test_get_freecad_errors(conn):
    # Trigger a known error via execute_code, then confirm it appears in Report View.
    conn.execute_code("raise RuntimeError('mcp_test_sentinel_error_xyz')")

    result = conn.get_freecad_errors(max_lines=200)
    assert result.get("success"), result.get("error")
    output = result.get("data", {}).get("report_view_errors", "")
    assert "mcp_test_sentinel_error_xyz" in output, (
        f"Expected sentinel error in Report View output, got: {output[:300]}"
    )
