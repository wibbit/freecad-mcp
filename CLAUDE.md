# FreeCAD MCP — Developer Heuristics for Claude Code

Operational notes for developers using Claude Code directly against the FreeCAD MCP server.

## Session Start

Always call `get_freecad_status` first. If it fails:
- Open FreeCAD and confirm the FreeCADMCP addon is loaded (Tools → Addon Manager).
- Check the RPC server panel inside FreeCAD — it must show "Running" and display a port number.
- Only after `get_freecad_status` succeeds should you call any other tool.

## Choosing a Workflow

| Goal | Approach |
|------|----------|
| Part that needs editing or re-parameterising later | Sketch workflow (`create_datum_plane` → sketch → extrude) |
| Quick solid for testing or FEM | Part primitives (`create_object` with `Part::Box`, `Part::Cylinder`, etc.) |
| Combining or hollowing existing solids | Boolean operations (`boolean_union`, `boolean_cut`, `boolean_intersection`) |
| Operation not covered by a dedicated tool | `execute_code` — last resort only |

Never reach for `execute_code` when a dedicated tool exists.

## Geometry Verification

Call `get_shape_topology(doc_name, obj_name)` before every `add_fillet` or `add_chamfer`.

Face and edge names (`"Face3"`, `"Edge7"`) are assigned dynamically by FreeCAD's topology
engine. They are not predictable from object shape alone and can change after boolean
operations. Always query topology first; never guess face or edge names.

## Saving Work

FreeCAD does not auto-save. Call `save_document(doc_name, path)` after any significant
progress. For a new document always supply an explicit path ending in `.FCStd`.

## If the RPC Server Stops Responding

The FreeCAD Qt GUI queue may be deadlocked. Symptoms: tool calls hang or time out,
`get_freecad_status` does not return.

Recovery:
1. Restart FreeCAD completely.
2. Wait for the RPC server panel to show "Running".
3. Call `get_freecad_status` to confirm connectivity before retrying work.

Do not retry hanging tool calls in a loop — that will not resolve a deadlock.

## `execute_code` as Escape Hatch

Use `execute_code` only for FreeCAD operations that have no dedicated MCP tool.
When you do use it:
- End every code path with `print("SUCCESS: ...")` or `print("ERROR: ...")` so the
  result can be parsed reliably.
- Keep the code minimal — do one thing and return a clear status string.
- Prefer dedicated tools even if `execute_code` would be shorter to write.

## Sketch Workflow Order

The four sketch tools must be called in exactly this order:

1. `create_datum_plane` — creates the reference plane
2. `create_sketch_on_plane` — attaches a sketch to that plane
3. `add_contour_to_sketch` — draws the 2-D profile with constraints
4. `extrude_sketch_bidirectional` — produces the 3-D solid

Never skip or reorder these steps. In particular, do not call `add_contour_to_sketch`
before `create_sketch_on_plane` — the sketch object must exist first.

## Object Names Are Case-Sensitive

`"BasePlate"` and `"baseplate"` are different objects in FreeCAD.
Always use `get_objects(doc_name)` to confirm the exact internal name before
referencing any object in a tool call. Copy-paste names rather than retyping them.
