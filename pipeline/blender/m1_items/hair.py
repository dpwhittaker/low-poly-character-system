"""M1 hair: MakeHuman CC0 hairstyles → solid low-poly shells bound to the head (M0 recipe).

The strand cards are solidified, voxel-remeshed into one closed shell (a bare remesh of the
cards came out bald in M0), decimated to budget, kept ≥ 2.5 mm off the scalp, and bound to
the body like any item (they follow head shape sliders and inherit head/neck weights).
ARGS: style ids to build (default: all of STYLES).
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

STYLES = {  # id: (MakeHuman asset, display name, triangle budget)
    "hair_ponytail": ("hair/ponytail01/ponytail01.mhclo", "Ponytail", 520),
    "hair_bob": ("hair/bob01/bob01.mhclo", "Bob", 480),  # bob02's side fringe hid an eye
    "hair_short": ("hair/short02/short02.mhclo", "Short", 420),
}
body = Body()
head_band = body.terminal_band("neck")
out = {}
for hid in (ARGS or list(STYLES)):
    rel, name, budget = STYLES[hid]
    ob, _ = mh_asset_on_default_body(rel, "Hair")
    # keep the eyes clear: drop strand cards in front of the face below the brow line
    # (MakeHuman's bobs comb a side fringe over one eye; remeshed thick, it hid the eye)
    eyes = [b for b in json.load(open(BUILD + "/skeleton.json"))["bones"] if b["name"].startswith("eye_")]
    ez = np.mean([b["rest_head"][2] for b in eyes]) + 0.012  # just under the brows (house style lifts the eyes)
    ey = np.mean([b["rest_head"][1] for b in eyes])
    bm = bmesh.new(); bm.from_mesh(ob.data)
    mw = ob.matrix_world
    kill = [f for f in bm.faces
            if (lambda c: abs(c.x) < 0.075 and c.y < ey + 0.01 and c.z < ez + 0.02)(mw @ f.calc_center_median())]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(ob.data); bm.free()
    solid_remesh(ob, thickness=0.009, voxel=0.0055)
    keep_largest(ob, 1)
    decimate_to(ob, budget)
    P, tris = mesh_arrays(ob)
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in P]
    for t in tris:
        try:
            bm.faces.new([vs[i] for i in t])
        except ValueError:
            pass
    still = clear_body(bm, body, {head_band}, 0.0025, iters=10)
    P, tris, _ = bm_tris(bm)
    info = export_item(body, hid, {"name": name, "slot": "hair", "layer": 5, "colors": ["5A3825"],
                                   "ages": ["toddler", "child", "teen", "adult", "elder"]},
                       P, tris, [0] * len(tris), [])
    to_object("ITEM_" + hid, P, tris)
    bpy.data.objects.remove(ob, do_unlink=True)
    out[hid] = {"tris": info["counts"]["tris"], "clearance": still}
result = out
