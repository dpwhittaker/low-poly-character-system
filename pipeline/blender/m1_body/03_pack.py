"""M1 step 3: the runtime body pack → public/m1/body.json + public/m1/body.bin.

Inputs: pipeline/build/m1/extract.npz (step 1) and skeleton.json (step 2).

Coordinates are glTF (Y up, character faces +Z), metres, matching skeleton.glb.
Two vertex sets:
  src     shape vertices: the 1605 proxy vertices + two rigid ring-topology eyes. Morphs,
          joints and skin weights live here.
  render  src vertices split where the per-face color region changes (S1 style: flat
          color per face, smooth normals computed on the src topology at runtime).

Body regions (palette slots): skin, lips, nails, sclera, iris, pupil, lash line, and the
non-removable base layer (PLAN §5.7: a top band and briefs, recolorable). Feature faces
need EVERY corner in their MakeHuman group (V16).

Also writes test fixtures (tests/fixtures/m1_*.json) from MPFB itself: macro weights from
`TargetService.calculate_target_stack_from_macro_info_dict`, and src positions + joints
for random descriptors, so the TypeScript assembler is tested against MakeHuman.
"""
import importlib
import json
import math
import os
import random
import sys

import bpy  # noqa: F401  (BVH for AO)
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = "/home/david/projects/low-poly-character-system"
HERE = ROOT + "/pipeline/blender/m1_body"
BUILD = ROOT + "/pipeline/build/m1"
OUT = ROOT + "/public/m1"
FIX = ROOT + "/tests/fixtures"
sys.path.insert(0, HERE)
import sliders  # noqa: E402
import cuts  # noqa: E402
importlib.reload(sliders)
importlib.reload(cuts)
from bl_ext.user_default.mpfb.services.targetservice import TargetService  # noqa: E402

os.makedirs(OUT, exist_ok=True)
os.makedirs(FIX, exist_ok=True)
d = dict(np.load(BUILD + "/extract.npz"))  # NpzFile re-decompresses on every [] access
skel = json.load(open(BUILD + "/skeleton.json"))["bones"]

REGIONS = ["skin", "lips", "nails", "sclera", "iris", "pupil", "lashline", "baseTop", "baseBottom"]
PALETTE_SRGB = ["D9A07E", "C46E6B", "EBB9AC", "F3F0EA", "4E7A5E", "1B1615", "3A2622", "E8E4EC", "E8E4EC"]
QUANT = 5e-5            # metres per int16 step (±1.64 m range)
SPARSE_EPS = 1e-5       # |Δ| below this is dropped from a target

names = [str(x) for x in d["target_names"]]
tix = {nm: i for i, nm in enumerate(names)}
lp0 = d["lp_basis"].astype(np.float64)
V = len(lp0)
faces = []
o = 0
for n in d["face_len"]:
    faces.append(list(d["face_flat"][o:o + n])); o += n
jnames = [str(x) for x in d["joint_names"]]
jix = {nm: i for i, nm in enumerate(jnames)}
jb = d["joint_basis"].astype(np.float64)


# ---- MakeHuman macro weights, exactly as MPFB computes them (the TS port is tested on this)
def macro_stack(m):
    stack = TargetService.calculate_target_stack_from_macro_info_dict(m, cutoff=0.0)
    return [(nm, w) for nm, w in stack if nm in tix]


DEFAULT = TargetService.get_default_macro_info_dict()


def body(m, slider_vals=None, style=1.0):
    """src-free reference: low-poly positions + joints for a descriptor (Blender axes)."""
    p = lp0.copy(); j = jb.copy()
    stack = macro_stack(m)
    for s in sliders.SLIDERS:
        val = (slider_vals or {}).get(s["id"], 0.0)
        side = "pos" if val > 0 else "neg"
        for e, w in sliders.entries(s[side]):
            if e in tix and val != 0:
                stack.append((e, abs(val) * w))
    for t, w in sliders.STYLE_TARGETS.items():
        for e in sliders.expand(t):
            if e in tix:
                stack.append((e, w * style))
    for nm, w in stack:
        p += w * d["lp_deltas"][tix[nm]]
        j += w * d["joint_deltas"][tix[nm]]
    return p, j, stack


p_def, j_def, _ = body(DEFAULT)

# ---- standard cut lines (PLAN §6.2): plane cuts on the default body (cuts.py). New
# vertices are linear combinations of proxy vertices, so every per-vertex linear array
# below is re-expressed through the combination matrix C and stays exact.
grp0 = {str(nm): d["lp_groups"][:, i] for i, nm in enumerate(d["group_names"])}
_bw = grp0["nippleTip"] + grp0["nipple"] * 0.5
_l, _r = np.where(p_def[:, 0] > 0, _bw, -1).argmax(), np.where(p_def[:, 0] < 0, _bw, -1).argmax()
bust = (p_def[_l] + p_def[_r]) / 2  # bust point (midway between the two strongest nipple vertices)
J = lambda nm: j_def[jix[nm]]  # noqa: E731
arm_axes = [(J("joint-%s-shoulder" % s), J("joint-%s-elbow" % s), J("joint-%s-hand" % s)) for s in ("l", "r")]


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1)
    return np.linalg.norm(p - (a + t * ab))


def line_dist(p, a, b):
    ab = (b - a) / np.linalg.norm(b - a)
    return np.linalg.norm((p - a) - np.dot(p - a, ab) * ab), np.dot(p - a, ab) / np.linalg.norm(b - a)


cm = cuts.CutMesh(p_def, faces)
cut_report = {}
for spec in cuts.CUTS:
    sided = spec["part"] in ("leg", "arm", "shoulder")
    for side in (("l", "r") if sided else (None,)):
        cid = spec["id"] + ("_" + side if side else "")
        sg = 1.0 if side in (None, "l") else -1.0   # MakeHuman l = +x
        fmt = lambda x: x.format(s=side or "l")  # noqa: E731
        if spec["part"] == "torso":
            lm, off = spec["z"]
            z = (bust[2] if lm == "bust" else J(fmt(lm))[2]) + off
            point, normal = np.array([0.0, 0.0, z]), np.array([0.0, 0.0, 1.0])

            def ok(fi, f, z=z):
                c = np.mean([cm.pos[v] for v in f], 0)
                return abs(c[0]) < 0.24 and abs(c[2] - z) < 0.12 and \
                    min(min(seg_dist(c, a, b), seg_dist(c, b, h)) for a, b, h in arm_axes) > 0.045
        elif spec["part"] == "shoulder":
            at = J(fmt(spec["at"]))
            point = at + np.array(spec["offset"]) * np.array([sg, 1, 1])
            normal = np.array(spec["normal"]) * np.array([sg, 1, 1])

            def ok(fi, f, at=at, sg=sg, reach=spec["reach"]):
                c = np.mean([cm.pos[v] for v in f], 0)
                return np.linalg.norm(c - at) < reach and c[0] * sg > 0.06
        else:
            a, b = J(fmt(spec["a"])), J(fmt(spec["b"]))
            point = a + spec["t"] * (b - a)
            normal = (b - a) / np.linalg.norm(b - a)
            if spec.get("tilt"):  # neckline: lower at the front (-y)
                normal = normal + np.array([0.0, -spec["tilt"], 0.0]); normal /= np.linalg.norm(normal)
            radius = spec.get("radius", {"neck": 0.09, "leg": 0.13, "arm": 0.075}[spec["part"]])

            def ok(fi, f, a=a, b=b, radius=radius, sg=sg, part=spec["part"], point=point):
                c = np.mean([cm.pos[v] for v in f], 0)
                r, t = line_dist(c, a, b)
                if r > radius or not (-0.4 < t < 1.4) or np.linalg.norm(c - point) > 0.2:
                    return False
                if part == "leg":
                    return c[0] * sg > 0.004
                if part == "arm":
                    return c[0] * sg > 0.09
                return True
        edges = cm.cut(cid, point, normal, ok)
        closed, nv = cuts.loop_report(edges)
        cut_report[cid] = {"closed": closed, "verts": nv}

open_cuts = {k: v for k, v in cut_report.items() if not v["closed"]}
assert not open_cuts, ("every cut line must be one closed loop (V19)", open_cuts)
Vb = len(cm.pos)
C = np.zeros((Vb, V))
for i, c in enumerate(cm.comb):
    for k, w in c.items():
        C[i, k] = w
T0 = len(names)
d["lp_deltas"] = np.einsum("uv,tvk->tuk", C, d["lp_deltas"].astype(np.float64)).astype(np.float32)
d["lp_weights"] = (C @ d["lp_weights"]).astype(np.float32)
d["lp_jaw"] = (C @ d["lp_jaw"]).astype(np.float32)
d["lp_groups"] = (C @ d["lp_groups"]).astype(np.float32)
lp0 = C @ lp0
faces = cm.faces
V = Vb
p_def, j_def, _ = body(DEFAULT)
assert np.abs(p_def - np.array(cm.pos)).max() < 1e-6, "cut positions must equal C · proxy"
band_of_face, n_bands = cuts.bands(faces, list(cm.cut_edges.values()))
edge_faces = {}
for fi, f in enumerate(faces):
    for a, b in zip(f, f[1:] + f[:1]):
        edge_faces.setdefault((min(a, b), max(a, b)), []).append(fi)

# ---- eyes: concentric rings (pupil / iris / sclera edges are real edges), rigid spheres
SEG = 10
RINGS_DEG = [11.0, 24.0, 48.0, 72.0, 96.0]
eye_verts, eye_faces, eye_region, eye_u, eye_side = [], [], [], [], []
for e, s in enumerate(("l", "r")):
    c = jb[jix["joint-%s-eye" % s]]
    f = jb[jix["joint-%s-eye-target" % s]] - c
    f /= np.linalg.norm(f)
    up = np.array([0.0, 0.0, 1.0]); side = np.cross(f, up); side /= np.linalg.norm(side); up = np.cross(side, f)
    base_i = V + len(eye_verts)
    us = [f]
    for deg in RINGS_DEG:
        t = math.radians(deg)
        for k in range(SEG):
            phi = 2 * math.pi * k / SEG
            us.append(math.cos(t) * f + math.sin(t) * (math.cos(phi) * side + math.sin(phi) * up))
    for u in us:
        eye_u.append(u); eye_side.append(e)
        eye_verts.append(None)
    for k in range(SEG):
        eye_faces.append([base_i, base_i + 1 + k, base_i + 1 + (k + 1) % SEG])
        eye_region.append(REGIONS.index("pupil"))
    for r in range(len(RINGS_DEG) - 1):
        for k in range(SEG):
            a = base_i + 1 + r * SEG + k; b = base_i + 1 + r * SEG + (k + 1) % SEG
            cc = base_i + 1 + (r + 1) * SEG + (k + 1) % SEG; dd = base_i + 1 + (r + 1) * SEG + k
            eye_faces.append([a, dd, cc, b])
            eye_region.append(REGIONS.index("iris") if r == 0 else REGIONS.index("sclera"))
eye_u = np.array(eye_u); eye_side = np.array(eye_side)
E = len(eye_u)
Vs = V + E


def eye_pos(cs, rs):
    return cs[eye_side] + eye_u * rs[eye_side][:, None]


eye0 = eye_pos(d["eye_c_basis"].astype(np.float64), d["eye_r_basis"].astype(np.float64))
src0 = np.vstack([lp0, eye0])
T = len(names)
src_d = np.zeros((T, Vs, 3))
src_d[:, :V] = d["lp_deltas"]
src_d[:, V:] = d["eye_c_deltas"][:, eye_side] + eye_u[None] * d["eye_r_deltas"][:, eye_side][..., None]

# ---- body face regions on the default body
grp = {str(nm): d["lp_groups"][:, i] for i, nm in enumerate(d["group_names"])}


def all_in(group, f, mean_min):
    w = grp[group][f]
    return w.min() > 0.05 and w.mean() > mean_min


edges = {}
for fi, f in enumerate(faces):
    for a, b in zip(f, f[1:] + f[:1]):
        edges.setdefault((min(a, b), max(a, b)), []).append(fi)
boundary = {e for e, fs in edges.items() if len(fs) == 1}
bverts = {v for e in boundary for v in e}
ec_def = np.array([j_def[jix["joint-l-eye"]], j_def[jix["joint-r-eye"]]])
pz = {nm: j_def[jix[nm]] for nm in ("joint-pelvis", "joint-l-upper-leg", "joint-spine-2", "joint-spine-3", "joint-neck")}
nip = p_def[grp["nippleTip"] > 0.3].mean(0) if (grp["nippleTip"] > 0.3).any() else p_def[grp["nipple"] > 0.3].mean(0)
bones_w = [str(x) for x in d["bones_w"]]
dom = np.array(bones_w)[d["lp_weights"].argmax(1)]
TORSO = {"pelvis", "spine_01", "spine_02", "spine_03", "thigh_l", "thigh_r", "clavicle_l", "clavicle_r"}


def band_at(z_lo, z_hi):
    """Band of the most forward midline face between two heights (front of the torso)."""
    best = min((fi for fi, f in enumerate(faces)
                if abs(p_def[f].mean(0)[0]) < 0.08 and z_lo < p_def[f].mean(0)[2] < z_hi),
               key=lambda fi: p_def[faces[fi]].mean(0)[1])
    return band_of_face[best]


z_ub = bust[2] + next(c["z"][1] for c in cuts.CUTS if c["id"] == "underBust")
top_band = band_at(z_ub + 0.005, bust[2] + 0.03)  # crop top: under-bust → neckline and armholes
bottom_band = band_at(j_def[jix["joint-l-upper-leg"]][2] - 0.06, j_def[jix["joint-l-upper-leg"]][2] + 0.03)
band_sizes = np.bincount(band_of_face, minlength=n_bands)
assert band_sizes[top_band] < 0.16 * len(faces) and band_sizes[bottom_band] < 0.12 * len(faces), \
    ("base-layer band leaked through an open cut line", band_sizes[top_band], band_sizes[bottom_band], cut_report)
face_region = []
for fi, f in enumerate(faces):
    c = p_def[f].mean(0)
    r = "skin"
    if all_in("lips", f, 0.6):
        r = "lips"
    elif all_in("fingernails", f, 0.5) or all_in("toenails", f, 0.5):
        r = "nails"
    elif any((min(a, b), max(a, b)) in boundary for a, b in zip(f, f[1:] + f[:1])) \
            and min(np.linalg.norm(c - ec) for ec in ec_def) < 0.03 \
            and c[2] > ec_def[0][2]:
        r = "lashline"
    elif band_of_face[fi] == top_band:
        r = "baseTop"
    elif band_of_face[fi] == bottom_band:
        r = "baseBottom"
    face_region.append(REGIONS.index(r))
all_faces = faces + eye_faces
all_region = face_region + eye_region

# ---- triangulate (shorter diagonal on the default body) and split render vertices by region
src_def = np.vstack([p_def, eye_pos(d["eye_c_basis"] + sum(w * d["eye_c_deltas"][tix[nm]] for nm, w in body(DEFAULT)[2]),
                                    d["eye_r_basis"] + sum(w * d["eye_r_deltas"][tix[nm]] for nm, w in body(DEFAULT)[2]))])
tris, tri_region, tri_band = [], [], []
for fi, (f, r) in enumerate(zip(all_faces, all_region)):
    if len(f) == 3:
        tris.append(f); tri_region.append(r)
    elif len(f) > 4:  # cut pieces of convex quads are convex: fan
        for k in range(1, len(f) - 1):
            tris.append([f[0], f[k], f[k + 1]]); tri_region.append(r)
    else:
        a, b, c, dd = f
        if np.linalg.norm(src_def[a] - src_def[c]) <= np.linalg.norm(src_def[b] - src_def[dd]):
            tris += [[a, b, c], [a, c, dd]]
        else:
            tris += [[a, b, dd], [b, c, dd]]
        tri_region += [r, r]
    tri_band += [band_of_face[fi] if fi < len(faces) else 255] * (len(tris) - len(tri_band))
rkey, render_src, render_region, indices = {}, [], [], []
for t, r in zip(tris, tri_region):
    for v in t:
        k = (v, r)
        if k not in rkey:
            rkey[k] = len(render_src); render_src.append(v); render_region.append(r)
        indices.append(rkey[k])
Vr = len(render_src)

# ---- AO on the default body: cosine-weighted hemisphere rays (as M0, R18)
bvh = BVHTree.FromPolygons([Vector(p) for p in src_def], tris, all_triangles=True)
vn = np.zeros((Vs, 3))
for t in tris:
    a, b, c = src_def[t]
    n = np.cross(b - a, c - a)
    for v in t:
        vn[v] += n
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
rng = random.Random(7)
dirs = []
for _ in range(64):
    u1, u2 = rng.random(), rng.random()
    rr, phi = math.sqrt(u1), 2 * math.pi * u2
    dirs.append((rr * math.cos(phi), rr * math.sin(phi), math.sqrt(max(0.0, 1 - u1))))
ao = np.zeros(Vs)
for v in range(Vs):
    n = Vector(vn[v]); tt = n.orthogonal().normalized(); bb = n.cross(tt)
    p = Vector(src_def[v]) + n * 0.001
    hits = 0
    for x, y, z in dirs:
        if bvh.ray_cast(p, (tt * x + bb * y + n * z).normalized(), 0.12)[0] is not None:
            hits += 1
    ao[v] = 0.35 + 0.65 * (1 - hits / 64)

# ---- skin weights: game_engine + jaw (carved from head) + twist splits + rigid eyes
bone_names = [b["name"] for b in skel]
bix = {nm: i for i, nm in enumerate(bone_names)}
Wfull = np.zeros((Vs, len(bone_names)))
for i, bn in enumerate(bones_w):
    Wfull[:V, bix[bn]] = d["lp_weights"][:, i]
jaw = np.minimum(d["lp_jaw"], Wfull[:V, bix["head"]])
Wfull[:V, bix["head"]] -= jaw; Wfull[:V, bix["jaw"]] += jaw


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


for s in ("l", "r"):
    sh, el, ha = (j_def[jix["joint-%s-%s" % (s, k)]] for k in ("shoulder", "elbow", "hand"))
    t_up = ((p_def - sh) @ (el - sh)) / np.dot(el - sh, el - sh)
    share = smoothstep(0.5, 0.0, t_up) * 0.6           # near the shoulder: counter-twist bone
    w = Wfull[:V, bix["upperarm_" + s]]
    Wfull[:V, bix["upperarm_twist_01_" + s]] += w * share; Wfull[:V, bix["upperarm_" + s]] = w * (1 - share)
    t_lo = ((p_def - el) @ (ha - el)) / np.dot(ha - el, ha - el)
    share = smoothstep(0.35, 0.95, t_lo)                 # toward the wrist: follows hand roll
    w = Wfull[:V, bix["lowerarm_" + s]]
    Wfull[:V, bix["lowerarm_twist_01_" + s]] += w * share; Wfull[:V, bix["lowerarm_" + s]] = w * (1 - share)
for e, s in enumerate(("l", "r")):
    Wfull[V:][eye_side == e, bix["eye_" + s]] = 1.0
order = np.argsort(-Wfull, axis=1)[:, :4]
w4 = np.take_along_axis(Wfull, order, 1)
w4 /= np.maximum(w4.sum(1, keepdims=True), 1e-12)
wq = np.round(w4 * 255).astype(np.int32)
wq[np.arange(Vs), 0] += 255 - wq.sum(1)
unweighted = int((Wfull.sum(1) < 0.5).sum())

# ---- joints the bones use (+ ground); per-target joint deltas
used = []


def use(nm):
    if nm not in used:
        used.append(nm)
    return used.index(nm)


bones_out = []
for b in skel:
    h = b["head"]
    head = {"joint": use(h["joint"])} if "joint" in h else {"lerp": [use(h["lerp"][0]), use(h["lerp"][1]), h["lerp"][2]]}
    bones_out.append({"name": b["name"], "parent": bix[b["parent"]] if b["parent"] else -1, "head": head})
ground = use("joint-ground")
uj = np.array([jix[nm] for nm in used])


def g(a):  # Blender → glTF axes
    return np.stack([a[..., 0], a[..., 2], -a[..., 1]], -1)


# ---- binary layout
blob = bytearray()
layout = {}


def put(name, arr, dtype):
    a = np.ascontiguousarray(arr, dtype=dtype)
    while len(blob) % 4:
        blob.append(0)
    layout[name] = {"offset": len(blob), "length": a.nbytes, "dtype": np.dtype(dtype).name, "shape": list(a.shape)}
    blob.extend(a.tobytes())


put("srcBasis", g(src0), np.float32)
put("renderSrc", render_src, np.uint16)
put("renderRegion", render_region, np.uint8)
put("renderAO", np.round(ao[render_src] * 255), np.uint8)
put("indices", indices, np.uint16)
assert n_bands < 255
put("triBand", tri_band, np.uint8)
put("skinBones", order, np.uint8)
put("skinWeights", wq, np.uint8)
put("jointBasis", g(jb[uj]), np.float32)
tidx, tdel, toff = [], [], []
maxq = 0
for t in range(T):
    dd = g(src_d[t])
    nz = np.nonzero(np.abs(dd).max(1) > SPARSE_EPS)[0]
    q = np.round(dd[nz] / QUANT)
    maxq = max(maxq, float(np.abs(q).max()) if len(q) else 0.0)
    toff.append([len(tidx), len(nz)])
    tidx.extend(nz.tolist()); tdel.append(q)
assert maxq < 32767, maxq
put("targetIndex", tidx, np.uint16)
put("targetDelta", np.vstack(tdel), np.int16)
jd = np.round(g(d["joint_deltas"][:, uj]) / QUANT)
assert np.abs(jd).max() < 32767
put("jointDelta", jd, np.int16)
open(OUT + "/body.bin", "wb").write(bytes(blob))

# ---- years → age macro per gender (sliders.GROWTH_M): MakeHuman height curve, inverted
age_samples = np.linspace(0.0, 0.5, 251)
age_curve = {}
for gname, gval in (("female", 0.0), ("male", 1.0)):
    hs = []
    for a in age_samples:
        m = dict(DEFAULT); m["gender"] = gval; m["age"] = float(a)
        pp, jj, _ = body(m)
        hs.append(pp[:, 2].max() - jj[jix["joint-ground"]][2])
    hs = np.array(hs); frac = hs / hs[-1]
    chart = sliders.GROWTH_M[gname]; adult = chart[-1][1]
    table = []
    for yrs, h in chart:
        f = h / adult
        a = float(np.interp(f, frac, age_samples)) if f > frac[0] else 0.0
        table.append([yrs, round(a, 5)])
    age_curve[gname] = {"years_to_macro": table, "mh_height_m": [round(float(x), 4) for x in hs[::25]]}

slider_defs = []
for s in sliders.SLIDERS:
    slider_defs.append({"id": s["id"], "group": s["group"],
                        **{side: [[tix[e], w] for e, w in sliders.entries(s[side]) if e in tix] for side in ("neg", "pos")}})
meta = {
    "version": 1, "space": "gltf Y-up, faces +Z, metres", "proxy": "MakeHuman female1605 (CC0)",
    "counts": {"src": Vs, "body": V, "eyes": E, "render": Vr, "tris": len(indices) // 3, "targets": T},
    "quant": QUANT, "layout": layout, "targetRanges": toff, "targets": names,
    "regions": REGIONS, "paletteSrgb": PALETTE_SRGB,
    "bones": bones_out, "joints": used, "groundJoint": ground,
    "macroParts": sliders.MACRO_PARTS, "races": list(sliders.RACES), "ageKeys": sliders.AGE_KEYS,
    "ageCurve": age_curve,
    "sliders": slider_defs,
    "cuts": cut_report,
    "bands": {"count": int(n_bands), "baseTop": int(top_band), "baseBottom": int(bottom_band),
              "bounds": {str(b): sorted(cid for cid, es in cm.cut_edges.items()
                                        if any(band_of_face[fi] == b for e in es for fi in edge_faces.get(e, [])))
                         for b in range(n_bands)}},
    "style": [[tix[e], w] for t, w in sliders.STYLE_TARGETS.items() for e in sliders.expand(t) if e in tix],
}
json.dump(meta, open(OUT + "/body.json", "w"), separators=(",", ":"))
# the cut body, for garment authoring (M1.5): proxy combinations, faces, bands, cut loops
np.savez_compressed(BUILD + "/body_cut.npz", comb_rows=np.array([len(c) for c in cm.comb]),
                    comb_idx=np.array([k for c in cm.comb for k in c]), comb_w=np.array([w for c in cm.comb for w in c.values()]),
                    face_flat=np.array([v for f in faces for v in f]), face_len=np.array([len(f) for f in faces]),
                    band=np.array(band_of_face), p_def=p_def)
json.dump({cid: sorted([int(a), int(b)] for a, b in es) for cid, es in cm.cut_edges.items()}, open(BUILD + "/cut_edges.json", "w"))

# ---- fixtures: MPFB macro weights + reference bodies for the TS assembler tests
rng = random.Random(1234)
cases = []
for k in range(6):
    m = {key: rng.random() for key in ("gender", "age", "muscle", "weight", "proportions", "height", "cupsize", "firmness")}
    rw = [rng.random() for _ in range(3)]
    m["race"] = {r: x / sum(rw) for r, x in zip(sliders.RACES, rw)}
    if k == 0:
        m = DEFAULT
    sv = {s["id"]: round(rng.uniform(-1, 1), 3) for s in sliders.SLIDERS} if k >= 3 else {}
    p, j, stack = body(m, sv)
    ec = d["eye_c_basis"] + sum(w * d["eye_c_deltas"][tix[nm]] for nm, w in stack)
    er = d["eye_r_basis"] + sum(w * d["eye_r_deltas"][tix[nm]] for nm, w in stack)
    src = np.vstack([p, eye_pos(ec, er)])
    cases.append({"macro": m, "sliders": sv,
                  "stack": [[nm, w] for nm, w in macro_stack(m)],
                  "probe": {str(i): g(src[i]).round(6).tolist() for i in range(0, Vs, 97)},
                  "joints": {used[i]: g(j[jix[used[i]]]).round(6).tolist() for i in range(0, len(used), 5)}})
json.dump({"cases": cases}, open(FIX + "/m1_body_reference.json", "w"))

result = {"src": Vs, "render": Vr, "tris": len(indices) // 3, "bin_bytes": len(blob),
          "targets_nnz": len(tidx), "unweighted": unweighted, "max_quant": maxq,
          "regions": {r: int(sum(1 for x in all_region if x == REGIONS.index(r))) for r in REGIONS},
          "bones": len(bones_out), "joints_used": len(used), "ao_mean": float(ao.mean()),
          "cuts": cut_report, "bands": int(n_bands), "band_sizes": {"top": int(band_sizes[top_band]), "bottom": int(band_sizes[bottom_band])},
          "age_curve": {k: v["years_to_macro"][::4] for k, v in age_curve.items()}}
