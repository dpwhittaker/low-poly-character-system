"""Standard cut lines (PLAN §6.2) authored onto the low-poly body by plane cuts.

The MakeHuman proxy topology has few complete edge loops where garments end (poles on
the chest and arms break the rings), so each cut line is made by cutting the mesh with a
plane fixed to the default body's joints, restricted to one body part. A vertex already
close to the plane is snapped onto the cut instead of creating a sliver, so existing
loops are reused where they are close.

Every new vertex lies on an original edge (a, b) at parameter t, so it is the linear
combination (1 − t)·a + t·b of proxy vertices. All per-vertex linear data — MakeHuman
target deltas, skin weights, feature-group weights — transfers through the same
combination, and stays exact (cuts happen in the shape-independent vertex space).

Pure numpy; used by 03_pack.py.
"""
import numpy as np

# id, part, where. Limb cuts: plane ⟂ the bone segment at parameter t from its first
# joint. Torso cuts: horizontal plane at a height given relative to landmarks.
CUTS = [
    {"id": "neck", "part": "neck", "a": "joint-neck", "b": "joint-head", "t": 0.12, "tilt": 0.35},
    {"id": "underBust", "part": "torso", "z": ("bust", -0.065)},
    {"id": "waist", "part": "torso", "z": ("joint-spine-3", 0.0)},
    {"id": "highHip", "part": "torso", "z": ("joint-spine-4", -0.01)},
    {"id": "lowHip", "part": "torso", "z": ("joint-{s}-upper-leg", 0.055)},
    {"id": "hotPants", "part": "leg", "a": "joint-{s}-upper-leg", "b": "joint-{s}-knee", "t": 0.2},
    {"id": "midThigh", "part": "leg", "a": "joint-{s}-upper-leg", "b": "joint-{s}-knee", "t": 0.55},
    {"id": "knee", "part": "leg", "a": "joint-{s}-upper-leg", "b": "joint-{s}-knee", "t": 1.0},
    {"id": "midCalf", "part": "leg", "a": "joint-{s}-knee", "b": "joint-{s}-ankle", "t": 0.5},
    {"id": "ankle", "part": "leg", "a": "joint-{s}-knee", "b": "joint-{s}-ankle", "t": 0.9},
    # armhole: a near-vertical plane just inside the shoulder joint (acromion → armpit), not
    # ⟂ the arm: in A-pose a plane ⟂ the upper arm runs on into the chest and never closes
    {"id": "armhole", "part": "shoulder", "at": "joint-{s}-shoulder", "offset": (-0.005, 0.0, 0.0),
     "normal": (1.0, 0.0, 0.25), "reach": 0.15},  # leans outward below: passes under the arm
    {"id": "shortSleeve", "part": "arm", "a": "joint-{s}-shoulder", "b": "joint-{s}-elbow", "t": 0.45},
    {"id": "elbow", "part": "arm", "a": "joint-{s}-shoulder", "b": "joint-{s}-elbow", "t": 1.0},
    {"id": "wrist", "part": "arm", "a": "joint-{s}-elbow", "b": "joint-{s}-hand", "t": 0.94},
]
SNAP = 0.22  # snap a vertex onto the plane when |d| < SNAP × its mean edge length


class CutMesh:
    """Polygon mesh whose vertices are sparse combinations of base (proxy) vertices."""

    def __init__(self, pos, faces):
        self.pos = [np.asarray(p, float) for p in pos]
        self.comb = [{i: 1.0} for i in range(len(pos))]
        self.faces = [list(f) for f in faces]
        self.cut_edges = {}  # cut id → set of (min, max) vertex pairs

    def edge_len(self):
        acc = np.zeros(len(self.pos)); cnt = np.zeros(len(self.pos))
        for f in self.faces:
            for a, b in zip(f, f[1:] + f[:1]):
                l = np.linalg.norm(self.pos[a] - self.pos[b])
                acc[a] += l; acc[b] += l; cnt[a] += 1; cnt[b] += 1
        return acc / np.maximum(cnt, 1)

    def cut(self, cid, point, normal, face_ok):
        normal = normal / np.linalg.norm(normal)
        el = self.edge_len()
        d = {}

        def dist(v):
            if v not in d:
                x = float(np.dot(self.pos[v] - point, normal))
                d[v] = 0.0 if abs(x) < SNAP * el[v] else x
            return d[v]

        new_on_edge = {}

        def edge_point(a, b):
            k = (min(a, b), max(a, b))
            if k not in new_on_edge:
                da, db = dist(a), dist(b)
                t = da / (da - db)
                p = self.pos[a] * (1 - t) + self.pos[b] * t
                c = {}
                for i, w in self.comb[a].items():
                    c[i] = c.get(i, 0.0) + w * (1 - t)
                for i, w in self.comb[b].items():
                    c[i] = c.get(i, 0.0) + w * t
                self.pos.append(p); self.comb.append(c)
                new_on_edge[k] = len(self.pos) - 1
            return new_on_edge[k]

        edges = set()
        out = []
        for fi, f in enumerate(self.faces):
            if not face_ok(fi, f):
                out.append(f); continue
            ds = [dist(v) for v in f]
            if not (min(ds) < 0 < max(ds)):
                # touching only: an edge lying on the plane is part of the cut line
                zs = [i for i, x in enumerate(ds) if x == 0.0]
                if len(zs) >= 2:
                    for i in zs:
                        j = (i + 1) % len(f)
                        if ds[j] == 0.0:
                            edges.add((min(f[i], f[j]), max(f[i], f[j])))
                out.append(f); continue
            poly = []  # (vertex, sign) around the face with crossing points inserted
            for i, v in enumerate(f):
                w = f[(i + 1) % len(f)]
                poly.append(v)
                if dist(v) * dist(w) < 0:
                    poly.append(edge_point(v, w))
            fresh = set(new_on_edge.values())
            zero = [i for i, v in enumerate(poly) if v in fresh or dist(v) == 0.0]
            if len(zero) != 2:
                out.append(f); continue  # degenerate (several crossings): leave whole
            i, j = zero
            a = poly[i:j + 1]
            b = poly[j:] + poly[:i + 1]
            out += [a, b]
            edges.add((min(poly[i], poly[j]), max(poly[i], poly[j])))
        self.faces = [p for p in out if len(p) >= 3]
        self.cut_edges[cid] = edges
        return edges


def loop_report(edges):
    """(closed?, vertex count): a clean cut line is one closed cycle."""
    deg = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
    if not deg:
        return False, 0
    if any(x != 2 for x in deg.values()):
        return False, len(deg)
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    start = next(iter(adj)); seen = {start}; stack = [start]
    while stack:
        v = stack.pop()
        for w in adj[v]:
            if w not in seen:
                seen.add(w); stack.append(w)
    return len(seen) == len(deg), len(deg)


def bands(faces, cut_edges_all):
    """Connected face components separated by cut edges → band id per face."""
    barrier = set().union(*cut_edges_all) if cut_edges_all else set()
    e2f = {}
    for fi, f in enumerate(faces):
        for a, b in zip(f, f[1:] + f[:1]):
            k = (min(a, b), max(a, b))
            if k not in barrier:
                e2f.setdefault(k, []).append(fi)
    band = [-1] * len(faces); nb = 0
    for s in range(len(faces)):
        if band[s] >= 0:
            continue
        band[s] = nb; stack = [s]
        while stack:
            fi = stack.pop(); f = faces[fi]
            for a, b in zip(f, f[1:] + f[:1]):
                for g in e2f.get((min(a, b), max(a, b)), []):
                    if band[g] < 0:
                        band[g] = nb; stack.append(g)
        nb += 1
    return band, nb
