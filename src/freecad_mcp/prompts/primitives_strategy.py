def part_primitives_strategy() -> str:
    """Strategic guide for creating geometry with Part primitives in FreeCAD MCP."""
    return """
Part Primitives Strategy for FreeCAD MCP

Use Part primitives when you need geometry quickly and do not require the full
parametric sketch workflow. Primitives are ideal for rapid prototyping, simple
mechanical parts, and geometry used as FEM input.

WHEN TO CHOOSE PRIMITIVES OVER THE SKETCH WORKFLOW:

Use Part primitives when:
- You need a quick solid without complex profiles (brackets, spacers, standoffs)
- You are setting up FEM geometry and need a simple test solid
- The shape is a standard geometric form (box, cylinder, sphere, cone, torus)
- Speed matters more than a fully parametric feature tree

Use the sketch workflow instead when:
- The cross-section is irregular or defined by precise constraints
- The part must be re-parameterised later by editing sketch dimensions
- You need to sweep or revolve a custom profile

AVAILABLE PRIMITIVE TYPES AND THEIR KEY PROPERTIES:

Part::Box
  Required: Length (X), Width (Y), Height (Z)
  Example: a 50 × 30 × 10 mm rectangular block

Part::Cylinder
  Required: Radius, Height
  Optional: Angle (partial cylinder, default 360)

Part::Sphere
  Required: Radius
  Optional: Angle1 (bottom latitude, default -90), Angle2 (top latitude, default 90),
            Angle3 (sweep angle, default 360)

Part::Cone
  Required: Radius1 (bottom), Radius2 (top), Height
  Set Radius2 = 0 for a sharp cone tip

Part::Torus
  Required: Radius1 (major, centre to tube centre), Radius2 (minor, tube radius)
  Optional: Angle1, Angle2, Angle3 (partial torus)

CREATING A PRIMITIVE — create_object CALL PATTERN:

{
  "doc_name": "MyDocument",
  "obj_type": "Part::Box",
  "obj_name": "BasePlate",
  "properties": {
    "Length": 80.0,
    "Width":  50.0,
    "Height": 10.0
  }
}

All dimension values are in millimetres. The object appears at the origin by default.

CHANGING PROPERTIES AFTER CREATION — edit_object:

{
  "doc_name": "MyDocument",
  "obj_name": "BasePlate",
  "properties": {
    "Height": 15.0
  }
}

Call edit_object whenever you need to resize or reposition an existing primitive.

POSITIONING WITH PLACEMENT:

Placement is a nested property. Set it through edit_object:

{
  "doc_name": "MyDocument",
  "obj_name": "HoleCylinder",
  "properties": {
    "Placement": {
      "Base": {"x": 25.0, "y": 15.0, "z": 0.0},
      "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 0.0}
    }
  }
}

Base x/y/z moves the origin of the primitive. Rotation.Axis is a unit vector;
Angle is in degrees. For cylinders the axis of symmetry is Z by default —
rotate by 90 degrees around X or Y to stand a cylinder on its side.

TYPICAL WORKFLOW — BOX WITH A CYLINDRICAL HOLE:

1. Create the base box:
   create_object(doc_name, "Part::Box", "Block",
                 {"Length": 80, "Width": 50, "Height": 20})

2. Create the cutting cylinder (slightly taller than the box so it passes through):
   create_object(doc_name, "Part::Cylinder", "HoleTool",
                 {"Radius": 8, "Height": 25})

3. Position the cylinder at the desired hole centre:
   edit_object(doc_name, "HoleTool",
               {"Placement": {"Base": {"x": 40, "y": 25, "z": -2.5},
                              "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 0}}})

4. Subtract the cylinder from the box:
   boolean_cut(doc_name, "Block", "HoleTool", "BlockWithHole")

5. Verify the result:
   measure_object(doc_name, "BlockWithHole")
   get_shape_topology(doc_name, "BlockWithHole")

COMBINING PRIMITIVES WITH BOOLEAN OPERATIONS:

- boolean_union(doc_name, base_obj, tool_obj, result_name)
    Fuses two solids; use to build up composite shapes.

- boolean_cut(doc_name, base_obj, tool_obj, result_name)
    Subtracts tool from base; use for holes, pockets, and cutouts.
    Order matters: base is what you keep, tool is what is removed.

- boolean_intersection(doc_name, base_obj, tool_obj, result_name)
    Keeps only the overlapping volume.

After each boolean operation the source objects are hidden but remain in the document.

VERIFYING RESULTS:

- measure_object — returns bounding box dimensions, volume, surface area, centre of mass.
  Use this to confirm the final size matches your design intent.

- get_shape_topology — returns face, edge, and vertex counts with their types and areas.
  Call this before add_fillet or add_chamfer to obtain valid face/edge names such as
  "Face3" or "Edge7". These names are NOT predictable; always query them first.

COMMON PATTERNS:

Spacer / standoff:
  Part::Cylinder (outer) → boolean_cut with smaller Part::Cylinder (inner bore)

Bracket:
  Part::Box (main arm) + Part::Box (flange) → boolean_union,
  then Part::Cylinder tools → boolean_cut for mounting holes

FEM test geometry:
  Part::Box or Part::Cylinder as a simple solid, then run_fem_analysis directly
  (see the fem_workflow prompt for full FEM setup instructions)

BEST PRACTICES:

1. Name every object descriptively ("HoleTool", "OuterRing") so it is easy to identify.
2. Verify the Placement of each primitive with get_objects before running a boolean.
3. Make cutting tools slightly larger/longer than the base solid to avoid zero-thickness
   faces at the cut boundary (e.g. cylinder Height = base Height + 5 mm, positioned -2.5 mm).
4. Use measure_object after each boolean to confirm the geometry is valid.
5. Call get_shape_topology before any fillet/chamfer — face and edge names are dynamic.
6. Save with save_document after completing the primitive assembly.
"""
