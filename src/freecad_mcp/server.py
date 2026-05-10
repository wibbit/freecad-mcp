import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent

from .freecad_client import FreeCADConnection
from .operations import (
    get_view_operation,
    run_fem_analysis_operation,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .responses import parse_execute_result
from .server_state import ServerState

from .modeling_tools import (
    create_loft as _create_loft,
    create_revolve as _create_revolve,
    create_sweep as _create_sweep,
    create_spline_3d as _create_spline_3d,
)
from .modeling_tools_advanced import (
    add_fillet as _add_fillet,
    add_chamfer as _add_chamfer,
    shell_object as _shell_object,
    mirror_object as _mirror_object,
    circular_pattern as _circular_pattern,
    linear_pattern as _linear_pattern,
    create_reference_plane as _create_reference_plane,
    create_reference_axis as _create_reference_axis,
    import_airfoil_profile as _import_airfoil_profile,
    import_dxf as _import_dxf,
)
from .sketch_tools.plane_manager import create_datum_plane as _create_datum_plane
from .sketch_tools.sketch_manager import create_sketch_on_plane as _create_sketch_on_plane
from .sketch_tools.contour_builder import add_contour_to_sketch as _add_contour_to_sketch
from .sketch_tools.extrude_manager import extrude_sketch_bidirectional as _extrude_sketch_bidirectional
from .sketch_tools.attachment_manager import attach_solid_to_plane as _attach_solid_to_plane
from .sketch_tools.boolean_operations import (
    boolean_union as _boolean_union,
    boolean_cut as _boolean_cut,
    boolean_intersection as _boolean_intersection,
)
from .sketch_tools.transform_manager import (
    transform_object as _transform_object,
    align_object as _align_object,
    attach_to_face as _attach_to_face,
)
from .assembly_tools.assembly3_manager import (
    create_assembly3 as _create_assembly3,
    add_part_to_assembly3 as _add_part_to_assembly3,
    add_assembly3_constraint as _add_assembly3_constraint,
    solve_assembly3 as _solve_assembly3,
)
from .assembly_tools.assembly4_manager import (
    create_assembly4 as _create_assembly4,
    create_lcs_assembly4 as _create_lcs_assembly4,
    insert_part_assembly4 as _insert_part_assembly4,
    attach_lcs_to_geometry as _attach_lcs_to_geometry,
)
from .assembly_tools.assembly_common import (
    list_assembly_parts as _list_assembly_parts,
    export_assembly as _export_assembly,
)
from .assembly_tools.assembly3_advanced import (
    list_assembly3_constraints as _list_assembly3_constraints,
    delete_assembly3_constraint as _delete_assembly3_constraint,
    modify_assembly3_constraint as _modify_assembly3_constraint,
)
from .assembly_tools.assembly4_advanced import (
    list_assembly4_lcs as _list_assembly4_lcs,
    delete_lcs_assembly4 as _delete_lcs_assembly4,
    modify_lcs_assembly4 as _modify_lcs_assembly4,
)
from .assembly_tools.bom_manager import (
    generate_bom as _generate_bom,
    get_assembly_properties as _get_assembly_properties,
)
from .prompts.sketch_strategy import sketch_workflow_strategy
from .prompts.boolean_strategy import boolean_operations_strategy
from .prompts.assembly_strategy import assembly_strategy
from .prompts.primitives_strategy import part_primitives_strategy
from .prompts.fem_strategy import fem_workflow_strategy
from .prompts.session_startup import session_startup_guide

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")

_MAX_LOG_LEN = 120


def _truncate(value, _depth=0):
    """Return a loggable, length-capped representation of a value."""
    if isinstance(value, str):
        if len(value) > _MAX_LOG_LEN:
            return f"{value[:_MAX_LOG_LEN]}…[{len(value)} chars]"
        return value
    if isinstance(value, dict):
        if _depth >= 1:
            return f"{{…{len(value)} keys}}"
        return {k: _truncate(v, _depth + 1) for k, v in list(value.items())[:6]}
    if isinstance(value, (list, tuple)):
        if _depth >= 1:
            return f"[…{len(value)} items]"
        return [_truncate(v, _depth + 1) for v in value[:4]]
    return value


def _log_tool(func):
    """Decorator that logs MCP tool entry, exit, duration, and whether a screenshot was returned."""
    import functools
    import time

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logged_kwargs = {k: _truncate(v) for k, v in kwargs.items() if k != "ctx"}
        logger.info("tool → %s %s", func.__name__, logged_kwargs)
        t = time.monotonic()
        try:
            result = func(*args, **kwargs)
            elapsed = time.monotonic() - t
            has_image = any(getattr(r, "type", None) == "image" for r in (result or []))
            logger.info(
                "tool ← %s OK (%.2fs)%s",
                func.__name__,
                elapsed,
                " [+screenshot]" if has_image else "",
            )
            return result
        except Exception as e:
            logger.error("tool ← %s FAIL (%.2fs): %s", func.__name__, time.monotonic() - t, e)
            raise

    return wrapper


state = ServerState()


def add_screenshot_if_available(response: list, screenshot) -> list:
    if screenshot and not state.only_text_feedback:
        response.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    elif not screenshot and not state.only_text_feedback:
        response.append(TextContent(
            type="text",
            text="Note: Visual preview unavailable in this view type (e.g. TechDraw or Spreadsheet). Switch to a 3D view for screenshots.",
        ))
    return response


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("FreeCADMCP server starting up")
        try:
            _ = get_freecad_connection()
            logger.info("Successfully connected to FreeCAD on startup")
        except Exception as e:
            logger.warning(f"Could not connect to FreeCAD on startup: {str(e)}")
            logger.warning(
                "Make sure the FreeCAD addon is running before using FreeCAD resources or tools"
            )
        yield {}
    finally:
        if state.freecad_connection:
            logger.info("Disconnecting from FreeCAD on shutdown")
            state.freecad_connection.disconnect()
            state.freecad_connection = None
        logger.info("FreeCADMCP server shut down")


mcp = FastMCP(
    "FreeCADMCP",
    instructions=(
        "FreeCAD parametric CAD modelling via MCP. FreeCAD must be running with the FreeCADMCP addon active.\n\n"
        "Getting started:\n"
        "1. Call get_freecad_status to confirm FreeCAD is running and see the active document.\n"
        "2. Call list_documents to see open documents, or create_document to start a new one.\n"
        "3. Read the relevant workflow prompt before any multi-step task: session_startup_guide_prompt (session checklist), sketch_workflow (sketch-to-solid), boolean_operations_guide (combining/subtracting solids), assembly_guide (Assembly3 and Assembly4), part_primitives_guide (Part primitives and boolean ops), fem_workflow (FEM stress analysis), asset_creation_strategy (general overview).\n\n"
        "Tool groups:\n"
        "- Document/object management: create_document, list_documents, get_objects, get_object, create_object, edit_object, delete_object, get_freecad_status\n"
        "- Sketch workflow: create_datum_plane, create_sketch_on_plane, add_contour_to_sketch, extrude_sketch_bidirectional, attach_solid_to_plane\n"
        "- Boolean operations: boolean_union, boolean_cut, boolean_intersection\n"
        "- Advanced modeling: create_loft, create_revolve, create_sweep, create_spline_3d, add_fillet, add_chamfer, shell_object, mirror_object, circular_pattern, linear_pattern, create_reference_plane, create_reference_axis, import_airfoil_profile, import_dxf\n"
        "- Assembly: create_assembly3, create_assembly4 and related tools\n"
        "- FEM analysis: run_fem_analysis (requires setup via create_object — see docstring)\n"
        "- Inspection/view: get_view, execute_code (escape hatch for operations not covered by dedicated tools)\n\n"
        "All doc_name and obj_name values are case-sensitive and must exactly match FreeCAD's internal names. Call get_objects or get_freecad_status if you are unsure what names exist."
    ),
    lifespan=server_lifespan,
)


def get_freecad_connection() -> FreeCADConnection:
    """Get or create a persistent FreeCAD connection, reconnecting if stale."""
    if state.freecad_connection is not None:
        try:
            state.freecad_connection.ping()
        except Exception:
            logger.warning("FreeCAD connection is stale, reconnecting...")
            state.freecad_connection = None

    if state.freecad_connection is None:
        state.freecad_connection = FreeCADConnection(host=state.rpc_host, port=9875)
        try:
            if not state.freecad_connection.ping():
                raise Exception("Ping returned false")
        except Exception as e:
            logger.error("Failed to connect to FreeCAD: %s", e)
            state.freecad_connection = None
            raise Exception(
                "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
            ) from e

    return state.freecad_connection


@mcp.tool()
@_log_tool
def create_document(ctx: Context, name: str) -> list[TextContent]:
    """Create a new document in FreeCAD.

    Args:
        name: The name of the document to create.

    Returns:
        A message indicating the success or failure of the document creation.

    Examples:
        If you want to create a document named "MyDocument", you can use the following data.
        ```json
        {
            "name": "MyDocument"
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return [TextContent(type="text", text=f"Document '{res['data']['document_name']}' created successfully")]
        else:
            raise Exception(f"Failed to create document: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def create_object(
    ctx: Context,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.

    Returns:
        A message indicating the success or failure of the object creation and a screenshot of the object.

    Examples:
        If you want to create a cylinder with a height of 30 and a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCylinder",
            "obj_name": "Cylinder",
            "obj_type": "Part::Cylinder",
            "obj_properties": {
                "Height": 30,
                "Radius": 10,
                "Placement": {
                    "Base": {
                        "x": 10,
                        "y": 10,
                        "z": 0
                    },
                    "Rotation": {
                        "Axis": {
                            "x": 0,
                            "y": 0,
                            "z": 1
                        },
                        "Angle": 45
                    }
                },
                "ViewObject": {
                    "ShapeColor": [0.5, 0.5, 0.5, 1.0]
                }
            }
        }
        ```

        If you want to create a circle with a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCircle",
            "obj_name": "Circle",
            "obj_type": "Draft::Circle",
        }
        ```

        If you want to create a FEM analysis, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemAnalysis",
            "obj_type": "Fem::AnalysisPython",
        }
        ```

        If you want to create a FEM constraint, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMConstraint",
            "obj_name": "FemConstraint",
            "obj_type": "Fem::ConstraintFixed",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "References": [
                    {
                        "object_name": "MyObject",
                        "face": "Face1"
                    }
                ]
            }
        }
        ```

        If you want to create a FEM mechanical material, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemMechanicalMaterial",
            "obj_type": "Fem::MaterialCommon",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Material": {
                    "Name": "MyMaterial",
                    "Density": "7900 kg/m^3",
                    "YoungModulus": "210 GPa",
                    "PoissonRatio": 0.3
                }
            }
        }
        ```

        If you want to create a FEM mesh, you can use the following data.
        The `Shape` property is required (legacy `Part` is also accepted).
        On FreeCAD 1.x the size limits are `CharacteristicLengthMax/Min`;
        the legacy `ElementSizeMax/Min` keys are also accepted.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Shape": "MyObject",
                "CharacteristicLengthMax": 10,
                "CharacteristicLengthMin": 0.1
            }
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        obj_data = {"Name": obj_name, "Type": obj_type, "Properties": obj_properties or {}, "Analysis": analysis_name}
        res = freecad.create_object(doc_name, obj_data)
        if res["success"]:
            screenshot = freecad.get_active_screenshot()
            response = [TextContent(type="text", text=f"Object '{res['data']['object_name']}' created successfully")]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to create object: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def edit_object(
    ctx: Context, doc_name: str, obj_name: str, obj_properties: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """Edit an object in FreeCAD.
    This tool is used when the `create_object` tool cannot handle the object creation.

    Args:
        doc_name: The name of the document to edit the object in.
        obj_name: The name of the object to edit.
        obj_properties: The properties of the object to edit.

    Returns:
        A message indicating the success or failure of the object editing and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        if res["success"]:
            screenshot = freecad.get_active_screenshot()
            response = [TextContent(type="text", text=f"Object '{res['data']['object_name']}' edited successfully")]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to edit object: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def delete_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.delete_object(doc_name, obj_name)
        if res["success"]:
            screenshot = freecad.get_active_screenshot()
            response = [TextContent(type="text", text=f"Object '{res['data']['object_name']}' deleted successfully")]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to delete object: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def execute_code(ctx: Context, code: str) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.execute_code(code)
        if res["success"]:
            screenshot = freecad.get_active_screenshot()
            response = [TextContent(type="text", text=f"Code executed successfully.\nOutput: {res['data']['output']}")]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to execute code: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def get_view(
    ctx: Context,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"],
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> list[ImageContent | TextContent]:
    """Get a screenshot of the active view.

    Args:
        view_name: The name of the view to get the screenshot of.
        The following views are available:
        - "Isometric"
        - "Front"
        - "Top"
        - "Right"
        - "Back"
        - "Left"
        - "Bottom"
        - "Dimetric"
        - "Trimetric"
        width: The width of the screenshot in pixels. If not specified, uses the viewport width.
        height: The height of the screenshot in pixels. If not specified, uses the viewport height.
        focus_object: The name of the object to focus on. If not specified, fits all objects in the view.

    Returns:
        A screenshot of the active view.
    """
    return get_view_operation(get_freecad_connection(), view_name, width, height, focus_object)


@mcp.tool()
@_log_tool
def insert_part_from_library(ctx: Context, relative_path: str) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.insert_part_from_library(relative_path)
        if res["success"]:
            screenshot = freecad.get_active_screenshot()
            response = [TextContent(type="text", text="Part inserted from library successfully")]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to insert part from library: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        raise


@mcp.tool()
@_log_tool
def get_objects(ctx: Context, doc_name: str) -> list[TextContent | ImageContent]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.get_objects(doc_name)
        screenshot = freecad.get_active_screenshot()
        if res["success"]:
            response = [TextContent(type="text", text=json.dumps(res["data"]))]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to get objects: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        raise Exception(f"Failed to get objects: {str(e)}")


@mcp.tool()
@_log_tool
def get_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.

    Returns:
        The object and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.get_object(doc_name, obj_name)
        screenshot = freecad.get_active_screenshot()
        if res["success"]:
            response = [TextContent(type="text", text=json.dumps(res["data"]))]
            return add_screenshot_if_available(response, screenshot)
        else:
            raise Exception(f"Failed to get object: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        raise Exception(f"Failed to get object: {str(e)}")


@mcp.tool()
@_log_tool
def get_parts_list(ctx: Context) -> list[TextContent]:
    """List all available parts in the FreeCAD parts library addon.

    Call this before insert_part_from_library to discover valid relative_path values.
    Returns an informative message if the parts_library addon is not installed.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.get_parts_list()
        if res.get("success") and res.get("data"):
            return [TextContent(type="text", text=json.dumps(res["data"]))]
        raise Exception("No parts found. Install the FreeCAD parts_library addon to use this feature.")
    except Exception as e:
        logger.error(f"Failed to get parts list: {e}")
        raise Exception(f"Failed to get parts list: {e}")


@mcp.tool()
@_log_tool
def list_documents(ctx: Context) -> list[TextContent]:
    """Get the list of open documents in FreeCAD.

    Returns:
        A list of document names. Call this before any operation that requires a doc_name.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.list_documents()
        if res.get("success"):
            return [TextContent(type="text", text=json.dumps(res["data"]))]
        raise Exception(f"Failed to list documents: {res.get('error')}")
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise Exception(f"Failed to list documents: {e}")


@mcp.tool()
@_log_tool
def get_freecad_status(ctx: Context) -> list[TextContent]:
    """Get the current state of the FreeCAD session.

    Returns the active document, open documents, active workbench, and active
    PartDesign body. Call this at the start of a session to orient yourself,
    or when a document/object operation fails unexpectedly.
    """
    freecad = get_freecad_connection()
    res = freecad.get_status()
    if res["success"]:
        return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
    else:
        raise Exception(f"Failed to get status: {res['error']}")


@mcp.tool()
@_log_tool
def get_shape_topology(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Return the topological summary of an object's shape: faces, edges, and vertices.

    Use this to inspect a solid's geometry for downstream operations such as
    selecting faces for boolean cuts, identifying edge counts for fillets, or
    verifying that an extrusion produced the expected number of faces.

    Returns a JSON object with:
    - faces: list of {index, area, normal, centroid}
    - edges: list of {index, length, curve_type}
    - vertices: list of {index, x, y, z}

    Args:
        doc_name: Name of the FreeCAD document.
        obj_name: Name of the object whose shape to inspect.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.get_shape_topology(doc_name, obj_name)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to get shape topology: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to get shape topology: {e}")


@mcp.tool()
@_log_tool
def save_document(
    ctx: Context,
    doc_name: str,
    path: str = "",
) -> list[TextContent]:
    """Save the FreeCAD document to disk.

    If `path` is provided, saves to that absolute file path (saveAs). If omitted,
    saves to the document's current file path. Fails if no path is set and the
    document has never been saved.

    Args:
        doc_name: Name of the FreeCAD document to save.
        path: Absolute file path to save to (optional). If empty, saves in place.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.save_document(doc_name, path)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to save document: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to save document: {e}")


@mcp.tool()
@_log_tool
def load_document(
    ctx: Context,
    path: str,
) -> list[TextContent]:
    """Open a FreeCAD document from disk and return the resulting document name.

    The document is opened in FreeCAD's GUI and becomes available for subsequent
    tool calls using the returned document name.

    Args:
        path: Absolute file path to the .FCStd file to open.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.load_document(path)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to load document: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to load document: {e}")


@mcp.tool()
@_log_tool
def measure_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
) -> list[TextContent]:
    """Return physical measurements for a solid object.

    Useful for validating dimensions after modelling, checking mass properties
    for FEM setup, or confirming bounding box extents before assembly placement.

    Returns a JSON object with:
    - bounding_box: {min_x, max_x, size_x, min_y, max_y, size_y, min_z, max_z, size_z} in mm
    - volume: in mm³
    - surface_area: in mm²
    - center_of_mass: {x, y, z} in mm

    Args:
        doc_name: Name of the FreeCAD document.
        obj_name: Name of the solid object to measure.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.measure_object(doc_name, obj_name)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to measure object: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to measure object: {e}")


@mcp.tool()
@_log_tool
def set_object_visibility(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    visible: bool,
) -> list[TextContent]:
    """Show or hide an object in the FreeCAD 3D view.

    Use this to toggle visibility of objects without deleting them, useful for
    managing complex assemblies or revealing hidden geometry.

    Args:
        doc_name: Name of the FreeCAD document.
        obj_name: Name of the object to show or hide.
        visible: True to show the object, False to hide it.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.set_object_visibility(doc_name, obj_name, visible)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to set object visibility: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to set object visibility: {e}")


@mcp.tool()
@_log_tool
def undo(
    ctx: Context,
    doc_name: str,
    steps: int = 1,
) -> list[TextContent]:
    """Undo the last N operations on a FreeCAD document.

    Use this to revert recent changes when a modeling operation produced
    an undesired result. Each call undoes the specified number of steps.

    Args:
        doc_name: Name of the FreeCAD document.
        steps: Number of undo steps to perform (default 1).
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.undo(doc_name, steps)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to undo: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to undo: {e}")


@mcp.tool()
@_log_tool
def export_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    path: str,
    export_format: Literal["step", "stl", "obj", "iges"],
) -> list[TextContent]:
    """Export a single FreeCAD object to a file.

    Writes the object geometry to the specified path in the chosen format.
    STEP and IGES preserve full B-Rep topology; STL and OBJ produce triangle meshes.

    Args:
        doc_name: Name of the FreeCAD document.
        obj_name: Name of the object to export.
        path: Absolute file path to write (e.g. "/tmp/part.step").
        export_format: File format — one of "step", "stl", "obj", "iges".
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.export_object(doc_name, obj_name, path, export_format)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to export object: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to export object: {e}")


@mcp.tool()
@_log_tool
def spreadsheet_read(
    ctx: Context,
    doc_name: str,
    sheet_name: str,
    cell_range: str,
) -> list[TextContent]:
    """Read one or more cells from a FreeCAD Spreadsheet object.

    Returns a dict mapping cell addresses to their values (string, float, or int).
    Use a single address like "A1" or a range like "A1:C3".

    Args:
        doc_name: Name of the FreeCAD document.
        sheet_name: Name of the Spreadsheet object in the document.
        cell_range: Cell address ("A1") or range ("A1:C3") to read.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.spreadsheet_read(doc_name, sheet_name, cell_range)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to read spreadsheet: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to read spreadsheet: {e}")


@mcp.tool()
@_log_tool
def spreadsheet_write(
    ctx: Context,
    doc_name: str,
    sheet_name: str,
    cell: str,
    value: str,
) -> list[TextContent]:
    """Write a value to a single cell in a FreeCAD Spreadsheet object.

    Sets the cell content and recomputes the sheet so any dependent
    expressions and linked model parameters are updated immediately.

    Args:
        doc_name: Name of the FreeCAD document.
        sheet_name: Name of the Spreadsheet object in the document.
        cell: Cell address to write (e.g. "B2").
        value: Value to write; formulas start with "=" (e.g. "=A1+10").
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.spreadsheet_write(doc_name, sheet_name, cell, value)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to write spreadsheet: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to write spreadsheet: {e}")


@mcp.tool()
@_log_tool
def copy_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    new_name: str,
) -> list[TextContent]:
    """Duplicate an object within the same FreeCAD document under a new label.

    Creates an independent copy of the named object and assigns it the given
    label. Returns the copy's internal Name (auto-assigned by FreeCAD) along
    with the requested label. Note that ``new_name`` sets the human-readable
    Label, not the internal Name used in expressions and object lookups.
    Dependencies are copied recursively so the copy is self-contained. The
    returned ``copy`` key is the internal FreeCAD object name (auto-generated);
    ``label`` is the human-readable name you provided.

    Args:
        doc_name: Name of the FreeCAD document containing the object.
        obj_name: Internal name of the object to duplicate.
        new_name: Label to assign to the newly created copy.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.copy_object(doc_name, obj_name, new_name)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to copy object: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to copy object: {e}")


@mcp.tool()
@_log_tool
def create_techdraw_page(
    ctx: Context,
    doc_name: str,
    page_name: str,
    template_path: str = "",
) -> list[TextContent]:
    """Create a TechDraw engineering drawing sheet in a FreeCAD document.

    Adds a new TechDraw::DrawPage object to the document, optionally loading
    an SVG border/title-block template. Once the page exists, use
    ``add_view_to_techdraw_page`` to place projected views of 3D objects on
    it.

    Args:
        doc_name: Name of the FreeCAD document.
        page_name: Name to assign to the new TechDraw page object.
        template_path: Absolute path to an SVG template file for the sheet
            border and title block. Leave empty to create a blank sheet.
            Note: blank pages (no template) require FreeCAD 1.0 or later;
            FreeCAD 0.21 and earlier require a template file to render correctly.
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.create_techdraw_page(doc_name, page_name, template_path)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to create TechDraw page: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to create TechDraw page: {e}")


@mcp.tool()
@_log_tool
def add_view_to_techdraw_page(
    ctx: Context,
    doc_name: str,
    page_name: str,
    obj_name: str,
    view_name: str,
    x: float = 100.0,
    y: float = 100.0,
    scale: float = 1.0,
) -> list[TextContent]:
    """Add a projected view of a 3D object onto an existing TechDraw page.

    Creates a TechDraw::DrawViewPart that projects the named 3D object onto
    the specified drawing page. Call ``create_techdraw_page`` first to ensure
    the page exists. Position the view with ``x``/``y`` page coordinates
    (in mm from the page origin) and control its size with ``scale``.

    Args:
        doc_name: Name of the FreeCAD document.
        page_name: Internal name of the TechDraw page to add the view to.
        obj_name: Internal name of the 3D object to project.
        view_name: Name to assign to the new DrawViewPart object.
        x: Horizontal position of the view on the page in mm.
        y: Vertical position of the view on the page in mm.
        scale: Scale ratio for the view (e.g. 0.5 for half size, 2.0 for double).
    """
    try:
        freecad = get_freecad_connection()
        res = freecad.add_view_to_techdraw_page(doc_name, page_name, obj_name, view_name, x, y, scale)
        if res["success"]:
            return [TextContent(type="text", text=json.dumps(res["data"], indent=2))]
        else:
            raise Exception(f"Failed to add view to TechDraw page: {res['error']}")
    except Exception as e:
        raise Exception(f"Failed to add view to TechDraw page: {e}")


@mcp.tool()
@_log_tool
def run_fem_analysis(
    ctx: Context,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> list[TextContent | ImageContent]:
    """Run the CalculiX solver on an existing Fem::FemAnalysis container and return summary results.

    Prerequisites in the document:
    - A Part-derived solid (e.g. Part::Box, PartDesign::Body) acting as the geometry.
    - A Fem::AnalysisPython container created via `create_object`.
    - A Fem::MaterialCommon assigned to the geometry, added to the analysis.
    - A Fem::FemMeshGmsh referencing the geometry, added to the analysis (the
      mesh is generated automatically when created via `create_object`).
    - At least one Fem::ConstraintFixed and one Fem::ConstraintForce (or
      ConstraintPressure) bound to faces of the geometry, added to the analysis.

    A SolverCcxTools is auto-created if the analysis has none.

    The solver runs synchronously on the FreeCAD GUI thread and blocks all
    other RPC calls for its duration; do not fan out parallel requests.

    Returns max von Mises stress (MPa), max/min displacement (mm), node count,
    and the working directory CalculiX wrote to. On failure, returns the
    prerequisite-check or solver error along with the working directory for
    triage.

    Args:
        doc_name: Name of the FreeCAD document.
        analysis_name: Name of the Fem::AnalysisPython object.
        timeout: Seconds to wait for the solver (default 600).
    """
    return run_fem_analysis_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        analysis_name,
        timeout,
    )


@mcp.tool()
@_log_tool
def create_datum_plane(
    ctx: Context,
    doc_name: str,
    plane_name: str,
    alignment: Literal["xy", "xz", "yz"] = "xy",
    offset: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Create a datum plane aligned with XY, XZ, or YZ coordinate system.
    
    This creates a reference plane (Body with Origin) that serves as the foundation for sketching.
    The plane name will be used as the base for related objects (sketch, solid).
    
    Args:
        doc_name: Document name
        plane_name: Name for the datum plane (e.g., 'base_plane', 'side_plane')
        alignment: Plane alignment - 'xy', 'xz', or 'yz' (default: 'xy')
        offset: Offset distance from origin (default: 0.0)
        
    Returns:
        Confirmation message and screenshot. See the `sketch_workflow` prompt for the full step-by-step guide before starting a sketch-based workflow.

    Example:
        {
            "doc_name": "MyDocument",
            "plane_name": "base_plane",
            "alignment": "xy",
            "offset": 0.0
        }
    """
    freecad = get_freecad_connection()
    return _create_datum_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name, alignment, offset)


@mcp.tool()
@_log_tool
def create_sketch_on_plane(
    ctx: Context,
    doc_name: str,
    plane_name: str,
) -> list[TextContent | ImageContent]:
    """Create a sketch attached to a datum plane.
    
    The sketch is automatically named as '{plane_name}_sketch'.
    This sketch inherits the coordinate system from the datum plane.
    
    Args:
        doc_name: Document name
        plane_name: Name of the datum plane (Body) to attach the sketch to
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "plane_name": "base_plane"
        }
        
        This creates: "base_plane_sketch"
    """
    freecad = get_freecad_connection()
    return _create_sketch_on_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name)


@mcp.tool()
@_log_tool
def add_contour_to_sketch(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geometry_elements: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
    fix_first_point_to_origin: bool = True,
) -> list[TextContent | ImageContent]:
    """Add geometric contour elements and constraints to a sketch.
    
    Supported geometry types:
    - point: {"type": "point", "x": float, "y": float}
    - line: {"type": "line", "start": {"x": float, "y": float}, "end": {"x": float, "y": float}}
    - arc: {"type": "arc", "center": {"x": float, "y": float}, "radius": float, "start_angle": float, "end_angle": float}
    - circle: {"type": "circle", "center": {"x": float, "y": float}, "radius": float}
    - bspline: {"type": "bspline", "points": [{"x": float, "y": float}, ...], "degree": int, "closed": bool}
    - ellipse: {"type": "ellipse", "center": {"x": float, "y": float}, "major_radius": float, "minor_radius": float, "angle": float}
    
    Supported constraints:
    - coincident: {"type": "coincident", "geo1": int, "point1": int, "geo2": int, "point2": int}
    - tangent: {"type": "tangent", "geo1": int, "geo2": int}
    - distance: {"type": "distance", "geo1": int, "point1": int, "geo2": int, "point2": int, "value": float}
    - horizontal: {"type": "horizontal", "geo": int}
    - vertical: {"type": "vertical", "geo": int}
    - angle: {"type": "angle", "geo1": int, "geo2": int, "value": float}
    - fix: {"type": "fix", "geo": int, "point": int}
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name
        geometry_elements: List of geometry elements to add
        constraints: List of constraints to apply (optional)
        fix_first_point_to_origin: If True, fixes the first point to sketch origin (default: True)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "sketch_name": "base_plane_sketch",
            "geometry_elements": [
                {"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
                {"type": "arc", "center": {"x": 100, "y": 50}, "radius": 50, "start_angle": 270, "end_angle": 0},
                {"type": "line", "start": {"x": 100, "y": 100}, "end": {"x": 0, "y": 100}}
            ],
            "constraints": [
                {"type": "coincident", "geo1": 0, "point1": 2, "geo2": 1, "point2": 1},
                {"type": "tangent", "geo1": 0, "geo2": 1}
            ],
            "fix_first_point_to_origin": true
        }
    """
    freecad = get_freecad_connection()
    return _add_contour_to_sketch(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, geometry_elements, constraints, fix_first_point_to_origin)


@mcp.tool()
@_log_tool
def extrude_sketch_bidirectional(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    length_forward: float,
    length_backward: float = 0.0,
    use_midplane: bool = False,
) -> list[TextContent | ImageContent]:
    """Extrude a sketch bidirectionally to create a 3D solid.
    
    The solid is automatically named by replacing '_sketch' with '_solid' in the sketch name.
    Can extrude in both directions (forward and backward) from the sketch plane.
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name to extrude
        length_forward: Extrusion length in the forward direction (normal to sketch)
        length_backward: Extrusion length in the backward direction (default: 0.0)
        use_midplane: If True, extrude symmetrically (default: False)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "sketch_name": "base_plane_sketch",
            "length_forward": 50.0,
            "length_backward": 25.0,
            "use_midplane": false
        }
        
        This creates: "base_plane_solid"
    """
    freecad = get_freecad_connection()
    return _extrude_sketch_bidirectional(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, length_forward, length_backward, use_midplane)


@mcp.tool()
@_log_tool
def attach_solid_to_plane(
    ctx: Context,
    doc_name: str,
    solid_body_name: str,
    target_plane_name: str,
    align_origin: bool = True,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    rotation_angle: float = 0.0,
    rotation_axis: Literal["x", "y", "z"] = "z",
) -> list[TextContent | ImageContent]:
    """Attach (position) a solid body to align with another datum plane.
    
    This positions a solid body so that its base plane aligns with a target plane.
    Useful for creating assemblies and positioning parts relative to each other.
    
    Args:
        doc_name: Document name
        solid_body_name: Name of the Body containing the solid to position
        target_plane_name: Name of the target datum plane (Body) to align with
        align_origin: If True, align the origins of the planes (default: True)
        offset_x: X offset from target plane origin (default: 0.0)
        offset_y: Y offset from target plane origin (default: 0.0)
        offset_z: Z offset from target plane origin (default: 0.0)
        rotation_angle: Rotation angle in degrees (default: 0.0)
        rotation_axis: Rotation axis - 'x', 'y', or 'z' (default: 'z')
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "solid_body_name": "base_plane",
            "target_plane_name": "mounting_plane",
            "align_origin": true,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "offset_z": 10.0,
            "rotation_angle": 90.0,
            "rotation_axis": "z"
        }
    """
    freecad = get_freecad_connection()
    return _attach_solid_to_plane(ctx, freecad, add_screenshot_if_available, doc_name, solid_body_name, target_plane_name, align_origin, offset_x, offset_y, offset_z, rotation_angle, rotation_axis)


@mcp.tool()
@_log_tool
def boolean_union(
    ctx: Context,
    doc_name: str,
    base_object_name: str,
    tool_object_names: list[str],
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Fuse multiple solids into one using Boolean Union operation.
    
    This operation merges the base object with one or more tool objects,
    creating a single unified solid. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        base_object_name: Name of the base object
        tool_object_names: List of object names to fuse with the base
        result_name: Name for the result (default: base_object_name + "_union")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "base_object_name": "base_plane_solid",
            "tool_object_names": ["side_plane_solid", "top_plane_solid"],
            "result_name": "assembled_part"
        }

    See the `boolean_operations_guide` prompt for positioning strategy.
    """
    freecad = get_freecad_connection()
    return _boolean_union(ctx, freecad, add_screenshot_if_available, doc_name, base_object_name, tool_object_names, result_name)


@mcp.tool()
@_log_tool
def boolean_cut(
    ctx: Context,
    doc_name: str,
    base_object_name: str,
    tool_object_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Subtract one solid from another using Boolean Cut operation.
    
    This operation removes the volume of the tool object from the base object,
    useful for creating holes, pockets, and cutouts. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        base_object_name: Name of the base object (what remains)
        tool_object_name: Name of the tool object (what is subtracted)
        result_name: Name for the result (default: base_object_name + "_cut")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "base_object_name": "base_plane_solid",
            "tool_object_name": "hole_solid",
            "result_name": "part_with_hole"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_cut(ctx, freecad, add_screenshot_if_available, doc_name, base_object_name, tool_object_name, result_name)


@mcp.tool()
@_log_tool
def boolean_intersection(
    ctx: Context,
    doc_name: str,
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Keep only the common volume between two solids using Boolean Intersection.
    
    This operation creates a new solid containing only the volume that is common
    to both input objects. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        object1_name: Name of the first object
        object2_name: Name of the second object
        result_name: Name for the result (default: object1_name + "_intersection")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "object1_name": "sphere_solid",
            "object2_name": "cube_solid",
            "result_name": "sphere_cube_common"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_intersection(ctx, freecad, add_screenshot_if_available, doc_name, object1_name, object2_name, result_name)



@mcp.tool()
@_log_tool
def transform_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    position: dict[str, float] | None = None,
    rotation: dict[str, Any] | None = None,
    relative: bool = False,
) -> list[TextContent | ImageContent]:
    """Transform an object with translation and/or rotation.
    
    This operation allows precise positioning and orientation of objects.
    Transformations can be absolute (set exact position/rotation) or 
    relative (add to current position/rotation).
    
    Args:
        doc_name: Document name
        obj_name: Name of the object to transform
        position: Position dict {"x": float, "y": float, "z": float} (optional)
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        relative: If True, transformation is relative to current placement
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # Absolute position
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 100, "y": 50, "z": 20}
        }
        
        # Rotation around Z axis
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 45}
        }
        
        # Combined position and rotation
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 100, "y": 50, "z": 20},
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 90}
        }
        
        # Relative move (+10 in X direction)
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 10, "y": 0, "z": 0},
            "relative": true
        }
    """
    freecad = get_freecad_connection()
    return _transform_object(ctx, freecad, add_screenshot_if_available, doc_name, obj_name, position, rotation, relative)


@mcp.tool()
@_log_tool
def align_object(
    ctx: Context,
    doc_name: str,
    source_obj_name: str,
    target_obj_name: str,
    align_type: Literal["position", "rotation", "both"] = "both",
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Align one object to another (position, rotation, or both).
    
    This operation copies the placement (position and/or rotation) from 
    a target object to a source object, optionally with an offset.
    
    Args:
        doc_name: Document name
        source_obj_name: Name of the object to move
        target_obj_name: Name of the reference object
        align_type: Type of alignment - "position", "rotation", or "both"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # Copy position only
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "position"
        }
        
        # Copy rotation only
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "rotation"
        }
        
        # Copy both with offset
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "both",
            "offset": {"x": 10, "y": 0, "z": 5}
        }
    """
    freecad = get_freecad_connection()
    return _align_object(ctx, freecad, add_screenshot_if_available, doc_name, source_obj_name, target_obj_name, align_type, offset)


@mcp.tool()
@_log_tool
def attach_to_face(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    target_obj_name: str,
    face_name: str,
    map_mode: Literal["FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"] = "FlatFace",
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Attach an object to a face of another object.
    
    This operation attaches an object to a specific face of a target object,
    using FreeCAD's attachment system or positioning it at the face center.
    
    Args:
        doc_name: Document name
        obj_name: Name of the object to attach
        target_obj_name: Name of the target face owner
        face_name: Face name (e.g., "Face1", "Face2", etc.)
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Map Modes:
        - "FlatFace": Align to a flat face
        - "ObjectXY": Align to object's XY plane
        - "ObjectXZ": Align to object's XZ plane
        - "ObjectYZ": Align to object's YZ plane
        - "NormalToEdge": Perpendicular to an edge
        
    Examples:
        # Attach to top face
        {
            "doc_name": "MyDoc",
            "obj_name": "Sketch",
            "target_obj_name": "Box",
            "face_name": "Face6",
            "map_mode": "FlatFace"
        }
        
        # Attach with offset
        {
            "doc_name": "MyDoc",
            "obj_name": "Sketch",
            "target_obj_name": "Box",
            "face_name": "Face1",
            "map_mode": "FlatFace",
            "offset": {"x": 0, "y": 0, "z": 10}
        }
    """
    freecad = get_freecad_connection()
    return _attach_to_face(ctx, freecad, add_screenshot_if_available, doc_name, obj_name, target_obj_name, face_name, map_mode, offset)


@mcp.tool()
@_log_tool
def create_assembly3(
    ctx: Context,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly3 object for constraint-based assembly.

    Assembly3 uses automatic constraint solving for part positioning.

    Args:
        doc_name: Document name
        assembly_name: Name for the assembly (default: "Assembly")

    Returns:
        Confirmation message and screenshot

    See the `assembly_guide` prompt before starting — Assembly3 and Assembly4 use completely different approaches.

    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _create_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
@_log_tool
def add_part_to_assembly3(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    part_file: str | None = None,
    part_object: str | None = None,
    part_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a part to Assembly3 from file or existing object.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file (optional)
        part_object: Existing object name in document (optional)
        part_name: Name for the imported part (optional)
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # From external file
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_file": "C:/parts/base.FCStd",
            "part_name": "Base"
        }
        
        # From existing object
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_object": "Box001"
        }
    """
    freecad = get_freecad_connection()
    return _add_part_to_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, part_file, part_object, part_name)


@mcp.tool()
@_log_tool
def add_assembly3_constraint(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    constraint_type: Literal["PlaneCoincident", "Axial", "PointsCoincident", "PointOnLine", "PointOnPlane", "SameOrientation", "MultiParallel", "Angle", "Distance", "Lock", "Perpendicular"],
    references: list[dict[str, str]],
    constraint_name: str | None = None,
    properties: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Add a constraint to Assembly3.
    
    Constraint types: PlaneCoincident, Axial, PointsCoincident, PointOnLine,
    PointOnPlane, SameOrientation, MultiParallel, Angle, Distance, Lock, Perpendicular
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_type: Type of constraint
        references: List of [{"object": "PartName", "element": "Face1"}, ...]
        constraint_name: Optional constraint name
        properties: Optional properties like {"Angle": 90, "Distance": 10}
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "constraint_type": "PlaneCoincident",
            "references": [
                {"object": "Base", "element": "Face6"},
                {"object": "Cover", "element": "Face1"}
            ]
        }
    """
    freecad = get_freecad_connection()
    return _add_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, constraint_type, references, constraint_name, properties)


@mcp.tool()
@_log_tool
def solve_assembly3(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Solve Assembly3 constraints to update part positions.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _solve_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
@_log_tool
def create_assembly4(
    ctx: Context,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly4 container for LCS-based assembly.

    Assembly4 uses Local Coordinate Systems (LCS) for manual placement.

    Args:
        doc_name: Document name
        assembly_name: Name for the assembly (default: "Assembly")

    Returns:
        Confirmation message and screenshot

    See the `assembly_guide` prompt before starting — Assembly3 and Assembly4 use completely different approaches.

    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _create_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
@_log_tool
def create_lcs_assembly4(
    ctx: Context,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
    position: dict[str, float],
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Create a Local Coordinate System (LCS) in Assembly4.
    
    Args:
        doc_name: Document name
        parent_name: Parent object (Assembly or Part)
        lcs_name: Name for the LCS
        position: Position dict {"x": float, "y": float, "z": float}
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly",
            "lcs_name": "LCS_Base",
            "position": {"x": 0, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _create_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, parent_name, lcs_name, position, rotation)


@mcp.tool()
@_log_tool
def insert_part_assembly4(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    part_file: str,
    part_name: str,
    attach_lcs_part: str | None = None,
    attach_lcs_target: str | None = None,
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Insert a part into Assembly4 using LCS attachment.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file
        part_name: Name for the inserted part
        attach_lcs_part: LCS name in the part (optional)
        attach_lcs_target: LCS name in assembly (optional)
        offset: Optional offset {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_file": "C:/parts/base.FCStd",
            "part_name": "Base",
            "attach_lcs_part": "LCS_Origin",
            "attach_lcs_target": "LCS_Base"
        }
    """
    freecad = get_freecad_connection()
    return _insert_part_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, part_file, part_name, attach_lcs_part, attach_lcs_target, offset)


@mcp.tool()
@_log_tool
def attach_lcs_to_geometry(
    ctx: Context,
    doc_name: str,
    lcs_name: str,
    target_object: str,
    element: str,
    map_mode: Literal["FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"] = "FlatFace",
) -> list[TextContent | ImageContent]:
    """Attach an LCS to a geometric element in Assembly4.
    
    Args:
        doc_name: Document name
        lcs_name: LCS object name
        target_object: Target object name
        element: Element name (e.g., "Face1", "Edge1")
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount",
            "target_object": "Box",
            "element": "Face6",
            "map_mode": "FlatFace"
        }
    """
    freecad = get_freecad_connection()
    return _attach_lcs_to_geometry(ctx, freecad, add_screenshot_if_available, doc_name, lcs_name, target_object, element, map_mode)


@mcp.tool()
@_log_tool
def list_assembly_parts(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    assembly_type: Literal["auto", "assembly3", "assembly4"] = "auto",
) -> list[TextContent | ImageContent]:
    """List all parts in an assembly (works with Assembly3 and Assembly4).
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        assembly_type: Type - "auto", "assembly3", or "assembly4"
        
    Returns:
        List of parts with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "assembly_type": "auto"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly_parts(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, assembly_type)


@mcp.tool()
@_log_tool
def export_assembly(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    export_path: str,
    export_format: Literal["step", "iges", "stl", "obj", "brep"] = "step",
) -> list[TextContent | ImageContent]:
    """Export an assembly to a file.
    
    Formats: step, iges, stl, obj, brep
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        export_path: Path for exported file
        export_format: Format - "step", "iges", "stl", "obj", "brep"
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "export_path": "C:/exports/assembly.step",
            "export_format": "step"
        }
    """
    freecad = get_freecad_connection()
    return _export_assembly(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, export_path, export_format)



# ==================== ASSEMBLY PHASE 2 - ADVANCED TOOLS (2025-10-08) ====================

@mcp.tool()
@_log_tool
def list_assembly3_constraints(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """List all constraints in an Assembly3 with details.
    
    Returns constraint type, references, properties, and state.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        JSON list of all constraints with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly3_constraints(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
@_log_tool
def delete_assembly3_constraint(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    constraint_name: str,
) -> list[TextContent | ImageContent]:
    """Delete a constraint from Assembly3.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_name: Constraint name to delete
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "constraint_name": "PlaneCoincident001"
        }
    """
    freecad = get_freecad_connection()
    return _delete_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, constraint_name)


@mcp.tool()
@_log_tool
def modify_assembly3_constraint(
    ctx: Context,
    doc_name: str,
    constraint_name: str,
    properties: dict[str, Any],
) -> list[TextContent | ImageContent]:
    """Modify properties of an Assembly3 constraint.
    
    Args:
        doc_name: Document name
        constraint_name: Constraint name
        properties: Properties to modify {"Distance": 10.0, "Enabled": False}
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "constraint_name": "Distance001",
            "properties": {
                "Distance": 15.0,
                "Enabled": true
            }
        }
    """
    freecad = get_freecad_connection()
    return _modify_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, constraint_name, properties)


@mcp.tool()
@_log_tool
def list_assembly4_lcs(
    ctx: Context,
    doc_name: str,
    parent_name: str,
) -> list[TextContent | ImageContent]:
    """List all LCS in an Assembly4 or Part with details.
    
    Returns position, rotation, and attachment information.
    
    Args:
        doc_name: Document name
        parent_name: Parent object (Assembly or Part) name
        
    Returns:
        JSON list of all LCS with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly4_lcs(ctx, freecad, add_screenshot_if_available, doc_name, parent_name)


@mcp.tool()
@_log_tool
def delete_lcs_assembly4(
    ctx: Context,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
) -> list[TextContent | ImageContent]:
    """Delete an LCS from Assembly4.
    
    Args:
        doc_name: Document name
        parent_name: Parent object name
        lcs_name: LCS name to delete
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly",
            "lcs_name": "LCS_Mount1"
        }
    """
    freecad = get_freecad_connection()
    return _delete_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, parent_name, lcs_name)


@mcp.tool()
@_log_tool
def modify_lcs_assembly4(
    ctx: Context,
    doc_name: str,
    lcs_name: str,
    position: dict[str, float] | None = None,
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Modify position and/or rotation of an LCS in Assembly4.
    
    Args:
        doc_name: Document name
        lcs_name: LCS name
        position: New position {"x": float, "y": float, "z": float} (optional)
        rotation: New rotation {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        Confirmation message
        
    Examples:
        # Change position only
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount1",
            "position": {"x": 100, "y": 0, "z": 50}
        }
        
        # Change rotation only
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount1",
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 90}
        }
    """
    freecad = get_freecad_connection()
    return _modify_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, lcs_name, position, rotation)


@mcp.tool()
@_log_tool
def generate_bom(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    output_format: Literal["json", "csv", "markdown"] = "json",
) -> list[TextContent | ImageContent]:
    """Generate Bill of Materials (BOM) for an assembly.

    Counts parts, calculates masses, generates formatted BOM.

    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        output_format: Output format - "json", "csv", or "markdown"

    Returns:
        Formatted BOM

    Examples:
        # JSON format
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "output_format": "json"
        }

        # Markdown table
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "output_format": "markdown"
        }
    """
    freecad = get_freecad_connection()
    return _generate_bom(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, output_format)


@mcp.tool()
@_log_tool
def get_assembly_properties(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Get detailed properties of an assembly.
    
    Returns mass, center of gravity, bounding box, part/constraint counts.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        Detailed assembly properties
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _get_assembly_properties(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.prompt()
def asset_creation_strategy() -> str:
    return ASSET_CREATION_STRATEGY


def _validate_host(value: str) -> str:
    """Validate that *value* is a valid IP address or hostname."""
    import argparse
    import validators

    if validators.ipv4(value) or validators.ipv6(value) or validators.hostname(value):
        return value
    raise argparse.ArgumentTypeError(
        f"Invalid host: '{value}'. Must be a valid IP address or hostname."
    )


@mcp.prompt()
def sketch_workflow() -> str:
    """Strategic guide for sketch-based workflow (2025-10-08)"""
    return sketch_workflow_strategy()


@mcp.prompt()
def boolean_operations_guide() -> str:
    """Strategic guide for Boolean operations (2025-10-08)"""
    return boolean_operations_strategy()


@mcp.prompt()
def assembly_guide() -> str:
    """Strategic guide for Assembly3 and Assembly4 (2025-10-08)"""
    return assembly_strategy()


@mcp.prompt()
def part_primitives_guide() -> str:
    """Guide for creating geometry with Part primitives and boolean operations"""
    return part_primitives_strategy()


@mcp.prompt()
def fem_workflow() -> str:
    """Step-by-step guide for FEM stress analysis setup and execution"""
    return fem_workflow_strategy()


@mcp.prompt()
def session_startup_guide_prompt() -> str:
    """Session startup checklist: status check, document setup, workflow selection"""
    return session_startup_guide()


# ==================== ADVANCED MODELING TOOLS ====================

@mcp.tool()
@_log_tool
def create_loft(ctx: Context, doc_name: str, sketch_names: list[str], result_name: str | None = None, solid: bool = True, ruled: bool = False) -> list[TextContent | ImageContent]:
    """Create a loft (swept solid) through two or more existing closed sketch profiles.

    Prerequisite: all sketches in sketch_names must already exist in the document and be closed profiles. Use create_sketch_on_plane and add_contour_to_sketch to create each profile first. See the sketch_workflow prompt.
    The order of sketch_names determines the loft direction (first profile to last).
    solid=True (default) produces a closed solid; False produces an open shell.
    ruled=True creates flat-ruled faces between sections; False (default) uses smooth B-spline interpolation.
    """
    freecad = get_freecad_connection()
    name = result_name or f"{'_'.join(sketch_names[:2])}_loft"
    return _create_loft(ctx, freecad, add_screenshot_if_available, doc_name, sketch_names, name, solid, ruled)

@mcp.tool()
@_log_tool
def create_revolve(ctx: Context, doc_name: str, sketch_name: str, axis: dict[str, dict[str, float]], angle: float = 360.0, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Revolve a closed 2D sketch profile around an axis to create a solid of revolution (e.g. cylinder, cone, vase).

    Prerequisite: sketch_name must already exist and be a closed 2D profile. The sketch must not cross the axis of revolution.
    axis format: {"point": {"x": 0, "y": 0, "z": 0}, "direction": {"x": 0, "y": 0, "z": 1}}
    angle: degrees of rotation — 360 creates a full solid, less creates a partial arc solid.
    """
    freecad = get_freecad_connection()
    return _create_revolve(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, axis, angle, result_name or f"{sketch_name}_revolve")

@mcp.tool()
@_log_tool
def create_sweep(ctx: Context, doc_name: str, profile_sketch: str, path_sketch: str, result_name: str) -> list[TextContent | ImageContent]:
    """Sweep a 2D profile sketch along a path sketch to create a solid (e.g. pipe, tube, extruded curve).

    Prerequisite: profile_sketch must be a closed 2D profile; path_sketch must be an open or closed wire/sketch defining the sweep direction.
    The profile is placed at the start of the path and swept along it.
    """
    freecad = get_freecad_connection()
    return _create_sweep(ctx, freecad, add_screenshot_if_available, doc_name, profile_sketch, path_sketch, result_name)

@mcp.tool()
@_log_tool
def create_spline_3d(ctx: Context, doc_name: str, points: list[dict[str, float]], spline_name: str, closed: bool = False) -> list[TextContent | ImageContent]:
    """Create a 3D B-spline wire through a list of 3D control points.

    This produces a Wire object, not a solid. To create a solid from a 3D spline, use it as the path in create_sweep with a profile sketch.
    points: list of {"x": float, "y": float, "z": float}, minimum 2 points required.
    closed: if True, the spline loops back to the first point.
    """
    freecad = get_freecad_connection()
    return _create_spline_3d(ctx, freecad, add_screenshot_if_available, doc_name, points, spline_name, closed)

@mcp.tool()
@_log_tool
def create_tube(
    ctx: Context,
    doc_name: str,
    tube_name: str,
    outer_radius: float,
    inner_radius: float,
    height: float,
) -> list[TextContent | ImageContent]:
    """Create a hollow cylinder (tube) by subtracting an inner cylinder from an outer cylinder.

    FreeCAD has no native Part::Tube object, so this tool builds the shape from two
    Part.makeCylinder calls and a boolean cut, then stores the result as a Part::Feature.

    Args:
        doc_name: Name of the FreeCAD document.
        tube_name: Name to assign to the resulting tube object.
        outer_radius: Outer radius of the tube in mm. Must be greater than inner_radius.
        inner_radius: Inner radius (bore) of the tube in mm. Must be less than outer_radius.
        height: Height (length) of the tube in mm.

    Returns:
        Confirmation message and screenshot of the created tube.

    Example:
        {
            "doc_name": "MyDocument",
            "tube_name": "MyTube",
            "outer_radius": 25.0,
            "inner_radius": 20.0,
            "height": 100.0
        }
    """
    freecad = get_freecad_connection()
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
if doc is None:
    print("ERROR: Document '{doc_name}' not found")
else:
    try:
        outer_radius = {outer_radius}
        inner_radius = {inner_radius}
        height = {height}

        if inner_radius >= outer_radius:
            print(f"ERROR: inner_radius ({{inner_radius}}) must be less than outer_radius ({{outer_radius}})")
        else:
            outer = Part.makeCylinder(outer_radius, height)
            inner = Part.makeCylinder(inner_radius, height)
            tube_shape = outer.cut(inner)

            tube_obj = doc.addObject('Part::Feature', '{tube_name}')
            tube_obj.Shape = tube_shape
            doc.recompute()

            print(f"SUCCESS: Tube '{tube_name}' created with outer_radius={{outer_radius}}, inner_radius={{inner_radius}}, height={{height}}")
    except Exception as e:
        print(f"ERROR: Failed to create tube - {{str(e)}}")
"""
    res = freecad.execute_code(code)
    screenshot = freecad.get_active_screenshot()
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_if_available([TextContent(type="text", text=msg)], screenshot)
    raise Exception(f"Failed to create tube: {msg}")


@mcp.tool()
@_log_tool
def add_fillet(ctx: Context, doc_name: str, object_name: str, edges: list[str], radius: float, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Add fillet (rounded edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        radius: Fillet radius
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Fuselage",
            "edges": ["Edge1", "Edge2", "Edge5"],
            "radius": 10.0,
            "result_name": "Fuselage_rounded"
        }
    """
    freecad = get_freecad_connection()
    return _add_fillet(ctx, freecad, add_screenshot_if_available, doc_name, object_name, edges, radius, result_name)

@mcp.tool()
@_log_tool
def add_chamfer(ctx: Context, doc_name: str, object_name: str, edges: list[str], distance: float, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Add chamfer (beveled edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        distance: Chamfer distance
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Panel",
            "edges": ["Edge1", "Edge3"],
            "distance": 2.0,
            "result_name": "Panel_chamfered"
        }
    """
    freecad = get_freecad_connection()
    return _add_chamfer(ctx, freecad, add_screenshot_if_available, doc_name, object_name, edges, distance, result_name)

@mcp.tool()
@_log_tool
def shell_object(ctx: Context, doc_name: str, object_name: str, thickness: float, faces_to_remove: list[str] | None = None, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Create hollow shell by removing faces and adding thickness
    
    Args:
        doc_name: Document name
        object_name: Object to shell
        thickness: Wall thickness
        faces_to_remove: List of face names to remove (opens the shell)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Fuselage_solid",
            "thickness": 2.0,
            "faces_to_remove": ["Face1", "Face6"],
            "result_name": "Fuselage_shell"
        }
    """
    freecad = get_freecad_connection()
    return _shell_object(ctx, freecad, add_screenshot_if_available, doc_name, object_name, thickness, faces_to_remove, result_name)

@mcp.tool()
@_log_tool
def mirror_object(ctx: Context, doc_name: str, source_obj: str, mirror_plane: dict[str, Any], result_name: str | None = None, merge: bool = True) -> list[TextContent | ImageContent]:
    """Mirror object across a plane
    
    Args:
        doc_name: Document name
        source_obj: Object to mirror
        mirror_plane: {"base": {"x": 0, "y": 0, "z": 0}, "normal": {"x": 1, "y": 0, "z": 0}}
        result_name: Result name (optional)
        merge: If True, fuse with original (creates symmetric object)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "source_obj": "RightWing",
            "mirror_plane": {
                "base": {"x": 0, "y": 0, "z": 0},
                "normal": {"x": 1, "y": 0, "z": 0}
            },
            "merge": true,
            "result_name": "BothWings"
        }
    """
    freecad = get_freecad_connection()
    return _mirror_object(ctx, freecad, add_screenshot_if_available, doc_name, source_obj, mirror_plane, result_name, merge)

@mcp.tool()
@_log_tool
def circular_pattern(ctx: Context, doc_name: str, object_name: str, axis: dict[str, dict[str, float]], count: int, angle: float = 360.0, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Create circular pattern (polar array) of an object
    
    Args:
        doc_name: Document name
        object_name: Object to pattern
        axis: {"point": {"x": 0, "y": 0, "z": 0}, "direction": {"x": 0, "y": 0, "z": 1}}
        count: Number of instances
        angle: Total angle in degrees (default 360)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "EngineCylinder",
            "axis": {
                "point": {"x": 0, "y": 0, "z": 0},
                "direction": {"x": 1, "y": 0, "z": 0}
            },
            "count": 18,
            "angle": 360,
            "result_name": "RadialEngine"
        }
    """
    freecad = get_freecad_connection()
    return _circular_pattern(ctx, freecad, add_screenshot_if_available, doc_name, object_name, axis, count, angle, result_name)

@mcp.tool()
@_log_tool
def linear_pattern(ctx: Context, doc_name: str, object_name: str, direction: dict[str, float], spacing: float, count: int, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """Create linear pattern (rectangular array) of an object
    
    Args:
        doc_name: Document name
        object_name: Object to pattern
        direction: {"x": 1, "y": 0, "z": 0} - normalized direction
        spacing: Distance between instances
        count: Number of instances
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "MachineGun",
            "direction": {"x": 0, "y": 1, "z": 0},
            "spacing": 300,
            "count": 6,
            "result_name": "WingGuns"
        }
    """
    freecad = get_freecad_connection()
    return _linear_pattern(ctx, freecad, add_screenshot_if_available, doc_name, object_name, direction, spacing, count, result_name)

@mcp.tool()
@_log_tool
def create_reference_plane(ctx: Context, doc_name: str, plane_name: str, definition: dict[str, Any]) -> list[TextContent | ImageContent]:
    """Create reference plane with various definition modes
    
    Args:
        doc_name: Document name
        plane_name: Name for the plane
        definition: Plane definition (multiple modes supported)
            Mode 1 - Offset from existing plane:
                {"mode": "offset", "plane": "XY", "offset": 50.0}
            Mode 2 - Three points:
                {"mode": "3points", 
                 "p1": {"x": 0, "y": 0, "z": 0},
                 "p2": {"x": 100, "y": 0, "z": 0},
                 "p3": {"x": 0, "y": 100, "z": 0}}
            Mode 3 - Point and normal:
                {"mode": "point_normal",
                 "point": {"x": 0, "y": 0, "z": 0},
                 "normal": {"x": 0, "y": 0, "z": 1}}
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "plane_name": "WingPlane",
            "definition": {
                "mode": "point_normal",
                "point": {"x": 0, "y": 0, "z": 100},
                "normal": {"x": 0.2, "y": 0, "z": 1}
            }
        }
    """
    freecad = get_freecad_connection()
    return _create_reference_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name, definition)

@mcp.tool()
@_log_tool
def create_reference_axis(ctx: Context, doc_name: str, axis_name: str, point: dict[str, float], direction: dict[str, float]) -> list[TextContent | ImageContent]:
    """Create reference axis from point and direction
    
    Args:
        doc_name: Document name
        axis_name: Name for the axis
        point: {"x": 0, "y": 0, "z": 0} - point on axis
        direction: {"x": 0, "y": 0, "z": 1} - axis direction
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "axis_name": "PropellerAxis",
            "point": {"x": 500, "y": 0, "z": 0},
            "direction": {"x": 1, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _create_reference_axis(ctx, freecad, add_screenshot_if_available, doc_name, axis_name, point, direction)

@mcp.tool()
@_log_tool
def import_airfoil_profile(ctx: Context, doc_name: str, sketch_name: str, naca_code: str, chord_length: float, position: dict[str, float] | None = None) -> list[TextContent | ImageContent]:
    """Import standard NACA airfoil profile into sketch
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name to create
        naca_code: NACA code (e.g., "2412", "0012", "23015")
        chord_length: Chord length in mm
        position: Optional position {"x": 0, "y": 0, "z": 0}
    
    Returns:
        Confirmation message and screenshot
    
    Note:
        Supports NACA 4-digit and 5-digit series
        Points are calculated using standard NACA equations
    
    Example:
        {
            "doc_name": "Corsair",
            "sketch_name": "WingProfile",
            "naca_code": "2412",
            "chord_length": 2000,
            "position": {"x": 0, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _import_airfoil_profile(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, naca_code, chord_length, position)

@mcp.tool()
@_log_tool
def import_dxf(ctx: Context, doc_name: str, file_path: str, sketch_name: str, scale: float = 1.0) -> list[TextContent | ImageContent]:
    """Import DXF file into a sketch
    
    Args:
        doc_name: Document name
        file_path: Full path to DXF file
        sketch_name: Sketch name to create
        scale: Scale factor (default 1.0)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "file_path": "C:/models/fuselage_section.dxf",
            "sketch_name": "FuselageProfile",
            "scale": 1.0
        }
    """
    freecad = get_freecad_connection()
    return _import_dxf(ctx, freecad, add_screenshot_if_available, doc_name, file_path, sketch_name, scale)


def main():
    """Run the MCP server"""
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    parser.add_argument("--host", type=_validate_host, default="localhost", help="Host address of the FreeCAD RPC server to connect to (default: localhost)")
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(f"Connecting to FreeCAD RPC server at: {state.rpc_host}")

    if not hasattr(sys.stdin, "buffer"):
        print(
            "ERROR: freecad-mcp must be launched as a subprocess by an MCP client (e.g. Claude Desktop, opencode).\n"
            "       The stdio transport requires a real stdin pipe — running it directly in a shell or backgrounded is not supported.",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp.run()
