# Modeling Tools — Integration Test Plan

Boolean operations, transformation/positioning, advanced modeling features, and import/export.
Last updated: 2026-05-10

---

## 1. Boolean Operations

### 1.1 `boolean_union`
- **Signature**: `boolean_union(doc_name, base_object_name, tool_object_names, result_name)`
- **Test**: Fuse two overlapping Box objects
- **Known**: ✅ Working

### 1.2 `boolean_cut`
- **Signature**: `boolean_cut(doc_name, base_object_name, tool_object_name, result_name)`
- **Test**: Cut smaller box from larger box
- **Known**: ✅ Working

### 1.3 `boolean_intersection`
- **Signature**: `boolean_intersection(doc_name, object1_name, object2_name, result_name)`
- **Known**: ⏳ Untested

#### Explicit test cases
- **Test**: Two overlapping boxes — Box1 (100×100×100 at origin), Box2 (50×50×150 offset 25 on each axis)
- **Expected result**: Intersection volume equals the overlapping region
- **Validation**: Run `measure_object` on result after intersection and verify volume matches calculated overlap
- **Setup**:
  1. `create_document`, create Box1 100×100×100
  2. Create Box2 50×50×150, `transform_object` offset (25, 25, 0)
  3. `boolean_intersection("doc", "Box1", "Box2", "Intersection")`
  4. `measure_object("doc", "Intersection")` — verify volume = 50×50×100 = 250000 mm³

---

## 2. Transformation & Positioning

### 2.1 `transform_object`
- **Signature**: `transform_object(doc_name, obj_name, position, rotation, relative)`
- **Test**: Move box to (200, 50, 0) and rotate 45° around Z
- **Known**: ✅ Working

### 2.2 `align_object`
- **Signature**: `align_object(doc_name, source_obj_name, target_obj_name, align_type, offset)`
- **Known**: ⏳ Untested

#### Test matrix
| `align_type` | Setup | Validation |
|-------------|-------|------------|
| `position` | Align Box2 to Box1's origin | COM of Box2 matches Box1's COM |
| `rotation` | Align Box2 rotation to a rotated Box1 | Rotation matrices match |
| `both` | Full align | Position and rotation both match |
| With offset | `align_type=position, offset={x:10}` | COM offset by 10 from target |

All variants: ⏳ Untested

### 2.3 `attach_to_face`
- **Signature**: `attach_to_face(doc_name, obj_name, target_obj_name, face_name, map_mode, offset)`
- **Known**: ⏳ Untested

#### Test matrix
| `map_mode` | Test | Status |
|-----------|------|--------|
| `FlatFace` | Attach sketch flat on Face1 of a box | ⏳ Untested |
| `NormalToEdge` | Attach perpendicular to Edge1 | ⏳ Untested |
| `ObjectXY` | Align object to target's XY plane | ⏳ Untested |

Also test: invalid `face_name` should return a clear error, not crash.

### 2.4 `set_object_visibility`
- **Signature**: `set_object_visibility(doc_name, obj_name, visible)`
- **Known**: ⏳ Untested

#### Test sequence
1. Create Box
2. `set_object_visibility(doc, "Box", False)` → `get_object` → verify `ViewObject.Visibility = False`
3. `set_object_visibility(doc, "Box", True)` → `get_object` → verify `ViewObject.Visibility = True`
4. `get_view` screenshot — hidden object should not appear in render

Edge case: hide an already-hidden object (should be a no-op, not error)

---

## 3. Advanced Modeling Features

### 3.1 `add_fillet`
- **Signature**: `add_fillet(doc_name, object_name, edges, radius, result_name)`
- **Test**: Fillet 3 edges of a box with radius 5
- **Known**: ✅ Working
- **Note**: Call `get_shape_topology` first to get valid edge names (e.g. `"Edge1"`, `"Edge3"`)

### 3.2 `add_chamfer`
- **Signature**: `add_chamfer(doc_name, object_name, edges, distance, result_name)`
- **Test**: Chamfer 2 edges with distance 3
- **Known**: ✅ Working

### 3.3 `shell_object`
- **Signature**: `shell_object(doc_name, object_name, thickness, faces_to_remove, result_name)`
- **Known**: ⏳ Untested
- **Note**: Uses `Part::Thickness` internally — face names must be valid `FaceN` strings. Call `get_shape_topology` first.

#### Test cases
- **Basic test**: Box 100×100×100, remove `Face1` (top), thickness 5
  - Expected: hollow box open at top, wall thickness = 5
  - Validate with `measure_object`: volume ≈ 100³ − 90³ = 1000000 − 729000 = 271000 mm³
- **Multiple faces**: remove `Face1` and `Face6` — verify two openings
- **Edge cases**:
  - Thickness larger than shortest dimension (should error gracefully)
  - `faces_to_remove=[]` (close all faces — no opening)

### 3.4 `mirror_object`
- **Signature**: `mirror_object(doc_name, source_obj, mirror_plane, result_name, merge)`
- **Test**: Mirror a body across YZ plane, union the result
- **Known**: ✅ Working
- **Also test**: `merge=True` — see Scenario H in main plan (validates the `if true:` NameError fix)

### 3.5 `circular_pattern`
- **Signature**: `circular_pattern(doc_name, object_name, axis, count, angle, result_name)`
- **Test**: 6 instances around Z axis, 360°
- **Known**: ✅ Working

### 3.6 `linear_pattern`
- **Signature**: `linear_pattern(doc_name, object_name, direction, spacing, count, result_name)`
- **Test**: 5 instances along X axis, spacing 100
- **Known**: ✅ Working

### 3.7 `create_loft`
- **Signature**: `create_loft(doc_name, sketch_names, result_name, solid, ruled)`
- **Known**: ⚠️ **Pydantic validation error** on ImageContent in response
- **Test**: Loft through 2+ profile sketches
- **Expected**: Backend code might work but response encoding broken

### 3.8 `create_revolve`
- **Signature**: `create_revolve(doc_name, sketch_name, axis, angle, result_name)`
- **Known**: ⏳ Untested

#### Test cases
**Test 1 — Full revolution (vase)**:
- Profile: sketch with a closed profile offset from Z axis
- `axis: {"point": {"x":0,"y":0,"z":0}, "direction": {"x":0,"y":0,"z":1}}`
- `angle: 360` → verify closed solid
- `measure_object`: volume should match πr²h formula

**Test 2 — Partial revolution**:
- Same profile, `angle: 90` → verify open solid (4 faces: 2 arcs + 2 flat)

**Edge cases**:
- Profile crosses axis (should error)
- `angle > 360` (should clamp or error)

### 3.9 `create_sweep`
- **Signature**: `create_sweep(doc_name, profile_sketch, path_sketch, result_name)`
- **Known**: ⏳ Untested
- **Note**: `path_sketch` must be a wire or open sketch — a closed profile will fail as path.

#### Test cases
**Basic test**: Circular profile swept along a 3D path
- Profile: circle r=5 in XY plane
- Path: a Line sketch along Z axis, length 100
- Expected: cylinder-like solid
- Validate with `measure_object`: volume ≈ π×5²×100 ≈ 7854 mm³

**Edge cases**:
- Path not connected (should error)
- Profile not closed (creates open shell, not solid)

### 3.10 `create_spline_3d`
- **Signature**: `create_spline_3d(doc_name, points, spline_name, closed)`
- **Known**: ⏳ Untested

#### Test cases
**Test 1 — Open spline**:
- `points: [(0,0,0), (50,50,0), (100,0,0), (150,50,0)]`
- `closed: False`
- Expected: Wire object, not solid. Use as path for `create_sweep`.

**Test 2 — Closed spline**:
- 5 points in a loop, `closed: True`
- Expected: closed Wire

**Edge cases**:
- Less than 2 points (should error)
- Duplicate adjacent points

### 3.11 `create_reference_plane`
- **Signature**: `create_reference_plane(doc_name, plane_name, definition)`
- **Known**: ⏳ Untested
- **Note**: Creates a Part::Feature at document level, NOT a PartDesign datum plane (use `create_datum_plane` for that).

#### Test cases for all three modes
| Mode | Parameters | Validation | Status |
|------|-----------|------------|--------|
| `offset` | `alignment="XY", offset=50` | Plane at Z=50 | ⏳ Untested |
| `3points` | Three non-collinear points | Plane passes through all three | ⏳ Untested |
| `point_normal` | Point + normal vector | Plane at point, perpendicular to normal | ⏳ Untested |

### 3.12 `create_reference_axis`
- **Signature**: `create_reference_axis(doc_name, axis_name, point, direction)`
- **Known**: ⏳ Untested

#### Test cases
- **Basic test**: `point=(0,0,0), direction=(1,0,0)` → creates axis along X
  - Validate: object exists, `TypeId = Part::Feature`
- **Edge case**: zero-length direction vector `(0,0,0)` (should error)

---

## 4. Import / Export

### 4.1 `import_airfoil_profile`
- **Signature**: `import_airfoil_profile(doc_name, sketch_name, naca_code, chord_length, position)`
- **Test**: NACA 2412 with chord 1000mm — verify point count in sketch
- **Known**: ⏳ Untested
- **Note**: Uses `execute_code` internally with NACA equations

### 4.2 `import_dxf`
- **Signature**: `import_dxf(doc_name, file_path, sketch_name, scale)`
- **Known**: ⏳ Untested
- **Requires**: Actual DXF file on disk

### 4.3 `export_object`
- **Signature**: `export_object(doc_name, obj_name, path, export_format)`

#### Format coverage
| Format | Test file | Status |
|--------|-----------|--------|
| `step` | `/tmp/test_export.step` | ✅ Working |
| `stl` | `/tmp/test_export.stl` — verify ASCII or binary STL produced | ⏳ Untested |
| `obj` | `/tmp/test_export.obj` — verify mesh file | ⏳ Untested |
| `iges` | `/tmp/test_export.iges` | ⏳ Untested |

#### Edge cases
- Path with non-existent directory (should error)
- Object with no shape (spreadsheet, datum) — should error
- Wrong format vs file extension mismatch

### 4.4 `insert_part_from_library`
- **Signature**: `insert_part_from_library(relative_path)`
- **Test**: Insert known library part
- **Known**: ⏳ Untested
- **Requires**: parts_library addon installed

### 4.5 `get_parts_list`
- **Signature**: `get_parts_list()`
- **Known**: ⏳ Untested
- **Note**: Must be called before `insert_part_from_library` to discover valid `relative_path` values

---

## JSON Test Payloads

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
