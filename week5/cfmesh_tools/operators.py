import bpy
import os
import math
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

def set_ui_error(message):
    """Set an error message that appears in the red alert box in the UI panel."""
    global_state.is_error = True
    global_state.status_message = message

def clear_ui_status():
    """Reset the UI status to idle."""
    global_state.is_error = False
    global_state.status_message = "Idle"

class OBJECT_OT_ImportSTL(bpy.types.Operator):
    bl_idname = "object.import_stl_geometry"
    bl_label = "Import STL Geometry"
    bl_description = "Import an external STL file as the geometry to mesh"
    
    filepath: bpy.props.StringProperty(
        subtype='FILE_PATH',
        default="",
    )
    
    filter_glob: bpy.props.StringProperty(
        default="*.stl;*.STL",
        options={'HIDDEN'},
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        filepath = self.filepath
        
        # --- Validation: File selected ---
        if not filepath:
            self.report({'ERROR'}, "No file selected.")
            set_ui_error("No STL file selected.")
            return {'CANCELLED'}
        
        # --- Validation: File exists ---
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            set_ui_error(f"File not found: {os.path.basename(filepath)}")
            return {'CANCELLED'}
        
        # --- Validation: File extension ---
        if not filepath.lower().endswith('.stl'):
            self.report({'ERROR'}, "Only .stl files are supported.")
            set_ui_error("Invalid file type. Only .stl files supported.")
            return {'CANCELLED'}
        
        # --- Validation: File not empty ---
        if os.path.getsize(filepath) == 0:
            self.report({'ERROR'}, "STL file is empty (0 bytes).")
            set_ui_error("STL file is empty.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        try:
            # Remember existing objects to identify the new one
            existing_objects = set(bpy.data.objects.keys())
            
            bpy.ops.wm.stl_import(filepath=filepath)
            
            # Find the newly imported object(s)
            new_objects = [obj for name, obj in bpy.data.objects.items() 
                         if name not in existing_objects and obj.type == 'MESH']
            
            if new_objects:
                # Select and set active the imported geometry
                bpy.ops.object.select_all(action='DESELECT')
                for obj in new_objects:
                    obj.select_set(True)
                context.view_layer.objects.active = new_objects[0]
                
                # Report stats
                total_verts = sum(len(o.data.vertices) for o in new_objects)
                total_faces = sum(len(o.data.polygons) for o in new_objects)
                name = new_objects[0].name
                
                self.report({'INFO'}, 
                    f"Imported '{name}' — {total_verts:,} vertices, {total_faces:,} faces. Ready for meshing.")
                global_state.status_message = f"Imported: {name} ({total_faces:,} faces)"
            else:
                self.report({'WARNING'}, "Import completed but no mesh objects were created.")
                set_ui_error("Import failed — no mesh objects created.")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            set_ui_error(f"Import error: {str(e)[:50]}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

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
        
        # --- Guard: Don't stack concurrent runs ---
        if global_state.is_running:
            self.report({'ERROR'}, "A process is already running. Wait for it to finish.")
            set_ui_error("A process is already running. Wait for it to finish.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        # --- Validation: Object geometry ---
        if len(obj.data.polygons) == 0:
            self.report({'ERROR'}, "The selected object has no geometry (0 polygons).")
            set_ui_error("Selected object has no geometry (0 polygons).")
            return {'CANCELLED'}
        
        # --- Validation: Cell size sanity ---
        if props.base_cell_size < 0.01:
            self.report({'ERROR'}, f"Cell size {props.base_cell_size} is too small. This would generate millions of cells. Use >= 0.01.")
            set_ui_error(f"Cell size {props.base_cell_size} too small (min 0.01).")
            return {'CANCELLED'}
        
        if props.base_cell_size > 5.0:
            self.report({'WARNING'}, "Cell size is very large — the mesh may be too coarse to capture geometry.")
        
        # --- Validation: Boundary layer params ---
        if props.boundary_layers > 10:
            self.report({'WARNING'}, "High boundary layer count (>10) may cause mesh quality issues.")
            
        if props.boundary_layers > 0 and props.layer_thickness <= 1.0:
            self.report({'WARNING'}, "Thickness ratio should be > 1.0 for boundary layer expansion.")
            
        if context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        try:
            case_dir = bpy.path.abspath(props.export_dir)
            
            # --- Validation: Export directory ---
            if not case_dir or case_dir.strip() in ("", "/"):
                self.report({'ERROR'}, "Export directory is empty or invalid.")
                set_ui_error("Export directory is empty or invalid.")
                return {'CANCELLED'}
            
            # Normalize the path
            case_dir = os.path.normpath(case_dir)
            
            # Walk up the path to find deepest existing ancestor
            # Reject if more than 1 level needs creation (prevents /abc/xyz/fake)
            check_path = case_dir
            levels_missing = 0
            while check_path and check_path != os.path.dirname(check_path):
                if os.path.exists(check_path):
                    break
                levels_missing += 1
                check_path = os.path.dirname(check_path)
            
            if levels_missing > 1:
                self.report({'ERROR'}, f"Invalid path — too many missing directories: {case_dir}")
                set_ui_error(f"Invalid path: {case_dir}")
                return {'CANCELLED'}
                
            os.makedirs(case_dir, exist_ok=True)
            if not os.access(case_dir, os.W_OK):
                self.report({'ERROR'}, f"Cannot write to export directory: {case_dir}")
                set_ui_error(f"No write permission: {case_dir}")
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
                set_ui_error("Failed to generate OpenFOAM case files.")
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
            
            # --- Validation: STL was actually exported ---
            if not os.path.isfile(stl_path) or os.path.getsize(stl_path) == 0:
                self.report({'ERROR'}, "STL export failed — file is missing or empty.")
                set_ui_error("STL export failed — file is empty or missing.")
                return {'CANCELLED'}
            
            self.report({'INFO'}, f"Exported {obj.name} to {stl_path}")
            self.report({'INFO'}, "Successfully generated OpenFOAM dictionaries!")
            print(f"Mesh Generation Triggered. Case saved in: {case_dir}")
            
            source_cmd = "source /opt/openfoam11/etc/bashrc"
            full_cmd = f"{source_cmd} && blockMesh && snappyHexMesh -overwrite && foamToSurface -latestTime constant/triSurface/result.stl"
            
            run_command_async(full_cmd, case_dir)
            self.report({'INFO'}, "Meshing started in background. Check 'Status' above.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            set_ui_error(f"Python: {str(e)[:50]}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}

class OBJECT_OT_RunSolver(bpy.types.Operator):
    bl_idname = "object.run_solver"
    bl_label = "Run Simulation"
    bl_description = "Starts the OpenFOAM solver (icoFoam/simpleFoam)"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        # --- Guard: Don't stack concurrent runs ---
        if global_state.is_running:
            self.report({'ERROR'}, "A process is already running. Wait for it to finish.")
            set_ui_error("A process is already running. Wait for it to finish.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        # --- Validation: Case directory ---
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, f"Case directory does not exist: {case_dir}")
            set_ui_error("Case directory does not exist. Run mesh first.")
            return {'CANCELLED'}
        
        # --- Validation: Essential OpenFOAM files ---
        control_dict = os.path.join(case_dir, "system", "controlDict")
        if not os.path.isfile(control_dict):
            self.report({'ERROR'}, "No OpenFOAM case found. Run 'Generate cfMesh' first.")
            set_ui_error("No OpenFOAM case found. Generate mesh first.")
            return {'CANCELLED'}
        
        # --- Validation: Mesh must exist ---
        poly_mesh = os.path.join(case_dir, "constant", "polyMesh")
        if not os.path.isdir(poly_mesh):
            self.report({'ERROR'}, "No mesh found. Run 'Generate cfMesh' first to create the mesh.")
            set_ui_error("No mesh found. Generate mesh first.")
            return {'CANCELLED'}
        
        # --- Validation: Velocity must not be zero ---
        vel = list(props.inlet_velocity)
        vel_mag = math.sqrt(vel[0]**2 + vel[1]**2 + vel[2]**2)
        if vel_mag < 1e-10:
            self.report({'ERROR'}, "Inlet velocity is zero. Set a non-zero velocity.")
            set_ui_error("Inlet velocity is zero — solver will not converge.")
            return {'CANCELLED'}
        
        # --- Validation: Viscosity ---
        if props.kinematic_viscosity <= 0:
            self.report({'ERROR'}, "Kinematic viscosity must be positive.")
            set_ui_error("Kinematic viscosity must be > 0.")
            return {'CANCELLED'}
        
        # --- Validation: Solver-turbulence compatibility ---
        if props.solver_type == 'icoFoam' and props.turbulence_model != 'laminar':
            self.report({'ERROR'}, "icoFoam only supports laminar flow. Use simpleFoam for turbulence.")
            set_ui_error("icoFoam is laminar-only. Switch to simpleFoam.")
            return {'CANCELLED'}
        
        # --- Validation: Turbulence values ---
        if props.turbulence_model in ('kEpsilon', 'kOmegaSST'):
            if props.turb_k <= 0:
                self.report({'ERROR'}, "Turbulent kinetic energy (k) must be > 0.")
                set_ui_error("k must be > 0. Check velocity and turbulence intensity.")
                return {'CANCELLED'}
        
        source_cmd = "source /opt/openfoam11/etc/bashrc"
        
        utils_mesh.generate_fields(
            case_dir, 
            props.solver_type, 
            props.kinematic_viscosity, 
            list(props.inlet_velocity),
            props.turbulence_model,
            turb_k=props.turb_k,
            turb_epsilon=props.turb_epsilon,
            turb_omega=props.turb_omega,
            turb_nut=props.turb_nut
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
            bpy.ops.wm.stl_import(filepath=result_stl)
            self.report({'INFO'}, "Successfully imported meshed result!")
        else:
            self.report({'ERROR'}, f"Result STL not found at {result_stl}. Did you run meshing?")
            set_ui_error("result.stl not found. Run mesh generation first.")
            
        return {'FINISHED'}
