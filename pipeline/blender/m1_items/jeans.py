"""M1 garment: straight-leg jeans (layer 3). Approach A of probe P3.

Shell of the hip + leg bands from the high-hip line to the ankle lines; snug at the hip,
easing to a straight leg (more clearance toward the ankle); a waistband standing 1.5 cm
above the high-hip line with a lip (accent channel = topstitch / waistband), and hems
that run 2.5 cm past the ankle line over the top of the foot.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

body = Body()
CUTS = ["highHip", "lowHip"] + [c + s for c in ("hotPants_", "midThigh_", "knee_", "midCalf_", "ankle_") for s in "lr"]
bands = body.bands_between(*CUTS)
z_hip, z_ankle = 0.93, 0.10


def offset(v, p):
    t = np.clip((z_hip - p[2]) / (z_hip - z_ankle), 0, 1)
    return 0.004 + 0.012 * t


bm, src = shell(body, bands, offset)
relax(bm, body, iters=6, strength=0.4, min_off=lambda p: 0.0035)
still = clear_body(bm, body, bands, 0.0035)
channel_of = {f.index: 0 for f in bm.faces}
openings = []
for loop in boundary_loops(bm):
    cid = loop_cut_id(body, loop, src)
    openings.append(cid)
    if cid == "highHip":
        ext, hem = extend_opening(bm, body, loop, length=0.015, flare=0.002, hem=0.003)
        for f in ext + hem:
            channel_of[f.index] = 1  # waistband
    elif cid and cid.startswith("ankle"):
        ext, hem = extend_opening(bm, body, loop, length=0.025, flare=0.004, hem=0.004)
        for f in hem:
            channel_of[f.index] = 1
    else:
        raise RuntimeError(f"unexpected opening on {cid}")
    for f in ext + hem:
        channel_of.setdefault(f.index, 0)
bm.faces.index_update()
P, tris, srcf = bm_tris(bm)
ch = [channel_of.get(f, 0) for f in srcf]
hides = measure_hides(body, P, tris, sorted(bands))
info = export_item(body, "jeans", {"name": "Straight jeans", "slot": "bottom", "layer": 2,
                                   "colors": ["2E3D5C", "C9A15A", "1C2438"], "ages": ["child", "teen", "adult", "elder"]},
                   P, tris, ch, hides)
to_object("ITEM_jeans", P, tris)
result = {k: info[k] for k in ("counts", "hides", "bindRoundTripMm")} | {"bands": sorted(bands), "openings": openings,
                                                                         "clearance_violations": still}
