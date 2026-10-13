"""Probe P3, approach C: MakeHuman's CC0 garments, decimated and rebound to our body.

female_casualsuit01 (a tee + jeans, MHCLO-bound to the MakeHuman base) on the house-style
default body → split shirt / jeans by connected component (M0 recipe) → decimated to the
same budgets as approach A's tee and jeans → bound, AO'd and exported exactly like any item
(`tee_mh`, `jeans_mh`), so the comparison isolates the authoring approach.
Hiding is measured the same way; clearance is enforced the same way.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

body = Body()
ob, _ = mh_asset_on_default_body("clothes/female_casualsuit01/female_casualsuit01.mhclo", "Clothes")
bm = bmesh.new(); bm.from_mesh(ob.data)
bm.faces.ensure_lookup_table()
mw = ob.matrix_world
seen, comps = set(), []
for f in bm.faces:
    if f.index in seen:
        continue
    comp, stack = [], [f]; seen.add(f.index)
    while stack:
        g = stack.pop(); comp.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index); stack.append(h)
    comps.append(comp)
comps.sort(key=len, reverse=True)
zmean = [np.mean([(mw @ v.co).z for f in c for v in f.verts]) for c in comps[:2]]
parts = {"tee_mh": comps[int(np.argmax(zmean))], "jeans_mh": comps[int(np.argmin(zmean))]}
budget = {"tee_mh": 754, "jeans_mh": 604}  # = approach A's counts
CUTS_TOP = ["neck", "armhole_l", "armhole_r", "underBust", "waist", "highHip", "lowHip", "shortSleeve_l", "shortSleeve_r"]
CUTS_BOT = ["highHip", "lowHip"] + [c + s for c in ("hotPants_", "midThigh_", "knee_", "midCalf_", "ankle_") for s in "lr"]
meta = {"tee_mh": {"name": "Tee (MakeHuman)", "slot": "top", "layer": 3, "colors": ["3F72B8", "F0F0F0", "2B2B2B"]},
        "jeans_mh": {"name": "Jeans (MakeHuman)", "slot": "bottom", "layer": 2, "colors": ["2E3D5C", "C9A15A", "1C2438"]}}
out = {}
for pid, comp in parts.items():
    keep = {f.index for f in comp}
    me = bpy.data.meshes.new(pid)
    b2 = bm.copy()
    b2.faces.ensure_lookup_table()
    bmesh.ops.delete(b2, geom=[f for f in b2.faces if f.index not in keep], context="FACES")
    b2.to_mesh(me); b2.free()
    o2 = bpy.data.objects.new("SRC_" + pid, me); bpy.context.scene.collection.objects.link(o2)
    o2.matrix_world = mw.copy()
    for p in me.polygons:
        p.use_smooth = False
    decimate_to(o2, budget[pid])
    P, tris = mesh_arrays(o2)
    b3 = bmesh.new()
    vs = [b3.verts.new(p) for p in P]
    for t in tris:
        try:
            b3.faces.new([vs[i] for i in t])
        except ValueError:
            pass
    bands = body.bands_between(*(CUTS_TOP if pid == "tee_mh" else CUTS_BOT))
    still = clear_body(b3, body, bands, 0.004, iters=20)
    P, tris, _ = bm_tris(b3)
    hides = measure_hides(body, P, tris, sorted(bands))
    info = export_item(body, pid, {**meta[pid], "ages": ["teen", "adult"], "probe": "P3-C"}, P, tris, [0] * len(tris), hides)
    bpy.data.objects.remove(o2, do_unlink=True)
    out[pid] = {"tris": info["counts"]["tris"], "hides": info["hides"], "clearance": still}
bm.free()
bpy.data.objects.remove(ob, do_unlink=True)
result = out
