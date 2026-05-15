from .ops_geometry import OBJECT_OT_ImportSTL, OBJECT_OT_RefreshPatches
from .ops_meshing import OBJECT_OT_GenerateCFMesh
from .ops_solver import OBJECT_OT_RunSolver
from .ops_postprocess import (
    OBJECT_OT_LaunchParaView,
    OBJECT_OT_LoadResult,
    OBJECT_OT_OpenExportDir
)
from .ops_analyze import (
    OBJECT_OT_RunCheckMesh,
    OBJECT_OT_ShowResiduals
)
from .ops_visualize_boundary import OBJECT_OT_ColorByField
from .ops_visualize_slice import OBJECT_OT_VisualizeSlice
from .ops_inspect import (
    OBJECT_OT_SetInspectBBox,
    OBJECT_OT_InspectRegion
)
