import bpy
import os
from .ops_utils import set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_system

def _parse_field_values(data_elem):
    """Extract scalar values from a DataArray element (handles vectors by computing magnitude)."""
    import math
    raw_data = [float(x) for x in data_elem.text.split()]
    is_vector = data_elem.get('NumberOfComponents') == '3'
    if is_vector:
        return [math.sqrt(raw_data[i]**2 + raw_data[i+1]**2 + raw_data[i+2]**2)
                for i in range(0, len(raw_data), 3)], True
    return raw_data, False


def load_vtu_mesh(context, vtu_path, field_name, mesh_name_prefix, operator, target_collection=None):
    """Load an internal.vtu (UnstructuredGrid) file — used for cell-quality fields."""
    import math
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(vtu_path)
        root = tree.getroot()

        ugrid = root.find('UnstructuredGrid')
        if ugrid is None:
            raise Exception("Missing <UnstructuredGrid> in VTU file.")
        piece = ugrid.find('Piece')
        if piece is None:
            raise Exception("Missing <Piece> in VTU file.")

        # --- Points ---
        points_elem = piece.find('Points/DataArray')
        if points_elem is None or not points_elem.text:
            raise Exception("VTU has no points.")
        raw_points = [float(x) for x in points_elem.text.split()]
        vertices = [(raw_points[i], raw_points[i+1], raw_points[i+2])
                    for i in range(0, len(raw_points), 3)]

        # --- Cells (connectivity + offsets + types) ---
        conn_elem   = piece.find('Cells/DataArray[@Name="connectivity"]')
        offsets_elem = piece.find('Cells/DataArray[@Name="offsets"]')
        types_elem  = piece.find('Cells/DataArray[@Name="types"]')
        if conn_elem is None or offsets_elem is None:
            raise Exception("Missing Cells DataArrays in VTU.")

        connectivity = [int(x) for x in conn_elem.text.split()]
        offsets      = [int(x) for x in offsets_elem.text.split()]

        faces = []
        start_idx = 0
        for offset in offsets:
            cell = connectivity[start_idx:offset]
            # Only include cells that Blender can handle as flat polygons (tris/quads/polys)
            # VTK cell type 5=tri, 9=quad, 7=polygon — skip volume cells
            faces.append(tuple(cell))
            start_idx = offset

        # --- Field data ---
        is_cell_data = True
        data_elem = piece.find(f'CellData/DataArray[@Name="{field_name}"]')
        if data_elem is None:
            data_elem = piece.find(f'PointData/DataArray[@Name="{field_name}"]')
            is_cell_data = False
        if data_elem is None:
            raise Exception(
                f"Field '{field_name}' not found in VTU.\n"
                "Did you enable 'Write Quality Fields' and run checkMesh first?"
            )

        values, _ = _parse_field_values(data_elem)

    except Exception as e:
        operator.report({'ERROR'}, f"Failed to parse VTU: {e}")
        from .ops_utils import set_ui_error
        set_ui_error(f"VTU Parse Error: {str(e)[:60]}")
        return None

    return _build_blender_mesh(context, vertices, faces, values, is_cell_data,
                               field_name, mesh_name_prefix, operator, target_collection)


def load_vtp_mesh(context, vtp_path, field_name, mesh_name_prefix, operator, target_collection=None):
    import math
    import xml.etree.ElementTree as ET
    
    try:
        tree = ET.parse(vtp_path)
        root = tree.getroot()
        
        polydata = root.find('PolyData')
        if polydata is None: raise Exception("Missing <PolyData>")
        piece = polydata.find('Piece')
        if piece is None: raise Exception("Missing <Piece>")
        
        # Points
        points_elem = piece.find('Points/DataArray')
        if points_elem is None or not points_elem.text: 
            raise Exception("Slice is completely outside the mesh bounds (0 points).")
        raw_points = [float(x) for x in points_elem.text.split()]
        if not raw_points:
            raise Exception("Slice is completely outside the mesh bounds (0 points).")
        vertices = [(raw_points[i], raw_points[i+1], raw_points[i+2]) for i in range(0, len(raw_points), 3)]
        
        # Polys
        conn_elem = piece.find('Polys/DataArray[@Name="connectivity"]')
        offsets_elem = piece.find('Polys/DataArray[@Name="offsets"]')
        if conn_elem is None or offsets_elem is None: raise Exception("Missing Polys DataArrays")
        
        connectivity = [int(x) for x in conn_elem.text.split()]
        offsets = [int(x) for x in offsets_elem.text.split()]
        
        faces = []
        start_idx = 0
        for offset in offsets:
            face = connectivity[start_idx:offset]
            faces.append(tuple(face))
            start_idx = offset
            
        # Data (CellData or PointData)
        is_cell_data = True
        data_elem = piece.find(f'CellData/DataArray[@Name="{field_name}"]')
        if data_elem is None:
            data_elem = piece.find(f'PointData/DataArray[@Name="{field_name}"]')
            is_cell_data = False
            
        if data_elem is None:
            raise Exception(f"Field {field_name} not found in VTK Data.")
            
        values, _ = _parse_field_values(data_elem)
            
    except Exception as e:
        operator.report({'ERROR'}, f"Failed to parse VTK: {e}")
        from .ops_utils import set_ui_error
        set_ui_error(f"VTK Parse Error: {str(e)[:50]}")
        return None
        
    return _build_blender_mesh(context, vertices, faces, values, is_cell_data,
                               field_name, mesh_name_prefix, operator, target_collection)


def _build_blender_mesh(context, vertices, faces, values, is_cell_data,
                        field_name, mesh_name_prefix, operator, target_collection=None):
    """Shared logic: build Blender mesh + vertex-colour material from parsed VTK data."""
    import bpy
    # Create Blender Mesh
    mesh = bpy.data.meshes.new(mesh_name_prefix)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    
    obj = bpy.data.objects.new(mesh_name_prefix, mesh)
    if target_collection:
        target_collection.objects.link(obj)
    else:
        context.collection.objects.link(obj)
    
    # Deselect all, select new object
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    
    # Apply Colors
    color_layer_name = f"CFD_{field_name}"
    color_layer = mesh.color_attributes.new(name=color_layer_name, type='FLOAT_COLOR', domain='CORNER')
    mesh.color_attributes.active_color = color_layer
    
    if len(values) > 0:
        props = context.scene.cfmesh_props
        if props.color_autoscale:
            vmin = min(values)
            vmax = max(values)
        else:
            vmin = props.color_min
            vmax = props.color_max
            
        val_range = vmax - vmin if vmax != vmin else 1.0
        
        if is_cell_data:
            for face_idx, poly in enumerate(mesh.polygons):
                val = values[face_idx] if face_idx < len(values) else 0.0
                t = (val - vmin) / val_range
                color = OBJECT_OT_ColorByField.jet_colormap(t) + (1.0,)
                for loop_idx in poly.loop_indices:
                    color_layer.data[loop_idx].color = color
        else:
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    vert_idx = mesh.loops[loop_idx].vertex_index
                    val = values[vert_idx] if vert_idx < len(values) else 0.0
                    t = (val - vmin) / val_range
                    color = OBJECT_OT_ColorByField.jet_colormap(t) + (1.0,)
                    color_layer.data[loop_idx].color = color
                
    # Apply a UNIQUE material per object so colors don't bleed between meshes
    mat_name = f"CFD_Mat_{mesh_name_prefix}"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (400, 0)
    
    bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf_node.location = (200, 0)
    
    vcol_node = nodes.new('ShaderNodeVertexColor')
    vcol_node.location = (0, 0)
    vcol_node.layer_name = color_layer_name
    
    links.new(vcol_node.outputs['Color'], bsdf_node.inputs['Base Color'])
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
    
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
        
    # Switch to Material Preview
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'
                    
    return obj


class OBJECT_OT_ColorByField(bpy.types.Operator):
    bl_idname = "object.color_by_field"
    bl_label = "Color Mesh by Field"
    bl_description = "Uses foamToVTK to sample fields onto boundaries and creates a colored mesh"
    
    def execute(self, context):
        import os
        import bpy
        from .. import utils_system
        from ..properties import global_state
        from .ops_utils import clear_ui_status, set_ui_error

        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        field_name = props.color_field if props.color_field != 'U_mag' else 'U'
        
        # --- Validation ---
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, "Case directory not found.")
            set_ui_error("Case directory not found.")
            return {'CANCELLED'}
            
        clear_ui_status()
        global_state.status_message = "Running foamToVTK..."

        # 1. Run foamToVTK
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        is_quality_field = props.color_field in ('nonOrthoAngle', 'skewness')

        # ── Auto-reconstruct parallel results ──────────────────────────────
        # When cpu_cores > 1, OpenFOAM writes to processor0/, processor1/...
        # foamToVTK needs the data in the main case directory.
        import glob
        proc_dirs = glob.glob(os.path.join(case_dir, "processor*"))
        if proc_dirs:
            global_state.status_message = "Reconstructing parallel results..."
            recon_cmd = f"{source_cmd} && reconstructPar -newTimes"
            recon_ok, recon_out = utils_system.run_cfmesh_command(recon_cmd, case_dir)
            if not recon_ok:
                self.report({'WARNING'},
                    "reconstructPar failed or partially succeeded. "
                    "VTK output may be incomplete. "
                    f"Detail: {recon_out[-200:]}")
            global_state.status_message = "Running foamToVTK..."

        if is_quality_field:
            # Step 1: Write quality fields to time 0 via checkMesh
            utils_system.run_cfmesh_command(f"{source_cmd} && checkMesh -writeAllFields -time 0", case_dir)
            # Step 2: Export internal mesh (NOT -no-internal) so cell-centre quality fields are available
            command = f"{source_cmd} && foamToVTK -ascii -time 0 -fields '(p U {props.color_field})'"
        elif props.animate_results:
            command = f"{source_cmd} && foamToVTK -no-internal -one-boundary -ascii"
        else:
            command = f"{source_cmd} && foamToVTK -no-internal -one-boundary -ascii -latestTime"

        success, output = utils_system.run_cfmesh_command(command, case_dir)
        
        if not success:
            self.report({'ERROR'}, "foamToVTK failed. Check solver logs.")
            set_ui_error("foamToVTK execution failed.")
            return {'CANCELLED'}
            
        # 2. Locate VTK output files
        vtk_dir = os.path.join(case_dir, "VTK")
        if not os.path.isdir(vtk_dir):
            self.report({'ERROR'}, "VTK directory not generated.")
            set_ui_error("VTK directory missing.")
            return {'CANCELLED'}

        # Quality fields live in the internal mesh (internal.vtu)
        # Pressure / velocity live on boundaries (boundary.vtp)
        if is_quality_field:
            target_filename = "internal.vtu"
        else:
            target_filename = "boundary.vtp"

        time_vtps = []
        for d in os.listdir(vtk_dir):
            time_dir = os.path.join(vtk_dir, d)
            if os.path.isdir(time_dir):
                # VTK dirs are named like "cfmesh_run_500" — grab the last segment
                last_part = d.rsplit('_', 1)[-1]
                try:
                    t = float(last_part)
                    vtk_path = os.path.join(time_dir, target_filename)
                    if os.path.isfile(vtk_path):
                        time_vtps.append((t, vtk_path))
                except ValueError:
                    continue
                    
        if not time_vtps:
            if is_quality_field:
                self.report({'ERROR'},
                    "internal.vtu not found. Enable 'Write Quality Fields', "
                    "run 'Check Mesh Quality', then try again.")
                set_ui_error("internal.vtu not found. Run checkMesh with fields first.")
            else:
                self.report({'ERROR'}, "boundary.vtp not found in VTK output.")
                set_ui_error("boundary.vtp not found.")
            return {'CANCELLED'}
            
        time_vtps.sort(key=lambda x: x[0])
        
        if not props.animate_results:
            time_vtps = [time_vtps[-1]]
            
        # 3. Create collection if animating
        anim_col = None
        if props.animate_results and len(time_vtps) > 1:
            col_name = f"CFD_Anim_Boundary_{props.color_field}"
            anim_col = bpy.data.collections.new(col_name)
            context.scene.collection.children.link(anim_col)
            
        # 4. Load Meshes
        objects = []
        for t, vtk_path in time_vtps:
            mesh_name = f"CFD_Boundary_t{t}_{props.color_field}"
            if is_quality_field:
                obj = load_vtu_mesh(context, vtk_path, field_name, mesh_name, self, target_collection=anim_col)
            else:
                obj = load_vtp_mesh(context, vtk_path, field_name, mesh_name, self, target_collection=anim_col)
            if obj:
                objects.append(obj)
                
        # 5. Animate
        if props.animate_results and len(objects) > 1:
            n = len(objects)
            context.scene.frame_start = 1
            context.scene.frame_end = n
            context.scene.render.fps = 24

            for i, obj in enumerate(objects):
                frame_on  = i + 1          # this mesh becomes visible
                frame_off = i + 2          # next mesh takes over

                # --- Before this mesh's turn: hidden ---
                obj.hide_viewport = True
                obj.hide_render   = True
                obj.keyframe_insert(data_path="hide_viewport", frame=max(1, frame_on - 1))
                obj.keyframe_insert(data_path="hide_render",   frame=max(1, frame_on - 1))

                # --- On its frame: visible ---
                obj.hide_viewport = False
                obj.hide_render   = False
                obj.keyframe_insert(data_path="hide_viewport", frame=frame_on)
                obj.keyframe_insert(data_path="hide_render",   frame=frame_on)

                # --- After the last frame: keep visible; others: hide on next ---
                if i < n - 1:
                    obj.hide_viewport = True
                    obj.hide_render   = True
                    obj.keyframe_insert(data_path="hide_viewport", frame=frame_off)
                    obj.keyframe_insert(data_path="hide_render",   frame=frame_off)

                # Force CONSTANT interpolation — compatible with Blender 3/4/5+
                if obj.animation_data and obj.animation_data.action:
                    action = obj.animation_data.action
                    # Try old API (Blender <= 4.3): action.fcurves
                    fcurves = getattr(action, 'fcurves', None)
                    if fcurves is not None:
                        for fc in fcurves:
                            for kp in fc.keyframe_points:
                                kp.interpolation = 'CONSTANT'
                    else:
                        # New layered action API (Blender 5+)
                        try:
                            for layer in action.layers:
                                for strip in layer.strips:
                                    binding = (obj.animation_data.action_binding
                                               if hasattr(obj.animation_data, 'action_binding') else None)
                                    cb = strip.channelbag(binding) if binding else None
                                    if cb:
                                        for fc in cb.fcurves:
                                            for kp in fc.keyframe_points:
                                                kp.interpolation = 'CONSTANT'
                        except Exception:
                            pass  # interpolation is cosmetic — silently skip if API changed again

            global_state.status_message = f"Animation: {n} time steps → {n} frames"
            self.report({'INFO'}, f"Animation created: {n} time steps mapped to {n} frames. "
                                   f"Use Timeline to scrub through (frame 1 = earliest time step).")
        elif objects:
            t = time_vtps[0][0]
            field_labels = {
                'p': 'Pressure', 'U_mag': 'Velocity Magnitude',
                'nonOrthoAngle': 'Non-Orthogonality', 'skewness': 'Skewness'
            }
            field_label = field_labels.get(props.color_field, props.color_field)
            global_state.status_message = f"Colored by {field_label} (t={t})"
            self.report({'INFO'}, f"Visualization created for {field_label}")
            
        return {'FINISHED'}

    @staticmethod
    def jet_colormap(t):
        """Convert 0-1 value to RGB using jet colormap (Blue→Cyan→Green→Yellow→Red)."""
        t = max(0.0, min(1.0, t))
        if t < 0.25:
            r, g, b = 0.0, t * 4, 1.0
        elif t < 0.5:
            r, g, b = 0.0, 1.0, 1.0 - (t - 0.25) * 4
        elif t < 0.75:
            r, g, b = (t - 0.5) * 4, 1.0, 0.0
        else:
            r, g, b = 1.0, 1.0 - (t - 0.75) * 4, 0.0
        return r, g, b
