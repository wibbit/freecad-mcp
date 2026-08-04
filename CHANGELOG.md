# Changelog

All notable changes to FreeCAD MCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-08-02

### 🔄 Changed

- **Repointed at Codeberg** — package URLs, clone commands and issue links now reference
  [codeberg.org/wibbit/freecad-mcp](https://codeberg.org/wibbit/freecad-mcp), which is now the
  project's canonical home.
- **GitHub converted to a push mirror** — `github.com/wibbit/freecad-mcp` now carries the same
  `main`, with issues and the wiki disabled and its description and homepage pointing at
  Codeberg. Its previous branch history was a rewritten duplicate of the upstream project
  (byte-identical tree, no unique content) and was replaced.
- **Authorship corrected** — `pyproject.toml` named the upstream author and pointed all five
  project URLs at upstream's repository. Now names the maintainer and this project's URLs.
- **Client-neutral documentation** — docs described Claude Desktop as the only supported
  client. They now cover Claude Code (CLI) as well; Desktop instructions are retained
  unchanged for Desktop users.
- **`CONTRIBUTING.md` testing instructions corrected** — they predated the pytest suite and
  told contributors to run test files directly with `python`.
- **Merged integration branches removed** — `pr-25`, `pr-38`, `pr-39` and `integrated` were
  local-only refs, never published. Their work has been in `main` since 2026-05-08 and the
  merge commits that brought it in remain in history, so nothing was lost.

### ✨ Added

- **README feature overview** — capability groups covering documents, sketching, solid
  modelling, booleans, assembly, FEM, TechDraw, import/export, inspection and spreadsheets.
- **README "Origins" section** — credits Shirokuma (k tanaka), links the upstream project,
  and states that this project is independently maintained and unaffiliated.
- **Flatpak addon path** — `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/`, previously
  undocumented despite being a common Linux install route.
- **`tests/test_project_metadata.py`** — guards branding, attribution and licensing
  invariants. Runs without FreeCAD.
- **`./check` test wrapper** — runs `uv run --extra dev python -m pytest` from the repo root
  and passes any arguments straight through, so the suite behaves the same from any working
  directory. `--extra dev` resolves pytest from the project's declared dev dependency. Note
  that a bare `./check` exercises the integration suite against a running FreeCAD.
- **Vision proxy tracked** — `freecad-mcp-proxy.py` and its TODO are now in version control.
- **`CONTRIBUTING.md` troubleshooting section** — covers `uv run --extra dev pytest` failing to
  spawn when the console script is missing from `.venv/bin/`, including the detail that
  `uv sync` reports "no changes" because it verifies packages rather than their scripts, and
  that `--reinstall-package pytest` is the repair.
- **Repository published on Codeberg** — the project is now live at
  [codeberg.org/wibbit/freecad-mcp](https://codeberg.org/wibbit/freecad-mcp), with its full
  commit history.
- **In-server vision summary** — `--vision-summary` replaces viewport screenshots with a short text
  description from a local Ollama vision model, saving roughly 2,000-5,000 tokens per call.
  `--vision-model` and `--vision-url` configure it; `execute_code` and `get_view` take an optional
  `vision_prompt` for per-call questions. Off by default. Replaces the standalone
  `freecad-mcp-proxy.py`, which is removed.

### 🐛 Fixed

- **`get_view` ignored `--only-text-feedback`** — it constructed its image response directly rather
  than going through the shared screenshot helper, so it returned a full base64 screenshot even when
  the user had asked for text-only output. All screenshot paths now route through one place.
- **Misleading badges removed** — the MseeP security-assessment badge and the `contrib.rocks`
  contributor image both described upstream's repository, not this one.
- **Install instructions installed the wrong package** — the documented `uvx freecad-mcp`
  resolves on PyPI to an unrelated package. This project is not published to PyPI, so every
  documented invocation now uses
  `uvx --from git+https://codeberg.org/wibbit/freecad-mcp freecad-mcp`.
- **`mcp` dependency capped below 2.0** — `mcp[cli]>=1.12.2` had no upper bound, so a fresh
  install resolved to `mcp` 2.0.0, which no longer provides `mcp.server.fastmcp` and made the
  server fail at import with `ModuleNotFoundError`. Now `mcp[cli]>=1.12.2,<2.0.0`.
- **Development setup omitted the dev dependencies** — `CONTRIBUTING.md` told contributors to
  run `pip install -e .`, which skips the `dev` extra. Anyone following the setup steps in
  order therefore had no pytest, pylint, black or mypy when they reached the test and lint
  commands given later on the same page. Now `uv sync --extra dev`, with the pip equivalent
  `pip install -e ".[dev]"` noted for those who prefer it.

---

## [Unreleased] - 2026-05-12

### 🐛 Fixed

- **RPC queue corruption** — The primary cause of `'bool' object is not subscriptable` on `get_objects`, `spreadsheet_write`, `save_document`, and most other non-`execute_code` tools. Root cause: `get_active_screenshot` in the MCP client made a redundant `execute_code` RPC call to check view support before the real screenshot call. If that check took longer than `TIMEOUT` seconds (common in flatpak), its result was orphaned on `rpc_response_queue` and picked up by the next unrelated RPC call. Fixed by:
  1. Removing the redundant client-side `execute_code` check from `freecad_client.get_active_screenshot` — the server-side `get_active_screenshot` handler already performs the view check internally.
  2. Adding `_run_gui()` helper to `FreeCADRPC` that drains any stale responses from `rpc_response_queue` before each new dispatch, preventing corruption from any future timeout scenario.
  3. All 20 RPC handler methods now use `_run_gui()` instead of the bare `rpc_request_queue.put / rpc_response_queue.get` pattern.
- **`TIMEOUT` increased from 10s to 30s** — 10 seconds was insufficient for FreeCAD running in a flatpak sandbox, where recomputes and GUI operations run measurably slower. 30 seconds is still responsive enough to detect real GUI deadlocks.

### 🔧 Enhanced

- **`get_active_screenshot` server-side** — Merged the redundant view-check sub-call into the main capture flow. The view check and screenshot capture are now two sequential `_run_gui` dispatches within the same RPC method, not two separate XML-RPC calls.

---

## [Unreleased] - 2026-05-11

### ✨ Added

- **`get_freecad_errors`** — New MCP tool that reads FreeCAD's Report View panel content, returning error and warning lines without requiring copy-paste. Requires the Report View panel to be open in FreeCAD (View → Panels → Report View). Accepts `max_lines` parameter (default 200).

### 🔧 Enhanced

- **`execute_code` logging** — When `execute_code` raises an exception, the full traceback and the first 500 characters of the offending code are now written to the addon log file (`freecad_mcp.log`), not only to FreeCAD's internal console. Requires FreeCAD restart to take effect.

### 📚 Documentation

- `docs/api_gotchas.md` — Added five new entries from live agent errors: `getExpression` vs `ExpressionEngine`, `Document.State` vs `DocumentObject.State`, Sketcher `Constraint('Radius', ...)` argument order, `Part.LineSegment.length` case sensitivity, `RuntimeError: shape is invalid` diagnosis. Expanded `Pad.Profile` entry with `PropertyLinkSub` tuple form and FreeCAD 1.0 context. Added three new entries: `PartDesign::Fillet` failure on multi-solid Body compound, `PartDesign::SubtractiveLoft` failure for conical flare geometry, and `execute_code` stdout not captured in flatpak installations.
- `docs/errors_and_workarounds.md` — Matching error entries for all five. Added `get_freecad_errors` reference in the log-reading section. Added three new entries: `'bool' object is not subscriptable` from get_objects, PartDesign::Fillet silent failure on compound, SubtractiveLoft conical flare workaround, and flatpak stdout capture issue.
- `docs/API_REFERENCE.md` — Added `get_freecad_errors` under new Debugging section.
- `docs/session_guide.md` — Added "Reading FreeCAD Errors" section: when to call `get_freecad_errors`, prerequisites, and how it relates to log files.
- `tests/test_plans/core.md` — Added section 4.5 `get_freecad_errors` with test cases and edge conditions.
- `tests/test_basic_operations.py` — Added `test_get_freecad_errors`: triggers a sentinel error via `execute_code`, then confirms it appears in Report View output.

---

## [Unreleased] - 2026-05-10

### ✨ Added

- **`groove`** — PartDesign::Groove (subtractive revolve). Axis choices: `H_Axis`, `V_Axis`, `X_Axis`, `Y_Axis`, `Z_Axis`. Configurable angle (default 360°). Result name defaults to `{sketch_name}_groove`.
- **`rename_object`** — Change the display label of any document object (FreeCAD's internal Name is immutable; this sets `obj.Label`).
- **`close_document`** — Close a document by name, with optional save-before-close.
- **`import_step`** — Import STEP or STL files into an open document via `Part.insert` / `Mesh.insert`. Assigns a label to the first imported object.
- **`add_techdraw_dimension`** — Add a dimension annotation to a TechDraw view. Supports `DistanceX`, `DistanceY`, `Distance`, `Radius`, `Diameter`, `Angle` types. Requires an existing page and view.
- **`pocket_sketch`** — PartDesign::Pocket (new dedicated tool, was previously absent). Supports fixed depth, two-sided, through-all, and symmetric modes.
- **`add_datum_plane_to_body`** — Add a `PartDesign::Plane` to an existing Body at a specified alignment and offset.
- **`create_sketch_in_body`** — Create a sketch inside an existing Body on a named datum plane.

### 🔧 Enhanced

- **`extrude_sketch_bidirectional`** — Added `taper_angle`, `taper_angle2` (draft angle), and `reversed` parameters. All FreeCAD 1.0 string enum `pad.Type` values (`"Length"`, `"TwoSides"`) used throughout.
- **`add_fillet`** / **`add_chamfer`** — Now detect PartDesign Body context and automatically use `PartDesign::Fillet` / `PartDesign::Chamfer` (via `body.newObject()`) instead of `Part::Fillet` / `Part::Chamfer`. Fixes scope errors when the source object is inside a Body.
- **`create_loft`** — Now detects PartDesign Body context and uses `PartDesign::AdditiveLoft` instead of `Part::Loft`. Fixes scope errors in Body workflows.
- **`get_objects`** / **`get_object`** — Response now includes `State` (e.g. `["Up-to-date"]`, `["Invalid"]`) and `HasError` (boolean) for every object, surfacing the exclamation-mark error indicator visible in FreeCAD's model tree.

### 🐛 Fixed

- **`execute_code` sandbox** — `App` and `Gui` are now pre-injected as aliases for `FreeCAD` and `FreeCADGui`. Standard FreeCAD scripting idioms using `App.getDocument()` etc. previously raised `NameError`.
- **`create_sketch_on_plane`** / **`create_sketch_in_body`** — `AttachmentSupport` now uses `'Face1'` subname instead of `''`. Empty subname was silently broken in FreeCAD 1.x, causing sketches to not properly inherit the datum plane's coordinate system.
- **`pocket_sketch`** — `pocket.Type` now uses string enums (`"Dimension"`, `"ThroughAll"`, `"TwoSides"`) instead of integers. Integer values were a FreeCAD 0.x-ism; FreeCAD 1.x silently ignored them.
- **`extrude_sketch_bidirectional`** — `pad.Type` now uses string enums (same fix as pocket).
- **`create_datum_plane`** — Plane now created via `body.newObject()` instead of `doc.addObject()`. The old approach did not properly add the plane to the Body's feature tree.
- **`serialize_shape`** — Now handles invalid/unrecomputed shapes that raise on `.Volume` or `.Area` access. Returns `{"BoundBox": ..., "invalid": True}` instead of crashing `get_objects`.

### 📚 Documentation

- `docs/api_gotchas.md` — Updated `PartDesign::Pad Type values` from integer to string enum table; added four new gotchas: PartDesign Body scoping, `PropertyLinkSub` tuple requirement, `AttachmentSupport 'Face1'` subname, and `Pocket.Type` string enums.
- `docs/errors_and_workarounds.md` — Added four new error entries: `NameError: name 'App'`, scope errors for fillet/chamfer/loft in Body, `'PartDesign.Feature' has no attribute 'Edges'`, and sketch orientation silent failure.
- `tests/test_plans/sketch_workflow.md` — Added test cases for all new sketch tools and parameters.
- `tests/INTEGRATION_TEST_PLAN.md` — Added bugs 11–16 to Known Bugs table.

---

## [3.0.0] - 2025-10-09 - Corsair Edition

### 🎊 Major Release: Complete CAD Workflow

This release transforms FreeCAD MCP into a professional-grade CAD automation tool with 52 total MCP tools and complete workflow support for complex projects like aircraft modeling.

### ✨ Added - Advanced Modeling (10 new tools)

#### Finishing Operations
- **`add_fillet_tool`** - Add rounded edges (fillets) to objects
  - Support for multiple edges
  - Configurable radius
  - Automatic result naming
  
- **`add_chamfer_tool`** - Add beveled edges (chamfers) to objects
  - Support for multiple edges
  - Configurable distance
  - Professional edge finishing

- **`shell_object_tool`** - Create hollow shells from solid objects
  - Configurable wall thickness
  - Selective face removal
  - Perfect for enclosures and containers

#### Transformation & Pattern Operations
- **`mirror_object_tool`** - Mirror objects across planes
  - Arbitrary plane definition
  - Optional merge with original
  - Essential for symmetric designs (60% time saving)

- **`circular_pattern_tool`** - Create circular arrays (polar patterns)
  - Configurable count and angle
  - Perfect for radial engines, bolt patterns
  - Automatic fusion of instances

- **`linear_pattern_tool`** - Create linear arrays (rectangular patterns)
  - Configurable direction and spacing
  - Ideal for repeated features
  - Automatic fusion of instances

#### Reference Geometry
- **`create_reference_plane_tool`** - Create datum planes
  - Multiple definition modes: offset, 3-points, point-normal
  - Essential for complex assemblies
  - Support for angled planes

- **`create_reference_axis_tool`** - Create datum axes
  - Point and direction definition
  - Reference for revolutions and patterns
  - Essential for rotational features

#### CAD Import & Profiles
- **`import_airfoil_profile_tool`** - Import NACA airfoil profiles
  - NACA 4-digit and 5-digit series support
  - Configurable chord length
  - Automatic profile calculation
  - Perfect for aircraft wing design

- **`import_dxf_tool`** - Import DXF files into sketches
  - Full 2D geometry support
  - Configurable scale
  - Professional CAD workflow integration

### 🔧 Enhanced - Sketch Workflow (Added 2025-10-08)

#### Datum Plane System
- **`create_datum_plane_tool`** - Foundation for sketch-based modeling
  - Alignment: XY, XZ, YZ
  - Configurable offset
  - Creates Body with Origin

#### Sketch Management
- **`create_sketch_on_plane_tool`** - Attach sketches to datum planes
  - Automatic naming convention
  - Inherits plane coordinate system
  - Part Design workflow compatible

- **`add_contour_to_sketch_tool`** - Build complex 2D profiles
  - Geometry: lines, arcs, circles, bsplines, ellipses
  - Constraints: coincident, tangent, distance, angle, fix
  - Automatic point-to-origin constraint

#### 3D Solid Creation
- **`extrude_sketch_bidirectional_tool`** - Create 3D solids from sketches
  - Bidirectional extrusion
  - Symmetric (midplane) mode
  - Automatic solid naming

#### Positioning
- **`attach_solid_to_plane_tool`** - Position solids relative to planes
  - Origin alignment
  - 3D offset support
  - Rotation around axes

### 🔨 Enhanced - Boolean Operations (Added 2025-10-08)

- **`boolean_union_tool`** - Fuse multiple solids
  - Multiple tool objects support
  - Automatic source hiding
  - Professional result naming

- **`boolean_cut_tool`** - Subtract solids
  - Single tool object
  - Perfect for holes and pockets
  - Automatic cleanup

- **`boolean_intersection_tool`** - Keep common volume
  - Two object operation
  - Useful for complex shapes
  - Clean result

- **`boolean_common_tool`** - Alias for intersection
  - FreeCAD terminology compatibility

### 🔗 Enhanced - Transform & Alignment (Added 2025-10-08)

- **`transform_object_tool`** - Precise object positioning
  - Translation (absolute/relative)
  - Rotation (axis + angle)
  - Combined transformations

- **`align_object_tool`** - Align objects together
  - Position alignment
  - Rotation alignment
  - Both with offset support

- **`attach_to_face_tool`** - Attach objects to faces
  - Multiple map modes
  - Face-based positioning
  - Offset support

### 🏗️ Enhanced - Assembly Support (Added 2025-10-08)

#### Assembly3 (Constraint-Based)
- **`create_assembly3_tool`** - Create Assembly3 container
- **`add_part_to_assembly3_tool`** - Add parts from file or document
- **`add_assembly3_constraint_tool`** - Add constraints
  - Types: PlaneCoincident, Axial, PointsCoincident, PointOnLine, etc.
- **`solve_assembly3_tool`** - Solve constraints

#### Assembly3 Advanced
- **`list_assembly3_constraints_tool`** - List all constraints with details
- **`delete_assembly3_constraint_tool`** - Remove constraints
- **`modify_assembly3_constraint_tool`** - Modify constraint properties

#### Assembly4 (LCS-Based)
- **`create_assembly4_tool`** - Create Assembly4 container
- **`create_lcs_assembly4_tool`** - Create Local Coordinate Systems
- **`insert_part_assembly4_tool`** - Insert parts with LCS attachment
- **`attach_lcs_to_geometry_tool`** - Attach LCS to faces/edges

#### Assembly4 Advanced
- **`list_assembly4_lcs_tool`** - List all LCS with details
- **`delete_lcs_assembly4_tool`** - Remove LCS
- **`modify_lcs_assembly4_tool`** - Modify LCS position/rotation

#### Assembly Common
- **`list_assembly_parts_tool`** - List parts (works with both Assembly3/4)
- **`export_assembly_tool`** - Export to STEP, IGES, STL, OBJ, BREP
- **`calculate_assembly_mass_tool`** - Calculate total mass
- **`generate_bom_tool`** - Generate Bill of Materials
  - Formats: JSON, CSV, Markdown
- **`get_assembly_properties_tool`** - Get detailed assembly info
  - Mass, center of gravity, bounding box, counts

### 📚 Documentation

#### New Documentation Files
- `CORSAIR_MODELING_WORKFLOW.md` - Complete aircraft modeling guide (706 lines)
- `QUICKSTART_CORSAIR.md` - 5-minute quick start
- `README_CORSAIR_COMPLETE.md` - Complete user guide
- `IMPLEMENTATION_SUMMARY_FINAL.md` - Technical implementation details
- `TESTS_RESULTS_CORSAIR.md` - Test results and validation

#### API Documentation
- Complete docstrings for all 52 tools
- JSON examples for Claude integration
- Workflow guides for complex operations
- Strategic prompts for AI assistant

### 🧪 Testing

#### New Test Suites
- `tests/test_sketch_workflow.py` - Sketch workflow validation
- `tests/test_boolean_operations.py` - Boolean operations tests
- `tests/test_advanced_simple.py` - Advanced features validation (4/10 tested)
- `tests/run_all_tests.py` - Consolidated test runner

#### Test Coverage
- ✅ 100% core features tested
- ✅ 40% advanced features validated
- ✅ All Assembly3/4 tools validated
- ✅ Boolean operations validated
- ✅ Sketch workflow validated

### 📊 Performance

#### Productivity Gains (Corsair Aircraft Example)
- **Fuselage**: 25h → 10h (-60%)
- **Wings**: 30h → 12h (-60%)
- **Engine**: 20h → 5h (-75%)
- **Armament**: 15h → 3h (-80%)
- **Total**: 100h → 40h (-60%)

**Overall: 60% time saving for complex projects**

### 🏗️ Architecture

#### New Modules
- `modeling_tools_advanced.py` (~1100 lines) - Advanced modeling features
- `sketch_tools/` - Sketch workflow package
  - `plane_manager.py` - Datum plane management
  - `sketch_manager.py` - Sketch creation
  - `contour_builder.py` - Geometry construction
  - `extrude_manager.py` - Solid extrusion
  - `attachment_manager.py` - Object positioning
  - `boolean_operations.py` - Boolean operations
  - `transform_manager.py` - Transformations
- `assembly_tools/` - Assembly package
  - `assembly3_manager.py` - Assembly3 core
  - `assembly3_advanced.py` - Assembly3 advanced
  - `assembly4_manager.py` - Assembly4 core
  - `assembly4_advanced.py` - Assembly4 advanced
  - `assembly_common.py` - Common operations
  - `bom_manager.py` - BOM generation
- `prompts/` - AI strategy prompts
  - `sketch_strategy.py` - Sketch workflow guidance
  - `boolean_strategy.py` - Boolean operations guidance
  - `assembly_strategy.py` - Assembly workflow guidance

### 🎯 Strategic Prompts

Added AI assistant strategy prompts:
- `@mcp.prompt() sketch_workflow()` - Sketch-based modeling strategy
- `@mcp.prompt() boolean_operations_guide()` - Boolean operations strategy
- `@mcp.prompt() assembly_guide()` - Assembly workflow strategy
- Enhanced `asset_creation_strategy()` - General CAD workflow

### 📈 Statistics

- **Total MCP Tools**: 52 (was 28 in v2.x)
- **New Tools**: +24 tools
- **Code Lines**: ~8730 (implementation + tests + docs)
- **Test Coverage**: 100% core, 40% advanced
- **Documentation**: ~6300 lines

### 🐛 Fixed

- Screenshot handling for TechDraw and Spreadsheet views
- Assembly3 constraint type validation
- Boolean operation result naming
- Sketch attachment to planes
- Transform relative/absolute modes

### 🔄 Changed

- Enhanced error messages with actionable guidance
- Improved screenshot availability detection
- Better object naming conventions
- Consistent return format for all tools

## [2.0.0] - Previous Version

### Added
- Advanced modeling: Loft, Revolve, Sweep, 3D Splines
- Basic boolean operations
- FEM analysis support
- Draft tools integration

## [1.0.0] - Initial Release

### Added
- Basic document management
- Parametric object creation (Box, Cylinder, Sphere, Cone)
- Object editing and deletion
- Visual feedback with screenshots
- Parts library integration
- Code execution capability
- FreeCAD addon with XML-RPC server

---

## Future Roadmap

### Planned for v3.1
- [ ] NURBS surface support
- [ ] Sheet metal tools
- [ ] TechDraw integration
- [ ] Animation support

### Planned for v4.0
- [ ] Real-time collaboration
- [ ] Cloud rendering
- [ ] Advanced FEM analysis
- [ ] Generative design tools

---

**Legend:**
- ✨ Added: New features
- 🔧 Enhanced: Improved features
- 🐛 Fixed: Bug fixes
- 🔄 Changed: Modified behavior
- 🗑️ Removed: Deprecated features

**Version Format:** `MAJOR.MINOR.PATCH`
- MAJOR: Incompatible API changes
- MINOR: New functionality (backward compatible)
- PATCH: Bug fixes (backward compatible)

