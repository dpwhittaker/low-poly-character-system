"""M1 step 2: the canonical skeleton → public/m1/skeleton.glb + pipeline/build/m1/skeleton.json.

MPFB's `game_engine` rig (53 bones, Unreal-mannequin names) fitted to the MakeHuman
DEFAULT body (all macros 0.5), plus seven bones the plan needs (PLAN §5.4, SPEC T23):
  jaw                   head at joint-mouth, tail at joint-jaw (MakeHuman's default rig jaw)
  eye_l, eye_r          head at the eye joint, tail at the eye-target joint (gaze)
  upperarm_twist_01_*   on the upper arm at 0.5 → elbow (against shoulder candy-wrap)
  lowerarm_twist_01_*   on the forearm at 0.75 → hand (against wrist candy-wrap)

The REST ROTATIONS of this armature are canonical for every body: the runtime keeps them
and moves only bone heads (joint-cube centroids per body), so rotation-only clips
authored on this rest play on any proportions. Animation clips (probe P6) are retargeted
onto the same MPFB default-body rig, so their rest matches bone for bone.

skeleton.json lists, per bone: name, parent, how its head is computed per body
(`joint` = a joint-cube name, or `lerp` = [a, b, t] between two joint cubes), and roll.
"""
import json
import os

import bpy
from mathutils import Vector

from bl_ext.user_default.mpfb.services.humanservice import HumanService

OUT_GLB = "/home/david/projects/low-poly-character-system/public/m1/skeleton.glb"
OUT_JSON = "/home/david/projects/low-poly-character-system/pipeline/build/m1/skeleton.json"
RIG_JSON = os.path.expanduser("~/.config/blender/5.2/extensions/user_default/mpfb/data/rigs/standard/rig.game_engine.json")

os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
base = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                                 feet_on_ground=True, scale=0.1)
arm = HumanService.add_builtin_rig(base, "game_engine", import_weights=False)
arm.name = arm.data.name = "Skeleton"
rig = json.load(open(RIG_JSON))

# joint-cube centroids of the default body (shape keys mixed), for the extra bones
me = base.data
kb = me.shape_keys.key_blocks
gidx = {g.index: g.name for g in base.vertex_groups}
pos = {}
for v in me.vertices:
    co = kb[0].data[v.index].co.copy()
    for k in kb[1:]:
        co += k.value * (k.data[v.index].co - kb[0].data[v.index].co)
    for e in v.groups:
        nm = gidx[e.group]
        if nm.startswith("joint-"):
            pos.setdefault(nm, []).append(co)
cube = {nm: sum(vs, Vector()) / len(vs) for nm, vs in pos.items()}

bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
heads = {nm: {"joint": rig[nm]["head"]["cube_name"]} for nm in rig}


def add_bone(name, parent, head, tail, roll_from=None, roll=0.0):
    b = eb.new(name)
    b.head, b.tail = head, tail
    b.parent = eb[parent]
    b.use_connect = False
    if roll_from is not None:
        b.align_roll(eb[roll_from].z_axis)
    else:
        b.roll = roll
    return b


add_bone("jaw", "head", cube["joint-mouth"], cube["joint-jaw"])
heads["jaw"] = {"joint": "joint-mouth"}
for s in ("l", "r"):
    add_bone("eye_" + s, "head", cube["joint-%s-eye" % s], cube["joint-%s-eye-target" % s])
    heads["eye_" + s] = {"joint": "joint-%s-eye" % s}
    sh, el, ha = cube["joint-%s-shoulder" % s], cube["joint-%s-elbow" % s], cube["joint-%s-hand" % s]
    add_bone("upperarm_twist_01_" + s, "upperarm_" + s, sh.lerp(el, 0.5), el, roll_from="upperarm_" + s)
    heads["upperarm_twist_01_" + s] = {"lerp": ["joint-%s-shoulder" % s, "joint-%s-elbow" % s, 0.5]}
    add_bone("lowerarm_twist_01_" + s, "lowerarm_" + s, el.lerp(ha, 0.75), ha, roll_from="lowerarm_" + s)
    heads["lowerarm_twist_01_" + s] = {"lerp": ["joint-%s-elbow" % s, "joint-%s-hand" % s, 0.75]}

bones = []
for b in eb:
    bones.append({"name": b.name, "parent": b.parent.name if b.parent else None, "head": heads[b.name],
                  "roll": b.roll, "rest_head": list(b.head), "rest_tail": list(b.tail)})
bpy.ops.object.mode_set(mode="OBJECT")

# export the armature alone (no mesh): rest pose only, Y-up like every other GLB here
bpy.data.objects.remove(base, do_unlink=True)
for o in list(bpy.data.objects):
    if o is not None and o.name in bpy.context.view_layer.objects:
        o.select_set(o == arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB", use_selection=True, export_yup=True,
                          export_animations=False, export_skins=True, export_morph=False, export_materials="NONE")
json.dump({"bones": bones}, open(OUT_JSON, "w"), indent=1)
result = {"bones": len(bones), "glb_bytes": os.path.getsize(OUT_GLB),
          "extra": [b["name"] for b in bones if b["name"] not in rig]}
