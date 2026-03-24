import bpy
import os
import threading
from .properties import global_state
from . import utils_mesh
from . import utils_system

def run_command_async(command, working_dir, report_callback=None):
    def task():
        global_state.is_running = True
        global_state.is_error = False
        global_state.status_message = "Processing..."
        
        success, output = utils_system.run_cfmesh_command(command, working_dir)
        
        global_state.last_output = output
        if success:
            global_state.status_message = "Finished Successfully"
        else:
            global_state.is_error = True
            lines = [line.strip() for line in output.split('\n') if line.strip()]
            if lines:
                err_msg = lines[-1]
                if "FatalError" in output or "FATAL" in output:
                    for line in lines:
                        if "Fatal" in line or "FATAL" in line:
                            err_msg = line
                            break
                global_state.status_message = f"{err_msg[:60]}..." if len(err_msg) > 60 else err_msg
            else:
                global_state.status_message = "Error: Process crashed silently."
        
        global_state.is_running = False

    global_state.thread = threading.Thread(target=task)
    global_state.thread.start()
    
    bpy.app.timers.register(check_async_status)

def check_async_status():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
            
    if global_state.is_running:
        return 0.5
    return None

class OBJECT_OT_GenerateCFMesh(bpy.types.Operator):
    bl_idname = "object.generate_cfmesh"
    bl_label = "Generate cfMesh"
    bl_description = "Exports STL and generates meshDict locally"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        props = context.scene.cfmesh_props
        obj = context.active_object
        
        if len(obj.data.polygons) == 0:
            self.report({'ERROR'}, "The selected object has no geometry (0 polygons).")
            return {'CANCELLED'}
        
        if props.boundary_layers > 10:
            self.report({'WARNING'}, "Generation may take a long time due to high boundary layer count.")
            
        if context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        try:
            case_dir = bpy.path.abspath(props.export_dir)
            if not case_dir or case_dir == "/" or case_dir == "":
                self.report({'ERROR'}, "Invalid Export Directory.")
                return {'CANCELLED'}
                
            os.makedirs(case_dir, exist_ok=True)
            if not os.access(case_dir, os.W_OK):
                self.report({'ERROR'}, f"Cannot write to export directory: {case_dir}")
                return {'CANCELLED'}
            
            success = utils_mesh.create_case_structure(
                base_dir=case_dir,
                cell_size=props.base_cell_size,
                boundary_layers=props.boundary_layers,
                thickness_ratio=props.layer_thickness,
                stl_name="mesh.stl"
            )
            
            if not success:
                self.report({'ERROR'}, "Failed to generate OpenFOAM structure.")
                return {'CANCELLED'}

            tri_surface_dir = os.path.join(case_dir, "constant", "triSurface")
            os.makedirs(tri_surface_dir, exist_ok=True)
            stl_path = os.path.join(tri_surface_dir, "mesh.stl")
            
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
            bpy.ops.object.modifier_add(type='TRIANGULATE')
            bpy.ops.object.modifier_apply(modifier=obj.modifiers[-1].name)
            
            bpy.ops.wm.stl_export(
                filepath=stl_path,
                export_selected_objects=True,
                global_scale=1.0
            )
            self.report({'INFO'}, f"Exported {obj.name} to {stl_path}")
            
            self.report({'INFO'}, "Successfully generated OpenFOAM dictionaries!")
            print(f"Mesh Generation Triggered. Case saved in: {case_dir}")
            
            source_cmd = "source /opt/openfoam11/etc/bashrc"
            full_cmd = f"{source_cmd} && blockMesh && snappyHexMesh -overwrite && foamToSurface -latestTime constant/triSurface/result.stl"
            
            run_command_async(full_cmd, case_dir)
            self.report({'INFO'}, "Meshing started in background. Check 'Status' above.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}

class OBJECT_OT_RunSolver(bpy.types.Operator):
    bl_idname = "object.run_solver"
    bl_label = "Run Simulation"
    bl_description = "Starts the OpenFOAM solver (icoFoam/simpleFoam)"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        source_cmd = "source /opt/openfoam11/etc/bashrc"
        
        utils_mesh.generate_fields(
            case_dir, 
            props.solver_type, 
            props.kinematic_viscosity, 
            list(props.inlet_velocity),
            props.turbulence_model
        )
        
        command = f"{source_cmd} && {props.solver_type}"
        run_command_async(command, case_dir)
        
        self.report({'INFO'}, f"Started {props.solver_type} in background.")
        return {'FINISHED'}

class OBJECT_OT_LaunchParaView(bpy.types.Operator):
    bl_idname = "object.launch_paraview"
    bl_label = "Launch ParaView"
    bl_description = "Opens the current case in ParaView"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        utils_system.launch_paraview(case_dir)
        return {'FINISHED'}

class OBJECT_OT_LoadResult(bpy.types.Operator):
    bl_idname = "object.load_result"
    bl_label = "Load Meshed Result"
    bl_description = "Imports the result.stl into the scene"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        result_stl = os.path.join(case_dir, "constant", "triSurface", "result.stl")
        
        if os.path.isfile(result_stl):
            bpy.ops.wm.stl_import(filepath=result_stl)
            self.report({'INFO'}, "Successfully imported meshed result!")
        else:
            self.report({'ERROR'}, f"Result STL not found at {result_stl}. Did you run meshing?")
            
        return {'FINISHED'}
