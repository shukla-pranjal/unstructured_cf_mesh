# Week 5 — Key Concepts & Notes

## Y+ (Dimensionless Wall Distance)
Dimensionless wall distance used to ensure proper mesh resolution near walls.
- Y+ ≤ 5: Resolves viscous sublayer (very fine mesh)
- 30 ≤ Y+ ≤ 300: Wall function region (common for industrial CFD)
- 5 < Y+ < 30: Transitional / buffer layer (not recommended)

## Turbulent Eddy Length Scale
Approximate size of turbulent eddies, usually taken as 0.07 × characteristic length.

## OpenFOAM 11 Breaking Changes
- `turbulenceProperties` renamed to `momentumTransport`
- `simpleFoam` deprecated → use `foamRun -solver incompressibleFluid`
- `icoFoam` still works as-is
- `wallDist { method meshWave; }` required in `fvSchemes` for kOmegaSST

## Boundary Condition Strategy (Wind Tunnel)
- **inlet** → fixedValue (velocity), zeroGradient (pressure)
- **outlet** → zeroGradient (velocity), fixedValue 0 (pressure)
- **sides** → symmetry (all fields)
- **mesh wall** → noSlip (velocity), wall functions (k, omega, nut)

## Post-Processing in Blender
- OpenFOAM fields stored in time directories (`0/`, `0.1/`, etc.)
- Scalar fields (p): one value per line, `nonuniform List<scalar>`
- Vector fields (U): `(Ux Uy Uz)` per line, `nonuniform List<vector>`
- Vertex colors applied via jet colormap (Blue → Cyan → Green → Yellow → Red)

## Useful Commands
```bash
# Clean old time directories
cd /mnt/NewVolume/code/unstructured_cf_mesh/data/cfmesh_run && rm -rf 0.[0-9]*

# Run solver (OF11)
source /opt/openfoam11/etc/bashrc && foamRun -solver incompressibleFluid

# Check mesh quality
source /opt/openfoam11/etc/bashrc && checkMesh
```