import bpy
import os
from .ops_utils import set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_system

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
        
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        
        if props.checkmesh_write_fields:
            global_state.status_message = "checkMesh: Writing quality fields..."
            command = f"{source_cmd} && checkMesh -allTopology -allGeometry -writeAllFields -time 0"
        else:
            global_state.status_message = "checkMesh: Running..."
            command = f"{source_cmd} && checkMesh"

        def parse_output(success, output):
            # Parse checkMesh output
            props.checkmesh_bad_cells = 0
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('***Number of') and ':' in line:
                    m = re.search(r':\s*(\d+)', line)
                    if m: props.checkmesh_bad_cells += int(m.group(1))
                    
                if 'cells:' in line and 'hex' not in line.lower():
                    m = re.search(r'cells:\s*(\d+)', line)
                    if m: props.checkmesh_cells = int(m.group(1))
                elif 'faces:' in line:
                    m = re.search(r'faces:\s*(\d+)', line)
                    if m: props.checkmesh_faces = int(m.group(1))
                elif 'points:' in line:
                    m = re.search(r'points:\s*(\d+)', line)
                    if m: props.checkmesh_points = int(m.group(1))
                elif 'non-orthogonality' in line.lower():
                    m = re.search(r'non-orthogonality.*?Max[\s:=]+([\d.]+)', line, re.IGNORECASE)
                    if not m:
                        m = re.search(r'Max non-orthogonality[\s:=]+([\d.]+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_non_ortho = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'Max skewness' in line:
                    m = re.search(r'Max skewness\s*=\s*([\d.]+)', line)
                    if m:
                        try: props.checkmesh_skewness = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'Max aspect ratio' in line:
                    m = re.search(r'Max aspect ratio\s*=\s*([\d.e+-]+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_aspect_ratio = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'Minimum volume' in line:
                    m = re.search(r'Minimum volume\s*=\s*([\d.e+-]+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_min_vol = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'Minimum face area' in line:
                    m = re.search(r'Minimum face area\s*=\s*([\d.e+-]+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_min_area = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'Min face weight' in line or 'Min volume ratio' in line:
                    m = re.search(r'(?:Min face weight|Min volume ratio)\s*=\s*([\d.e+-]+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_min_weight = float(m.group(1).rstrip('. \t'))
                        except ValueError: pass
                elif 'faces with concave angles' in line.lower() or 'concave faces' in line.lower():
                    m = re.search(r'(\d+)\s+faces with concave angles|concave faces.*?\b(\d+)', line, re.IGNORECASE)
                    if m:
                        try: props.checkmesh_concave = int(m.group(1) or m.group(2))
                        except ValueError: pass
            
            if 'Mesh OK' in output:
                props.checkmesh_result = "PASSED"
                global_state.status_message = "checkMesh: PASSED"
            elif 'Failed' in output or 'FAILED' in output:
                props.checkmesh_result = "FAILED"
                set_ui_error("checkMesh: FAILED — mesh has quality issues")
            else:
                props.checkmesh_result = "COMPLETED"
                global_state.status_message = "checkMesh: Completed"

        from .ops_utils import run_command_async
        run_command_async(command, case_dir, report_callback=parse_output, log_filename="checkMesh.log")
        
        self.report({'INFO'}, "checkMesh running in background...")
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
        
        # Find solver log — look for solver.log in the case directory,
        # then fall back to global_state.last_output if not found.
        log_content = ""
        solver_log_path = os.path.join(case_dir, "solver.log")
        if os.path.isfile(solver_log_path):
            try:
                with open(solver_log_path, 'r') as sf:
                    log_content = sf.read()
            except Exception as e:
                print(f"[cfMesh] Error reading solver.log: {e}")
        
        if not log_content:
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
