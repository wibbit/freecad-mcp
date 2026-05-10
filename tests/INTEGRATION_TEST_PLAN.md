# FreeCAD MCP Integration Test Plan

Comprehensive integration test covering all MCP tools against the FreeCAD XML-RPC backend.
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

## 1. Document Lifecycle

### 1.1 `create_document`
- **Signature**: `create_document(name: str)`
- **Test**: Create doc with unique name
- **Validation**: List documents, confirm exists by name
- **Known**: ✅ Working
- **Edge cases**: Doc with name conflict (should error or auto-rename)

### 1.2 `list_documents`
- **Signature**: `list_documents()`
- **Test**: After create + load, list should reflect open docs
- **Known**: ✅ Working

### 1.3 `save_document`
- **Signature**: `save_document(doc_name: str, path: str = "")`
- **Test**: Save to `/tmp/test.FCStd`, reload in new session
- **Known**: ✅ Working
- **Edge cases**: Save without path on unsaved doc (should error)

### 1.4 `load_document`
- **Signature**: `load_document(path: str)`
- **Test**: Load the saved file, inspect objects preserved
- **Known**: ✅ Working
- **Edge cases**: Missing file path (should error)

---

## 2. Object CRUD

### 2.1 `create_object`
- **Signature**: `create_object(doc_name, obj_type, obj_name, obj_properties)`
- **Test matrix** — create each type, verify properties applied correctly:

#### 2.1.1 Part:: primitives

| Type | Properties Tested | Status |
|------|-------------------|--------|
| `Part::Box` | Length, Width, Height | ✅ Working |
| `Part::Cylinder` | Radius, Height | ✅ Working |
| `Part::Sphere` | Radius | ✅ Working |
| `Part::Cone` | Radius1, Radius2, Height | ✅ Working |
| `Part::Torus` | Radius1, Radius2 | ✅ Working |
| `Part::Plane` | Length, Width | ⏳ Untested |
| `Part::Tube` | InnerRadius, OuterRadius, Height | ⏳ Untested |
| `Part::Prism` | Polygon, Circumradius, Height | ⏳ Untested |
| `Part::Helix` | Pitch, Height, Radius | ⏳ Untested |

#### 2.1.2 PartDesign:: features

| Type | Notes | Status |
|------|-------|--------|
| `PartDesign::Body` | Container | ✅ Working |
| `PartDesign::AdditiveBox` | Requires Body context | ✅ Working |
| `PartDesign::AdditiveCylinder` | Requires Body context | ✅ Working |
| `PartDesign::AdditiveSphere` | Requires Body context | ✅ Working |
| `PartDesign::AdditiveCone` | Requires Body context | ✅ Working |
| `PartDesign::AdditiveTorus` | Requires Body context | ✅ Working |
| `PartDesign::SubtractiveBox` | Requires Body context | ✅ Working |
| `PartDesign::SubtractiveCylinder` | Requires Body context | ✅ Working |
| `PartDesign::SubtractiveSphere` | Requires Body context | ⏳ Untested |
| `PartDesign::SubtractiveCone` | Requires Body context | ⏳ Untested |
| `PartDesign::SubtractiveTorus` | Requires Body context | ⏳ Untested |
| `PartDesign::Pocket` | Requires Body+Sketch | ⏳ Untested (use exec) |

#### 2.1.3 Draft:: types

| Type | Status | Notes |
|------|--------|-------|
| `Draft::Circle` | ❌ Blocked | `addObject` rejects this type |
| `Draft::Rectangle` | ❌ Blocked | Same issue |
| `Draft::Wire` | ❌ Blocked | Same issue |
| Workaround: `Draft.makeCircle()` via `execute_code` | ✅ Working |

#### 2.1.4 Other failing object types

| Type | Error |
|------|-------|
| `PartDesign::SketcherSketchObject` | Not a document object type |
| `PartDesign::Sketch` | Not a document object type |
| `Sketcher::SketchObject` | ⚠️ Works via `execute_code` only |

### 2.2 `get_object`
- **Signature**: `get_object(doc_name, obj_name)`
- **Test**: Retrieve each created object, check TypeId matches
- **Known**: ❌ **Broken** — `string indices must be integers, not 'str'`
- **Probable cause**: Response parsing in `responses.py` or RPC JSON encoding
- **Workaround**: Use `execute_code` to inspect objects

### 2.3 `get_objects`
- **Signature**: `get_objects(doc_name)`
- **Test**: List all objects in document
- **Known**: ❌ **Broken** — Same error as `get_object`
- **Count objects via**: `execute_code("len(doc.Objects)")`

### 2.4 `edit_object`
- **Signature**: `edit_object(doc_name, obj_name, obj_properties)`
- **Test**: Create a Box, edit Length from 100 to 200
- **Known**: ✅ Working
- **Also test**: ViewObject properties (ShapeColor, Transparency)
- **Edge cases**: Null values, read-only properties

### 2.5 `delete_object`
- **Signature**: `delete_object(doc_name, obj_name)`
- **Test**: Create then delete, verify removed
- **Known**: ✅ Working
- **Edge cases**: Delete already-deleted object (should error gracefully)

### 2.6 `copy_object`
- **Signature**: `copy_object(doc_name, obj_name, new_name)`
- **Test**: Copy Box, verify independent properties
- **Known**: ✅ Working
- **Edge cases**: Name conflict (should auto-generate unique name)

### 2.7 `undo`
- **Signature**: `undo(doc_name, steps=1)`
- **Test**: Create then undo, object should vanish
- **Known**: ✅ Working
- **Edge cases**: Undo past document creation

---

## 3. Code Execution

### 3.1 `execute_code`
- **Signature**: `execute_code(code: str)`
- **Test matrix**:

| Scenario | Test | Status |
|----------|------|--------|
| Simple arithmetic | `result = 2+2` | ⏳ Untested |
| FreeCAD API import | `import FreeCAD; doc = FreeCAD.ActiveDocument` | ✅ Working |
| Create object | `doc.addObject("Part::Box", "X")` | ✅ Working |
| Create sketch | `doc.addObject("Sketcher::SketchObject", "S")` | ✅ Working |
| Add geometry to sketch | `sketch.addGeometry(Part.LineSegment(...))` | ✅ Working |
| Part::Extrusion | `doc.addObject("Part::Extrusion", ...)` | ✅ Working |
| PartDesign::Pad | `doc.addObject("PartDesign::Pad", ...)` via `Profile=` | ✅ Working |
| Draft API | `Draft.makeCircle(radius=25)` | ✅ Working |
| Boolean fuse | `Part::MultiFuse` | ✅ Working |
| Boolean cut | `Part::Cut` | ✅ Working |
| Boolean common | `Part::MultiCommon` | ✅ Working |
| Part:: fillet | `shape.makeFillet(5.0, edges)` | ✅ Working |

**Important note on output capture**: `FreeCAD.Console.PrintMessage` output may not be
returned in the `execute_code` response. Exceptions ARE captured. Use `raise Exception()`
or check `Shape.isValid()` for validation.

- **Edge cases**: Syntax error, runtime error, import error, long-running code (timeout)

---

## 4. Inspection & Measurement

### 4.1 `measure_object`
- **Signature**: `measure_object(doc_name, obj_name)`
- **Returns**: bounding_box, volume, surface_area, center_of_mass
- **Known**: ✅ Working
- **Test**: Box 100x50x25 → volume 125000, COM (50, 25, 12.5)
- **Edge cases**: Empty compound, null shape

### 4.2 `get_shape_topology`
- **Signature**: `get_shape_topology(doc_name, obj_name)`
- **Returns**: faces (area, normal, centroid), edges (length, curve_type), vertices
- **Known**: ✅ Working
- **Test**: Box 100x50x25 → should report 6 faces, 12 edges, 8 vertices
- **Edge cases**: Null shape (should error gracefully)

### 4.3 `get_freecad_status`
- **Signature**: `get_freecad_status()`
- **Returns**: active_document, open_documents, active_workbench, active_body, rpc_port, timer_chain
- **Known**: ✅ Working

### 4.4 `get_view`
- **Signature**: `get_view(view_name, width, height, focus_object)`
- **Returns**: Screenshot (ImageContent)
- **Known**: ✅ Working (returns empty in non-GUI context or model that can't render)
- **Test all views**: Isometric, Front, Top, Right, Back, Left, Bottom, Dimetric, Trimetric
- **Edge cases**: focus_object that doesn't exist (should fit all)

---

## 5. Sketch Workflow

### 5.1 `create_datum_plane`
- **Signature**: `create_datum_plane(doc_name, plane_name, alignment, offset)`
- **Test**: XY plane at origin, XZ plane at offset 50
- **Known**: ✅ Working
- **Creates**: PartDesign::Body named `{plane_name}` with plane as its ShapeBinder

### 5.2 `create_sketch_on_plane`
- **Signature**: `create_sketch_on_plane(doc_name, plane_name)`
- **Test**: Create sketch on existing datum plane
- **Known**: ✅ Working
- **Creates**: `{plane_name}_sketch` as Sketcher::SketchObject inside the Body

### 5.3 `add_contour_to_sketch`
- **Signature**: `add_contour_to_sketch(doc_name, sketch_name, geometry_elements, constraints, fix_first_point_to_origin)`
- **Known**: ❌ **Broken** — `name 'constraints' is not defined`
- **Root cause**: In `contour_builder.py:87` the print f-string references `constraints`
  but no such variable exists in FreeCAD's namespace — the constraints are built as
  `constraint_list` in the generated code.
- **Workaround**: Use `execute_code` directly to add geometry:
  ```python
  sketch.addGeometry([Part.LineSegment(v1, v2), ...], False)
  for i in range(n):
      sketch.addConstraint(Sketcher.Constraint('Coincident', ...))
  ```

### 5.4 `extrude_sketch_bidirectional`
- **Signature**: `extrude_sketch_bidirectional(doc_name, sketch_name, length_forward, length_backward, use_midplane)`
- **Known**: ⚠️ **Requires sketch inside a PartDesign::Body** — error: "Sketch is not in a Body"
- **Expected**: Creates PartDesign::Pad (or equivalent)
- **Alternative**: Use `execute_code` to create Pad:
  ```python
  pad = doc.addObject("PartDesign::Pad", "name")
  pad.Profile = sketch  # NOT pad.Sketch — that's wrong!
  pad.Length = 25.0
  body.addObject(pad)
  ```

### 5.5 `attach_solid_to_plane`
- **Signature**: `attach_solid_to_plane(doc_name, solid_body_name, target_plane_name, ...)`
- **Known**: ⏳ Untested

---

## 6. Boolean Operations

### 6.1 `boolean_union`
- **Signature**: `boolean_union(doc_name, base_object_name, tool_object_names, result_name)`
- **Test**: Fuse two overlapping Box objects
- **Known**: ✅ Working

### 6.2 `boolean_cut`
- **Signature**: `boolean_cut(doc_name, base_object_name, tool_object_name, result_name)`
- **Test**: Cut smaller box from larger box
- **Known**: ✅ Working

### 6.3 `boolean_intersection`
- **Signature**: `boolean_intersection(doc_name, object1_name, object2_name, result_name)`
- **Test**: Intersect two overlapping boxes
- **Known**: ⏳ Not directly tested but shares code path with union/cut
- **Expected**: ✅ Should work

---

## 7. Transformation & Positioning

### 7.1 `transform_object`
- **Signature**: `transform_object(doc_name, obj_name, position, rotation, relative)`
- **Test**: Move box to (200, 50, 0) and rotate 45° around Z
- **Known**: ✅ Working

### 7.2 `align_object`
- **Signature**: `align_object(doc_name, source_obj_name, target_obj_name, align_type, offset)`
- **Test**: Align position of one box to another
- **Known**: ⏳ Untested

### 7.3 `attach_to_face`
- **Signature**: `attach_to_face(doc_name, obj_name, target_obj_name, face_name, map_mode, offset)`
- **Test**: Attach a sketch to Face6 of a box
- **Known**: ⏳ Untested

### 7.4 `set_object_visibility`
- **Signature**: `set_object_visibility(doc_name, obj_name, visible)`
- **Test**: Hide then show a box
- **Known**: ⏳ Untested

---

## 8. Modeling Features

### 8.1 `add_fillet`
- **Signature**: `add_fillet(doc_name, object_name, edges, radius, result_name)`
- **Test**: Fillet 3 edges of a box with radius 5
- **Known**: ✅ Working

### 8.2 `add_chamfer`
- **Signature**: `add_chamfer(doc_name, object_name, edges, distance, result_name)`
- **Test**: Chamfer 2 edges with distance 3
- **Known**: ✅ Working

### 8.3 `shell_object`
- **Signature**: `shell_object(doc_name, object_name, thickness, faces_to_remove, result_name)`
- **Test**: Create a hollow shell from a box
- **Known**: ⏳ Untested
- **Expected**: Uses `makeThickness()` internally

### 8.4 `mirror_object`
- **Signature**: `mirror_object(doc_name, source_obj, mirror_plane, result_name, merge)`
- **Test**: Mirror a body across YZ plane, union the result
- **Known**: ✅ Working

### 8.5 `circular_pattern`
- **Signature**: `circular_pattern(doc_name, object_name, axis, count, angle, result_name)`
- **Test**: 6 instances around Z axis, 360°
- **Known**: ✅ Working

### 8.6 `linear_pattern`
- **Signature**: `linear_pattern(doc_name, object_name, direction, spacing, count, result_name)`
- **Test**: 5 instances along X axis, spacing 100
- **Known**: ✅ Working

### 8.7 `create_loft`
- **Signature**: `create_loft(doc_name, sketch_names, result_name, solid, ruled)`
- **Known**: ⚠️ **Pydantic validation error** on ImageContent in response
- **Test**: Loft through 2+ profile sketches
- **Expected**: Backend code might work but response encoding broken

### 8.8 `create_revolve`
- **Signature**: `create_revolve(doc_name, sketch_name, axis, angle, result_name)`
- **Known**: ⏳ Untested

### 8.9 `create_sweep`
- **Signature**: `create_sweep(doc_name, profile_sketch, path_sketch, result_name)`
- **Known**: ⏳ Untested

### 8.10 `create_spline_3d`
- **Signature**: `create_spline_3d(doc_name, points, spline_name, closed)`
- **Known**: ⏳ Untested

### 8.11 `create_reference_plane`
- **Signature**: `create_reference_plane(doc_name, plane_name, definition)`
- **Test**: offset mode, 3-points mode, point+normal mode
- **Known**: ⏳ Untested
- **Note**: This creates Part::Plane or Part::Feature, NOT PartDesign datum

### 8.12 `create_reference_axis`
- **Signature**: `create_reference_axis(doc_name, axis_name, point, direction)`
- **Known**: ⏳ Untested

---

## 9. Import / Export

### 9.1 `import_airfoil_profile`
- **Signature**: `import_airfoil_profile(doc_name, sketch_name, naca_code, chord_length, position)`
- **Test**: NACA 2412 with chord 1000mm — verify point count in sketch
- **Known**: ⏳ Untested
- **Note**: Uses `execute_code` internally with NACA equations

### 9.2 `import_dxf`
- **Signature**: `import_dxf(doc_name, file_path, sketch_name, scale)`
- **Known**: ⏳ Untested
- **Requires**: Actual DXF file on disk

### 9.3 `export_object`
- **Signature**: `export_object(doc_name, obj_name, path, export_format)`
- **Formats**: step, stl, obj, iges
- **Test**: Export to STEP, re-import and verify
- **Known**: ✅ Working (STEP tested)
- **Test all 4 formats**: step, stl, obj, iges

### 9.4 `insert_part_from_library`
- **Signature**: `insert_part_from_library(relative_path)`
- **Test**: Insert known library part
- **Known**: ⏳ Untested
- **Requires**: parts_library addon installed

### 9.5 `get_parts_list`
- **Signature**: `get_parts_list()`
- **Known**: ⏳ Untested

---

## 10. TechDraw

### 10.1 `create_techdraw_page`
- **Signature**: `create_techdraw_page(doc_name, page_name, template_path)`
- **Test**: Create page with and without SVG template
- **Known**: ⏳ Untested
- **Note**: Non-template pages require FreeCAD ≥ 1.0

### 10.2 `add_view_to_techdraw_page`
- **Signature**: `add_view_to_techdraw_page(doc_name, page_name, obj_name, view_name, x, y, scale)`
- **Test**: Project Box onto page at scale 0.5
- **Known**: ⏳ Untested

---

## 11. FEM

### 11.1 `run_fem_analysis`
- **Signature**: `run_fem_analysis(doc_name, analysis_name, timeout)`
- **Test**: Full FEM workflow (solid → mesh → constraints → solve)
- **Known**: ⏳ Untested
- **Requires**: CalculiX solver installed

---

## 12. Assembly (Assembly3 / Assembly4)

Assembly3 and Assembly4 are mutually exclusive workbenches. Test EACH separately.

### 12.1 `create_assembly3`
- **Signature**: `create_assembly3(doc_name, assembly_name)`
- **Test**: Create, add parts, add constraints, solve
- **Known**: ⏳ Untested

### 12.2 Assembly3 sub-tools
- `add_part_to_assembly3` — test with internal and external parts
- `add_assembly3_constraint` — test PlaneCoincident, Axial, PointsCoincident, etc.
- `solve_assembly3` — verify solver resolves constraints
- `list_assembly3_constraints` — verify listed
- `delete_assembly3_constraint` — verify removed
- `modify_assembly3_constraint` — verify updated

### 12.3 `create_assembly4`
- **Signature**: `create_assembly4(doc_name, assembly_name)`
- **Test**: Create, add LCS, insert parts
- **Known**: ⏳ Untested

### 12.4 Assembly4 sub-tools
- `create_lcs_assembly4` — test LCS creation
- `insert_part_assembly4` — test with external part file
- `attach_lcs_to_geometry` — test LCS on face/edge
- `list_assembly4_lcs` — verify listed
- `delete_lcs_assembly4` — verify removed
- `modify_lcs_assembly4` — verify updated

### 12.5 Shared assembly tools
- `list_assembly_parts` — test with both types
- `export_assembly` — test STEP export
- `generate_bom` — test JSON/CSV/Markdown output
- `get_assembly_properties` — test mass, COM, bounding box

---

## 13. Spreadsheet

### 13.1 `spreadsheet_read`
- **Signature**: `spreadsheet_read(doc_name, sheet_name, cell_range)`
- **Test**: Single cell "A1", range "A1:C3"
- **Known**: ⏳ Untested
- **Requires**: Spreadsheet::Sheet object in document

### 13.2 `spreadsheet_write`
- **Signature**: `spreadsheet_write(doc_name, sheet_name, cell, value)`
- **Test**: Write value, read back, verify
- **Known**: ⏳ Untested

---

## 14. Output Capture Investigation

The `execute_code` tool does not reliably return `FreeCAD.Console.PrintMessage` output.
This section documents how output is handled.

**Known behavior**:
- Syntax errors → returned in tool error field
- Runtime exceptions → returned in tool error field
- `print()` in FreeCAD's Python console → depends on stdio capture
- `FreeCAD.Console.PrintMessage()` → not captured in response
- `raise Exception("msg")` → reliably shown in error

**Test each method**:
| Method | Captured? |
|--------|-----------|
| `print("hello")` | ⏳ Test |
| `FreeCAD.Console.PrintMessage("hello")` | ⏳ Test |
| `FreeCAD.Console.PrintLog("hello")` | ⏳ Test |
| `FreeCAD.Console.PrintError("hello")` | ⏳ Test |
| `raise Exception("hello")` | ✅ Working |
| `App.Console.PrintMessage("hello")` | ⏳ Test |

---

## 15. Known Bugs Summary

| # | Tool | Symptom | Root Cause |
|---|------|---------|------------|
| 1 | `get_object`, `get_objects` | `string indices must be integers, not 'str'` | Response parsing in RPC/serialization layer |
| 2 | `add_contour_to_sketch` | `name 'constraints' is not defined` | Server-side variable name mismatch in f-string |
| 3 | `extrude_sketch_bidirectional` | "Sketch is not in a Body" | Tool doesn't auto-attach sketch to body or accepts standalone |
| 4 | `create_loft` | Pydantic validation error on ImageContent | Response type mismatch |
| 5 | Draft:: types in `create_object` | "not a document object type" | Draft objects require Draft API, not addObject |
| 6 | `execute_code` output | PrintMessage not captured | No stdout capture from FreeCAD console |
| 7 | Sketcher types in `create_object` | "not a document object type" | Sketcher objects require `Sketcher::SketchObject` |

---

## 16. Regression Test Scenarios

These are end-to-end workflows that exercise multiple tools in sequence.

### Scenario A: Part:: primitive → edit → measure → export
1. `create_document("RegA")`
2. `create_object("RegA", "Part::Box", "Box", {Length:50, Width:30, Height:20})`
3. `edit_object("RegA", "Box", {Height:25})`
4. `measure_object("RegA", "Box")` → verify volume = 50×30×25 = 37500
5. `export_object("RegA", "Box", "/tmp/reg_a.step", "step")`
6. Verify file exists

### Scenario B: Sketch → extrude → fillet → save/load
1. `create_document("RegB")`
2. `execute_code` to create body + sketch + pad (80×40×25)
3. `add_fillet("RegB", "Body", ["Edge1","Edge2"], 5, "Filleted")
4. `measure_object("RegB", "Filleted")` → volume < 80000 (fillet removes material)
5. `save_document("RegB", "/tmp/reg_b.FCStd")`
6. `load_document("/tmp/reg_b.FCStd")` → verify objects exist

### Scenario C: Multiple primitives → boolean union → mirror → export
1. Create 3 overlapping cylinders
2. `boolean_union(...)` → fused solid
3. `mirror_object(...)` → mirrored copy
4. `boolean_union(...)` → symmetric solid
5. Export as STL

### Scenario D: Assembly workflow (if Assembly3/4 available)
1. Create 2 independent Part::Box parts
2. Create Assembly3 container
3. Add parts to assembly
4. Add PlaneCoincident constraint
5. Solve
6. Export assembly as STEP

---

## 17. JSON Test Payloads

For manual testing via `execute_code`, these payloads exercise key operations:

### Create rectangular profile sketch:
```python
import FreeCAD, Part, Sketcher
doc = FreeCAD.getDocument("DOC_NAME")
sketch = doc.addObject("Sketcher::SketchObject", "Profile")
geo = [
    Part.LineSegment(FreeCAD.Vector(0,0,0), FreeCAD.Vector(100,0,0)),
    Part.LineSegment(FreeCAD.Vector(100,0,0), FreeCAD.Vector(100,50,0)),
    Part.LineSegment(FreeCAD.Vector(100,50,0), FreeCAD.Vector(0,50,0)),
    Part.LineSegment(FreeCAD.Vector(0,50,0), FreeCAD.Vector(0,0,0)),
]
sketch.addGeometry(geo, False)
for i in range(4):
    sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i+1)%4, 1))
doc.recompute()
```

### Extrude sketch to solid:
```python
ext = doc.addObject("Part::Extrusion", "Extrusion")
ext.Base = sketch
ext.DirMode = "Normal"
ext.LengthFwd = 30.0
ext.Solid = True
doc.recompute()
```

### PartDesign Pad (requires Body):
```python
body = doc.addObject("PartDesign::Body", "Body")
sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
body.addObject(sketch)
# ... add geometry ...
pad = doc.addObject("PartDesign::Pad", "Pad")
pad.Profile = sketch  # NOT pad.Sketch!
pad.Length = 25.0
body.addObject(pad)
doc.recompute()
```

### Boolean cut:
```python
cut = doc.addObject("Part::Cut", "Cut")
cut.Base = box_big
cut.Tool = box_small
doc.recompute()
```

### Part fillet via Python API:
```python
solid = box.Shape
edges = [solid.Edges[0], solid.Edges[1], solid.Edges[2]]
filleted = solid.makeFillet(5.0, edges)
fillet_obj = doc.addObject("Part::Feature", "Filleted")
fillet_obj.Shape = filleted
doc.recompute()
```

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

Key: Use `raise Exception("message")` for validation since it's the only reliably
captured output channel.
