"""M1 garment: crew-neck tee (layer 2, regular fit). Approach A of probe P3.

Shell of the torso + upper-arm bands, relaxed so fabric bridges the concavities (under the
bust, the small of the back), looser toward the hem; openings extended past their cut lines
(sleeves 2 cm, hem 3 cm) so no skin gap shows in motion; a rib collar in the accent channel.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

body = Body()
CUTS = ["neck", "armhole_l", "armhole_r", "underBust", "waist", "highHip", "lowHip", "shortSleeve_l", "shortSleeve_r"]
bands = body.bands_between(*CUTS)
zb = {"bust": 1.24, "hem": 0.95}
J = lambda nm: body._jb[body._jn.index(nm)]  # noqa: E731


def offset(v, p):
    t = np.clip((zb["bust"] - p[2]) / (zb["bust"] - zb["hem"]), 0, 1)
    return 0.005 + 0.010 * t * t


bm, src = shell(body, bands, offset)
relax(bm, body, iters=8, strength=0.45, min_off=lambda p: 0.004)
still = clear_body(bm, body, bands, 0.004)
channel_of = {f.index: 0 for f in bm.faces}
for loop in boundary_loops(bm):
    cid = loop_cut_id(body, loop, src)
    if cid == "neck":
        ext, hem = extend_opening(bm, body, loop, length=0.012, flare=0.0015, hem=0.003)
        for f in ext + hem:
            channel_of[f.index] = 1  # rib collar: accent
    elif cid and cid.startswith("shortSleeve"):
        ext, hem = extend_opening(bm, body, loop, length=0.02, flare=0.004, hem=0.003)
    elif cid == "lowHip":
        ext, hem = extend_opening(bm, body, loop, length=0.03, flare=0.006, hem=0.004, steps=2)
    else:
        raise RuntimeError(f"unexpected opening on {cid}")
    for f in ext + hem:
        channel_of.setdefault(f.index, 0)
bm.faces.index_update()
P, tris, srcf = bm_tris(bm)
ch = [channel_of.get(f, 0) for f in srcf]
hides = measure_hides(body, P, tris, sorted(bands))
# untucked: stacks OVER the bottom's waistband, so its layer is above the jeans' (D9)
info = export_item(body, "tee", {"name": "Crew tee", "slot": "top", "layer": 3,
                                 "colors": ["3F72B8", "F0F0F0", "2B2B2B"], "ages": ["child", "teen", "adult", "elder"]},
                   P, tris, ch, hides)
to_object("ITEM_tee", P, tris)
result = {k: info[k] for k in ("counts", "hides", "bindRoundTripMm")} | {"bands": sorted(bands), "clearance_violations": still}
