"""Filmstrip renders for P6: N posed copies of the skinned MakeHuman default body in one image.

Poses are set straight from clip data (pose-bone quaternions + pelvis location), so what is
rendered is exactly what the clip holds. Lighting = the shared stage of `pipeline/blender/lib_render.py`
(grey world + key/fill/rim suns) plus a floor for contact cues. Cycles on CUDA (EEVEE/Workbench
crash headless on this machine, SPEC R18).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import lib_render  # noqa: E402  (shared stage lights)

import lib_anim as LA  # noqa: E402

SKIN = (0xD9 / 255, 0xA0 / 255, 0x7E / 255)


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, srgb, rough=0.8):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(_srgb_to_lin(c) for c in srgb) + (1.0,)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def setup_scene(samples=24):
    scene = bpy.context.scene
    lib_render.setup_stage(scene)
    floor = bpy.data.objects.get("Floor")
    if floor is None:
        me = bpy.data.meshes.new("Floor")
        s = 40.0
        me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        floor = bpy.data.objects.new("Floor", me)
        scene.collection.objects.link(floor)
        floor.data.materials.append(material("FloorMat", (0.62, 0.63, 0.66), 0.9))
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            if any(d.type == backend for d in prefs.devices):
                break
        except TypeError:
            continue
    for d in prefs.devices:
        d.use = d.type != "CPU"
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 3
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    return scene


class Crowd:
    """K copies of (rig, body). Copy 0 is the original pair."""

    def __init__(self, rig, body, k):
        body.data.materials.clear()
        body.data.materials.append(material("Skin", SKIN, 0.7))
        self.pairs = [(rig, body)]
        for i in range(1, k):
            r = rig.copy()
            r.data = rig.data  # share armature data (rest is identical)
            bpy.context.scene.collection.objects.link(r)
            b = body.copy()
            bpy.context.scene.collection.objects.link(b)
            b.parent = r
            for m in b.modifiers:
                if m.type == "ARMATURE":
                    m.object = r
            self.pairs.append((r, b))
        for r, _b in self.pairs:
            r.animation_data_clear()
            for pb in r.pose.bones:
                pb.rotation_mode = "QUATERNION"

    def pose(self, idx, clip, frame, offset):
        r, _b = self.pairs[idx]
        rest = LA.rest_info(r)
        for bname in LA.BONES:
            pb = r.pose.bones[bname]
            pb.rotation_quaternion = clip.q[bname][frame]
            pb.location = (0, 0, 0)
        pel = r.pose.bones["pelvis"]
        pel.location = rest["pelvis"]["R"].inverted() @ (clip.pelvis[frame] - rest["pelvis"]["head"])
        r.location = offset

    def hide_from(self, k):
        for i, (r, b) in enumerate(self.pairs):
            hide = i >= k
            r.hide_render = hide
            b.hide_render = hide


def clip_bounds(rest, clip, frames, margin=0.14):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for f in frames:
        w = LA.fk(rest, clip, f)
        for b in LA.BONES:
            m = w[b]
            tail = m @ Vector((0, (rest[b]["tail"] - rest[b]["head"]).length, 0))
            for p in (m.translation, tail):
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    lo -= Vector((margin, margin, 0))
    hi += Vector((margin, margin, margin))
    lo.z = min(lo.z, 0.0)
    return lo, hi


def render_strip(crowd, clip, frames, out_path, view="front", tile_w=300, tile_h=560, spacing=None,
                 bounds=None):
    """One image: the clip's `frames` side by side, seen from `view` ('front' | 'side' | 'three_quarter')."""
    scene = bpy.context.scene
    k = len(frames)
    crowd.hide_from(k)
    rest = LA.rest_info(crowd.pairs[0][0])
    lo, hi = bounds if bounds else clip_bounds(rest, clip, frames)
    w_x = hi.x - lo.x
    w_y = hi.y - lo.y
    height = hi.z - lo.z
    if view == "front":
        across = w_x
        step = spacing or max(across, 0.8)
        axis = Vector((1, 0, 0))
    else:
        across = w_y
        step = spacing or max(across, 0.7)
        axis = Vector((0, 1, 0)) if view == "side" else Vector((1, 0, 0))
    if view == "three_quarter":
        step = spacing or max(w_x, w_y, 0.8)
    for i, f in enumerate(frames):
        crowd.pose(i, clip, f, axis * (i * step))
    bpy.context.view_layer.update()
    cam = bpy.data.objects.get("StripCam")
    if cam is None:
        cam = bpy.data.objects.new("StripCam", bpy.data.cameras.new("StripCam"))
        scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    scene.camera = cam
    total_across = step * (k - 1) + max(across, 0.6)
    scene.render.resolution_x = tile_w * k
    scene.render.resolution_y = tile_h
    aspect = scene.render.resolution_x / scene.render.resolution_y
    # ortho_scale spans the image's longer side
    if aspect >= 1:
        cam.data.ortho_scale = max(total_across * 1.02, height * 1.04 * aspect)
    else:
        cam.data.ortho_scale = max(height * 1.04, total_across * 1.02 / aspect)
    zc = lo.z + height / 2
    if view == "front":
        cx = (lo.x + hi.x) / 2 + step * (k - 1) / 2
        cy = (lo.y + hi.y) / 2
        cam.location = (cx, cy - 20, zc)
        cam.rotation_euler = (math.radians(90), 0, 0)
    elif view == "side":
        # camera on the character's left (+X) looking at -X; character faces -Y = image left
        cx = (lo.x + hi.x) / 2
        cy = (lo.y + hi.y) / 2 + step * (k - 1) / 2
        cam.location = (cx + 20, cy, zc)
        cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    else:  # three_quarter: copies along X, camera 35 deg round to the character's left
        a = math.radians(35)
        cx = (lo.x + hi.x) / 2 + step * (k - 1) / 2
        cy = (lo.y + hi.y) / 2
        cam.location = (cx + math.sin(a) * 20, cy - math.cos(a) * 20, zc)
        cam.rotation_euler = (math.radians(90), 0, a)
        cam.data.ortho_scale *= 1.0
    cam.data.clip_end = 100
    scene.render.filepath = out_path
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return out_path
