# FreeCAD API Gotchas

Behaviours that differ from what you would expect from the FreeCAD documentation or from general Python intuition. Each entry describes the wrong approach, the right approach, and why.

---

## PartDesign Pad: use `Profile`, not `Sketch`

**Wrong**: `pad.Sketch = sketch_obj`  
**Right**: `pad.Profile = sketch_obj`

The `Sketch` property existed in older FreeCAD versions and is now deprecated. Using it silently does nothing in FreeCAD 1.x — the pad will not extrude. `Profile` is the correct property name.

---

## Object Visibility: use `ViewObject`, not the object directly

**Wrong**: `obj.Visibility = False`  
**Right**: `obj.ViewObject.Visibility = False`

`Visibility` does not exist on `DocumentObject`. Setting it either creates a spurious custom property or raises `AttributeError`. Visibility is a view-layer property and lives on `obj.ViewObject`.

---

## BSplineCurve: use `.interpolate()`, not constructor arguments

**Wrong**: `Part.BSplineCurve([v1, v2, v3], ...)` — raises `TypeError`  
**Right**:
```python
spline = Part.BSplineCurve()
spline.interpolate([v1, v2, v3])
```

The `BSplineCurve` constructor does not accept point lists as positional arguments. Create the object first, then call `.interpolate()` with a list of `FreeCAD.Vector` instances.

---

## Arc Angles: radians, not degrees

`Part.ArcOfCircle(circle, start, end)` expects `start` and `end` in **radians**.

```python
import math
arc = Part.ArcOfCircle(circle, math.radians(0), math.radians(180))
```

Passing degrees (e.g. `0`, `90`, `180`) produces arcs at wrong angles with no error.

---

## `print()` is captured; `FreeCAD.Console.PrintMessage()` is not

In `execute_code`, the exec sandbox captures `sys.stdout`. `print("hello")` appears in the tool response. `FreeCAD.Console.PrintMessage("hello")` writes to FreeCAD's internal console but is not captured and will not appear in the response.

Pattern for reliable output:
```python
print("SUCCESS: created Box with volume 125000")
# or
print("ERROR: object 'Box' not found")
```

Use `raise Exception("message")` for errors — exceptions are always captured.

---

## Chamfer edges: 3-tuple, not 2-tuple

**Wrong**: `chamfer.Edges = [(0, 3.0), (1, 3.0)]`  
**Right**: `chamfer.Edges = [(0, 3.0, 3.0), (1, 3.0, 3.0)]`

`Part::Chamfer.Edges` expects `(edge_index, dist1, dist2)` 3-tuples. Passing 2-tuples silently produces incorrect results.

---

## Shell (Thickness) faces: name strings, not integers

**Wrong**: `shell.Faces = [(obj, 0), (obj, 2)]`  
**Right**: `shell.Faces = [(obj, "Face1"), (obj, "Face3")]`

`Part::Thickness.Faces` expects a list of `(DocumentObject, subshape_name_string)` tuples. Integer indices are not accepted. Use `get_shape_topology` to get the correct face name strings before calling `shell_object`.

---

## Draft objects: use `execute_code`, not `create_object`

`create_object(doc_name, "Draft::Circle", ...)` fails — FreeCAD rejects Draft type strings in `doc.addObject()`.

Correct approach:
```python
# Inside execute_code:
import Draft
circle = Draft.makeCircle(radius=25)
doc.recompute()
print("SUCCESS: Draft circle created")
```

---

## PartDesign::Pad and Pocket Type values (FreeCAD 1.x)

FreeCAD 1.x uses **string enum values** for `pad.Type` and `pocket.Type`. Integer values silently do nothing or cause a silent no-op.

| String value | Meaning |
|---|---|
| `"Length"` | One direction, uses `pad.Length` |
| `"ThroughAll"` | Ignore length, cut/extrude to end of model |
| `"TwoSides"` | Both directions: `pad.Length` forward, `pad.Length2` backward |
| `"Symmetric"` | Equal both sides using `pad.Length` as total |

For bidirectional extrusion with explicit lengths, use `pad.Type = "TwoSides"`. For a symmetric pad, use `pad.Midplane = True` with `pad.Type = "Length"` (the `extrude_sketch_bidirectional` tool does this automatically).

---

## PartDesign Body scoping: fillet, chamfer, loft inside a Body

`Part::Fillet`, `Part::Chamfer`, and `Part::Loft` **cannot reference objects that live inside a `PartDesign::Body`**. Attempting to do so raises a scope error like:

```
Part::Fillet: Link(s) to object(s) 'Pad' go out of the allowed scope 'Body'
```

Use the PartDesign equivalents instead when the source object is inside a Body:

| Part:: type | PartDesign:: equivalent |
|---|---|
| `Part::Fillet` | `PartDesign::Fillet` |
| `Part::Chamfer` | `PartDesign::Chamfer` |
| `Part::Loft` | `PartDesign::AdditiveLoft` |

The `add_fillet`, `add_chamfer`, and `create_loft` MCP tools detect Body context automatically and switch to the correct type.

---

## PartDesign::Fillet / Chamfer Base: tuple, not list

**Wrong**: `fillet.Base = (obj, ["Edge1", "Edge2"])` — raises `AttributeError: 'list' object has no attribute 'Name'`  
**Right**: `fillet.Base = (obj, tuple(["Edge1", "Edge2"]))`

`PropertyLinkSub` expects the subname collection to be a `tuple` of strings, not a `list`. The error message is misleading — it appears to come from the wrong place but is caused by this type mismatch.

---

## Sketch AttachmentSupport: use 'Face1' subname, not ''

**Wrong**: `sketch.AttachmentSupport = [(datum_plane, '')]` — sketch attaches but has no proper face reference; silently broken in FreeCAD 1.x  
**Right**: `sketch.AttachmentSupport = [(datum_plane, 'Face1')]`

For `PartDesign::Plane` objects, the correct subname for `AttachmentSupport` is `'Face1'`. An empty string was accepted in earlier FreeCAD versions but causes the sketch to not properly adopt the plane's coordinate system in FreeCAD 1.x.

---

## Spreadsheet cell references in expressions

When linking a Box dimension to a spreadsheet cell via `setExpression`:
```python
box.setExpression("Length", "Params.A1")
```
The expression uses the **sheet's Name** (e.g. `"Params"`), not its label. After calling `setExpression`, always call `doc.recompute()` for the expression to evaluate.

---

## `copy_object` does not copy dependencies by default

`doc.copyObject(obj, False)` — the `False` means "do not recursively copy dependencies". If the object references others (e.g. a fillet referencing a box), the copy will have broken references. The MCP `copy_object` tool defaults to recursive copy (`True`) to avoid this.
