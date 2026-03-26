import sys
import os
import bpy

sys.path.append(os.path.abspath('.'))

try:
    import cfmesh_tools
    print("Successfully imported cfmesh_tools")
except Exception as e:
    import traceback
    traceback.print_exc()
