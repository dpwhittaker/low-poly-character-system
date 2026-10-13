"""M1 garment: open-front work jacket (layer 4), after reference #01.

Shell of the torso + full-arm bands, loose (16–22 mm off the body), relaxed harder than
the tee; the front strip is removed so it hangs open over the tee. One boundary then runs
neck → placket → hem: the neck part becomes a stand collar, the hem drops 4 cm past the
low-hip line, the placket edges only get a hem. Cuffs run 1.5 cm past the wrist line.
The jacket clears the tee by ≥ 4 mm (D2 between
layers) as well as the body.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

body = Body()
CUTS = ["neck", "armhole_l", "armhole_r", "underBust", "waist", "highHip", "lowHip"] + \
       [c + s for c in ("shortSleeve_", "elbow_", "wrist_") for s in "lr"]
bands = body.bands_between(*CUTS)
J = lambda nm: body._jb[body._jn.index(nm)]  # noqa: E731
z_neck, z_hem = 1.40, 0.95


def offset(v, p):
    if abs(p[0]) > 0.19:  # sleeves: clear the tee's flared sleeve (≤ 11 mm) by ≥ 4 mm
        return 0.017 + 0.004 * np.clip((abs(p[0]) - 0.19) / 0.25, 0, 1)
    t = np.clip((1.25 - p[2]) / (1.25 - z_hem), 0, 1)
    return 0.020 + 0.006 * t


bm, src = shell(body, bands, offset)
# open front: drop the face columns either side of the front midline, collar to hem
kill = [f for f in bm.faces if abs(f.calc_center_median().x) < 0.03 and f.calc_center_median().y < -0.02]
bmesh.ops.delete(bm, geom=kill, context="FACES")
bm.verts.ensure_lookup_table(); bm.verts.index_update()
src = {v.index: s for v, s in zip(bm.verts, [None] * len(bm.verts))}  # srcs no longer needed after the cut
relax(bm, body, iters=10, strength=0.45, min_off=lambda p: 0.015)
front = [v for v in bm.verts if abs(v.co.x) < 0.1 and v.co.y < -0.05]
bust_v = min(front, key=lambda v: v.co.y)  # most forward front vertex = the bust point
drape_front(bm, bust_v.co.z, bust_v.co.y)
channel_of = {f.index: 0 for f in bm.faces}
for loop in boundary_loops(bm):
    bm.verts.ensure_lookup_table()
    xs = [abs(bm.verts[i].co.x) for i in loop]
    if min(xs) > 0.25:  # a sleeve: cuff past the wrist line
        ext, hem = extend_opening(bm, body, loop, length=0.015, flare=0.003, hem=0.005)
        for f in ext + hem:
            channel_of[f.index] = 1
        for f in hem:
            f.tag = True
        continue

    def length(co):  # collar up, hem down, placket edges barely
        return 0.035 if co.z > z_neck - 0.03 else 0.04 if co.z < z_hem + 0.06 else 0.004

    def flare(co):
        return 0.012 if co.z > z_neck - 0.03 else 0.008 if co.z < z_hem + 0.06 else 0.0

    def hem_of(co):  # lips on the collar and hem; the open placket edges stay clean
        return 0.005 if (co.z > z_neck - 0.03 or co.z < z_hem + 0.06) else 0.0

    ext, hem = extend_opening(bm, body, loop, length=length, flare=flare, hem=hem_of)
    for f in ext + hem:
        channel_of.setdefault(f.index, 0)
    for f in hem:
        f.tag = True
bm.faces.index_update()
# clearance last, so collar, cuffs and hems are checked too: body, then the tee (D2 between layers)
# hem lips are tagged (f.tag): they fold toward the body by design, clearance ignores them
still = clear_body(bm, body, bands, 0.012, iters=30, ignore=True)
tee_P, tee_T = load_item_rest("tee")
still_tee = clear_item(bm, tee_P, tee_T, 0.004, iters=30, ignore=True)
P, tris, srcf = bm_tris(bm)
ch = [channel_of.get(f, 0) for f in srcf]
hides = measure_hides(body, P, tris, sorted(bands))
info = export_item(body, "jacket", {"name": "Work jacket", "slot": "outer", "layer": 4,
                                    "colors": ["C8962E", "B07F22", "8A6418"], "ages": ["child", "teen", "adult", "elder"]},
                   P, tris, ch, hides)
to_object("ITEM_jacket", P, tris)
result = {k: info[k] for k in ("counts", "hides", "bindRoundTripMm")} | {"clearance_body": still, "clearance_tee": still_tee}
