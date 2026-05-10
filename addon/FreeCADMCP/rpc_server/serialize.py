import FreeCAD as App


def _get_optional_app_type(name: str) -> type | tuple[type, ...] | None:
    value = getattr(App, name, None)
    if isinstance(value, type):
        return value
    if isinstance(value, tuple) and all(isinstance(item, type) for item in value):
        return value
    return None


_COLOR_TYPE = _get_optional_app_type("Color")


def serialize_value(value):
    if isinstance(value, (int, float, str, bool)):
        return value
    elif isinstance(value, App.Vector):
        return {"x": value.x, "y": value.y, "z": value.z}
    elif isinstance(value, App.Rotation):
        return {
            "Axis": {"x": value.Axis.x, "y": value.Axis.y, "z": value.Axis.z},
            "Angle": value.Angle,
        }
    elif isinstance(value, App.Placement):
        return {
            "Base": serialize_value(value.Base),
            "Rotation": serialize_value(value.Rotation),
        }
    elif isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    elif _COLOR_TYPE is not None and isinstance(value, _COLOR_TYPE):
        return tuple(value)
    else:
        return str(value)


def serialize_shape(shape):
    if shape is None:
        return None
    try:
        bb = shape.BoundBox
        bound_box = {
            "XMin": round(bb.XMin, 4), "XMax": round(bb.XMax, 4),
            "YMin": round(bb.YMin, 4), "YMax": round(bb.YMax, 4),
            "ZMin": round(bb.ZMin, 4), "ZMax": round(bb.ZMax, 4),
        }
    except Exception:
        bound_box = None
    try:
        return {
            "Volume": shape.Volume,
            "Area": shape.Area,
            "VertexCount": len(shape.Vertexes),
            "EdgeCount": len(shape.Edges),
            "FaceCount": len(shape.Faces),
            "BoundBox": bound_box,
        }
    except Exception:
        return {"BoundBox": bound_box, "invalid": True}


def serialize_view_object(view):
    if view is None:
        return None
    return {
        "ShapeColor": serialize_value(getattr(view, "ShapeColor", None)),
        "Transparency": getattr(view, "Transparency", None),
        "Visibility": getattr(view, "Visibility", None),
    }


def serialize_object(obj):
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    elif isinstance(obj, App.Document):
        return {
            "Name": obj.Name,
            "Label": obj.Label,
            "FileName": obj.FileName,
            "Objects": [serialize_object(child) for child in obj.Objects],
        }
    else:
        state = getattr(obj, "State", [])
        has_error = any(s in ("Invalid", "Error") for s in state)
        result = {
            "Name": obj.Name,
            "Label": obj.Label,
            "TypeId": obj.TypeId,
            "State": state,
            "HasError": has_error,
            "Properties": {},
            "Placement": serialize_value(getattr(obj, "Placement", None)),
            "Shape": serialize_shape(getattr(obj, "Shape", None)),
            "ViewObject": {},
        }

        for prop in obj.PropertiesList:
            try:
                result["Properties"][prop] = serialize_value(getattr(obj, prop))
            except Exception as e:
                result["Properties"][prop] = f"<error: {str(e)}>"

        try:
            if hasattr(obj, "ViewObject") and obj.ViewObject is not None:
                result["ViewObject"] = serialize_view_object(obj.ViewObject)
        except Exception as e:
            result["ViewObject"] = {"error": str(e)}

        return result
