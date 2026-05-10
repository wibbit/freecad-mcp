ASSET_CREATION_STRATEGY = """
Asset Creation Strategy for FreeCAD MCP

Before starting any task:
1. Call get_freecad_status to confirm FreeCAD is running and identify the active document.
2. Call list_documents or get_objects to understand the current state.

Choosing the right creation method:

A. Parts library (fastest — use first)
   - Call get_parts_list to see available parts.
   - If the part exists, use insert_part_from_library.

B. Sketch-based workflow (preferred for precision solids)
   - Read the sketch_workflow prompt before starting.
   - Sequence: create_datum_plane → create_sketch_on_plane → add_contour_to_sketch → extrude_sketch_bidirectional
   - Combine results with boolean_union, boolean_cut, or boolean_intersection.
   - Refine with add_fillet, add_chamfer, or shell_object.

C. Advanced shapes
   - Swept/revolved solids: create_loft, create_revolve, create_sweep
   - Patterns: circular_pattern, linear_pattern, mirror_object
   - Reference geometry: create_reference_plane, create_reference_axis

D. Part primitives (for simple shapes or FEM setup)
   - Use create_object with types like Part::Box, Part::Cylinder, Part::Sphere.
   - Adjust properties with edit_object. Verify with get_object.

E. Assemblies
   - Read the assembly_guide prompt before starting.
   - Use Assembly3 (constraint-based) or Assembly4 (LCS-based) tools.

F. Inspection and file management
   - Measure geometry: measure_object (bounding box, volume, surface area, centre of mass)
   - Inspect topology: get_shape_topology (face/edge/vertex counts and properties)
   - Save/load: save_document, load_document
   - Export: export_object (STEP, IGES, STL, OBJ)
   - Copy: copy_object (duplicates an object with all dependencies)
   - Visibility: set_object_visibility (show/hide objects)
   - Undo: undo (rolls back N operations; requires document opened via FreeCAD GUI)
   - Spreadsheets: spreadsheet_read, spreadsheet_write (read/write Spreadsheet::Sheet cells)
   - Engineering drawings: create_techdraw_page, add_view_to_techdraw_page (TechDraw views)

G. execute_code — escape hatch only
   - Use only for operations not covered by any dedicated tool above.
   - Prefer dedicated tools wherever they exist.

Always use clear, descriptive names for documents and objects. All names are case-sensitive.
"""
