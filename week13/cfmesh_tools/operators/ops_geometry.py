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

class OBJECT_OT_AddBoxRefinement(bpy.types.Operator):
    bl_idname = "object.add_box_refinement"
    bl_label = "Add Box Refinement"
    bl_description = "Add a new volumetric box refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        item = props.box_refinements.add()
        item.name = f"Box_{len(props.box_refinements)}"
        props.active_box_index = len(props.box_refinements) - 1
        return {'FINISHED'}

class OBJECT_OT_RemoveBoxRefinement(bpy.types.Operator):
    bl_idname = "object.remove_box_refinement"
    bl_label = "Remove Box Refinement"
    bl_description = "Remove the selected volumetric box refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        if len(props.box_refinements) > 0:
            props.box_refinements.remove(props.active_box_index)
            props.active_box_index = min(max(0, props.active_box_index - 1), len(props.box_refinements) - 1)
        return {'FINISHED'}

class OBJECT_OT_AddSurfaceRefinement(bpy.types.Operator):
    bl_idname = "object.add_surface_refinement"
    bl_label = "Add Surface Refinement"
    bl_description = "Add a new surface refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        item = props.surface_refinements.add()
        item.name = f"Surface_{len(props.surface_refinements)}"
        props.active_surface_index = len(props.surface_refinements) - 1
        return {'FINISHED'}

class OBJECT_OT_RemoveSurfaceRefinement(bpy.types.Operator):
    bl_idname = "object.remove_surface_refinement"
    bl_label = "Remove Surface Refinement"
    bl_description = "Remove the selected surface refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        if len(props.surface_refinements) > 0:
            props.surface_refinements.remove(props.active_surface_index)
            props.active_surface_index = min(max(0, props.active_surface_index - 1), len(props.surface_refinements) - 1)
        return {'FINISHED'}

class OBJECT_OT_AddCylinderRefinement(bpy.types.Operator):
    bl_idname = "object.add_cylinder_refinement"
    bl_label = "Add Cylinder Refinement"
    bl_description = "Add a new cylindrical refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        item = props.cylinder_refinements.add()
        item.name = f"Cylinder_{len(props.cylinder_refinements)}"
        props.active_cylinder_index = len(props.cylinder_refinements) - 1
        return {'FINISHED'}

class OBJECT_OT_RemoveCylinderRefinement(bpy.types.Operator):
    bl_idname = "object.remove_cylinder_refinement"
    bl_label = "Remove Cylinder Refinement"
    bl_description = "Remove the selected cylindrical refinement zone"
    
    def execute(self, context):
        props = context.scene.cfmesh_props
        if len(props.cylinder_refinements) > 0:
            props.cylinder_refinements.remove(props.active_cylinder_index)
            props.active_cylinder_index = min(max(0, props.active_cylinder_index - 1), len(props.cylinder_refinements) - 1)
        return {'FINISHED'}

class OBJECT_OT_AddWakePreset(bpy.types.Operator):
    bl_idname = "object.add_wake_preset"
    bl_label = "Add Auto Wake Box"
    bl_description = "Automatically generate a wake refinement box behind the active object based on inlet velocity direction"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        from mathutils import Vector
        props = context.scene.cfmesh_props
        obj = context.active_object
        
        bb = obj.bound_box
        xs = [v[0] for v in bb]; ys = [v[1] for v in bb]; zs = [v[2] for v in bb]
        min_b = Vector((min(xs), min(ys), min(zs)))
        max_b = Vector((max(xs), max(ys), max(zs)))
        
        vel = Vector(props.inlet_velocity)
        if vel.length == 0:
            vel = Vector((1.0, 0.0, 0.0))
        vel_norm = vel.normalized()
        
        obj_len_x = max_b.x - min_b.x
        obj_len_y = max_b.y - min_b.y
        obj_len_z = max_b.z - min_b.z
        
        item = props.box_refinements.add()
        item.name = f"{obj.name}_Wake"
        
        new_min = Vector(min_b)
        new_max = Vector(max_b)
        
        # wake_factor: how many object-lengths the wake extends DOWNSTREAM.
        # For a 30m cube with X-flow: wake box = 120m x-axis, 30m y/z.
        # This is physically correct — wakes are long, not wide.
        # A small lateral margin (10%) is added so the box slightly exceeds the object cross-section.
        wake_factor = 3.0
        lateral_margin = 0.10  # 10% of cross-dimension added each side

        if vel_norm.x > 0.5:
            new_max.x += obj_len_x * wake_factor
            new_min.y -= obj_len_y * lateral_margin
            new_max.y += obj_len_y * lateral_margin
            new_min.z -= obj_len_z * lateral_margin
            new_max.z += obj_len_z * lateral_margin
        elif vel_norm.x < -0.5:
            new_min.x -= obj_len_x * wake_factor
            new_min.y -= obj_len_y * lateral_margin
            new_max.y += obj_len_y * lateral_margin
            new_min.z -= obj_len_z * lateral_margin
            new_max.z += obj_len_z * lateral_margin
        elif vel_norm.y > 0.5:
            new_max.y += obj_len_y * wake_factor
            new_min.x -= obj_len_x * lateral_margin
            new_max.x += obj_len_x * lateral_margin
            new_min.z -= obj_len_z * lateral_margin
            new_max.z += obj_len_z * lateral_margin
        elif vel_norm.y < -0.5:
            new_min.y -= obj_len_y * wake_factor
            new_min.x -= obj_len_x * lateral_margin
            new_max.x += obj_len_x * lateral_margin
            new_min.z -= obj_len_z * lateral_margin
            new_max.z += obj_len_z * lateral_margin
        elif vel_norm.z > 0.5:
            new_max.z += obj_len_z * wake_factor
            new_min.x -= obj_len_x * lateral_margin
            new_max.x += obj_len_x * lateral_margin
            new_min.y -= obj_len_y * lateral_margin
            new_max.y += obj_len_y * lateral_margin
        else:
            new_min.z -= obj_len_z * wake_factor
            new_min.x -= obj_len_x * lateral_margin
            new_max.x += obj_len_x * lateral_margin
            new_min.y -= obj_len_y * lateral_margin
            new_max.y += obj_len_y * lateral_margin
            
        mat = obj.matrix_world
        world_min = mat @ new_min
        world_max = mat @ new_max
        
        item.min_bounds = (min(world_min.x, world_max.x), min(world_min.y, world_max.y), min(world_min.z, world_max.z))
        item.max_bounds = (max(world_min.x, world_max.x), max(world_min.y, world_max.y), max(world_min.z, world_max.z))
        item.cell_size = props.base_cell_size * 0.5
        
        props.active_box_index = len(props.box_refinements) - 1
        return {'FINISHED'}

class OBJECT_OT_AddCylinderWakePreset(bpy.types.Operator):
    bl_idname = "object.add_cylinder_wake_preset"
    bl_label = "Add Auto Wake Cylinder"
    bl_description = "Automatically generate a cylindrical wake refinement behind the active object based on inlet velocity direction"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        from mathutils import Vector
        props = context.scene.cfmesh_props
        obj = context.active_object
        
        bb = obj.bound_box
        xs = [v[0] for v in bb]; ys = [v[1] for v in bb]; zs = [v[2] for v in bb]
        min_b = Vector((min(xs), min(ys), min(zs)))
        max_b = Vector((max(xs), max(ys), max(zs)))
        
        vel = Vector(props.inlet_velocity)
        if vel.length == 0:
            vel = Vector((1.0, 0.0, 0.0))
        vel_norm = vel.normalized()
        
        obj_len_x = max_b.x - min_b.x
        obj_len_y = max_b.y - min_b.y
        obj_len_z = max_b.z - min_b.z
        
        # We find the center of the bounding box to start the cylinder
        center_x = (max_b.x + min_b.x) / 2.0
        center_y = (max_b.y + min_b.y) / 2.0
        center_z = (max_b.z + min_b.z) / 2.0
        
        center_pt = Vector((center_x, center_y, center_z))
        
        item = props.cylinder_refinements.add()
        item.name = f"{obj.name}_CylWake"
        
        wake_factor = 3.0
        p1 = Vector(center_pt)
        p2 = Vector(center_pt)
        radius = 0.5
        
        if abs(vel_norm.x) > 0.5:
            # Flow is mainly along X
            radius = max(obj_len_y, obj_len_z) / 2.0 * 1.5 # 1.5x wider than object
            if vel_norm.x > 0:
                p1.x = max_b.x
                p2.x = p1.x + (obj_len_x * wake_factor)
            else:
                p1.x = min_b.x
                p2.x = p1.x - (obj_len_x * wake_factor)
        elif abs(vel_norm.y) > 0.5:
            # Flow is mainly along Y
            radius = max(obj_len_x, obj_len_z) / 2.0 * 1.5
            if vel_norm.y > 0:
                p1.y = max_b.y
                p2.y = p1.y + (obj_len_y * wake_factor)
            else:
                p1.y = min_b.y
                p2.y = p1.y - (obj_len_y * wake_factor)
        else:
            # Flow is mainly along Z
            radius = max(obj_len_x, obj_len_y) / 2.0 * 1.5
            if vel_norm.z > 0:
                p1.z = max_b.z
                p2.z = p1.z + (obj_len_z * wake_factor)
            else:
                p1.z = min_b.z
                p2.z = p1.z - (obj_len_z * wake_factor)
                
        mat = obj.matrix_world
        world_p1 = mat @ p1
        world_p2 = mat @ p2
        
        item.p1 = (world_p1.x, world_p1.y, world_p1.z)
        item.p2 = (world_p2.x, world_p2.y, world_p2.z)
        
        # Scale radius by matrix scale roughly (assuming uniform scale for simplicity)
        avg_scale = (mat.to_scale().x + mat.to_scale().y + mat.to_scale().z) / 3.0
        item.radius = radius * avg_scale
        item.cell_size = props.base_cell_size * 0.5
        
        props.active_cylinder_index = len(props.cylinder_refinements) - 1
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
                
        except MemoryError:
            self.report({'ERROR'}, "Out of memory. The STL file might be too large for Blender to handle.")
            set_ui_error("Out of memory. File too large.")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Import failed. Ensure the file is a valid 3D ASCII or Binary STL. Detail: {str(e)[:50]}")
            set_ui_error(f"Import error: {str(e)[:50]}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
