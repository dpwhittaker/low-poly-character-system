"""M1 step 1: transfer MakeHuman's anatomy data onto the low-poly body topology.

The topology is MakeHuman's CC0 proxy `female1605` (1605 vertices, 1584 human-designed
quads; PLAN §5.3, SPEC T22). A proxy vertex is bound to three base-mesh vertices plus an
offset scaled by three base-mesh distances (MPFB `ClothesService.fit_clothes_to_human`).
That fit is linear in the base positions, so a base-mesh target Δ maps to a low-poly
delta fit(B + Δ) − fit(B) *exactly*, and sums of targets stay exact.

For every macro, slider and style target (`sliders.py`) this writes:
  lp_deltas     low-poly vertex deltas (Blender axes, metres)
  joint_deltas  joint-cube centroid deltas (bone heads, MPFB rig "CUBE" strategy)
  eye_*         eye-helper centre / radius deltas (eyes are rigid spheres at runtime)
plus the low-poly basis, faces, `game_engine` skin weights interpolated through the same
binding, the default rig's jaw weights, and feature-group weights (lips, nails, ...).

Run inside the persistent Blender (`tools/blender-exec.py pipeline/blender/m1_body/01_extract.py`).
Output: pipeline/build/m1/extract.npz (+ extract.json). Re-runnable; wipes the scene.
"""
import gzip
import importlib
import json
import os
import sys

import bpy
import numpy as np

HERE = "/home/david/projects/low-poly-character-system/pipeline/blender/m1_body"
OUT = "/home/david/projects/low-poly-character-system/pipeline/build/m1"
sys.path.insert(0, HERE)
import sliders  # noqa: E402
importlib.reload(sliders)

from bl_ext.user_default.mpfb.entities.clothes.mhclo import Mhclo  # noqa: E402
from bl_ext.user_default.mpfb.services.humanservice import HumanService  # noqa: E402
from bl_ext.user_default.mpfb.services.locationservice import LocationService  # noqa: E402

PROXY = "female1605"
FEATURE_GROUPS = ["lips", "fingernails", "toenails", "ears", "scalp", "nipple", "nippleTip", "Left", "Mid", "Right"]

os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_homefile(use_empty=True)
base = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                                 feet_on_ground=True, scale=0.1)
me = base.data
n = len(me.vertices)
kb = me.shape_keys.key_blocks
B = np.zeros(n * 3); kb[0].data.foreach_get("co", B); B = B.reshape(-1, 3)
mix = B.copy()  # MPFB default human (macros 0.5) = basis + Σ value·(key − basis)
for k in kb[1:]:
    c = np.zeros(n * 3); k.data.foreach_get("co", c)
    mix += k.value * (c.reshape(-1, 3) - B)

# ---- vertex groups of the base mesh
gidx = {g.index: g.name for g in base.vertex_groups}
members, gweights = {}, {}
for v in me.vertices:
    for e in v.groups:
        nm = gidx[e.group]
        members.setdefault(nm, []).append(v.index)
        gweights.setdefault(nm, {})[v.index] = e.weight
joint_names = sorted(nm for nm in members if nm.startswith("joint-"))
J = [np.array(members[nm]) for nm in joint_names]

# ---- proxy binding
user = LocationService.get_user_data()
mh = Mhclo(); mh.load(os.path.join(user, "proxymeshes", PROXY, PROXY + ".proxy"))
V = len(mh.verts)
I = np.array([mh.verts[i]["verts"] for i in range(V)], dtype=np.int64)
W = np.array([mh.verts[i]["weights"] for i in range(V)], dtype=np.float64)
O = np.array([tuple(mh.verts[i]["offsets"]) for i in range(V)], dtype=np.float64)
xs, ys, zs = mh.x_scale, mh.y_scale, mh.z_scale


def fit(P):
    """MPFB's proxy fit (ClothesService.fit_clothes_to_human), vectorized."""
    x = abs(P[xs[0], 0] - P[xs[1], 0]) / xs[2]
    y = abs(P[ys[0], 2] - P[ys[1], 2]) / ys[2]
    z = abs(P[zs[0], 1] - P[zs[1], 1]) / zs[2]
    return (P[I] * W[..., None]).sum(1) + O * np.array([x, z, y])


# proxy faces from the OBJ (v/vt/vn tokens, 1-based)
faces = []
with open(os.path.join(user, "proxymeshes", PROXY, PROXY + ".obj")) as f:
    for line in f:
        if line.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])

# eyes: rigid spheres from the eye helper geometry
EYE_GROUPS = ["helper-l-eye", "helper-r-eye"]
EYE_IDX = [np.array(members[g]) for g in EYE_GROUPS]


def eye_params(P):
    cs = np.array([P[ix].mean(0) for ix in EYE_IDX])
    rs = np.array([np.linalg.norm(P[ix] - c, axis=1).mean() for ix, c in zip(EYE_IDX, cs)])
    return cs, rs


TDIR = os.path.join(LocationService.get_mpfb_data(), "targets")


def load_target(rel):
    """Sparse MakeHuman target → dense Blender-axis delta (×0.1: MPFB scale=0.1)."""
    idx, d = [], []
    with gzip.open(os.path.join(TDIR, rel + ".target.gz"), "rt") as fh:
        for line in fh:
            if not line.strip() or line[0] in "#\"":
                continue
            a = line.split()
            idx.append(int(a[0])); d.append((float(a[1]), -float(a[3]), float(a[2])))
    D = np.zeros((n, 3))
    if idx:
        D[np.array(idx)] = np.array(d) * 0.1
    return D


style_names = []
for t in sliders.STYLE_TARGETS:
    style_names += sliders.expand(t)
names = []
for nm in sliders.macro_target_names() + sliders.slider_target_names() + style_names:
    if nm not in names and os.path.exists(os.path.join(TDIR, nm + ".target.gz")):
        names.append(nm)
missing = [nm for nm in sliders.macro_target_names() + sliders.slider_target_names() + style_names
           if not os.path.exists(os.path.join(TDIR, nm + ".target.gz"))]

lp0 = fit(B)
c0, r0 = eye_params(B)
j0 = np.array([B[ix].mean(0) for ix in J])
T = len(names)
lp_d = np.zeros((T, V, 3), np.float32)
j_d = np.zeros((T, len(J), 3), np.float32)
ec_d = np.zeros((T, 2, 3), np.float32)
er_d = np.zeros((T, 2), np.float32)
for t, nm in enumerate(names):
    D = load_target(nm)
    P = B + D
    lp_d[t] = fit(P) - lp0
    j_d[t] = np.array([D[ix].mean(0) for ix in J])
    c, r = eye_params(P)
    ec_d[t] = c - c0; er_d[t] = r - r0

# ---- skin weights: game_engine (53 bones) + the default rig's jaw, through the binding
RIGS = os.path.join(LocationService.get_mpfb_data(), "rigs", "standard")
ge = json.load(open(os.path.join(RIGS, "weights.game_engine.json")))["weights"]
bones_w = sorted(ge)
wb = np.zeros((n, len(bones_w)))
for bi, bn in enumerate(bones_w):
    for vi, w in ge[bn]:
        wb[vi, bi] = w
jaw_b = np.zeros(n)
for vi, w in json.load(open(os.path.join(RIGS, "weights.default.json")))["weights"]["jaw"]:
    jaw_b[vi] = w
lp_w = (wb[I] * W[..., None]).sum(1)
lp_jaw = (jaw_b[I] * W).sum(1)

grp = np.zeros((V, len(FEATURE_GROUPS)))
for gi, g in enumerate(FEATURE_GROUPS):
    gw = np.zeros(n)
    for vi, w in gweights.get(g, {}).items():
        gw[vi] = w
    grp[:, gi] = (gw[I] * W).sum(1)

# ---- check: our vectorized fit of the MPFB default human vs MPFB's own proxy fit
proxy_ob = HumanService.add_mhclo_asset(os.path.join(user, "proxymeshes", PROXY, PROXY + ".proxy"), base,
                                        asset_type="Proxymeshes", subdiv_levels=0, material_type="NONE")
mp = np.zeros(V * 3); proxy_ob.data.vertices.foreach_get("co", mp); mp = mp.reshape(-1, 3)
mw = np.array(proxy_ob.matrix_world)
mp = mp @ mw[:3, :3].T + mw[:3, 3]
ours = fit(mix)
# and the linear-delta claim: fit(B) + Σ value·Δ_t over the default macro stack
lin = lp0.copy()
for k in kb[1:]:
    c = np.zeros(n * 3); k.data.foreach_get("co", c)
    lin += k.value * (fit(c.reshape(-1, 3)) - lp0)

np.savez_compressed(os.path.join(OUT, "extract.npz"),
                    base_n=n, lp_basis=lp0.astype(np.float32), lp_I=I, lp_W=W.astype(np.float32),
                    target_names=np.array(names), lp_deltas=lp_d, joint_names=np.array(joint_names),
                    joint_basis=j0.astype(np.float32), joint_deltas=j_d,
                    eye_c_basis=c0.astype(np.float32), eye_r_basis=r0.astype(np.float32),
                    eye_c_deltas=ec_d, eye_r_deltas=er_d,
                    bones_w=np.array(bones_w), lp_weights=lp_w.astype(np.float32), lp_jaw=lp_jaw.astype(np.float32),
                    group_names=np.array(FEATURE_GROUPS), lp_groups=grp.astype(np.float32),
                    face_flat=np.array([i for f in faces for i in f]), face_len=np.array([len(f) for f in faces]))
info = {"proxy": PROXY, "base_verts": n, "lp_verts": V, "faces": len(faces),
        "tris": sum(len(f) - 2 for f in faces), "targets": T, "missing_targets": missing,
        "joints": len(joint_names), "weight_bones": len(bones_w),
        "fit_vs_mpfb_max_mm": float(np.abs(ours - mp).max() * 1000),
        "linear_sum_vs_fit_max_mm": float(np.abs(lin - ours).max() * 1000),
        "default_height_m": float(ours[:, 2].max() - ours[:, 2].min()),
        "bytes_npz": os.path.getsize(os.path.join(OUT, "extract.npz"))}
json.dump(info, open(os.path.join(OUT, "extract.json"), "w"), indent=1)
result = info
