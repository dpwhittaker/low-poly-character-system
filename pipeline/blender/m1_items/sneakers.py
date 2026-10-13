"""M1 shoes: chunky sneakers (feet slot). The reference's shoes are big and blocky.

Shell of the foot bands (terminal bands past the ankle lines) with a roomy toe box, a flat
1.8 cm sole below the foot (accent channel) and a padded collar at the ankle line. The
sole lifts the whole character (`lift`, applied at assembly) instead of sinking into the
floor. Feet are hidden only where measured covered ("clip feet when possible", D1).
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

body = Body()
SOLE = 0.018
feet = {body.terminal_band("ankle_l"), body.terminal_band("ankle_r")}


def offset(v, p):
    toe = np.clip((-p[1] - 0.02) / 0.12, 0, 1)  # roomier toward the toes (front = -y)
    return 0.005 + 0.006 * toe


bm, src = shell(body, feet, offset)
relax(bm, body, iters=4, strength=0.35, min_off=lambda p: 0.004)
# toe box: a sneaker is the convex wrap of the foot, not a sock over each toe. Project the
# lower shell outward onto each foot's convex hull (toes and arch merge into one box);
# keep the snug shell near the ankle collar.
for side in (1, -1):
    vs = [v for v in bm.verts if v.co.x * side > 0]
    tmp = bmesh.new()
    for v in vs:
        tmp.verts.new(v.co)
    bmesh.ops.convex_hull(tmp, input=list(tmp.verts))
    hull = BVHTree.FromBMesh(tmp)
    z_top = max(v.co.z for v in vs)
    for v in vs:
        w = np.clip((z_top - 0.03 - v.co.z) / 0.03, 0, 1)  # 0 at the collar → 1 below it
        if w <= 0:
            continue
        q, ti, _ = body.nearest(np.array(v.co))
        n = Vector(body.frame(ti, body.bary(ti, q))[2])
        hit = hull.ray_cast(v.co + n * 0.0002, n, 0.04)
        if hit[0] is not None:
            v.co = v.co.lerp(hit[0], float(w))
    tmp.free()
still = clear_body(bm, body, feet, 0.004)
channel_of = {f.index: 0 for f in bm.faces}
for f in bm.faces:
    c = f.calc_center_median()
    if c.y < -0.06 and f.normal.z > 0.6 and c.z > 0.03:
        channel_of[f.index] = 2  # laces / tongue on top of the foot
for loop in boundary_loops(bm):
    cid = loop_cut_id(body, loop, src)
    if not (cid and cid.startswith("ankle")):
        raise RuntimeError(f"unexpected opening on {cid}")
    ext, hem = extend_opening(bm, body, loop, length=0.012, flare=0.004, hem=0.004)
    for f in ext + hem:
        channel_of[f.index] = 0


def hull2d(pts):
    """Monotone-chain convex hull of 2D points, counter-clockwise."""
    pts = sorted(set(map(tuple, np.round(pts, 6))))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1])


# the sole: a slab under each foot's footprint (convex outline, chunky), wrapping the
# upper's lower edge (top 13 mm up, 9 mm proud) so no seam or step shows, bottom flat at -SOLE
for side in (1, -1):
    low = np.array([tuple(v.co) for v in bm.verts if v.co.z < 0.03 and v.co.x * side > 0])
    ring = hull2d(low[:, :2])
    c = ring.mean(0)
    ring = c + (ring - c) * (1 + 0.009 / np.linalg.norm(ring - c, axis=1, keepdims=True))  # 9 mm outward
    top = [bm.verts.new((x, y, 0.013)) for x, y in ring]
    bot = [bm.verts.new((x, y, -SOLE)) for x, y in ring]
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        channel_of[bm.faces.new([bot[i], bot[j], top[j], top[i]]).index] = 1
    channel_of[bm.faces.new(list(reversed(bot))).index] = 1
bm.verts.index_update()
bm.faces.index_update()
P, tris, srcf = bm_tris(bm)
ch = [channel_of.get(f, 0) for f in srcf]
hides = measure_hides(body, P, tris, sorted(feet))
info = export_item(body, "sneakers", {"name": "Chunky sneakers", "slot": "shoes", "layer": 1, "lift": SOLE,
                                      "colors": ["F4F2EE", "C9C2B6", "D04A3A"], "ages": ["toddler", "child", "teen", "adult", "elder"]},
                   P, tris, ch, hides)
to_object("ITEM_sneakers", P, tris)
result = {k: info[k] for k in ("counts", "hides", "bindRoundTripMm")} | {"feet": sorted(feet), "clearance_violations": still}
