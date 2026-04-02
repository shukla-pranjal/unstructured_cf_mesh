bl_info = {
    "name": "cfMesh Tools",
    "author": "FOSSEE",
    "version": (1, 6, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > cfMesh",
    "description": "Blender UI for interacting with OpenFOAM cfMesh. Refactored into modules.",
    "warning": "",
    "category": "Development",
}

import bpy

from .properties import CFMeshProperties
from .operators import (
    OBJECT_OT_ImportSTL,
    OBJECT_OT_GenerateCFMesh,
    OBJECT_OT_RunSolver,
    OBJECT_OT_LaunchParaView,
    OBJECT_OT_LoadResult
)
from .ui import (
    VIEW3D_PT_CFMeshPanel,
    VIEW3D_PT_MeshSettings,
    VIEW3D_PT_SolverSettings,
    VIEW3D_PT_PostProcess
)

classes = (
    CFMeshProperties,
    OBJECT_OT_ImportSTL,
    OBJECT_OT_GenerateCFMesh,
    OBJECT_OT_RunSolver,
    OBJECT_OT_LaunchParaView,
    OBJECT_OT_LoadResult,
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
