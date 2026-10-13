"""M0.1 step 2: derive the shared low-poly geometry from the step-1 source character.

All three style options (S1 vertex color / S2 painted face / S3 texture detail) use
this same geometry, so the comparison isolates *surface treatment*. Run after
step 01, inside the persistent Blender:

    tools/blender-exec.py pipeline/blender/m0_style/02_lowpoly.py

Each LP_* object is a baked (modifiers and shape keys applied), decimated copy of a
Source_* object, with the triangle budget below (PLAN §8.3 LOD0 ≤ 3.5k visible).
It also tags per-face region ids (an int face attribute `region`) used for coloring:
skin, lips, scalp edge, nails, sclera, iris, pupil, brow, hair, top, bottom, shoe and
sole. M0 placeholder garments come from MakeHuman CC0 clothes; real garments are
authored in M1+.
"""
import math

import bmesh
import bpy
from mathutils import Vector

BUDGET = {  # target triangles per part
    "body": 1700,   # visible skin only: head, neck, arms, hands (covered parts are masked)
    "hair": 520,
    "top": 380,
    "bottom": 460,
    "shoes": 240,
    "brows": 48,
    "eyes": 200,    # both eyes, built here (not decimated)
}

REGION = {"skin": 0, "lips": 1, "nails": 2, "sclera": 3, "iris": 4, "pupil": 5, "brow": 6, "hair": 7,
          "top": 8, "top_trim": 9, "bottom": 10, "shoe": 11, "sole": 12, "lashline": 13}

SRC = {
    "body": "SourceBody",
    "hair": "Source_Hair_ponytail01",
    "top_bottom": "Source_Clothes_female_casualsuit01",
    "shoes": "Source_Clothes_shoes02",
    "brows": "Source_Eyebrows_eyebrow005",
    "eyes": "Source_Eyes_low-poly",
}


def baked_copy(src_name, new_name):
    """Evaluated (modifiers + shape keys applied) standalone copy of a source object."""
    src = bpy.data.objects[src_name]
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(src.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = bpy.data.objects.get(new_name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    ob = bpy.data.objects.new(new_name, mesh)
    ob.matrix_world = src.matrix_world.copy()
    bpy.context.scene.collection.objects.link(ob)
    return ob


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def decimate_to(ob, target, symmetry=True, weight_group=None, factor=1.0):
    """Collapse-decimate to `target` tris. With `weight_group`, a LOW vertex weight adds
    collapse cost (Blender's bmesh decimator: cost += edge_len × (2 - w1 - w2) × factor),
    so weight-0 regions keep their triangles."""
    tris = tri_count(ob)
    if tris <= target:
        return
    mod = ob.modifiers.new("dec", "DECIMATE")
    if weight_group:
        mod.vertex_group = weight_group
        mod.vertex_group_factor = factor
    mod.decimate_type = "COLLAPSE"
    mod.ratio = target / tris
    mod.use_symmetry = symmetry
    mod.symmetry_axis = "X"
    mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def triangulate(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(ob.data); bm.free()


def region_attr(ob):
    a = ob.data.attributes.get("region") or ob.data.attributes.new("region", "INT", "FACE")
    return a


def set_all_regions(ob, rid):
    a = region_attr(ob)
    for d in a.data:
        d.value = rid


def group_weight_per_face(ob, group_name):
    g = ob.vertex_groups.get(group_name)
    if g is None:
        return [0.0] * len(ob.data.polygons)
    vw = [0.0] * len(ob.data.vertices)
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group == g.index:
                vw[v.index] = e.weight
    return [sum(vw[i] for i in p.vertices) / len(p.vertices) for p in ob.data.polygons]


def components(bm):
    """Connected face sets of a bmesh, largest first."""
    seen, comps = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        stack, comp = [f], []
        while stack:
            g = stack.pop()
            if g in seen:
                continue
            seen.add(g); comp.append(g)
            for e in g.edges:
                stack.extend(h for h in e.link_faces if h not in seen)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def solid_remesh(ob, thickness, voxel):
    """Thin cards → closed solid: solidify, then voxel remesh (hair, brows)."""
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness = thickness; so.offset = 1.0; so.use_even_offset = True
    rm = ob.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"; rm.voxel_size = voxel; rm.adaptivity = 0.0
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=so.name)
        bpy.ops.object.modifier_apply(modifier=rm.name)


def remove_objects(prefix):
    for o in [o for o in bpy.data.objects if o.name.startswith(prefix)]:
        bpy.data.objects.remove(o, do_unlink=True)


remove_objects("LP_")
report = {}

# ---- body: visible skin only (MakeHuman's mask modifiers drop helpers + clothed parts)
eye_l = eye_r = None
src_body = bpy.data.objects[SRC["body"]]


def helper_sphere(group):
    g = src_body.vertex_groups[group]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = src_body.evaluated_get(dg)
    # helpers are masked in the evaluated mesh, so read the shape-keyed *basis* positions instead.
    keyed = src_body.data.shape_keys
    pts = []
    for v in src_body.data.vertices:
        if any(e.group == g.index and e.weight > 0.5 for e in v.groups):
            co = Vector((0, 0, 0))
            if keyed:
                base = keyed.key_blocks[0].data[v.index].co
                co = base.copy()
                for kb in keyed.key_blocks[1:]:
                    if kb.value:
                        co += (kb.data[v.index].co - base) * kb.value
            else:
                co = v.co.copy()
            pts.append(src_body.matrix_world @ co)
    c = sum(pts, Vector()) / len(pts)
    r = sum((p - c).length for p in pts) / len(pts)
    return c, r


eye_l = helper_sphere("helper-l-eye")
eye_r = helper_sphere("helper-r-eye")

body = baked_copy(SRC["body"], "LP_body")
triangulate(body)
# decimation priority: lips / eyes / nose get the most triangles (identity lives there),
# the rest of the head next, limbs least. Without it, long triangles ran from the lips to
# the chin and smeared lip color (render lp3, 2026-10-12).
lips_g = body.vertex_groups.get("lips")
dec = body.vertex_groups.new(name="dec_w")
mw = body.matrix_world
z_chin = mw.translation.z + src_body.dimensions.z * 0.86
for v in body.data.vertices:
    p = mw @ v.co
    w = 1.0
    if p.z > z_chin:
        w = 0.7
        near_eye = min((p - eye_l[0]).length / eye_l[1], (p - eye_r[0]).length / eye_r[1]) < 2.0
        lip = lips_g is not None and any(e.group == lips_g.index and e.weight > 0.05 for e in v.groups)
        nose = abs(p.x - mw.translation.x) < 0.02 and p.y < eye_l[0].y and eye_l[0].z - 0.05 < p.z < eye_l[0].z + 0.005
        if near_eye or lip or nose:
            w = 0.35
    dec.add([v.index], w, "REPLACE")
decimate_to(body, BUDGET["body"], weight_group="dec_w", factor=0.25)
lips_w = group_weight_per_face(body, "lips")
nails_w = group_weight_per_face(body, "fingernails")
a = region_attr(body)
for i, p in enumerate(body.data.polygons):
    rid = REGION["skin"]
    if lips_w[i] > 0.6:
        rid = REGION["lips"]
    elif nails_w[i] > 0.5:
        rid = REGION["nails"]
    a.data[i].value = rid
# lash line: MakeHuman lids are closed skin hugging the eyeball (no boundary holes), so
# find the upper-lid rim as faces whose center sits on the eyeball surface, above and in
# front of the eye center.
mw = body.matrix_world
for i, p in enumerate(body.data.polygons):
    c = mw @ p.center
    for (ec, er) in (eye_l, eye_r):
        d = (c - ec).length
        if abs(d - er) < 0.0022 and c.z > ec.z + er * 0.2 and c.y < ec.y - er * 0.45:
            a.data[i].value = REGION["lashline"]
report["body"] = tri_count(body)

# ---- hair: close the strand cards into a solid shell, then decimate
hair = baked_copy(SRC["hair"], "LP_hair")
# the cap is a stack of thin cards hugging the scalp; a bare voxel remesh erased it
# (2026-10-12: the first render came out bald). Thicken outward first.
solid_remesh(hair, thickness=0.009, voxel=0.0055)
triangulate(hair)
decimate_to(hair, BUDGET["hair"])
set_all_regions(hair, REGION["hair"])
report["hair"] = tri_count(hair)

# ---- clothes: the MakeHuman suit is two connected pieces, shirt (upper) and jeans (lower)
suit = baked_copy(SRC["top_bottom"], "LP_suit")
triangulate(suit)
bm = bmesh.new(); bm.from_mesh(suit.data)
comps = components(bm)
zmid = [sum((suit.matrix_world @ v.co).z for f in c for v in f.verts) / sum(len(f.verts) for f in c) for c in comps[:2]]
top_comp = 0 if zmid[0] > zmid[1] else 1
cut_ids = {f.index for f in comps[top_comp]}
bm.free()


def split_by_faces(src_ob, keep_pred, name):
    ob = src_ob.copy(); ob.data = src_ob.data.copy(); ob.name = name
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if not keep_pred(f.index)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(ob.data); bm.free()
    return ob


top = split_by_faces(suit, lambda i: i in cut_ids, "LP_top")
bottom = split_by_faces(suit, lambda i: i not in cut_ids, "LP_bottom")
bpy.data.objects.remove(suit, do_unlink=True)
decimate_to(top, BUDGET["top"])
decimate_to(bottom, BUDGET["bottom"])
set_all_regions(top, REGION["top"])
set_all_regions(bottom, REGION["bottom"])
report["top"] = tri_count(top); report["bottom"] = tri_count(bottom)

# ---- shoes
shoes = baked_copy(SRC["shoes"], "LP_shoes")
# shoes02 carries sock tops (small parts reaching 0.23 m) hidden under the jeans; decimated
# they became white shards through the trousers. Keep the two shoes only.
bm = bmesh.new(); bm.from_mesh(shoes.data)
comps = components(bm)
bmesh.ops.delete(bm, geom=[f for c in comps[2:] for f in c], context="FACES")
bm.to_mesh(shoes.data); bm.free()
triangulate(shoes)
decimate_to(shoes, BUDGET["shoes"])
a = region_attr(shoes)
zmin = min((shoes.matrix_world @ v.co).z for v in shoes.data.vertices)
for i, p in enumerate(shoes.data.polygons):
    a.data[i].value = REGION["sole"] if (shoes.matrix_world @ p.center).z < zmin + 0.022 else REGION["shoe"]
report["shoes"] = tri_count(shoes)

# ---- brows: cut real geometry out of the alpha-textured card
brows = baked_copy(SRC["brows"], "LP_brows")
img = None
for s in bpy.data.objects[SRC["brows"]].material_slots:
    if s.material and s.material.use_nodes:
        for n in s.material.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                img = n.image
bm = bmesh.new(); bm.from_mesh(brows.data)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
uv = bm.loops.layers.uv.active
W, H = img.size
px = img.pixels[:]


def alpha_at(u, v):
    x = min(W - 1, max(0, int((u % 1.0) * W))); y = min(H - 1, max(0, int((v % 1.0) * H)))
    return px[(y * W + x) * 4 + 3]


kill = []
for f in bm.faces:
    uc = sum((l[uv].uv for l in f.loops), Vector((0, 0))) / len(f.loops)
    if alpha_at(uc.x, uc.y) < 0.35:
        kill.append(f)
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.to_mesh(brows.data); bm.free()
# the alpha cut alone leaves a ragged, sketchy edge; close it into a clean solid shape
solid_remesh(brows, thickness=0.0015, voxel=0.0018)
bm = bmesh.new(); bm.from_mesh(brows.data)   # keep the two brows; drop stray hair-tip blobs
bmesh.ops.delete(bm, geom=[f for c in components(bm)[2:] for f in c], context="FACES")
bm.to_mesh(brows.data); bm.free()
triangulate(brows)
decimate_to(brows, BUDGET["brows"])
# nudge brows 1.5 mm off the skin along their normals so they never z-fight
for v in brows.data.vertices:
    v.co += v.normal * 0.0015
set_all_regions(brows, REGION["brow"])
report["brows"] = tri_count(brows)

# ---- eyes: concentric-ring topology so pupil / iris / sclera edges are real edges
SEG = 10
RINGS_DEG = [0.0, 11.0, 24.0, 48.0, 72.0, 96.0]   # pole (front) → back; boundaries on rings


def make_eye(name, center, radius):
    bm = bmesh.new()
    fwd = Vector((0, -1, 0))  # MakeHuman faces -Y
    rings = []
    for deg in RINGS_DEG[1:]:
        t = math.radians(deg)
        ring = []
        for s in range(SEG):
            phi = 2 * math.pi * s / SEG
            x = math.sin(t) * math.cos(phi); z = math.sin(t) * math.sin(phi); y = -math.cos(t)
            ring.append(bm.verts.new(center + Vector((x, y, z)) * radius))
        rings.append(ring)
    pole = bm.verts.new(center + fwd * radius)
    faces = []
    for s in range(SEG):
        faces.append((bm.faces.new((pole, rings[0][s], rings[0][(s + 1) % SEG])), 0))
    for r in range(len(rings) - 1):
        for s in range(SEG):
            a, b = rings[r][s], rings[r][(s + 1) % SEG]
            c, d = rings[r + 1][(s + 1) % SEG], rings[r + 1][s]
            faces.append((bm.faces.new((a, d, c, b)), r + 1))
    bmesh.ops.triangulate(bm, faces=[f for f, _ in faces])
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    # tag rings: 0 → pupil, 1 → iris, ≥2 → sclera (by angle of face center from the front pole)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    a = region_attr(ob)
    for i, p in enumerate(me.polygons):
        ang = math.degrees(fwd.angle((p.center - center).normalized()))
        a.data[i].value = REGION["pupil"] if ang < RINGS_DEG[1] else REGION["iris"] if ang < RINGS_DEG[2] else REGION["sclera"]
    return ob


eyes = [make_eye("LP_eye_l", eye_l[0], eye_l[1] * 0.98), make_eye("LP_eye_r", eye_r[0], eye_r[1] * 0.98)]
report["eyes"] = sum(tri_count(e) for e in eyes)

lp = [o for o in bpy.data.objects if o.name.startswith("LP_")]
for o in bpy.data.objects:
    if o.name.startswith("Source"):
        o.hide_render = True
report["total"] = sum(tri_count(o) for o in lp)
report["eye_radius_mm"] = round(eye_l[1] * 1000, 1)
result = report
