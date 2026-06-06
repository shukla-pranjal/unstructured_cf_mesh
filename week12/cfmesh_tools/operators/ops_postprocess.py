import bpy
import os
import math
from .ops_utils import set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_system

class OBJECT_OT_LaunchParaView(bpy.types.Operator):
    bl_idname = "object.launch_paraview"
    bl_label = "Launch ParaView"
    bl_description = "Opens the current case in ParaView"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        # --- Validation: Case directory ---
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, "Case directory does not exist. Nothing to visualize.")
            set_ui_error("Case directory does not exist.")
            return {'CANCELLED'}
        
        # --- Validation: Check for mesh or results ---
        poly_mesh = os.path.join(case_dir, "constant", "polyMesh")
        if not os.path.isdir(poly_mesh):
            self.report({'ERROR'}, "No mesh data found. Run 'Generate cfMesh' first.")
            set_ui_error("No data to visualize. Generate mesh first.")
            return {'CANCELLED'}
        
        success = utils_system.launch_paraview(case_dir)
        if not success:
            self.report({'ERROR'}, "Failed to launch ParaView. Is it installed?")
            set_ui_error("ParaView launch failed. Is it installed?")
            return {'CANCELLED'}
            
        self.report({'INFO'}, "ParaView launched.")
        return {'FINISHED'}

class OBJECT_OT_LoadResult(bpy.types.Operator):
    bl_idname = "object.load_result"
    bl_label = "Load Meshed Result"
    bl_description = "Imports the result.stl into the scene"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        result_stl = os.path.join(case_dir, "constant", "triSurface", "result.stl")
        
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, "Case directory does not exist.")
            set_ui_error("Case directory does not exist.")
            return {'CANCELLED'}
        
        if os.path.isfile(result_stl):
            if os.path.getsize(result_stl) == 0:
                self.report({'ERROR'}, "Result STL is empty — meshing may have failed.")
                set_ui_error("Result STL is empty. Check meshing logs.")
                return {'CANCELLED'}

            existing = set(bpy.data.objects.keys())
            bpy.ops.wm.stl_import(filepath=result_stl)

            # Find the newly imported mesh objects
            new_objs = [o for n, o in bpy.data.objects.items()
                        if n not in existing and o.type == 'MESH']

            # Auto Shade Smooth — fixes the "faceted sphere" look
            for o in new_objs:
                # Set every polygon to smooth shading
                for poly in o.data.polygons:
                    poly.use_smooth = True
                o.data.update()
                # Enable auto smooth normals so sharp real edges stay sharp
                if hasattr(o.data, "use_auto_smooth"):
                    o.data.use_auto_smooth = True
                    o.data.auto_smooth_angle = 1.0472  # 60 degrees in radians

            # Auto-focus the camera
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with context.temp_override(area=area, region=region):
                                bpy.ops.view3d.view_selected()
                            break

            self.report({'INFO'}, "Successfully imported meshed result! (Shade Smooth applied)")
        else:
            self.report({'ERROR'}, f"Result STL not found at {result_stl}. Did you run meshing?")
            set_ui_error("result.stl not found. Run mesh generation first.")
            
        return {'FINISHED'}



class OBJECT_OT_OpenExportDir(bpy.types.Operator):
    bl_idname = "object.open_export_dir"
    bl_label = "Open Directory"
    bl_description = "Opens the export directory in the system file explorer"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        if os.path.isdir(case_dir):
            success = utils_system.open_directory(case_dir)
            if success:
                self.report({'INFO'}, f"Opened directory: {case_dir}")
            else:
                self.report({'ERROR'}, f"Failed to open {case_dir}")
                set_ui_error("Failed to open directory natively.")
        else:
            self.report({'ERROR'}, "Export directory does not exist yet. Run Generate cfMesh first.")
            set_ui_error("Export directory does not exist.")
            
        return {'FINISHED'}
