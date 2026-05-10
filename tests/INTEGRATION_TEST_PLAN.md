# FreeCAD MCP Integration Test Plan

Comprehensive integration test covering all 68 MCP tools against the FreeCAD XML-RPC backend.
Last updated: 2026-05-10 | Tested against: MCP server v0.x + FreeCAD (Flatpak)

---

## Test Environment

| Variable | Value |
|----------|-------|
| FreeCAD | Flatpak install (no AppImage) |
| MCP server | `freecad-mcp` addon via XML-RPC :9875 |
| RPC mechanism | Queue-based writes via `QtCore.QTimer.singleShot`, sync reads |
| Known issue | `FreeCAD.Console.PrintMessage` output not captured by `execute_code` |
| Known issue | Some object types not directly creatable via `addObject()` |

---

## Reporting Results

**Write results to a separate file — do not edit the test plan files.**

Results go in `tests/test_results_YYYY-MM-DD_HHMMSS.md`. Test plan files (`INTEGRATION_TEST_PLAN.md` and `test_plans/*.md`) are updated only when the test plan itself changes — new scenarios added, prerequisites updated, or coverage gaps identified.

Result files are snapshots of a specific test run and accumulate over time. The status column below reflects the latest known run.

---

## Sub-documents

Each area has its own focused test plan. Start here to find the right document.

| Area | File | Tools covered | Status |
|------|------|---------------|--------|
| Document lifecycle, CRUD, execute_code, inspection | [test_plans/core.md](test_plans/core.md) | `create_document`, `list_documents`, `save_document`, `load_document`, `create_object`, `get_object`, `get_objects`, `edit_object`, `delete_object`, `copy_object`, `undo`, `execute_code`, `measure_object`, `get_shape_topology`, `get_freecad_status`, `get_view` | Tested 2026-05-10 |
| Sketch workflow | [test_plans/sketch_workflow.md](test_plans/sketch_workflow.md) | `create_datum_plane`, `add_datum_plane_to_body`, `create_sketch_on_plane`, `create_sketch_in_body`, `add_contour_to_sketch`, `extrude_sketch_bidirectional`, `pocket_sketch`, `attach_solid_to_plane` | Tested 2026-05-10 (`pocket_sketch`, `add_datum_plane_to_body`, `create_sketch_in_body` untested — added 2026-05-10) |
| Boolean ops, transforms, advanced modeling, import/export | [test_plans/modeling.md](test_plans/modeling.md) | `boolean_union`, `boolean_cut`, `boolean_intersection`, `transform_object`, `align_object`, `attach_to_face`, `set_object_visibility`, `add_fillet`, `add_chamfer`, `shell_object`, `mirror_object`, `circular_pattern`, `linear_pattern`, `create_loft`, `create_revolve`, `create_sweep`, `create_spline_3d`, `create_reference_plane`, `create_reference_axis`, `import_airfoil_profile`, `import_dxf`, `export_object`, `insert_part_from_library`, `get_parts_list` | Tested 2026-05-10 |
| Assembly3 + Assembly4 | [test_plans/assembly.md](test_plans/assembly.md) | `create_assembly3`, `add_part_to_assembly3`, `add_assembly3_constraint`, `solve_assembly3`, `list_assembly3_constraints`, `delete_assembly3_constraint`, `modify_assembly3_constraint`, `create_assembly4`, `create_lcs_assembly4`, `insert_part_assembly4`, `attach_lcs_to_geometry`, `list_assembly4_lcs`, `delete_lcs_assembly4`, `modify_lcs_assembly4`, `list_assembly_parts`, `export_assembly`, `generate_bom`, `get_assembly_properties` | Tested 2026-05-10 |
| TechDraw, FEM, Spreadsheet | [test_plans/output_tools.md](test_plans/output_tools.md) | `create_techdraw_page`, `add_view_to_techdraw_page`, `run_fem_analysis`, `spreadsheet_read`, `spreadsheet_write` | Tested 2026-05-10 |

---

## Known Bugs Summary

Open issues only. Fixed bugs are recorded in `CHANGELOG.md`.

| # | Tool | Symptom | Root Cause | Status |
|---|------|---------|------------|--------|
| 7 | `execute_code` output | `FreeCAD.Console.PrintMessage` not captured | Output goes to FreeCAD internal console, not stdout | By design — use `print()` instead |
| 9 | `Part::Tube` via `create_object` | "not a document object type" | `Part::Tube` does not exist; use `create_tube` tool instead | By design — use dedicated `create_tube` tool |
| 10 | `add_assembly3_constraint` | `No module named 'asm3'` | Assembly3 workbench not installed in this environment | Environment — install Assembly3 addon |

---

## Regression Test Scenarios

End-to-end workflows that exercise multiple tools in sequence. Run these to catch regressions.

### Scenario A: Part:: primitive → edit → measure → export
1. `create_document("RegA")`
2. `create_object("RegA", "Part::Box", "Box", {Length:50, Width:30, Height:20})`
3. `edit_object("RegA", "Box", {Height:25})`
4. `measure_object("RegA", "Box")` → verify volume = 50×30×25 = 37500
5. `export_object("RegA", "Box", "/tmp/reg_a.step", "step")`
6. Verify file exists

### Scenario B: Sketch → extrude → fillet → save/load
1. `create_document("RegB")`
2. `execute_code` to create body + sketch + pad (80×40×25) — note the actual pad object name from this step
3. `get_objects("RegB")` — confirm the pad/solid object name (use this name, NOT "Body", in next step)
4. `add_fillet("RegB", "<actual_pad_name>", ["Edge1","Edge2"], 5, "Filleted")`
5. `measure_object("RegB", "Filleted")` → volume < 80000 (fillet removes material)
6. `save_document("RegB", "/tmp/reg_b.FCStd")`
7. `load_document("/tmp/reg_b.FCStd")` → verify objects exist

### Scenario C: Multiple primitives → boolean union → mirror → export
1. Create 3 overlapping cylinders
2. `boolean_union(...)` → fused solid
3. `mirror_object(...)` → mirrored copy
4. `boolean_union(...)` → symmetric solid
5. Export as STL

### Scenario D: Assembly workflow (if Assembly3 available)
1. Create 2 independent `Part::Box` parts
2. `create_assembly3` container
3. `add_part_to_assembly3` × 2
4. `add_assembly3_constraint` — PlaneCoincident
5. `solve_assembly3`
6. `export_assembly` as STEP

### Scenario E: Full sketch workflow with non-XY datum plane
*Validates: `plane_manager.py` alignment fix, `sketch_manager.py` attachment fix, end-to-end sketch→solid*

1. `create_document("RegE")`
2. `create_datum_plane("RegE", "xz_plane", alignment="xz", offset=50)`
3. `create_sketch_on_plane("RegE", "xz_plane")` — creates `xz_plane_sketch`
4. `add_contour_to_sketch` — rectangular profile 80×40 in the XZ plane
5. `extrude_sketch_bidirectional("RegE", "xz_plane_sketch", length_forward=25)`
6. `measure_object` — verify solid exists and dimensions are correct
7. `get_view("Isometric")` — confirm orientation is correct (not XY)

**Prerequisite**: `add_contour_to_sketch` constraints bug (bug #2) must be fixed first.

### Scenario F: TechDraw page with projection views
1. `create_document("RegF")`
2. `create_object("RegF", "Part::Box", "DrawBox", {Length:80, Width:60, Height:40})`
3. `create_techdraw_page("RegF", "Sheet1")`
4. `add_view_to_techdraw_page("RegF", "Sheet1", "DrawBox", "Front", x=100, y=100, scale=1.0)`
5. `add_view_to_techdraw_page("RegF", "Sheet1", "DrawBox", "Top", x=200, y=100, scale=1.0)`
6. `get_view("Front")` — screenshot should show TechDraw page with projections

### Scenario G: Spreadsheet-driven parametric design
1. `create_document("RegG")`
2. `execute_code` — create `Spreadsheet::Sheet` "Params"
3. `spreadsheet_write` — A1=100 (length), A2=50 (width), A3=30 (height)
4. `execute_code` — create Box with expressions `=Params.A1`, `=Params.A2`, `=Params.A3`
5. `measure_object` — verify volume = 100×50×30 = 150000
6. `spreadsheet_write` — A1=200 (double length)
7. `execute_code` — `doc.recompute()`
8. `measure_object` — verify volume = 300000 (doubled)

### Scenario H: Mirror with merge=True
*Validates: `mirror_object` `merge=True` fix (was generating `if true:` NameError)*

1. `create_document("RegH")`
2. `create_object("RegH", "Part::Cylinder", "Cyl", {Radius:20, Height:100})`
3. `transform_object` — move to (50, 0, 0)
4. `mirror_object("RegH", "Cyl", "YZ", "CylMirror", merge=True)`
5. `measure_object("RegH", "CylMirror")` — verify volume ≈ 2× single cylinder (≈ 2×π×20²×100 ≈ 251327 mm³)

---

## Writing New Tests

When adding tests, follow this pattern:

```python
import xmlrpc.client
import time

SERVER = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)

def test_something():
    doc_name = f"Test_{int(time.time())}"
    SERVER.create_document(doc_name)

    code = f'''
import FreeCAD as App
doc = App.getDocument("{doc_name}")
# ... test logic ...
if not result:
    raise Exception("FAIL: expected X but got Y")
'''
    result = SERVER.execute_code(code)
    assert result.get("success"), f"Test failed: {result.get('error')}"
    print(f"[PASS] Something works")
```

Key: Use `raise Exception("message")` for validation since it is the only reliably
captured output channel.

---

## Appendix: Existing Test Files

| File | Coverage | Approach |
|------|----------|----------|
| `test_basic_operations.py` | Create doc, objects, get, edit, exec, delete | XML-RPC directly |
| `test_boolean_operations.py` | Union, cut, intersection | XML-RPC + exec_code |
| `test_sketch_workflow.py` | Datum plane, sketch, contour, extrude | XML-RPC + exec_code |
| `test_advanced_simple.py` | Fillet, mirror, circular, NACA | XML-RPC + exec_code |
| `test_advanced_features.py` | Fillet, mirror, circular, linear, NACA, ref plane | XML-RPC + exec_code |
| `test_remaining_6_functions.py` | Chamfer, shell, linear, ref plane/axis, DXF | XML-RPC + exec_code |

All existing tests call the FreeCAD XML-RPC server directly (port 9875), NOT through the MCP
FastMCP tool layer. They test the backend capability, not the MCP interface.
