# Missing / Planned MCP Tools

Identified 2026-05-10. Check off as implemented and tested.

---

## Required — blocks correct PartDesign workflow

- [ ] **`add_datum_plane_to_body(doc_name, body_name, plane_name, alignment, offset)`**
  Add a datum plane to an existing Body rather than always creating a new one.
  Currently `create_datum_plane` creates one Body per plane, making multi-feature
  PartDesign parts impossible without `execute_code`.

- [ ] **`create_sketch_in_body(doc_name, body_name, plane_name)`**
  Create a sketch inside an existing Body on a named datum plane within it.
  Companion to `add_datum_plane_to_body` — together they allow a full PartDesign
  feature tree in a single Body.

- [ ] **`create_sketch_on_face(doc_name, body_name, obj_name, face_name)`**
  Create a sketch directly on an existing solid face. Needed for ribs, drain holes,
  and any feature added to an existing solid without an intermediate datum plane.
  Call `get_shape_topology` first to get valid face names.

- [ ] **Taper angle on `extrude_sketch_bidirectional`**
  PartDesign::Pad supports a draft/taper angle parameter. Needed for tapered inserts,
  moulded parts, etc. (e.g. `-1.5°` draft on a 30mm deep insert body).

- [ ] **Reversed direction on `extrude_sketch_bidirectional`**
  Pad below the sketch plane (negative direction) without relying on the bidirectional
  `length_backward` workaround. Should map to PartDesign::Pad `Reversed = True`.

---

## Suggested — general gaps

- [ ] **`groove(doc_name, sketch_name, axis, angle)`**
  PartDesign::Groove — subtractive revolve. Complements `create_revolve` (additive)
  the same way `pocket_sketch` complements `extrude_sketch_bidirectional`.

- [ ] **`rename_object(doc_name, old_name, new_name)`**
  Rename a document object. Auto-generated names (Pad, Pocket001, etc.) need tidying
  for readable feature trees. Currently requires `execute_code`.

- [ ] **`close_document(doc_name)`**
  Close an open document. Currently no way to do this without `execute_code`.

- [ ] **`import_step(doc_name, path)`**
  Import existing 3D geometry (STEP or STL) into a document. `import_dxf` exists
  for 2D but there is no equivalent for 3D files.

- [ ] **TechDraw dimension tools**
  `create_techdraw_page` and `add_view_to_techdraw_page` exist but produce a page
  with no annotations. At minimum: add linear dimension, add radius/diameter dimension,
  add angle dimension.
