# FreeCAD Concepts for MCP Users

Core FreeCAD concepts that affect how MCP tools behave.

---

## The Document Model

Everything in FreeCAD lives inside a named Document. A document must exist before any object can be created in it. Multiple documents can be open simultaneously.

Key rules:
- Every tool that creates or reads objects takes a `doc_name` parameter.
- `doc_name` is the document's internal name, not its label or filename. Use `list_documents` to see open document names.
- Objects within a document are referenced by their internal `Name` (e.g. `"Box"`, `"Sketch001"`), not their display label. Use `get_objects(doc_name)` to confirm exact names — they are case-sensitive.
- Changes are not saved automatically. Call `save_document` explicitly.

---

## Part:: vs PartDesign:: vs Draft::

FreeCAD has three different paradigms for creating geometry. Using the wrong one causes silent failures.

### Part:: (Constructive Solid Geometry)
- Created via `create_object(doc_name, "Part::Box", ...)` or boolean operations.
- Objects live directly in the document — no container required.
- Best for: quick solids, FEM setup geometry, boolean source objects.
- Can be combined with `boolean_union`, `boolean_cut`, `boolean_intersection`.

### PartDesign:: (Feature-based modelling)
- Objects must live inside a `PartDesign::Body` container.
- Creating a `PartDesign::AdditiveBox` without an active Body will fail.
- `create_datum_plane` automatically creates a Body — use the sketch workflow to stay inside it.
- Best for: parts that will be edited, re-parameterised, or have features added/removed later.

### Draft::
- Draft objects (`Draft::Circle`, `Draft::Wire`, etc.) **cannot** be created via `create_object` or `doc.addObject()` — FreeCAD rejects the type string.
- Use `execute_code` with the Draft Python API instead: `Draft.makeCircle(radius=25)`.
- Draft objects live at document level like Part:: objects.

---

## Why PartDesign Requires a Body

A `PartDesign::Body` is a container that holds a sequential feature history. Each feature (pad, pocket, fillet) is applied on top of the previous one. Without a Body, FreeCAD has no place to attach the feature and refuses to create it.

The MCP sketch workflow handles this automatically: `create_datum_plane` creates a Body, and `create_sketch_on_plane` creates the sketch inside that Body. As long as you follow the four-step sketch workflow, you will always be inside a Body when `extrude_sketch_bidirectional` is called.

If you create a sketch manually via `execute_code` outside a Body, `extrude_sketch_bidirectional` will return "Sketch is not in a Body". Fix: create a Body explicitly and call `body.addObject(sketch)` before extruding.

---

## Topology Naming — Face1, Edge3, Vertex7

FreeCAD assigns names like `Face1`, `Edge3`, `Vertex7` to the sub-shapes of an object. These names:
- Are assigned dynamically by the topology engine, not by position or geometry.
- Are **not predictable** from the object's shape or creation parameters.
- **Change** when boolean operations are applied to the object — a fillet might shift `Face6` to `Face8`.

Always call `get_shape_topology(doc_name, obj_name)` to get current face/edge names before calling `add_fillet`, `add_chamfer`, `shell_object`, or `attach_to_face`. Never hardcode names like `"Face1"` without querying first.

---

## Placement and Coordinate Systems

FreeCAD uses a right-handed coordinate system: X right, Y forward, Z up (by convention, though FreeCAD does not enforce this).

A `Placement` consists of a `Base` (position vector) and a `Rotation`. When working with the MCP tools:
- `transform_object` sets absolute or relative placement.
- `create_datum_plane` with `alignment="XZ"` and `offset=50` places a plane in the XZ plane at Y=50 — the offset is along the axis perpendicular to the plane.
- Datum plane alignments: `"XY"` → offset along Z; `"XZ"` → offset along Y; `"YZ"` → offset along X.

---

## Recompute

After modifying object properties, FreeCAD must recompute to propagate changes through the dependency graph. The MCP tools call `doc.recompute()` internally. When using `execute_code`, always end with `doc.recompute()` after making changes, otherwise dependent objects (expressions, pads, fillets) will not update.
