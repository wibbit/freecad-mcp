# Output Tools — Integration Test Plan

TechDraw (2D drawings), FEM analysis, and Spreadsheet parameter management.
Last updated: 2026-05-10

All tools in this file are currently ⏳ Untested.

---

## TechDraw

### 1. `create_techdraw_page`
- **Signature**: `create_techdraw_page(doc_name, page_name, template_path)`
- **Note**: Non-template pages require FreeCAD ≥ 1.0

#### Test cases

**Test 1 — Without template**:
1. Create doc + `Part::Box`
2. `create_techdraw_page(doc, "Page1", template_path="")`
3. Verify page object exists in doc (via `get_objects`)
4. Verify no crash on `doc.recompute()`

**Test 2 — With template**:
1. Same setup but provide a real SVG template path
2. Verify template object exists and `Template` property is set

**Edge case**: Non-existent template path (should error gracefully, not crash FreeCAD)

### 2. `add_view_to_techdraw_page`
- **Signature**: `add_view_to_techdraw_page(doc_name, page_name, obj_name, view_name, x, y, scale)`

#### Test sequence
1. `create_document`, create `Part::Box`
2. `create_techdraw_page`
3. `add_view_to_techdraw_page(doc, "Page1", "Box", view_name="Front", x=100, y=100, scale=0.5)`
4. `get_view` screenshot — verify page renders with projection visible

#### View names to test
| view_name | Expected projection | Status |
|-----------|-------------------|--------|
| `Front` | Front elevation | ⏳ Untested |
| `Top` | Plan view | ⏳ Untested |
| `Right` | Right elevation | ⏳ Untested |
| `Isometric` | Isometric projection | ⏳ Untested |

#### End-to-end scenario
See **Scenario F** in [INTEGRATION_TEST_PLAN.md](../INTEGRATION_TEST_PLAN.md):
1. Create doc + Box
2. Create TechDraw page
3. Add Front and Top views
4. Screenshot to verify rendered output

---

## FEM

### 3. `run_fem_analysis`
- **Signature**: `run_fem_analysis(doc_name, analysis_name, timeout)`
- **Requires**: CalculiX solver installed

Check CalculiX availability:
```python
import subprocess
result = subprocess.run(["ccx", "-v"], capture_output=True)
print("CalculiX available" if result.returncode == 0 else "NOT installed")
```

#### Full FEM test sequence (requires CalculiX)
1. `create_document("FEM_Test")`
2. `execute_code`: create `Part::Box` 100×100×100
3. `execute_code`: set up analysis container:
   ```python
   import ObjectsFem
   analysis = doc.addObject("Fem::FemAnalysis", "Analysis")
   mesh = doc.addObject("Fem::FemMeshGmsh", "FEMMesh")
   mesh.Part = box
   analysis.addObject(mesh)
   mat = ObjectsFem.makeMaterialSolid(doc, "Steel")
   analysis.addObject(mat)
   fixed = ObjectsFem.makeConstraintFixed(doc, "FixedBC")
   fixed.References = [(box, "Face1")]
   analysis.addObject(fixed)
   force = ObjectsFem.makeConstraintForce(doc, "Force")
   force.References = [(box, "Face6")]
   force.Force = 1000.0
   analysis.addObject(force)
   doc.recompute()
   ```
4. `run_fem_analysis("FEM_Test", "Analysis", timeout=120)`
5. Validate: result object exists in document, no error in response

#### Minimal smoke test (no solver needed)
1. Steps 1–3 only
2. `get_objects("FEM_Test")` — verify analysis setup objects all present
3. Do NOT call `run_fem_analysis` if CalculiX is not installed

---

## Spreadsheet

### 4. `spreadsheet_read`
- **Signature**: `spreadsheet_read(doc_name, sheet_name, cell_range)`
- **Requires**: `Spreadsheet::Sheet` object in the document (create via `execute_code`)

#### Test cases
- **Single cell**: Write "hello" to A1, read A1, verify "hello" returned
- **Numeric cell**: Write 42 to B2, read B2, verify number returned
- **Range**: Write values to A1:C3, read A1:C3, verify all 9 cells returned
- **Empty cell**: Read a cell that was never written (should return empty/None, not error)
- **Known**: ⏳ Untested

### 5. `spreadsheet_write`
- **Signature**: `spreadsheet_write(doc_name, sheet_name, cell, value)`

#### Test cases
- **String value**: Write "TestValue", read back, verify
- **Numeric value**: Write 123.45, read back, verify number (not string)
- **Overwrite**: Write A1=10, then A1=20, read back — verify 20
- **Known**: ⏳ Untested

### 6. Spreadsheet expressions and parametric link
- **Note**: This is the primary parametric design use case for spreadsheets.
- **Known**: ⏳ Untested

#### Test — expression-driven object
1. Create spreadsheet via `execute_code`:
   ```python
   sheet = doc.addObject("Spreadsheet::Sheet", "Params")
   doc.recompute()
   ```
2. `spreadsheet_write(doc, "Params", "A1", 100)` ← Width parameter
3. `spreadsheet_write(doc, "Params", "A2", 50)` ← Height parameter
4. `execute_code` — create Box with expressions:
   ```python
   box = doc.addObject("Part::Box", "ParamBox")
   box.setExpression("Length", "Params.A1")
   box.setExpression("Width", "Params.A2")
   box.Height = 30
   doc.recompute()
   ```
5. `measure_object` → verify volume = 100×50×30 = 150000 mm³
6. `spreadsheet_write(doc, "Params", "A1", 200)` ← Double the width
7. `execute_code`: `doc.recompute()`
8. `measure_object` → verify volume = 300000 mm³ (width doubled)

See also **Scenario G** in [INTEGRATION_TEST_PLAN.md](../INTEGRATION_TEST_PLAN.md).
