import bpy

class CFMeshState:
    is_running = False
    is_error = False
    status_message = "Idle"
    last_output = ""
    thread = None

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

class CFMeshProperties(bpy.types.PropertyGroup):
    base_cell_size: bpy.props.FloatProperty(
        name="Base Cell Size",
        description="The target size of the background mesh cells",
        default=0.1,
        min=0.001,
        max=10.0
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
        default='icoFoam'
    )
    
    turbulence_model: bpy.props.EnumProperty(
        name="Turbulence Model",
        items=[
            ('laminar', 'Laminar', 'Laminar flow (No turbulence model)'),
            ('kEpsilon', 'k-epsilon', 'Standard k-epsilon (RANS)'),
            ('kOmegaSST', 'k-omega SST', 'k-omega Shear Stress Transport (RANS)')
        ],
        default='laminar'
    )
    
    kinematic_viscosity: bpy.props.FloatProperty(
        name="Viscosity (nu)",
        description="Kinematic viscosity of the fluid",
        default=0.01,
        min=0.000001,
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

    # --- Post-Processing: checkMesh results ---
    checkmesh_cells: bpy.props.IntProperty(name="Cells", default=0)
    checkmesh_faces: bpy.props.IntProperty(name="Faces", default=0)
    checkmesh_points: bpy.props.IntProperty(name="Points", default=0)
    checkmesh_non_ortho: bpy.props.FloatProperty(name="Max Non-Ortho", default=0.0)
    checkmesh_skewness: bpy.props.FloatProperty(name="Max Skewness", default=0.0)
    checkmesh_result: bpy.props.StringProperty(name="Mesh Quality", default="Not checked")
    
    # --- Post-Processing: Solver residuals ---
    residual_Ux: bpy.props.FloatProperty(name="Ux Residual", default=0.0)
    residual_Uy: bpy.props.FloatProperty(name="Uy Residual", default=0.0)
    residual_Uz: bpy.props.FloatProperty(name="Uz Residual", default=0.0)
    residual_p: bpy.props.FloatProperty(name="p Residual", default=0.0)
    residual_k: bpy.props.FloatProperty(name="k Residual", default=0.0)
    residual_omega: bpy.props.FloatProperty(name="omega Residual", default=0.0)
    solver_converged: bpy.props.StringProperty(name="Solver Status", default="Not run")
    solver_iterations: bpy.props.IntProperty(name="Iterations", default=0)

    # --- Post-Processing: Color visualization ---
    color_field: bpy.props.EnumProperty(
        name="Color Field",
        items=[
            ('p', 'Pressure (p)', 'Color mesh by pressure field'),
            ('U_mag', 'Velocity Magnitude', 'Color mesh by velocity magnitude'),
        ],
        default='p'
    )
