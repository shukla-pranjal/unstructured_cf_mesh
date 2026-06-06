import bpy
from .properties import global_state

class VIEW3D_PT_CFMeshPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "cfMesh"
    bl_label = "OpenFOAM Control Center"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cfmesh_props
        
        if global_state.is_running:
            box = layout.box()
            box.label(text=global_state.status_message, icon='URL')
            box.label(text="Blender is free to use while processing.")
            return
            
        if global_state.is_error:
            box = layout.box()
            box.alert = True
            box.label(text="OpenFOAM Error:", icon='CANCEL')
            box.label(text=global_state.status_message)
        elif global_state.status_message != "Idle":
            layout.label(text=f"Status: {global_state.status_message}", icon='INFO')

class VIEW3D_PT_MeshSettings(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "cfMesh"
    bl_parent_id = "VIEW3D_PT_CFMeshPanel"
    bl_label = "1. Mesh Generation"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cfmesh_props
        
        # Smart Geometry Classification: Box vs Sphere vs Cylinder
        is_box_geometry = False
        is_sphere_geometry = False
        is_cylinder_geometry = False
        
        if context.active_object and context.active_object.type == 'MESH':
            bb = context.active_object.bound_box
            xs = [v[0] for v in bb]; ys = [v[1] for v in bb]; zs = [v[2] for v in bb]
            lx = max(xs)-min(xs); ly = max(ys)-min(ys); lz = max(zs)-min(zs)
            dims = sorted([d for d in [lx, ly, lz] if d > 0])
            if len(dims) == 3 and dims[0] > 0:
                bb_is_cubic = (dims[2] / dims[0]) < 1.5
                mesh = context.active_object.data
                num_polygons = len(mesh.polygons)
                
                if num_polygons <= 1000:
                    unique_normals = { (round(f.normal.x, 3), round(f.normal.y, 3), round(f.normal.z, 3)) for f in mesh.polygons if f.normal.length > 0.1 }
                    num_unique_normals = len(unique_normals)
                else:
                    num_unique_normals = 999
                
                # 1. Box Detection
                if bb_is_cubic and num_unique_normals <= 12:
                    is_box_geometry = True
                
                # 2. Sphere & Cylinder Detection (for curved geometry)
                if not is_box_geometry and num_polygons > 0:
                    verts = mesh.vertices
                    n_verts = len(verts)
                    if n_verts > 0:
                        # Centroid in local space
                        avg_x = sum(v.co.x for v in verts) / n_verts
                        avg_y = sum(v.co.y for v in verts) / n_verts
                        avg_z = sum(v.co.z for v in verts) / n_verts
                        
                        # Radial distance of each vertex from centroid
                        dists = [ ((v.co.x - avg_x)**2 + (v.co.y - avg_y)**2 + (v.co.z - avg_z)**2)**0.5 for v in verts ]
                        min_dist = min(dists)
                        max_dist = max(dists)
                        # If min and max distance are within 5% of each other, it's a sphere!
                        if max_dist > 0 and (max_dist - min_dist) / max_dist < 0.05:
                            is_sphere_geometry = True
                        else:
                            is_cylinder_geometry = True
                            
        # Import STL button at the top
        layout.operator("object.import_stl_geometry", icon='IMPORT', text="Import STL Geometry")
        layout.operator("object.refresh_patches", icon='FILE_REFRESH', text="Load Selected as Patches")
        
        if len(props.boundary_patches) > 0:
            box = layout.box()
            box.label(text="Geometry Patches:")
            for p in props.boundary_patches:
                row = box.row()
                row.label(text=p.name, icon='MESH_DATA')
                row.prop(p, "bc_type", text="")
                
                sub = box.box()
                col = sub.column(align=True)
                col.prop(p, "boundary_layers")
                col.prop(p, "use_local_cell_size", text="Override Cell Size")
                if p.use_local_cell_size:
                    col.prop(p, "local_cell_size")
        
        layout.separator()
        
        layout.prop(props, "cpu_cores", icon='MOD_PARTICLES')
        
        col = layout.column(align=True)
        col.prop(props, "base_cell_size")
        col.prop(props, "export_dir")

        # --- Cell Count Estimator (live) ---
        if props.est_cell_count > 0:
            est_row = layout.row()
            est_row.enabled = False
            if props.est_cell_count > 5_000_000:
                est_row.alert = True
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}  ⛔ WILL BE BLOCKED!", icon='ERROR')
            elif props.est_cell_count > 2_000_000:
                est_row.alert = True
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}  ⚠ Very large!", icon='ERROR')
            elif props.est_cell_count > 500_000:
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}  (Large)", icon='INFO')
            else:
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}", icon='CHECKMARK')

        # --- Cell Explosion Smart Recommendations ---
        if props.cell_explosion_message:
            cex_box = layout.box()
            cex_box.alert = True
            for line in props.cell_explosion_message.split('\n'):
                line = line.strip()
                if line:
                    cex_box.label(text=line, icon='ERROR' if 'OVER' in line else 'DOT')

        layout.operator("object.open_export_dir", icon='FILE_FOLDER', text="Open Export Directory")
        
        layout.label(text="Boundary Layers:")
        box = layout.box()
        box.prop(props, "boundary_layers")
        if props.boundary_layers > 0:
            box.prop(props, "layer_thickness")

        # --- Trailing Edge & Mesh Quality ---
        box = layout.box()
        box.label(text="Advanced: Trailing Edge & BL", icon='MOD_EDGESPLIT')
        # Inform the user what this feature is for
        info_row = box.row()
        info_row.alert = False
        info_row.label(text="Only for sharp-edged geometry (e.g. airfoils)", icon='INFO')
        box.prop(props, "trailing_edge_enabled")
        if props.trailing_edge_enabled:
            # Additional hint when enabled
            hint = box.column(align=True)
            hint.label(text="Tip: Patch name must match a patch in your STL.", icon='QUESTION')
            col = box.column(align=True)
            col.prop(props, "trailing_edge_patch_name")
            col.prop(props, "trailing_edge_cell_size")
        
        # --- Phase 1, 2 & 4: Multiple Box Refinements & Wake ---
        box2 = layout.box()
        box2.label(text="Phase 1, 2 & 4: Box Refinements", icon='MESH_CUBE')
        
        if is_sphere_geometry or is_cylinder_geometry:
            warn_row = box2.row()
            warn_row.label(
                text="Active object is round/curved. Consider using Cylinder Refinement (Phase 5) instead.",
                icon='QUESTION'
            )
            
        row = box2.row()
        row.operator("object.add_box_refinement", text="Add Box", icon='ADD')
        row.operator("object.remove_box_refinement", text="Remove Box", icon='REMOVE')

        # Wake box button with tooltip about expected dimensions
        wake_row = box2.row(align=True)
        wake_row.operator("object.add_wake_preset", text="Auto-Generate Wake Box", icon='MOD_FLUIDSIM')
        if context.active_object and context.active_object.type == 'MESH':
            bb = context.active_object.bound_box
            xs = [v[0] for v in bb]; ys = [v[1] for v in bb]; zs = [v[2] for v in bb]
            obj_lx = max(xs)-min(xs); obj_ly = max(ys)-min(ys); obj_lz = max(zs)-min(zs)
            vel = props.inlet_velocity
            import math as _m
            v_mag = _m.sqrt(vel[0]**2+vel[1]**2+vel[2]**2)
            if v_mag > 0:
                # Calculate expected wake box size for user info
                if abs(vel[0]/v_mag) > 0.5:
                    wake_x = obj_lx*(1+3.0); wake_y = obj_ly; wake_z = obj_lz
                elif abs(vel[1]/v_mag) > 0.5:
                    wake_x = obj_lx; wake_y = obj_ly*(1+3.0); wake_z = obj_lz
                else:
                    wake_x = obj_lx; wake_y = obj_ly; wake_z = obj_lz*(1+3.0)
                info_row = box2.row()
                info_row.enabled = False
                info_row.label(
                    text=f"Wake ~{wake_x:.1f} × {wake_y:.1f} × {wake_z:.1f} m  (3× obj length, downstream only)",
                    icon='INFO'
                )

        if len(props.box_refinements) > 0:
            box2.template_list("UI_UL_list", "box_refinements", props, "box_refinements", props, "active_box_index", rows=3)
            
            if 0 <= props.active_box_index < len(props.box_refinements):
                active_box = props.box_refinements[props.active_box_index]
                col = box2.column(align=True)
                col.prop(active_box, "name")
                col.prop(active_box, "min_bounds")
                col.prop(active_box, "max_bounds")
                col.prop(active_box, "cell_size")
                
        # --- Phase 3: Surface Refinement ---
        box3 = layout.box()
        box3.label(text="Phase 3: Surface Refinement", icon='MESH_DATA')
        
        row = box3.row()
        row.operator("object.add_surface_refinement", text="Add Surface", icon='ADD')
        row.operator("object.remove_surface_refinement", text="Remove Surface", icon='REMOVE')
        
        if len(props.surface_refinements) > 0:
            box3.template_list("UI_UL_list", "surface_refinements", props, "surface_refinements", props, "active_surface_index", rows=3)
            
            if 0 <= props.active_surface_index < len(props.surface_refinements):
                active_surf = props.surface_refinements[props.active_surface_index]
                col = box3.column(align=True)
                col.prop(active_surf, "name")
                col.prop(active_surf, "ref_object")
                col.prop(active_surf, "cell_size")
                col.prop(active_surf, "thickness")
                
        # --- Phase 5: Cylinder Refinement (for ROUND/CURVED geometry only) ---
        box4 = layout.box()
        box4.label(text="Phase 5: Cylinder Refinement", icon='MESH_CYLINDER')

        if is_box_geometry:
            warn_row = box4.row()
            warn_row.alert = True
            warn_row.label(
                text="Cylinder refinement is for ROUND geometry. Not ideal for boxes.",
                icon='ERROR'
            )
        elif is_sphere_geometry:
            info_row = box4.row()
            info_row.label(
                text="Active object is a SPHERE. Cylinder refinement is highly recommended.",
                icon='CHECKMARK'
            )
        elif is_cylinder_geometry:
            info_row = box4.row()
            info_row.label(
                text="Active object is a CYLINDER. Cylinder refinement is highly recommended.",
                icon='CHECKMARK'
            )
        else:
            info_row = box4.row()
            info_row.enabled = False
            info_row.label(
                text="Active object contains round/curved geometry (cylinder refinement recommended).",
                icon='INFO'
            )

        row = box4.row()
        row.operator("object.add_cylinder_refinement", text="Add Cylinder", icon='ADD')
        row.operator("object.remove_cylinder_refinement", text="Remove Cylinder", icon='REMOVE')

        cyl_wake_row = box4.row()
        cyl_wake_row.enabled = not is_box_geometry
        cyl_wake_row.operator("object.add_cylinder_wake_preset", text="Auto-Generate Wake Cylinder", icon='MOD_FLUIDSIM')
        if is_box_geometry:
            box4.label(text="Wake Cylinder disabled — use Wake Box instead for rectangular geometry", icon='INFO')
        elif is_sphere_geometry:
            box4.label(text="Wake Cylinder enabled — ideal for spherical wakes", icon='CHECKMARK')
        elif is_cylinder_geometry:
            box4.label(text="Wake Cylinder enabled — ideal for cylindrical wakes", icon='CHECKMARK')
        else:
            box4.label(text="Wake Cylinder enabled — ideal for curved wakes", icon='CHECKMARK')

        if len(props.cylinder_refinements) > 0:
            box4.template_list("UI_UL_list", "cylinder_refinements", props, "cylinder_refinements", props, "active_cylinder_index", rows=3)
            
            if 0 <= props.active_cylinder_index < len(props.cylinder_refinements):
                active_cyl = props.cylinder_refinements[props.active_cylinder_index]
                col = box4.column(align=True)
                col.prop(active_cyl, "name")
                col.prop(active_cyl, "p1")
                col.prop(active_cyl, "p2")
                col.prop(active_cyl, "radius")
                col.prop(active_cyl, "cell_size")
            
        box.prop(props, "improve_mesh_quality")
        
        row = box.row()
        row.prop(props, "layer_optimise")
        if props.layer_optimise:
            row.prop(props, "layer_max_iter", text="Max Iter")
            
        layout.operator("object.generate_cfmesh", icon='MESH_CUBE')

class VIEW3D_PT_SolverSettings(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "cfMesh"
    bl_parent_id = "VIEW3D_PT_CFMeshPanel"
    bl_label = "2. Physics & Solver"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cfmesh_props
        
        layout.prop(props, "solver_type")
        
        row = layout.row()
        row.prop(props, "turbulence_model")
        if props.solver_type == 'icoFoam':
            row.enabled = False
        
        box = layout.box()
        box.label(text="Physical Properties:")
        box.prop(props, "fluid_type")
        
        row = box.row()
        row.prop(props, "kinematic_viscosity")
        if props.fluid_type != 'Custom':
            row.enabled = False
            
        box.prop(props, "inlet_velocity")
        
        if props.solver_type == 'icoFoam' and props.calc_reynolds_number > 2000:
            err_box = layout.box()
            err_box.alert = True
            err_box.label(text="WARNING: Flow is highly turbulent!", icon='ERROR')
            err_box.label(text=f"Reynolds No: {props.calc_reynolds_number:.0f} > 2000")
            err_box.label(text="icoFoam will likely crash. Use simpleFoam.")
        
        row = layout.row()
        row.prop(props, "show_time_controls", 
                 icon="TRIA_DOWN" if props.show_time_controls else "TRIA_RIGHT", 
                 icon_only=True, emboss=False)
        row.label(text="Time and Interval")
        
        if props.show_time_controls:
            time_box = layout.box()
            col = time_box.column(align=True)

            if props.solver_type == 'simpleFoam':
                col.label(text="Steady-State (iterations are solved, not physical time)", icon='INFO')
                row_time = col.row()
                row_time.enabled = False
                row_time.prop(props, "start_time")
                col.prop(props, "end_time", text="Max Iterations")
                row_dt = col.row()
                row_dt.enabled = False
                row_dt.prop(props, "delta_t")
                col.prop(props, "write_interval")
                # simpleFoam: frames = max_iterations / write_interval (step-based)
                wi = max(props.write_interval, 1)
                n_est = int(props.end_time / wi)
            else:
                col.prop(props, "start_time")
                col.prop(props, "end_time", text="End Time (seconds)")
                col.prop(props, "delta_t")
                col.prop(props, "write_interval")
                # icoFoam uses adjustableRunTime — writeInterval is physical seconds
                n_est = props.write_interval + 1

                # Calculate total transient time steps
                dt = max(props.delta_t, 1e-6)
                sim_duration = props.end_time - props.start_time
                time_steps = int(sim_duration / dt) if sim_duration > 0 else 0
                
                col.label(text=f"Total Steps: {time_steps:,} time-steps", icon='TIME')
                if time_steps > 1000:
                    warn_box = col.box()
                    warn_box.alert = True
                    warn_box.label(text="⚠️ Slow! High transient step count.", icon='ERROR')
                    warn_box.label(text="icoFoam resolves each step sequentially, taking much longer.")
                    warn_box.label(text="Switch to simpleFoam (steady) for fast results.")

            # --- Live frame estimate ---
            est_row = time_box.row()
            est_row.enabled = False
            if n_est <= 0:
                est_row.alert = True
                est_row.label(text="0 frames — check End Time / Write Interval", icon='ERROR')
            elif n_est == 1:
                est_row.alert = True
                est_row.label(text="~1 frame saved — reduce Write Interval for animation", icon='ERROR')
            elif n_est > 500:
                est_row.alert = True
                est_row.label(text=f"~{n_est} frames — may use a lot of disk space!", icon='INFO')
            else:
                est_row.label(text=f"~{n_est} frames will be saved", icon='RENDER_ANIMATION')


        # --- Reynolds Number Calculator: always visible ---
        rbox = layout.box()
        rbox.prop(props, "characteristic_length")
        res = rbox.column()
        res.enabled = False
        res.prop(props, "calc_reynolds_number", text="Reynolds No.")
        
        if props.solver_type == 'icoFoam':
            if props.calc_reynolds_number > 2000:
                rbox.label(text="Re > 2000: Turbulent! Use simpleFoam.", icon='ERROR')
            elif props.calc_reynolds_number > 0:
                rbox.label(text="Re < 2000: Laminar flow (icoFoam OK)", icon='CHECKMARK')

        # --- Courant Number block (icoFoam only) ---
        if props.solver_type == 'icoFoam' and props.courant_number > 0:
            co_box = layout.box()

            # Show which cell size drives Co (smallest in mesh)
            dx_base = props.base_cell_size
            dx_min  = dx_base
            for box in props.box_refinements:
                if box.cell_size > 0: dx_min = min(dx_min, box.cell_size)
            for cyl in props.cylinder_refinements:
                if cyl.cell_size > 0: dx_min = min(dx_min, cyl.cell_size)
            for surf in props.surface_refinements:
                if surf.cell_size > 0: dx_min = min(dx_min, surf.cell_size)
            import math as _m
            n_layers = props.boundary_layers
            if n_layers > 0:
                ratio = max(props.layer_thickness, 1.01)
                bl_cell = (dx_min * 0.5) / (ratio ** max(n_layers - 1, 0))
                dx_min = min(dx_min, bl_cell)

            co_row = co_box.row()
            co_row.enabled = False
            co_row.prop(props, "courant_number", text="Courant No. (Co)")

            # Explain what dx is driving it
            if abs(dx_min - dx_base) < 1e-6:
                co_box.label(text=f"Based on base cell size ({dx_base:.4f} m)", icon='INFO')
            else:
                co_box.label(
                    text=f"Based on SMALLEST cell: {dx_min:.4f} m  (not base {dx_base:.3f} m!)",
                    icon='ERROR'
                )

            # Note about local acceleration / future prediction
            co_box.label(text="*Co is an initial estimate. Local flow acceleration", icon='QUESTION')
            co_box.label(text=" around geometry will increase Co during the run.", icon='BLANK1')

            if props.courant_number >= 1.0:
                co_box.alert = True
                co_box.label(text="\u26a0 Co \u2265 1: Solver WILL diverge! Fix below:", icon='ERROR')
                sug = co_box.row()
                sug.enabled = False
                sug.prop(props, "suggested_dt", text="Max safe \u0394t")
                co_box.label(text="Or switch to simpleFoam (steady) \u2014 no Co limit", icon='INFO')
            elif props.courant_number > 0.5:
                co_box.alert = True
                co_box.label(text="Co > 0.5: Borderline. Consider reducing \u0394t.", icon='INFO')
                sug = co_box.row()
                sug.enabled = False
                sug.prop(props, "suggested_dt", text="Safer \u0394t")
            else:
                co_box.label(text="Co < 0.5: Time step is stable \u2713", icon='CHECKMARK')


        # --- Full Y+ + Turbulence calculator: only for turbulence models ---
        if props.turbulence_model in ('kEpsilon', 'kOmegaSST'):
            cbox = layout.box()
            cbox.label(text="Turbulence & Y+ Calculator", icon='CON_KINEMATIC')
            cbox.prop(props, "turbulent_intensity")
            cbox.prop(props, "target_yplus")
            
            # Dynamic Y+ Context
            if props.target_yplus <= 5.0:
                cbox.label(text="Y+ Region: Very fine (resolves boundary layer)", icon='INFO')
            elif 30.0 <= props.target_yplus <= 300.0:
                cbox.label(text="Y+ Region: Wall function region (common)", icon='INFO')
            else:
                cbox.label(text="Y+ Region: Transitional / Not Recommended", icon='ERROR')
                
            res2 = cbox.column()
            res2.enabled = False
            res2.prop(props, "calc_first_cell", text="Est. First Cell (y)")
            
            tbox = layout.box()
            tbox.enabled = False # Prevents user from manually typing k, epsilon, omega
            tbox.label(text=f"Computed {props.turbulence_model} Values:")
            tbox.prop(props, "turb_k", text="k")
            if props.turbulence_model == 'kEpsilon':
                tbox.prop(props, "turb_epsilon", text="epsilon")
            else:
                tbox.prop(props, "turb_omega", text="omega")
            tbox.prop(props, "turb_nut", text="nut")
        
        row = layout.row()
        row.scale_y = 1.2
        row.operator("object.run_solver", icon='PLAY')

class VIEW3D_PT_PostProcess(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "cfMesh"
    bl_parent_id = "VIEW3D_PT_CFMeshPanel"
    bl_label = "3. Post-Processing"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cfmesh_props
        
        # --- Mesh Quality ---
        layout.prop(props, "checkmesh_write_fields")
        layout.operator("object.run_checkmesh", icon='CHECKMARK')
        if props.checkmesh_result != "Not checked":
            qbox = layout.box()
            qbox.enabled = False
            
            if props.checkmesh_result == "PASSED":
                qbox.label(text="Mesh Quality: PASSED", icon='INFO')
            elif props.checkmesh_result == "FAILED":
                qbox.label(text="Mesh Quality: FAILED", icon='ERROR')
            else:
                qbox.label(text=f"Mesh Quality: {props.checkmesh_result}", icon='INFO')
            
            col = qbox.column(align=True)
            col.prop(props, "checkmesh_cells", text="Cells")
            col.prop(props, "checkmesh_faces", text="Faces")
            col.prop(props, "checkmesh_points", text="Points")

            # Quality metrics with graded icons
            def quality_icon(val, warn, bad):
                if val >= bad: return 'ERROR'
                if val >= warn: return 'INFO'
                return 'CHECKMARK'

            no_icon = quality_icon(props.checkmesh_non_ortho, 70, 85)
            sk_icon = quality_icon(props.checkmesh_skewness, 4, 20)
            ar_icon = quality_icon(props.checkmesh_aspect_ratio, 50, 1000)

            no_row = col.row()
            no_row.prop(props, "checkmesh_non_ortho", text="Max Non-Ortho")
            no_row.label(text="", icon=no_icon)

            sk_row = col.row()
            sk_row.prop(props, "checkmesh_skewness", text="Max Skewness")
            sk_row.label(text="", icon=sk_icon)

            ar_row = col.row()
            ar_row.prop(props, "checkmesh_aspect_ratio", text="Max Aspect Ratio")
            ar_row.label(text="", icon=ar_icon)

            col.prop(props, "checkmesh_min_vol", text="Min Volume")
            col.prop(props, "checkmesh_min_area", text="Min Area")
            col.prop(props, "checkmesh_min_weight", text="Min Face Weight")
            if props.checkmesh_concave > 0:
                col.prop(props, "checkmesh_concave", text="Concave Faces")
                
            bc_icon = 'ERROR' if props.checkmesh_bad_cells > 0 else 'CHECKMARK'
            bc_row = col.row()
            bc_row.prop(props, "checkmesh_bad_cells", text="Total Bad Cells/Faces")
            bc_row.label(text="", icon=bc_icon)
        
        # --- Region Inspection ---
        ibox = layout.box()
        ibox.prop(props, "inspect_use_bbox", icon='VIEWZOOM')
        if props.inspect_use_bbox:
            ibox.operator("object.set_inspect_bbox", icon='UV_SYNC_SELECT')
            col = ibox.column(align=True)
            col.prop(props, "inspect_bbox_min")
            col.prop(props, "inspect_bbox_max")
            ibox.operator("object.inspect_region", icon='ZOOM_SELECTED')
            
            if props.inspect_cells_count > 0:
                res = ibox.box()
                res.enabled = False
                res.label(text=f"Cells in region: {props.inspect_cells_count}", icon='MESH_DATA')
                col = res.column(align=True)
                col.prop(props, "inspect_max_nonortho")
                col.prop(props, "inspect_mean_nonortho")
                col.prop(props, "inspect_max_skewness")
                col.prop(props, "inspect_mean_skewness")
                col.prop(props, "inspect_max_aspect")

        layout.separator()
        
        # --- Solver Residuals ---
        layout.operator("object.show_residuals", icon='FCURVE')
        if props.solver_converged != "Not run":
            rbox = layout.box()
            rbox.enabled = False
            
            if props.solver_converged == "Converged":
                rbox.label(text=f"Status: {props.solver_converged}", icon='INFO')
            elif props.solver_converged == "Diverged":
                rbox.label(text=f"Status: {props.solver_converged}", icon='ERROR')
            else:
                rbox.label(text=f"Status: {props.solver_converged}", icon='TIME')
            
            rbox.prop(props, "solver_iterations", text="Time Steps")
            
            col = rbox.column(align=True)
            col.prop(props, "residual_Ux", text="Ux")
            col.prop(props, "residual_Uy", text="Uy")
            col.prop(props, "residual_Uz", text="Uz")
            col.prop(props, "residual_p", text="p")
            if props.residual_k > 0:
                col.prop(props, "residual_k", text="k")
            if props.residual_omega > 0:
                col.prop(props, "residual_omega", text="omega/eps")
        
        layout.separator()
        
        vbox = layout.box()
        vbox.label(text="Field Visualization:", icon='SHADING_RENDERED')
        vbox.prop(props, "color_field")
        vbox.prop(props, "animate_results")

        # --- Live Frame Count Preview ---
        if props.animate_results:
            import os
            case_dir = bpy.path.abspath(props.export_dir)
            vtk_dir  = os.path.join(case_dir, "VTK")
            n_frames = 0

            if os.path.isdir(vtk_dir):
                # Count VTK time dirs that contain a boundary.vtp
                for d in os.listdir(vtk_dir):
                    td = os.path.join(vtk_dir, d)
                    if os.path.isdir(td):
                        last = d.rsplit("_", 1)[-1]
                        try:
                            float(last)
                            if os.path.isfile(os.path.join(td, "boundary.vtp")):
                                n_frames += 1
                        except ValueError:
                            pass
            else:
                # VTK not generated yet — estimate from raw time directories
                if os.path.isdir(case_dir):
                    for d in os.listdir(case_dir):
                        try:
                            t = float(d)
                            if t > 0:
                                n_frames += 1
                        except ValueError:
                            pass

            fc_row = vbox.row()
            fc_row.enabled = False
            if n_frames == 0:
                fc_row.label(text="No time steps found yet — run solver first", icon='INFO')
            elif n_frames == 1:
                fc_row.alert = True
                fc_row.label(text="Only 1 frame found — increase Write Interval or End Time", icon='ERROR')
            else:
                fc_row.label(text=f"Will generate {n_frames} animation frames", icon='RENDER_ANIMATION')
        vbox.prop(props, "color_autoscale")

        # Color legend: always show the active range
        legend_col = vbox.column(align=True)
        legend_col.enabled = not props.color_autoscale
        row_min = legend_col.row()
        row_min.prop(props, "color_min", text="Range Min")
        row_max = legend_col.row()
        row_max.prop(props, "color_max", text="Range Max")
        if props.color_autoscale:
            vbox.label(text="Range auto-scaled to data", icon='INFO')
            
        vbox.operator("object.color_by_field", text="Color Boundary Mesh", icon='BRUSH_DATA')
        
        layout.separator()
        
        # --- Slice Plane Visualization ---
        sbox = layout.box()
        sbox.label(text="Internal Slice Plane:", icon='MESH_PLANE')
        row = sbox.row()
        row.prop(props, "slice_axis", expand=True)
        sbox.prop(props, "slice_offset")
        sbox.operator("object.visualize_slice", text="Extract Slice Plane", icon='MESH_GRID')
        
        layout.separator()
        
        # --- Existing buttons ---
        layout.operator("object.load_result", icon='IMPORT')
        layout.operator("object.launch_paraview", icon='OUTLINER_OB_FORCE_FIELD')
