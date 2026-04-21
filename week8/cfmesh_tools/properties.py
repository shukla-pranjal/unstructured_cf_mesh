import bpy
import math

class CFMeshPatch(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Patch Name")
    use_local_cell_size: bpy.props.BoolProperty(name="Override Size", default=False)
    local_cell_size: bpy.props.FloatProperty(name="Cell Size", default=0.1, min=0.001)
    boundary_layers: bpy.props.IntProperty(name="Boundary Layers", default=3, min=0)
    bc_type: bpy.props.EnumProperty(
        name="Type",
        items=[
            ('wall', 'Wall', 'Solid Boundary (noSlip)'),
            ('inlet', 'Inlet', 'Flow Inlet (fixedValue)'),
            ('outlet', 'Outlet', 'Flow Outlet (zeroGradient/fixedValue)'),
            ('symmetry', 'Symmetry', 'Symmetry Plane')
        ],
        default='wall'
    )

class CFMeshState:
    is_running = False
    is_error = False
    status_message = "Idle"
    last_output = ""
    thread = None
    live_log = []

global_state = CFMeshState()

import math

def update_calculator(self, context):
    U_x, U_y, U_z = self.inlet_velocity
    U_mag = math.sqrt(U_x**2 + U_y**2 + U_z**2)
    L = getattr(self, "characteristic_length", 1.0)
    nu = self.kinematic_viscosity
    I = getattr(self, "turbulent_intensity", 0.05)
    
    if nu > 0 and L > 0 and U_mag > 0:
        Re = (U_mag * L) / nu
        self.calc_reynolds_number = Re
        
        k = 1.5 * (U_mag * I)**2
        self.turb_k = k
        
        l = 0.07 * L
        C_mu = 0.09
        if l > 0:
            self.turb_epsilon = (C_mu**0.75) * (k**1.5) / l
            
            beta_star = 0.09
            self.turb_omega = self.turb_epsilon / (beta_star * k) if k > 0 else 0.0
            
            if self.turb_omega > 0:
                self.turb_nut = k / self.turb_omega
        
        y_plus = getattr(self, "target_yplus", 30.0)
        if y_plus > 0:
            C_f = 0.0576 * (Re**-0.2)
            u_star = U_mag * math.sqrt(C_f / 2.0) if C_f > 0 else 0
            if u_star > 0:
                self.calc_first_cell = (y_plus * nu) / u_star

def update_fluid_properties(self, context):
    if self.fluid_type == 'Air':
        self.kinematic_viscosity = 1.5e-5
    elif self.fluid_type == 'Water':
        self.kinematic_viscosity = 1.0e-6
    elif self.fluid_type == 'EngineOil':
        self.kinematic_viscosity = 1.0e-4
    elif self.fluid_type == 'Glycerin':
        self.kinematic_viscosity = 1.18e-3
    elif self.fluid_type == 'Custom':
        pass
    update_calculator(self, context)

def get_turbulence_models(self, context):
    if self.solver_type == 'icoFoam':
        return [('laminar', 'Laminar', 'Laminar flow (No turbulence model)')]
    else:
        return [
            ('kEpsilon', 'k-epsilon', 'Standard k-epsilon (RANS)'),
            ('kOmegaSST', 'k-omega SST', 'k-omega Shear Stress Transport (RANS)')
        ]

def update_solver_type(self, context):
    if self.solver_type == 'icoFoam':
        self.turbulence_model = 'laminar'
    elif self.turbulence_model not in ('kEpsilon', 'kOmegaSST'):
        self.turbulence_model = 'kEpsilon'

class CFMeshProperties(bpy.types.PropertyGroup):
    boundary_patches: bpy.props.CollectionProperty(type=CFMeshPatch)
    
    base_cell_size: bpy.props.FloatProperty(
        name="Base Cell Size",
        description="The target size of the background mesh cells",
        default=0.1,
        min=0.001,
        max=10.0
    )
    
    cpu_cores: bpy.props.IntProperty(
        name="CPU Cores",
        description="Number of processor cores for parallel meshing and solving",
        default=4,
        min=1,
        max=64
    )
    
    boundary_layers: bpy.props.IntProperty(
        name="Boundary Layers",
        description="Number of boundary layers to generate",
        default=3,
        min=0,
        max=20
    )
    
    layer_thickness: bpy.props.FloatProperty(
        name="Thickness Ratio",
        description="Thickness ratio of the boundary layers",
        default=1.2,
        min=1.0,
        max=3.0
    )
    
    export_dir: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to save the OpenFOAM case",
        default="/mnt/NewVolume/code/unstructured_cf_mesh/data/cfmesh_run",
        subtype='DIR_PATH'
    )


    solver_type: bpy.props.EnumProperty(
        name="Solver",
        items=[
            ('icoFoam', 'icoFoam (Laminar)', 'Incompressible laminar flow'),
            ('simpleFoam', 'simpleFoam (Steady)', 'Incompressible steady-state flow')
        ],
        default='icoFoam',
        update=update_solver_type
    )
    
    start_time: bpy.props.FloatProperty(
        name="Start Time",
        description="Simulation start time",
        default=0.0
    )
    
    end_time: bpy.props.FloatProperty(
        name="End Time",
        description="Simulation end time or max iterations",
        default=0.5
    )
    
    delta_t: bpy.props.FloatProperty(
        name="Delta T",
        description="Time step size",
        default=0.001,
        min=0.000001,
        precision=4
    )
    
    write_interval: bpy.props.IntProperty(
        name="Write Interval",
        description="Number of time steps between writes",
        default=20,
        min=1
    )
    
    show_time_controls: bpy.props.BoolProperty(
        name="Time and Interval",
        description="Show time and save controls",
        default=True
    )
    
    turbulence_model: bpy.props.EnumProperty(
        name="Turbulence Model",
        items=get_turbulence_models
    )
    
    fluid_type: bpy.props.EnumProperty(
        name="Fluid",
        items=[
            ('Air', 'Air (nu = 1.5e-5)', 'Standard Air'),
            ('Water', 'Water (nu = 1.0e-6)', 'Standard Water'),
            ('EngineOil', 'Engine Oil (nu = 1.0e-4)', 'Standard Engine Oil'),
            ('Glycerin', 'Glycerin (nu = 1.18e-3)', 'Standard Glycerin'),
            ('Custom', 'Custom...', 'User defined fluid property')
        ],
        default='Air',
        update=update_fluid_properties
    )
    
    kinematic_viscosity: bpy.props.FloatProperty(
        name="Viscosity (nu)",
        description="Kinematic viscosity of the fluid",
        default=0.000015,
        min=0.0000001,
        update=update_calculator
    )
    
    inlet_velocity: bpy.props.FloatVectorProperty(
        name="Inlet Velocity",
        description="Initial velocity at the inlet",
        default=(1.0, 0.0, 0.0),
        subtype='VELOCITY',
        update=update_calculator
    )
    
    characteristic_length: bpy.props.FloatProperty(
        name="Length (L)",
        description="Characteristic length of the geometry",
        default=1.0,
        min=0.001,
        update=update_calculator
    )
    
    turbulent_intensity: bpy.props.FloatProperty(
        name="Intensity (I)",
        description="Turbulent Intensity (e.g. 0.05 for 5%)",
        default=0.05,
        min=0.001,
        max=1.0,
        update=update_calculator
    )

    target_yplus: bpy.props.FloatProperty(
        name="Target Y+",
        description="Desired Y+ for first cell height",
        default=30.0,
        min=1.0,
        update=update_calculator
    )

    calc_reynolds_number: bpy.props.FloatProperty(
        name="Reynolds Number",
        default=0.0
    )
    
    calc_first_cell: bpy.props.FloatProperty(
        name="Est. 1st Cell Height",
        default=0.0
    )

    turb_k: bpy.props.FloatProperty(
        name="Turbulent KE (k)",
        description="Turbulent kinetic energy",
        default=0.1,
        min=0.000001
    )
    
    turb_epsilon: bpy.props.FloatProperty(
        name="Dissipation (epsilon)",
        description="Turbulent dissipation rate",
        default=0.1,
        min=0.000001
    )
    
    turb_omega: bpy.props.FloatProperty(
        name="Specific Dissipation (omega)",
        description="Specific dissipation rate",
        default=1.0,
        min=0.000001
    )

    turb_nut: bpy.props.FloatProperty(
        name="Turbulent Viscosity (nut)",
        description="Turbulent kinematic viscosity (initial guess)",
        default=0.0,
        min=0.0
    )

    is_running: bpy.props.BoolProperty(
        name="Is Running",
        default=False
    )

    progress_percent: bpy.props.FloatProperty(
        name="Progress",
        default=0.0,
        min=0.0,
        max=100.0
    )

    live_log_tail: bpy.props.StringProperty(
        name="Live Log",
        default=""
    )

    # --- Post-Processing: checkMesh results ---
    checkmesh_cells: bpy.props.IntProperty(name="Cells", default=0)
    checkmesh_faces: bpy.props.IntProperty(name="Faces", default=0)
    checkmesh_points: bpy.props.IntProperty(name="Points", default=0)
    checkmesh_non_ortho: bpy.props.FloatProperty(name="Max Non-Ortho", default=0.0)
    checkmesh_skewness: bpy.props.FloatProperty(name="Max Skewness", default=0.0)
    checkmesh_aspect_ratio: bpy.props.FloatProperty(name="Max Aspect Ratio", default=0.0)
    checkmesh_min_vol: bpy.props.FloatProperty(name="Min Volume", default=0.0)
    checkmesh_min_area: bpy.props.FloatProperty(name="Min Area", default=0.0)
    checkmesh_min_weight: bpy.props.FloatProperty(name="Min Face Weight", default=0.0)
    checkmesh_concave: bpy.props.IntProperty(name="Concave Faces", default=0)
    checkmesh_result: bpy.props.StringProperty(name="Mesh Quality", default="Not checked")
    checkmesh_write_fields: bpy.props.BoolProperty(
        name="Write Quality Fields",
        description="Write quality fields like nonOrthoAngle and skewness to the case for visualization (Uses more disk space)",
        default=True
    )
    
    # --- Post-Processing: Solver residuals ---
    residual_Ux: bpy.props.FloatProperty(name="Ux Residual", default=0.0)
    residual_Uy: bpy.props.FloatProperty(name="Uy Residual", default=0.0)
    residual_Uz: bpy.props.FloatProperty(name="Uz Residual", default=0.0)
    residual_p: bpy.props.FloatProperty(name="p Residual", default=0.0)
    residual_k: bpy.props.FloatProperty(name="k Residual", default=0.0)
    residual_omega: bpy.props.FloatProperty(name="omega Residual", default=0.0)
    solver_converged: bpy.props.StringProperty(name="Solver Status", default="Not run")
    solver_iterations: bpy.props.IntProperty(name="Iterations", default=0)

    # --- Post-Processing: Region Inspection ---
    inspect_use_bbox: bpy.props.BoolProperty(
        name="Inspect Sub-Region",
        description="Enable bounding-box region quality inspection",
        default=False
    )
    inspect_bbox_min: bpy.props.FloatVectorProperty(
        name="BBox Min",
        description="Lower corner of the inspection bounding box (XYZ)",
        default=(0.0, 0.0, 0.0),
        subtype='XYZ'
    )
    inspect_bbox_max: bpy.props.FloatVectorProperty(
        name="BBox Max",
        description="Upper corner of the inspection bounding box (XYZ)",
        default=(1.0, 1.0, 1.0),
        subtype='XYZ'
    )
    inspect_cells_count:  bpy.props.IntProperty(name="Cells in Region",  default=0)
    inspect_max_nonortho: bpy.props.FloatProperty(name="Max Non-Ortho",   default=0.0, precision=2)
    inspect_mean_nonortho:bpy.props.FloatProperty(name="Mean Non-Ortho",  default=0.0, precision=2)
    inspect_max_skewness: bpy.props.FloatProperty(name="Max Skewness",    default=0.0, precision=4)
    inspect_mean_skewness:bpy.props.FloatProperty(name="Mean Skewness",   default=0.0, precision=4)
    inspect_max_aspect:   bpy.props.FloatProperty(name="Max Aspect Ratio",default=0.0, precision=2)

    # --- Post-Processing: Color visualization ---
    color_field: bpy.props.EnumProperty(
        name="Color Field",
        items=[
            ('p', 'Pressure (p)', 'Color mesh by pressure field'),
            ('U_mag', 'Velocity Magnitude', 'Color mesh by velocity magnitude'),
            ('nonOrthoAngle', 'Non-Orthogonality', 'Color mesh by non-orthogonal angle (Run checkMesh with fields first)'),
            ('skewness', 'Skewness', 'Color mesh by cell skewness (Run checkMesh with fields first)')
        ],
        default='p'
    )
    
    animate_results: bpy.props.BoolProperty(
        name="Animate Results",
        description="Load all time steps and map to Blender animation frames",
        default=False
    )
    
    color_autoscale: bpy.props.BoolProperty(
        name="Auto-Scale Colors",
        description="Automatically scale the colormap to the min/max of the current view",
        default=True
    )
    
    color_min: bpy.props.FloatProperty(
        name="Min Value",
        description="Minimum value for the colormap (Blue)",
        default=0.0
    )
    
    color_max: bpy.props.FloatProperty(
        name="Max Value",
        description="Maximum value for the colormap (Red)",
        default=10.0
    )

    # --- Post-Processing: Slice Plane ---
    slice_axis: bpy.props.EnumProperty(
        name="Slice Axis",
        description="Axis normal to the slice plane",
        items=[
            ('X', 'X-Axis', 'Plane normal to X-axis (YZ plane)'),
            ('Y', 'Y-Axis', 'Plane normal to Y-axis (XZ plane)'),
            ('Z', 'Z-Axis', 'Plane normal to Z-axis (XY plane)')
        ],
        default='X'
    )
    
    slice_offset: bpy.props.FloatProperty(
        name="Offset",
        description="Position of the slice plane along the chosen axis",
        default=0.0
    )

    # ------------------------------------------------------------------ #
    # Feature 2 — Trailing Edge & Mesh Quality                            #
    # ------------------------------------------------------------------ #
    trailing_edge_enabled: bpy.props.BoolProperty(
        name="Trailing Edge Refinement",
        description="Refine cells near a named trailing-edge patch in cfMesh",
        default=False
    )
    trailing_edge_patch_name: bpy.props.StringProperty(
        name="Edge Patch Name",
        description="Name of the trailing-edge surface patch in the STL",
        default="trailingEdge"
    )
    trailing_edge_cell_size: bpy.props.FloatProperty(
        name="Edge Cell Size",
        description="Cell size to use near the trailing-edge patch (smaller = finer)",
        default=0.01,
        min=0.0001,
        precision=4
    )
    improve_mesh_quality: bpy.props.BoolProperty(
        name="Improve Mesh Quality",
        description="Run cfMesh post-processing to improve overall mesh quality",
        default=True
    )
    layer_optimise: bpy.props.BoolProperty(
        name="Optimise Layers",
        description="Run layer optimisation pass after boundary layer insertion",
        default=True
    )
    layer_max_iter: bpy.props.IntProperty(
        name="Layer Max Iterations",
        description="Maximum iterations for the layer smoothing/optimisation pass",
        default=5,
        min=1,
        max=20
    )
