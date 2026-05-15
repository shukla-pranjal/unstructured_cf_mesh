import os

def write_foam_file(path, content):
    with open(path, "w") as f:
        f.write(content.strip() + "\n")
    print(f"    -> Created file: {path}")

def write_decompose_par(base_dir, cpu_cores):
    if cpu_cores <= 1: return
    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
  \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  v2412
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      decomposeParDict;
}}
numberOfSubdomains {cpu_cores};
method          scotch;
"""
    write_foam_file(os.path.join(base_dir, "system", "decomposeParDict"), content)

def generate_fields(base_dir, solver_type, nu, inlet_vel, turb_model="laminar", turb_k=0.1, turb_epsilon=0.1, turb_omega=1.0, turb_nut=0.0, start_time=0.0, end_time=0.5, delta_t=0.001, write_interval=20, boundary_patches=None):
    """
    Generates or updates fluid properties and boundary conditions.
    """
    # Smart override for steady-state
    if solver_type == 'simpleFoam':
        delta_t = 1
        start_time = 0
        if end_time < 10:  # If the user passed a transient end_time like 0.5
            end_time = 500
        if write_interval < 10:
            write_interval = 100

    u_bcs = ""
    p_bcs = ""
    k_bcs = ""
    eps_bcs = ""
    omega_bcs = ""
    nut_bcs = ""

    # Primary catch-all regex for OpenFOAM
    catch_all = '".*"'

    if not boundary_patches or len(boundary_patches) == 0:
        # Defaults for un-labeled geometry
        u_bcs = f'''
    {catch_all}
    {{
        type            noSlip;
    }}
    "inlet"
    {{
        type            fixedValue;
        value           uniform ({inlet_vel[0]} {inlet_vel[1]} {inlet_vel[2]});
    }}
    "outlet"
    {{
        type            zeroGradient;
    }}
    "sides"
    {{
        type            symmetry;
    }}'''
        p_bcs = f'''
    {catch_all}
    {{
        type            zeroGradient;
    }}
    "inlet"
    {{
        type            zeroGradient;
    }}
    "outlet"
    {{
        type            fixedValue;
        value           uniform 0;
    }}
    "sides"
    {{
        type            symmetry;
    }}'''
        k_bcs = f'''
    {catch_all} {{ type kqRWallFunction; value uniform {turb_k}; }}
    "inlet" {{ type fixedValue; value uniform {turb_k}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        eps_bcs = f'''
    {catch_all} {{ type epsilonWallFunction; value uniform {turb_epsilon}; }}
    "inlet" {{ type fixedValue; value uniform {turb_epsilon}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        omega_bcs = f'''
    {catch_all} {{ type omegaWallFunction; value uniform {turb_omega}; }}
    "inlet" {{ type fixedValue; value uniform {turb_omega}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        nut_bcs = f'''
    {catch_all} {{ type nutkWallFunction; value uniform {turb_nut}; }}
    "inlet" {{ type calculated; value uniform {turb_nut}; }}
    "outlet" {{ type calculated; value uniform {turb_nut}; }}
    "sides" {{ type symmetry; }}'''
    else:
        # Dynamic patches defined by user
        u_bcs = f'\n    {catch_all} {{ type noSlip; }}'
        p_bcs = f'\n    {catch_all} {{ type zeroGradient; }}'
        k_bcs = f'\n    {catch_all} {{ type kqRWallFunction; value uniform {turb_k}; }}'
        eps_bcs = f'\n    {catch_all} {{ type epsilonWallFunction; value uniform {turb_epsilon}; }}'
        omega_bcs = f'\n    {catch_all} {{ type omegaWallFunction; value uniform {turb_omega}; }}'
        nut_bcs = f'\n    {catch_all} {{ type nutkWallFunction; value uniform {turb_nut}; }}'

        for p in boundary_patches:
            safe_name = p.name.replace(' ', '_')
            name = f'"{safe_name}.*"'
            btype = p.bc_type
            if btype == 'wall':
                u_bcs += f"\n    {name} {{ type noSlip; }}"
                p_bcs += f"\n    {name} {{ type zeroGradient; }}"
                k_bcs += f"\n    {name} {{ type kqRWallFunction; value uniform {turb_k}; }}"
                eps_bcs += f"\n    {name} {{ type epsilonWallFunction; value uniform {turb_epsilon}; }}"
                omega_bcs += f"\n    {name} {{ type omegaWallFunction; value uniform {turb_omega}; }}"
                nut_bcs += f"\n    {name} {{ type nutkWallFunction; value uniform {turb_nut}; }}"
            elif btype == 'inlet':
                u_bcs += f"\n    {name} {{ type fixedValue; value uniform ({inlet_vel[0]} {inlet_vel[1]} {inlet_vel[2]}); }}"
                p_bcs += f"\n    {name} {{ type zeroGradient; }}"
                k_bcs += f"\n    {name} {{ type fixedValue; value uniform {turb_k}; }}"
                eps_bcs += f"\n    {name} {{ type fixedValue; value uniform {turb_epsilon}; }}"
                omega_bcs += f"\n    {name} {{ type fixedValue; value uniform {turb_omega}; }}"
                nut_bcs += f"\n    {name} {{ type calculated; value uniform {turb_nut}; }}"
            elif btype == 'outlet':
                u_bcs += f"\n    {name} {{ type zeroGradient; }}"
                p_bcs += f"\n    {name} {{ type fixedValue; value uniform 0; }}"
                k_bcs += f"\n    {name} {{ type zeroGradient; }}"
                eps_bcs += f"\n    {name} {{ type zeroGradient; }}"
                omega_bcs += f"\n    {name} {{ type zeroGradient; }}"
                nut_bcs += f"\n    {name} {{ type calculated; value uniform {turb_nut}; }}"
            elif btype == 'symmetry':
                sym = f"\n    {name} {{ type symmetry; }}"
                u_bcs += sym
                p_bcs += sym
                k_bcs += sym
                eps_bcs += sym
                omega_bcs += sym
                nut_bcs += sym

    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
  \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Version:  v2412
     \\/     M anipulation  |
\*---------------------------------------------------------------------------*/"""

    # 1. 0/U
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
{{{u_bcs}
}}
"""
    write_foam_file(os.path.join(base_dir, "0", "U"), U_CONTENT)

    # 2. 0/p
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
{{{p_bcs}
}}
"""
    write_foam_file(os.path.join(base_dir, "0", "p"), p_CONTENT)

    # 3. physicalProperties
    TRANSPORT_CONTENT_PHYS = f"""{HEADER}
FoamFile
{{
    format      ascii;
    class       dictionary;
    object      physicalProperties;
}}
transportModel  Newtonian;
nu              [0 2 -1 0 0 0 0] {nu};
"""
    write_foam_file(os.path.join(base_dir, "constant", "physicalProperties"), TRANSPORT_CONTENT_PHYS)
    write_foam_file(os.path.join(base_dir, "constant", "transportProperties"), TRANSPORT_CONTENT_PHYS)

    # 4. controlDict
    # For icoFoam: enable adjustable time-stepping to keep Courant number < 1.
    # This prevents the FPE/divergence crash that occurs when a fixed dt gives Co >> 1.
    # For simpleFoam: steady-state, adjustTimeStep has no meaning so it stays off.
    if solver_type == 'icoFoam':
        adjust_block = "adjustTimeStep  yes;\nmaxCo           0.8;\nmaxDeltaT       {delta_t};".format(delta_t=delta_t * 10)
        write_control = "adjustableRunTime"
        write_interval_val = end_time / max(write_interval, 1)  # write_interval as physical time
    else:
        adjust_block = "adjustTimeStep  no;"
        write_control = "timeStep"
        write_interval_val = write_interval

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
startTime       {start_time};
stopAt          endTime;
endTime         {end_time};
deltaT          {delta_t};
{adjust_block}
writeControl    {write_control};
writeInterval   {write_interval_val};
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
        RAS_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class dictionary; location "constant"; object momentumTransport; }}
simulationType RAS;
RAS {{ RASModel kEpsilon; turbulence on; printCoeffs on; }}
"""
        write_foam_file(os.path.join(base_dir, "constant", "momentumTransport"), RAS_CONTENT)
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), RAS_CONTENT.replace("momentumTransport", "turbulenceProperties"))
        
        K_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {turb_k};
boundaryField {{{k_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "k"), K_CONTENT)
        
        EPS_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object epsilon; }}
dimensions [0 2 -3 0 0 0 0];
internalField uniform {turb_epsilon};
boundaryField {{{eps_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "epsilon"), EPS_CONTENT)

        NUT_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform {turb_nut};
boundaryField {{{nut_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "nut"), NUT_CONTENT)

    elif turb_model == "kOmegaSST":
        RAS_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class dictionary; location "constant"; object momentumTransport; }}
simulationType RAS;
RAS {{ RASModel kOmegaSST; turbulence on; printCoeffs on; }}
"""
        write_foam_file(os.path.join(base_dir, "constant", "momentumTransport"), RAS_CONTENT)
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), RAS_CONTENT.replace("momentumTransport", "turbulenceProperties"))
        
        K_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object k; }}
dimensions [0 2 -2 0 0 0 0];
internalField uniform {turb_k};
boundaryField {{{k_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "k"), K_CONTENT)

        OMEGA_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object omega; }}
dimensions [0 0 -1 0 0 0 0];
internalField uniform {turb_omega};
boundaryField {{{omega_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "omega"), OMEGA_CONTENT)

        NUT_CONTENT = f"""{HEADER}
FoamFile {{ format ascii; class volScalarField; object nut; }}
dimensions [0 2 -1 0 0 0 0];
internalField uniform {turb_nut};
boundaryField {{{nut_bcs}\n}}"""
        write_foam_file(os.path.join(base_dir, "0", "nut"), NUT_CONTENT)
    else:
        lam_content = f"{HEADER}\nFoamFile {{ format ascii; class dictionary; location \"constant\"; object momentumTransport; }}\nsimulationType laminar;"
        write_foam_file(os.path.join(base_dir, "constant", "momentumTransport"), lam_content)
        write_foam_file(os.path.join(base_dir, "constant", "turbulenceProperties"), lam_content.replace("momentumTransport", "turbulenceProperties"))

def create_case_structure(base_dir, cell_size=0.1, boundary_layers=3, thickness_ratio=1.2, stl_name="mesh.stl", cpu_cores=1, boundary_patches=None, edge_refinements=None, improve_quality=True, layer_optimise=True, layer_max_iter=5):
    """
    Creates the required OpenFOAM case directory structure.
    """
    folders = ["0", "constant", "system", "constant/triSurface"]
    for folder in folders:
        os.makedirs(os.path.join(base_dir, folder), exist_ok=True)

    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
  \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Version:  v2412
     \\/     M anipulation  |
\*---------------------------------------------------------------------------*/"""

    FV_SCHEMES = f"""{HEADER}
FoamFile {{ format ascii; class dictionary; location "system"; object fvSchemes; }}
ddtSchemes {{ default Euler; }}
gradSchemes {{ default Gauss linear; }}
divSchemes {{ default none; div(phi,U) Gauss limitedLinearV 1; div(phi,k) Gauss limitedLinear 1; div(phi,epsilon) Gauss limitedLinear 1; div(phi,omega) Gauss limitedLinear 1; div((nuEff*dev2(T(grad(U))))) Gauss linear; }}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default corrected; }}

wallDist
{{
    method meshWave;
}}
"""
    write_foam_file(os.path.join(base_dir, "system", "fvSchemes"), FV_SCHEMES)

    FV_SOLUTION = f"""{HEADER}
FoamFile {{ version 2.0; format ascii; class dictionary; object fvSolution; }}
solvers
{{
    p {{ solver PCG; preconditioner DIC; tolerance 1e-06; relTol 0.01; }}
    pFinal {{ $p; relTol 0; }}
    U {{ solver PBiCGStab; preconditioner DILU; tolerance 1e-05; relTol 0.1; }}
    UFinal {{ $U; relTol 0; }}
    Phi {{ $p; }}
    "(k|epsilon|omega|_.*)" {{ solver PBiCGStab; preconditioner DILU; tolerance 1e-05; relTol 0.1; }}
    "(kFinal|epsilonFinal|omegaFinal)" {{ $k; relTol 0; }}
}}
potentialFlow {{ nNonOrthogonalCorrectors 3; pRefCell 0; pRefValue 0; PhiRefCell 0; PhiRefValue 0; }}
PISO {{ nCorrectors 2; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }}
PIMPLE {{ nOuterCorrectors 1; nCorrectors 2; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }}
SIMPLE {{ nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0; }}
relaxationFactors {{ equations {{ U 0.7; k 0.7; epsilon 0.7; omega 0.7; }} fields {{ p 0.3; }} }}
"""
    write_foam_file(os.path.join(base_dir, "system", "fvSolution"), FV_SOLUTION)

    # meshDict
    patch_layers = ""
    local_refine = ""
    rename_boundary = ""
    catch_all = '".*"'
    
    if not boundary_patches or len(boundary_patches) == 0:
        patch_layers = f'\n        {catch_all}\n        {{ nLayers {boundary_layers}; thicknessRatio {thickness_ratio}; maxFirstLayerThickness {cell_size*0.5}; }}'
        local_refine = f'\n    {catch_all}\n    {{ cellSize {cell_size*0.5}; }}'
    else:
        for p in boundary_patches:
            # OpenFOAM replaces spaces with underscores for patch names
            safe_name = p.name.replace(' ', '_')
            
            # Use safe_name for wildcard matching too, just to be robust
            name = f'"{safe_name}.*"'
            csize = p.local_cell_size if p.use_local_cell_size else cell_size
            
            optimise_str = ""
            if p.boundary_layers > 0:
                if layer_optimise:
                    optimise_str = f" optimiseLayer yes; nSmoothingIterations {layer_max_iter};"
                patch_layers += f'\n        {name}\n        {{ nLayers {p.boundary_layers}; thicknessRatio {thickness_ratio}; maxFirstLayerThickness {csize*0.5};{optimise_str} }}'
            local_refine += f'\n    {name}\n    {{ cellSize {csize*0.5}; }}'
            
            # Fix boundary types for OpenFOAM
            btype = "wall"
            if p.bc_type in ['inlet', 'outlet']:
                btype = "patch"
            elif p.bc_type == 'symmetry':
                btype = "symmetry"
            
            rename_boundary += f'\n        "{safe_name}"\n        {{\n            type {btype};\n            newName "{safe_name}";\n        }}'

    rename_block = ""
    if rename_boundary:
        rename_block = f"\nrenameBoundary\n{{\n    newPatchNames\n    {{{rename_boundary}\n    }}\n}}"

    edge_refine_block = ""
    if edge_refinements:
        edge_refine_block = "\nedgeRefinement\n{"
        for er in edge_refinements:
            edge_refine_block += f'\n    "{er["name"]}.*"\n    {{ cellSize {er["cell_size"]}; }}'
        edge_refine_block += "\n}"

    improve_str = "yes" if improve_quality else "no"

    # ── Octree-exact-multiple guard ─────────────────────────────────────────
    # cfMesh crashes with "0 cells" when maxCellSize divides evenly into the
    # bounding box. The official fix (per the FOAM error message itself) is
    # to nudge the cell size by a tiny fraction. We apply 1e-5 relative
    # epsilon automatically so the user never has to worry about this.
    safe_cell_size = cell_size * (1.0 - 1e-5)
    if safe_cell_size != cell_size:
        print(f"[cfMesh] Applying octree-safe cell size: {safe_cell_size:.8g} (user: {cell_size})")

    MESH_DICT = f"""{HEADER}
FoamFile {{ version 2.0; format ascii; class dictionary; object meshDict; }}
surfaceFile "constant/triSurface/{stl_name}";
maxCellSize {safe_cell_size};
boundaryCellSize {safe_cell_size};
boundaryLayers {{ patchBoundaryLayers {{{patch_layers}\n    }} }}\nlocalRefinement {{{local_refine}\n}}{edge_refine_block}{rename_block}
improveMeshQuality {improve_str};
"""
    write_foam_file(os.path.join(base_dir, "system", "meshDict"), MESH_DICT)
    return True
