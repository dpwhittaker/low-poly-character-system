"""Shared preview-render helpers for pipeline scripts (exec'd into the MCP Blender).

`render_views(objs, out_prefix, views=('front','three_quarter','side'), engine='BLENDER_EEVEE', res=640)`
frames the given objects with an orthographic-ish long lens and writes one PNG per view.
"""
import math
import bpy
from mathutils import Vector


def _bounds(objs):
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    return lo, hi


def setup_stage(scene):
    """Neutral grey world + key/fill/rim sun lights, idempotent."""
    world = bpy.data.worlds.get("Stage") or bpy.data.worlds.new("Stage")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.82, 0.82, 0.84, 1.0)
    bg.inputs[1].default_value = 0.9
    scene.world = world
    for name, rot, energy in (("Key", (50, 0, 35), 3.2), ("Fill", (65, 0, -50), 1.2), ("Rim", (60, 0, 170), 1.6)):
        ob = bpy.data.objects.get("Stage" + name)
        if ob is None:
            ob = bpy.data.objects.new("Stage" + name, bpy.data.lights.new("Stage" + name, "SUN"))
            scene.collection.objects.link(ob)
        ob.data.energy = energy
        ob.rotation_euler = tuple(math.radians(a) for a in rot)


VIEWS = {"front": 0.0, "three_quarter": 35.0, "side": 90.0, "back": 180.0}


def render_views(objs, out_prefix, views=("front", "three_quarter", "side"), engine="CYCLES",
                 res=640, focus="full", aspect=0.6):
    scene = bpy.context.scene
    setup_stage(scene)
    lo, hi = _bounds(objs)
    if focus == "head":
        h = hi.z - lo.z
        lo = Vector((lo.x, lo.y, hi.z - 0.14 * h)); hi = Vector((hi.x, hi.y, hi.z))
    center = (lo + hi) / 2
    height = hi.z - lo.z
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
        scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    # ortho_scale spans the image's longer side. Fit the subject's height and its widest
    # horizontal extent (aspect > 1 used to render square and crop, 2026-10-13).
    width = max(hi.x - lo.x, hi.y - lo.y)
    if aspect >= 1:
        cam.data.ortho_scale = max(height * 1.12 * aspect, width * 1.06)
    else:
        cam.data.ortho_scale = max(height * 1.12, width * 1.06 / aspect)
    scene.camera = cam
    scene.render.engine = engine
    if engine == "CYCLES":
        # EEVEE/Workbench need EGL; until the NVIDIA driver reboot that falls back to Mesa
        # and crashed (2026-10-12). Cycles on CUDA/OptiX has no EGL dependency.
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
        scene.cycles.samples = 48
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 4
    scene.render.resolution_x = int(res * aspect)
    scene.render.resolution_y = res
    scene.render.film_transparent = False
    out = []
    for v in views:
        a = math.radians(VIEWS[v])
        d = 10.0
        cam.location = center + Vector((math.sin(a) * d, -math.cos(a) * d, 0.0))
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.render.filepath = "{}_{}.png".format(out_prefix, v)
        bpy.ops.render.render(write_still=True)
        out.append(scene.render.filepath)
    return out
