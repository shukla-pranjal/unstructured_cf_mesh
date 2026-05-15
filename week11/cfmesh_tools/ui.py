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

        # --- Cell Count Estimator ---
        if props.est_cell_count > 0:
            est_row = layout.row()
            est_row.enabled = False
            if props.est_cell_count > 2_000_000:
                est_row.alert = True
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}  ⚠ Very large!", icon='ERROR')
            elif props.est_cell_count > 500_000:
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}  (Large)", icon='INFO')
            else:
                est_row.label(text=f"Est. Cells: ~{props.est_cell_count:,}", icon='CHECKMARK')
        
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
                col.label(text="Steady-State (Time/DeltaT disabled)", icon='INFO')
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
                col.prop(props, "end_time", text="End Time")
                col.prop(props, "delta_t")
                col.prop(props, "write_interval")
                # icoFoam uses adjustableRunTime — writeInterval is physical seconds
                # actual writeInterval = end_time / write_interval
                # frames = write_interval (one per interval) + 1 (for t=0 initial condition)
                n_est = props.write_interval + 1

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
            co_row = co_box.row()
            co_row.enabled = False
            co_row.prop(props, "courant_number", text="Courant No. (Co)")
            if props.courant_number >= 1.0:
                co_box.alert = True
                co_box.label(text="⚠ Co ≥ 1: Solver WILL diverge! Reduce Δt.", icon='ERROR')
                sug = co_box.row()
                sug.enabled = False
                sug.prop(props, "suggested_dt", text="Safe Δt")
            elif props.courant_number > 0.5:
                co_box.label(text="Co > 0.5: Borderline. Consider reducing Δt.", icon='INFO')
                sug = co_box.row()
                sug.enabled = False
                sug.prop(props, "suggested_dt", text="Safe Δt")
            else:
                co_box.label(text="Co < 0.5: Time step is stable ✓", icon='CHECKMARK')

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
