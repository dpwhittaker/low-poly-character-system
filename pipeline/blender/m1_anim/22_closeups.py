"""P6 detail renders: hands (finger curl, wrist twist) and feet (floor contact) close up.

  gpu-lease run m1-anim -- blender -b --python pipeline/blender/m1_anim/22_closeups.py -- <clip>__<source>:<frame> ...

Writes _work/frames/closeup_<key>_<frame>.png: 4 panels (right hand front/side, left foot side,
whole body 3/4) of one frame.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lib_anim as LA  # noqa: E402
import lib_stage as LS  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
rig, body, _ = LA.build_canonical()
rest = LA.rest_info(rig)
scene = LS.setup_scene(samples=32)
crowd = LS.Crowd(rig, body, 1)
cam = bpy.data.objects.new("CloseCam", bpy.data.cameras.new("CloseCam"))
scene.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.clip_end = 100
scene.camera = cam
OUT = os.path.join(LA.WORK, "frames")


def shot(center, view, scale, path, res=420):
    a = {"front": 0.0, "side": 90.0, "back": 180.0, "tq": 35.0, "rside": -90.0}[view]
    r = math.radians(a)
    cam.location = center + Vector((math.sin(r) * 20, -math.cos(r) * 20, 0))
    cam.rotation_euler = (math.radians(90), 0, r)
    cam.data.ortho_scale = scale
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


for spec in argv:
    key, frame = spec.rsplit(":", 1)
    frame = int(frame)
    clip = LA.clip_from_json(json.load(open(os.path.join(LA.WORK, "clips", key + ".json"))))
    crowd.pose(0, clip, frame, Vector((0, 0, 0)))
    bpy.context.view_layer.update()
    w = LA.fk(rest, clip, frame)
    hand = w["middle_01_r"].translation
    foot = (w["foot_l"].translation + w["ball_l"].translation) / 2
    paths = [
        shot(hand, "front", 0.32, os.path.join(OUT, "_c1.png")),
        shot(hand, "rside", 0.32, os.path.join(OUT, "_c2.png")),
        shot(Vector((foot.x, foot.y, 0.08)), "side", 0.36, os.path.join(OUT, "_c3.png")),
        shot(Vector((0, -0.05, 0.9)), "tq", 2.1, os.path.join(OUT, "_c4.png")),
    ]
    # stitch 4 panels with Blender's image API (no PIL inside Blender)
    import numpy as np
    tiles = []
    for p in paths:
        im = bpy.data.images.load(p)
        px = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        tiles.append(px)
        bpy.data.images.remove(im)
    row = np.concatenate(tiles, axis=1)
    out = bpy.data.images.new("closeup", row.shape[1], row.shape[0], alpha=True)
    out.pixels = row.ravel()
    dst = os.path.join(OUT, "closeup_%s_%d.png" % (key, frame))
    out.filepath_raw = dst
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    print("CLOSEUP", dst)
