import bpy

class CFMeshState:
    is_running = False
    is_error = False
    status_message = "Idle"
    last_output = ""
    thread = None

global_state = CFMeshState()

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
        min=0.000001
    )
    
    inlet_velocity: bpy.props.FloatVectorProperty(
        name="Inlet Velocity",
        description="Initial velocity at the inlet",
        default=(1.0, 0.0, 0.0),
        subtype='VELOCITY'
    )

    is_running: bpy.props.BoolProperty(
        name="Is Running",
        default=False
    )
