import os
import re

utils_path = '/mnt/NewVolume/code/unstructured_cf_mesh/week8/cfmesh_tools/utils_mesh.py'
with open(utils_path, 'r') as f:
    text = f.read()

# 1. Update signatures
text = text.replace(
    'def create_case_structure(base_dir, cell_size=0.1, boundary_layers=3, thickness_ratio=1.2, stl_name="mesh.stl", cpu_cores=1):',
    'def create_case_structure(base_dir, cell_size=0.1, boundary_layers=3, thickness_ratio=1.2, stl_name="mesh.stl", cpu_cores=1, boundary_patches=None):'
)

text = text.replace(
    'def generate_fields(base_dir, solver_type, nu, inlet_vel, turb_model="laminar", turb_k=0.1, turb_epsilon=0.1, turb_omega=1.0, turb_nut=0.0, start_time=0.0, end_time=0.5, delta_t=0.001, write_interval=20):',
    'def generate_fields(base_dir, solver_type, nu, inlet_vel, turb_model="laminar", turb_k=0.1, turb_epsilon=0.1, turb_omega=1.0, turb_nut=0.0, start_time=0.0, end_time=0.5, delta_t=0.001, write_interval=20, boundary_patches=None):'
)


# 2. Add generator for boundary_patches before HEADER
new_patch_logic = """
    u_bcs = ""
    p_bcs = ""
    k_bcs = ""
    eps_bcs = ""
    omega_bcs = ""
    nut_bcs = ""

    if not boundary_patches or len(boundary_patches) == 0:
        u_bcs = f'''
    "mesh.*" { { "type": "noSlip;" } }
    "inlet" { { "type": "fixedValue;", "value": "uniform ({inlet_vel[0]} {inlet_vel[1]} {inlet_vel[2]});" } }
    "outlet" { { "type": "zeroGradient;" } }
    "sides" { { "type": "symmetry;" } }'''
        p_bcs = '''
    "mesh.*" { type zeroGradient; }
    "inlet" { type zeroGradient; }
    "outlet" { type fixedValue; value uniform 0; }
    "sides" { type symmetry; }'''
        k_bcs = f'''
    "mesh.*" {{ type kqRWallFunction; value uniform {turb_k}; }}
    "inlet" {{ type fixedValue; value uniform {turb_k}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        eps_bcs = f'''
    "mesh.*" {{ type epsilonWallFunction; value uniform {turb_epsilon}; }}
    "inlet" {{ type fixedValue; value uniform {turb_epsilon}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        omega_bcs = f'''
    "mesh.*" {{ type omegaWallFunction; value uniform {turb_omega}; }}
    "inlet" {{ type fixedValue; value uniform {turb_omega}; }}
    "outlet" {{ type zeroGradient; }}
    "sides" {{ type symmetry; }}'''
        nut_bcs = f'''
    "mesh.*" {{ type nutkWallFunction; value uniform {turb_nut}; }}
    "inlet" {{ type calculated; value uniform {turb_nut}; }}
    "outlet" {{ type calculated; value uniform {turb_nut}; }}
    "sides" {{ type symmetry; }}'''
    else:
        for p in boundary_patches:
            name = f'"{p.name}.*"'
            btype = p.bc_type
            if btype == 'wall':
                u_bcs += f"\\n    {name} {{ type noSlip; }}"
                p_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                k_bcs += f"\\n    {name} {{ type kqRWallFunction; value uniform {turb_k}; }}"
                eps_bcs += f"\\n    {name} {{ type epsilonWallFunction; value uniform {turb_epsilon}; }}"
                omega_bcs += f"\\n    {name} {{ type omegaWallFunction; value uniform {turb_omega}; }}"
                nut_bcs += f"\\n    {name} {{ type nutkWallFunction; value uniform {turb_nut}; }}"
            elif btype == 'inlet':
                u_bcs += f"\\n    {name} {{ type fixedValue; value uniform ({inlet_vel[0]} {inlet_vel[1]} {inlet_vel[2]}); }}"
                p_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                k_bcs += f"\\n    {name} {{ type fixedValue; value uniform {turb_k}; }}"
                eps_bcs += f"\\n    {name} {{ type fixedValue; value uniform {turb_epsilon}; }}"
                omega_bcs += f"\\n    {name} {{ type fixedValue; value uniform {turb_omega}; }}"
                nut_bcs += f"\\n    {name} {{ type calculated; value uniform {turb_nut}; }}"
            elif btype == 'outlet':
                u_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                p_bcs += f"\\n    {name} {{ type fixedValue; value uniform 0; }}"
                k_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                eps_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                omega_bcs += f"\\n    {name} {{ type zeroGradient; }}"
                nut_bcs += f"\\n    {name} {{ type calculated; value uniform {turb_nut}; }}"
            elif btype == 'symmetry':
                sym = f"\\n    {name} {{ type symmetry; }}"
                u_bcs += sym
                p_bcs += sym
                k_bcs += sym
                eps_bcs += sym
                omega_bcs += sym
                nut_bcs += sym
                
    # Fix the curly braces formatting for u_bcs string literal mapping
    u_bcs = u_bcs.replace("{ {", "{{").replace("} }", "}}")

    HEADER="""

# Need to replace the old block for U
old_u_block = '''boundaryField
{
    "mesh.*"
    {
        type            noSlip;
    }
    "inlet"
    {
        type            fixedValue;
        value           $internalField;
    }
    "outlet"
    {
        type            zeroGradient;
    }
    "sides"
    {
        type            symmetry;
    }
}'''
text = text.replace(old_u_block, 'boundaryField\\n{'+'{u_bcs}'+'\\n}')

old_p_block = '''boundaryField
{
    "mesh.*"
    {
        type            zeroGradient;
    }
    "inlet"
    {
        type            zeroGradient;
    }
    "outlet"
    {
        type            fixedValue;
        value           uniform 0;
    }
    "sides"
    {
        type            symmetry;
    }
}'''
text = text.replace(old_p_block, 'boundaryField\\n{'+'{p_bcs}'+'\\n}')


# For turbulence files we replace the static fields:
k_old = '''boundaryField
{
    "mesh.*" { type kqRWallFunction; value uniform {turb_k}; }
    "inlet" { type fixedValue; value uniform {turb_k}; }
    "outlet" { type zeroGradient; }
    "sides" { type symmetry; }
}'''
text = text.replace(k_old, 'boundaryField\\n{'+'{k_bcs}'+'\\n}')

eps_old = '''boundaryField
{
    "mesh.*" { type epsilonWallFunction; value uniform {turb_epsilon}; }
    "inlet" { type fixedValue; value uniform {turb_epsilon}; }
    "outlet" { type zeroGradient; }
    "sides" { type symmetry; }
}'''
text = text.replace(eps_old, 'boundaryField\\n{'+'{eps_bcs}'+'\\n}')

o_old = '''boundaryField
{
    "mesh.*" { type omegaWallFunction; value uniform {turb_omega}; }
    "inlet" { type fixedValue; value uniform {turb_omega}; }
    "outlet" { type zeroGradient; }
    "sides" { type symmetry; }
}'''
text = text.replace(o_old, 'boundaryField\\n{'+'{omega_bcs}'+'\\n}')

n_old = '''boundaryField
{
    "mesh.*" { type nutkWallFunction; value uniform {turb_nut}; }
    "inlet" { type calculated; value uniform {turb_nut}; }
    "outlet" { type calculated; value uniform {turb_nut}; }
    "sides" { type symmetry; }
}'''
text = text.replace(n_old, 'boundaryField\\n{'+'{nut_bcs}'+'\\n}')

text = text.replace('    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\\', new_patch_logic + '    HEADER = r"""/*--------------------------------*- C++ -*----------------------------------*\\')

# Next, inside create_case_structure

old_meshdict = '''    MESH_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      meshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

surfaceFile "{stl_name}";

maxCellSize {cell_size};

boundaryCellSize
{{
    "{stl_name.replace('.stl', '')}.*"
    {{
        cellSize {cell_size};
    }}
}}

boundaryLayers
{{
    patchBoundaryLayers
    {{
        "{stl_name.replace('.stl', '')}.*"
        {{
            nLayers {boundary_layers};
            thicknessRatio {thickness_ratio};
            maxFirstLayerThickness {float(cell_size) * 0.5};
        }}
    }}
}}

localRefinement
{{
    "{stl_name.replace('.stl', '')}.*"
    {{
        cellSize {cell_size * 0.5};
    }}
}}
"""'''

new_meshdict = '''
    boundary_cell_size_str = ""
    patch_boundary_layers_str = ""
    local_refinement_str = ""
    
    if not boundary_patches or len(boundary_patches) == 0:
        base_name = f'"{stl_name.replace(".stl", "")}.*"'
        boundary_cell_size_str = f"\\n    {base_name}\\n    {{\\n        cellSize {cell_size};\\n    }}"
        patch_boundary_layers_str = f"\\n        {base_name}\\n        {{\\n            nLayers {boundary_layers};\\n            thicknessRatio {thickness_ratio};\\n            maxFirstLayerThickness {float(cell_size) * 0.5};\\n        }}"
        local_refinement_str = f"\\n    {base_name}\\n    {{\\n        cellSize {cell_size * 0.5};\\n    }}"
    else:
        for p in boundary_patches:
            name = f'"{p.name}.*"'
            csize = p.local_cell_size if p.use_local_cell_size else cell_size
            layers = p.boundary_layers
            
            boundary_cell_size_str += f"\\n    {name}\\n    {{\\n        cellSize {csize};\\n    }}"
            if layers > 0:
                patch_boundary_layers_str += f"\\n        {name}\\n        {{\\n            nLayers {layers};\\n            thicknessRatio {thickness_ratio};\\n            maxFirstLayerThickness {float(csize) * 0.5};\\n        }}"
            local_refinement_str += f"\\n    {name}\\n    {{\\n        cellSize {csize * 0.5};\\n    }}"

    MESH_DICT_TEMPLATE = f"""{HEADER}
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      meshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

surfaceFile "{stl_name}";

maxCellSize {cell_size};

boundaryCellSize
{{{boundary_cell_size_str}
}}

boundaryLayers
{{
    patchBoundaryLayers
    {{{patch_boundary_layers_str}
    }}
}}

localRefinement
{{{local_refinement_str}
}}
"""'''

text = text.replace(old_meshdict, new_meshdict)

with open(utils_path, 'w') as f:
    f.write(text)

