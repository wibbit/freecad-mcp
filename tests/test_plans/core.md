# Core Tools — Integration Test Plan

Document lifecycle, object CRUD, code execution, and inspection/measurement.
Last updated: 2026-05-10

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

### 4.5 `get_freecad_errors`
- **Signature**: `get_freecad_errors(max_lines: int = 200)`
- **Returns**: Filtered error/warning lines from FreeCAD's Report View panel
- **Requires**: Report View panel open in FreeCAD (View → Panels → Report View)
- **Known**: ✅ Working
- **Test**: Call after `execute_code` with intentional error; confirm the error appears in output
- **Edge cases**:
  - Report View closed → returns descriptive message, not error
  - No errors in Report View → returns empty/no-errors message
  - `max_lines` smaller than available errors → returns tail of log (most recent lines)

---

## 5. Output Capture Investigation

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
