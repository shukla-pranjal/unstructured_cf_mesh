import re

with open('week8/cfmesh_tools/operators/ops_postprocess.py', 'r') as f:
    content = f.read()

# Find the start of OBJECT_OT_ColorByField
start_idx = content.find('class OBJECT_OT_ColorByField')

# Find the end of OBJECT_OT_ColorByField (before OBJECT_OT_OpenExportDir)
end_idx = content.find('class OBJECT_OT_OpenExportDir')

new_content = """def load_vtp_mesh(context, vtp_path, field_name, mesh_name_prefix, operator):
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
        if points_elem is None: raise Exception("Missing Points/DataArray")
        raw_points = [float(x) for x in points_elem.text.split()]
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
            
        raw_data = [float(x) for x in data_elem.text.split()]
        
        values = []
        is_vector = data_elem.get('NumberOfComponents') == '3'
        if is_vector:
            for i in range(0, len(raw_data), 3):
                mag = math.sqrt(raw_data[i]**2 + raw_data[i+1]**2 + raw_data[i+2]**2)
                values.append(mag)
        else:
            values = raw_data
            
    except Exception as e:
        operator.report({'ERROR'}, f"Failed to parse VTK: {e}")
        from .ops_meshing import set_ui_error
        set_ui_error(f"VTK Parse Error: {str(e)[:50]}")
        return False
        
    # Create Blender Mesh
    import bpy
    mesh = bpy.data.meshes.new(mesh_name_prefix)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    
    obj = bpy.data.objects.new(mesh_name_prefix, mesh)
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
        vmin = min(values)
        vmax = max(values)
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
                
    # Apply Material
    mat_name = "CFD_Visualization"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
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
    else:
        for node in mat.node_tree.nodes:
            if node.type == 'VERTEX_COLOR':
                node.layer_name = color_layer_name
                
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
                    
    return True


class OBJECT_OT_ColorByField(bpy.types.Operator):
    bl_idname = "object.color_by_field"
    bl_label = "Color Mesh by Field"
    bl_description = "Uses foamToVTK to sample fields onto boundaries and creates a colored mesh"
    
    def execute(self, context):
        import os
        import bpy
        from .. import utils_system
        from ..properties import global_state
        from .ops_meshing import clear_ui_status, set_ui_error

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
        # Use -no-internal -one-boundary -ascii -latestTime
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        command = f"{source_cmd} && foamToVTK -no-internal -one-boundary -ascii -latestTime"
        success, output = utils_system.run_cfmesh_command(command, case_dir)
        
        if not success:
            self.report({'ERROR'}, "foamToVTK failed. Check solver logs.")
            set_ui_error("foamToVTK execution failed.")
            return {'CANCELLED'}
            
        # 2. Locate boundary.vtp
        # Find the latest time VTK folder
        vtk_dir = os.path.join(case_dir, "VTK")
        if not os.path.isdir(vtk_dir):
            self.report({'ERROR'}, "VTK directory not generated.")
            set_ui_error("VTK directory missing.")
            return {'CANCELLED'}
            
        latest_vtp = None
        latest_time = -1.0
        
        for d in os.listdir(vtk_dir):
            time_dir = os.path.join(vtk_dir, d)
            if os.path.isdir(time_dir):
                parts = d.split('_')
                if not parts: continue
                try:
                    t = float(parts[-1])
                    vtp_path = os.path.join(time_dir, "boundary.vtp")
                    if os.path.isfile(vtp_path) and t > latest_time:
                        latest_time = t
                        latest_vtp = vtp_path
                except ValueError:
                    continue
                    
        if not latest_vtp:
            self.report({'ERROR'}, "boundary.vtp not found in VTK output.")
            set_ui_error("boundary.vtp not found.")
            return {'CANCELLED'}
            
        # 3. Parse and Load VTK
        mesh_name = f"CFD_Boundary_t{latest_time}_{props.color_field}"
        success = load_vtp_mesh(context, latest_vtp, field_name, mesh_name, self)
        
        if success:
            field_label = "Pressure" if props.color_field == 'p' else "Velocity Magnitude"
            global_state.status_message = f"Colored by {field_label} (t={latest_time})"
            self.report({'INFO'}, f"Visualization created for {field_label}")
            
        return {'FINISHED'}

    @staticmethod
    def jet_colormap(t):
        \"\"\"Convert 0-1 value to RGB using jet colormap (Blue→Cyan→Green→Yellow→Red).\"\"\"
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

class OBJECT_OT_VisualizeSlice(bpy.types.Operator):
    bl_idname = "object.visualize_slice"
    bl_label = "Visualize Slice Plane"
    bl_description = "Extracts an internal slice plane using OpenFOAM and visualizes it"
    
    def execute(self, context):
        import os
        import bpy
        from .. import utils_system
        from ..properties import global_state
        from .ops_meshing import clear_ui_status, set_ui_error

        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        field_name = props.color_field if props.color_field != 'U_mag' else 'U'
        
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, "Case directory not found.")
            set_ui_error("Case directory not found.")
            return {'CANCELLED'}
            
        clear_ui_status()
        global_state.status_message = "Extracting Slice Plane..."
        
        # 1. Generate system/sliceDict
        sys_dir = os.path.join(case_dir, "system")
        if not os.path.exists(sys_dir): os.makedirs(sys_dir)
        
        slice_dict_path = os.path.join(sys_dir, "sliceDict")
        
        # Determine normal and point
        axis = props.slice_axis
        offset = props.slice_offset
        if axis == 'X':
            normal = "(1 0 0)"
            point = f"({offset} 0 0)"
        elif axis == 'Y':
            normal = "(0 1 0)"
            point = f"(0 {offset} 0)"
        else:
            normal = "(0 0 1)"
            point = f"(0 0 {offset})"
            
        slice_dict_content = f\"\"\"FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      sliceDict;
}}

type            surfaces;
libs            (sampling);
writeControl    onEnd;
surfaceFormat   vtk;
formatOptions {{ vtk {{ format ascii; }} }}
fields          ( p U k omega epsilon nut );

surfaces
{{
    slice_plane
    {{
        type            cuttingPlane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {{
            point   {point};
            normal  {normal};
        }}
        interpolate     true;
    }}
}}
\"\"\"
        with open(slice_dict_path, 'w') as f:
            f.write(slice_dict_content)
            
        # 2. Run postProcess
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        command = f"{source_cmd} && postProcess -dict system/sliceDict -latestTime"
        success, output = utils_system.run_cfmesh_command(command, case_dir)
        
        if not success:
            self.report({'ERROR'}, "postProcess slice failed. Check solver logs.")
            set_ui_error("Slice extraction failed.")
            return {'CANCELLED'}
            
        # 3. Locate slice_plane.vtp
        post_dir = os.path.join(case_dir, "postProcessing", "sliceDict")
        if not os.path.isdir(post_dir):
            self.report({'ERROR'}, "postProcessing directory not generated.")
            set_ui_error("Slice VTK missing.")
            return {'CANCELLED'}
            
        latest_vtp = None
        latest_time = -1.0
        
        for d in os.listdir(post_dir):
            time_dir = os.path.join(post_dir, d)
            if os.path.isdir(time_dir):
                try:
                    t = float(d)
                    vtp_path = os.path.join(time_dir, "slice_plane.vtp")
                    if os.path.isfile(vtp_path) and t > latest_time:
                        latest_time = t
                        latest_vtp = vtp_path
                except ValueError:
                    continue
                    
        if not latest_vtp:
            self.report({'ERROR'}, "slice_plane.vtp not found.")
            set_ui_error("slice_plane.vtp not found.")
            return {'CANCELLED'}
            
        # 4. Parse and Load VTK
        mesh_name = f"CFD_Slice_{axis}_{offset}_t{latest_time}_{props.color_field}"
        success = load_vtp_mesh(context, latest_vtp, field_name, mesh_name, self)
        
        if success:
            field_label = "Pressure" if props.color_field == 'p' else "Velocity Magnitude"
            global_state.status_message = f"Slice Extracted: {field_label} (t={latest_time})"
            self.report({'INFO'}, f"Slice plane created for {field_label}")
            
        return {'FINISHED'}

"""

final_content = content[:start_idx] + new_content + content[end_idx:]

with open('week8/cfmesh_tools/operators/ops_postprocess.py', 'w') as f:
    f.write(final_content)
