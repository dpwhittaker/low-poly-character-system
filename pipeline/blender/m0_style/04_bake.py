"""M0.1 step 4: bake the textures that S2 (painted face) and S3 (texture detail) need.

Everything is derived from the step-1 high-res source, onto the step-2 low-poly parts:
  face.png     LP_body UV: skin + lips + upper-lid line + blush + hair-stroke brows (S2, S3)
  iris.png     front-projected eye UV: painted iris / pupil / limbal ring (S2, S3)
  detail_*.png greyscale detail, 0.5 = neutral (shader: albedo × 2·d), for top / bottom /
               shoes / hair (S3)
Output goes to public/m0/tex/. Run after step 03.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

OUT = "/home/david/projects/low-poly-character-system/public/m0/tex"
os.makedirs(OUT, exist_ok=True)
FACE_RES = 1024
DETAIL_RES = 512

SKIN = (0xD9, 0xA0, 0x7E); LIPS = (0xC4, 0x6E, 0x6B); LID = (0x3A, 0x26, 0x22)
BLUSH = (0xE0, 0x7A, 0x6E); BROW = (0x4A, 0x2E, 0x22)


def lin(rgb):  # sRGB bytes → linear floats (Blender emission works in linear)
    return tuple(((c / 255.0 + 0.055) / 1.055) ** 2.4 if c / 255.0 > 0.04045 else (c / 255.0) / 12.92 for c in rgb)


scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "GPU"
scene.cycles.samples = 16
bake = scene.render.bake
bake.target = "IMAGE_TEXTURES"
bake.use_selected_to_active = True
bake.use_cage = False
bake.cage_extrusion = 0.012
bake.max_ray_distance = 0.03
bake.margin = 8


def new_image(name, res, color=(0, 0, 0, 1)):
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, res, res, alpha=True, float_buffer=True)
    img.generated_color = color
    return img


def emission_material(name, build):
    """Material whose surface is emission; `build(nt, emission_node)` wires the color."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    build(nt, em)
    return m


def target_node(ob, img):
    """Image node made active on the bake target's (first) material."""
    mat = ob.active_material
    if mat is None or not mat.use_nodes:
        mat = bpy.data.materials.new(ob.name + "_bake"); mat.use_nodes = True
        ob.data.materials.clear(); ob.data.materials.append(mat)
    nt = mat.node_tree
    n = nt.nodes.get("bake_target") or nt.nodes.new("ShaderNodeTexImage")
    n.name = "bake_target"; n.image = img
    nt.nodes.active = n
    return n


def bake_emit(sources, target, img):
    target_node(target, img)
    for o in bpy.context.view_layer.objects:   # (select_all's poll fails after a UV edit-mode trip)
        o.select_set(False)
    for s in sources:
        s.hide_render = False; s.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    with bpy.context.temp_override(selected_objects=list(sources) + [target], active_object=target, object=target):
        bpy.ops.object.bake(type="EMIT")


def pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def save_png(arr_lin_rgba, path, srgb=True):
    h, w, _ = arr_lin_rgba.shape
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    a = np.clip(arr_lin_rgba, 0, 1).astype(np.float32)
    if srgb:  # store sRGB-encoded bytes; viewer decodes
        rgb = a[..., :3]
        a = a.copy()
        a[..., :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(a.ravel())
    img.filepath_raw = path; img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


src_body = bpy.data.objects["SourceBody"]
lp_body = bpy.data.objects["LP_body"]

# ---------------------------------------------------------------- face features on the source
# per-vertex feature weights → color attribute Feat (R lips, G upper-lid line, B blush)
dg = bpy.context.evaluated_depsgraph_get()
src_eval_mesh = bpy.data.meshes.new_from_object(src_body.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
face_src = bpy.data.objects.get("BakeSrc_face")
if face_src:
    bpy.data.objects.remove(face_src, do_unlink=True)
face_src = bpy.data.objects.new("BakeSrc_face", src_eval_mesh)
face_src.matrix_world = src_body.matrix_world.copy()
scene.collection.objects.link(face_src)


def eye_sphere(name):
    o = bpy.data.objects[name]
    pts = [o.matrix_world @ v.co for v in o.data.vertices]
    c = sum(pts, Vector()) / len(pts)
    return c, sum((p - c).length for p in pts) / len(pts)


eyes = [eye_sphere("LP_eye_l"), eye_sphere("LP_eye_r")]
me = face_src.data
lips_g = face_src.vertex_groups.get("lips")
feat = me.color_attributes.new("Feat", "FLOAT_COLOR", "POINT")
mw = face_src.matrix_world


def smooth(x0, x1, x):
    t = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
    return t * t * (3 - 2 * t)


for v in me.vertices:
    p = mw @ v.co
    lips = 0.0
    if lips_g is not None:
        for e in v.groups:
            if e.group == lips_g.index:
                lips = e.weight
    lid = blush = 0.0
    for (ec, er) in eyes:
        d = (p - ec).length
        up = smooth(ec.z - er * 0.05, ec.z + er * 0.35, p.z)
        front = smooth(ec.y - er * 0.2, ec.y - er * 0.6, p.y)
        lid = max(lid, (1.0 - smooth(0.0, 0.0035, abs(d - er * 1.02))) * up * front)
        side = 1.0 if ec.x > mw.translation.x else -1.0
        cheek = ec + Vector((side * er * 0.55, -er * 0.35, -er * 2.1))
        blush = max(blush, math.exp(-((p - cheek).length / (er * 1.35)) ** 2))
    feat.data[v.index].color = (smooth(0.35, 0.8, lips), lid, blush, 1.0)


def build_face(nt, em):
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_name = "Feat"
    sep = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(a.outputs["Color"], sep.inputs[0])
    m1 = nt.nodes.new("ShaderNodeMix"); m1.data_type = "RGBA"
    m1.inputs["A"].default_value = (*lin(SKIN), 1); m1.inputs["B"].default_value = (*lin(BLUSH), 1)
    mb = nt.nodes.new("ShaderNodeMath"); mb.operation = "MULTIPLY"; mb.inputs[1].default_value = 0.32
    nt.links.new(sep.outputs["Blue"], mb.inputs[0]); nt.links.new(mb.outputs[0], m1.inputs["Factor"])
    m2 = nt.nodes.new("ShaderNodeMix"); m2.data_type = "RGBA"
    m2.inputs["B"].default_value = (*lin(LIPS), 1)
    nt.links.new(m1.outputs["Result"], m2.inputs["A"]); nt.links.new(sep.outputs["Red"], m2.inputs["Factor"])
    m3 = nt.nodes.new("ShaderNodeMix"); m3.data_type = "RGBA"
    m3.inputs["B"].default_value = (*lin(LID), 1)
    nt.links.new(m2.outputs["Result"], m3.inputs["A"]); nt.links.new(sep.outputs["Green"], m3.inputs["Factor"])
    nt.links.new(m3.outputs["Result"], em.inputs["Color"])


# Face decal island: in MakeHuman's UV layout the whole face gets ~150 px of 1024, so
# painted features came out tiny and blurry (first bake, 2026-10-12). Give front-of-face
# triangles their own planar island in the right half (~5 px/mm at 1024²) and squeeze
# the rest of the body UVs into the left half. Seams fall on plain skin, so they're invisible.
cx = lp_body.matrix_world.translation.x
ez = (eyes[0][0].z + eyes[1][0].z) / 2
ey = (eyes[0][0].y + eyes[1][0].y) / 2
Z0, Z1, HALFW = ez - 0.115, ez + 0.075, 0.08
lpme = lp_body.data
uvl = lpme.uv_layers.active
mwb = lp_body.matrix_world
n_face = 0
for poly in lpme.polygons:
    ws = [mwb @ lpme.vertices[i].co for i in poly.vertices]
    nrm = (mwb.to_3x3() @ poly.normal).normalized()
    in_face = all(Z0 < w.z < Z1 and abs(w.x - cx) < HALFW and w.y < ey + 0.02 for w in ws) and nrm.y < -0.25
    for li, w in zip(poly.loop_indices, ws):
        if in_face:
            uvl.data[li].uv = (0.5 + 0.5 * (w.x - cx + HALFW) / (2 * HALFW), (w.z - Z0) / (Z1 - Z0))
        else:
            u, v = uvl.data[li].uv
            uvl.data[li].uv = (0.5 * u, v)
    n_face += in_face

face_src.data.materials.clear()
face_src.data.materials.append(emission_material("BakeFace", build_face))
for o in bpy.data.objects:
    o.select_set(False)
face_img = new_image("face_bake", FACE_RES, (*lin(SKIN), 1))
bake_emit([face_src], lp_body, face_img)
face = pixels(face_img)

# hair-stroke brows: bake the brow card's alpha as a coverage mask, then composite
brow_src = bpy.data.objects["Source_Eyebrows_eyebrow005"]
brow_tex = None
for s in brow_src.material_slots:
    if s.material and s.material.use_nodes:
        for n in s.material.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                brow_tex = n.image


def build_brow(nt, em):
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = brow_tex
    nt.links.new(t.outputs["Alpha"], em.inputs["Color"])


brow_bake_ob = bpy.data.objects.get("BakeSrc_brows")
if brow_bake_ob:
    bpy.data.objects.remove(brow_bake_ob, do_unlink=True)
brow_bake_ob = brow_src.copy(); brow_bake_ob.data = brow_src.data.copy(); brow_bake_ob.name = "BakeSrc_brows"
scene.collection.objects.link(brow_bake_ob)
brow_bake_ob.data.materials.clear(); brow_bake_ob.data.materials.append(emission_material("BakeBrow", build_brow))
mask_img = new_image("brow_mask", FACE_RES, (0, 0, 0, 1))
bake.margin = 2
bake_emit([brow_bake_ob], lp_body, mask_img)
bake.margin = 8
mask = np.clip(pixels(mask_img)[..., 0:1] * 1.1, 0, 1)
face[..., :3] = face[..., :3] * (1 - mask * 0.92) + np.array(lin(BROW)) * (mask * 0.92)
face[..., 3] = 1.0
save_png(face, os.path.join(OUT, "face.png"))

# ---------------------------------------------------------------- iris (procedural, 256²)
R = 256
yy, xx = np.mgrid[0:R, 0:R]
u = (xx + 0.5) / R - 0.5; v = (yy + 0.5) / R - 0.5
rad = np.sqrt(u * u + v * v)
ang = np.arctan2(v, u)
IRIS_R = math.sin(math.radians(24.0)) / 2.0   # matches the ring topology / UV projection below
PUPIL_R = IRIS_R * 0.42
sclera = np.array(lin((0xF3, 0xF0, 0xEA)))
iris_in = np.array(lin((0x8A, 0xA6, 0x5E))); iris_out = np.array(lin((0x2F, 0x5A, 0x48)))
t = np.clip((rad - PUPIL_R) / (IRIS_R - PUPIL_R), 0, 1)[..., None]
streak = (0.92 + 0.08 * np.sin(ang * 23.0))[..., None]
col = (iris_in * (1 - t) + iris_out * t) * streak
col = np.where((rad < IRIS_R)[..., None], col, sclera)
ring = np.clip(1 - np.abs(rad - IRIS_R) / 0.012, 0, 1)[..., None]
col = col * (1 - ring * 0.7) + np.array(lin((0x1E, 0x2A, 0x24))) * ring * 0.7
col = np.where((rad < PUPIL_R)[..., None], np.array(lin((0x14, 0x11, 0x10))), col)
hl = np.exp(-(((u + 0.045) ** 2 + (v - 0.05) ** 2) / 0.00045))[..., None]
col = col * (1 - hl) + hl
iris = np.concatenate([col, np.ones((R, R, 1))], axis=2)
save_png(iris[::-1], os.path.join(OUT, "iris.png"))

for name in ("LP_eye_l", "LP_eye_r"):  # front-projected UV (MakeHuman faces -Y)
    o = bpy.data.objects[name]
    c, r = eye_sphere(name)
    me = o.data
    uvl = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        p = o.matrix_world @ me.vertices[loop.vertex_index].co - c
        uvl.data[loop.index].uv = (0.5 + p.x / (2 * r), 0.5 + p.z / (2 * r))

# ---------------------------------------------------------------- S3 greyscale detail
def luminance_detail(arr, mask=None):
    lum = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722
    sel = lum[mask] if mask is not None else lum[lum > 0.002]
    med = float(np.median(sel)) if sel.size else 1.0
    d = np.clip(0.5 * lum / max(med, 1e-4), 0, 1)
    return np.stack([d, d, d, np.ones_like(d)], axis=2)


def bake_texture_detail(lp_name, src_name, res=DETAIL_RES, smart_uv=False):
    lp = bpy.data.objects[lp_name]; src = bpy.data.objects[src_name]
    if smart_uv:
        # Remeshed hair has no UVs, and edit-mode UV operators don't run in -b. Use a
        # cylindrical projection about the head axis (strands run along v), with the
        # ponytail (below the cap, behind the head) in the right half so the two don't overlap.
        me = lp.data
        uvl = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
        me.uv_layers.active = uvl
        cen = sum((lp.matrix_world @ v.co for v in me.vertices), Vector()) / len(me.vertices)
        zs = [(lp.matrix_world @ v.co).z for v in me.vertices]
        zlo, zhi = min(zs), max(zs)
        for poly in me.polygons:
            ws = [lp.matrix_world @ me.vertices[i].co for i in poly.vertices]
            pc = sum(ws, Vector()) / len(ws)
            tail = pc.y > cen.y + 0.03 and pc.z < cen.z - 0.02
            for li, w in zip(poly.loop_indices, ws):
                a = (math.atan2(w.x - cen.x, w.y - cen.y) / (2 * math.pi)) % 1.0
                uvl.data[li].uv = ((0.5 if tail else 0.0) + 0.48 * a, (w.z - zlo) / (zhi - zlo))
    tex = None
    for s in src.material_slots:
        if s.material and s.material.use_nodes:
            for n in s.material.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image and "diffuse" in n.image.name:
                    tex = n.image
    tmp = src.copy(); tmp.data = src.data.copy(); tmp.name = "BakeSrc_" + lp_name
    scene.collection.objects.link(tmp)

    def build(nt, em, tex=tex):
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = tex
        nt.links.new(t.outputs["Color"], em.inputs["Color"])
    tmp.data.materials.clear(); tmp.data.materials.append(emission_material("BakeDetail_" + lp_name, build))
    img = new_image("detail_" + lp_name, res, (0, 0, 0, 1))
    bake_emit([tmp], lp, img)
    arr = pixels(img)
    bpy.data.objects.remove(tmp, do_unlink=True)
    return luminance_detail(arr)


out = {}
for lp_name, src_name, key, uv in (("LP_top", "Source_Clothes_female_casualsuit01", "top", False),
                                   ("LP_bottom", "Source_Clothes_female_casualsuit01", "bottom", False),
                                   ("LP_shoes", "Source_Clothes_shoes02", "shoes", False),
                                   ("LP_hair", "Source_Hair_ponytail01", "hair", True)):
    d = bake_texture_detail(lp_name, src_name, smart_uv=uv)
    save_png(d, os.path.join(OUT, "detail_{}.png".format(key)), srgb=False)
    out[key] = float(d[..., 0].mean())

for n in ("BakeSrc_face", "BakeSrc_brows"):
    o = bpy.data.objects.get(n)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
result = {"written": sorted(os.listdir(OUT)), "detail_means": out, "brow_mask_max": float(mask.max()),
          "face_island_tris": n_face}
