# Assembly Tools — Integration Test Plan

Assembly3 and Assembly4 are **mutually exclusive workbenches** — test each separately in its own document.
Last updated: 2026-05-10

All assembly tools are currently ⏳ Untested. These tools have addon dependencies (Assembly3 / Assembly4 must be installed).

---

## Prerequisites

Before running assembly tests, verify addons are installed:
```python
# Check Assembly3
try:
    import asm3
    print("Assembly3 available")
except ImportError:
    print("Assembly3 NOT installed")

# Check Assembly4
try:
    import Asm4
    print("Assembly4 available")
except ImportError:
    print("Assembly4 NOT installed")
```

---

## Assembly3

### 1. `create_assembly3`
- **Signature**: `create_assembly3(doc_name, assembly_name)`
- **Test**: Create an Assembly3 container in a document
- **Known**: ⏳ Untested

### 2. `add_part_to_assembly3`
- **Test cases**:
  - Add a `Part::Box` that exists in the same document
  - Add a part from an external `.FCStd` file (linked part)
- **Known**: ⏳ Untested

### 3. `add_assembly3_constraint`
- **Constraint types to test**:

| Constraint | Test setup | Status |
|-----------|-----------|--------|
| `PlaneCoincident` | Align top face of Part1 to bottom face of Part2 | ⏳ Untested |
| `Axial` | Align cylinder axis to hole axis | ⏳ Untested |
| `PointsCoincident` | Align two vertices | ⏳ Untested |
| `PointOnLine` | Constrain point to lie on edge | ⏳ Untested |
| `PointOnPlane` | Constrain point to lie on face | ⏳ Untested |
| `Lock` | Fix a part in place | ⏳ Untested |

### 4. `solve_assembly3`
- **Test**: After adding PlaneCoincident constraint, solve should move parts into position
- **Validate**: Part positions change after solve
- **Known**: ⏳ Untested

### 5. `list_assembly3_constraints`
- **Test**: After adding 2+ constraints, list should return all
- **Known**: ⏳ Untested

### 6. `delete_assembly3_constraint`
- **Test**: Add constraint, list to get name, delete, list again to confirm removed
- **Known**: ⏳ Untested

### 7. `modify_assembly3_constraint`
- **Test**: Add Distance constraint with value 50, modify to 100, solve, verify spacing changed
- **Known**: ⏳ Untested

### Full Assembly3 workflow (Scenario D)
1. `create_document("Asm3Test")`
2. Create 2 `Part::Box` objects
3. `create_assembly3("Asm3Test", "Assembly")`
4. `add_part_to_assembly3` × 2
5. `add_assembly3_constraint` — PlaneCoincident between top of Box1 and bottom of Box2
6. `solve_assembly3`
7. `get_view("Isometric")` — verify stacked arrangement
8. `export_assembly("Asm3Test", "Assembly", "/tmp/asm3_test.step", "step")`

---

## Assembly4

### 8. `create_assembly4`
- **Signature**: `create_assembly4(doc_name, assembly_name)`
- **Test**: Create an Assembly4 container
- **Known**: ⏳ Untested

### 9. `create_lcs_assembly4`
- **Test**: Create a Local Coordinate System inside the assembly
- **Known**: ⏳ Untested

### 10. `insert_part_assembly4`
- **Test**: Insert an external `.FCStd` part into the assembly
- **Requires**: An external part file on disk
- **Known**: ⏳ Untested

### 11. `attach_lcs_to_geometry`
- **Test matrix**:

| `map_mode` | Target | Status |
|-----------|--------|--------|
| `FlatFace` | Face of inserted part | ⏳ Untested |
| `NormalToEdge` | Edge of inserted part | ⏳ Untested |

- **Known**: ⏳ Untested

### 12. `list_assembly4_lcs`
- **Test**: After creating 2+ LCS objects, list should return all names
- **Known**: ⏳ Untested

### 13. `delete_lcs_assembly4`
- **Test**: Create LCS, list, delete, list again to confirm removed
- **Known**: ⏳ Untested

### 14. `modify_lcs_assembly4`
- **Test**: Create LCS, modify its offset, verify placement changed
- **Known**: ⏳ Untested

---

## Shared Assembly Tools

### 15. `list_assembly_parts`
- **Signature**: `list_assembly_parts(doc_name, assembly_name, assembly_type)`
- **Test**: After adding 2 parts to an assembly, list should return both
- **Test both**: `assembly_type="assembly3"` and `assembly_type="assembly4"`
- **Known**: ⏳ Untested

### 16. `export_assembly`
- **Signature**: `export_assembly(doc_name, assembly_name, path, format)`
- **Test**: Export assembled parts to STEP
- **Formats to test**: `step`, `iges`, `stl`
- **Known**: ⏳ Untested

### 17. `generate_bom`
- **Signature**: `generate_bom(doc_name, assembly_name, output_format)`
- **Test matrix**:

| Format | Validation | Status |
|--------|-----------|--------|
| `json` | Parse returned JSON, verify part names and counts | ⏳ Untested |
| `csv` | Verify comma-separated rows with header | ⏳ Untested |
| `markdown` | Verify markdown table format | ⏳ Untested |

### 18. `get_assembly_properties`
- **Signature**: `get_assembly_properties(doc_name, assembly_name)`
- **Returns**: mass, centre of mass, bounding box
- **Test**: Create assembly with known parts, verify mass = sum of parts
- **Known**: ⏳ Untested
- **Note**: Replaces the removed `calculate_assembly_mass` tool — mass is included in this response
