import bpy
import os
from .ops_utils import set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_system
from .ops_visualize_boundary import load_vtp_mesh

class OBJECT_OT_VisualizeSlice(bpy.types.Operator):
    bl_idname = "object.visualize_slice"
    bl_label = "Visualize Slice Plane"
    bl_description = "Extracts an internal slice plane using OpenFOAM and visualizes it"
    
    def execute(self, context):
        import os
        import bpy
        from .. import utils_system
        from ..properties import global_state
        from .ops_utils import clear_ui_status, set_ui_error

        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        # U_mag is a Blender alias — the actual field name OpenFOAM uses is 'U'
        # Quality fields (nonOrthoAngle, skewness) must be passed through unchanged
        field_name = 'U' if props.color_field == 'U_mag' else props.color_field
        
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
            
        # 1. If quality fields are requested, run checkMesh to write them to 0/ first
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        is_quality_field = props.color_field in ('nonOrthoAngle', 'skewness')
        if is_quality_field or props.checkmesh_write_fields:
            utils_system.run_cfmesh_command(f"{source_cmd} && checkMesh -writeAllFields -time 0", case_dir)
            
        # 2. Dynamically discover which fields actually exist in the 0/ folder
        # to prevent postProcess from crashing on missing turbulence fields (e.g. in laminar or icoFoam runs)
        candidates = ["p", "U", "k", "omega", "epsilon", "nut", "nonOrthoAngle", "skewness", "cellLevel"]
        zero_dir = os.path.join(case_dir, "0")
        available_fields = []
        if os.path.isdir(zero_dir):
            available_fields = [f for f in candidates if os.path.isfile(os.path.join(zero_dir, f))]
            
        # Fallbacks to guarantee minimum fields
        if "p" not in available_fields: available_fields.append("p")
        if "U" not in available_fields: available_fields.append("U")
        
        fields_str = " ".join(available_fields)
            
        slice_dict_content = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      sliceDict;
}}

functions
{{
    mySlice
    {{
        type            surfaces;
        libs            (sampling);
        writeControl    onEnd;
        surfaceFormat   vtk;
        formatOptions {{ vtk {{ format ascii; }} }}
        fields          ( {fields_str} );

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
    }}
}}
"""
        with open(slice_dict_path, 'w') as f:
            f.write(slice_dict_content)
            
        # 3. Run postProcess
        if is_quality_field:
            command = f"{source_cmd} && postProcess -dict system/sliceDict -fields '({fields_str})' -time 0"
        elif props.animate_results:
            command = f"{source_cmd} && postProcess -dict system/sliceDict -fields '({fields_str})'"
        else:
            command = f"{source_cmd} && postProcess -dict system/sliceDict -fields '({fields_str})' -latestTime"
            
        success, output = utils_system.run_cfmesh_command(command, case_dir)
        
        if not success:
            self.report({'ERROR'}, "postProcess slice failed. Check solver logs.")
            set_ui_error("Slice extraction failed.")
            return {'CANCELLED'}
            
        # 3. Locate slice_plane.vtp files — clear stale results first
        post_dir = os.path.join(case_dir, "postProcessing", "mySlice")
        if not os.path.isdir(post_dir):
            self.report({'ERROR'}, "postProcessing directory not generated.")
            set_ui_error("Slice VTK missing.")
            return {'CANCELLED'}
            
        time_vtps = []
        for d in os.listdir(post_dir):
            time_dir = os.path.join(post_dir, d)
            if os.path.isdir(time_dir):
                try:
                    t = float(d)
                    vtp_path = os.path.join(time_dir, "slice_plane.vtp")
                    if os.path.isfile(vtp_path):
                        time_vtps.append((t, vtp_path))
                except ValueError:
                    continue
                    
        if not time_vtps:
            self.report({'ERROR'}, "slice_plane.vtp not found.")
            set_ui_error("slice_plane.vtp not found.")
            return {'CANCELLED'}
            
        time_vtps.sort(key=lambda x: x[0])
        
        if not props.animate_results:
            time_vtps = [time_vtps[-1]]
            
        # 4. Create collection if animating
        anim_col = None
        if props.animate_results and len(time_vtps) > 1:
            col_name = f"CFD_Anim_Slice_{axis}_{offset}_{props.color_field}"
            anim_col = bpy.data.collections.new(col_name)
            context.scene.collection.children.link(anim_col)
            
        # 5. Load Meshes
        objects = []
        for t, vtp_path in time_vtps:
            mesh_name = f"CFD_Slice_{axis}_{offset}_t{t}_{props.color_field}"
            obj = load_vtp_mesh(context, vtp_path, field_name, mesh_name, self, target_collection=anim_col)
            if obj:
                objects.append(obj)
                
        # 6. Animate
        if props.animate_results and len(objects) > 1:
            context.scene.frame_start = 1
            context.scene.frame_end = len(objects)
            
            for frame, obj in enumerate(objects, start=1):
                obj.hide_viewport = True
                obj.hide_render = True
                obj.keyframe_insert(data_path="hide_viewport", frame=frame-1)
                obj.keyframe_insert(data_path="hide_render", frame=frame-1)
                
                obj.hide_viewport = False
                obj.hide_render = False
                obj.keyframe_insert(data_path="hide_viewport", frame=frame)
                obj.keyframe_insert(data_path="hide_render", frame=frame)
                
                obj.hide_viewport = True
                obj.hide_render = True
                obj.keyframe_insert(data_path="hide_viewport", frame=frame+1)
                obj.keyframe_insert(data_path="hide_render", frame=frame+1)
                
            global_state.status_message = f"Animation Created: {len(objects)} frames"
            self.report({'INFO'}, f"Animation created with {len(objects)} frames.")
        elif objects:
            t = time_vtps[0][0]
            field_labels = {
                'p': 'Pressure', 'U_mag': 'Velocity Magnitude',
                'nonOrthoAngle': 'Non-Orthogonality', 'skewness': 'Skewness'
            }
            field_label = field_labels.get(props.color_field, props.color_field)
            global_state.status_message = f"Slice Extracted: {field_label} (t={t})"
            self.report({'INFO'}, f"Slice plane created for {field_label}")
            
        return {'FINISHED'}
