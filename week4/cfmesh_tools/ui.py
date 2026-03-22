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
        
        col = layout.column(align=True)
        col.prop(props, "base_cell_size")
        col.prop(props, "export_dir")
        
        layout.label(text="Boundary Layers:")
        box = layout.box()
        box.prop(props, "boundary_layers")
        if props.boundary_layers > 0:
            box.prop(props, "layer_thickness")

            
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
        layout.prop(props, "turbulence_model")
        
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
