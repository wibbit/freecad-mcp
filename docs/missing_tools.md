# Missing / Planned MCP Tools

Identified 2026-05-10. Check off as implemented and tested.

---

## Required — blocks correct PartDesign workflow

- [x] **`add_datum_plane_to_body(doc_name, body_name, plane_name, alignment, offset)`** — implemented 2026-05-10
  Add a datum plane to an existing Body rather than always creating a new one.
  Currently `create_datum_plane` creates one Body per plane, making multi-feature
  PartDesign parts impossible without `execute_code`.

- [x] **`create_sketch_in_body(doc_name, body_name, plane_name)`** — implemented 2026-05-10
  Create a sketch inside an existing Body on a named datum plane within it.
  Companion to `add_datum_plane_to_body` — together they allow a full PartDesign
  feature tree in a single Body.

- [x] **`create_sketch_on_face(doc_name, body_name, obj_name, face_name)`** — implemented 2026-05-10
  Create a sketch directly on an existing solid face. Needed for ribs, drain holes,
  and any feature added to an existing solid without an intermediate datum plane.
  Call `get_shape_topology` first to get valid face names.

- [x] **Taper angle on `extrude_sketch_bidirectional`** — implemented 2026-05-10
  PartDesign::Pad supports a draft/taper angle parameter. Needed for tapered inserts,
  moulded parts, etc. (e.g. `-1.5°` draft on a 30mm deep insert body).
  New params: `taper_angle` (forward), `taper_angle2` (backward), both default 0.0.

- [x] **Reversed direction on `extrude_sketch_bidirectional`** — implemented 2026-05-10
  Pad below the sketch plane (negative direction) without relying on the bidirectional
  `length_backward` workaround. Maps to PartDesign::Pad `Reversed = True`.
  New param: `reversed` (bool, default False).

---

## Suggested — general gaps

- [x] **`groove(doc_name, sketch_name, axis, angle)`** — implemented 2026-05-10
  PartDesign::Groove — subtractive revolve. Complements `create_revolve` (additive)
  the same way `pocket_sketch` complements `extrude_sketch_bidirectional`.
  `axis` accepts: 'H_Axis', 'V_Axis', 'X_Axis', 'Y_Axis', 'Z_Axis'.

- [x] **`rename_object(doc_name, obj_name, new_label)`** — implemented 2026-05-10
  Renames the display label of a document object (FreeCAD's internal Name is immutable).
  Auto-generated names like Pad, Pocket001 etc. can be tidied this way.

- [x] **`close_document(doc_name, save_before_close)`** — implemented 2026-05-10
  Close an open document. Optional `save_before_close` flag.

- [x] **`import_step(doc_name, file_path, obj_name)`** — implemented 2026-05-10
  Import STEP (.step/.stp) or STL/OBJ files into a document. STEP imports as solid
  geometry; STL imports as mesh. `obj_name` sets the label of the first imported object.

- [x] **`add_techdraw_dimension(doc_name, page_name, view_name, dimension_type, references, x, y)`** — implemented 2026-05-10
  Add dimension annotations to a TechDraw view. Supports 'DistanceX', 'DistanceY',
  'Distance', 'Radius', 'Diameter', 'Angle'. References are edge/vertex names from
  the projected view. Call `get_shape_topology` on the source object first.
