# FreeCAD MCP — Errors and Workarounds

Indexed by error symptom. For each error: what caused it, how to fix it, and which log to check.

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
