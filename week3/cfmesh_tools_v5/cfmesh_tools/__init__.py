bl_info = {
    "name": "cfMesh Tools",
    "author": "FOSSEE",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > cfMesh",
    "description": "Blender UI for interacting with OpenFOAM cfMesh.",
    "warning": "",
    "category": "Development",
}

import bpy
import os
import threading
import time

# --- Async Global State ---
class CFMeshState:
    is_running = False
    status_message = "Idle"
    last_output = ""
    thread = None

global_state = CFMeshState()

# 1. Define the Properties
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

    final_layer_thickness: bpy.props.FloatProperty(
        name="Final Layer Thickness",
        description="Thickness of the final (thickest) layer relative to local cell size",
        default=0.3,
        min=0.01,
        max=1.0
    )

    min_thickness: bpy.props.FloatProperty(
        name="Min Thickness",
        description="Minimum overall thickness of the layer stack",
        default=0.1,
        min=0.001,
        max=1.0
    )

    max_medial_ratio: bpy.props.FloatProperty(
        name="Max Medial Ratio",
        description="Maximum ratio of layer thickness to medial axis distance",
        default=0.3,
        min=0.01,
        max=1.0
    )

    # --- Solver Properties ---
    solver_type: bpy.props.EnumProperty(
        name="Solver",
        items=[
            ('icoFoam', 'icoFoam (Laminar)', 'Incompressible laminar flow'),
            ('simpleFoam', 'simpleFoam (Steady)', 'Incompressible steady-state flow')
        ],
        default='icoFoam'
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

# 2. Define the Operator (The Action when a button is clicked)
class OBJECT_OT_GenerateCFMesh(bpy.types.Operator):
    bl_idname = "object.generate_cfmesh"
    bl_label = "Generate cfMesh"
    bl_description = "Exports STL and generates meshDict locally"
    
    @classmethod
    def poll(cls, context):
        # Only allow clicking if an object is selected and it's a Mesh
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        props = context.scene.cfmesh_props
        obj = context.active_object
        
        # Ensure we are in Object Mode to avoid context errors during operators
        if context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Real Execution Link
        import sys
        
        # Ensure Blender can find our local script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.append(script_dir)
            
        try:
            import run_cfmesh
            import importlib
            importlib.reload(run_cfmesh) # Ensure we get the latest saved version
            
            # Use the directory specified in the UI
            case_dir = bpy.path.abspath(props.export_dir)
            
            # Create the case structure FIRST so constant/triSurface exists
            success = run_cfmesh.create_case_structure(
                base_dir=case_dir,
                cell_size=props.base_cell_size,
                boundary_layers=props.boundary_layers,
                thickness_ratio=props.layer_thickness,
                stl_name="mesh.stl",
                final_layer_thickness=props.final_layer_thickness,
                min_thickness=props.min_thickness,
                max_medial_ratio=props.max_medial_ratio
            )
            
            if not success:
                self.report({'ERROR'}, "Failed to generate OpenFOAM structure.")
                return {'CANCELLED'}

            # Export the mesh directly to constant/triSurface
            tri_surface_dir = os.path.join(case_dir, "constant", "triSurface")
            os.makedirs(tri_surface_dir, exist_ok=True)
            stl_path = os.path.join(tri_surface_dir, "mesh.stl")
            
            # Select only the active object to export
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Apply all transforms (location, rotation, scale)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            
            # Triangulate the mesh to ensure cfMesh compatibility
            bpy.ops.object.modifier_add(type='TRIANGULATE')
            bpy.ops.object.modifier_apply(modifier=obj.modifiers[-1].name)
            
            # Export STL to the case directory
            bpy.ops.wm.stl_export(
                filepath=stl_path,
                export_selected_objects=True,
                global_scale=1.0
            )
            self.report({'INFO'}, f"Exported {obj.name} to {stl_path}")
            
            # Since we generated the OpenFOAM structure above, we can just run it now
            self.report({'INFO'}, "Successfully generated OpenFOAM dictionaries!")
            print(f"Mesh Generation Triggered. Case saved in: {case_dir}")
            
            # Step 1: Run blockMesh and snappyHexMesh in sequence via async thread
            source_cmd = "source /opt/openfoam11/etc/bashrc"
            full_cmd = f"{source_cmd} && blockMesh && snappyHexMesh -overwrite && foamToSurface -latestTime constant/triSurface/result.stl"
            
            run_command_async(full_cmd, case_dir)
            self.report({'INFO'}, "Meshing started in background. Check 'Status' above.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}

# --- Async Helper Functions ---

def run_command_async(command, working_dir, report_callback=None):
    """
    Runs a terminal command in a background thread.
    """
    def task():
        global_state.is_running = True
        global_state.status_message = "Processing..."
        
        import run_cfmesh
        success, output = run_cfmesh.run_cfmesh_command(command, working_dir)
        
        global_state.last_output = output
        if success:
            global_state.status_message = "Finished Successfully"
        else:
            global_state.status_message = "Error: Check Terminal"
        
        global_state.is_running = False

    global_state.thread = threading.Thread(target=task)
    global_state.thread.start()
    
    # Start the Blender timer to refresh the UI
    bpy.app.timers.register(check_async_status)

def check_async_status():
    """
    A timer function that runs periodically to check the thread status.
    Returns the interval in seconds for the next call.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw() # Force UI refresh
            
    if global_state.is_running:
        return 0.5 # Check again in 0.5s
    return None # Stop the timer

# --- New Operators for Week 3 ---

class OBJECT_OT_RunSolver(bpy.types.Operator):
    bl_idname = "object.run_solver"
    bl_label = "Run Simulation"
    bl_description = "Starts the OpenFOAM solver (icoFoam/simpleFoam)"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        source_cmd = "source /opt/openfoam11/etc/bashrc"
        
        import run_cfmesh
        # 1. Update fields based on UI
        run_cfmesh.generate_fields(
            case_dir, 
            props.solver_type, 
            props.kinematic_viscosity, 
            list(props.inlet_velocity)
        )
        
        # 2. Run solver asynchronously
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
        
        import run_cfmesh
        run_cfmesh.launch_paraview(case_dir)
        
        return {'FINISHED'}

class OBJECT_OT_LoadResult(bpy.types.Operator):
    bl_idname = "object.load_result"
    bl_label = "Load Meshed Result"
    bl_description = "Imports the result.stl into the scene"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        case_dir = bpy.path.abspath(props.export_dir)
        result_stl = os.path.join(case_dir, "constant", "triSurface", "result.stl")
        
        if os.path.isfile(result_stl):
            bpy.ops.wm.stl_import(filepath=result_stl)
            self.report({'INFO'}, "Successfully imported meshed result!")
        else:
            self.report({'ERROR'}, f"Result STL not found at {result_stl}. Did you run meshing?")
            
        return {'FINISHED'}

# 3. Define the UI Panels
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
            box.label(text="Blender is free to use while meshing/solving.")
            return
        
        if global_state.status_message != "Idle":
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
        
        col = layout.column(align=True)
        col.prop(props, "base_cell_size")
        col.prop(props, "export_dir")
        
        layout.label(text="Boundary Layers:")
        box = layout.box()
        box.prop(props, "boundary_layers")
        if props.boundary_layers > 0:
            box.prop(props, "layer_thickness")
            box.prop(props, "final_layer_thickness")
            box.prop(props, "min_thickness")
            box.prop(props, "max_medial_ratio")
            
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
        
        box = layout.box()
        box.label(text="Physical Properties:")
        box.prop(props, "kinematic_viscosity")
        box.prop(props, "inlet_velocity")
        
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
        layout.operator("object.load_result", icon='IMPORT')
        layout.operator("object.launch_paraview", icon='OUTLINER_OB_FORCE_FIELD')

# 4. Registration
def register():
    bpy.utils.register_class(CFMeshProperties)
    bpy.utils.register_class(OBJECT_OT_GenerateCFMesh)
    bpy.utils.register_class(OBJECT_OT_RunSolver)
    bpy.utils.register_class(OBJECT_OT_LaunchParaView)
    bpy.utils.register_class(OBJECT_OT_LoadResult)
    bpy.utils.register_class(VIEW3D_PT_CFMeshPanel)
    bpy.utils.register_class(VIEW3D_PT_MeshSettings)
    bpy.utils.register_class(VIEW3D_PT_SolverSettings)
    bpy.utils.register_class(VIEW3D_PT_PostProcess)
    
    bpy.types.Scene.cfmesh_props = bpy.props.PointerProperty(type=CFMeshProperties)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_PostProcess)
    bpy.utils.unregister_class(VIEW3D_PT_SolverSettings)
    bpy.utils.unregister_class(VIEW3D_PT_MeshSettings)
    bpy.utils.unregister_class(VIEW3D_PT_CFMeshPanel)
    bpy.utils.unregister_class(OBJECT_OT_LoadResult)
    bpy.utils.unregister_class(OBJECT_OT_LaunchParaView)
    bpy.utils.unregister_class(OBJECT_OT_RunSolver)
    bpy.utils.unregister_class(OBJECT_OT_GenerateCFMesh)
    bpy.utils.unregister_class(CFMeshProperties)
    del bpy.types.Scene.cfmesh_props

if __name__ == "__main__":
    register()
