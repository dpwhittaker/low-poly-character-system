"""M0.1 step 1: build the high-res *source* test character from MakeHuman CC0 data.

The result is reference anatomy only, not a game asset. Step 02 derives the low-poly
style variants from it. Run inside the persistent Blender:

    tools/blender-exec.py pipeline/blender/m0_style/01_source_human.py

It is idempotent: it wipes the scene and rebuilds. Character: a teen girl (the core
audience), ~16 years old by MakeHuman's age mapping (0 = 1 y, 0.1875 = 11 y, 0.5 = 25 y,
1 = 90 y). Ponytail, natural brows, casual clothes, sneakers. All assets are from
the MakeHuman system pack (CC0).
"""
import os
import bpy

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

AGE_16 = 0.1875 + (16 - 11) / (25 - 11) * (0.5 - 0.1875)
# MakeHuman interpolates linearly between its 11 y and 25 y models, so AGE_16 (0.30)
# gives a 1.37 m, child-proportioned body ("petite reads as a child" was a real bug
# before). Teens are near adult height, so the teen look uses near-adult proportions
# (MakeHuman ~21 y); youthfulness comes from the face and the styling.
TEEN_LOOK = 0.42

MACROS = {
    "gender": 0.0, "age": TEEN_LOOK, "muscle": 0.5, "weight": 0.47, "proportions": 0.65,
    "height": 0.62, "cupsize": 0.42, "firmness": 0.5,
    "race": {"asian": 0.2, "caucasian": 0.45, "african": 0.35},
}

# Stylization toward the approved reference: a slightly big, round head; a younger,
# fuller, friendlier face; bigger eyes; a hint of a smile; a small upturned nose. Raw
# MakeHuman realism, decimated, read stern and gaunt (first S1 render, 2026-10-12).
# Values are target weights; L/R targets are applied symmetrically.
STYLE_TARGETS = {
    "head/head-age-decr": 0.45, "head/head-round": 0.3, "head/head-fat-incr": 0.2,
    "head/head-scale-vert-incr": 0.3, "head/head-scale-horiz-incr": 0.25, "head/head-scale-depth-incr": 0.15,
    "cheek/{s}-cheek-volume-incr": 0.45, "cheek/{s}-cheek-bones-decr": 0.25,
    "eyes/{s}-eye-scale-incr": 0.4, "eyes/{s}-eye-bag-decr": 0.6, "eyes/{s}-eye-height2-incr": 0.25,
    "mouth/mouth-angles-up": 0.25, "mouth/mouth-scale-horiz-decr": 0.1, "mouth/mouth-scale-depth-decr": 0.25,
    "eyebrows/eyebrows-trans-up": 0.35, "eyebrows/eyebrows-angle-up": 0.6,  # kind, not scowling (angle-down made it worse)
    "chin/chin-prominent-decr": 0.25, "chin/chin-bones-decr": 0.2, "chin/chin-width-decr": 0.15,
    "nose/nose-scale-horiz-decr": 0.2, "nose/nose-point-up": 0.25, "nose/nose-volume-decr": 0.2,
}

ASSETS = [  # (relative mhclo path, asset_type)
    ("hair/ponytail01/ponytail01.mhclo", "Hair"),
    ("eyebrows/eyebrow005/eyebrow005.mhclo", "Eyebrows"),  # soft clean arch; 001 read heavy/angry
    ("eyes/low-poly/low-poly.mhclo", "Eyes"),
    ("clothes/female_casualsuit01/female_casualsuit01.mhclo", "Clothes"),
    ("clothes/shoes02/shoes02.mhclo", "Clothes"),
]


def wipe():
    # read_factory_settings is blocked by the MCP add-on (it would reset prefs and unload MPFB).
    bpy.ops.wm.read_homefile(use_empty=True)


wipe()
basemesh = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                                     feet_on_ground=True, scale=0.1, macro_detail_dict=MACROS)
basemesh.name = "SourceBody"
mpfb_targets = os.path.join(LocationService.get_mpfb_data(), "targets")
applied = 0
for rel, w in STYLE_TARGETS.items():
    for side in (("l", "r") if "{s}" in rel else ("",)):
        path = os.path.join(mpfb_targets, rel.format(s=side) + ".target.gz")
        if os.path.exists(path):
            TargetService.load_target(basemesh, path, weight=w)
            applied += 1
user_data = LocationService.get_user_data()
added = []
for rel, kind in ASSETS:
    path = os.path.join(user_data, rel)
    if not os.path.exists(path):
        added.append((rel, "MISSING"))
        continue
    ob = HumanService.add_mhclo_asset(path, basemesh, asset_type=kind, subdiv_levels=0, material_type="MAKESKIN",
                                      set_up_rigging=False)
    if ob is not None:
        ob.name = "Source_" + kind + "_" + os.path.basename(os.path.dirname(path))
    added.append((rel, ob.name if ob else None))

result = {
    "age_value": TEEN_LOOK,
    "style_targets_applied": applied,
    "basemesh_verts": len(basemesh.data.vertices),
    "basemesh_faces": len(basemesh.data.polygons),
    "shape_keys": len(basemesh.data.shape_keys.key_blocks) if basemesh.data.shape_keys else 0,
    "objects": [(o.name, o.type, len(o.data.polygons) if o.type == "MESH" else 0) for o in bpy.data.objects],
    "added": added,
    "dims": tuple(round(d, 3) for d in basemesh.dimensions),
}
