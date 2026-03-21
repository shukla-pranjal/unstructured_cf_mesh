import subprocess
import os

def run_cfmesh_command(command, working_dir=None):
    """
    A basic Python script to execute terminal commands via subprocess.
    Forces /bin/bash as the shell so that 'source' works correctly.
    """
    print(f"Executing: {command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            executable='/bin/bash',  # Force bash instead of /bin/sh
            cwd=working_dir,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if result.returncode == 0:
            print("Command executed successfully!")
            print("STDOUT:\n", result.stdout)
            return True, result.stdout
        else:
            print("Command failed!")
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr)
            return False, result.stderr
            
    except Exception as e:
        print(f"An exception occurred: {e}")
        return False, str(e)

def launch_paraview(base_dir):
    """
    Creates a .foam stub and launches ParaView as a background process.
    """
    foam_file = os.path.join(base_dir, "case.foam")
    if not os.path.exists(foam_file):
        with open(foam_file, "w") as f:
            pass
    
    print(f"Launching ParaView for: {foam_file}")
    try:
        # Use Popen to avoid blocking Blender
        subprocess.Popen(["paraview", foam_file])
        return True
    except Exception as e:
        print(f"Failed to launch ParaView: {e}")
        return False

def write_foam_file(path, content):
    with open(path, "w") as f:
        f.write(content.strip() + "\n")
    print(f"    -> Created file: {path}")

def generate_fields(base_dir, solver_type, nu, inlet_vel):
    """
    Generates or updates fluid properties and boundary conditions.
    """
    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \    /   O peration     | Website:  https://openfoam.org
    \  /    A nd           | Version:  11
     \/     M anipulation  |
\*---------------------------------------------------------------------------*/"""

    # 1. 0/U (Velocity)
    U_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volVectorField;
    object      U;
}}
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({inlet_vel[0]} {inlet_vel[1]} {inlet_vel[2]});
boundaryField
{{
    ".*"
    {{
        type            fixedValue;
        value           $internalField;
    }}
    "allBoundary"
    {{
        type            noSlip;
    }}
}}
"""
    write_foam_file(os.path.join(base_dir, "0", "U"), U_CONTENT)

    # 2. 0/p (Pressure)
    p_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      p;
}}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{{
    ".*"
    {{
        type            zeroGradient;
    }}
}}
"""
    write_foam_file(os.path.join(base_dir, "0", "p"), p_CONTENT)

    # 3. constant/transportProperties
    TRANSPORT_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      transportProperties;
}}
transportModel  constant;
nu              [0 2 -1 0 0 0 0] {nu};
"""
    write_foam_file(os.path.join(base_dir, "constant", "transportProperties"), TRANSPORT_CONTENT)

    PHYSICAL_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      physicalProperties;
}}
transportModel  constant;
nu              [0 2 -1 0 0 0 0] {nu};
"""
    write_foam_file(os.path.join(base_dir, "constant", "physicalProperties"), PHYSICAL_CONTENT)

    MOMENTUM_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      momentumTransport;
}}
simulationType  laminar;
"""
    write_foam_file(os.path.join(base_dir, "constant", "momentumTransport"), MOMENTUM_CONTENT)

    CONTROL_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}
application     {"foamRun" if solver_type == 'simpleFoam' else solver_type};
startFrom       startTime;
startTime       0;
stopAt          {"endTime" if solver_type == 'icoFoam' else "nextWrite"};
endTime         0.5;
deltaT          0.001;
writeControl    {"timeStep" if solver_type == 'icoFoam' else "runTime"};
writeInterval   {"20" if solver_type == 'icoFoam' else "0.1"};
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""
    write_foam_file(os.path.join(base_dir, "system", "controlDict"), CONTROL_CONTENT)

    # 5. system/fvSchemes & system/fvSolution dynamically
    ddt_scheme = "steadyState" if solver_type == 'simpleFoam' else "Euler"
    
    FV_SCHEMES = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}}
ddtSchemes {{ default {ddt_scheme}; }}
gradSchemes {{ default Gauss linear; }}
divSchemes {{
    default none;
    div(phi,U) Gauss limitedLinearV 1;
    div(phi,k) Gauss limitedLinear 1;
    div(phi,epsilon) Gauss limitedLinear 1;
    div(phi,omega) Gauss limitedLinear 1;
    div(phi,R) Gauss limitedLinear 1;
    div(R) Gauss linear;
    div(phi,nuTilda) Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default corrected; }}
"""
    write_foam_file(os.path.join(base_dir, "system", "fvSchemes"), FV_SCHEMES)

    algo_block = """SIMPLE
{
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       0;
}
relaxationFactors
{
    fields { p 0.3; }
    equations { U 0.7; }
}""" if solver_type == 'simpleFoam' else """PISO
{
    nCorrectors     2;
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       0;
}"""

    FV_SOLUTION = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}}
solvers
{{
    p
    {{
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-06;
        relTol          0.1;
    }}
    pFinal
    {{
        $p;
        relTol          0;
    }}
    U
    {{
        solver          PBiCG;
        preconditioner  DILU;
        tolerance       1e-05;
        relTol          0;
    }}
}}
{algo_block}
"""
    write_foam_file(os.path.join(base_dir, "system", "fvSolution"), FV_SOLUTION)


def create_case_structure(base_dir, cell_size=0.1, boundary_layers=3, thickness_ratio=1.2, stl_name="mesh.stl", final_layer_thickness=0.3, min_thickness=0.1, max_medial_ratio=0.3):
    """
    Creates the required OpenFOAM case directory structure and 
    populates it with real dictionary files.
    """
    print(f"Creating OpenFOAM case structure in: {base_dir}")
    
    # 1. Create Folders
    folders = ["0", "constant", "system"]
    for folder in folders:
        path = os.path.join(base_dir, folder)
        os.makedirs(path, exist_ok=True)
        print(f"  -> Created folder: {path}")

    # 2. Define Templates
    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \    /   O peration     | Website:  https://openfoam.org
    \  /    A nd           | Version:  11
     \/     M anipulation  |
\*---------------------------------------------------------------------------*/"""

    FV_SCHEMES_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}}
ddtSchemes
{{
    default         Euler;
}}
gradSchemes
{{
    default         Gauss linear;
}}
divSchemes
{{
    default         none;
    div(phi,U)      Gauss limitedLinearV 1;
    div(phi,k)      Gauss limitedLinear 1;
    div(phi,epsilon) Gauss limitedLinear 1;
    div(phi,omega)  Gauss limitedLinear 1;
    div(phi,R)      Gauss limitedLinear 1;
    div(R)          Gauss linear;
    div(phi,nuTilda) Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes
{{
    default         Gauss linear corrected;
}}
interpolationSchemes
{{
    default         linear;
}}
snGradSchemes
{{
    default         corrected;
}}
"""

    FV_SOLUTION_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}}
solvers
{{
    p
    {{
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-06;
        relTol          0.1;
    }}
    pFinal
    {{
        $p;
        relTol          0;
    }}
    U
    {{
        solver          PBiCG;
        preconditioner  DILU;
        tolerance       1e-05;
        relTol          0;
    }}
}}
PISO
{{
    nCorrectors     2;
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       0;
}}
"""

    n_bg_cells = max(5, min(20, int(1.0 / cell_size)))
    
    BLOCK_MESH_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version   2.0;
    format    ascii;
    class     dictionary;
    location  "system";
    object    blockMeshDict;
}}
convertToMeters 1;
vertices
(
    (-2 -2 -2) ( 2 -2 -2) ( 2  2 -2) (-2  2 -2)
    (-2 -2  2) ( 2 -2  2) ( 2  2  2) (-2  2  2)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({n_bg_cells} {n_bg_cells} {n_bg_cells}) simpleGrading (1 1 1)
);
boundary
(
    allBoundary
    {{
        type patch;
        faces
        (
            (3 7 6 2) (0 4 7 3) (2 6 5 1)
            (1 5 4 0) (0 3 2 1) (4 5 6 7)
        );
    }}
);
"""

    SNAPPY_HEX_MESH_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version   2.0;
    format    ascii;
    class     dictionary;
    location  "system";
    object    snappyHexMeshDict;
}}
castellatedMesh true;
snap            true;
addLayers       {"true" if boundary_layers > 0 else "false"};
geometry
{{
    {stl_name}
    {{
        type triSurfaceMesh;
        name {stl_name.replace('.stl', '')};
    }}
}};
castellatedMeshControls
{{
    maxLocalCells       100000;
    maxGlobalCells      2000000;
    minRefinementCells  10;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels 3;
    features ();
    refinementSurfaces
    {{
        {stl_name.replace('.stl', '')}
        {{
            level (2 2);
        }}
    }}
    resolveFeatureAngle 30;
    refinementRegions {{}};
    locationInMesh (1.9 1.9 1.9);
    allowFreeStandingZoneFaces true;
}};
snapControls
{{
    nSmoothPatch    3;
    tolerance       2.0;
    nSolveIter      100;
    nRelaxIter      5;
    nFeatureSnapIter 10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}};
addLayersControls
{{
    relativeSizes       true;
    layers
    {{
        "{stl_name.replace('.stl', '')}.*"
        {{
            nSurfaceLayers {boundary_layers};
        }}
    }}
    expansionRatio      {thickness_ratio};
    finalLayerThickness {final_layer_thickness};
    minThickness        {min_thickness};
    nGrow               0;
    featureAngle        60;
    nRelaxIter          3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio {max_medial_ratio};
    minMedialAxisAngle  90;
    nBufferCellsNoExtrude 0;
    nLayerIter          50;
}};
meshQualityControls
{{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minVol              1e-13;
    minTetQuality       -1e30;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.02;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
}};
mergeTolerance 1e-6;
"""

    write_foam_file(os.path.join(base_dir, "system", "fvSchemes"), FV_SCHEMES_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "fvSolution"), FV_SOLUTION_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "blockMeshDict"), BLOCK_MESH_DICT_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "snappyHexMeshDict"), SNAPPY_HEX_MESH_DICT_TEMPLATE)
    
    # Initialize fields with default values
    generate_fields(base_dir, "icoFoam", 1e-5, (0, 0, 0))
    
    return True

if __name__ == "__main__":
    test_case_dir = os.path.join(os.getcwd(), "test_cfmesh_case")
    create_case_structure(test_case_dir)
    print("\n--- Test Finished ---")
