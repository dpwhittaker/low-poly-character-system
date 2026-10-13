"""Item authoring library (M1.5, PLAN §6.3, §7.3 D1–D4). exec()'d by the item scripts.

Every item is authored on the MakeHuman DEFAULT body (the cut body from m1_body/03_pack:
`pipeline/build/m1/body_cut.npz`, Blender axes) and exported as a *binding* to that body:
per vertex three body src vertices, barycentrics and an offset in the surface's local frame
(D3). The runtime re-evaluates the binding on any baked body, so one authored item fits every
body; skin weights are inherited from the body through the same binding (D4).

Garments (approach A of probe P3) start from the body's own layer shell over whole bands,
so their openings sit exactly on the standard cut lines, then get an authored silhouette:
relaxed fit (bridging concavities), extensions past the cut lines, hems, collars, cuffs.
Hiding (D1) is measured: a body band is hidden only if every sample ray from it hits the item.
"""
import json
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = "/home/david/projects/low-poly-character-system"
BUILD = ROOT + "/pipeline/build/m1"
ITEMS_OUT = ROOT + "/public/m1/items"


# ---------------------------------------------------------------- the body
class Body:
    """Default body: src positions, polygons + bands, the pack's src triangles and normals."""

    def __init__(self):
        z = np.load(BUILD + "/body_cut.npz")
        self.P = z["p_def"].astype(np.float64)
        self.V = len(self.P)
        self.polys, o = [], 0
        for n in z["face_len"]:
            self.polys.append([int(x) for x in z["face_flat"][o:o + n]]); o += n
        self.poly_band = [int(b) for b in z["band"]]
        meta = json.load(open(ROOT + "/public/m1/body.json"))
        self.meta = meta
        raw = open(ROOT + "/public/m1/body.bin", "rb").read()

        def arr(name, dt):
            l = meta["layout"][name]
            return np.frombuffer(raw, dtype=dt, count=l["length"] // np.dtype(dt).itemsize, offset=l["offset"])
        rsrc = arr("renderSrc", np.uint16).astype(np.int64)
        idx = arr("indices", np.uint16).astype(np.int64)
        tband = arr("triBand", np.uint8)
        tris = rsrc[idx].reshape(-1, 3)
        keep = tband != 255  # drop the eyes
        self.tris = tris[keep]
        self.tri_band = tband[keep].astype(np.int64)
        self.N = self.normals(self.P)
        self.bvh = BVHTree.FromPolygons([Vector(p) for p in self.P], self.tris.tolist(), all_triangles=True)
        self.cut_edges = {k: [tuple(e) for e in v] for k, v in json.load(open(BUILD + "/cut_edges.json")).items()}
        self.joints = {}
        jb = np.frombuffer(raw, dtype=np.float32, count=meta["layout"]["jointBasis"]["length"] // 4,
                           offset=meta["layout"]["jointBasis"]["offset"]).reshape(-1, 3)
        del jb  # joints of the default body come from the extract below (Blender axes)
        d = np.load(BUILD + "/extract.npz")
        self._jn = [str(x) for x in d["joint_names"]]
        self._jb = d["joint_basis"].astype(np.float64)
        self._jd = d["joint_deltas"]
        self._tn = [str(x) for x in d["target_names"]]

    def normals(self, P):
        """Area-weighted vertex normals over the pack's triangles (= runtime srcNormals)."""
        n = np.zeros_like(P)
        a, b, c = P[self.tris[:, 0]], P[self.tris[:, 1]], P[self.tris[:, 2]]
        fn = np.cross(b - a, c - a)
        for k in range(3):
            np.add.at(n, self.tris[:, k], fn)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)

    def nearest(self, p):
        """(location, triangle index, normal there) of the closest body point."""
        loc, nrm, ti, dist = self.bvh.find_nearest(Vector(p))
        return np.array(loc), ti, dist

    def bary(self, ti, q):
        a, b, c = self.P[self.tris[ti]]
        v0, v1, v2 = b - a, c - a, q - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        return np.array([1 - v - w, v, w])

    def frame(self, ti, bc):
        """Local surface frame (t, b, n) at barycentric bc of triangle ti (runtime-identical)."""
        ids = self.tris[ti]
        n = (self.N[ids] * bc[:, None]).sum(0); n /= np.linalg.norm(n)
        e = self.P[ids[1]] - self.P[ids[0]]
        t = e - (e @ n) * n; t /= np.linalg.norm(t)
        return t, np.cross(n, t), n

    def faces_in_bands(self, bands):
        return [f for f, b in zip(self.polys, self.poly_band) if b in bands]

    def band_of_cut(self, cid):
        return {self.poly_band[i] for i, f in enumerate(self.polys)
                if any(((min(a, b), max(a, b)) in set(map(tuple, self.cut_edges[cid])))
                       for a, b in zip(f, f[1:] + f[:1]))}

    def bands_between(self, *cuts, terminal=False):
        """Bands whose cut-line boundary ⊆ the given cut ids. Terminal bands (head, hands,
        feet: one bounding cut) only with terminal=True, so a sleeve never swallows a hand."""
        bounds = self.meta["bands"]["bounds"]
        return {int(b) for b, cs in bounds.items() if cs and set(cs) <= set(cuts) and (terminal or len(cs) > 1)}

    def terminal_band(self, cut):
        """The terminal band beyond a cut (hand past a wrist, foot past an ankle, head past the neck)."""
        bounds = self.meta["bands"]["bounds"]
        return next(int(b) for b, cs in bounds.items() if cs == [cut])


# ---------------------------------------------------------------- shells and modelling
def shell(body, bands, offset):
    """bmesh copy of the body faces in `bands`, pushed out along the body normal.
    `offset(src_id, pos)` → metres. Returns (bm, src_of_vert dict)."""
    bm = bmesh.new()
    vmap, src = {}, {}
    for f in body.faces_in_bands(bands):
        for v in f:
            if v not in vmap:
                vmap[v] = bm.verts.new(body.P[v] + body.N[v] * offset(v, body.P[v]))
                src[vmap[v]] = v
        bm.faces.new([vmap[v] for v in f])
    bm.verts.ensure_lookup_table(); bm.verts.index_update()
    return bm, {bv.index: s for bv, s in src.items()}


def relax(bm, body, iters, strength, min_off, pinned=()):
    """Laplacian relax (fabric bridges concavities), then keep ≥ min_off(pos) off the body."""
    pin = set(pinned)
    for k in range(iters * 2):
        # Taubin λ|μ: alternate a smoothing and an inflating step, so the shell bridges
        # concavities without shrinking (plain Laplacian pulled shoulders through the shell)
        lam = strength if k % 2 == 0 else -strength * 1.04
        new = {}
        for v in bm.verts:
            if v.index in pin or v.is_boundary:
                continue
            nb = [e.other_vert(v).co for e in v.link_edges]
            avg = sum(nb, Vector()) / len(nb)
            new[v] = v.co + (avg - v.co) * lam
        for v, co in new.items():
            v.co = co
        for v in bm.verts:
            q, ti, dist = body.nearest(np.array(v.co))
            n = body.frame(ti, body.bary(ti, q))[2]
            off = float((np.array(v.co) - q) @ n)
            m = min_off(np.array(v.co))
            if off < m:
                v.co = Vector(q + n * m)


def clear_body(bm, body, bands, min_off, iters=12, ignore=None, cap=0.015):
    """D2 shell rule, enforced: every body vertex of `bands` sits ≥ min_off below the item
    along its normal. Relaxing slides shell vertices tangentially, so convex body points
    (acromion, bust) can rise through the flat item faces; push those faces out until clear.
    Returns the number of body vertices still violating (0 = clean)."""
    pts = sorted({v for f in body.faces_in_bands(bands) for v in f})
    bad = len(pts)
    moved = {}
    for _ in range(iters):
        bm.verts.index_update(); bm.faces.index_update()  # BVH hit indices = BM_elem_index
        bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        bvh = BVHTree.FromBMesh(bm)
        push = {}
        bad = 0
        for v in pts:
            p, n = Vector(body.P[v]), Vector(body.N[v])
            hit = bvh.ray_cast(p - n * 0.03, n, 0.03 + min_off)  # item below the skin or too close
            if hit[0] is None:
                continue
            gap = (hit[0] - p).dot(n)
            if gap >= min_off - 1e-5:
                continue
            if ignore and bm.faces[hit[2]].tag:  # hem lips fold toward the body by design
                continue
            bad += 1
            for fv in bm.faces[hit[2]].verts:
                push[fv.index] = max(push.get(fv.index, 0.0), min_off - gap + 0.0005)
        if not push:
            return 0
        for i, d in list(push.items()):  # spread to the 1-ring at half strength: no single-face lumps
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                push[j] = max(push.get(j, 0.0), d * 0.5)
        for i, d in push.items():
            d = min(d, cap - moved.get(i, 0.0))  # never run away: a vertex moves ≤ cap in total
            if d <= 0:
                continue
            moved[i] = moved.get(i, 0.0) + d
            v = bm.verts[i]
            q, ti, _ = body.nearest(np.array(v.co))
            v.co = v.co + Vector(body.frame(ti, body.bary(ti, q))[2]) * d
    return bad


def load_item_rest(item_id):
    """(positions in Blender axes, triangles) of an exported item on the default body."""
    meta = json.load(open(f"{ITEMS_OUT}/{item_id}.json"))
    raw = open(f"{ITEMS_OUT}/{item_id}.bin", "rb").read()

    def arr(name, dt):
        l = meta["layout"][name]
        return np.frombuffer(raw, dtype=dt, count=l["length"] // np.dtype(dt).itemsize, offset=l["offset"])
    g = arr("restPos", np.float32).reshape(-1, 3).astype(np.float64)
    P = np.stack([g[:, 0], -g[:, 2], g[:, 1]], -1)  # glTF → Blender axes
    return P, arr("indices", np.uint16).reshape(-1, 3).astype(np.int64)


def clear_item(bm, P2, T2, min_off, iters=12, ignore=None, cap=0.015):
    """D2 between layers: every vertex of a lower-layer item (P2, T2) sits ≥ min_off below
    this item along its own normal; push offending faces of `bm` outward."""
    n2 = np.zeros_like(P2)
    for t in T2:
        a, b, c = P2[t]
        fn = np.cross(b - a, c - a)
        for v in t:
            n2[v] += fn
    n2 /= np.maximum(np.linalg.norm(n2, axis=1, keepdims=True), 1e-12)
    bad = len(P2)
    moved = {}
    for _ in range(iters):
        bm.verts.index_update(); bm.faces.index_update()  # BVH hit indices = BM_elem_index
        bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        bvh = BVHTree.FromBMesh(bm)
        push, bad = {}, 0
        for p, n in zip(P2, n2):
            p, n = Vector(p), Vector(n)
            # look only 6 mm below the lower item: deeper hits are other folds (armpit,
            # an opening's inward hem), not penetration, and pushing them tears the item
            hit = bvh.ray_cast(p - n * 0.006, n, 0.006 + min_off)
            if hit[0] is None:
                continue
            gap = (hit[0] - p).dot(n)
            if gap >= min_off - 1e-5:
                continue
            if ignore and bm.faces[hit[2]].tag:
                continue
            bad += 1
            for fv in bm.faces[hit[2]].verts:
                d, _ = push.get(fv.index, (0.0, n))
                push[fv.index] = (max(d, min_off - gap + 0.0005), n)
        if not push:
            return 0
        for i, (dd, n) in list(push.items()):  # 1-ring spread, as in clear_body
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                if push.get(j, (0.0, n))[0] < dd * 0.5:
                    push[j] = (dd * 0.5, n)
        for i, (dd, n) in push.items():
            dd = min(dd, cap - moved.get(i, 0.0))
            if dd <= 0:
                continue
            moved[i] = moved.get(i, 0.0) + dd
            bm.verts[i].co += n * dd  # along the lower item's normal there
    return bad


def drape_front(bm, bust_z, bust_front_y, below=0.25, slope=0.12):
    """Fabric hangs from the bust instead of following the body under it: front vertices
    below the bust are pushed forward to at least a plane falling back gently from the bust
    front (Blender front = −y). The binding turns this into larger offsets under the bust, so
    every body's garment drapes the same way."""
    for v in bm.verts:
        dz = bust_z - v.co.z
        if 0 < dz < below and v.co.y < 0.02:
            limit = bust_front_y + slope * dz
            w = min(1.0, dz / 0.03) * max(0.0, 1 - (abs(v.co.x) - 0.09) / 0.06) if abs(v.co.x) > 0.09 else min(1.0, dz / 0.03)
            if v.co.y > limit:
                v.co.y = v.co.y + (limit - v.co.y) * w


def boundary_loops(bm):
    """Closed boundary edge loops as ordered vertex lists."""
    edges = [e for e in bm.edges if e.is_boundary]
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a.index, []).append(b.index); adj.setdefault(b.index, []).append(a.index)
    seen, loops = set(), []
    for s in adj:
        if s in seen:
            continue
        loop = [s]; seen.add(s); prev, cur = None, s
        while True:
            nxt = [x for x in adj[cur] if x != prev and x not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]; loop.append(cur); seen.add(cur)
        loops.append(loop)
    return loops


def loop_cut_id(body, loop, src):
    """Which cut line a garment opening sits on (by its src vertices)."""
    vs = {src.get(i) for i in loop}
    best, score = None, 0
    for cid, es in body.cut_edges.items():
        cv = {v for e in es for v in e}
        s = len(vs & cv) / max(1, len(vs))
        if s > score:
            best, score = cid, s
    return best if score > 0.6 else None


def extend_opening(bm, body, loop, length, flare, hem=0.004, steps=1):  # noqa: C901
    """Extend an opening past its cut line along the body surface (overlapping the visible
    skin, so no gap shows in motion), flaring outward; finish with a hem lip of thickness
    `hem` folded toward the body. Returns (extension faces, hem faces)."""
    bm.verts.ensure_lookup_table()
    ring = [bm.verts[i] for i in loop]
    ext_faces, hem_faces = [], []
    cur = ring
    for k in range(steps):
        new = []
        for v in cur:
            L = length(v.co) if callable(length) else length
            F = flare(v.co) if callable(flare) else flare
            inner = [e.other_vert(v) for e in v.link_edges if not e.is_boundary]
            away = Vector(v.co) - sum((u.co for u in inner), Vector()) / max(1, len(inner))
            q, ti, _ = body.nearest(np.array(v.co))
            t, b, n = body.frame(ti, body.bary(ti, q))
            d = np.array(away); d -= (d @ n) * n; d /= max(np.linalg.norm(d), 1e-9)
            off = float((np.array(v.co) - q) @ n) + F / steps
            p = q + d * (L / steps)
            q2, ti2, _ = body.nearest(p)
            n2 = body.frame(ti2, body.bary(ti2, q2))[2]
            new.append(bm.verts.new(Vector(q2 + n2 * off)))
        for i in range(len(cur)):
            j = (i + 1) % len(cur)
            ext_faces.append(bm.faces.new([cur[i], cur[j], new[j], new[i]]))
        cur = new
    if callable(hem) or hem > 0:
        inner_ring = []
        for v in cur:
            h = hem(v.co) if callable(hem) else hem
            q, ti, _ = body.nearest(np.array(v.co))
            n = body.frame(ti, body.bary(ti, q))[2]
            off = float((np.array(v.co) - q) @ n)
            inner_ring.append(bm.verts.new(Vector(np.array(v.co) - n * min(h, max(0.0, off - 0.002)))))
        for i in range(len(cur)):
            j = (i + 1) % len(cur)
            if (inner_ring[i].co - cur[i].co).length < 1e-5 and (inner_ring[j].co - cur[j].co).length < 1e-5:
                continue  # no lip on this stretch (e.g. a placket edge)
            hem_faces.append(bm.faces.new([cur[i], inner_ring[i], inner_ring[j], cur[j]]))
    bm.verts.index_update(); bm.faces.index_update()
    return ext_faces, hem_faces


# ---------------------------------------------------------------- binding + export
def bind(body, P):
    """D3 binding per vertex: src ids of the nearest body triangle, barycentrics, local offset."""
    ids, bcs, offs, bands = [], [], [], []
    for p in P:
        q, ti, _ = body.nearest(p)
        bc = body.bary(ti, q)
        bc = np.clip(bc, 0, 1); bc /= bc.sum()
        q = (body.P[body.tris[ti]] * bc[:, None]).sum(0)
        t, b, n = body.frame(ti, bc)
        r = p - q
        ids.append(body.tris[ti]); bcs.append(bc[:2]); offs.append([r @ t, r @ b, r @ n]); bands.append(body.tri_band[ti])
    return np.array(ids), np.array(bcs), np.array(offs), np.array(bands)


def refit(body, ids, bcs, offs):
    """The runtime fit on the default body (round-trip check)."""
    out = []
    for i, bc2, o in zip(ids, bcs, offs):
        bc = np.array([bc2[0], bc2[1], 1 - bc2[0] - bc2[1]])
        q = (body.P[i] * bc[:, None]).sum(0)
        ns = (body.N[i] * bc[:, None]).sum(0); ns /= np.linalg.norm(ns)
        e = body.P[i[1]] - body.P[i[0]]; t = e - (e @ ns) * ns; t /= np.linalg.norm(t)
        out.append(q + o[0] * t + o[1] * np.cross(ns, t) + o[2] * ns)
    return np.array(out)


def ao_bake(body, P, tris, dist=0.1, rays=48):
    """Per-vertex AO against the body and the item itself (cosine hemisphere)."""
    allP = np.vstack([body.P, P])
    allT = np.vstack([body.tris, np.array(tris) + body.V])
    bvh = BVHTree.FromPolygons([Vector(p) for p in allP], allT.tolist(), all_triangles=True)
    n = np.zeros_like(P)
    for t in tris:
        a, b, c = P[list(t)]
        fn = np.cross(b - a, c - a)
        for v in t:
            n[v] += fn
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rng = random.Random(3)
    dirs = []
    for _ in range(rays):
        u1, u2 = rng.random(), rng.random()
        r, phi = math.sqrt(u1), 2 * math.pi * u2
        dirs.append((r * math.cos(phi), r * math.sin(phi), math.sqrt(max(0.0, 1 - u1))))
    ao = np.zeros(len(P))
    for i, p in enumerate(P):
        nn = Vector(n[i]); tt = nn.orthogonal().normalized(); bb = nn.cross(tt)
        o = Vector(p) + nn * 0.001
        hits = sum(1 for x, y, z in dirs if bvh.ray_cast(o, (tt * x + bb * y + nn * z).normalized(), dist)[0] is not None)
        ao[i] = 0.4 + 0.6 * (1 - hits / rays)
    return ao


def measure_hides(body, P, tris, candidates, reach=0.12, min_clear=0.0):
    """D1: a body band is hidden only if EVERY sample ray (each vertex + face centre of the
    band, along the body normal) hits the item within `reach`."""
    bvh = BVHTree.FromPolygons([Vector(p) for p in P], [list(t) for t in tris], all_triangles=True)
    hidden = []
    for band in candidates:
        tri_ids = np.nonzero(body.tri_band == band)[0]
        if len(tri_ids) == 0:
            continue
        samples = []
        for ti in tri_ids:  # each corner, nudged 15% toward its triangle's centre, cast along
            ids = body.tris[ti]; c = body.P[ids].mean(0)  # the FACE normal (vertex normals in
            a, b, cc = body.P[ids]                          # creases point into arm/torso gaps)
            fn = np.cross(b - a, cc - a); fn /= max(np.linalg.norm(fn), 1e-12)
            for v in ids:
                mid = fn + body.N[v]; mid /= max(np.linalg.norm(mid), 1e-12)
                samples.append((body.P[v] * 0.85 + c * 0.15, (fn, body.N[v], mid)))
        for ti in tri_ids:
            ids = body.tris[ti]
            c = body.P[ids].mean(0); nn = body.N[ids].mean(0); nn /= np.linalg.norm(nn)
            samples.append((c, (nn,)))
        # covered = a ray along the face normal OR the vertex normal hits the item: in creases
        # one of them points into a body gap (armpit: vertex normal; crotch: face normal)
        ok = all(any(bvh.ray_cast(Vector(p + n * 0.0005), Vector(n), reach)[0] is not None for n in ns)
                 for p, ns in samples)
        if ok:
            hidden.append(int(band))
    return hidden


def export_item(body, item_id, meta, P, tris, tri_channel, hides, ao=None):
    """→ public/m1/items/<id>.json + .bin. Vertices are split by channel (S1 flat color)."""
    os.makedirs(ITEMS_OUT, exist_ok=True)
    P = np.asarray(P, float)
    ids, bcs, offs, vband = bind(body, P)
    err = np.abs(refit(body, ids, bcs, offs) - P).max()
    if ao is None:
        ao = ao_bake(body, P, tris)
    key, rv, rch, idx = {}, [], [], []
    for t, ch in zip(tris, tri_channel):
        for v in t:
            k = (v, ch)
            if k not in key:
                key[k] = len(rv); rv.append(v); rch.append(ch)
            idx.append(key[k])
    rv = np.array(rv)
    tri_band = []
    for t in tris:
        c = P[list(t)].mean(0)
        q, ti, _ = body.nearest(c)
        tri_band.append(int(body.tri_band[ti]))

    def g(a):  # Blender → glTF axes (offsets are frame-local: unchanged)
        return np.stack([a[..., 0], a[..., 2], -a[..., 1]], -1)
    blob = bytearray(); layout = {}

    def put(name, arr, dt):
        a = np.ascontiguousarray(arr, dtype=dt)
        while len(blob) % 4:
            blob.append(0)
        layout[name] = {"offset": len(blob), "length": a.nbytes, "dtype": np.dtype(dt).name, "shape": list(a.shape)}
        blob.extend(a.tobytes())
    put("bindSrc", ids[rv], np.uint16)
    put("bindBary", bcs[rv], np.float32)
    put("bindOffset", offs[rv], np.float32)
    put("channel", rch, np.uint8)
    put("ao", np.round(np.asarray(ao)[rv] * 255), np.uint8)
    put("indices", idx, np.uint16)
    put("triBand", tri_band, np.uint8)
    a, b, c = body.P[ids[:, 0]], body.P[ids[:, 1]], body.P[ids[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    put("bindArea", area[rv], np.float32)  # rest area of the binding triangle: offsets scale by √(A/A₀)
    put("restPos", g(P[rv]), np.float32)  # default-body positions, for checks only
    open(f"{ITEMS_OUT}/{item_id}.bin", "wb").write(bytes(blob))
    info = {**meta, "id": item_id, "hides": sorted(hides), "layout": layout,
            "counts": {"verts": len(rv), "tris": len(tris)}, "bindRoundTripMm": float(err * 1000)}
    json.dump(info, open(f"{ITEMS_OUT}/{item_id}.json", "w"), separators=(",", ":"))
    ids = sorted(f[:-5] for f in os.listdir(ITEMS_OUT) if f.endswith(".json") and f != "index.json")
    json.dump({"items": [{"id": i, "slot": json.load(open(f"{ITEMS_OUT}/{i}.json"))["slot"]} for i in ids]},
              open(f"{ITEMS_OUT}/index.json", "w"))
    return info


def to_object(name, P, tris, colors=None):
    """Preview object in the Blender scene (for renders / inspection)."""
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in P], [], [list(t) for t in tris])
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def bm_tris(bm):
    """Triangulated copy: (positions, triangles, source face index per triangle)."""
    bm2 = bm.copy()
    bm2.faces.ensure_lookup_table()
    for f in bm2.faces:
        f.tag = False
    fidx = {f: f.index for f in bm2.faces}
    res = bmesh.ops.triangulate(bm2, faces=list(bm2.faces), quad_method="SHORT_EDGE")
    bm2.verts.index_update()
    P = np.array([tuple(v.co) for v in bm2.verts])
    tris, src_face = [], []
    face_map = res.get("face_map", {})
    for f in bm2.faces:
        tris.append([v.index for v in f.verts])
        orig = face_map.get(f, f)
        src_face.append(fidx.get(orig, orig.index))
    bm2.free()
    return P, tris, src_face


# ---------------------------------------------------------------- MakeHuman assets as sources
def mh_asset_on_default_body(rel, kind):
    """A MakeHuman CC0 asset (hair, brows) fitted to the DEFAULT body *with the house style*
    (the same shape the cut body was packed in), baked to a standalone mesh object."""
    import importlib
    import sys
    sys.path.insert(0, ROOT + "/pipeline/blender/m1_body")
    import sliders
    importlib.reload(sliders)
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.locationservice import LocationService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    base = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                                     feet_on_ground=True, scale=0.1)
    tdir = os.path.join(LocationService.get_mpfb_data(), "targets")
    for t, w in sliders.STYLE_TARGETS.items():
        for e in sliders.expand(t):
            path = os.path.join(tdir, e + ".target.gz")
            if os.path.exists(path):
                TargetService.load_target(base, path, weight=w)
    asset = HumanService.add_mhclo_asset(os.path.join(LocationService.get_user_data(), rel), base,
                                         asset_type=kind, subdiv_levels=0, material_type="MAKESKIN")
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(asset.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    name = "SRC_" + os.path.basename(rel).split(".")[0]
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.matrix_world = asset.matrix_world.copy()
    img = None
    for s in asset.material_slots:
        if s.material and s.material.use_nodes:
            for n in s.material.node_tree.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    img = n.image
    doomed = {base.name, asset.name} | {c.name for c in base.children_recursive}
    if base.parent:
        doomed.add(base.parent.name)
    for nm in doomed:
        if nm in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[nm], do_unlink=True)
    for o in list(bpy.data.objects):
        if o.type == "ARMATURE" and not o.children:
            bpy.data.objects.remove(o, do_unlink=True)
    return ob, img


def solid_remesh(ob, thickness, voxel):
    """Thin cards → closed solid: solidify, then voxel remesh (hair, brows; M0 recipe)."""
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness = thickness; so.offset = 1.0; so.use_even_offset = True
    rm = ob.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"; rm.voxel_size = voxel; rm.adaptivity = 0.0
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=so.name)
        bpy.ops.object.modifier_apply(modifier=rm.name)


def decimate_to(ob, target, symmetry=True):
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if tris <= target:
        return
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"; mod.ratio = target / tris
    mod.use_symmetry = symmetry; mod.symmetry_axis = "X"; mod.use_collapse_triangulate = True
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def keep_largest(ob, n):
    """Keep the n largest connected components (drop stray blobs)."""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
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
    bmesh.ops.delete(bm, geom=[f for c in comps[n:] for f in c], context="FACES")
    bm.to_mesh(ob.data); bm.free()


def mesh_arrays(ob):
    me = ob.data
    mw = ob.matrix_world
    P = np.array([tuple(mw @ v.co) for v in me.vertices])
    tris = []
    for p in me.polygons:
        vs = list(p.vertices)
        for k in range(1, len(vs) - 1):
            tris.append([vs[0], vs[k], vs[k + 1]])
    return P, tris


def decimate_bm(bm, target, channel_of, protect_faces=()):
    """Collapse-decimate an authored item to its triangle budget (PLAN §8.3). Faces in
    `protect_faces` (collars, cuffs, hems: thin strips the decimator would eat first) and
    the openings keep their vertices; channel ids and hem tags survive as face attributes.
    Returns (bm, channel_of) of the decimated mesh."""
    me = bpy.data.meshes.new("_dec")
    bm.faces.index_update()
    tags = [f.tag for f in bm.faces]
    chans = [channel_of.get(f.index, 0) for f in bm.faces]
    prot = {f.index for f in protect_faces}
    keepv = {v.index for f in bm.faces if f.index in prot for v in f.verts} | \
            {v.index for v in bm.verts if v.is_boundary}
    bm.to_mesh(me)
    a = me.attributes.new("channel", "INT", "FACE"); a.data.foreach_set("value", chans)
    h = me.attributes.new("hem", "BOOLEAN", "FACE"); h.data.foreach_set("value", tags)
    ob = bpy.data.objects.new("_dec", me); bpy.context.scene.collection.objects.link(ob)
    vg = ob.vertex_groups.new(name="free")
    vg.add([v.index for v in me.vertices if v.index not in keepv], 1.0, "REPLACE")
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    if tris > target:
        mod = ob.modifiers.new("dec", "DECIMATE")
        mod.decimate_type = "COLLAPSE"; mod.ratio = target / tris
        mod.use_symmetry = True; mod.symmetry_axis = "X"; mod.use_collapse_triangulate = True
        mod.vertex_group = "free"; mod.vertex_group_factor = 50.0  # weight 0 (protected) = very costly
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    out = bmesh.new(); out.from_mesh(ob.data)
    # decimation can leave slits (2-edge boundaries) and tiny holes: weld, then fill holes of
    # ≤ 4 edges (real openings are far larger)
    bmesh.ops.remove_doubles(out, verts=out.verts, dist=1e-5)
    bmesh.ops.holes_fill(out, edges=[e for e in out.edges if e.is_boundary], sides=4)
    cl = out.faces.layers.int.get("channel")
    hl = out.faces.layers.bool.get("hem")
    out.faces.index_update()
    ch2 = {}
    for f in out.faces:
        ch2[f.index] = f[cl] if cl else 0
        f.tag = bool(f[hl]) if hl else False
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    return out, ch2
