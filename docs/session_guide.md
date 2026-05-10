# FreeCAD MCP Session Guide

Operational guide for any LLM or developer using the FreeCAD MCP server.
Tool-agnostic — applies to Claude Code, OpenCode, or any MCP client.

---

## Session Startup

Always call `get_freecad_status` as the first tool in any session.

If it fails or does not respond:
- Open FreeCAD and confirm the FreeCADMCP addon is loaded (Tools → Addon Manager).
- Check the RPC server panel inside FreeCAD — it must show "Running" with a port number.
- Only after `get_freecad_status` succeeds should any other tool be called.

After confirming status:
- Call `list_documents` to see what is already open.
- If continuing prior work, use `load_document(path)` to restore the `.FCStd` file.
- If starting fresh, use `create_document(name)`.

---

## Choosing a Workflow

| Goal | Recommended approach |
|------|---------------------|
| Part that needs editing or re-parameterising later | Sketch workflow: `create_datum_plane` → `create_sketch_on_plane` → `add_contour_to_sketch` → `extrude_sketch_bidirectional` |
| Quick solid for testing, FEM, or boolean source | Part primitives: `create_object` with `Part::Box`, `Part::Cylinder`, etc. |
| Combining, subtracting, or intersecting solids | Boolean ops: `boolean_union`, `boolean_cut`, `boolean_intersection` |
| Dimensioned 2D drawing output | TechDraw: `create_techdraw_page` → `add_view_to_techdraw_page` |
| Design driven by named parameters | Spreadsheet: `spreadsheet_write` cells → `execute_code` to link with `setExpression` |
| Operation not covered by any dedicated tool | `execute_code` — last resort only |

Never reach for `execute_code` when a dedicated tool exists.

---

## Sketch Workflow — Required Order

The four sketch tools must be called in exactly this order:

1. `create_datum_plane(doc_name, plane_name, alignment, offset)` — creates the reference plane
2. `create_sketch_on_plane(doc_name, plane_name)` — attaches a sketch to that plane
3. `add_contour_to_sketch(doc_name, sketch_name, geometry_elements, ...)` — draws the 2-D profile
4. `extrude_sketch_bidirectional(doc_name, sketch_name, length_forward, ...)` — produces the 3-D solid

Do not skip or reorder steps. The sketch object must exist before adding contours, and the sketch must be inside a Body (which `create_datum_plane` creates automatically) before extruding.

---

## Geometry Verification Before Fillets and Chamfers

Call `get_shape_topology(doc_name, obj_name)` before every `add_fillet` or `add_chamfer`.

Face and edge names (`"Face3"`, `"Edge7"`) are assigned dynamically by FreeCAD's topology engine. They are not predictable from object shape alone and change after boolean operations. Always query topology first; never guess face or edge names.

---

## Saving Work

FreeCAD does not auto-save. Call `save_document(doc_name, path)` after any significant progress. For a new document always supply an explicit path ending in `.FCStd`.

---

## Object Names Are Case-Sensitive

`"BasePlate"` and `"baseplate"` are different objects in FreeCAD. Always use `get_objects(doc_name)` to confirm the exact internal name before referencing any object. Copy-paste names rather than retyping them.

---

## `execute_code` Usage

Use `execute_code` only for FreeCAD operations that have no dedicated MCP tool.

When using it:
- End every code path with `print("SUCCESS: ...")` or `print("ERROR: ...")` so the result can be parsed reliably. `print()` output IS captured; `FreeCAD.Console.PrintMessage()` is NOT.
- Keep the code minimal — do one thing, return a clear status string.
- Import FreeCAD modules inside the code string — the exec sandbox has `FreeCAD` and `FreeCADGui` pre-imported, but workbench modules (`Part`, `Sketcher`, `Draft`) must be imported explicitly.
- Always call `doc.recompute()` after making changes to the document.

---

## If the RPC Server Stops Responding

The FreeCAD Qt GUI queue may be deadlocked. Symptoms: tool calls hang or time out, `get_freecad_status` does not return.

Recovery:
1. Restart FreeCAD completely.
2. Wait for the RPC server panel to show "Running".
3. Call `get_freecad_status` to confirm connectivity before retrying.

Do not retry hanging tool calls in a loop — that will not resolve a deadlock.

---

## Debugging with Logs

Three log files cover the full stack. Consult them when a tool fails unexpectedly.

### FreeCAD addon log — XML-RPC activity
**Default path**: `/home/dfurlong/freecad_mcp.log`  
(Configurable via FreeCAD MCP panel — enable logging and set path. Default if blank: `~/.local/share/FreeCAD/freecad_mcp.log`)

**Contains**: Every RPC call — method name, parameters (truncated to 120 chars), elapsed time in seconds, and success or error outcome. Also captures GUI task exceptions.

**Use it to answer**: Did the call reach FreeCAD? What did FreeCAD return? How long did the operation take?

Example lines:
```
2026-05-09 14:46:01,234 DEBUG    RPC → execute_code ['import FreeCAD…[312 chars]']
2026-05-09 14:46:01,891 DEBUG    RPC ← execute_code OK (0.66s)
2026-05-09 14:47:03,100 WARNING  RPC ← get_objects FAIL (0.02s): Document 'Test' not found
```

### MCP server log — tool layer activity
**Path**: stdout of the `freecad-mcp` process (captured by Claude Desktop, OpenCode, or your MCP client's log)

**Contains**: Each MCP tool call entry with parameters, duration, and whether a screenshot was included in the response.

**Use it to answer**: Which MCP tool was called, with what arguments? How long did the full round-trip take?

### RAG server log — knowledge search activity
**Path**: `/home/dfurlong/git/freecad-rag/mcp_server.log`

**Contains**: Every `search_freecad_docs` query, the source filter applied, and the Ollama rewriting/reranking HTTP calls.

**Use it to answer**: What query terms reached the RAG? Why did the search return irrelevant results?

Example lines:
```
2026-05-06 18:59:08,411 INFO  Search: 'PartDesign body sketcher pad'  filter=FreeCAD-MCP
2026-05-06 18:59:09,090 INFO  HTTP Request: POST http://localhost:11434/api/chat "HTTP/1.1 200 OK"
```
