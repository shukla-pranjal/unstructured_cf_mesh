# Progress Tracking: Solver Orchestration & Async Handling

## 📂 Project Architecture (Week 3 Update)
The addon is evolving into a full simulation toolkit:
- **`__init__.py`**: (Updated) Now includes logic for solver selection and physics parameter input.
- **`run_cfmesh.py`**: (Updated) Handles `blockMesh`, `snappyHexMesh`, and now `icoFoam`/`simpleFoam` solvers.

## 📦 Release Versioning (ZIP Archives)
- **v5 (Upcoming)**:
    - **Solver Support**: Choose between `icoFoam` (laminar) and `simpleFoam` (steady-state).
    - **Physical Bounds**: Define kinematic viscosity and boundary velocities directly in Blender.
    - **Async Progress**: Non-blocking solver execution with status reports.
    - **ParaView Integration**: One-click results visualization.

## 🏗️ The Week 3 Foundation (Simulations)
- **The Solver Pivot**: Moving beyond just meshing to running full OpenFOAM simulations within Blender.
- **Background Computing**: Using Python threading to keep Blender responsive during long mesh/solve cycles.
- **Result Automation**: Automated creation of OpenFOAM field files (`0/U`, `0/p`) based on Blender parameters.

## ✅ Current Milestone: Week 3
- [ ] Implement `simpleFoam` orchestration.
- [ ] Add `Async Threading` for background execution.
- [ ] Create `Quick-ParaView` launch button.

## 🚀 Upcoming Roadmap (Week 4+)
- **Dynamic Mesh**: Support for moving boundaries.
- **Post-processing in Blender**: Basic scalar field visualization (pseudo-color) directly on meshes.
- **Advanced Turbulence**: Support for RANS models (k-epsilon, k-omega).



Mistakes i did
* _init_.py:  I named the registration dictionary maxbl_info instead of the expected bl_info. Blender requires it to be exactly bl_info in order to recognize the script as a valid add-on, which is why it wasn't showing up.

I've fixed that typo in the script and re-package


*

Error faced:
    import run_cfmesh
ModuleNotFoundError: No module named 'run_cfmesh'
23:38.997  bpy.rna          | ERROR Python script error in OBJECT_OT_run_solver.execute
23:38.997  operator         | ERROR Python: Traceback (most recent call last):
                            |   File "/home/pranjal/.config/blender/5.1/scripts/addons/cfmesh_tools/__init__.py", line 258, in execute
                            |     import run_cfmesh
                            | ModuleNotFoundError: No module named 'run_cfmesh'


oing a standard import run_cfmesh doesn't work unless Blender's internal path is perfectly aligned.

I've changed all the import statements to relative imports (from . import run_cfmesh) which is the correct and robust way to handle multi-file Blender addons.


* The user reported that snappyHexMesh was not cutting the mesh out properly. This is because locationInMesh was hardcoded to (0, 0, 0) which is INSIDE the simulated object (meshing the hollow inside instead of the wind tunnel). Also, Suzanne the Monkey is not watertight which breaks snappyHexMesh. I am modifying locationInMesh to be outside the object.

* hat OpenFOAM 11 uses a unified foamRun solver, and determining steady vs transient relies on ddtScheme

*lvers into a single unified application called foamRun. Because we asked for simpleFoam, it crashed and told us its new name. Furthermore, running a steady-state simulation in OF-11 now strictly requires a SIMPLE block in your fvSolution dictionary and steadyState in fvSchemes instead of the default transient ones.

I have completely upgraded our python script (run_cfmesh.py) to properly support OpenFOAM 11's new modular architecture!

When you select simpleFoam in the UI, the addon now intelligently runs the modern foamRun -solver incompressibleFluid command for you.
It dynamically builds the correct SIMPLE / steadyState math dictionaries so OpenFOAM doesn't crash!