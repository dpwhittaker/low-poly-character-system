"""P6 step 1: retarget every job in jobs.py onto the canonical game_engine rest, clean up, measure.

  ~/opt/blender-5.2.2-linux-x64/blender -b --python pipeline/blender/m1_anim/10_retarget.py -- [--only idle,walk] [--source cmu]

Writes _work/clips/<clip>__<source>.json (clip data + metrics), _work/metrics.json, and the
committed canonical_rest.json. Deterministic: same downloads -> same output.
"""
import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jobs  # noqa: E402
import lib_anim as LA  # noqa: E402
import maps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
only = set()
only_src = set()
for k, a in enumerate(argv):
    if a == "--only":
        only = set(argv[k + 1].split(","))
    if a == "--source":
        only_src = set(argv[k + 1].split(","))

OUT = os.path.join(LA.WORK, "clips")
os.makedirs(OUT, exist_ok=True)

rig, body, _ = LA.build_canonical()
rest = LA.rest_info(rig)
FINGERS = LA.relaxed_fingers(rest)
TGT_LEG = (rest["calf_l"]["head"] - rest["thigh_l"]["head"]).length + (rest["foot_l"]["head"] - rest["calf_l"]["head"]).length
with open(os.path.join(HERE, "canonical_rest.json"), "w") as f:
    json.dump({"rig": "MPFB 2.0.18 game_engine on the MakeHuman default body (create_human defaults, scale 0.1, feet on ground)",
               "space": "Blender armature space: +Z up, character faces -Y, left = +X; metres",
               "hip_height_m": round(rest["pelvis"]["head"].z, 5), "leg_length_m": round(TGT_LEG, 5),
               "bones": LA.rest_json(rig)}, f, indent=1)


def load_src(job):
    if job["src"][0] == "glb":
        _, rel, anim = job["src"]
        return LA.GltfSource(os.path.join(LA.DL, rel), anim, label="%s:%s" % (os.path.basename(rel), anim),
                             wrap=job.get("wrap", False))
    trial = job["src"][1]
    subj = trial.split("_")[0]
    return LA.AmcSource(os.path.join(LA.DL, "cmu", subj + ".asf"), os.path.join(LA.DL, "cmu", trial + ".amc"),
                        label="CMU %s" % trial)


def map_name(job):
    return "cmu" if job["src"][0] == "cmu" else ("kaykit" if "kaykit" in job["src"][1] else "m2m")


def last(clip, frac=0.2):
    k = max(1, int(round((clip.n + 1) * frac)))
    return list(range(clip.n + 1 - k, clip.n + 1))


def apply_clean(clip, ops, log):
    for op in ops:
        if op == "inplace":
            tr = LA.remove_root_motion(clip, rest)
            log["removed_travel_m"] = round(tr.length, 4)
        elif op == "anchor_feet":
            LA.anchor_feet(rest, clip)
        elif op == "anchor_feet_end":
            LA.anchor_feet(rest, clip, last(clip))
        elif op == "level_head":
            log["level_head_deg"] = LA.level_head(rest, clip)
        elif op == "level_head_end":
            log["level_head_deg"] = LA.level_head(rest, clip, last(clip))
        elif op.startswith("damp_head"):
            keep = float(op.split(":")[1]) if ":" in op else 0.25
            LA.damp_bones(clip, ["neck_01", "head"], keep)
        elif op == "smooth_hands":
            LA.smooth_bones(clip, ["hand_l", "hand_r"], passes=2)
        elif op == "flatten":
            log["flatten_deg"] = LA.flatten_feet(rest, clip)
        elif op == "flatten_stance":
            log["flatten_deg"] = LA.flatten_feet(rest, clip, LA.stance_frames(rest, clip))
        elif op == "pin_feet":
            LA.pin_feet(rest, clip)
        elif op == "pin_rest":
            LA.pin_feet(rest, clip, targets={s: (rest["foot_" + s]["head"].copy(), rest["foot_" + s]["R"].copy())
                                             for s in ("l", "r")})
        elif op.startswith("pin_to:"):
            # feet held where the hand-over clip (already built) has them on its first frame
            other = LA.clip_from_json(json.load(open(os.path.join(OUT, op.split(":")[1] + ".json"))))
            w0 = LA.fk(rest, other, 0)
            LA.pin_feet(rest, clip, targets={s: (w0["foot_" + s].translation.copy(), w0["foot_" + s].to_3x3().normalized())
                                             for s in ("l", "r")})
        elif op.startswith("blend_end_to:"):
            # last k frames ease into the hand-over clip's first frame (exact match on the last frame)
            _, key, k = op.split(":")
            other = LA.clip_from_json(json.load(open(os.path.join(OUT, key + ".json"))))
            k = int(k)
            for j in range(k + 1):
                i = clip.n - k + j
                u = j / k
                u = u * u * (3 - 2 * u)
                for b in LA.BONES:
                    clip.q[b][i] = LA.qslerp(clip.q[b][i], other.q[b][0], u)
                clip.pelvis[i] = clip.pelvis[i].lerp(other.pelvis[0], u)
            LA.fix_signs(clip)
        elif op == "pin_under":
            # hip-width stance (rest spacing) centred under the clip-mean pelvis, rest foot angles
            mp = Vector((0, 0, 0))
            for p in clip.pelvis:
                mp += p
            mp /= len(clip.pelvis)
            off = Vector((mp.x - rest["pelvis"]["head"].x, mp.y - rest["pelvis"]["head"].y, 0))
            LA.pin_feet(rest, clip, targets={s: (rest["foot_" + s]["head"] + off, rest["foot_" + s]["R"].copy())
                                             for s in ("l", "r")})
        elif op.startswith("arms_fwd"):
            log["arms_fwd_deg"] = float(op.split(":")[1])
            LA.swing_bones_world(rest, clip, ["upperarm_l", "upperarm_r"], Vector((1, 0, 0)), -log["arms_fwd_deg"])
        elif op == "plant_feet":
            log["plant_feet_dz_m"] = LA.plant_feet(rest, clip)
        elif op == "toe_floor":
            log["toe_floor"] = LA.toe_floor(rest, clip)
        elif op == "ground_min_hb":
            LA.ground_offset(rest, clip, "min_hb")
        elif op == "ground_min":
            LA.ground_offset(rest, clip, "min")
        elif op == "ground_mean":
            LA.ground_offset(rest, clip, "planted")
        elif op == "close_loop":
            LA.close_loop(clip)
        else:
            raise ValueError(op)


def pose_rig(clip, i):
    for b in LA.BONES:
        pb = rig.pose.bones[b]
        pb.rotation_quaternion = clip.q[b][i]
        pb.location = (0, 0, 0)
    rig.pose.bones["pelvis"].location = rest["pelvis"]["R"].inverted() @ (clip.pelvis[i] - rest["pelvis"]["head"])


GROUPS = {g.name: g.index for g in body.vertex_groups}


def seat_metrics(clip):
    """Seat surface height under the neutral body: lowest point of the thigh/buttock underside
    behind the knees, on the skinned MakeHuman default body (mid-clip frame)."""
    i = clip.n // 2
    pose_rig(clip, i)
    mask = body.modifiers.get("Hide helpers")
    if mask:
        mask.show_viewport = False
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    want = {GROUPS[n] for n in ("thigh_l", "thigh_r", "pelvis") if n in GROUPS}
    in_body = GROUPS["body"]
    w = LA.fk(rest, clip, i)
    knee_y = (w["calf_l"].translation.y + w["calf_r"].translation.y) / 2
    hip_y = (w["thigh_l"].translation.y + w["thigh_r"].translation.y) / 2
    pts = []
    for v in body.data.vertices:
        gs = {g.group: g.weight for g in v.groups}
        if in_body not in gs:
            continue
        if sum(gs.get(g, 0.0) for g in want) < 0.5:
            continue
        co = ev.matrix_world @ me.vertices[v.index].co
        if co.y > knee_y + 0.12:
            pts.append(co)
    ev.to_mesh_clear()
    if mask:
        mask.show_viewport = True
    seat = min(p.z for p in pts)
    contact = [p for p in pts if p.z < seat + 0.01]
    return {"seat_height_m": round(seat, 4), "pelvis_height_m": round(clip.pelvis[i].z, 4),
            "seat_contact_y_m": [round(min(p.y for p in contact), 3), round(max(p.y for p in contact), 3)],
            "hip_joint_y_m": round(hip_y, 3), "knee_y_m": round(knee_y, 3), "frame": i}


results = {}
mpath = os.path.join(LA.WORK, "metrics.json")
if os.path.exists(mpath):
    results = json.load(open(mpath))
for job in jobs.JOBS:
    if only and job["clip"] not in only:
        continue
    if only_src and job["source"] not in only_src:
        continue
    t_start = time.time()
    mname = map_name(job)
    bmap = maps.MAPS[mname]
    if mname == "cmu":
        bmap = {k: v for k, v in bmap.items() if not k.startswith("ball_")}  # CMU toes are noise
    src = load_src(job)
    root = bmap["pelvis"]["src"]
    win = job.get("window")
    log = {"source_label": src.label, "map": mname, "kind": job["kind"], "clean": job["clean"]}
    if win is None:
        t0, t1 = src.t0, src.t1
    elif win[0] == "find":
        step = 1.0 / getattr(src, "fps", 60.0)
        err, t0, t1 = LA.find_loop(src, maps.LOOP_JOINTS[mname], win[1], win[2], win[3], win[4], step=step)
        log["loop_search_err"] = round(err, 4)
    else:
        t0, t1 = win
    y = job.get("yaw", "none")
    if y == "none":
        yaw = 0.0
    elif y == "auto":
        yaw = -LA.heading(src, root, t0, t1)
    elif y == "travel":
        yaw = -LA.travel_heading(src, root, t0, t1)
    elif y == "end":
        yaw = -LA.heading(src, root, t0 + 0.8 * (t1 - t0), t1)
    else:
        yaw = math.radians(float(y))
    k_hip = TGT_LEG / maps.leg_length(mname, src)
    hip_ref = None
    if mname == "cmu":
        Y = LA.yaw_matrix(yaw)
        r0 = Y @ src.sample(t0)[root][0]
        hip_ref = Y.inverted() @ Vector((r0.x, r0.y, maps.leg_length(mname, src) + 0.07))
    clip = LA.retarget(src, bmap, rest, t0, t1, job["clip"], yaw=yaw, k_hip=k_hip, hip_ref=hip_ref,
                       loop=job["kind"] == "loop", finger_pose=FINGERS)
    log["raw_loop_err_deg"], log["raw_loop_err_pelvis_m"] = LA.loop_error_deg(clip)
    apply_clean(clip, job["clean"], log)
    le, lp = LA.loop_error_deg(clip)
    ms, mb = LA.max_step_deg(clip)
    log.update({"t0": round(t0, 4), "t1": round(t1, 4), "yaw_deg": round(math.degrees(yaw), 2), "k_hip": round(k_hip, 4),
                "frames": clip.n + 1, "duration_s": round(clip.n / LA.FPS, 4),
                "loop_err_deg": le, "loop_err_pelvis_m": lp, "max_step_deg": ms, "max_step_bone": mb,
                "feet": LA.foot_metrics(rest, clip)})
    log.update({k: v for k, v in clip.meta.items() if k.startswith("loop_fix") or k == "ground_dz_m"})
    if job["clip"] in ("walk", "run"):
        v, nst = LA.walk_speed(rest, clip)
        log["speed_mps"] = round(v, 4)
        log["stride_per_cycle_m"] = round(v * clip.n / LA.FPS, 4)
        log["stance_samples"] = nst
    if job["clip"] == "sit":
        log["seat"] = seat_metrics(clip)
    if job["clip"] == "sit_down":
        end = LA.Clip("end", 0)
        end.q = {b: [clip.q[b][clip.n]] for b in LA.BONES}
        end.pelvis = [clip.pelvis[clip.n]]
        log["seat_end"] = seat_metrics(end)
    log["seconds"] = round(time.time() - t_start, 1)
    key = "%s__%s" % (job["clip"], job["source"])
    clip.meta.update(log)
    with open(os.path.join(OUT, key + ".json"), "w") as f:
        json.dump(LA.clip_to_json(clip), f)
    results[key] = log
    print("JOB", key, json.dumps({k: log[k] for k in ("frames", "duration_s", "raw_loop_err_deg", "loop_fix_max_deg",
                                                      "max_step_deg", "max_step_bone", "feet") if k in log}))
    for k in ("speed_mps", "stride_per_cycle_m", "seat", "seat_end", "level_head_deg", "flatten_deg", "t0", "t1", "yaw_deg"):
        if k in log:
            print("    ", k, log[k])

# transition continuity: a one-shot's last frame vs the loop it hands over to (same source)
for a, b in (("sit_down", "sit"),):
    for src_key in {k.split("__")[1] for k in results if k.startswith(a + "__")}:
        pa = os.path.join(OUT, "%s__%s.json" % (a, src_key))
        pb = os.path.join(OUT, "%s__%s.json" % (b, src_key))
        if not (os.path.exists(pa) and os.path.exists(pb)):
            continue
        ca = LA.clip_from_json(json.load(open(pa)))
        cb = LA.clip_from_json(json.load(open(pb)))
        worst = max((LA.qangle_deg(ca.q[x][ca.n], cb.q[x][0]), x) for x in LA.BONES)
        results["%s__%s" % (a, src_key)]["handover_to_" + b] = {
            "max_bone_deg": round(worst[0], 2), "bone": worst[1],
            "pelvis_m": round((ca.pelvis[ca.n] - cb.pelvis[0]).length, 4)}
        print("HANDOVER", a, "->", b, src_key, results["%s__%s" % (a, src_key)]["handover_to_" + b])

with open(mpath, "w") as f:
    json.dump(results, f, indent=1, sort_keys=True)
print("WROTE", mpath, len(results))
