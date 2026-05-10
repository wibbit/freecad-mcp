def session_startup_guide() -> str:
    """Concise session-startup checklist for an LLM beginning a FreeCAD MCP session."""
    return """
FreeCAD MCP Session Startup Guide

Follow these steps at the start of every FreeCAD MCP session before doing any
modelling work.

STEP 1 — CONFIRM FREECAD IS RUNNING:

Call get_freecad_status first, always.

This confirms:
- FreeCAD is running and the RPC server is reachable
- Which document is currently active
- Which workbench is loaded

If this call fails, the FreeCAD addon is not running. Check that the FreeCADMCP
addon is active in FreeCAD (Tools → Addon Manager) and the RPC server panel shows
a "Running" status. Do not proceed until get_freecad_status succeeds.

STEP 2 — CHECK OPEN DOCUMENTS:

Call list_documents to see what is already open.

- If a suitable document is listed, use it — pass its exact name to subsequent calls.
- If nothing is open and you need a new session, call create_document:
    create_document(doc_name="MyProject")

STEP 3 — LOAD EXISTING WORK (OPTIONAL):

If the user wants to continue from a previous session, call load_document:

    load_document(path="/path/to/project.FCStd")

The document name returned by load_document is what you pass as doc_name
to all subsequent tool calls. Verify with get_objects to see what already exists.

STEP 4 — CHOOSE THE RIGHT WORKFLOW:

Read the appropriate prompt before starting any multi-step task:

  Precision parametric solids (profiles, sweeps, extrusions)
    → Read the "sketch_workflow" prompt
    → Tools: create_datum_plane → create_sketch_on_plane → add_contour_to_sketch
             → extrude_sketch_bidirectional

  Quick solid modelling (boxes, cylinders, spheres, cones, tori)
    → Read the "part_primitives_guide" prompt
    → Tools: create_object (Part::Box / Part::Cylinder / etc.) + boolean_cut / boolean_union

  Combining or subtracting existing solids
    → Read the "boolean_operations_guide" prompt
    → Tools: boolean_union, boolean_cut, boolean_intersection

  Multi-part assembly with constraints
    → Read the "assembly_guide" prompt
    → Tools: create_assembly3 / create_assembly4 and related tools

  FEM stress analysis
    → Read the "fem_workflow" prompt
    → Tools: create_object (Fem::AnalysisPython, Fem::FemMeshGmsh, etc.)
             + run_fem_analysis

STEP 5 — VERIFY AS YOU GO:

- get_objects(doc_name) — list all objects currently in the document
- measure_object(doc_name, obj_name) — check bounding box, volume, surface area
- get_shape_topology(doc_name, obj_name) — required before add_fillet or add_chamfer;
  face and edge names like "Face3" or "Edge7" are dynamic and must be queried

STEP 6 — SAVE REGULARLY:

FreeCAD does not auto-save. After significant progress call:

    save_document(doc_name, path="/path/to/project.FCStd")

If no path is given and the document has been saved before, FreeCAD saves to the
same path. For a new document always provide an explicit path.

STEP 7 — IF SOMETHING GOES WRONG:

- Roll back recent operations:
    undo(doc_name, steps=N)
  N defaults to 1. Undo works only if the document was opened or created during
  the current FreeCAD GUI session (not via load_document in a fresh FreeCAD start).

- See current document state:
    get_objects(doc_name)

- If the RPC server stops responding (possible Qt GUI deadlock), restart FreeCAD
  entirely and reconnect. Do not retry tool calls in a loop — that will not resolve
  a deadlock.

QUICK-REFERENCE CHECKLIST:

  [ ] get_freecad_status → FreeCAD is reachable
  [ ] list_documents → know which document to work in
  [ ] load_document (if resuming) or create_document (if new)
  [ ] Read the relevant workflow prompt for the task at hand
  [ ] get_shape_topology before any fillet / chamfer
  [ ] save_document after significant progress
"""
