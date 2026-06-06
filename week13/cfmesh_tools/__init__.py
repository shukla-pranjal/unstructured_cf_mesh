bl_info = {
    "name": "cfMesh Tools",
    "author": "FOSSEE",
    "version": (2, 5, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > cfMesh",
    "description": "Blender UI for interacting with OpenFOAM cfMesh. Refactored into modules.",
    "warning": "",
    "category": "Development",
}

import bpy

from .properties import CFMeshProperties, CFMeshPatch, CFMeshBoxRefinement, CFMeshSurfaceRefinement, CFMeshCylinderRefinement
from .operators import (
    OBJECT_OT_ImportSTL,
    OBJECT_OT_GenerateCFMesh,
    OBJECT_OT_RefreshPatches,
    OBJECT_OT_AddBoxRefinement,
    OBJECT_OT_RemoveBoxRefinement,
    OBJECT_OT_AddSurfaceRefinement,
    OBJECT_OT_RemoveSurfaceRefinement,
    OBJECT_OT_AddCylinderRefinement,
    OBJECT_OT_RemoveCylinderRefinement,
    OBJECT_OT_AddWakePreset,
    OBJECT_OT_AddCylinderWakePreset,
    OBJECT_OT_RunSolver,
    OBJECT_OT_LaunchParaView,
    OBJECT_OT_LoadResult,
    OBJECT_OT_RunCheckMesh,
    OBJECT_OT_ShowResiduals,
    OBJECT_OT_ColorByField,
    OBJECT_OT_VisualizeSlice,
    OBJECT_OT_OpenExportDir,
    OBJECT_OT_SetInspectBBox,
    OBJECT_OT_InspectRegion
)
from .ui import (
    VIEW3D_PT_CFMeshPanel,
    VIEW3D_PT_MeshSettings,
    VIEW3D_PT_SolverSettings,
    VIEW3D_PT_PostProcess
)

classes = (
    CFMeshPatch,
    CFMeshBoxRefinement,
    CFMeshSurfaceRefinement,
    CFMeshCylinderRefinement,
    CFMeshProperties,
    OBJECT_OT_ImportSTL,
    OBJECT_OT_GenerateCFMesh,
    OBJECT_OT_RefreshPatches,
    OBJECT_OT_AddBoxRefinement,
    OBJECT_OT_RemoveBoxRefinement,
    OBJECT_OT_AddSurfaceRefinement,
    OBJECT_OT_RemoveSurfaceRefinement,
    OBJECT_OT_AddCylinderRefinement,
    OBJECT_OT_RemoveCylinderRefinement,
    OBJECT_OT_AddWakePreset,
    OBJECT_OT_AddCylinderWakePreset,
    OBJECT_OT_RunSolver,
    OBJECT_OT_LaunchParaView,
    OBJECT_OT_LoadResult,
    OBJECT_OT_RunCheckMesh,
    OBJECT_OT_ShowResiduals,
    OBJECT_OT_ColorByField,
    OBJECT_OT_VisualizeSlice,
    OBJECT_OT_OpenExportDir,
    OBJECT_OT_SetInspectBBox,
    OBJECT_OT_InspectRegion,
    VIEW3D_PT_CFMeshPanel,
    VIEW3D_PT_MeshSettings,
    VIEW3D_PT_SolverSettings,
    VIEW3D_PT_PostProcess,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cfmesh_props = bpy.props.PointerProperty(type=CFMeshProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cfmesh_props

if __name__ == "__main__":
    register()
