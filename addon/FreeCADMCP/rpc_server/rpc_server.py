import FreeCAD
import FreeCADGui
import ObjectsFem

import contextlib
import ipaddress
import json
import logging
import queue
import re
import base64
import io
import os
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.server import SimpleXMLRPCServer

from PySide import QtCore, QtGui, QtWidgets

from .parts_library import get_parts_list, insert_part_from_library
from .serialize import serialize_object

rpc_server_thread = None
rpc_server_instance = None


_MAX_LOG_STR = 120


def _truncate_params(params):
    """Return a loggable, length-capped representation of RPC call params."""
    def _trunc(v):
        if isinstance(v, str):
            if len(v) > _MAX_LOG_STR:
                return f"{v[:_MAX_LOG_STR]}…[{len(v)} chars]"
            return v
        if isinstance(v, (list, tuple)):
            truncated = [_trunc(x) for x in v[:6]]
            if len(v) > 6:
                truncated.append(f"…+{len(v) - 6} more")
            return truncated
        if isinstance(v, dict):
            return {k: _trunc(vv) for k, vv in list(v.items())[:8]}
        return v
    return [_trunc(p) for p in params]


# --- Settings persistence ---

_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_server": True,
    "startup_remote_enabled": False,
    "log_enabled": False,
    "log_path": "",
}


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                settings = json.load(f)
            # Ensure all default keys exist
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Failed to load MCP settings: {e}\n")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings):
    path = _get_settings_path()
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")


_logger = logging.getLogger("freecad_mcp")


def _setup_logging(settings):
    # Remove any existing handlers so toggling via the GUI doesn't stack duplicates.
    for h in list(_logger.handlers):
        _logger.removeHandler(h)
        h.close()

    if not settings.get("log_enabled", False):
        _logger.setLevel(logging.NOTSET)
        return

    log_path = settings.get("log_path", "").strip() or os.path.join(
        FreeCAD.getUserAppDataDir(), "freecad_mcp.log"
    )
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG)
    _logger.info("FreeCAD MCP addon logging started")


# --- IP-filtered XML-RPC server ---

class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """XML-RPC server that filters connections by allowed IP addresses/subnets."""

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        super().__init__(addr, **kwargs)

    def _dispatch(self, method, params):
        start = time.monotonic()
        _logger.debug("RPC → %s %s", method, _truncate_params(params))
        result = super()._dispatch(method, params)
        elapsed = time.monotonic() - start
        if isinstance(result, dict):
            if result.get("error"):
                _logger.warning("RPC ← %s FAIL (%.2fs): %s", method, elapsed, result["error"])
            else:
                _logger.debug("RPC ← %s OK (%.2fs)", method, elapsed)
        else:
            _logger.debug("RPC ← %s (%.2fs)", method, elapsed)
        return result

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        try:
            addr = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if addr in network:
                    return True
        except ValueError:
            pass
        FreeCAD.Console.PrintWarning(
            f"MCP RPC: Rejected connection from {client_ip}\n"
        )
        return False


_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def validate_allowed_ips(allowed_ips_str):
    """Validate a comma-separated string of IP addresses/subnets.

    Returns a ``(valid, errors)`` tuple.  ``valid`` is a list of normalised
    entry strings that passed validation; ``errors`` is a list of
    human-readable error messages (empty when the input is fully valid).

    Checks performed:
    1. The overall string is well-formed comma-separated (no leading/trailing
       commas, no empty entries between commas, not blank).
    2. Each individual entry is a valid IPv4/IPv6 address or CIDR subnet
       (validated via the stdlib ``ipaddress`` module).
    """
    errors = []

    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]

    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        ]

    valid = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(allowed_ips_str):
    """Parse a comma-separated string of IPs/subnets into a list of ip_network objects."""
    valid, errors = validate_allowed_ips(allowed_ips_str)
    for msg in errors:
        FreeCAD.Console.PrintWarning(f"MCP RPC: {msg}, skipping\n")
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]

# GUI task queue
rpc_request_queue = queue.Queue()
rpc_response_queue = queue.Queue()


def _flush_gui_events(delay_ms: int = 50) -> None:
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    app.processEvents(QtCore.QEventLoop.AllEvents, delay_ms)
    if delay_ms > 0:
        QtCore.QThread.msleep(delay_ms)
        app.processEvents(QtCore.QEventLoop.AllEvents, delay_ms)


def _get_view_size(view: Any) -> tuple[int, int]:
    try:
        size = view.getSize()
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return max(1, int(size[0])), max(1, int(size[1]))
        return max(1, int(size.width())), max(1, int(size.height()))
    except Exception:
        return 1024, 768


def _resolve_screenshot_size(
    view: Any,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    view_width, view_height = _get_view_size(view)
    resolved_width = view_width if width is None else max(1, int(width))
    resolved_height = view_height if height is None else max(1, int(height))
    return resolved_width, resolved_height


def process_gui_tasks():
    try:
        while not rpc_request_queue.empty():
            task = rpc_request_queue.get()
            try:
                res = task()
                if res is not None:
                    rpc_response_queue.put(res)
            except Exception as e:
                tb = traceback.format_exc()
                _logger.error("GUI task raised an exception: %s\n%s", e, tb)
                FreeCAD.Console.PrintError(f"MCP GUI task error: {e}\n{tb}")
                rpc_response_queue.put(f"GUI task error: {e}")
    finally:
        QtCore.QTimer.singleShot(500, process_gui_tasks)


@dataclass
class Object:
    name: str
    type: str | None = None
    analysis: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def set_object_property(
    doc: FreeCAD.Document, obj: FreeCAD.DocumentObject, properties: dict[str, Any]
):
    for prop, val in properties.items():
        try:
            if prop in obj.PropertiesList:
                if prop == "Placement" and isinstance(val, dict):
                    if "Base" in val:
                        pos = val["Base"]
                    elif "Position" in val:
                        pos = val["Position"]
                    else:
                        pos = {}
                    rot = val.get("Rotation", {})
                    placement = FreeCAD.Placement(
                        FreeCAD.Vector(
                            pos.get("x", 0),
                            pos.get("y", 0),
                            pos.get("z", 0),
                        ),
                        FreeCAD.Rotation(
                            FreeCAD.Vector(
                                rot.get("Axis", {}).get("x", 0),
                                rot.get("Axis", {}).get("y", 0),
                                rot.get("Axis", {}).get("z", 1),
                            ),
                            rot.get("Angle", 0),
                        ),
                    )
                    setattr(obj, prop, placement)

                elif isinstance(getattr(obj, prop), FreeCAD.Vector) and isinstance(
                    val, dict
                ):
                    vector = FreeCAD.Vector(
                        val.get("x", 0), val.get("y", 0), val.get("z", 0)
                    )
                    setattr(obj, prop, vector)

                elif prop in ["Base", "Tool", "Source", "Profile"] and isinstance(
                    val, str
                ):
                    ref_obj = doc.getObject(val)
                    if ref_obj:
                        setattr(obj, prop, ref_obj)
                    else:
                        raise ValueError(f"Referenced object '{val}' not found.")

                elif prop == "References" and isinstance(val, list):
                    refs = []
                    for ref_name, face in val:
                        ref_obj = doc.getObject(ref_name)
                        if ref_obj:
                            refs.append((ref_obj, face))
                        else:
                            raise ValueError(f"Referenced object '{ref_name}' not found.")
                    setattr(obj, prop, refs)

                else:
                    setattr(obj, prop, val)
            # ShapeColor is a property of the ViewObject
            elif prop == "ShapeColor" and isinstance(val, (list, tuple)):
                setattr(obj.ViewObject, prop, (float(val[0]), float(val[1]), float(val[2]), float(val[3])))

            elif prop == "ViewObject" and isinstance(val, dict):
                for k, v in val.items():
                    if k == "ShapeColor":
                        setattr(obj.ViewObject, k, (float(v[0]), float(v[1]), float(v[2]), float(v[3])))
                    else:
                        setattr(obj.ViewObject, k, v)

            else:
                setattr(obj, prop, val)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Property '{prop}' assignment error: {e}\n")


class FreeCADRPC:
    """RPC server for FreeCAD"""
    TIMEOUT = 10

    def ping(self):
        return True

    def create_document(self, name="New_Document"):
        rpc_request_queue.put(lambda: self._create_document_gui(name))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "data": {"document_name": name}, "error": None}
        else:
            return {"success": False, "data": None, "error": res}

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._create_object_gui(doc_name, obj))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "data": {"object_name": obj.name}, "error": None}
        else:
            return {"success": False, "data": None, "error": res}

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._edit_object_gui(doc_name, obj))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "data": {"object_name": obj.name}, "error": None}
        else:
            return {"success": False, "data": None, "error": res}

    def delete_object(self, doc_name: str, obj_name: str):
        rpc_request_queue.put(lambda: self._delete_object_gui(doc_name, obj_name))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "data": {"object_name": obj_name}, "error": None}
        else:
            return {"success": False, "data": None, "error": res}

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
        try:
            timeout_s = int(timeout)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid timeout: {timeout!r}"}
        rpc_request_queue.put(lambda: self._run_fem_analysis_gui(doc_name, analysis_name))
        try:
            res = rpc_response_queue.get(timeout=timeout_s)
        except queue.Empty:
            return {"success": False, "error": f"solver did not return within {timeout_s}s (still running on the GUI thread)"}
        if isinstance(res, dict):
            return res
        return {"success": False, "error": str(res)}

    def execute_code(self, code: str) -> dict[str, Any]:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        def task():
            try:
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    sandbox = {
                        "__builtins__": __builtins__,
                        "FreeCAD": FreeCAD,
                        "FreeCADGui": FreeCADGui,
                    }
                    exec(code, sandbox)
                FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
                return True
            except Exception:
                tb = traceback.format_exc()
                FreeCAD.Console.PrintError(f"Error executing Python code:\n{tb}\n")
                return tb

        rpc_request_queue.put(task)
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        stdout = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()
        if res is True:
            return {
                "success": True,
                "data": {"output": stdout, "stderr": stderr},
                "error": None,
            }
        else:
            return {
                "success": False,
                "data": {"output": stdout, "stderr": stderr, "traceback": res},
                "error": res.splitlines()[-1] if res else "Unknown error",
            }

    def get_objects(self, doc_name):
        rpc_request_queue.put(lambda: self._get_objects_gui(doc_name))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def get_object(self, doc_name, obj_name):
        rpc_request_queue.put(lambda: self._get_object_gui(doc_name, obj_name))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def get_status(self) -> dict:
        rpc_request_queue.put(lambda: self._get_status_gui())
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def insert_part_from_library(self, relative_path):
        rpc_request_queue.put(lambda: self._insert_part_from_library(relative_path))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "data": None, "error": None}
        else:
            return {"success": False, "data": None, "error": res}

    def get_shape_topology(self, doc_name: str, obj_name: str) -> dict:
        rpc_request_queue.put(lambda: self._get_shape_topology_gui(doc_name, obj_name))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def save_document(self, doc_name: str, path: str = "") -> dict:
        rpc_request_queue.put(lambda: self._save_document_gui(doc_name, path))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def load_document(self, path: str) -> dict:
        rpc_request_queue.put(lambda: self._load_document_gui(path))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def measure_object(self, doc_name: str, obj_name: str) -> dict:
        rpc_request_queue.put(lambda: self._measure_object_gui(doc_name, obj_name))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def set_object_visibility(self, doc_name: str, obj_name: str, visible: bool) -> dict:
        rpc_request_queue.put(lambda: self._set_object_visibility_gui(doc_name, obj_name, visible))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def undo(self, doc_name: str, steps: int = 1) -> dict:
        rpc_request_queue.put(lambda: self._undo_gui(doc_name, steps))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def export_object(self, doc_name: str, obj_name: str, path: str, export_format: str) -> dict:
        rpc_request_queue.put(lambda: self._export_object_gui(doc_name, obj_name, path, export_format))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def spreadsheet_read(self, doc_name: str, sheet_name: str, cell_range: str) -> dict:
        rpc_request_queue.put(lambda: self._spreadsheet_read_gui(doc_name, sheet_name, cell_range))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def spreadsheet_write(self, doc_name: str, sheet_name: str, cell: str, value) -> dict:
        rpc_request_queue.put(lambda: self._spreadsheet_write_gui(doc_name, sheet_name, cell, value))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def copy_object(self, doc_name: str, obj_name: str, new_name: str) -> dict:
        rpc_request_queue.put(lambda: self._copy_object_gui(doc_name, obj_name, new_name))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def create_techdraw_page(self, doc_name: str, page_name: str, template_path: str = "") -> dict:
        rpc_request_queue.put(lambda: self._create_techdraw_page_gui(doc_name, page_name, template_path))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def add_view_to_techdraw_page(self, doc_name: str, page_name: str, obj_name: str, view_name: str, x: float = 100.0, y: float = 100.0, scale: float = 1.0) -> dict:
        rpc_request_queue.put(lambda: self._add_view_to_techdraw_page_gui(doc_name, page_name, obj_name, view_name, x, y, scale))
        return rpc_response_queue.get(timeout=self.TIMEOUT)

    def list_documents(self):
        return {"success": True, "data": list(FreeCAD.listDocuments().keys()), "error": None}

    def get_parts_list(self):
        try:
            return {"success": True, "data": get_parts_list(), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def get_active_screenshot(self, view_name: str = "Isometric", width: int | None = None, height: int | None = None, focus_object: str | None = None) -> str:
        """Get a screenshot of the active view.
        
        Returns a base64-encoded string of the screenshot or None if a screenshot
        cannot be captured (e.g., when in TechDraw or Spreadsheet view).
        """
        # First check if the active view supports screenshots
        def check_view_supports_screenshots():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
                if active_view is None:
                    FreeCAD.Console.PrintWarning("No active view available\n")
                    return False
                
                view_type = type(active_view).__name__
                has_save_image = hasattr(active_view, 'saveImage')
                FreeCAD.Console.PrintMessage(f"View type: {view_type}, Has saveImage: {has_save_image}\n")
                return has_save_image
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error checking view capabilities: {e}\n")
                return False
                
        rpc_request_queue.put(check_view_supports_screenshots)
        supports_screenshots = rpc_response_queue.get(timeout=self.TIMEOUT)
        
        if not supports_screenshots:
            FreeCAD.Console.PrintWarning("Current view does not support screenshots\n")
            return None
            
        # If view supports screenshots, proceed with capture
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        rpc_request_queue.put(
            lambda: self._save_active_screenshot(tmp_path, view_name, width, height, focus_object)
        )
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            try:
                with open(tmp_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return encoded
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            FreeCAD.Console.PrintWarning(f"Failed to capture screenshot: {res}\n")
            return None

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
        return True

    def _create_object_gui(self, doc_name, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            try:
                if obj.type == "Fem::FemMeshGmsh" and obj.analysis:
                    from femmesh.gmshtools import GmshTools
                    res = getattr(doc, obj.analysis).addObject(ObjectsFem.makeMeshGmsh(doc, obj.name))[0]
                    # FreeCAD 1.x renamed the Gmsh-mesh geometry link from "Part" to "Shape"
                    # and the size limits from "ElementSize{Max,Min}" to "CharacteristicLength{Max,Min}".
                    # Accept both spellings so older snippets keep working.
                    geom_attr = "Shape" if hasattr(res, "Shape") else ("Part" if hasattr(res, "Part") else None)
                    legacy_to_new = {
                        "Part": geom_attr,
                        "ElementSizeMax": "CharacteristicLengthMax",
                        "ElementSizeMin": "CharacteristicLengthMin",
                    }
                    geom_key = "Part" if "Part" in obj.properties else ("Shape" if "Shape" in obj.properties else None)
                    if geom_key is None:
                        raise ValueError("'Part' (or 'Shape') property not found in properties.")
                    target_obj = doc.getObject(obj.properties[geom_key])
                    if target_obj is None:
                        raise ValueError(f"Referenced object '{obj.properties[geom_key]}' not found.")
                    if geom_attr is None:
                        raise ValueError("Mesh object has neither 'Shape' nor 'Part' property.")
                    setattr(res, geom_attr, target_obj)
                    del obj.properties[geom_key]

                    for param, value in obj.properties.items():
                        target_param = legacy_to_new.get(param, param)
                        if target_param and hasattr(res, target_param):
                            setattr(res, target_param, value)
                    doc.recompute()

                    gmsh_tools = GmshTools(res)
                    gmsh_tools.create_mesh()
                    FreeCAD.Console.PrintMessage(
                        f"FEM Mesh '{res.Name}' generated successfully in '{doc_name}'.\n"
                    )
                elif obj.type.startswith("Fem::"):
                    fem_make_methods = {
                        "MaterialCommon": ObjectsFem.makeMaterialSolid,
                        "AnalysisPython": ObjectsFem.makeAnalysis,
                    }
                    obj_type_short = obj.type.split("::")[1]
                    method_name = "make" + obj_type_short
                    make_method = fem_make_methods.get(obj_type_short, getattr(ObjectsFem, method_name, None))

                    if callable(make_method):
                        res = make_method(doc, obj.name)
                        set_object_property(doc, res, obj.properties)
                        FreeCAD.Console.PrintMessage(
                            f"FEM object '{res.Name}' created with '{method_name}'.\n"
                        )
                    else:
                        raise ValueError(f"No creation method '{method_name}' found in ObjectsFem.")
                    if obj.type != "Fem::AnalysisPython" and obj.analysis:
                        getattr(doc, obj.analysis).addObject(res)
                elif obj.type.startswith("Draft::"):
                    import Draft
                    draft_type = obj.type.split("::")[1]
                    props = obj.properties

                    if draft_type == "Circle":
                        radius = float(props.get("Radius", 1.0))
                        first_angle = float(props.get("FirstAngle", 0))
                        last_angle = float(props.get("LastAngle", 360))
                        res = Draft.makeCircle(
                            radius,
                            face=False,
                            startangle=first_angle,
                            endangle=last_angle,
                        )
                    elif draft_type == "Rectangle":
                        length = float(props.get("Length", 1.0))
                        width = float(props.get("Width", 1.0))
                        res = Draft.makeRectangle(length, width)
                    elif draft_type == "Wire":
                        raw_points = props.get("Points", [])
                        points = [
                            FreeCAD.Vector(p["x"], p["y"], p["z"])
                            if isinstance(p, dict)
                            else p
                            for p in raw_points
                        ]
                        res = Draft.makeWire(points)
                    elif draft_type == "Line":
                        start = props.get("Start", {})
                        end = props.get("End", {})
                        p1 = FreeCAD.Vector(start["x"], start["y"], start["z"])
                        p2 = FreeCAD.Vector(end["x"], end["y"], end["z"])
                        res = Draft.makeLine(p1, p2)
                    else:
                        raise ValueError(f"Unsupported Draft type: '{obj.type}'.")

                    res.Label = obj.name
                    FreeCAD.Console.PrintMessage(
                        f"Draft object '{res.Name}' ({obj.type}) created in '{doc_name}'.\n"
                    )
                else:
                    res = doc.addObject(obj.type, obj.name)
                    set_object_property(doc, res, obj.properties)
                    FreeCAD.Console.PrintMessage(
                        f"{res.TypeId} '{res.Name}' added to '{doc_name}' via RPC.\n"
                    )
 
                doc.recompute()
                return True
            except Exception as e:
                return str(e)
        else:
            open_docs = list(FreeCAD.listDocuments().keys())
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found. Open documents: {open_docs}"

    def _edit_object_gui(self, doc_name: str, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            open_docs = list(FreeCAD.listDocuments().keys())
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found. Open documents: {open_docs}"

        obj_ins = doc.getObject(obj.name)
        if not obj_ins:
            available = [o.Name for o in doc.Objects]
            FreeCAD.Console.PrintError(f"Object '{obj.name}' not found in document '{doc_name}'.\n")
            return f"Object '{obj.name}' not found in '{doc_name}'. Available: {available}"

        try:
            # For Fem::ConstraintFixed
            if hasattr(obj_ins, "References") and "References" in obj.properties:
                refs = []
                for ref_name, face in obj.properties["References"]:
                    ref_obj = doc.getObject(ref_name)
                    if ref_obj:
                        refs.append((ref_obj, face))
                    else:
                        raise ValueError(f"Referenced object '{ref_name}' not found.")
                obj_ins.References = refs
                FreeCAD.Console.PrintMessage(
                    f"References updated for '{obj.name}' in '{doc_name}'.\n"
                )
                # delete References from properties
                del obj.properties["References"]
            set_object_property(doc, obj_ins, obj.properties)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _run_fem_analysis_gui(self, doc_name: str, analysis_name: str):
        # MUST always return a dict — process_gui_tasks treats None as no-response,
        # and the caller would block until its timeout. Keep the broad except.
        work_dir = None
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "error": f"Document '{doc_name}' not found."}
            analysis = doc.getObject(analysis_name)
            if analysis is None:
                return {"success": False, "error": f"Analysis '{analysis_name}' not found."}
            if analysis.TypeId not in ("Fem::FemAnalysis", "Fem::FemAnalysisPython"):
                return {"success": False, "error": f"'{analysis_name}' is not a FEM analysis (TypeId={analysis.TypeId})."}

            solver = None
            for member in analysis.Group:
                tid = getattr(member, "TypeId", "")
                if "SolverCcx" in tid or "SolverCalculix" in tid:
                    solver = member
                    break
            if solver is None:
                solver_factory = (
                    getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None)
                    or getattr(ObjectsFem, "makeSolverCalculixCcxTools", None)
                )
                if solver_factory is None:
                    return {"success": False, "error": "ObjectsFem has no Calculix solver factory."}
                solver = solver_factory(doc, "CalculiX")
                analysis.addObject(solver)

            from femtools import ccxtools

            fea = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
            fea.update_objects()

            work_dir = tempfile.mkdtemp(prefix="freecad_mcp_fem_")
            fea.setup_working_dir(work_dir)
            fea.setup_ccx()

            prereq_msg = fea.check_prerequisites()
            if prereq_msg:
                return {"success": False, "error": f"Prerequisites failed: {prereq_msg}", "working_dir": work_dir}

            fea.purge_results()
            fea.run()
            fea.load_results()

            result_obj = None
            for member in analysis.Group:
                if "Result" in getattr(member, "TypeId", "") and hasattr(member, "vonMises"):
                    result_obj = member
                    break
            if result_obj is None:
                return {"success": False, "error": "Solver ran but no result object was produced.", "working_dir": work_dir}

            # vonMises / DisplacementLengths can be None on a degenerate run.
            vm = list(getattr(result_obj, "vonMises", None) or [])
            disp = list(getattr(result_obj, "DisplacementLengths", None) or [])
            doc.recompute()

            return {
                "success": True,
                "result_object": result_obj.Name,
                "node_count": len(vm),
                "max_von_mises_MPa": max(vm) if vm else None,
                "min_von_mises_MPa": min(vm) if vm else None,
                "max_displacement_mm": max(disp) if disp else None,
                "working_dir": work_dir,
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
                "working_dir": work_dir,
            }

    def _delete_object_gui(self, doc_name: str, obj_name: str):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            open_docs = list(FreeCAD.listDocuments().keys())
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found. Open documents: {open_docs}"

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
            if FreeCAD.ActiveDocument:
                FreeCAD.ActiveDocument.recompute()
            return True
        except Exception as e:
            return str(e)

    def _get_shape_topology_gui(self, doc_name: str, obj_name: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                open_docs = list(FreeCAD.listDocuments().keys())
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found. Open documents: {open_docs}"}
            obj = doc.getObject(obj_name)
            if not obj:
                available = [o.Name for o in doc.Objects]
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found in '{doc_name}'. Available: {available}"}
            if not hasattr(obj, "Shape") or obj.Shape.isNull():
                return {"success": False, "data": None, "error": f"Object '{obj_name}' has no valid shape. It may need to be recomputed."}

            shape = obj.Shape

            faces = []
            for i, face in enumerate(shape.Faces):
                try:
                    com = face.CenterOfMass
                    centroid = {"x": com.x, "y": com.y, "z": com.z}
                    try:
                        normal = face.normalAt(0, 0)
                        normal_dict = {"x": round(normal.x, 6), "y": round(normal.y, 6), "z": round(normal.z, 6)}
                    except Exception:
                        normal_dict = None
                    faces.append({
                        "name": f"Face{i + 1}",
                        "index": i + 1,
                        "area": round(face.Area, 4),
                        "normal": normal_dict,
                        "centroid": {k: round(v, 4) for k, v in centroid.items()},
                    })
                except Exception as e:
                    faces.append({"name": f"Face{i + 1}", "index": i + 1, "error": str(e)})

            edges = []
            for i, edge in enumerate(shape.Edges):
                try:
                    curve_type = type(edge.Curve).__name__
                    edges.append({
                        "name": f"Edge{i + 1}",
                        "index": i + 1,
                        "length": round(edge.Length, 4),
                        "curve_type": curve_type,
                    })
                except Exception as e:
                    edges.append({"name": f"Edge{i + 1}", "index": i + 1, "error": str(e)})

            vertices = []
            for i, vtx in enumerate(shape.Vertexes):
                vertices.append({
                    "name": f"Vertex{i + 1}",
                    "index": i + 1,
                    "x": round(vtx.X, 4),
                    "y": round(vtx.Y, 4),
                    "z": round(vtx.Z, 4),
                })

            return {
                "success": True,
                "data": {
                    "object": obj_name,
                    "document": doc_name,
                    "face_count": len(faces),
                    "edge_count": len(edges),
                    "vertex_count": len(vertices),
                    "faces": faces,
                    "edges": edges,
                    "vertices": vertices,
                },
                "error": None,
            }
        except Exception as e:
            import traceback
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}

    def _save_document_gui(self, doc_name: str, path: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                open_docs = list(FreeCAD.listDocuments().keys())
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found. Open documents: {open_docs}"}
            if path:
                doc.saveAs(path)
                saved_path = path
            else:
                if not doc.FileName:
                    return {"success": False, "data": None, "error": f"Document '{doc_name}' has never been saved. Provide a path to save it for the first time."}
                doc.save()
                saved_path = doc.FileName
            return {"success": True, "data": {"document": doc_name, "path": saved_path}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _load_document_gui(self, path: str) -> dict:
        try:
            doc = FreeCAD.open(path)
            if doc is None:
                return {"success": False, "data": None, "error": f"FreeCAD.open() returned None for path: {path}"}
            return {"success": True, "data": {"document": doc.Name, "path": path}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _measure_object_gui(self, doc_name: str, obj_name: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                open_docs = list(FreeCAD.listDocuments().keys())
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found. Open documents: {open_docs}"}
            obj = doc.getObject(obj_name)
            if not obj:
                available = [o.Name for o in doc.Objects]
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found in '{doc_name}'. Available: {available}"}
            if not hasattr(obj, "Shape") or obj.Shape.isNull():
                return {"success": False, "data": None, "error": f"Object '{obj_name}' has no valid shape."}

            shape = obj.Shape
            bb = shape.BoundBox

            data = {
                "object": obj_name,
                "document": doc_name,
                "bounding_box": {
                    "x_min": round(bb.XMin, 4), "x_max": round(bb.XMax, 4),
                    "y_min": round(bb.YMin, 4), "y_max": round(bb.YMax, 4),
                    "z_min": round(bb.ZMin, 4), "z_max": round(bb.ZMax, 4),
                    "x_size": round(bb.XLength, 4),
                    "y_size": round(bb.YLength, 4),
                    "z_size": round(bb.ZLength, 4),
                },
                "volume": round(shape.Volume, 4),
                "surface_area": round(shape.Area, 4),
            }

            try:
                com = shape.CenterOfMass
                data["center_of_mass"] = {"x": round(com.x, 4), "y": round(com.y, 4), "z": round(com.z, 4)}
            except Exception:
                data["center_of_mass"] = None

            return {"success": True, "data": data, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _set_object_visibility_gui(self, doc_name: str, obj_name: str, visible: bool) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            obj = doc.getObject(obj_name)
            if not obj:
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found"}
            obj.ViewObject.Visibility = visible
            return {"success": True, "data": {"obj_name": obj_name, "visible": visible}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _undo_gui(self, doc_name: str, steps: int = 1) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            if not doc.UndoMode:
                return {"success": False, "data": None,
                        "error": "Undo not enabled on this document. Documents must be opened via the FreeCAD GUI to enable undo tracking."}
            for _ in range(steps):
                doc.undo()
            return {"success": True, "data": {"steps_undone": steps}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _export_object_gui(self, doc_name: str, obj_name: str, path: str, export_format: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            obj = doc.getObject(obj_name)
            if not obj:
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found"}
            fmt = export_format.lower()
            import os
            ext_map = {"step": ".step", "iges": ".iges", "stl": ".stl", "obj": ".obj"}
            expected_ext = ext_map.get(fmt, "")
            _, actual_ext = os.path.splitext(path)
            if actual_ext.lower() != expected_ext:
                path = os.path.splitext(path)[0] + expected_ext
            if fmt in ("step", "iges"):
                import Part
                Part.export([obj], path)
            elif fmt in ("stl", "obj"):
                import Mesh
                Mesh.export([obj], path)
            else:
                return {"success": False, "data": None, "error": f"Unsupported format '{export_format}'. Use: step, stl, obj, iges"}
            return {"success": True, "data": {"path": path, "format": export_format}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _read_cell(sheet, addr: str):
        """Read a spreadsheet cell, returning the computed value.

        Tries sheet.get() first (returns evaluated quantity/float/str).
        Falls back to sheet.getContents() for older FreeCAD versions.
        Unwraps FreeCAD Quantity objects to their numeric Value.
        """
        try:
            val = sheet.get(addr)
        except AttributeError:
            val = sheet.getContents(addr)
        if hasattr(val, "Value"):
            val = val.Value
        return val

    def _spreadsheet_read_gui(self, doc_name: str, sheet_name: str, cell_range: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return {"success": False, "data": None, "error": f"Sheet '{sheet_name}' not found"}
            cells = {}
            if ":" in cell_range:
                start, end = cell_range.split(":", 1)
                # Parse column letters and row numbers
                import re
                def parse_cell(c):
                    m = re.match(r"([A-Za-z]+)(\d+)", c.strip())
                    if not m:
                        raise ValueError(f"Invalid cell address: {c}")
                    return m.group(1).upper(), int(m.group(2))
                start_col, start_row = parse_cell(start)
                end_col, end_row = parse_cell(end)
                # Convert column letters to indices
                def col_to_idx(col):
                    idx = 0
                    for ch in col:
                        idx = idx * 26 + (ord(ch) - ord('A') + 1)
                    return idx
                def idx_to_col(idx):
                    result = ""
                    while idx > 0:
                        idx, rem = divmod(idx - 1, 26)
                        result = chr(ord('A') + rem) + result
                    return result
                sc = col_to_idx(start_col)
                ec = col_to_idx(end_col)
                for r in range(start_row, end_row + 1):
                    for c in range(sc, ec + 1):
                        addr = f"{idx_to_col(c)}{r}"
                        try:
                            cells[addr] = self._read_cell(sheet, addr)
                        except Exception:
                            cells[addr] = None
            else:
                addr = cell_range.strip().upper()
                try:
                    cells[addr] = self._read_cell(sheet, addr)
                except Exception:
                    cells[addr] = None
            return {"success": True, "data": {"cells": cells}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _spreadsheet_write_gui(self, doc_name: str, sheet_name: str, cell: str, value) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return {"success": False, "data": None, "error": f"Sheet '{sheet_name}' not found"}
            sheet.set(cell, str(value))
            sheet.recompute()
            doc.recompute()
            return {"success": True, "data": {"cell": cell, "value": value}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _copy_object_gui(self, doc_name: str, obj_name: str, new_name: str) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            obj = doc.getObject(obj_name)
            if not obj:
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found"}
            new_obj = doc.copyObject(obj, True)
            new_obj.Label = new_name
            doc.recompute()
            return {"success": True, "data": {"original": obj_name, "copy": new_obj.Name, "label": new_name}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _create_techdraw_page_gui(self, doc_name: str, page_name: str, template_path: str = "") -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            page = doc.addObject("TechDraw::DrawPage", page_name)
            if template_path:
                template = doc.addObject("TechDraw::DrawSVGTemplate", page_name + "_template")
                template.Template = template_path
                page.Template = template
            doc.recompute()
            return {"success": True, "data": {"page_name": page.Name, "label": page_name}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _add_view_to_techdraw_page_gui(self, doc_name: str, page_name: str, obj_name: str, view_name: str, x: float = 100.0, y: float = 100.0, scale: float = 1.0) -> dict:
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found"}
            page = doc.getObject(page_name)
            if not page:
                return {"success": False, "data": None, "error": f"Page '{page_name}' not found"}
            obj = doc.getObject(obj_name)
            if not obj:
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found"}
            view = doc.addObject("TechDraw::DrawViewPart", view_name)
            view.Source = [obj]
            view.X = x
            view.Y = y
            view.Scale = scale
            page.addView(view)
            doc.recompute()
            return {"success": True, "data": {"view_name": view.Name, "page": page_name, "object": obj_name}, "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"{type(e).__name__}: {e}"}

    def _get_objects_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if doc is None:
                open_docs = list(FreeCAD.listDocuments().keys())
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found. Open documents: {open_docs}"}
            return {"success": True, "data": [serialize_object(obj) for obj in doc.Objects], "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"Failed to get objects: {type(e).__name__}: {e}"}

    def _get_object_gui(self, doc_name, obj_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if doc is None:
                open_docs = list(FreeCAD.listDocuments().keys())
                return {"success": False, "data": None, "error": f"Document '{doc_name}' not found. Open documents: {open_docs}"}
            obj = doc.getObject(obj_name)
            if not obj:
                available = [o.Name for o in doc.Objects]
                return {"success": False, "data": None, "error": f"Object '{obj_name}' not found in '{doc_name}'. Available: {available}"}
            return {"success": True, "data": serialize_object(obj), "error": None}
        except Exception as e:
            return {"success": False, "data": None, "error": f"Failed to get object: {type(e).__name__}: {e}"}

    def _get_status_gui(self) -> dict:
        try:
            open_docs = list(FreeCAD.listDocuments().keys())
            active_doc = None
            active_workbench = None
            active_body = None

            if FreeCAD.ActiveDocument:
                active_doc = FreeCAD.ActiveDocument.Name

            try:
                active_workbench = FreeCADGui.activeWorkbench().name()
            except Exception:
                pass

            try:
                import PartDesignGui
                body = PartDesignGui.getBody(False)
                if body:
                    active_body = body.Name
            except Exception:
                pass

            return {
                "success": True,
                "data": {
                    "active_document": active_doc,
                    "open_documents": open_docs,
                    "active_workbench": active_workbench,
                    "active_body": active_body,
                    "rpc_port": 9875,
                    "timer_chain": "running",
                },
                "error": None,
            }
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    def _save_active_screenshot(
        self,
        save_path: str,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ):
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
            # Check if the view supports screenshots
            if not hasattr(view, 'saveImage'):
                return "Current view does not support screenshots"
                
            if view_name == "Isometric":
                view.viewIsometric()
            elif view_name == "Front":
                view.viewFront()
            elif view_name == "Top":
                view.viewTop()
            elif view_name == "Right":
                view.viewRight()
            elif view_name == "Back":
                view.viewBack()
            elif view_name == "Left":
                view.viewLeft()
            elif view_name == "Bottom":
                view.viewBottom()
            elif view_name == "Dimetric":
                view.viewDimetric()
            elif view_name == "Trimetric":
                view.viewTrimetric()
            else:
                raise ValueError(f"Invalid view name: {view_name}")

            focused_selection = False

            # Focus on specific object or fit all
            if focus_object:
                doc = FreeCAD.ActiveDocument
                obj = doc.getObject(focus_object) if doc else None
                if obj:
                    FreeCADGui.Selection.clearSelection()
                    FreeCADGui.Selection.addSelection(obj)
                    FreeCADGui.SendMsgToActiveView("ViewSelection")
                    focused_selection = True
                    _flush_gui_events()
                    FreeCADGui.Selection.clearSelection()
                else:
                    view.fitAll()
            else:
                view.fitAll()

            _flush_gui_events()
            width, height = _resolve_screenshot_size(view, width, height)
            view.saveImage(save_path, width, height, "Current")

            if focused_selection:
                FreeCADGui.Selection.clearSelection()
                _flush_gui_events(delay_ms=0)
            return True
        except Exception as e:
            return str(e)


def _make_status_icon(color):
    """Create a small filled-circle icon in the given QColor."""
    pixmap = QtGui.QPixmap(16, 16)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setBrush(QtGui.QBrush(color))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QtGui.QIcon(pixmap)


_ICON_RUNNING = None  # built lazily after Qt is ready
_ICON_STOPPED = None

_COLOR_RUNNING = QtGui.QColor(76, 175, 80)   # Material Green 500
_COLOR_STOPPED = QtGui.QColor(190, 58, 50)   # Muted red


def _get_icon_running():
    global _ICON_RUNNING
    if _ICON_RUNNING is None:
        _ICON_RUNNING = _make_status_icon(_COLOR_RUNNING)
    return _ICON_RUNNING


def _get_icon_stopped():
    global _ICON_STOPPED
    if _ICON_STOPPED is None:
        _ICON_STOPPED = _make_status_icon(_COLOR_STOPPED)
    return _ICON_STOPPED


# Action references, populated once by _init_gui().
_actions: dict[str, list] = {}


def _update_server_action():
    """Update server toggle button icon and text."""
    running = rpc_server_instance is not None
    icon = _get_icon_running() if running else _get_icon_stopped()
    for a in _actions.get("server_button", []):
        a.setIcon(icon)
        if running:
            a.setText("Stop Server")
            a.setToolTip("Stop the MCP RPC server.")
        else:
            a.setText("Start Server")
            a.setToolTip("Start the MCP RPC server.")


def _update_remote_action():
    """Update remote toggle button and configure-IPs visibility/count."""
    settings = load_settings()
    enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")
    ip_count = len([e for e in allowed_ips.split(",") if e.strip()])
    for a in _actions.get("remote_button", []):
        if enabled:
            a.setText("Disable Remote Access")
            a.setToolTip("Restrict to local connections only.")
        else:
            a.setText("Enable Remote Access")
            a.setToolTip("Allow connections from other machines on the network.")
    for a in _actions.get("configure_ips", []):
        a.setVisible(enabled)
        if enabled:
            a.setText(f"Configure Allowed IPs ({ip_count})")


def start_rpc_server(port=9875):
    global rpc_server_thread, rpc_server_instance

    if rpc_server_instance:
        return "RPC Server already running."

    settings = load_settings()
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")

    if remote_enabled:
        host = "0.0.0.0"
    else:
        host = "localhost"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(FreeCADRPC())

    def server_loop():
        FreeCAD.Console.PrintMessage(f"RPC Server started at {host}:{port}\n")
        if remote_enabled:
            FreeCAD.Console.PrintMessage(f"Remote connections enabled. Allowed IPs: {allowed_ips}\n")
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    QtCore.QTimer.singleShot(500, process_gui_tasks)
    _update_server_action()

    msg = f"RPC Server started at {host}:{port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread

    if rpc_server_instance:
        rpc_server_instance.shutdown()
        rpc_server_thread.join()
        rpc_server_instance = None
        rpc_server_thread = None
        _update_server_action()
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")
        return "RPC Server stopped."

    return "RPC Server was not running."


class StartupSettingsDialog(QtWidgets.QDialog):
    """Dialog for configuring startup defaults."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Startup Settings")
        self.setMinimumWidth(320)

        settings = load_settings()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Server group ---
        server_group = QtWidgets.QGroupBox("Server")
        server_layout = QtWidgets.QVBoxLayout(server_group)
        server_layout.setSpacing(8)
        server_layout.setContentsMargins(12, 12, 12, 12)

        self._server_on = QtWidgets.QRadioButton("Start automatically")
        self._server_off = QtWidgets.QRadioButton("Start manually")
        if settings.get("auto_start_server", True):
            self._server_on.setChecked(True)
        else:
            self._server_off.setChecked(True)

        server_layout.addWidget(self._server_on)
        server_layout.addWidget(self._server_off)
        layout.addWidget(server_group)

        # --- Remote access group ---
        remote_group = QtWidgets.QGroupBox("Remote Access")
        remote_layout = QtWidgets.QVBoxLayout(remote_group)
        remote_layout.setSpacing(8)
        remote_layout.setContentsMargins(12, 12, 12, 12)

        self._remote_on = QtWidgets.QRadioButton("Enable on startup")
        self._remote_off = QtWidgets.QRadioButton("Disable on startup")
        if settings.get("startup_remote_enabled", False):
            self._remote_on.setChecked(True)
        else:
            self._remote_off.setChecked(True)

        remote_layout.addWidget(self._remote_on)
        remote_layout.addWidget(self._remote_off)
        layout.addWidget(remote_group)

        # --- Logging group ---
        log_group = QtWidgets.QGroupBox("Logging")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setSpacing(8)
        log_layout.setContentsMargins(12, 12, 12, 12)

        self._log_enabled = QtWidgets.QCheckBox("Write logs to file")
        self._log_enabled.setChecked(settings.get("log_enabled", False))
        log_layout.addWidget(self._log_enabled)

        path_row = QtWidgets.QHBoxLayout()
        self._log_path = QtWidgets.QLineEdit()
        default_log = os.path.join(FreeCAD.getUserAppDataDir(), "freecad_mcp.log")
        self._log_path.setPlaceholderText(default_log)
        self._log_path.setText(settings.get("log_path", ""))
        self._log_path.setEnabled(self._log_enabled.isChecked())
        self._browse_btn = QtWidgets.QPushButton("Browse…")
        self._browse_btn.setEnabled(self._log_enabled.isChecked())
        self._browse_btn.clicked.connect(self._browse_log_path)
        path_row.addWidget(self._log_path)
        path_row.addWidget(self._browse_btn)
        log_layout.addLayout(path_row)

        self._log_enabled.toggled.connect(self._log_path.setEnabled)
        self._log_enabled.toggled.connect(self._browse_btn.setEnabled)

        layout.addWidget(log_group)

        # --- Buttons ---
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_log_path(self):
        current = self._log_path.text().strip() or os.path.join(
            FreeCAD.getUserAppDataDir(), "freecad_mcp.log"
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select Log File",
            current,
            "Log files (*.log);;All files (*)",
        )
        if path:
            self._log_path.setText(path)

    def accept(self):
        settings = load_settings()
        settings["auto_start_server"] = self._server_on.isChecked()
        settings["startup_remote_enabled"] = self._remote_on.isChecked()
        settings["log_enabled"] = self._log_enabled.isChecked()
        settings["log_path"] = self._log_path.text().strip()
        save_settings(settings)
        _setup_logging(settings)
        log_state = "enabled" if settings["log_enabled"] else "disabled"
        FreeCAD.Console.PrintMessage(
            f"Startup settings saved — server: "
            f"{'auto-start' if settings['auto_start_server'] else 'manual'}, "
            f"remote: {'enabled' if settings['startup_remote_enabled'] else 'disabled'}, "
            f"logging: {log_state}\n"
        )
        super().accept()


class ToggleRPCServerCommand:
    def GetResources(self):
        return {
            "MenuText": "Start Server",
            "ToolTip": "Start the MCP RPC server.",
        }

    def Activated(self):
        if rpc_server_instance:
            msg = stop_rpc_server()
        else:
            msg = start_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        return {
            "MenuText": "Enable Remote Access",
            "ToolTip": "Allow connections from other machines on the network.",
        }

    def Activated(self):
        settings = load_settings()
        settings["remote_enabled"] = not settings.get("remote_enabled", False)
        save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

        _update_remote_action()

    def IsActive(self):
        return True


class ConfigureAllowedIPsCommand:
    def GetResources(self):
        return {
            "MenuText": "Configure Allowed IPs",
            "ToolTip": "Set which IP addresses or subnets can connect when remote access is enabled.",
        }

    def Activated(self):
        settings = load_settings()
        current_ips = settings.get("allowed_ips", "127.0.0.1")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Allowed IP Addresses",
            "Enter allowed IP addresses or subnets (comma-separated):\n"
            "Examples: 127.0.0.1, 192.168.1.0/24, 10.0.0.5",
            QtWidgets.QLineEdit.Normal,
            current_ips,
        )
        if ok and text.strip():
            valid, errors = validate_allowed_ips(text.strip())
            if errors:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Invalid IP Configuration",
                    "The following errors were found:\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + ("\n\nOnly valid entries will be saved."
                       if valid else "\n\nNo valid entries found. Settings not changed."),
                )
            if not valid:
                FreeCAD.Console.PrintWarning("Allowed IPs not changed — no valid entries.\n")
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            save_settings(settings)
            FreeCAD.Console.PrintMessage(
                f"Allowed IPs updated to: {normalised}\n"
            )
            if rpc_server_instance:
                FreeCAD.Console.PrintMessage(
                    "Restart the RPC server for changes to take effect.\n"
                )
            _update_remote_action()
        else:
            FreeCAD.Console.PrintMessage("Allowed IPs not changed.\n")

    def IsActive(self):
        return True


class StartupSettingsCommand:
    def GetResources(self):
        return {
            "MenuText": "Startup Settings",
            "ToolTip": "Configure default startup behavior for the server and remote access.",
        }

    def Activated(self):
        dialog = StartupSettingsDialog(None)
        dialog.exec_()

    def IsActive(self):
        return True


FreeCADGui.addCommand("Toggle_RPC_Server", ToggleRPCServerCommand())
FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())
FreeCADGui.addCommand("Startup_Settings", StartupSettingsCommand())


# Map of initial MenuText -> action key (used once to find QActions at startup).
_ACTION_KEYS = {
    "Start Server": "server_button",
    "Enable Remote Access": "remote_button",
    "Configure Allowed IPs": "configure_ips",
}


def _init_gui():
    """One-shot startup: set toolbar style, cache QAction refs, apply initial state."""
    try:
        main_window = FreeCADGui.getMainWindow()
        if main_window is None:
            raise RuntimeError("Main window not ready")

        # Clear in case this is a retry after a partial failure.
        _actions.clear()

        # Show icon + text side-by-side on our toolbar.
        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            if toolbar.windowTitle() == "FreeCAD MCP":
                toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
                break

        # Cache every matching QAction (toolbar and menu each get one).
        for action in main_window.findChildren(QtWidgets.QAction):
            key = _ACTION_KEYS.get(action.text())
            if key is not None:
                _actions.setdefault(key, []).append(action)

        # Apply startup defaults.
        settings = load_settings()
        settings["remote_enabled"] = settings.get("startup_remote_enabled", False)
        save_settings(settings)

        server_started = False
        if settings.get("auto_start_server", True) and rpc_server_instance is None:
            msg = start_rpc_server()
            FreeCAD.Console.PrintMessage(msg + "\n")
            server_started = rpc_server_instance is not None
            if not server_started:
                _logger.error("_init_gui: server failed to start: %s", msg)

        _update_server_action()
        _update_remote_action()

        remote_enabled = settings.get("remote_enabled", False)
        _logger.info(
            "_init_gui completed: server_started=%s port=9875 remote_enabled=%s",
            server_started,
            remote_enabled,
        )
        _logger.info(
            "_init_gui settings: auto_start_server=%s log_enabled=%s log_path=%r",
            settings.get("auto_start_server"),
            settings.get("log_enabled"),
            settings.get("log_path"),
        )
    except Exception:
        QtCore.QTimer.singleShot(2000, _init_gui)


_setup_logging(load_settings())
QtCore.QTimer.singleShot(2000, _init_gui)
