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

## Error 8: `simpleFoam` Deprecated in OpenFOAM 11
**Error:** Solver appeared to run (100 time steps counted) but all residuals were 0.00 and showed "Converged" falsely.

**Cause:** OpenFOAM 11 replaced `simpleFoam` with `foamRun -solver incompressibleFluid`. The `simpleFoam` command only prints a deprecation notice and exits — the solver never actually ran. The residual parser then found zero residual lines and defaulted everything to 0.

**Fix:**
1. Mapped `simpleFoam` → `foamRun -solver incompressibleFluid` in `operators.py` before launching.
2. Fixed residual parser to show "No Residuals Found" error instead of falsely claiming "Converged" when no data exists.

---

## Error 9: Silent Path Creation (No Validation)
**Error:** Users could type `/abc/xyz/fake` as the export directory and the addon would silently create deeply nested directories via `os.makedirs(exist_ok=True)`.

**Fix:** Added path-walk validation — walks up the path tree and rejects if more than 1 level needs creation. Also added parent directory existence check.

---

## Error 10: Field Parser Couldn't Read OF11 Data
**Error:** "Could not extract field values" when clicking "Color Mesh by Field".

**Cause:** The regex expected the data count on the same line as `List<scalar>`, but OF11 puts the count on a separate line. Vector values `(Ux Uy Uz)` with parentheses also weren't being parsed properly.

**Fix:** Rewrote `parse_foam_field()` to:
- Handle count on separate line
- Strip parentheses from vector entries
- Use `try/except ValueError` for robust parsing
- Tested against actual 17,228-value pressure field data

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
| `utils_mesh.py` | Wrapped create_case_structure in try/except |
| `operators.py` | 15+ validation checks across all 4 operators |
| `operators.py` | STL importer with file browser and validation |
| `operators.py` | simpleFoam → foamRun -solver incompressibleFluid |
| `operators.py` | checkMesh quality stats parser |
| `operators.py` | Solver residual log parser |
| `operators.py` | Color mesh by field (jet colormap vertex colors) |
| `operators.py` | Concurrent run guard (don't stack processes) |
| `properties.py` | Y+ calculator with live Reynolds number |
| `properties.py` | Post-processing properties (checkMesh, residuals, color field) |
| `ui.py` | Red alert box for error display |
| `ui.py` | Expanded Post-Processing panel (checkMesh, residuals, color viz) |
| `ui.py` | Import STL Geometry button |
| `__init__.py` | Registered all new operators |
| `blender_manifest.toml` | Version bumped to 2.3.0 |

**Final working zip:** `cfmesh_tools_2.3.zip`