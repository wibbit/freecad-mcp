def fem_workflow_strategy() -> str:
    """Step-by-step guide for FEM stress analysis setup and execution in FreeCAD MCP."""
    return """
FEM Workflow Strategy for FreeCAD MCP

This guide walks through every step required to run a finite-element stress
analysis using the run_fem_analysis tool. Follow the steps in order; skipping
any step will cause the analysis to fail.

PREREQUISITES:

A solid geometry object must exist in the document before you start.
- Use Part primitives (Part::Box, Part::Cylinder, etc.) for simple test geometry.
- Use the sketch workflow (create_datum_plane → create_sketch_on_plane →
  add_contour_to_sketch → extrude_sketch_bidirectional) for precision solids.
- The object must be a valid closed solid, not a surface or wire.
- Confirm it exists: get_objects(doc_name)

STEP 1 — CREATE THE ANALYSIS CONTAINER:

create_object with Type "Fem::AnalysisPython":

{
  "doc_name": "MyDocument",
  "obj_type": "Fem::AnalysisPython",
  "obj_name": "Analysis",
  "properties": {}
}

All subsequent FEM objects (mesh, material, constraints) must be placed inside
this container. run_fem_analysis looks up objects by the analysis name you provide.

STEP 2 — ASSIGN MATERIAL:

create_object with Type "Fem::MaterialCommon":

{
  "doc_name": "MyDocument",
  "obj_type": "Fem::MaterialCommon",
  "obj_name": "Material",
  "properties": {}
}

After creation, set material properties with edit_object. Properties are stored
inside a nested "Material" dict:

{
  "doc_name": "MyDocument",
  "obj_name": "Material",
  "properties": {
    "Material": {
      "YoungsModulus":   "210000 MPa",
      "PoissonRatio":    "0.30",
      "Density":         "7900 kg/m^3",
      "UltimateTensileStrength": "460 MPa"
    }
  }
}

Common material presets (approximate values):
  Steel:     YoungsModulus=210000 MPa, PoissonRatio=0.30, Density=7900 kg/m^3
  Aluminium: YoungsModulus=70000 MPa,  PoissonRatio=0.33, Density=2700 kg/m^3
  Titanium:  YoungsModulus=114000 MPa, PoissonRatio=0.34, Density=4500 kg/m^3

STEP 3 — CREATE THE MESH:

create_object with Type "Fem::FemMeshGmsh", referencing the solid geometry object:

{
  "doc_name": "MyDocument",
  "obj_type": "Fem::FemMeshGmsh",
  "obj_name": "FEMMesh",
  "properties": {
    "Part": "MySolidObject"
  }
}

Mesh element size is set automatically by FreeCAD/Gmsh based on the geometry.
To control element size, edit_object after creation:

{
  "doc_name": "MyDocument",
  "obj_name": "FEMMesh",
  "properties": {
    "CharacteristicLengthMax": 5.0
  }
}

Smaller values produce finer meshes with more accurate results but longer solve times.

STEP 4 — ADD BOUNDARY CONDITIONS:

Fixed constraint (prevent movement on a face):

{
  "doc_name": "MyDocument",
  "obj_type": "Fem::ConstraintFixed",
  "obj_name": "FixedSupport",
  "properties": {
    "References": [["MySolidObject", "Face1"]]
  }
}

Force constraint (apply a load to a face):

{
  "doc_name": "MyDocument",
  "obj_type": "Fem::ConstraintForce",
  "obj_name": "AppliedLoad",
  "properties": {
    "References": [["MySolidObject", "Face3"]],
    "Force":     1000.0,
    "Direction": {"x": 0, "y": 0, "z": -1}
  }
}

Force is in Newtons. Direction is a unit vector in the global coordinate system.

IMPORTANT: Face names like "Face1", "Face3" are dynamic — they depend on the
object's topology. Always call get_shape_topology(doc_name, solid_name) first to
see which face indices exist and what area each face has. Choose the intended face
based on area or position.

You must add at least one fixed constraint and one force constraint before running.

STEP 5 — RUN THE SOLVER:

run_fem_analysis(doc_name, analysis_name)

Example:
{
  "doc_name": "MyDocument",
  "analysis_name": "Analysis"
}

This call is synchronous. FreeCAD will create a CalculiX solver automatically,
mesh the geometry, write input files, run the solver, and read back results.
Depending on mesh density and geometry complexity, this may take several seconds
to minutes. Do not call other tools while it is running.

The analysis container ("Analysis") must contain the mesh, material, and all
constraints before this call is made. If any required object is missing the
call will return an error describing what is absent.

STEP 6 — INTERPRET RESULTS:

run_fem_analysis returns a result summary including:
- max_von_mises_stress (MPa)   — peak equivalent stress; compare to yield strength
- max_displacement (mm)        — largest nodal deflection
- min_displacement (mm)        — smallest nodal deflection (usually ~0 at fixed face)
- node_count                   — total mesh nodes; higher = more accurate result

Design check (simple):
  Safety factor = Material UTS / max_von_mises_stress
  If safety factor < 1.5 consider redesigning the part.

COMMON PITFALLS:

1. Missing analysis container
   All FEM objects must be children of a "Fem::AnalysisPython" object.
   If you skip this step, run_fem_analysis will not find the mesh or constraints.

2. No material assigned
   The solver will refuse to run without material properties.

3. Face names are wrong
   Always call get_shape_topology before specifying face names in constraints.
   The same geometry object can have different face numbering after a boolean operation.

4. Solid is not closed
   A surface or open shell cannot be meshed as a solid FEM domain.
   Verify with measure_object — a valid solid has non-zero Volume.

5. Force with no reaction
   You must have at least one fixed constraint; otherwise the part is free to
   accelerate as a rigid body and the solver will diverge.

TYPICAL FULL WORKFLOW EXAMPLE:

  1. create_object "Part::Box" → "TestBlock" (100 × 50 × 20 mm)
  2. get_shape_topology "TestBlock" → note face names and areas
  3. create_object "Fem::AnalysisPython" → "Analysis"
  4. create_object "Fem::MaterialCommon" → "Material"
     edit_object "Material" → set Steel properties
  5. create_object "Fem::FemMeshGmsh" → "FEMMesh", Part = "TestBlock"
  6. create_object "Fem::ConstraintFixed" → "Fixed", References = [["TestBlock","Face1"]]
  7. create_object "Fem::ConstraintForce" → "Load",
     References = [["TestBlock","Face2"]], Force = 5000, Direction z = -1
  8. run_fem_analysis "MyDocument" "Analysis"
  9. Review max_von_mises_stress against material UTS
"""
