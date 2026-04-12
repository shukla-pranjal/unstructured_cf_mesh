# Week 5 — Error Log & Debugging Track

## Error 1: Missing `PIMPLE` Dictionary in `fvSolution`
**Error:**
```
FOAM FATAL IO ERROR: keyword PIMPLE is undefined in dictionary "system/fvSolution"
```
**Cause:** The `fvSolution` template only had a `PISO` block. When `simpleFoam` (which internally uses `PIMPLE`) was selected, OpenFOAM couldn't find the required solver configuration.

**Fix:** Added `PIMPLE`, `SIMPLE`, and `relaxationFactors` blocks to the `FV_SOLUTION_TEMPLATE` in `utils_mesh.py`. Also added turbulence field solvers (`PBiCGStab`) for `k`, `epsilon`, and `omega`.

---

## Error 2: `turbulenceProperties` → `momentumTransport` (OF11)
**Error:** OpenFOAM 11 silently fell back to laminar mode — turbulence fields (`k`, `omega`) were never computed by the solver despite being present in `0/`.

**Cause:** OpenFOAM 11 renamed `constant/turbulenceProperties` to `constant/momentumTransport`. The old filename was silently ignored.

**Fix:** Renamed all references from `turbulenceProperties` to `momentumTransport` in `utils_mesh.py`.

---

## Error 3: Missing `wallDist` in `fvSchemes`
**Error:**
```
FOAM FATAL IO ERROR: keyword wallDist is undefined in dictionary "system/fvSchemes"
```
**Cause:** The `kOmegaSST` model requires wall-distance calculations. OpenFOAM needs the `wallDist` method specified in `fvSchemes`.

**Fix:** Added `wallDist { method meshWave; }` to the `FV_SCHEMES_TEMPLATE`.

---

## Error 4: Wall Function on Non-Wall Patch
**Error:**
```
FOAM FATAL ERROR: Invalid wall function specification
Patch type for patch allBoundary must be wall. Current patch type is patch.
```
**Cause:** Wall functions (`nutkWallFunction`, `kqRWallFunction`, etc.) were applied to `allBoundary`, which was declared as `type patch` in `blockMeshDict`. OpenFOAM requires these functions only on `type wall` patches.

**Fix:** Changed `allBoundary` from `type patch` to `type wall` in `blockMeshDict`. Later replaced with the proper inlet/outlet/sides approach.

---

## Error 5: Continuity Error (Closed Domain)
**Error:**
```
FOAM FATAL ERROR: Continuity error cannot be removed by adjusting the outflow.
Total flux: 5231.32 | Specified mass inflow: 188.818 | Adjustable mass outflow: 0
```
**Cause:** All 6 faces of the bounding box were defined as a single `allBoundary` patch. When velocity was set as `fixedValue` on `allBoundary`, all faces forced inflow with no outlet, violating mass conservation.

**Fix:** Split `allBoundary` into three proper patches in `blockMeshDict`:
- `inlet` (1 face) — `type patch`
- `outlet` (1 face) — `type patch`
- `sides` (4 faces) — `type symmetry`

Updated all boundary condition files (`U`, `p`, `k`, `omega`, `nut`) accordingly.

---

## Error 6: Symmetry Patch Type Mismatch
**Error:**
```
FOAM FATAL IO ERROR: inconsistent patch and patchField types for
patch type symmetry and patchField type zeroGradient for field p
```
**Cause:** The `".*"` wildcard in the `p` boundary field was applying `zeroGradient` to the `sides` patch (which is `type symmetry`). OpenFOAM requires `symmetry`-type patches to use `type symmetry` in boundary fields.

**Fix:**
1. Changed `".*"` to `"mesh.*"` so it only targets the STL geometry wall patch.
2. Added explicit entries for `inlet`, `outlet`, and `sides` in every boundary field.

---

## Error 7: Missing `inlet` Entry in Pressure Field
**Error:**
```
FOAM FATAL IO ERROR: Cannot find patchField entry for inlet
```
**Cause:** After splitting boundaries into `inlet/outlet/sides`, the pressure field `p` was not updated — it still only had `"mesh.*"` with no entries for `inlet`, `outlet`, or `sides`.

**Fix:** Added explicit boundary conditions for all patches in the `p` field:
- `inlet` → `zeroGradient`
- `outlet` → `fixedValue; value uniform 0`
- `sides` → `symmetry`

---

## Summary of All Changes Made

| File | Change |
|------|--------|
| `utils_mesh.py` | Added PIMPLE/SIMPLE/relaxationFactors to fvSolution |
| `utils_mesh.py` | Renamed turbulenceProperties → momentumTransport |
| `utils_mesh.py` | Added wallDist meshWave to fvSchemes |
| `utils_mesh.py` | Split allBoundary → inlet/outlet/sides in blockMeshDict |
| `utils_mesh.py` | Added patchInfo type wall to snappyHexMeshDict |
| `utils_mesh.py` | Changed ".*" → "mesh.*" in all boundary fields |
| `utils_mesh.py` | Added explicit inlet/outlet/sides BCs to all fields |
| `blender_manifest.toml` | Version bumped to 1.8.0 |

**Final working zip:** `cfmesh_tools_2.2.zip`




    object      turbulenceProperties;


    to momentumTransport




    type patch:
    to 
    type wall';


    wallDist
{
    method          meshWave;
}

This single meshWave algorithm tells OpenFOAM exactly how to map out the boundary layer distances for your turbulence fields.

To skip any potential cache issues from before, I have bundled this into a brand new zip file: cfmesh_tools_2.0.zip.


to clean old directorieys error => cd /mnt/NewVolume/code/unstructured_cf_mesh/data/cfmesh_run && rm -rf 0.[0-9]*



i was creatnig directory , without checking path exist, or not