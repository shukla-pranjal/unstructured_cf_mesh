import bpy
import os
from .ops_utils import run_command_async, set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_mesh


def _sanitize_patch_name(name: str) -> str:
    """Return a valid OpenFOAM patch name.

    Rules:
    - Replace spaces and hyphens with underscores.
    - Prefix 'p_' if the first character is a digit  (OpenFOAM boundary
      parser reads a leading digit as the patch-count integer and then
      fails on the rest of the name).
    """
    name = name.replace(' ', '_').replace('-', '_')
    if name and name[0].isdigit():
        name = 'p_' + name
    return name



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

        # --- Guard: Check OpenFOAM is installed ---
        import shutil
        if not shutil.which("cartesianMesh"):
            # Try sourcing OpenFOAM first via a quick check
            import subprocess
            probe = subprocess.run(
                "source /usr/lib/openfoam/openfoam2412/etc/bashrc && which cartesianMesh",
                shell=True, executable='/bin/bash',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if probe.returncode != 0:
                self.report({'ERROR'},
                    "OpenFOAM not found. Please install OpenFOAM 2412 or check your installation path.")
                set_ui_error("OpenFOAM not found. Is it installed?")
                return {'CANCELLED'}

        if context.active_object and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # --- Validation: Object geometry ---
        if not obj or (obj.type == 'MESH' and len(obj.data.polygons) == 0):
            self.report({'ERROR'}, "The selected active object has no geometry.")
            set_ui_error("Selected object has no geometry.")
            return {'CANCELLED'}

        # --- Validation: Non-manifold geometry check ---
        import bmesh as _bmesh_check
        bm_check = _bmesh_check.new()
        bm_check.from_mesh(obj.data)
        bm_check.edges.ensure_lookup_table()
        non_manifold = [e for e in bm_check.edges if not e.is_manifold]
        bm_check.free()
        if non_manifold:
            msg = f"{len(non_manifold)} non-manifold edges detected. Please fix in Edit Mode."
            self.report({'ERROR'}, msg)
            set_ui_error(msg)
            return {'CANCELLED'}
        
        # --- Validation: Cell size sanity ---
        # Dynamically compute minimum safe cell size based on geometry (1/1000 of max dim)
        import math as _math
        bb_q = obj.bound_box
        xs_q = [v[0] for v in bb_q]; ys_q = [v[1] for v in bb_q]; zs_q = [v[2] for v in bb_q]
        max_dim = max(
            max(xs_q)-min(xs_q),
            max(ys_q)-min(ys_q),
            max(zs_q)-min(zs_q)
        )
        min_sensible = max(0.001, max_dim / 1000.0)
        if props.base_cell_size < min_sensible:
            self.report({'ERROR'},
                f"Cell size {props.base_cell_size:.4f} m is dangerously small for this geometry "
                f"({max_dim:.1f} m). "
                f"Minimum recommended: {min_sensible:.4f} m (1/1000 of longest dimension). "
                f"This would generate millions of cells."
            )
            set_ui_error(f"Cell size {props.base_cell_size:.4f} m too small. Min recommended: {min_sensible:.4f} m")
            return {'CANCELLED'}

        if props.base_cell_size > max_dim * 0.9:
            self.report({'WARNING'},
                f"Cell size {props.base_cell_size:.2f} m is larger than 90% of the geometry ({max_dim:.1f} m). "
                "Mesh may be too coarse to capture any features."
            )

        # --- Cell Count Estimator (re-uses same logic as live UI estimator) ---
        from ..properties import _compute_cell_estimate
        est, explosion_msg = _compute_cell_estimate(props)
        props.est_cell_count = est
        props.cell_explosion_message = explosion_msg

        # --- HARD BLOCK: Prevent Cell Explosion ---
        if est > 5_000_000:
            # Build human-readable recommendation block
            lines = explosion_msg.split('\n') if explosion_msg else [f"~{est:,} cells exceeds the 5M limit."]
            msg = " | ".join(l.strip() for l in lines if l.strip())
            self.report({'ERROR'}, msg)
            set_ui_error(f"Cell Explosion! (~{est:,} cells) — see panel for fix suggestions")
            return {'CANCELLED'}
            
        elif est > 2_000_000:
            self.report({'WARNING'},
                f"Estimated ~{est:,} cells. This may take a long time and use a lot of memory. "
                "Consider increasing the Base or Box Cell Size.")
        elif est > 0:
            self.report({'INFO'}, f"Estimated ~{est:,} cells based on volume.")

        
        # --- Validation: Boundary layer params ---
        if props.boundary_layers > 10:
            self.report({'WARNING'}, "High boundary layer count (>10) may cause mesh quality issues.")
            
        if props.boundary_layers > 0 and props.layer_thickness <= 1.0:
            self.report({'WARNING'}, "Thickness ratio should be > 1.0 for boundary layer expansion.")
            
        # Mode set was moved to the top of the function
            
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
            
            edge_refs = [{"name": props.trailing_edge_patch_name, "cell_size": props.trailing_edge_cell_size}] if props.trailing_edge_enabled else []
            
            box_refs = []
            for b in props.box_refinements:
                box_refs.append({
                    "min": b.min_bounds,
                    "max": b.max_bounds,
                    "cell_size": b.cell_size
                })
                
            tri_surface_dir = os.path.join(case_dir, "constant", "triSurface")
            os.makedirs(tri_surface_dir, exist_ok=True)
            
            surface_refs = []
            for s in props.surface_refinements:
                if not s.ref_object:
                    self.report({'ERROR'}, f"Surface Refinement '{s.name}' is missing an object! Please select an object or remove the refinement.")
                    set_ui_error(f"Missing object in '{s.name}'")
                    return {'CANCELLED'}
                if s.ref_object.type != 'MESH':
                    self.report({'ERROR'}, f"Surface Refinement '{s.name}' uses a non-mesh object. Please select a 3D Mesh.")
                    set_ui_error(f"Invalid object type in '{s.name}'")
                    return {'CANCELLED'}
                    
                filename = f"{_sanitize_patch_name(s.ref_object.name)}.stl"
                bpy.ops.object.select_all(action='DESELECT')
                s.ref_object.select_set(True)
                context.view_layer.objects.active = s.ref_object
                bpy.ops.wm.stl_export(
                    filepath=os.path.join(tri_surface_dir, filename),
                    export_selected_objects=True,
                    global_scale=1.0,
                    ascii_format=True
                )
                surface_refs.append({
                    "name": _sanitize_patch_name(s.name),
                    "file": filename,
                    "cell_size": s.cell_size,
                    "thickness": s.thickness
                })
                    
            cylinder_refs = []
            for c in props.cylinder_refinements:
                cylinder_refs.append({
                    "name": c.name.replace(' ', '_'),
                    "p1": c.p1,
                    "p2": c.p2,
                    "radius": c.radius,
                    "cell_size": c.cell_size
                })

            success = utils_mesh.create_case_structure(
                base_dir=case_dir,
                cell_size=props.base_cell_size,
                boundary_layers=props.boundary_layers,
                thickness_ratio=props.layer_thickness,
                stl_name="mesh.stl",
                cpu_cores=props.cpu_cores,
                boundary_patches=props.boundary_patches,
                edge_refinements=edge_refs,
                box_refinements=box_refs,
                surface_refinements=surface_refs,
                cylinder_refinements=cylinder_refs,
                improve_quality=props.improve_mesh_quality,
                layer_optimise=props.layer_optimise,
                layer_max_iter=props.layer_max_iter
            )
            
            if not success:
                self.report({'ERROR'}, "Failed to generate OpenFOAM structure.")
                set_ui_error("Failed to generate OpenFOAM case files.")
                return {'CANCELLED'}

            tri_surface_dir = os.path.join(case_dir, "constant", "triSurface")
            os.makedirs(tri_surface_dir, exist_ok=True)
            stl_path = os.path.join(tri_surface_dir, "mesh.stl")
            
            # Multi-patch Selection Logic
            bpy.ops.object.select_all(action='DESELECT')
            active_target = None
            if len(props.boundary_patches) > 0:
                for patch in props.boundary_patches:
                    if patch.name in bpy.data.objects:
                        o = bpy.data.objects[patch.name]
                        o.select_set(True)
                        active_target = o
            else:
                if obj:
                    obj.select_set(True)
                    active_target = obj
                    
            if active_target:
                context.view_layer.objects.active = active_target
            
            # Apply Transforms
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
            # Triangulate meshes and check for sharp edges
            import bmesh
            import math
            has_sharp_edge = False
            
            for o in context.selected_objects:
                if o.type == 'MESH':
                    context.view_layer.objects.active = o
                    
                    bm = bmesh.new()
                    bm.from_mesh(o.data)
                    
                    # Check for sharp edges if trailing edge is enabled
                    if props.trailing_edge_enabled and not has_sharp_edge:
                        bm.edges.ensure_lookup_table()
                        for edge in bm.edges:
                            if len(edge.link_faces) == 2:
                                angle = edge.calc_face_angle()
                                if math.degrees(angle) > 30.0:
                                    has_sharp_edge = True
                                    break
                    
                    # Optimized Triangulation via bmesh
                    bmesh.ops.triangulate(bm, faces=bm.faces[:])
                    bm.to_mesh(o.data)
                    bm.free()
                    o.data.update()
            
            # Validation: Trailing Edge Geometry Check
            if props.trailing_edge_enabled and not has_sharp_edge:
                self.report({'ERROR'}, "Trailing edge refinement requires sharp edges. Your geometry appears completely smooth. Please disable this feature for shapes like spheres.")
                set_ui_error("No sharp edges found for trailing edge refinement.")
                return {'CANCELLED'}
            
            # Export each object as a separate ASCII STL into a temp folder
            temp_stl_dir = os.path.join(tri_surface_dir, "temp_stls")
            os.makedirs(temp_stl_dir, exist_ok=True)
            
            bpy.ops.wm.stl_export(
                filepath=temp_stl_dir + "/",
                export_selected_objects=True,
                global_scale=1.0,
                ascii_format=True,
                use_batch=True
            )
            
            # Combine them into a single multi-solid ASCII STL so cfMesh recognizes patch names
            with open(stl_path, 'w') as outfile:
                for f in os.listdir(temp_stl_dir):
                    if f.endswith('.stl'):
                        obj_name = _sanitize_patch_name(os.path.splitext(f)[0])
                        with open(os.path.join(temp_stl_dir, f), 'r') as infile:
                            first_line = True
                            for line in infile:
                                if first_line and line.startswith('solid'):
                                    outfile.write(f"solid {obj_name}\n")
                                    first_line = False
                                elif line.startswith('endsolid'):
                                    outfile.write(f"endsolid {obj_name}\n")
                                else:
                                    outfile.write(line)
                                    
            # Clean up temp dir
            import shutil
            shutil.rmtree(temp_stl_dir)
            
            # --- Validation: STL was actually exported ---
            if not os.path.isfile(stl_path) or os.path.getsize(stl_path) == 0:
                self.report({'ERROR'}, "STL export failed — file is missing or empty.")
                set_ui_error("STL export failed — file is empty or missing.")
                return {'CANCELLED'}
            
            self.report({'INFO'}, f"Exported {obj.name} to {stl_path}")
            self.report({'INFO'}, "Successfully generated OpenFOAM dictionaries!")
            print(f"Mesh Generation Triggered. Case saved in: {case_dir}")
            
            utils_mesh.write_decompose_par(case_dir, props.cpu_cores)
            
            # COMPLETELY reset the 0/ directory to ensure no old non-uniform fields remain
            import shutil
            zero_dir = os.path.join(case_dir, "0")
            if os.path.isdir(zero_dir):
                shutil.rmtree(zero_dir)
            os.makedirs(zero_dir, exist_ok=True)
            
            utils_mesh.generate_fields(
                case_dir,
                props.solver_type,
                props.kinematic_viscosity,
                props.inlet_velocity,
                props.turbulence_model,
                props.turb_k,
                props.turb_epsilon,
                props.turb_omega,
                props.turb_nut,
                props.start_time,
                props.end_time,
                props.delta_t,
                props.write_interval,
                props.boundary_patches
            )
            
            source_cmd = "source /usr/lib/openfoam/openfoam2412/etc/bashrc"
            clean_cmd = "foamListTimes -rm && rm -rf processor* postProcessing VTK constant/polyMesh"
            
            # NOTE: cartesianMesh MUST run in serial — its boundary layer generator
            # (createLayerCells) has a known segfault when run in parallel via MPI.
            # Only the solver (simpleFoam/icoFoam) benefits from multi-core execution.
            run_mesher = f"{clean_cmd} && cartesianMesh"
                
            full_cmd = f"{source_cmd} && {run_mesher} && foamToSurface -constant constant/triSurface/result.stl"
            
            run_command_async(full_cmd, case_dir, log_filename="meshing.log")
            self.report({'INFO'}, "Meshing started in background. Check 'Status' above.")
            
        except PermissionError:
            msg = "Permission denied. You cannot save the OpenFOAM case here. Please choose a folder in your Documents or Desktop."
            self.report({'ERROR'}, msg)
            set_ui_error("Permission denied. Check export path.")
            return {'CANCELLED'}
        except MemoryError:
            msg = "Out of memory. The cell size might be too small, creating too many cells. Please increase the Base Cell Size."
            self.report({'ERROR'}, msg)
            set_ui_error("Out of memory. Increase Base Cell Size.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            set_ui_error(f"Python: {str(e)[:50]}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}
