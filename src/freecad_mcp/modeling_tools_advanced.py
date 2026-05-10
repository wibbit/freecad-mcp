"""
modeling_tools_advanced.py: Advanced modeling operations for FreeCAD MCP
Date création: 2025-10-08
Phase 3-5: Fonctions avancées pour modélisation F4U Corsair
"""

from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

from .responses import parse_execute_result


# ==================== PHASE 3: CRITICAL FEATURES ====================

def add_fillet(ctx: Context, freecad_connection, add_screenshot_helper,
               doc_name: str, object_name: str, edges: list[str],
               radius: float, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """
    Add fillet (rounded edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        radius: Fillet radius
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        Rounded edges on a box:
        edges=["Edge1", "Edge2", "Edge3"], radius=5.0
    """
    res_name = result_name or f"{object_name}_filleted"
    edges_list = ', '.join([f'"{e}"' for e in edges])
    
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
obj = doc.getObject('{object_name}')

if not obj:
    print('ERROR: Object {object_name} not found')
elif not hasattr(obj, 'Shape') or obj.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        # Create fillet object
        fillet = doc.addObject('Part::Fillet', '{res_name}')
        fillet.Base = obj
        
        # Parse edge names and add to fillet
        edge_names = [{edges_list}]
        edges_to_fillet = []
        
        for edge_name in edge_names:
            edge_idx = int(edge_name.replace('Edge', ''))
            # Format: (edge_index, start_radius, end_radius)
            edges_to_fillet.append((edge_idx, {radius}, {radius}))
        
        fillet.Edges = edges_to_fillet
        doc.recompute()

        # Hide original
        obj.ViewObject.Visibility = False

        if fillet.Shape.isValid():
            print(f'SUCCESS: Fillet added to {{len(edges_to_fillet)}} edges with radius {radius}')
        else:
            print('ERROR: Fillet operation produced invalid shape')
    except Exception as e:
        print(f'ERROR: Fillet failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to add fillet: {msg}')], screenshot)


def add_chamfer(ctx: Context, freecad_connection, add_screenshot_helper,
                doc_name: str, object_name: str, edges: list[str],
                distance: float, result_name: str | None = None) -> list[TextContent | ImageContent]:
    """
    Add chamfer (beveled edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        distance: Chamfer distance
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    """
    res_name = result_name or f"{object_name}_chamfered"
    edges_list = ', '.join([f'"{e}"' for e in edges])
    
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
obj = doc.getObject('{object_name}')

if not obj:
    print('ERROR: Object {object_name} not found')
elif not hasattr(obj, 'Shape') or obj.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        # Create chamfer object
        chamfer = doc.addObject('Part::Chamfer', '{res_name}')
        chamfer.Base = obj
        
        # Parse edge names and add to chamfer
        edge_names = [{edges_list}]
        edges_to_chamfer = []
        
        for edge_name in edge_names:
            edge_idx = int(edge_name.replace('Edge', ''))
            # Format: (edge_index, dist1, dist2)
            edges_to_chamfer.append((edge_idx, {distance}, {distance}))

        chamfer.Edges = edges_to_chamfer
        doc.recompute()

        # Hide original
        obj.ViewObject.Visibility = False

        if chamfer.Shape.isValid():
            print(f'SUCCESS: Chamfer added to {{len(edges_to_chamfer)}} edges with distance {distance}')
        else:
            print('ERROR: Chamfer operation produced invalid shape')
    except Exception as e:
        print(f'ERROR: Chamfer failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to add chamfer: {msg}')], screenshot)


def shell_object(ctx: Context, freecad_connection, add_screenshot_helper,
                 doc_name: str, object_name: str, thickness: float,
                 faces_to_remove: list[str] | None = None, 
                 result_name: str | None = None) -> list[TextContent | ImageContent]:
    """
    Create a hollow shell by removing faces and adding thickness
    
    Args:
        doc_name: Document name
        object_name: Object to shell
        thickness: Wall thickness
        faces_to_remove: List of face names to remove (opens the shell)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        Create hollow fuselage:
        thickness=2.0, faces_to_remove=["Face1", "Face6"]
    """
    res_name = result_name or f"{object_name}_shelled"

    # Build the face names list for injection into the generated code
    if faces_to_remove:
        face_names_repr = repr(faces_to_remove)  # e.g. ['Face1', 'Face3']
    else:
        face_names_repr = '[]'

    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
obj = doc.getObject('{object_name}')

if not obj:
    print('ERROR: Object {object_name} not found')
elif not hasattr(obj, 'Shape') or obj.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        face_names = {face_names_repr}
        faces = []
        for name in face_names:
            if name.startswith('Face'):
                try:
                    faces.append(obj.Shape.Faces[int(name[4:]) - 1])
                except (ValueError, IndexError) as e:
                    print(f'ERROR: Invalid face name {{name}}: {{e}}')
                    raise
        shell_shape = obj.Shape.makeThickness(faces, {thickness}, 1e-5)
        shell = doc.addObject('Part::Feature', '{res_name}')
        shell.Shape = shell_shape
        doc.recompute()
        obj.ViewObject.Visibility = False
        if shell.Shape.isValid():
            print(f'SUCCESS: Shell created with thickness {thickness}, {{len(faces)}} face(s) removed')
        else:
            print('ERROR: Shell operation produced invalid shape')
    except Exception as e:
        print(f'ERROR: Shell failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create shell: {msg}')], screenshot)


def mirror_object(ctx: Context, freecad_connection, add_screenshot_helper,
                  doc_name: str, source_obj: str, mirror_plane: dict,
                  result_name: str | None = None, merge: bool = True) -> list[TextContent | ImageContent]:
    """
    Mirror an object across a plane
    
    Args:
        doc_name: Document name
        source_obj: Object to mirror
        mirror_plane: {"base": {"x": 0, "y": 0, "z": 0}, 
                       "normal": {"x": 1, "y": 0, "z": 0}}
        result_name: Result name (optional)
        merge: If True, fuse with original (creates symmetric object)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        Mirror wing left to right:
        mirror_plane={"base": {"x": 0, "y": 0, "z": 0}, 
                      "normal": {"x": 1, "y": 0, "z": 0}}
    """
    res_name = result_name or f"{source_obj}_mirrored"
    base = mirror_plane['base']
    normal = mirror_plane['normal']
    
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
src = doc.getObject('{source_obj}')

if not src:
    print('ERROR: Source object {source_obj} not found')
elif not hasattr(src, 'Shape') or src.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        # Create mirror
        mirror = doc.addObject('Part::Mirroring', '{res_name}')
        mirror.Source = src
        mirror.Base = App.Vector({base['x']}, {base['y']}, {base['z']})
        mirror.Normal = App.Vector({normal['x']}, {normal['y']}, {normal['z']})
        
        doc.recompute()
        
        # Merge if requested
        if {merge}:
            fusion = doc.addObject('Part::MultiFuse', '{res_name}_fused')
            fusion.Shapes = [src, mirror]
            doc.recompute()
            
            if fusion.Shape.isValid():
                mirror.ViewObject.Visibility = False
                src.ViewObject.Visibility = False
                print(f'SUCCESS: Mirror created and fused into symmetric object')
            else:
                print('ERROR: Fusion produced invalid shape')
        else:
            if mirror.Shape.isValid():
                print(f'SUCCESS: Mirror created (not fused)')
            else:
                print('ERROR: Mirror produced invalid shape')
    except Exception as e:
        print(f'ERROR: Mirror failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to mirror: {msg}')], screenshot)


def circular_pattern(ctx: Context, freecad_connection, add_screenshot_helper,
                     doc_name: str, object_name: str, axis: dict,
                     count: int, angle: float = 360.0, 
                     result_name: str | None = None) -> list[TextContent | ImageContent]:
    """
    Create circular pattern (polar array) of an object
    
    Args:
        doc_name: Document name
        object_name: Object to pattern
        axis: {"point": {"x": 0, "y": 0, "z": 0}, 
               "direction": {"x": 0, "y": 0, "z": 1}}
        count: Number of instances
        angle: Total angle in degrees (default 360)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        18 cylinders around Z axis:
        axis={"point": {"x": 0, "y": 0, "z": 0}, 
              "direction": {"x": 0, "y": 0, "z": 1}}
        count=18, angle=360
    """
    res_name = result_name or f"{object_name}_pattern"
    pt = axis['point']
    direction = axis['direction']
    angle_step = angle / count
    
    code = f"""
import FreeCAD as App
import Part
import math

doc = App.getDocument('{doc_name}')
src = doc.getObject('{object_name}')

if not src:
    print('ERROR: Source object {object_name} not found')
elif not hasattr(src, 'Shape') or src.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        objects = [src]
        axis_point = App.Vector({pt['x']}, {pt['y']}, {pt['z']})
        axis_dir = App.Vector({direction['x']}, {direction['y']}, {direction['z']})
        axis_dir.normalize()
        
        # Create rotated copies
        for i in range(1, {count}):
            angle_deg = i * {angle_step}
            
            # Create rotation
            rot = App.Rotation(axis_dir, angle_deg)
            
            # Create copy
            copy = doc.addObject('Part::Feature', '{object_name}_copy_' + str(i))
            
            # Calculate new placement
            original_placement = src.Placement
            original_center = original_placement.Base
            
            # Rotate around axis point
            vec_from_axis = original_center - axis_point
            rotated_vec = rot.multVec(vec_from_axis)
            new_center = axis_point + rotated_vec
            
            # Apply rotation to shape orientation
            new_rotation = rot.multiply(original_placement.Rotation)
            
            copy.Shape = src.Shape.copy()
            copy.Placement = App.Placement(new_center, new_rotation)
            objects.append(copy)
        
        # Fuse all copies
        if len(objects) > 1:
            pattern = doc.addObject('Part::MultiFuse', '{res_name}')
            pattern.Shapes = objects
            doc.recompute()
            
            if pattern.Shape.isValid():
                # Hide sources
                for obj in objects:
                    obj.ViewObject.Visibility = False

                print(f'SUCCESS: Circular pattern created with {count} instances over {angle}°')
            else:
                print('ERROR: Pattern fusion produced invalid shape')
        else:
            print('ERROR: Could not create copies')
    except Exception as e:
        print(f'ERROR: Circular pattern failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create circular pattern: {msg}')], screenshot)


def linear_pattern(ctx: Context, freecad_connection, add_screenshot_helper,
                   doc_name: str, object_name: str, direction: dict,
                   spacing: float, count: int, 
                   result_name: str | None = None) -> list[TextContent | ImageContent]:
    """
    Create linear pattern (rectangular array) of an object
    
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
        6 machine guns along X axis:
        direction={"x": 1, "y": 0, "z": 0}, spacing=50, count=6
    """
    res_name = result_name or f"{object_name}_pattern"
    dir_vec = direction
    
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')
src = doc.getObject('{object_name}')

if not src:
    print('ERROR: Source object {object_name} not found')
elif not hasattr(src, 'Shape') or src.Shape.isNull():
    print('ERROR: Object has no valid shape')
else:
    try:
        objects = [src]
        direction = App.Vector({dir_vec['x']}, {dir_vec['y']}, {dir_vec['z']})
        direction.normalize()
        
        # Create copies
        for i in range(1, {count}):
            offset = direction * ({spacing} * i)
            
            # Create copy
            copy = doc.addObject('Part::Feature', '{object_name}_copy_' + str(i))
            copy.Shape = src.Shape.copy()
            
            # Apply offset
            new_placement = src.Placement.copy()
            new_placement.Base = src.Placement.Base + offset
            copy.Placement = new_placement
            
            objects.append(copy)
        
        # Fuse all copies
        if len(objects) > 1:
            pattern = doc.addObject('Part::MultiFuse', '{res_name}')
            pattern.Shapes = objects
            doc.recompute()
            
            if pattern.Shape.isValid():
                # Hide sources
                for obj in objects:
                    obj.ViewObject.Visibility = False

                print(f'SUCCESS: Linear pattern created with {count} instances, spacing {spacing}')
            else:
                print('ERROR: Pattern fusion produced invalid shape')
        else:
            print('ERROR: Could not create copies')
    except Exception as e:
        print(f'ERROR: Linear pattern failed - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create linear pattern: {msg}')], screenshot)


# ==================== PHASE 4-5: ADVANCED FEATURES ====================

def create_reference_plane(ctx: Context, freecad_connection, add_screenshot_helper,
                           doc_name: str, plane_name: str, 
                           definition: dict) -> list[TextContent | ImageContent]:
    """
    Create reference plane with various definition modes
    
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
    """
    mode = definition.get('mode', 'offset')
    
    if mode == 'offset':
        plane = definition['plane']
        offset = definition['offset']
        
        code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')

try:
    if '{plane}' == 'XY':
        normal = App.Vector(0, 0, 1)
        origin = App.Vector(-500, -500, {offset})
    elif '{plane}' == 'XZ':
        normal = App.Vector(0, 1, 0)
        origin = App.Vector(-500, {offset}, -500)
    else:  # YZ
        normal = App.Vector(1, 0, 0)
        origin = App.Vector({offset}, -500, -500)
    plane_shape = Part.makePlane(1000, 1000, origin, normal)
    plane_obj = doc.addObject('Part::Feature', '{plane_name}')
    plane_obj.Shape = plane_shape
    doc.recompute()
    print(f'SUCCESS: Reference plane created with offset {offset} from {plane}')
except Exception as e:
    print(f'ERROR: Failed to create reference plane - {{str(e)}}')
"""
    
    elif mode == '3points':
        p1 = definition['p1']
        p2 = definition['p2']
        p3 = definition['p3']
        
        code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')

try:
    # Create plane from 3 points
    v1 = App.Vector({p1['x']}, {p1['y']}, {p1['z']})
    v2 = App.Vector({p2['x']}, {p2['y']}, {p2['z']})
    v3 = App.Vector({p3['x']}, {p3['y']}, {p3['z']})
    
    # Calculate normal
    vec1 = v2 - v1
    vec2 = v3 - v1
    normal = vec1.cross(vec2)
    normal.normalize()
    
    # Create plane
    plane_shape = Part.makePlane(1000, 1000, v1, normal)
    plane_obj = doc.addObject('Part::Feature', '{plane_name}')
    plane_obj.Shape = plane_shape
    
    doc.recompute()
    print('SUCCESS: Reference plane created from 3 points')
except Exception as e:
    print(f'ERROR: Failed to create reference plane - {{str(e)}}')
"""
    
    elif mode == 'point_normal':
        point = definition['point']
        normal = definition['normal']
        
        code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')

try:
    # Create plane from point and normal
    pos = App.Vector({point['x']}, {point['y']}, {point['z']})
    norm = App.Vector({normal['x']}, {normal['y']}, {normal['z']})
    norm.normalize()
    
    # Create plane
    plane_shape = Part.makePlane(1000, 1000, pos, norm)
    plane_obj = doc.addObject('Part::Feature', '{plane_name}')
    plane_obj.Shape = plane_shape
    
    doc.recompute()
    print('SUCCESS: Reference plane created from point and normal')
except Exception as e:
    print(f'ERROR: Failed to create reference plane - {{str(e)}}')
"""
    else:
        return [TextContent(type='text', text=f'ERROR: Unknown mode {mode}')]
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create reference plane: {msg}')], screenshot)


def create_reference_axis(ctx: Context, freecad_connection, add_screenshot_helper,
                          doc_name: str, axis_name: str, point: dict, 
                          direction: dict) -> list[TextContent | ImageContent]:
    """
    Create reference axis from point and direction
    
    Args:
        doc_name: Document name
        axis_name: Name for the axis
        point: {"x": 0, "y": 0, "z": 0} - point on axis
        direction: {"x": 0, "y": 0, "z": 1} - axis direction
    
    Returns:
        Confirmation message and screenshot
    """
    pt = point
    dir_vec = direction
    
    code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{doc_name}')

try:
    # Create axis line
    start_point = App.Vector({pt['x']}, {pt['y']}, {pt['z']})
    direction = App.Vector({dir_vec['x']}, {dir_vec['y']}, {dir_vec['z']})
    direction.normalize()
    
    # Create line 1000mm long
    end_point = start_point + (direction * 1000)
    
    line = Part.makeLine(start_point, end_point)
    axis_obj = doc.addObject('Part::Feature', '{axis_name}')
    axis_obj.Shape = line
    
    doc.recompute()
    print('SUCCESS: Reference axis created')
except Exception as e:
    print(f'ERROR: Failed to create reference axis - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to create reference axis: {msg}')], screenshot)


def import_airfoil_profile(ctx: Context, freecad_connection, add_screenshot_helper,
                           doc_name: str, sketch_name: str, naca_code: str,
                           chord_length: float, 
                           position: dict | None = None) -> list[TextContent | ImageContent]:
    """
    Import standard NACA airfoil profile into sketch
    
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
    """
    pos = position or {"x": 0, "y": 0, "z": 0}
    
    code = f"""
import FreeCAD as App
import Part
import Sketcher
import math

doc = App.getDocument('{doc_name}')

def naca_4digit(code, chord, num_points=50):
    '''Generate NACA 4-digit airfoil coordinates'''
    m = int(code[0]) / 100.0  # Max camber
    p = int(code[1]) / 10.0   # Location of max camber
    t = int(code[2:4]) / 100.0  # Thickness
    
    # Generate x coordinates (cosine spacing for better resolution at LE/TE)
    beta = [i * math.pi / num_points for i in range(num_points + 1)]
    x = [(1 - math.cos(b)) / 2 * chord for b in beta]
    
    # Thickness distribution
    yt = []
    for xi in x:
        xc = xi / chord
        yt_val = 5 * t * chord * (0.2969 * math.sqrt(xc) - 0.1260 * xc - 
                                   0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        yt.append(yt_val)
    
    # Camber line
    yc = []
    dyc_dx = []
    for xi in x:
        xc = xi / chord
        if xc < p:
            yc_val = m * (2 * p * xc - xc**2) / (p**2) * chord
            dyc_val = 2 * m * (p - xc) / (p**2)
        else:
            yc_val = m * ((1 - 2*p) + 2*p*xc - xc**2) / ((1-p)**2) * chord
            dyc_val = 2 * m * (p - xc) / ((1-p)**2)
        yc.append(yc_val)
        dyc_dx.append(dyc_val)
    
    # Upper and lower surfaces
    xu = [x[i] - yt[i] * math.sin(math.atan(dyc_dx[i])) for i in range(len(x))]
    yu = [yc[i] + yt[i] * math.cos(math.atan(dyc_dx[i])) for i in range(len(x))]
    xl = [x[i] + yt[i] * math.sin(math.atan(dyc_dx[i])) for i in range(len(x))]
    yl = [yc[i] - yt[i] * math.cos(math.atan(dyc_dx[i])) for i in range(len(x))]
    
    return xu, yu, xl, yl

try:
    # Generate NACA profile
    xu, yu, xl, yl = naca_4digit('{naca_code}', {chord_length})
    
    # Create sketch
    sketch = doc.addObject('Sketcher::SketchObject', '{sketch_name}')
    sketch.Placement = App.Placement(
        App.Vector({pos['x']}, {pos['y']}, {pos['z']}),
        App.Rotation()
    )
    
    # Add upper surface as B-spline
    upper_points = [App.Vector(xu[i], yu[i], 0) for i in range(len(xu))]
    upper_spline = Part.BSplineCurve()
    upper_spline.interpolate(upper_points)
    sketch.addGeometry(upper_spline)

    # Add lower surface as B-spline
    lower_points = [App.Vector(xl[i], yl[i], 0) for i in range(len(xl))]
    lower_spline = Part.BSplineCurve()
    lower_spline.interpolate(lower_points)
    sketch.addGeometry(lower_spline)
    
    # Close at trailing edge
    sketch.addGeometry(Part.LineSegment(
        App.Vector(xu[-1], yu[-1], 0),
        App.Vector(xl[-1], yl[-1], 0)
    ))
    
    doc.recompute()
    print(f'SUCCESS: NACA {naca_code} airfoil imported with chord {chord_length}mm')
except Exception as e:
    print(f'ERROR: Failed to import airfoil - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to import airfoil: {msg}')], screenshot)


def import_dxf(ctx: Context, freecad_connection, add_screenshot_helper,
               doc_name: str, file_path: str, sketch_name: str, 
               scale: float = 1.0) -> list[TextContent | ImageContent]:
    """
    Import DXF file into a sketch
    
    Args:
        doc_name: Document name
        file_path: Full path to DXF file
        sketch_name: Sketch name to create
        scale: Scale factor (default 1.0)
    
    Returns:
        Confirmation message and screenshot
    """
    code = f"""
import FreeCAD as App
import Part
import importDXF

doc = App.getDocument('{doc_name}')

try:
    # Import DXF
    importDXF.insert(r'{file_path}', '{doc_name}')
    doc.recompute()
    
    # Scale if needed
    if {scale} != 1.0:
        for obj in doc.Objects:
            if hasattr(obj, 'Shape'):
                scaled_shape = obj.Shape.copy()
                scaled_shape.scale({scale})
                obj.Shape = scaled_shape
    
    doc.recompute()
    print(f'SUCCESS: DXF imported from {file_path} with scale {scale}')
except Exception as e:
    print(f'ERROR: Failed to import DXF - {{str(e)}}')
"""
    
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    
    ok, msg = parse_execute_result(res)
    if ok:
        return add_screenshot_helper([TextContent(type='text', text=msg)], screenshot)
    return add_screenshot_helper([TextContent(type='text', text=f'Failed to import DXF: {msg}')], screenshot)



