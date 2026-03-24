import os

def write_foam_file(path, content):
    with open(path, "w") as f:
        f.write(content.strip() + "\n")
    print(f"    -> Created file: {path}")

def generate_fields(base_dir, solver_type, nu, inlet_vel, turb_model="laminar"):
    """
    Generates or updates fluid properties and boundary conditions.
    """
    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Version:  11
     \\/     M anipulation  |
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

    # 4. system/controlDict
    CONTROL_CONTENT = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}
application     {solver_type};
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

    # 5. Turbulence Files
    if turb_model == "kEpsilon":
        TURB_PROP = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      turbulenceProperties;
}}
simulationType RAS;
RAS
{{
    RASModel        kEpsilon;
    turbulence      on;
    printCoeffs     on;
}}
"""
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), TURB_PROP)
        
        K_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      k;
}}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{{
    ".*" {{ type zeroGradient; }}
    "allBoundary" {{ type kqRWallFunction; value uniform 0.1; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "k"), K_FILE)
        
        EPS_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      epsilon;
}}
dimensions      [0 2 -3 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{{
    ".*" {{ type zeroGradient; }}
    "allBoundary" {{ type epsilonWallFunction; value uniform 0.1; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "epsilon"), EPS_FILE)

        NUT_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      nut;
}}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{{
    ".*" {{ type calculated; value uniform 0; }}
    "allBoundary" {{ type nutkWallFunction; value uniform 0; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "nut"), NUT_FILE)

    elif turb_model == "kOmegaSST":
        TURB_PROP = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      turbulenceProperties;
}}
simulationType RAS;
RAS
{{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}}
"""
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), TURB_PROP)
        
        K_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      k;
}}
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{{
    ".*" {{ type zeroGradient; }}
    "allBoundary" {{ type kqRWallFunction; value uniform 0.1; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "k"), K_FILE)
        
        OMEGA_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      omega;
}}
dimensions      [0 0 -1 0 0 0 0];
internalField   uniform 1;
boundaryField
{{
    ".*" {{ type zeroGradient; }}
    "allBoundary" {{ type omegaWallFunction; value uniform 1; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "omega"), OMEGA_FILE)
        
        NUT_FILE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      nut;
}}
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{{
    ".*" {{ type calculated; value uniform 0; }}
    "allBoundary" {{ type nutkWallFunction; value uniform 0; }}
}}
"""
        write_foam_file(os.path.join(base_dir, "0", "nut"), NUT_FILE)

    else:
        TURB_PROP = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      turbulenceProperties;
}}
simulationType laminar;
"""
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), TURB_PROP)

def create_case_structure(base_dir, cell_size=0.1, boundary_layers=3, thickness_ratio=1.2, stl_name="mesh.stl"):
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

    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Version:  11
     \\/     M anipulation  |
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

    # Background cell count
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
    locationInMesh (1.5 1.5 1.5);
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
    finalLayerThickness 0.3;
    minThickness        0.1;
    nGrow               0;
    featureAngle        60;
    nRelaxIter          3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals      3;
    nSmoothThickness    10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
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
    minTwist            -1;
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
    
    generate_fields(base_dir, "icoFoam", 1e-5, (0, 0, 0), "laminar")
    
    return True
