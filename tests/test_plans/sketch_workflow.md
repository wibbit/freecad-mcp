# Sketch Workflow — Integration Test Plan

Datum plane creation, sketch attachment, contour building, and extrusion.
Last updated: 2026-05-10

The full workflow is sequential and must be executed in order:
`create_datum_plane` → `create_sketch_on_plane` → `add_contour_to_sketch` → `extrude_sketch_bidirectional`

See Scenario E in the main [INTEGRATION_TEST_PLAN.md](../INTEGRATION_TEST_PLAN.md) for the end-to-end regression test.

---

## 1. `create_datum_plane`
- **Signature**: `create_datum_plane(doc_name, plane_name, alignment, offset)`
- **Known**: ✅ Working
- **Creates**: PartDesign::Body named `{plane_name}` with plane as its ShapeBinder

### Alignment test cases

| Alignment | Offset | Test | Status |
|-----------|--------|------|--------|
| `XY` | 0 | Baseline — plane at Z=0 | ⏳ Untested |
| `XZ` | 50 | Verify plane is XZ orientation (not XY), placed at Y=50 | ⏳ Untested |
| `YZ` | -25 | Verify plane is YZ orientation, placed at X=-25 | ⏳ Untested |

### Offset-only test cases
- Same alignment (`XY`), vary offset across positive and negative values (e.g., 0, 25, -10)
- Validate via `measure_object` or `get_shape_topology` that placement changes match offset value
- All: ⏳ Untested

---

## 2. `create_sketch_on_plane`
- **Signature**: `create_sketch_on_plane(doc_name, plane_name)`
- **Test**: Create sketch on existing datum plane
- **Known**: ✅ Working
- **Creates**: `{plane_name}_sketch` as Sketcher::SketchObject inside the Body
- **Edge cases**: `plane_name` that doesn't exist (should error with clear message)

---

## 3. `add_contour_to_sketch`
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

### 3.1 Geometry type coverage (when fixed)
Once the constraints bug is resolved, test each geometry type individually:

| Type | Test case | Status |
|------|-----------|--------|
| `line` | Two endpoints at (0,0)→(100,0) | ⏳ Untested |
| `arc` | Center (50,0), radius 25, 0°→180° — verify arc direction | ⏳ Untested |
| `circle` | Center (0,0), radius 30 — verify closed loop | ⏳ Untested |
| `bspline` | 4 control points — verify smooth curve added | ⏳ Untested |
| `ellipse` | Center (0,0), major 40, minor 20 | ⏳ Untested |

### 3.2 Constraint type coverage

| Type | Test case | Status |
|------|-----------|--------|
| `coincident` | Join end of line to start of next | ⏳ Untested |
| `horizontal` | Force a line horizontal | ⏳ Untested |
| `vertical` | Force a line vertical | ⏳ Untested |
| `tangent` | Tangent between line and arc | ⏳ Untested |
| `distance` | Fixed length constraint on a line | ⏳ Untested |
| `fix` | Block a point at a specific location | ⏳ Untested |

### 3.3 `fix_first_point_to_origin` behaviour
- `True` (default): First geometry point is constrained to sketch origin
- `False`: No automatic constraint — useful when geometry doesn't start at origin
- Test: rectangle not centred at origin with `fix_first_point_to_origin=False` → verify no distortion

---

## 4. `extrude_sketch_bidirectional`
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

### Extrude modes

| Mode | Parameters | Status |
|------|-----------|--------|
| Forward only | `length_forward=25, length_backward=0` | ⏳ Untested (requires Body) |
| Bidirectional | `length_forward=20, length_backward=10` — verify total depth 30 | ⏳ Untested |
| Midplane | `use_midplane=True, length_forward=30` — verify symmetric | ⏳ Untested |

**Note**: The full sketch workflow works end-to-end when the sketch is created via
`create_sketch_on_plane` (which places it inside a Body). See Scenario E in the main plan.

---

## 5. `attach_solid_to_plane`
- **Signature**: `attach_solid_to_plane(doc_name, solid_body_name, target_plane_name, ...)`
- **Known**: ⏳ Untested
- **Purpose**: Positions a solid body relative to a named reference plane

---

## JSON Test Payload — Manual sketch via `execute_code`

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

### Extrude to solid via Part::Extrusion:
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
