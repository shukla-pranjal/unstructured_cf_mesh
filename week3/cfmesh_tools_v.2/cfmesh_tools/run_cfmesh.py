import subprocess
import os

def run_cfmesh_command(command, working_dir=None):
    """
    A basic Python script to execute terminal commands via subprocess.
    This fulfills the Week 1 requirement.
    """
    print(f"Executing: {command}")
    try:
        # We use shell=True here for basic commands, but for real cfMesh
        # it might be safer to pass as a list of strings if shell=False.
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=working_dir,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if result.returncode == 0:
            print("Command executed successfully!")
            print("Output:\n", result.stdout)
            return True, result.stdout
        else:
            print("Command failed with error:")
            print(result.stderr)
            return False, result.stderr
            
    except Exception as e:
        print(f"An exception occurred: {e}")
def write_foam_file(path, content):
    with open(path, "w") as f:
        f.write(content.strip() + "\n")
    print(f"    -> Created file: {path}")

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

    # 2. Define Templates
    HEADER = """/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Version:  11
     \\/     M anipulation  |
\*---------------------------------------------------------------------------*/"""

    U_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volVectorField;
    object      U;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{{
    ".*"
    {{
        type            zeroGradient;
    }}
}}
"""

    p_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       volScalarField;
    object      p;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
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

    PHYSICAL_PROP_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "constant";
    object      physicalProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
viscosityModel  constant;
nu              [0 2 -1 0 0 0 0] 1e-05;
"""

    CONTROL_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
application     icoFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         10;
deltaT          0.005;
writeControl    timeStep;
writeInterval   100;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""

    FV_SCHEMES_TEMPLATE = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
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
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
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

    MESH_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version   2.0;
    format    ascii;
    class     dictionary;
    location  "system";
    object    meshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
surfaceFile "{stl_name}";
maxCellSize {cell_size};
boundaryCellSize {cell_size / 2.0};

boundaryLayers
{{
    nLayers {boundary_layers};
    thicknessRatio {thickness_ratio};
    
    patchBoundaryLayers
    {{
        // Auto-generated default
    }}
}}
"""

    # 3. Write Files
    write_foam_file(os.path.join(base_dir, "0", "U"), U_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "0", "p"), p_TEMPLATE)
    
    # physicalProperties corresponds to our template
    write_foam_file(os.path.join(base_dir, "constant", "physicalProperties"), PHYSICAL_PROP_TEMPLATE)
    
    write_foam_file(os.path.join(base_dir, "system", "controlDict"), CONTROL_DICT_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "fvSchemes"), FV_SCHEMES_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "fvSolution"), FV_SOLUTION_TEMPLATE)
    write_foam_file(os.path.join(base_dir, "system", "meshDict"), MESH_DICT_TEMPLATE)
    
    return True

if __name__ == "__main__":
    import tempfile
    
    print("\n--- Testing OpenFOAM Case Creation ---")
    # Create a dummy case in a temporary directory for testing
    test_case_dir = os.path.join(os.getcwd(), "test_cfmesh_case")
    create_case_structure(test_case_dir)
    
    print("\n--- Testing OpenFOAM installation (inside case dir) ---")
    # To run OpenFOAM commands via subprocess on Linux, we usually need to source the environment first.
    # The documentation indicates OpenFOAM 11 is installed at /opt/openfoam11
    
    source_command = ". /opt/openfoam11/etc/bashrc"
    
    # Notice we now pass `working_dir=test_case_dir` because OpenFOAM commands
    # must be run from inside a valid case folder!
    full_command = f"{source_command} && cartesianMesh -help"
    
    run_cfmesh_command(full_command, working_dir=test_case_dir)
