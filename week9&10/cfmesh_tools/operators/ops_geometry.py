import bpy
import os
from .ops_utils import run_command_async, set_ui_error, clear_ui_status
from ..properties import global_state
from .. import utils_mesh

class OBJECT_OT_RefreshPatches(bpy.types.Operator):
    bl_idname = "object.refresh_patches"
    bl_label = "Refresh Patches"
    bl_description = "Loads all selected objects as independent mesh patches"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        props.boundary_patches.clear()
        
        objects = context.selected_objects
        if not objects:
            self.report({'WARNING'}, "No objects selected!")
            global_state.status_message = "No objects selected."
            return {'FINISHED'}
            
        for obj in objects:
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
                patch = props.boundary_patches.add()
                patch.name = obj.name
                
        self.report({'INFO'}, f"Loaded {len(props.boundary_patches)} patches.")
        global_state.status_message = f"Loaded {len(props.boundary_patches)} patches."
        return {'FINISHED'}

class OBJECT_OT_ImportSTL(bpy.types.Operator):
    bl_idname = "object.import_stl_geometry"
    bl_label = "Import STL Geometry"
    bl_description = "Import an external STL file as the geometry to mesh"
    
    filepath: bpy.props.StringProperty(
        subtype='FILE_PATH',
        default="",
    )
    
    filter_glob: bpy.props.StringProperty(
        default="*.stl;*.STL",
        options={'HIDDEN'},
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        filepath = self.filepath
        
        # --- Validation: File selected ---
        if not filepath:
            self.report({'ERROR'}, "No file selected.")
            set_ui_error("No STL file selected.")
            return {'CANCELLED'}
        
        # --- Validation: File exists ---
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            set_ui_error(f"File not found: {os.path.basename(filepath)}")
            return {'CANCELLED'}
        
        # --- Validation: File extension ---
        if not filepath.lower().endswith('.stl'):
            self.report({'ERROR'}, "Only .stl files are supported.")
            set_ui_error("Invalid file type. Only .stl files supported.")
            return {'CANCELLED'}
        
        # --- Validation: File not empty ---
        if os.path.getsize(filepath) == 0:
            self.report({'ERROR'}, "STL file is empty (0 bytes).")
            set_ui_error("STL file is empty.")
            return {'CANCELLED'}
        
        clear_ui_status()
        
        try:
            # Remember existing objects to identify the new one
            existing_objects = set(bpy.data.objects.keys())
            
            bpy.ops.wm.stl_import(filepath=filepath)
            
            # Find the newly imported object(s)
            new_objects = [obj for name, obj in bpy.data.objects.items() 
                         if name not in existing_objects and obj.type == 'MESH']
            
            if new_objects:
                # Select and set active the imported geometry
                bpy.ops.object.select_all(action='DESELECT')
                for obj in new_objects:
                    obj.select_set(True)
                context.view_layer.objects.active = new_objects[0]
                
                # Report stats
                total_verts = sum(len(o.data.vertices) for o in new_objects)
                total_faces = sum(len(o.data.polygons) for o in new_objects)
                name = new_objects[0].name
                
                self.report({'INFO'}, 
                    f"Imported '{name}' — {total_verts:,} vertices, {total_faces:,} faces. Ready for meshing.")
                global_state.status_message = f"Imported: {name} ({total_faces:,} faces)"
            else:
                self.report({'WARNING'}, "Import completed but no mesh objects were created.")
                set_ui_error("Import failed — no mesh objects created.")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            set_ui_error(f"Import error: {str(e)[:50]}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
