"""P6 step 2: render filmstrips (front + side) of retargeted clips on the skinned default body.

  gpu-lease run m1-anim -- blender -b --python pipeline/blender/m1_anim/20_render.py -- [--only idle,walk] [--source cmu] [--frames 8] [--tile 300x560]

Reads _work/clips/<clip>__<source>.json, writes _work/frames/<clip>__<source>_{front,side}.png and
a manifest (frame numbers + times). Loops sample [0, n) evenly; one-shots include the last frame.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib_anim as LA  # noqa: E402
import lib_stage as LS  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = {"--only": "", "--source": "", "--frames": "8", "--tile": "300x560", "--samples": "24", "--views": "front,side"}
for k, a in enumerate(argv):
    if a in opt:
        opt[a] = argv[k + 1]
only = set(filter(None, opt["--only"].split(",")))
only_src = set(filter(None, opt["--source"].split(",")))
nf = int(opt["--frames"])
tw, th = (int(v) for v in opt["--tile"].split("x"))
views = opt["--views"].split(",")

CLIPS = os.path.join(LA.WORK, "clips")
OUT = os.path.join(LA.WORK, "frames")
os.makedirs(OUT, exist_ok=True)

rig, body, _ = LA.build_canonical()
rest = LA.rest_info(rig)
LS.setup_scene(samples=int(opt["--samples"]))
crowd = LS.Crowd(rig, body, max(nf, 8))
mpath = os.path.join(OUT, "manifest.json")
manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
for fn in sorted(os.listdir(CLIPS)):
    key = fn[:-5]
    clip_name, source = key.split("__")
    if only and clip_name not in only:
        continue
    if only_src and source not in only_src:
        continue
    clip = LA.clip_from_json(json.load(open(os.path.join(CLIPS, fn))))
    n = clip.n
    if clip.loop:
        frames = [round(i * n / nf) for i in range(nf)]
    else:
        frames = [round(i * n / (nf - 1)) for i in range(nf)]
    # one framing per clip for every source (comparable sheets): stance + arms + head room
    lo, hi = LS.clip_bounds(rest, clip, frames)
    lo.x, hi.x = min(lo.x, -0.62), max(hi.x, 0.62)
    lo.y, hi.y = min(lo.y, -0.55), max(hi.y, 0.45)
    hi.z = max(hi.z, 1.85)
    for v in views:
        LS.render_strip(crowd, clip, frames, os.path.join(OUT, "%s_%s.png" % (key, v)), v, tile_w=tw, tile_h=th,
                        bounds=(lo, hi))
    manifest[key] = {"frames": frames, "times": [round(f / LA.FPS, 3) for f in frames], "n": n, "loop": clip.loop}
    json.dump(manifest, open(mpath, "w"), indent=1)
    print("RENDERED", key, frames)
