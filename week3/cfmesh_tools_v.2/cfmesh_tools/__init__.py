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
        default="/tmp/cfmesh_run",
        subtype='DIR_PATH'
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
            
            # Export the mesh (Pre-requisite for cfMesh)
            stl_path = os.path.join(case_dir, "mesh.stl")
            os.makedirs(case_dir, exist_ok=True)
            
            # Select only the active object to export
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            
            # Export STL to the case directory
            bpy.ops.wm.stl_export(
                filepath=stl_path,
                export_selected_objects=True,
                global_scale=1.0
            )
            self.report({'INFO'}, f"Exported {obj.name} to {stl_path}")
            
            # 1. Generate the OpenFOAM Structure using the UI values
            success = run_cfmesh.create_case_structure(
                base_dir=case_dir,
                cell_size=props.base_cell_size,
                boundary_layers=props.boundary_layers,
                thickness_ratio=props.layer_thickness,
                stl_name="mesh.stl"
            )
            
            if success:
                self.report({'INFO'}, "Successfully generated OpenFOAM dictionaries!")
                print(f"CFMesh Generation Triggered. Case saved in: {case_dir}")
                
                # Run cfMesh
                self.report({'INFO'}, "Running cfMesh... This may take a moment.")
                # We need to run inside the case directory
                source_cmd = ". /opt/openfoam11/etc/bashrc"
                run_cmd = f"{source_cmd} && cartesianMesh"
                success, output = run_cfmesh.run_cfmesh_command(run_cmd, working_dir=case_dir)
                
                if success:
                    self.report({'INFO'}, "cfMesh finished successfully!")
                    
                    # Now import it back
                    # Since OpenFOAM writes to constant/polyMesh, we need to convert it to something Blender can read like VTK or STL
                    # For now, OpenFOAM has a foamToSurface command which is fast
                    conv_cmd = f"{source_cmd} && foamToSurface constant/triSurface/surface.stl"
                    run_cfmesh.run_cfmesh_command(conv_cmd, working_dir=case_dir)
                    
                    # Try importing the exported surface back into Blender
                    result_stl = os.path.join(case_dir, "constant", "triSurface", "surface.stl")
                    if os.path.exists(result_stl):
                        bpy.ops.wm.stl_import(filepath=result_stl)
                        # Hide the original object to see the new one
                        obj.hide_set(True)
                        self.report({'INFO'}, "Successfully imported meshed result.")
                    else:
                        self.report({'WARNING'}, "Meshing finished but output STL not found.")
                else:
                    self.report({'ERROR'}, "cfMesh failed! Check terminal for details.")
            else:
                self.report({'ERROR'}, "Failed to generate OpenFOAM structure.")
                
        except Exception as e:
            self.report({'ERROR'}, f"Python Error: {str(e)}")
            print(f"Error during execution: {e}")
            
        return {'FINISHED'}

# 3. Define the UI Panel
class VIEW3D_PT_CFMeshPanel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "cfMesh"  # Name of the tab in the N-Panel
    bl_label = "OpenFOAM Meshing"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.cfmesh_props
        
        # Mesh settings
        layout.label(text="Global Mesh Settings:")
        box = layout.box()
        box.prop(props, "base_cell_size")
        box.prop(props, "export_dir")
        
        # Boundary layer settings
        layout.label(text="Boundary Layers:")
        box = layout.box()
        box.prop(props, "boundary_layers")
        if props.boundary_layers > 0:
            box.prop(props, "layer_thickness")
            
        layout.separator()
        
        # Action button
        row = layout.row()
        row.scale_y = 1.5 # Make the button big
        if context.active_object and context.active_object.type == 'MESH':
            row.operator("object.generate_cfmesh", icon='MESH_CUBE')
        else:
            row.label(text="Select a Mesh Object first!", icon='ERROR')

# 4. Registration
classes = (
    CFMeshProperties,
    OBJECT_OT_GenerateCFMesh,
    VIEW3D_PT_CFMeshPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Register the properties to the Scene
    bpy.types.Scene.cfmesh_props = bpy.props.PointerProperty(type=CFMeshProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cfmesh_props

if __name__ == "__main__":
    register()
