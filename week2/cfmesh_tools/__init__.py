maxbl_info = {
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
            
            # Step 1: Run blockMesh (creates background hex mesh)
            self.report({'INFO'}, "Running blockMesh...")
            source_cmd = "source /opt/openfoam11/etc/bashrc"
            
            success, output = run_cfmesh.run_cfmesh_command(
                f"{source_cmd} && blockMesh", working_dir=case_dir
            )
            if not success:
                self.report({'ERROR'}, "blockMesh failed! Check terminal.")
                return {'FINISHED'}
            
            # Step 2: Run snappyHexMesh (refines around STL geometry)
            self.report({'INFO'}, "Running snappyHexMesh... This may take a moment.")
            success, output = run_cfmesh.run_cfmesh_command(
                f"{source_cmd} && snappyHexMesh -overwrite", working_dir=case_dir
            )
            
            if success:
                self.report({'INFO'}, "snappyHexMesh finished successfully!")
                
                # Convert the OpenFOAM mesh boundary to STL so Blender can import it
                conv_cmd = f"{source_cmd} && foamToSurface -latestTime constant/triSurface/result.stl"
                conv_success, _ = run_cfmesh.run_cfmesh_command(conv_cmd, working_dir=case_dir)
                
                # Try importing the exported surface back into Blender
                result_stl = os.path.join(case_dir, "constant", "triSurface", "result.stl")
                if os.path.isfile(result_stl):
                    bpy.ops.wm.stl_import(filepath=result_stl)
                    # Hide the original object to see the new one
                    obj.hide_set(True)
                    self.report({'INFO'}, "Successfully imported meshed result!")
                else:
                    self.report({'WARNING'}, f"Meshing finished but result STL not found at {result_stl}. Check terminal.")
            else:
                self.report({'ERROR'}, "snappyHexMesh failed! Check terminal for details.")
                
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
            box.prop(props, "final_layer_thickness")
            box.prop(props, "min_thickness")
            box.prop(props, "max_medial_ratio")
            
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
