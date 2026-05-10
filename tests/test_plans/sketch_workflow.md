# Sketch Workflow — Integration Test Plan

Datum plane creation, sketch attachment, contour building, and extrusion.
Last updated: 2026-05-10

**Simple workflow** (one sketch, one solid — new Body per plane):
`create_datum_plane` → `create_sketch_on_plane` → `add_contour_to_sketch` → `extrude_sketch_bidirectional` or `pocket_sketch`

**Multi-feature workflow** (multiple sketches/features in one Body):
`create_datum_plane` (creates Body) → `add_datum_plane_to_body` × N → `create_sketch_in_body` × N → `add_contour_to_sketch` × N → `extrude_sketch_bidirectional` / `pocket_sketch` / `create_loft`

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
- **Signature**: `extrude_sketch_bidirectional(doc_name, sketch_name, length_forward, length_backward, use_midplane, taper_angle, taper_angle2, reversed)`
- **Known**: ✅ Working — `getParentGroup()` fallback body search fixed 2026-05-10; taper + reversed added 2026-05-10
- **Creates**: PartDesign::Pad named `{sketch_name}_solid`

### Extrude modes

| Mode | Parameters | Status |
|------|-----------|--------|
| Forward only | `length_forward=25, length_backward=0` | ✅ Tested 2026-05-10 |
| Bidirectional | `length_forward=20, length_backward=10` — verify total depth 30 | ⏳ Untested |
| Midplane | `use_midplane=True, length_forward=30` — verify symmetric | ⏳ Untested |
| Taper forward | `length_forward=25, taper_angle=-1.5` — verify draft angle on side faces | ⏳ Untested |
| Taper bidirectional | `length_forward=20, length_backward=10, taper_angle=-1.5, taper_angle2=-1.5` | ⏳ Untested |
| Reversed | `length_forward=25, reversed=True` — verify pad extrudes below sketch plane | ⏳ Untested |

---

## 5. `pocket_sketch`
- **Signature**: `pocket_sketch(doc_name, sketch_name, depth, depth2, through_all, symmetric)`
- **Known**: ⏳ Untested — added 2026-05-10
- **Creates**: PartDesign::Pocket named `{sketch_name}_pocket`
- **Prerequisite**: Sketch must be inside a PartDesign Body (use `create_sketch_on_plane`). The Body must already have an additive solid (e.g. from `extrude_sketch_bidirectional`) for the pocket to cut into.

### Pocket modes

| Mode | Parameters | Expected result | Status |
|------|-----------|-----------------|--------|
| Fixed depth | `depth=10` | Pocket 10mm deep | ⏳ Untested |
| Two-sided | `depth=10, depth2=5` — verify total cut 15mm | Both directions cut | ⏳ Untested |
| Through-all | `through_all=True` — verify `depth` ignored | Cuts entire solid | ⏳ Untested |
| Symmetric | `symmetric=True, depth=20` — verify 10mm each side | Symmetric cut | ⏳ Untested |

### Suggested test sequence
1. `create_document("PocketTest")`
2. `create_datum_plane("PocketTest", "base", alignment="xy")`
3. `create_sketch_on_plane("PocketTest", "base")` → creates `base_sketch`
4. `add_contour_to_sketch` — 80×60 rectangle → `base_sketch`
5. `extrude_sketch_bidirectional("PocketTest", "base_sketch", length_forward=30)` → creates `base_solid`
6. `create_sketch_on_plane("PocketTest", "base")` → creates second sketch (name will differ — check with `get_objects`)
7. `add_contour_to_sketch` — 20×20 rectangle centred on face
8. `pocket_sketch("PocketTest", "<second_sketch_name>", depth=15)` → creates pocket
9. `measure_object("PocketTest", "<pocket_name>")` — verify volume < 80×60×30 = 144000 mm³

---

## 6. `add_datum_plane_to_body`
- **Signature**: `add_datum_plane_to_body(doc_name, body_name, plane_name, alignment, offset)`
- **Known**: ⏳ Untested — added 2026-05-10
- **Purpose**: Add a datum plane to an existing Body. Use after `create_datum_plane` (which creates the Body) to add further planes for multi-feature PartDesign parts.

### Test cases

| Test | Parameters | Expected | Status |
|------|-----------|----------|--------|
| Basic | `body_name="Holder", plane_name="DP_Top", alignment="xy", offset=28` | Plane inside Holder body at Z=28 | ⏳ Untested |
| XZ plane | `alignment="xz", offset=16` | Plane at Y=16 in XZ orientation | ⏳ Untested |
| Body not found | `body_name="NoSuchBody"` | Clear error message | ⏳ Untested |
| Wrong type | `body_name` points to a Part::Box | Clear error: not a Body | ⏳ Untested |

### Suggested multi-feature test sequence
1. `create_datum_plane("Doc", "Holder", alignment="xy")` — creates Body "Holder" at Z=0
2. `add_datum_plane_to_body("Doc", "Holder", "DP_Top", alignment="xy", offset=28)` — adds plane at Z=28
3. `get_objects("Doc")` — confirm both `Holder` and `DP_Top` exist, `DP_Top` inside `Holder`

---

## 7. `create_sketch_in_body`
- **Signature**: `create_sketch_in_body(doc_name, body_name, plane_name)`
- **Known**: ⏳ Untested — added 2026-05-10
- **Purpose**: Create a sketch inside an existing Body on a named datum plane within it. Produces `{plane_name}_sketch`.

### Test cases

| Test | Parameters | Expected | Status |
|------|-----------|----------|--------|
| Basic | `body_name="Holder", plane_name="DP_Top"` | `DP_Top_sketch` inside Holder | ⏳ Untested |
| Body not found | `body_name="NoSuchBody"` | Clear error message | ⏳ Untested |
| Plane not found | `plane_name="NoSuchPlane"` | Clear error message | ⏳ Untested |

### Suggested end-to-end multi-Body test
1. `create_datum_plane("Doc", "Holder", alignment="xy", offset=0)`
2. `add_datum_plane_to_body("Doc", "Holder", "DP_NeckBottom", alignment="xy", offset=16)`
3. `add_datum_plane_to_body("Doc", "Holder", "DP_NeckTop", alignment="xy", offset=28)`
4. `create_sketch_on_plane("Doc", "Holder")` → `Holder_sketch` (flange profile)
5. `create_sketch_in_body("Doc", "Holder", "DP_NeckBottom")` → `DP_NeckBottom_sketch`
6. `create_sketch_in_body("Doc", "Holder", "DP_NeckTop")` → `DP_NeckTop_sketch`
7. `get_objects("Doc")` — all three sketches should be inside the same `Holder` Body
8. `add_contour_to_sketch` on each sketch
9. `extrude_sketch_bidirectional("Doc", "Holder_sketch", 10)` → flange pad
10. `create_loft("Doc", ["DP_NeckBottom_sketch", "DP_NeckTop_sketch"])` → neck transition
11. `measure_object` — verify resulting solid

---

## 8. `create_sketch_on_face`
- **Signature**: `create_sketch_on_face(doc_name, body_name, obj_name, face_name, sketch_name?)`
- **Known**: ⏳ Untested — added 2026-05-10
- **Purpose**: Attach a sketch directly to a planar face of an existing solid. Prerequisite: call `get_shape_topology` first to get valid face names.
- **Creates**: `{obj_name}_{face_name}_sketch` (or explicit `sketch_name`) inside the specified Body

### Test cases

| Test | Parameters | Expected | Status |
|------|-----------|----------|--------|
| Top face of box | `obj_name="Box", face_name="Face6"` | Sketch on top face | ⏳ Untested |
| Side face | `face_name="Face2"` | Sketch on side face | ⏳ Untested |
| Non-planar face | Cylinder curved face | Clear error or warning | ⏳ Untested |
| Bad face name | `face_name="Face99"` | Clear out-of-range error | ⏳ Untested |
| Explicit sketch name | `sketch_name="BoreProfile"` | Sketch named "BoreProfile" | ⏳ Untested |

### Suggested test sequence
1. `create_document("FaceSketchTest")`
2. `create_object("FaceSketchTest", "Part::Box", "Box", {"Length":80,"Width":60,"Height":40})`
3. `create_object("FaceSketchTest", "PartDesign::Body", "Holder")` — body for sketches
4. `get_shape_topology("FaceSketchTest", "Box")` — identify top face name
5. `create_sketch_on_face("FaceSketchTest", "Holder", "Box", "<top_face>", "SlotProfile")`
6. `add_contour_to_sketch` — 20×40 rectangle
7. `pocket_sketch("FaceSketchTest", "SlotProfile", depth=15)` — cut slot into box
8. `measure_object("FaceSketchTest", "SlotProfile_pocket")` — volume < 80×60×40 = 192000

---

## 9. `attach_solid_to_plane`
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
