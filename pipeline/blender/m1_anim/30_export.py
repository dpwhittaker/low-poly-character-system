"""P6 step 4: export the winning clips as ONE GLB on the canonical game_engine armature.

  ~/opt/blender-5.2.2-linux-x64/blender -b --python pipeline/blender/m1_anim/30_export.py -- [--no-body]

-> public/m1/anim/clips.glb : armature (53 bones, rest = canonical rest) + the MakeHuman
   `female1605` proxy skinned to it (CC0, the T22 base-body candidate; omitted with --no-body)
   + one animation per clip. Channels: rotation for all 53 bones, translation for `pelvis` only
   (the runtime keeps per-body bone translations; see README "Pelvis translation").
-> public/m1/anim/clips.json : per-clip metadata (also stored as animation extras in the GLB).

Blender's exporter samples every bone's TRS; a post-pass drops the scale channels and every
translation channel except pelvis, re-packs the binary chunk, and verifies the GLB rest pose
against canonical_rest.json.
"""
import json
import math
import os
import struct
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jobs  # noqa: E402
import lib_anim as LA  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
WITH_BODY = "--no-body" not in argv
OUT_DIR = os.path.join(LA.REPO, "public", "m1", "anim")
OUT = os.path.join(OUT_DIR, "clips.glb")
os.makedirs(OUT_DIR, exist_ok=True)
ORDER = ["idle", "walk", "sit", "sit_down", "arms_up", "wave", "run", "crouch", "arms_crossed"]

rig, body, prox = LA.build_canonical(proxy="female1605" if WITH_BODY else None)
rest = LA.rest_info(rig)
metrics = json.load(open(os.path.join(LA.WORK, "metrics.json")))

# --- objects to export: rig (+ proxy) -------------------------------------------------------
bpy.data.objects.remove(body, do_unlink=True)
rig.name = rig.data.name = "game_engine"
if prox is not None:
    prox.name = prox.data.name = "body_female1605"
    prox.data.materials.clear()
    mat = bpy.data.materials.new("skin")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.70, 0.36, 0.21, 1.0)
    prox.data.materials.append(mat)
    for m in list(prox.modifiers):
        if m.type != "ARMATURE":
            prox.modifiers.remove(m)
    bpy.context.view_layer.objects.active = prox
    for o in bpy.context.view_layer.objects:
        o.select_set(o == prox)
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
    for uv in list(prox.data.uv_layers):
        prox.data.uv_layers.remove(uv)

# --- actions ---------------------------------------------------------------------------------
meta = {}
for name in ORDER:
    src = jobs.WINNERS.get(name)
    path = os.path.join(LA.WORK, "clips", "%s__%s.json" % (name, src))
    if not src or not os.path.exists(path):
        print("SKIP", name)
        continue
    clip = LA.clip_from_json(json.load(open(path)))
    clip.meta = {}  # keep the action clean; metadata goes to clips.json / glTF extras
    act = LA.write_action(rig, clip, name)
    m = metrics["%s__%s" % (name, src)]
    meta[name] = {k: m[k] for k in ("frames", "duration_s", "kind", "source_label", "loop_fix_max_deg",
                                    "max_step_deg", "stride_per_cycle_m", "speed_mps", "seat", "seat_end", "feet")
                  if k in m}
    meta[name]["loop"] = clip.loop
    meta[name]["source"] = src
    # FK reference for the Babylon check: joint heights (glTF +Y = Blender +Z) at two frames
    probe = {}
    for f in (0, clip.n // 2):
        w = LA.fk(rest, clip, f)
        probe[str(f)] = {b: round(w[b].translation.z, 5) for b in ("pelvis", "head", "hand_l", "hand_r", "ball_l", "ball_r")}
    meta[name]["probe_heights"] = probe
rig.animation_data.action = None
bpy.context.scene.render.fps = LA.FPS
bpy.context.scene.frame_start = 0

for o in bpy.context.view_layer.objects:
    o.select_set(o.name in ("game_engine", "body_female1605"))
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", use_selection=True,
    export_yup=True, export_apply=False, export_texcoords=False, export_normals=True,
    export_materials="EXPORT", export_morph=False, export_skins=True, export_influence_nb=4,
    export_def_bones=False, export_leaf_bone=False, export_rest_position_armature=True,
    export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
    export_frame_step=1, export_frame_range=False, export_anim_slide_to_zero=True,
    export_optimize_animation_size=False, export_optimize_animation_keep_anim_armature=True,
    export_reset_pose_bones=True, export_bake_animation=False, export_extras=False,
)

# --- post-process ----------------------------------------------------------------------------
data = open(OUT, "rb").read()
clen = struct.unpack_from("<I", data, 12)[0]
gl = json.loads(data[20:20 + clen])
off = 20 + clen
blen = struct.unpack_from("<I", data, off)[0]
binary = data[off + 8: off + 8 + blen]
names = {i: n.get("name") for i, n in enumerate(gl["nodes"])}
dropped = 0
for a in gl.get("animations", []):
    keep_ch, keep_s, remap = [], [], {}
    for ch in a["channels"]:
        node = names[ch["target"]["node"]]
        p = ch["target"]["path"]
        if p == "rotation" or (p == "translation" and node == "pelvis"):
            si = ch["sampler"]
            if si not in remap:
                remap[si] = len(keep_s)
                keep_s.append(a["samplers"][si])
            ch["sampler"] = remap[si]
            keep_ch.append(ch)
        else:
            dropped += 1
    a["channels"], a["samplers"] = keep_ch, keep_s
    if a["name"] in meta:
        a["extras"] = meta[a["name"]]
# re-pack: keep only referenced accessors / bufferViews
used_acc = set()
for m in gl.get("meshes", []):
    for p in m["primitives"]:
        used_acc.update(p["attributes"].values())
        if "indices" in p:
            used_acc.add(p["indices"])
for s in gl.get("skins", []):
    if "inverseBindMatrices" in s:
        used_acc.add(s["inverseBindMatrices"])
for a in gl.get("animations", []):
    for s in a["samplers"]:
        used_acc.update((s["input"], s["output"]))
acc_map, new_acc = {}, []
for i, acc in enumerate(gl["accessors"]):
    if i in used_acc:
        acc_map[i] = len(new_acc)
        new_acc.append(acc)
bv_map, new_bv, chunks, pos = {}, [], [], 0
for acc in new_acc:
    bi = acc["bufferView"]
    if bi not in bv_map:
        bv = dict(gl["bufferViews"][bi])
        raw = binary[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        pad = (-pos) % 4
        chunks.append(b"\0" * pad)
        pos += pad
        bv["byteOffset"] = pos
        chunks.append(raw)
        pos += len(raw)
        bv_map[bi] = len(new_bv)
        new_bv.append(bv)
    acc["bufferView"] = bv_map[bi]
gl["accessors"], gl["bufferViews"] = new_acc, new_bv
for m in gl.get("meshes", []):
    for p in m["primitives"]:
        p["attributes"] = {k: acc_map[v] for k, v in p["attributes"].items()}
        if "indices" in p:
            p["indices"] = acc_map[p["indices"]]
for s in gl.get("skins", []):
    if "inverseBindMatrices" in s:
        s["inverseBindMatrices"] = acc_map[s["inverseBindMatrices"]]
for a in gl.get("animations", []):
    for s in a["samplers"]:
        s["input"], s["output"] = acc_map[s["input"]], acc_map[s["output"]]
new_bin = b"".join(chunks)
new_bin += b"\0" * ((-len(new_bin)) % 4)
gl["buffers"] = [{"byteLength": len(new_bin)}]
gl.setdefault("asset", {})["extras"] = {
    "p6": "M1 probe P6 clips; rest = MPFB 2.0.18 game_engine on the MakeHuman default body",
    "fps": LA.FPS, "hip_height_m": round(rest["pelvis"]["head"].z, 5),
    "pelvis_rest_translation": None,  # filled below
}

# rest check: GLB joint TRS vs canonical rest. Child joints are stored in their parent bone's
# frame exactly as in Blender; the parent-less Root joint carries the Z-up -> Y-up conversion:
# rotation = Rx(-90 deg) . R_canon, translation swizzled (x, y, z) -> (x, z, -y).
canon = {r["name"]: r for r in json.load(open(os.path.join(HERE, "canonical_rest.json")))["bones"]}
QC = LA.Quaternion((math.sqrt(0.5), -math.sqrt(0.5), 0.0, 0.0))
max_rot = max_tr = 0.0
for n in gl["nodes"]:
    nm = n.get("name")
    if nm not in canon:
        continue
    qc = LA.Quaternion(canon[nm]["local_rotation_wxyz"])
    tx, ty, tz = canon[nm]["local_translation"]
    if canon[nm]["parent"] is None:
        qc = QC @ qc
        exp_t = (tx, tz, -ty)
    else:
        exp_t = (tx, ty, tz)
    exp_q = (qc.x, qc.y, qc.z, qc.w)
    q = n.get("rotation", [0, 0, 0, 1])
    t = n.get("translation", [0, 0, 0])
    qa = LA.Quaternion((q[3], q[0], q[1], q[2])).normalized()
    qd = LA.Quaternion((exp_q[3], exp_q[0], exp_q[1], exp_q[2])).normalized().conjugated() @ qa
    max_rot = max(max_rot, math.degrees(2 * math.atan2(math.sqrt(qd.x ** 2 + qd.y ** 2 + qd.z ** 2), abs(qd.w))))  # acos(w) is ill-conditioned
    max_tr = max(max_tr, max(abs(a - b) for a, b in zip(t, exp_t)))
    if nm == "pelvis":
        gl["asset"]["extras"]["pelvis_rest_translation"] = [round(v, 6) for v in t]
print("REST CHECK: max joint rotation diff %.4f deg, max translation diff %.6f m" % (max_rot, max_tr))

js = json.dumps(gl, separators=(",", ":")).encode()
js += b" " * ((-len(js)) % 4)
total = 12 + 8 + len(js) + 8 + len(new_bin)
with open(OUT, "wb") as f:
    f.write(struct.pack("<III", 0x46546C67, 2, total))
    f.write(struct.pack("<II", len(js), 0x4E4F534A))
    f.write(js)
    f.write(struct.pack("<II", len(new_bin), 0x004E4942))
    f.write(new_bin)
meta_out = {"fps": LA.FPS, "hip_height_m": round(rest["pelvis"]["head"].z, 5),
            "leg_length_m": round((rest["calf_l"]["head"] - rest["thigh_l"]["head"]).length
                                  + (rest["foot_l"]["head"] - rest["calf_l"]["head"]).length, 5),
            "pelvis_rest_translation_gltf": gl["asset"]["extras"]["pelvis_rest_translation"],
            "rest_check": {"max_rot_deg": round(max_rot, 5), "max_translation_m": round(max_tr, 7)},
            "clips": meta}
json.dump(meta_out, open(os.path.join(OUT_DIR, "clips.json"), "w"), indent=1)
anims = [(a["name"], len(a["channels"])) for a in gl["animations"]]
print("EXPORTED", OUT, os.path.getsize(OUT), "bytes; dropped channels", dropped, "; animations", anims)
