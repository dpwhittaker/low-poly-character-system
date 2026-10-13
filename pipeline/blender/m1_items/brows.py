"""M1 brows: authored geometric brows (S1: features are geometry).

MakeHuman's brows are alpha-textured cards; cut into geometry they came out low and angled
down toward the nose, so every face read stern (line-up review 2026-10-13). Here each brow
is an authored tapered strip — inner end, arch, tail — placed relative to the eye opening
and projected onto the brow ridge 1.2 mm off the skin. The inner end sits level with or
above the arch's start, which reads friendly; style = shape + thickness.
"""
import numpy as np

exec(open("/home/david/projects/low-poly-character-system/pipeline/blender/m1_items/lib_items.py").read())

# per style: control points (dx outward from the eye centre, dz above it; metres) and
# half-thickness at each point. Inner end first. Mirrored for the right brow.
STYLES = {
    "brows_soft": ("Soft arch", [(-0.019, 0.0165), (-0.008, 0.0205), (0.006, 0.0225), (0.017, 0.0195), (0.026, 0.0130)],
                   [0.0021, 0.0020, 0.0016, 0.0012, 0.0006]),
    "brows_straight": ("Straight", [(-0.019, 0.0175), (-0.006, 0.0195), (0.008, 0.0200), (0.019, 0.0180), (0.026, 0.0140)],
                       [0.0026, 0.0025, 0.0022, 0.0017, 0.0008]),
    "brows_bold": ("Bold", [(-0.020, 0.0165), (-0.007, 0.0205), (0.007, 0.0225), (0.018, 0.0195), (0.027, 0.0125)],
                   [0.0034, 0.0033, 0.0028, 0.0020, 0.0009]),
}
SEG = 10

body = Body()
# eye openings: boundary loops of the body mesh near the eyes → their centres
edges = {}
for f in body.polys:
    for a, b in zip(f, f[1:] + f[:1]):
        k = (min(a, b), max(a, b)); edges[k] = edges.get(k, 0) + 1
adj = {}
for (a, b), n in edges.items():
    if n == 1:
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
loops, seen = [], set()
for s0 in adj:  # boundary loops of the body (eye openings and any others)
    if s0 in seen:
        continue
    comp, stack = [], [s0]; seen.add(s0)
    while stack:
        v = stack.pop(); comp.append(v)
        for w in adj[v]:
            if w not in seen:
                seen.add(w); stack.append(w)
    loops.append(np.array([body.P[v] for v in comp]).mean(0))
skel = {b["name"]: b for b in json.load(open(BUILD + "/skeleton.json"))["bones"]}
eye_c = {}
for side in ("l", "r"):  # the opening nearest the (unstyled) skeleton's eye bone
    ref = np.array(skel["eye_" + side]["rest_head"])
    eye_c[side] = min(loops, key=lambda c: np.linalg.norm(c - ref))


def catmull(pts, n):
    pts = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = map(np.array, pts[i - 1:i + 3])
        for t in np.linspace(0, 1, n, endpoint=(i == len(pts) - 3)):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.array(out)


def surface_point(x, z):
    """Project (x, z) onto the face from the front (Blender front = -y)."""
    hit = body.bvh.ray_cast(Vector((x, -0.4, z)), Vector((0, 1, 0)), 1.0)
    p = np.array(hit[0])
    q, ti, _ = body.nearest(p)
    n = body.frame(ti, body.bary(ti, q))[2]
    return p + n * 0.0012


out = {}
for bid in (ARGS or list(STYLES)):
    name, ctrl, half = STYLES[bid]
    P, tris = [], []
    for side, sg in (("l", 1), ("r", -1)):
        c = eye_c[side]
        line = catmull([(c[0] + sg * dx, c[2] + dz) for dx, dz in ctrl], SEG // (len(ctrl) - 1) + 1)
        th = np.interp(np.linspace(0, 1, len(line)), np.linspace(0, 1, len(half)), half)
        base = len(P)
        for i, (x, z) in enumerate(line):
            d = line[min(i + 1, len(line) - 1)] - line[max(i - 1, 0)]
            nrm = np.array([-d[1], d[0]]) / np.linalg.norm(d)
            if nrm[1] < 0:
                nrm = -nrm
            for s in (1, -1):
                q = np.array([x, z]) + nrm * th[i] * s
                P.append(surface_point(q[0], q[1]))
        for i in range(len(line) - 1):
            a, b, cc, dd = base + 2 * i, base + 2 * i + 1, base + 2 * i + 3, base + 2 * i + 2
            tris += [[a, dd, cc], [a, cc, b]] if sg > 0 else [[a, cc, dd], [a, b, cc]]
    P = np.array(P)
    info = export_item(body, bid, {"name": name, "slot": "brows", "layer": 1, "colors": ["3B2A20"],
                                   "ages": ["toddler", "child", "teen", "adult", "elder"]},
                       P, tris, [0] * len(tris), [])
    out[bid] = info["counts"]
result = out
