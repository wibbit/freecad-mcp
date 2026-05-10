import os
import pytest
from freecad_mcp.freecad_client import FreeCADConnection


def _create_box(conn, doc, name, L=50, W=30, H=20):
    result = conn.create_object(doc, {
        "Name": name,
        "Type": "Part::Box",
        "Properties": {"Length": float(L), "Width": float(W), "Height": float(H)},
    })
    assert result.get("success"), f"Failed to create {name}: {result.get('error')}"


def test_save_and_load_document(conn, doc):
    _create_box(conn, doc, "SaveBox")
    path = f"/tmp/freecad_test_{doc}.FCStd"

    save_result = conn.save_document(doc, path)
    assert save_result.get("success"), f"save_document failed: {save_result.get('error')}"
    assert os.path.exists(path), f"Saved file not found at {path}"

    conn.execute_code(f"import FreeCAD; FreeCAD.closeDocument('{doc}')")

    load_result = conn.load_document(path)
    assert load_result.get("success"), f"load_document failed: {load_result.get('error')}"

    loaded_doc = load_result.get("data", {}).get("document_name", doc)
    objects = conn.get_objects(loaded_doc)
    names = [o["Name"] for o in objects]
    assert "SaveBox" in names, f"SaveBox not found after reload, got: {names}"

    # Cleanup
    conn.execute_code(f"import FreeCAD; FreeCAD.closeDocument('{loaded_doc}')")
    try:
        os.unlink(path)
    except OSError:
        pass


def test_rename_object(conn, doc):
    _create_box(conn, doc, "OldName")

    res = conn.execute_code(f"""
import FreeCAD as App
doc = App.getDocument('{doc}')
obj = doc.getObject('OldName')
if obj:
    obj.Label = 'RenamedLabel'
    doc.recompute()
    print('SUCCESS: label updated to ' + obj.Label)
else:
    print('ERROR: OldName not found')
""")
    assert res.get("success") and "SUCCESS" in res["data"]["output"], \
        f"rename failed: {res}"

    info = conn.get_object(doc, "OldName")
    assert info.get("success"), info.get("error")
    data = info.get("data", {})
    assert data.get("Label") == "RenamedLabel", \
        f"Expected Label 'RenamedLabel', got {data.get('Label')}"


def test_export_object(conn, doc):
    _create_box(conn, doc, "ExportBox")
    path = "/tmp/test_export.step"

    result = conn.export_object(doc, "ExportBox", path, "STEP")
    assert result.get("success"), f"export_object failed: {result.get('error')}"
    assert os.path.exists(path), f"Exported file not found at {path}"
    assert os.path.getsize(path) > 0, "Exported file is empty"

    try:
        os.unlink(path)
    except OSError:
        pass


def test_undo(conn, doc):
    _create_box(conn, doc, "UndoBox")

    objects_before = conn.get_objects(doc)
    names_before = [o["Name"] for o in objects_before]
    assert "UndoBox" in names_before

    conn.delete_object(doc, "UndoBox")
    objects_after_delete = conn.get_objects(doc)
    names_after_delete = [o["Name"] for o in objects_after_delete]
    assert "UndoBox" not in names_after_delete

    undo_result = conn.undo(doc, 1)
    assert undo_result.get("success"), f"undo failed: {undo_result.get('error')}"

    objects_after_undo = conn.get_objects(doc)
    names_after_undo = [o["Name"] for o in objects_after_undo]
    assert "UndoBox" in names_after_undo, \
        f"UndoBox not restored after undo, got: {names_after_undo}"
