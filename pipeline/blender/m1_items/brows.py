"""M1 brows: geometric brows (S1 style: features are geometry) from MakeHuman CC0 brow cards.

M0 recipe: subdivide the alpha-textured card, keep faces where the brow texture is opaque,
close the ragged cut into a clean thin solid (solidify + voxel remesh), keep the two brows,
decimate, float 1.5 mm off the skin (never z-fights) and bind to the face.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

STYLES = {"brows_soft": ("eyebrows/eyebrow005/eyebrow005.mhclo", "Soft arch"),
          "brows_bold": ("eyebrows/eyebrow001/eyebrow001.mhclo", "Bold")}
body = Body()
head_band = body.terminal_band("neck")
out = {}
for bid in (ARGS or list(STYLES)):
    rel, name = STYLES[bid]
    ob, img = mh_asset_on_default_body(rel, "Eyebrows")
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
    uv = bm.loops.layers.uv.active
    W, H = img.size
    px = img.pixels[:]

    def alpha_at(u, v):
        x = min(W - 1, max(0, int((u % 1.0) * W))); y = min(H - 1, max(0, int((v % 1.0) * H)))
        return px[(y * W + x) * 4 + 3]
    kill = [f for f in bm.faces
            if alpha_at(*(sum((l[uv].uv for l in f.loops), Vector((0, 0))) / len(f.loops))) < 0.35]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(ob.data); bm.free()
    solid_remesh(ob, thickness=0.0015, voxel=0.0018)
    keep_largest(ob, 2)
    decimate_to(ob, 60)
    P, tris = mesh_arrays(ob)
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in P]
    for t in tris:
        try:
            bm.faces.new([vs[i] for i in t])
        except ValueError:
            pass
    still = clear_body(bm, body, {head_band}, 0.0015, iters=8)
    P, tris, _ = bm_tris(bm)
    info = export_item(body, bid, {"name": name, "slot": "brows", "layer": 1, "colors": ["3B2A20"],
                                   "ages": ["toddler", "child", "teen", "adult", "elder"]},
                       P, tris, [0] * len(tris), [])
    bpy.data.objects.remove(ob, do_unlink=True)
    out[bid] = {"tris": info["counts"]["tris"], "clearance": still}
result = out
