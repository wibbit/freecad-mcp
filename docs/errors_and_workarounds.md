# FreeCAD MCP — Errors and Workarounds

Indexed by error symptom. For each error: what caused it, how to fix it, and which log to check.

---

## `'bool' object is not subscriptable` from `get_objects` or `get_object`

**Tools**: `get_object`, `get_objects`  
**Cause**: A GUI task in the FreeCAD addon crashed before it could return a proper response dict. The RPC layer received a bare `False` (the exception-path sentinel) instead of `{"success": ..., "data": ...}`. The MCP client then tried to do `result["success"]` on a bool, raising this error.  
**Fix**: This was an internal bug; current versions wrap all GUI task results in a proper dict. If still seeing it, update the addon. Meanwhile, check the FreeCAD addon log for the underlying exception that caused the task to fail before returning.  
**Log to check**: FreeCAD addon log (`/home/dfurlong/freecad_mcp.log`) — look for `GUI task error:` immediately before the timestamp of the failing call.

---

## "string indices must be integers, not 'str'"

**Tools**: `get_object`, `get_objects`  
**Cause**: The FreeCAD addon's GUI task raised an exception while serializing the object (e.g. a ViewObject property that doesn't exist on that object type). The exception was caught and put into the response queue as a plain string. The MCP layer then tried to index into that string as a dict.  
**Fix**: Check the FreeCAD addon log for the underlying exception. If it says `AttributeError: 'NoneType' object has no attribute 'ShapeColor'` or similar, the serialize layer is failing on a specific object type.  
**Log to check**: FreeCAD addon log (`/home/dfurlong/freecad_mcp.log`) — look for `GUI task raised an exception` around the same timestamp.

---

## "Sketch is not in a Body"

**Tool**: `extrude_sketch_bidirectional`  
**Cause**: The sketch was created manually via `execute_code` and is not inside a `PartDesign::Body` container.  
**Fix**: Use the MCP sketch workflow — `create_datum_plane` creates a Body automatically, and `create_sketch_on_plane` places the sketch inside it. If you created a sketch manually, wrap it: `body.addObject(sketch)` before calling extrude.  
**Workaround**: Use `Part::Extrusion` via `execute_code` instead of PartDesign::Pad — it works on standalone sketches.

---

## "name 'constraints' is not defined"

**Tool**: `add_contour_to_sketch`  
**Cause**: The generated code string referenced the Python variable `constraints` inside the exec'd FreeCAD namespace, where it doesn't exist.  
**Status**: Fixed in current codebase — `n_con = len(constraints)` is now interpolated at code-generation time.  
**If still seeing this**: You are running an old version of the addon. Update `contour_builder.py`.

---

## Pydantic validation error

**Cause**: A required tool parameter was not supplied, or was supplied with the wrong type.  
**Common cases**:
- `create_loft` — `result_name` was previously required; now optional (auto-generated from sketch names).
- Any tool accepting `list[str]` — passing a comma-separated string instead of a JSON array.
- Any tool accepting `dict` — passing a JSON string instead of an object.  
**Fix**: Check the tool signature. Pass `sketch_names` as a JSON array `["s1", "s2"]`, not as a string.  
**Log to check**: MCP server stdout — the Pydantic error message names the offending parameter.

---

## "not a document object type" (Draft objects)

**Tool**: `create_object`  
**Cause**: `Draft::Circle`, `Draft::Rectangle`, `Draft::Wire` cannot be created via `doc.addObject()`. FreeCAD rejects these type strings.  
**Fix**: Use `execute_code` with the Draft Python API:
```python
import Draft
circle = Draft.makeCircle(radius=25)
doc.recompute()
print("SUCCESS: circle created")
```

---

## Tool call hangs / does not return

**Cause**: The FreeCAD Qt GUI queue is deadlocked. This can happen if a GUI operation raised an uncaught exception that left the queue in a bad state.  
**Fix**:
1. Do not retry in a loop.
2. Restart FreeCAD completely.
3. Confirm `get_freecad_status` succeeds before retrying.  
**Log to check**: FreeCAD addon log — look for `GUI task error:` entries just before the hang.

---

## Tool reports success but FreeCAD shows no change

**Cause**: `doc.recompute()` was either not called, or a dependent feature is in an error state. FreeCAD's recompute can silently skip features that have upstream errors.  
**Fix**: In `execute_code`, always end with `doc.recompute()`. After calling it, check `obj.State` — if it contains `"Invalid"`, the feature failed.  
**Log to check**: FreeCAD addon log — look for the `execute_code` RPC call and whether its response contained `ERROR:` in the output.

---

## Boolean operation produces empty or invalid shape

**Cause**: The two input objects do not actually overlap, or one of them has a degenerate shape.  
**Fix**:
1. Call `measure_object` on both inputs to confirm they have non-zero volume.
2. Call `get_shape_topology` to confirm both have a valid `Shape` field.
3. Use `get_view("Isometric")` to visually inspect the object positions before the operation.

---

## `get_shape_topology` returns empty faces/edges list

**Cause**: The object has not been recomputed, or it has no `Shape` attribute (e.g. it is a datum plane or spreadsheet).  
**Fix**: Call `execute_code` with `doc.recompute()` first. Confirm the object `TypeId` via `get_objects` — only `Part::Feature` and similar solid-producing types have a `Shape`.

---

## `NameError: name 'App' is not defined` in `execute_code`

**Tool**: Any tool that uses `execute_code` internally, or manual `execute_code` calls  
**Cause**: The exec sandbox previously only exposed `FreeCAD` and `FreeCADGui` as names. Standard FreeCAD scripting idioms use `App` and `Gui` as shorthand aliases, and code using those names raised `NameError`.  
**Fix**: `App` and `Gui` are now pre-injected into the sandbox alongside `FreeCAD`/`FreeCADGui`. If you still see this error, you are running an old version of the FreeCAD addon (`rpc_server.py`). Pull the latest addon code and restart FreeCAD.  
**Log to check**: FreeCAD addon log — look for `NameError` inside the `execute_code` entry.

---

## `Part::Fillet / Chamfer / Loft: Link(s) go out of allowed scope`

**Tools**: `add_fillet`, `add_chamfer`, `create_loft`  
**Symptom**: Error like `Part::Fillet: Link(s) to object(s) 'Pad' go out of the allowed scope 'MyBody'`  
**Cause**: `Part::Fillet`, `Part::Chamfer`, and `Part::Loft` are document-level objects and cannot reference objects that live inside a `PartDesign::Body`. FreeCAD's scope rules forbid the cross-boundary reference.  
**Fix**: Use `PartDesign::Fillet`, `PartDesign::Chamfer`, or `PartDesign::AdditiveLoft` instead, created via `body.newObject()`. The MCP tools `add_fillet`, `add_chamfer`, and `create_loft` detect Body context and switch automatically. If you see this error, ensure the source object is correctly inside the Body (`get_objects` → check the Body's Group list).  
**Log to check**: FreeCAD's main log (`/home/dfurlong/freecad_mcp.log`) — the scope error appears in the FreeCAD console, not in the MCP response.

---

## `'PartDesign.Feature' has no attribute 'Edges'` (fillet/chamfer)

**Tools**: `add_fillet`, `add_chamfer`  
**Cause**: `PropertyLinkSub` (the `Base` property of `PartDesign::Fillet`) requires the subname collection to be a **tuple**, not a list. Passing `(obj, ["Edge1", "Edge2"])` causes FreeCAD to try to iterate the list as though it were a single object and fails with a confusing attribute error.  
**Fix**: Pass `(obj, tuple(edge_names))`. The MCP tools handle this correctly. If using `execute_code` manually:  
```python
fillet.Base = (solid_obj, ("Edge1", "Edge2"))   # tuple, not list
```

---

## Sketch created on datum plane but has wrong orientation / no profile

**Tools**: `create_sketch_on_plane`, `create_sketch_in_body`  
**Cause**: `AttachmentSupport = [(plane, '')]` was accepted by older FreeCAD but silently broken in FreeCAD 1.x — the sketch exists but does not properly inherit the plane's coordinate system.  
**Fix**: Use `'Face1'` as the subname: `AttachmentSupport = [(plane, 'Face1')]`. Both MCP sketch creation tools use this form. If you created a sketch manually via `execute_code` with an empty subname, re-attach it:  
```python
sketch.AttachmentSupport = [(datum_plane, 'Face1')]
sketch.MapMode = 'FlatFace'
doc.recompute()
```

---

## `AttributeError: has no attribute 'getExpression'`

**Tool**: Any `execute_code` call that tries to read an expression off an object  
**Cause**: `getExpression()` does not exist on FreeCAD objects. Only `setExpression()` exists for writing.  
**Fix**: Read `obj.ExpressionEngine` — it is a list of `(property, expression)` tuples. See `api_gotchas.md` for usage.

---

## `AttributeError: 'App.Document' object has no attribute 'State'`

**Tool**: Any `execute_code` call that checks `doc.State`  
**Cause**: `State` is a property of `DocumentObject` (a Box, Sketch, Pad, etc.) — not of the `Document` itself.  
**Fix**: Call `obj.State` on a specific object, not on the document. Use `get_objects(doc_name)` to see `State` and `HasError` for all objects via the MCP layer.

---

## `TypeError: Invalid parameters: ('Radius', 0)` — Sketcher constraint

**Tool**: Any `execute_code` call adding Sketcher constraints  
**Cause**: `Sketcher.Constraint('Radius', edge_index)` is missing the required radius value as the third argument.  
**Fix**: `Sketcher.Constraint('Radius', edge_index, value_mm)`. Constraints that carry a numeric value (`Radius`, `Distance`, `DistanceX`, `DistanceY`, `Angle`) always require the value as the last positional argument.

---

## `AttributeError: 'Part.LineSegment' object has no attribute 'Length'`

**Tool**: Any `execute_code` call inspecting sketch geometry  
**Cause**: `Part.LineSegment` (a geometry primitive) uses lowercase `.length`, not `.Length`. The uppercase convention applies to FreeCAD `DocumentObject` properties (e.g. `box.Length`), not to raw geometry objects.  
**Fix**: Use `.length` (lowercase). Similarly, use `.startPoint` and `.endPoint` (camelCase) not `.StartPoint`.

---

## `RuntimeError: shape is invalid`

**Tool**: Any `execute_code` call that computes or uses a shape after a failed sketch  
**Cause**: The sketch was not properly solved — constraints are contradictory, over-determined, or the profile is not closed. A common trigger is a malformed Sketcher constraint (wrong argument count — see above).  
**Fix**:
1. Call `get_objects(doc_name)` and check `HasError` on the sketch object.
2. Use `undo` to roll back the bad constraint.
3. Fix the constraint and re-add it.
4. Confirm the sketch is solved (no `HasError`) before retrying the 3D feature.  
**Log to check**: FreeCAD addon log — look for the constraint or geometry error that preceded the `shape is invalid` line.

---

## `PartDesign::Fillet` fails silently on multi-solid Body compound

**Tools**: `add_fillet` (Body context), manual `execute_code`  
**Symptom**: `add_fillet` completes but the result has `HasError: true`, or the fillet shape looks wrong/missing.  
**Cause**: `PartDesign::Fillet` expects the Body tip to be a single, well-formed solid. If the Body contains a multi-solid compound (from a merge or a boolean that produced disjoint geometry), the fillet operation fails.  
**Fix**: Use shape-level filleting via `execute_code` instead:
```python
import Part
solid = doc.getObject('MyPad')
edges = [solid.Shape.Edges[i] for i in edge_indices]  # from get_shape_topology
result = solid.Shape.makeFillet(radius, edges)
out = doc.addObject('Part::Feature', 'FilletResult')
out.Shape = result
doc.recompute()
```
This bypasses PartDesign's feature tree and works directly on the shape. The result is a `Part::Feature` outside the Body.  
**Log to check**: FreeCAD addon log — look for the fillet object's `State` in the response, or call `get_freecad_errors` to see the recompute error.

---

## `PartDesign::SubtractiveLoft` fails for conical flare geometry

**Tool**: Any SubtractiveLoft call targeting a simple conical flare  
**Symptom**: Solver error during recompute, or the subtracted shape is geometrically wrong.  
**Cause**: `PartDesign::SubtractiveLoft` uses FreeCAD's loft solver, which can fail for degenerate or nearly-straight loft paths. A simple expanding circle (cone) is such a degenerate case.  
**Fix**: Use `Part::Cone` as a cutter with `boolean_cut`:
```python
# Create a cone positioned to cover the flare volume
cone = doc.addObject('Part::Cone', 'FlareCutter')
cone.Radius1 = inner_radius
cone.Radius2 = outer_radius
cone.Height = flare_depth
cone.Placement = App.Placement(App.Vector(x, y, z), App.Rotation())
doc.recompute()
# Then subtract it from the main solid
```
Pass `cone.Name` as the tool in `boolean_cut`. The boolean-based approach is more robust than the loft solver for axially symmetric geometry.  
**Log to check**: FreeCAD addon log — look for the SubtractiveLoft recompute error in the Report View via `get_freecad_errors`.

---

## `execute_code` `print()` output not captured (flatpak installations)

**Tool**: `execute_code`  
**Symptom**: Code runs without error, but the response `data.output` is empty even though the code contained `print()` calls.  
**Cause**: FreeCAD installed as a flatpak runs in a sandboxed environment where `sys.stdout` may not be the same file descriptor captured by the RPC server. `print()` output goes to the sandboxed process's stdout rather than being returned in the response.  
**Detection**: run `execute_code("print('HELLO')")` — if `"HELLO"` is absent from the response, stdout is not captured.  
**Fix**:
- Use `raise Exception("result: " + str(value))` for output that must be returned — exceptions are always captured.
- Call `get_freecad_errors` after the code runs; FreeCAD's Report View may contain output written via `FreeCAD.Console.PrintMessage`.
- Check the addon log (`freecad_mcp.log`) for the full execute_code response.

---

## Accessing FreeCAD Errors Without Copy-Paste

Use the `get_freecad_errors` MCP tool to read the Report View panel directly. It returns filtered error and warning lines without requiring you to switch to FreeCAD and copy-paste.

```json
{ "tool": "get_freecad_errors", "max_lines": 100 }
```

Call this first whenever a tool behaves unexpectedly. The Report View captures errors from recomputes, constraint failures, and `execute_code` tracebacks that are not surfaced in the MCP response. Requires the Report View panel to be open (View → Panels → Report View).

When `execute_code` raises an exception, the full traceback is also written to `freecad_mcp.log` — see below for how to read that log efficiently.

---

## How to Read the Addon Log Efficiently

The FreeCAD addon log (`/home/dfurlong/freecad_mcp.log`) is the most useful debugging tool. Key patterns to `grep` for:

```bash
# See all failures
grep "FAIL\|ERROR\|exception" /home/dfurlong/freecad_mcp.log

# See calls in the last 5 minutes
grep "$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M')" /home/dfurlong/freecad_mcp.log

# See all calls to a specific method
grep "RPC → execute_code" /home/dfurlong/freecad_mcp.log
```

Each RPC line shows method name, truncated params (120 chars max), elapsed time, and OK/FAIL status. If a call failed, the next line shows the error message returned by FreeCAD.
