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
        
        # OpenFOAM 11: simpleFoam is deprecated, use foamRun
        if props.solver_type == 'simpleFoam':
            solver_cmd = 'foamRun -solver incompressibleFluid'
        else:
            solver_cmd = props.solver_type
        
        command = f"{source_cmd} && {solver_cmd}"
        run_command_async(command, case_dir)
        
        self.report({'INFO'}, f"Started {solver_cmd} in background.")
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

class OBJECT_OT_RunCheckMesh(bpy.types.Operator):
    bl_idname = "object.run_checkmesh"
    bl_label = "Check Mesh Quality"
    bl_description = "Runs OpenFOAM checkMesh and displays quality metrics"
    
    def execute(self, context):
        import re
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        if not os.path.isdir(os.path.join(case_dir, "constant", "polyMesh")):
            self.report({'ERROR'}, "No mesh found. Run 'Generate cfMesh' first.")
            set_ui_error("No mesh to check. Generate mesh first.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        source_cmd = "source /opt/openfoam11/etc/bashrc"
        command = f"{source_cmd} && checkMesh"
        
        success, output = utils_system.run_cfmesh_command(command, case_dir)
        
        # Parse checkMesh output
        for line in output.split('\n'):
            line = line.strip()
            if 'cells:' in line and 'hex' not in line.lower():
                m = re.search(r'cells:\s*(\d+)', line)
                if m: props.checkmesh_cells = int(m.group(1))
            elif 'faces:' in line:
                m = re.search(r'faces:\s*(\d+)', line)
                if m: props.checkmesh_faces = int(m.group(1))
            elif 'points:' in line:
                m = re.search(r'points:\s*(\d+)', line)
                if m: props.checkmesh_points = int(m.group(1))
            elif 'Max non-orthogonality' in line:
                m = re.search(r'Max non-orthogonality\s*=\s*([\d.]+)', line, re.IGNORECASE)
                if m: props.checkmesh_non_ortho = float(m.group(1))
            elif 'Max skewness' in line:
                m = re.search(r'Max skewness\s*=\s*([\d.]+)', line)
                if m: props.checkmesh_skewness = float(m.group(1))
        
        if 'Mesh OK' in output:
            props.checkmesh_result = "PASSED"
            global_state.status_message = "checkMesh: PASSED"
        elif 'Failed' in output or 'FAILED' in output:
            props.checkmesh_result = "FAILED"
            set_ui_error("checkMesh: FAILED — mesh has quality issues")
        else:
            props.checkmesh_result = "COMPLETED"
            global_state.status_message = "checkMesh: Completed"
        
        self.report({'INFO'}, f"checkMesh: {props.checkmesh_cells} cells, quality: {props.checkmesh_result}")
        return {'FINISHED'}

class OBJECT_OT_ShowResiduals(bpy.types.Operator):
    bl_idname = "object.show_residuals"
    bl_label = "Parse Solver Log"
    bl_description = "Reads the solver log and extracts final residual values"
    
    def execute(self, context):
        import re
        import glob
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        
        # Find solver log — look for log files or parse stdout saved by our async runner
        log_content = global_state.last_output
        
        if not log_content:
            self.report({'ERROR'}, "No solver output found. Run the solver first.")
            set_ui_error("No solver output. Run simulation first.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        # Parse residuals from OpenFOAM output
        # Format: "Solving for Ux, Initial residual = 0.123, Final residual = 0.00456"
        residuals = {}
        iterations = 0
        
        for line in log_content.split('\n'):
            m = re.search(r'Solving for (\w+),.*Final residual = ([\d.e+-]+)', line)
            if m:
                field_name = m.group(1)
                value = float(m.group(2))
                residuals[field_name] = value
            
            # Count time steps
            if line.strip().startswith('Time ='):
                iterations += 1
        
        # Map to properties
        props.residual_Ux = residuals.get('Ux', 0.0)
        props.residual_Uy = residuals.get('Uy', 0.0)
        props.residual_Uz = residuals.get('Uz', 0.0)
        props.residual_p = residuals.get('p', 0.0)
        props.residual_k = residuals.get('k', 0.0)
        props.residual_omega = residuals.get('omega', residuals.get('epsilon', 0.0))
        props.solver_iterations = iterations
        
        # Determine convergence
        if not residuals:
            props.solver_converged = "No Residuals Found"
            set_ui_error("No residual data in solver output. Solver may not have run.")
            return {'CANCELLED'}
        
        max_residual = max(residuals.values())
        if max_residual < 1e-4:
            props.solver_converged = "Converged"
            global_state.status_message = f"Solver: Converged ({iterations} iterations)"
        elif max_residual > 1.0:
            props.solver_converged = "Diverged"
            set_ui_error(f"Solver DIVERGED — max residual: {max_residual:.2e}")
        else:
            props.solver_converged = "In Progress"
            global_state.status_message = f"Solver: In Progress ({iterations} steps, max res: {max_residual:.2e})"
        
        self.report({'INFO'}, f"Residuals parsed: {len(residuals)} fields, {iterations} iterations")
        return {'FINISHED'}

class OBJECT_OT_ColorByField(bpy.types.Operator):
    bl_idname = "object.color_by_field"
    bl_label = "Color Mesh by Field"
    bl_description = "Applies vertex colors to the mesh based on CFD field data"
    
    def execute(self, context):
        import struct
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        obj = context.active_object
        
        # --- Validation ---
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object first (use 'Load Meshed Result').")
            set_ui_error("Select a mesh object first.")
            return {'CANCELLED'}
        
        if not os.path.isdir(case_dir):
            self.report({'ERROR'}, "Case directory not found.")
            set_ui_error("Case directory not found.")
            return {'CANCELLED'}
        
        # Find the latest time directory with field data
        field_name = props.color_field if props.color_field != 'U_mag' else 'U'
        time_dirs = []
        for d in os.listdir(case_dir):
            try:
                t = float(d)
                field_path = os.path.join(case_dir, d, field_name)
                if os.path.isfile(field_path):
                    time_dirs.append((t, d))
            except ValueError:
                continue
        
        if not time_dirs:
            # Also check 0/ directory
            field_path = os.path.join(case_dir, "0", field_name)
            if os.path.isfile(field_path):
                time_dirs.append((0.0, "0"))
        
        if not time_dirs:
            self.report({'ERROR'}, f"No field data '{field_name}' found. Run solver first.")
            set_ui_error(f"No '{field_name}' field data. Run solver first.")
            return {'CANCELLED'}
        
        # Use latest time step
        time_dirs.sort(key=lambda x: x[0])
        latest_dir = time_dirs[-1][1]
        field_path = os.path.join(case_dir, latest_dir, field_name)
        
        clear_ui_status()
        
        # Parse the OpenFOAM field file for internalField values
        try:
            values = self.parse_foam_field(field_path, props.color_field)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to parse field: {e}")
            set_ui_error(f"Field parse error: {str(e)[:50]}")
            return {'CANCELLED'}
        
        if not values:
            self.report({'ERROR'}, "Could not extract field values.")
            set_ui_error("No field values found in file.")
            return {'CANCELLED'}
        
        # Apply vertex colors
        try:
            self.apply_vertex_colors(obj, values, props.color_field)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply colors: {e}")
            set_ui_error(f"Color error: {str(e)[:50]}")
            return {'CANCELLED'}
        
        # Switch to Material Preview so colors are visible
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
        
        field_label = "Pressure" if props.color_field == 'p' else "Velocity Magnitude"
        global_state.status_message = f"Colored by {field_label} (t={latest_dir})"
        self.report({'INFO'}, f"Mesh colored by {field_label} from time={latest_dir}")
        return {'FINISHED'}
    
    def parse_foam_field(self, filepath, field_type):
        """Parse an OpenFOAM field file and extract internalField values."""
        import re
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        values = []
        
        # Find the internalField section
        if 'nonuniform' in content:
            # OF11 format:
            #   internalField   nonuniform List<scalar> 
            #   17228
            #   (
            #   9.38424
            #   ...
            # OR for vectors:
            #   internalField   nonuniform List<vector> 
            #   17228
            #   (
            #   (6.92443 -0.112326 -0.113665)
            
            # Find the opening parenthesis after the count
            m = re.search(r'internalField\s+nonuniform\s+List<(?:scalar|vector)>\s*\n(\d+)\s*\n\(', content)
            if m:
                count = int(m.group(1))
                start = m.end()
                data_section = content[start:]
                
                lines = data_section.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # Stop at closing parenthesis
                    if line == ')' or line == ');':
                        break
                    
                    if not line:
                        continue
                    
                    try:
                        if field_type == 'p':
                            # Scalar: just a number per line
                            val = float(line)
                            values.append(val)
                        elif field_type == 'U_mag':
                            # Vector: (Ux Uy Uz) — strip parens
                            cleaned = line.strip('(').strip(')')
                            parts = cleaned.split()
                            if len(parts) == 3:
                                ux, uy, uz = float(parts[0]), float(parts[1]), float(parts[2])
                                values.append(math.sqrt(ux**2 + uy**2 + uz**2))
                    except ValueError:
                        continue
                    
                    if len(values) >= count:
                        break
        
        elif 'uniform' in content:
            # Uniform field — single value for all cells
            if field_type == 'p':
                m = re.search(r'internalField\s+uniform\s+([-\d.e+-]+)', content)
                if m:
                    values = [float(m.group(1))] * 100
            elif field_type == 'U_mag':
                m = re.search(r'internalField\s+uniform\s+\(([-\d.e+\-\s]+)\)', content)
                if m:
                    parts = m.group(1).split()
                    if len(parts) == 3:
                        mag = math.sqrt(sum(float(x)**2 for x in parts))
                        values = [mag] * 100
        
        return values
    
    def apply_vertex_colors(self, obj, values, field_type):
        """Apply a color gradient to mesh vertices based on field values."""
        mesh = obj.data
        
        # Create or get vertex color layer
        color_layer_name = f"CFD_{field_type}"
        if color_layer_name not in mesh.color_attributes:
            mesh.color_attributes.new(name=color_layer_name, type='FLOAT_COLOR', domain='CORNER')
        
        color_layer = mesh.color_attributes[color_layer_name]
        mesh.color_attributes.active_color = color_layer
        
        # Normalize values to 0-1 range
        if len(values) < 2:
            return
            
        vmin = min(values)
        vmax = max(values)
        val_range = vmax - vmin if vmax != vmin else 1.0
        
        # Map values to vertices (use as many as we have, cycling if needed)
        num_verts = len(mesh.vertices)
        vert_values = []
        for i in range(num_verts):
            idx = i % len(values)
            normalized = (values[idx] - vmin) / val_range
            vert_values.append(normalized)
        
        # Apply colors per face corner (loop)
        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                vert_idx = mesh.loops[loop_idx].vertex_index
                t = vert_values[vert_idx] if vert_idx < len(vert_values) else 0.5
                
                # Blue → Cyan → Green → Yellow → Red (jet colormap)
                r, g, b = self.jet_colormap(t)
                color_layer.data[loop_idx].color = (r, g, b, 1.0)
        
        # Create/update material to show vertex colors
        mat_name = "CFD_Visualization"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        
        # Vertex Color -> Principled BSDF -> Output
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (200, 0)
        
        vcol_node = nodes.new('ShaderNodeVertexColor')
        vcol_node.location = (0, 0)
        vcol_node.layer_name = color_layer_name
        
        links.new(vcol_node.outputs['Color'], bsdf_node.inputs['Base Color'])
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # Assign material to object
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
    
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
