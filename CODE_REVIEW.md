# FreeCAD MCP Code Review

Review date: 2026-05-09  
Scope: All changes made during the MCP protocol review, logging implementation, and Tier 1–3 new tools.

---

## Critical — will fail at runtime

### C1 — `shell_object`: wrong type for `Part::Thickness.Faces`
**File:** `src/freecad_mcp/modeling_tools_advanced.py` ~line 207  
**Issue:** `shell.Faces = [(obj, face_indices)]` passes a list of integers as the second element. FreeCAD's `Part::Thickness.Faces` expects a list of `(DocumentObject, subshape_name_string)` tuples, e.g. `[(obj, "Face1"), (obj, "Face3")]`.  
**Fix:**
```python
face_names = [f"Face{i+1}" for i in face_indices]
shell.Faces = [(obj, name) for name in face_names]
```

### C2 — `shell_object`: broken string-vs-None comparison and wrong `len()` usage
**File:** `src/freecad_mcp/modeling_tools_advanced.py` ~lines 195 and 222  
**Issue:** `faces_to_remove_list` is a Python string inside the generated code (e.g. `"Face1", "Face3"`). The check `faces_to_remove_list != 'None'` happens to work, but `len(faces_to_remove_list)` at line 222 returns the character count of the string, not the face count.  
**Fix:** Build `faces_to_remove_list` as a proper Python list inside the generated code rather than embedding a raw string. Then `len()` and truthiness work correctly.

### C3 — `_create_techdraw_page_gui`: blank template branch creates invalid SVGTemplate
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py` ~lines 1105–1107  
**Issue:** The `else` branch adds a `TechDraw::DrawSVGTemplate` object without setting `template.Template` to a file path. `doc.recompute()` will fail or produce a broken page.  
**Fix:** When no template path is given, skip the template object entirely and leave `page.Template` unset (TechDraw accepts this as a blank page), or remove `doc.recompute()` from the else branch.

---

## High — silent failures or wrong behaviour

### H1 — `_undo_gui`: silently succeeds when undo is not enabled
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py`  
**Issue:** `doc.undo()` is a no-op when `doc.UndoMode == 0`. The method reports success even though nothing was undone.  
**Fix:**
```python
if not doc.UndoMode:
    return {"success": False, "data": None,
            "error": "Undo not enabled on this document. Open documents via FreeCAD GUI to enable undo tracking."}
```

### H2 — `_create_techdraw_page_gui`: interactive `setEdit()` in RPC context
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py` ~line 1109  
**Issue:** `FreeCADGui.ActiveDocument.setEdit(page)` opens an interactive edit dialog, which is inappropriate for an automated RPC call. It may steal focus, block, or fail silently.  
**Fix:** Remove the `setEdit` call entirely.

### H3 — `obj.Visibility = False` in generated code (6 locations)
**File:** `src/freecad_mcp/modeling_tools_advanced.py` ~lines 68, 136, 219, 293–294, 400, 486  
**Issue:** `obj.Visibility` does not exist on `DocumentObject`. Visibility is controlled via `obj.ViewObject.Visibility`. Setting the wrong attribute either silently creates a spurious property or raises `AttributeError`.  
**Fix:** Replace all occurrences with `obj.ViewObject.Visibility = False`.

### H4 — `add_chamfer`: wrong tuple arity for `Part::Chamfer.Edges`
**File:** `src/freecad_mcp/modeling_tools_advanced.py` ~line 130  
**Issue:** Generated code appends `(edge_idx, {distance})` — a 2-tuple. `Part::Chamfer.Edges` expects 3-tuples: `(edge_index, dist1, dist2)`.  
**Fix:**
```python
edges_to_chamfer.append((edge_idx, {distance}, {distance}))
```

---

## API Concerns

### A1 — Face centroid computed from bounding box midpoint
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py` — `_get_shape_topology_gui`  
**Issue:** Centroid is approximated as bounding-box centre. Incorrect for non-rectangular or curved faces.  
**Fix:** Use `face.CenterOfMass` (a `Vector` — correct FreeCAD API):
```python
com = face.CenterOfMass
centroid = {"x": round(com.x, 4), "y": round(com.y, 4), "z": round(com.z, 4)}
```

### A2 — `create_reference_plane` (offset mode) uses `PartDesign::Plane` outside a Body
**File:** `src/freecad_mcp/modeling_tools_advanced.py`  
**Issue:** `PartDesign::Plane` must live inside a `PartDesign::Body`. Creating it at document level fails with "feature not allowed outside a body".  
**Fix:** Use `Part::Feature` with an appropriate `Placement` for the offset datum plane, matching how the `3points` and `point_normal` modes work.

### A3 — `import_airfoil_profile`: wrong Sketcher API for B-splines
**File:** `src/freecad_mcp/modeling_tools_advanced.py`  
**Issue:** `sketch.addGeometry(upper_spline.toShape().Curve)` passes a `Part::Curve` adapter not supported by Sketcher's geometry representation.  
**Fix:** `sketch.addGeometry(upper_spline)` — pass the `BSplineCurve` directly.

### A4 — `copy_object`: non-recursive copy breaks references
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py` — `_copy_object_gui`  
**Issue:** `doc.copyObject(obj, False)` — the `False` means "do not recursively copy dependencies". For objects that reference others (e.g. a fillet referencing a box), the copy holds broken references.  
**Fix:** Default to `True` (recursive copy), or document the limitation clearly in the MCP tool docstring.

### A5 — `export_object`: format fallback when extension doesn't match
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py` — `_export_object_gui`  
**Issue:** `Part.export` selects the exporter from the file extension. If the user provides a path with the wrong extension for the requested format, the export silently produces the wrong format.  
**Fix:** Validate or normalise the file extension against the `export_format` parameter before calling export.

---

## Code Quality

### Q1 — No `try/except` around `get_freecad_connection()` in newer tools
**File:** `src/freecad_mcp/server.py` — all tools added in Tiers 1–3  
**Issue:** If FreeCAD is not running, `get_freecad_connection()` raises an unhandled exception that propagates through `_log_tool` to FastMCP as an internal error. Older tools wrap this in `try/except`.  
**Fix:** Wrap the connection + RPC call in a consistent `try/except ConnectionError` (or equivalent) block in each new tool, returning a user-facing error message.

### Q2 — `obj_properties: dict[str, Any] = None` incorrect annotation
**File:** `src/freecad_mcp/server.py` ~line 247  
**Fix:** `dict[str, Any] | None = None`

### Q3 — `result_name: str = None` in 6 functions
**File:** `src/freecad_mcp/modeling_tools_advanced.py`  
**Fix:** `str | None = None` on all six occurrences.

### Q4 — Dead import: `boolean_common`
**File:** `src/freecad_mcp/server.py` ~line 44  
**Issue:** Imported but never exposed as an MCP tool. Either wire it up or remove the import.

### Q5 — Stale "future feature" references in sketch strategy prompt
**File:** `src/freecad_mcp/prompts/sketch_strategy.py` ~lines 177 and 207  
**Issue:** References to boolean operations and mirror as "future features" — these tools exist now.  
**Fix:** Remove or update the references.

### Q6 — `ASSET_CREATION_STRATEGY` missing new tools
**File:** `src/freecad_mcp/prompt_text.py`  
**Issue:** Does not mention `save_document`, `load_document`, `measure_object`, `get_shape_topology`, `export_object`, `copy_object`, `set_object_visibility`, `undo`, `spreadsheet_read`, `spreadsheet_write`.  
**Fix:** Add a section for inspection and file-management tools.

---

## Minor / Style

### M1 — Redundant `import re` inside `_spreadsheet_read_gui`
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py`  
`re` is already imported at module top. Remove the nested import.

### M2 — RPC faults not logged in `_dispatch`
**File:** `addon/FreeCADMCP/rpc_server/rpc_server.py`  
`super()._dispatch()` can raise `xmlrpc.server.Fault` for unknown methods; these are not caught or logged. Wrap the call in `try/except` to also log faults.

### M3 — French-language comments in `modeling_tools_advanced.py`
**File:** `src/freecad_mcp/modeling_tools_advanced.py` ~lines 1–5  
Leftover project-specific artefacts. Remove.

### M4 — Dead `True`/`False` expressions in screenshot check
**File:** `src/freecad_mcp/freecad_client.py` — `_SCREENSHOT_SUPPORT_CHECK` ~lines 23 and 26  
Bare `True`/`False` as statements are discarded by `exec()`. Remove them.

---

## What looks good

- **Queue discipline**: Every GUI helper that touches FreeCAD GUI state correctly dispatches via `rpc_request_queue`/`rpc_response_queue`. Pure data reads bypass the queue appropriately.
- **`_setup_logging`**: Correctly removes and closes existing handlers before reconfiguring, preventing duplicate log entries on re-init.
- **`FilteredXMLRPCServer._dispatch` logging**: Captures method name, params (truncated), elapsed time, and success/error discrimination correctly.
- **`_log_tool` decorator**: Wraps all 68 `@mcp.tool()` functions (counts match); logs tool entry, duration, and screenshot presence.
- **`parse_execute_result`**: Correctly reads `res["data"]["output"]`, handles `data=None`, and all 13 callers use it correctly.
- **`_get_shape_topology_gui`**: Correct Shape API (`obj.Shape.Faces/.Edges/.Vertexes`), per-element `try/except`, `isNull()` guard.
- **Error envelopes**: All new RPC helpers return consistent `{"success": bool, "data": …, "error": …}` on both success and failure paths.
- **`Literal` types**: Used correctly for all fixed-enumeration parameters (`export_format`, `view_name`, `alignment`, `rotation_axis`, etc.).
- **`_save_document_gui`**: Correctly handles save-as vs in-place, and the never-saved case.
- **`_load_document_gui`**: Correctly checks `FreeCAD.open()` return value for `None`.
