"""Quick look at raw retargets (no cleanup beyond fingers): front + side strips.

  blender -b --python preview.py -- <out_dir> <map>:<glb rel path>:<anim>[:frames] ...
  blender -b --python preview.py -- <out_dir> cmu:<amc id>:<t0>:<t1>[:yaw_deg] ...
  blender -b --python preview.py -- <out_dir> refpose:<map>:<glb or amc>   (target in source rest)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_anim as LA  # noqa: E402
import lib_stage as LS  # noqa: E402
import maps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = argv[0]
if len(argv) == 2 and argv[1].startswith("@"):  # one spec per line in a file
    argv = [out_dir] + [ln.strip() for ln in open(argv[1][1:]) if ln.strip() and not ln.startswith("#")]
rig, body, _ = LA.build_canonical()
rest = LA.rest_info(rig)
fingers = LA.relaxed_fingers(rest)
LS.setup_scene(samples=12)
crowd = LS.Crowd(rig, body, 16)


def load(spec):
    """-> (map, src, t0, t1, yaw, nframes)"""
    parts = spec.split(":")
    if parts[0] == "cmu":
        src = LA.AmcSource(os.path.join(LA.DL, "cmu", parts[1].split("_")[0] + ".asf"), os.path.join(LA.DL, "cmu", parts[1] + ".amc"))
        t0, t1 = float(parts[2]), min(float(parts[3]), src.duration)
        y = parts[4] if len(parts) > 4 else "auto"
        if y == "auto":
            yaw = -LA.heading(src, "root", t0, t1)
        elif y == "travel":
            yaw = -LA.travel_heading(src, "root", t0, t1)
        else:
            yaw = math.radians(float(y))
        nf = int(parts[5]) if len(parts) > 5 else 8
        return "cmu", src, t0, t1, yaw, nf
    src = LA.GltfSource(os.path.join(LA.DL, parts[1]), parts[2])
    nf = int(parts[3]) if len(parts) > 3 else 8
    return parts[0], src, src.t0, src.t1, 0.0, nf


for spec in argv[1:]:
    if spec.startswith("refpose:"):
        _, mname, rel = spec.split(":", 2)
        if mname == "cmu":
            src = LA.AmcSource(os.path.join(LA.DL, "cmu", rel.split("_")[0] + ".asf"), os.path.join(LA.DL, "cmu", rel + ".amc"))
        else:
            path, anim = rel.split("@")
            src = LA.GltfSource(os.path.join(LA.DL, path), anim)
        bmap = maps.MAPS[mname]
        # a clip of one frame = the source rest -> our rig in the source's rest posture
        src_rest = src.rest()

        class RestOnly:
            label = "rest"

            def rest(self):
                return src_rest

            def sample(self, t):
                return src_rest

        hip = src_rest[bmap["pelvis"]["src"]][0]
        clip = LA.retarget(RestOnly(), bmap, rest, 0, 1, "ref", frames=1, finger_pose=fingers,
                           hip_ref=hip, k_hip=1.0)
        tag = "refpose_" + mname
        LS.render_strip(crowd, clip, [0], os.path.join(out_dir, tag + "_front.png"), "front", tile_w=420)
        LS.render_strip(crowd, clip, [0], os.path.join(out_dir, tag + "_side.png"), "side", tile_w=420)
        continue
    mname, src, t0, t1, yaw, nf = load(spec)
    bmap = maps.MAPS[mname]
    hip = None
    if mname == "cmu":
        r0 = LA.yaw_matrix(yaw) @ src.sample(t0)["root"][0]
        hip = LA.yaw_matrix(yaw).inverted() @ LA.Vector((r0.x, r0.y, 0.93))
    clip = LA.retarget(src, bmap, rest, t0, t1, "pv", yaw=yaw, finger_pose=fingers, hip_ref=hip,
                       k_hip=1.07 if mname == "cmu" else None)
    LA.remove_root_motion(clip, rest)
    LA.ground_offset(rest, clip, "min")
    n = clip.n
    frames = [round(i * n / nf) for i in range(nf)]
    print("FRAMES", spec, [round(t0 + (t1 - t0) * f / n, 2) for f in frames])
    tag = spec.replace("/", "_").replace(":", "_").replace(".glb", "")
    print("CLIP", tag, "frames", n + 1, "loop err", LA.loop_error_deg(clip), "max step", LA.max_step_deg(clip),
          "feet", LA.foot_metrics(rest, clip))
    LS.render_strip(crowd, clip, frames, os.path.join(out_dir, tag + "_front.png"), "front", tile_w=220, tile_h=420)
    LS.render_strip(crowd, clip, frames, os.path.join(out_dir, tag + "_side.png"), "side", tile_w=220, tile_h=420)
