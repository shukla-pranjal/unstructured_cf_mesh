import bpy
import os
import math
import shutil
from .ops_utils import run_command_async, set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_mesh

def _clean_old_time_dirs(case_dir):
    """
    Removes all numeric time directories from the root case and all processor*
    subdirectories, except for t=0. This is required before re-running
    decomposePar -force to prevent 'cannot find processorN/<time>/p' errors
    that occur when the processor dirs are out of sync with the root case.
    """
    dirs_to_clean = [case_dir] + [
        os.path.join(case_dir, d)
        for d in os.listdir(case_dir)
        if d.startswith("processor") and os.path.isdir(os.path.join(case_dir, d))
    ]

    for target_dir in dirs_to_clean:
        for entry in os.listdir(target_dir):
            full_path = os.path.join(target_dir, entry)
            if not os.path.isdir(full_path):
                continue
            try:
                t = float(entry)
                if t > 0.0:
                    shutil.rmtree(full_path)
                    print(f"  [Cleanup] Removed: {full_path}")
            except ValueError:
                pass  # not a time directory, skip

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
        
        source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
        utils_mesh.write_decompose_par(case_dir, props.cpu_cores)
        
        utils_mesh.generate_fields(
            case_dir, 
            props.solver_type, 
            props.kinematic_viscosity, 
            list(props.inlet_velocity),
            props.turbulence_model,
            turb_k=props.turb_k,
            turb_epsilon=props.turb_epsilon,
            turb_omega=props.turb_omega,
            turb_nut=props.turb_nut,
            start_time=props.start_time,
            end_time=props.end_time,
            delta_t=props.delta_t,
            write_interval=props.write_interval,
            boundary_patches=props.boundary_patches
        )
        
        if props.cpu_cores > 1:
            _clean_old_time_dirs(case_dir)  # fast Python pre-clean
            # Shell-level cleanup is the guaranteed guard: rm -rf processor* wipes
            # stale time dirs that decomposePar -force would otherwise leave intact,
            # preventing the "cannot find processor0/<time>/p" fatal error on re-run.
            cleanup_cmd = "rm -rf processor*"
            if props.solver_type == 'simpleFoam':
                run_solver = f"{cleanup_cmd} && potentialFoam -writephi && decomposePar -force && mpirun -np {props.cpu_cores} simpleFoam -parallel && reconstructPar -latestTime"
            else:
                run_solver = f"{cleanup_cmd} && decomposePar -force && mpirun -np {props.cpu_cores} {props.solver_type} -parallel && reconstructPar -latestTime"
        else:
            if props.solver_type == 'simpleFoam':
                run_solver = f"potentialFoam -writephi && simpleFoam"
            else:
                run_solver = f"{props.solver_type}"
        
        command = f"{source_cmd} && {run_solver}"
        run_command_async(command, case_dir)
        
        self.report({'INFO'}, f"Started {props.solver_type} in background.")
        return {'FINISHED'}
