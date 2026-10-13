"""M0.1 step 3: per-face palette colors (S1) plus baked ambient occlusion.

It writes two corner-domain color attributes on every LP_* object:
  `Col` — palette albedo by face `region`, so flat per-face color is crisp on facets
  `AO`  — Cycles-baked ambient occlusion of the assembled low-poly character
The style viewer multiplies them, and the runtime material will do the same, with
`Col` replaced by recolor channels × palette. Run after step 02.
"""
import bpy

PALETTE_SRGB = {  # region id → sRGB hex. A teen-girl test look, not a final palette.
    0: "D9A07E",   # skin
    1: "C46E6B",   # lips
    2: "EBB9AC",   # nails
    3: "F3F0EA",   # sclera
    4: "4E7A5E",   # iris (green-hazel)
    5: "1B1615",   # pupil
    6: "4A2E22",   # brow
    7: "6E3F27",   # hair (auburn brown)
    8: "3F72B8",   # top
    9: "F0F0F0",   # top trim
    10: "2E3D5C",  # bottom (dark denim)
    11: "EDEDED",  # shoe
    12: "9C9C9C",  # sole
    13: "3A2622",  # lash line
}


def srgb(hexs):
    return tuple(int(hexs[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def ensure_color(me, name):
    a = me.color_attributes.get(name)
    if a is None:
        a = me.color_attributes.new(name, "BYTE_COLOR", "CORNER")
    return a


lp = [o for o in bpy.data.objects if o.name.startswith("LP_") and o.type == "MESH"]
for o in lp:
    me = o.data
    for p in me.polygons:
        p.use_smooth = False
    reg = me.attributes["region"].data
    col = ensure_color(me, "Col")
    for p in me.polygons:
        r, g, b = srgb(PALETTE_SRGB.get(reg[p.index].value, "FF00FF"))
        for li in p.loop_indices:
            col.data[li].color_srgb = (r, g, b, 1.0)
    me.color_attributes.active_color = col
    ensure_color(me, "AO")

# material that shows Col (× AO when present) for Blender previews
mat = bpy.data.materials.get("LP_vertexcolor") or bpy.data.materials.new("LP_vertexcolor")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
bsdf.inputs["Roughness"].default_value = 0.85
ca = nt.nodes.new("ShaderNodeVertexColor"); ca.layer_name = "Col"
nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
for o in lp:
    o.data.materials.clear()
    o.data.materials.append(mat)

# --- ambient occlusion, computed directly: N cosine-weighted hemisphere rays per vertex
# against every LP part within AO_DIST. Cycles' bake-to-vertex-colors only wrote the
# active object and left 85 % of body corners at 0 (2026-10-12), so it isn't used.
import math
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree

AO_DIST = 0.25
AO_RAYS = 64
rng = random.Random(7)
dirs = []
for _ in range(AO_RAYS):  # cosine-weighted hemisphere around +Z, rotated per normal below
    u1, u2 = rng.random(), rng.random()
    r, phi = math.sqrt(u1), 2 * math.pi * u2
    dirs.append(Vector((r * math.cos(phi), r * math.sin(phi), math.sqrt(max(0.0, 1 - u1)))))

dg = bpy.context.evaluated_depsgraph_get()
trees = [BVHTree.FromObject(o, dg) for o in lp]  # object space; rays are mapped per object
inv = [o.matrix_world.inverted() for o in lp]
for o in lp:
    me = o.data
    me.update()
    mw = o.matrix_world; nm = mw.to_3x3().inverted().transposed()
    vao = []
    for v in me.vertices:
        p = mw @ v.co
        n = (nm @ v.normal).normalized()
        t = n.orthogonal().normalized(); b = n.cross(t)
        hits = 0
        for d in dirs:
            wd = (t * d.x + b * d.y + n * d.z).normalized()
            origin = p + n * 0.0015
            for tree, iv in zip(trees, inv):
                lo = iv @ origin; ld = (iv.to_3x3() @ wd).normalized()
                hit = tree.ray_cast(lo, ld, AO_DIST)
                if hit[0] is not None:
                    hits += 1
                    break
        vao.append(1.0 - hits / AO_RAYS)
    ao = me.color_attributes["AO"]
    for loop in me.loops:
        a = 0.35 + 0.65 * vao[loop.vertex_index]   # keep fully-occluded creases from going black
        ao.data[loop.index].color = (a, a, a, 1.0)

# preview material: Col × AO
mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
mix.inputs["Factor"].default_value = 1.0
ao = nt.nodes.new("ShaderNodeVertexColor"); ao.layer_name = "AO"
nt.links.new(ca.outputs["Color"], mix.inputs["A"])
nt.links.new(ao.outputs["Color"], mix.inputs["B"])
nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])

result = {"objects": [o.name for o in lp]}
