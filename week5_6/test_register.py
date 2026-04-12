import sys
import os
import bpy

sys.path.append(os.path.abspath('.'))

try:
    import cfmesh_tools
    cfmesh_tools.register()
    print("Successfully registered cfmesh_tools")
except Exception as e:
    import traceback
    traceback.print_exc()

import sys
sys.exit(0)
