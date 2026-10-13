"""M1 P6 animation pipeline library: canonical rig, source readers, retargeting, cleanup.

Runs inside Blender 5.2.2 (bpy + mathutils + numpy). Source files are parsed with our own
readers (glTF/GLB JSON + binary, CMU ASF/AMC text); nothing from a download is executed.

Conventions (see README.md):
- Blender world: +Z up, character faces -Y, character's left = +X.
- Target = MPFB 2.0.18 `game_engine` rig fitted to the MakeHuman DEFAULT body (canonical rest).
- A clip = per-frame local rotations (quaternions, relative to the canonical rest = Blender
  pose-bone `rotation_quaternion`) for all 53 bones + a pelvis location (pose-bone `location`).
- Retarget = world-space rotation transfer: R_T(t) = D_S(t) . Align . R_T_rest, where
  D_S(t) = R_S(t) . R_S_rest^-1 is the source joint's world rotation away from its own rest and
  Align maps the target rest onto the source rest (swing of bone direction, optional twist from a
  secondary vector, or identity for bones whose rest is "the same posture" in both rigs).
"""
import json
import math
import os
import struct

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DL = os.path.join(HERE, "_downloads")
WORK = os.path.join(HERE, "_work")

# glTF (+Y up, character faces +Z) -> Blender (+Z up, faces -Y); same as Blender's importer.
A_GLTF = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
# CMU ASF (+Y up, faces +Z, left = +X) -> Blender. Same axis swap.
A_CMU = A_GLTF.copy()
CMU_UNIT = (1.0 / 0.45) * 2.54 / 100.0  # ASF length units -> metres (CMU FAQ)
CMU_FPS = {"113": 120.0, "141": 60.0}  # measured from walk cadence, see AmcSource

BONES = [  # canonical game_engine bone order (parents before children)
    "Root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head",
    "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
    "thumb_01_l", "thumb_02_l", "thumb_03_l", "index_01_l", "index_02_l", "index_03_l",
    "middle_01_l", "middle_02_l", "middle_03_l", "ring_01_l", "ring_02_l", "ring_03_l",
    "pinky_01_l", "pinky_02_l", "pinky_03_l",
    "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
    "thumb_01_r", "thumb_02_r", "thumb_03_r", "index_01_r", "index_02_r", "index_03_r",
    "middle_01_r", "middle_02_r", "middle_03_r", "ring_01_r", "ring_02_r", "ring_03_r",
    "pinky_01_r", "pinky_02_r", "pinky_03_r",
    "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r",
]
FINGERS = ("thumb", "index", "middle", "ring", "pinky")


# --------------------------------------------------------------------------------------------
# canonical target
# --------------------------------------------------------------------------------------------
def build_canonical(proxy=None):
    """Clean scene -> MakeHuman default body + game_engine rig. Returns (rig, body, proxy_obj).

    Canonical rest = this exact call sequence (no macro dict = MPFB defaults). Never edit bones.
    """
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.locationservice import LocationService
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    body = HumanService.create_human(mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
                                     feet_on_ground=True, scale=0.1)
    rig = HumanService.add_builtin_rig(body, "game_engine")
    prox = None
    if proxy:
        p = os.path.join(LocationService.get_user_data(), "proxymeshes", proxy, proxy + ".proxy")
        prox = HumanService.add_mhclo_asset(p, body, asset_type="Proxymeshes", subdiv_levels=0,
                                            material_type="MAKESKIN")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    assert sorted(b.name for b in rig.data.bones) == sorted(BONES), "rig bone set changed"
    return rig, body, prox


def rest_info(rig):
    """Bone rest data in armature space (rig object sits at the origin, identity)."""
    out = {}
    for name in BONES:
        b = rig.data.bones[name]
        out[name] = {
            "parent": b.parent.name if b.parent else None,
            "head": Vector(b.head_local), "tail": Vector(b.tail_local),
            "R": b.matrix_local.to_3x3().normalized(),
            "M": b.matrix_local.copy(),
        }
    return out


def rest_json(rig):
    """Serializable canonical rest (committed as canonical_rest.json for runtime checks)."""
    rows = []
    for name in BONES:
        b = rig.data.bones[name]
        ml = b.matrix_local
        if b.parent:
            loc = b.parent.matrix_local.inverted() @ ml
        else:
            loc = ml
        q = loc.to_quaternion()
        rows.append({
            "name": name, "parent": b.parent.name if b.parent else None,
            "head": [round(v, 6) for v in b.head_local], "tail": [round(v, 6) for v in b.tail_local],
            "local_rotation_wxyz": [round(v, 6) for v in q], "local_translation": [round(v, 6) for v in loc.translation],
        })
    return rows


# --------------------------------------------------------------------------------------------
# small math helpers
# --------------------------------------------------------------------------------------------
def frame_from(primary, secondary):
    """Orthonormal 3x3 whose columns are (p, s_perp, p x s_perp)."""
    p = primary.normalized()
    s = (secondary - p * secondary.dot(p))
    if s.length < 1e-6:
        s = Vector((0, 0, 1)) if abs(p.z) < 0.9 else Vector((1, 0, 0))
        s = s - p * s.dot(p)
    s.normalize()
    return Matrix((p, s, p.cross(s))).transposed()


def swing(a, b):
    """Minimal rotation (3x3) taking direction a onto direction b."""
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


def qslerp(a, b, t):
    if a.dot(b) < 0:
        b = -b
    return a.slerp(b, t)


def qangle_deg(a, b):
    """Angle between two rotations in degrees, well-conditioned near zero (atan2, not acos)."""
    d = a.conjugated() @ b
    return math.degrees(2 * math.atan2(math.sqrt(d.x * d.x + d.y * d.y + d.z * d.z), abs(d.w)))


def yaw_matrix(angle):
    return Matrix.Rotation(angle, 3, "Z")


# --------------------------------------------------------------------------------------------
# source: glTF / GLB
# --------------------------------------------------------------------------------------------
class GltfSource:
    """Reads a GLB's node hierarchy + one named animation. World data in Blender coordinates."""

    def __init__(self, path, anim_name, label=None, wrap=False):
        """wrap: the clip is cyclic WITHOUT a duplicated end key (last key = one frame before the
        first): sampling past the last key interpolates back to the first; period = keys * dt."""
        self.path, self.anim_name = path, anim_name
        self.label = label or anim_name
        self.wrap = wrap
        data = open(path, "rb").read()
        magic, _ver, _len = struct.unpack_from("<III", data, 0)
        assert magic == 0x46546C67, "not a GLB"
        clen = struct.unpack_from("<I", data, 12)[0]
        self.gl = json.loads(data[20:20 + clen])
        off = 20 + clen
        blen = struct.unpack_from("<I", data, off)[0]
        self.bin = data[off + 8: off + 8 + blen]
        self.nodes = self.gl["nodes"]
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.index = {n.get("name", "node%d" % i): i for i, n in enumerate(self.nodes)}
        self.order = []  # parents first
        seen = set()

        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i)
            self.order.append(i)

        for i in range(len(self.nodes)):
            visit(i)
        anims = [a for a in self.gl.get("animations", []) if a.get("name") == anim_name]
        if not anims:
            raise KeyError("animation %r not in %s" % (anim_name, path))
        anim = anims[0]
        self.channels = {}  # (node, path) -> (times, values, interp)
        t0, t1 = 1e9, -1e9
        for ch in anim["channels"]:
            s = anim["samplers"][ch["sampler"]]
            times = self._acc(s["input"]).reshape(-1)
            vals = self._acc(s["output"])
            interp = s.get("interpolation", "LINEAR")
            if interp == "CUBICSPLINE":  # keep the value of each (in, value, out) triplet
                vals = vals.reshape(len(times), 3, -1)[:, 1, :]
                interp = "LINEAR"
            self.channels[(ch["target"]["node"], ch["target"]["path"])] = (times, vals, interp)
            t0, t1 = min(t0, float(times[0])), max(t1, float(times[-1]))
        self.t0, self.t1 = t0, t1
        self.dt = 0.0
        if wrap:
            self.dt = min(float(np.min(np.diff(c[0]))) for c in self.channels.values() if len(c[0]) > 2)
            self.t1 = t1 + self.dt
        self.duration = self.t1 - t0
        self._rest = self._world(None)

    def _acc(self, i):
        a = self.gl["accessors"][i]
        bv = self.gl["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
        dt = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32, 5122: np.int16,
              5120: np.int8}[a["componentType"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride")
        isz = np.dtype(dt).itemsize
        if stride and stride != n * isz:
            raw = np.frombuffer(self.bin, dtype=np.uint8, count=stride * a["count"], offset=off)
            arr = np.stack([np.frombuffer(raw[k * stride:k * stride + n * isz].tobytes(), dtype=dt) for k in range(a["count"])])
        else:
            arr = np.frombuffer(self.bin, dtype=dt, count=a["count"] * n, offset=off).reshape(a["count"], n)
        arr = arr.astype(np.float64)
        if a.get("normalized"):
            arr = arr / float(np.iinfo(dt).max)
        return arr

    def _sample_channel(self, key, t):
        times, vals, interp = self.channels[key]
        if self.wrap and t > times[-1]:
            period = self.t1 - self.t0
            t = self.t0 + ((t - self.t0) % period)
            if t > times[-1]:  # between the last key and the first key of the next cycle
                u = (t - times[-1]) / (self.t0 + period - times[-1] + times[0] - self.t0)
                a, b = vals[-1], vals[0]
                if key[1] == "rotation":
                    q = qslerp(Quaternion((a[3], a[0], a[1], a[2])), Quaternion((b[3], b[0], b[1], b[2])), u)
                    return np.array((q.x, q.y, q.z, q.w))
                return a + (b - a) * u
        if t <= times[0]:
            return vals[0]
        if t >= times[-1]:
            return vals[-1]
        k = int(np.searchsorted(times, t, side="right")) - 1
        if interp == "STEP":
            return vals[k]
        u = (t - times[k]) / (times[k + 1] - times[k])
        a, b = vals[k], vals[k + 1]
        if key[1] == "rotation":
            qa = Quaternion((a[3], a[0], a[1], a[2]))
            qb = Quaternion((b[3], b[0], b[1], b[2]))
            q = qslerp(qa, qb, u)
            return np.array((q.x, q.y, q.z, q.w))
        return a + (b - a) * u

    def _local(self, i, t):
        n = self.nodes[i]
        if "matrix" in n:
            return Matrix(np.array(n["matrix"]).reshape(4, 4).T.tolist())
        tr = n.get("translation", [0, 0, 0])
        ro = n.get("rotation", [0, 0, 0, 1])
        sc = n.get("scale", [1, 1, 1])
        if t is not None:
            if (i, "translation") in self.channels:
                tr = self._sample_channel((i, "translation"), t)
            if (i, "rotation") in self.channels:
                ro = self._sample_channel((i, "rotation"), t)
            if (i, "scale") in self.channels:
                sc = self._sample_channel((i, "scale"), t)
        q = Quaternion((ro[3], ro[0], ro[1], ro[2])).normalized()
        m = q.to_matrix().to_4x4() @ Matrix.Diagonal((sc[0], sc[1], sc[2], 1.0))
        m.translation = Vector(tr)
        return m

    def _world(self, t):
        w = {}
        for i in self.order:
            m = self._local(i, t)
            if i in self.parent:
                m = w[self.parent[i]] @ m
            w[i] = m
        out = {}
        for i, m in w.items():
            name = self.nodes[i].get("name", "node%d" % i)
            out[name] = (A_GLTF @ m.translation, (A_GLTF @ m.to_3x3()).normalized())
        return out

    def rest(self):
        return self._rest

    def sample(self, t):
        return self._world(t)


# --------------------------------------------------------------------------------------------
# source: CMU ASF/AMC
# --------------------------------------------------------------------------------------------
def _euler_xyz(deg):
    """ASF/AMC convention (static XYZ): R = Rz . Ry . Rx."""
    rx, ry, rz = (math.radians(v) for v in deg)
    return (Matrix.Rotation(rz, 3, "Z") @ Matrix.Rotation(ry, 3, "Y") @ Matrix.Rotation(rx, 3, "X"))


class AmcSource:
    """CMU mocap: an ASF skeleton + one AMC motion. Joint heads plus '<bone>.tail'.

    fps: the CMU site lists every trial used here at 120 fps, which is right for subject 113
    (its walk: 94 steps/min, 1.0 m/s) but not for 141, whose walks would then run at
    220 steps/min and 2.4 m/s; at 60 fps they are 111 steps/min, 1.23 m/s (natural). So the frame
    rate is per subject, measured from gait cadence (CMU_FPS; README "CMU frame rate")."""

    def __init__(self, asf_path, amc_path, label=None, fps=None):
        if fps is None:
            fps = CMU_FPS[os.path.basename(asf_path).split(".")[0]]
        self.path = amc_path
        self.label = label or os.path.basename(amc_path)
        self.fps = fps
        self.bones = {}
        self.children = {}
        sec = None
        cur = None
        for raw in open(asf_path, encoding="latin1"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(":"):
                sec = line.split()[0]
                continue
            tok = line.split()
            if sec == ":bonedata":
                if tok[0] == "begin":
                    cur = {"dof": []}
                elif tok[0] == "end":
                    self.bones[cur["name"]] = cur
                elif tok[0] == "name":
                    cur["name"] = tok[1]
                elif tok[0] == "direction":
                    cur["dir"] = Vector([float(v) for v in tok[1:4]])
                elif tok[0] == "length":
                    cur["len"] = float(tok[1]) * CMU_UNIT
                elif tok[0] == "axis":
                    assert tok[4] == "XYZ"
                    cur["C"] = _euler_xyz([float(v) for v in tok[1:4]])
                elif tok[0] == "dof":
                    cur["dof"] = tok[1:]
            elif sec == ":hierarchy":
                if tok[0] in ("begin", "end"):
                    continue
                self.children[tok[0]] = tok[1:]
        self.parent = {c: p for p, cs in self.children.items() for c in cs}
        self.order = []

        def visit(n):
            self.order.append(n)
            for c in self.children.get(n, []):
                visit(c)

        visit("root")
        self.frames = []
        cur = None
        for raw in open(amc_path, encoding="latin1"):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(":"):
                continue
            tok = line.split()
            if len(tok) == 1 and tok[0].isdigit():
                cur = {}
                self.frames.append(cur)
                continue
            cur[tok[0]] = [float(v) for v in tok[1:]]
        self.t0 = 0.0
        self.t1 = (len(self.frames) - 1) / fps
        self.duration = self.t1
        self._cache = {}
        self._rest = self._world_frame(None)

    def _world_frame(self, k):
        f = self.frames[k] if k is not None else {}
        G = {}
        head = {}
        tails = {}
        out = {}
        for n in self.order:
            if n == "root":
                v = f.get("root", [0, 0, 0, 0, 0, 0])
                pos = Vector(v[:3]) * CMU_UNIT
                G[n] = _euler_xyz(v[3:6])
                head[n] = pos
                tail = pos
            else:
                b = self.bones[n]
                vals = f.get(n, [])
                ang = [0.0, 0.0, 0.0]
                for d, val in zip(b["dof"], vals):
                    ang["xyz".index(d[1])] = val
                M = _euler_xyz(ang)
                G[n] = G[self.parent[n]] @ b["C"] @ M @ b["C"].inverted()
                head[n] = tails[self.parent[n]]
                tail = head[n] + G[n] @ (b["dir"].normalized() * b["len"])
            tails[n] = tail
            # rest frame of every bone = global identity -> world "frame" = A . G
            out[n] = (A_CMU @ head[n], (A_CMU @ G[n]).normalized())
            out[n + ".tail"] = (A_CMU @ tail, out[n][1])
        return out

    def rest(self):
        # rest frames are A (identity in CMU coords) for every bone
        return {k: (p, A_CMU.copy()) for k, (p, _r) in self._rest.items()}

    def frame(self, k):
        if k not in self._cache:
            self._cache[k] = self._world_frame(k)
        return self._cache[k]

    def sample(self, t):
        x = t * self.fps
        k = int(math.floor(x))
        k = max(0, min(k, len(self.frames) - 1))
        k2 = min(k + 1, len(self.frames) - 1)
        u = x - k
        a, b = self.frame(k), self.frame(k2)
        if u < 1e-6 or k2 == k:
            return a
        out = {}
        for name, (pa, ra) in a.items():
            pb, rb = b[name]
            q = qslerp(ra.to_quaternion(), rb.to_quaternion(), u)
            out[name] = (pa.lerp(pb, u), q.to_matrix())
        return out


def heading(src, joint, t0, t1, steps=24):
    """Mean facing yaw (rad, 0 = facing -Y, positive = turned toward +X... i.e. CCW about +Z)
    of `joint` over [t0, t1], from its world rotation applied to the rest facing (-Y)."""
    rest_R = src.rest()[joint][1]
    sx = sy = 0.0
    for k in range(steps + 1):
        t = t0 + (t1 - t0) * k / steps
        D = src.sample(t)[joint][1] @ rest_R.inverted()
        f = D @ Vector((0, -1, 0))
        a = math.atan2(f.x, -f.y)
        sx += math.cos(a)
        sy += math.sin(a)
    return math.atan2(sy, sx)


def travel_heading(src, joint, t0, t1):
    """Yaw of the horizontal travel direction (same convention as heading())."""
    a = src.sample(t0)[joint][0]
    b = src.sample(t1)[joint][0]
    d = b - a
    return math.atan2(d.x, -d.y)


def find_loop(src, joints, t_lo, t_hi, p_min, p_max, step=1.0 / 60, vel_dt=0.1):
    """Best (t0, t1) with t0 in [t_lo, t_hi], period in [p_min, p_max] whose poses match:
    joint positions relative to `joints[0]` (root) and their velocities over `vel_dt`
    (so a swinging foot only matches the same swing phase), plus root height and velocity."""
    root = joints[0]
    cache = {}

    def F(t):
        key = round(t / step)
        if key not in cache:
            w = src.sample(key * step)
            w2 = src.sample(key * step + vel_dt)
            r, r2 = w[root][0], w2[root][0]
            Rr = w[root][1].inverted()
            rot = [(Rr @ w[j][1]).to_quaternion() for j in joints]  # joints vs root (+ root tilt)
            rot[0] = w[root][1].to_quaternion()
            rel = [w[j][0] - r for j in joints[1:]]
            rel2 = [w2[j][0] - r2 for j in joints[1:]]
            cache[key] = (rot, [b - a for a, b in zip(rel, rel2)], r.z, r2 - r)
        return cache[key]

    def ang(qa, qb):
        d = abs(qa.dot(qb))
        return 2 * math.acos(min(1.0, d))

    best = (1e9, None, None)
    t0 = t_lo
    while t0 <= t_hi:
        a = F(t0)
        p = p_min
        while p <= p_max:
            b = F(t0 + p)
            e = (sum(ang(x, y) for x, y in zip(a[0][1:], b[0][1:]))
                 + sum((x - y).length for x, y in zip(a[1], b[1])) * 2
                 + abs(a[2] - b[2]) * 3 + (a[3] - b[3]).length * 0.5)
            if e < best[0]:
                best = (e, t0, t0 + p)
            p += step
        t0 += step
    return best


# --------------------------------------------------------------------------------------------
# bone maps
# --------------------------------------------------------------------------------------------
def _side(spec, s):
    if isinstance(spec, str):
        return spec.replace("{s}", s)
    if isinstance(spec, (list, tuple)):
        return type(spec)(_side(x, s) for x in spec)
    if isinstance(spec, dict):
        return {k: _side(v, s) for k, v in spec.items()}
    return spec


def expand_map(m):
    """'{s}' placeholders -> l/r pairs. Source side tokens use {S} (e.g. KayKit '.l'), {c} (CMU 'l')."""
    out = {}
    for tgt, spec in m.items():
        if "{s}" in tgt:
            for s in ("l", "r"):
                sp = json.loads(json.dumps(spec).replace("{S}", s).replace("{c}", s))
                out[tgt.replace("{s}", s)] = _side(sp, s)
        else:
            out[tgt] = spec
    return out


# Target segments: bone head -> named joint head ('@tail' = own tail).
TGT_TIP = {
    "pelvis": "spine_01", "spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "neck_01",
    "neck_01": "head", "head": "@tail",
    "clavicle_{s}": "upperarm_{s}", "upperarm_{s}": "lowerarm_{s}", "lowerarm_{s}": "hand_{s}",
    "hand_{s}": "middle_01_{s}", "thigh_{s}": "calf_{s}", "calf_{s}": "foot_{s}", "foot_{s}": "ball_{s}",
    "ball_{s}": "@tail",
}
for _f in FINGERS:
    TGT_TIP["%s_01_{s}" % _f] = "%s_02_{s}" % _f
    TGT_TIP["%s_02_{s}" % _f] = "%s_03_{s}" % _f
    TGT_TIP["%s_03_{s}" % _f] = "@tail"
TGT_TIP = expand_map(TGT_TIP)


def tgt_dir(rest, bone):
    tip = TGT_TIP.get(bone, "@tail")
    end = rest[bone]["tail"] if tip == "@tail" else rest[tip]["head"]
    return end - rest[bone]["head"]


def palm_vec(rest, s):
    """Across-the-palm vector (pinky -> index knuckles) at the canonical rest."""
    return rest["index_01_" + s]["head"] - rest["pinky_01_" + s]["head"]


# --------------------------------------------------------------------------------------------
# retarget
# --------------------------------------------------------------------------------------------
def build_alignment(rest, src_rest, bmap):
    """Align[b]: world rotation taking the target rest bone onto the source rest posture."""
    align = {}
    for b, spec in bmap.items():
        mode = spec.get("align", "identity")
        if mode == "identity":
            align[b] = Matrix.Identity(3)
            continue
        d_t = tgt_dir(rest, b)
        tip = spec["tip"]
        src_j = spec["src"] if isinstance(spec["src"], str) else spec["src"][0][0]
        d_s = src_rest[tip][0] - src_rest[src_j][0]
        if mode == "swing":
            align[b] = swing(d_t, d_s)
        elif mode == "frame":
            sec_t = spec["sec_tgt"]
            if isinstance(sec_t, str) and sec_t.startswith("palm_"):
                sec_t = palm_vec(rest, sec_t[5:])
            else:
                sec_t = Vector(sec_t)
            sec_s = spec["sec_src"]
            if isinstance(sec_s, (list, tuple)) and len(sec_s) == 2 and isinstance(sec_s[0], str):
                sec_s = src_rest[sec_s[0]][0] - src_rest[sec_s[1]][0]
            else:
                sec_s = Vector(sec_s)
            align[b] = frame_from(d_s, sec_s) @ frame_from(d_t, sec_t).transposed()
        else:
            raise ValueError(mode)
    return align


def src_delta(spec, src_now, src_rest):
    """Source joint world rotation away from its rest; a list spec blends joints by weight."""
    def one(j):
        return src_now[j][1] @ src_rest[j][1].inverted()
    s = spec["src"]
    if isinstance(s, str):
        return one(s)
    (ja, _wa), (jb, wb) = s
    qa, qb = one(ja).to_quaternion(), one(jb).to_quaternion()
    return qslerp(qa, qb, wb).to_matrix()


def world_to_local(rest, world):
    """Per-bone world rotations (3x3, all 53) -> local pose quaternions relative to rest."""
    q = {}
    for b in BONES:
        Rb = rest[b]["R"]
        p = rest[b]["parent"]
        if p is None:
            basis = Rb.inverted() @ world[b]
        else:
            basis = Rb.inverted() @ rest[p]["R"] @ world[p].inverted() @ world[b]
        q[b] = basis.to_quaternion().normalized()
    return q


def local_to_world(rest, q):
    world = {}
    for b in BONES:
        p = rest[b]["parent"]
        Rb = rest[b]["R"]
        if p is None:
            world[b] = Rb @ q[b].to_matrix()
        else:
            world[b] = world[p] @ rest[p]["R"].inverted() @ Rb @ q[b].to_matrix()
    return world


class Clip:
    """Retargeted clip on the canonical rig: frames 0..n (n+1 samples at 30 fps)."""

    def __init__(self, name, n):
        self.name = name
        self.n = n
        self.q = {b: [Quaternion() for _ in range(n + 1)] for b in BONES}
        self.pelvis = [Vector((0, 0, 0)) for _ in range(n + 1)]  # pelvis head, armature space
        self.loop = True
        self.meta = {}

    @property
    def frames(self):
        return self.n + 1


def retarget(src, bmap, rest, t_start, t_end, name, yaw=0.0, k_hip=None, loop=True, frames=None,
             finger_pose=None, hip_ref=None):
    """Sample src over [t_start, t_end] at 30 fps onto the canonical rest. Returns a Clip.

    yaw: rotation (rad, about +Z) applied to the source motion so the character faces -Y.
    k_hip: scale for the pelvis displacement (target hip height / source hip height).
    hip_ref: source pelvis position that maps onto the target rest pelvis (default: source rest).
    finger_pose: {bone: Quaternion} local rotations for unmapped finger bones.
    """
    src_rest = src.rest()
    align = build_alignment(rest, src_rest, bmap)
    n = frames if frames else max(1, int(round((t_end - t_start) * FPS)))
    clip = Clip(name, n)
    clip.loop = loop
    Y = yaw_matrix(yaw)
    pel_src = bmap["pelvis"]["src"]
    hip_src = Vector(hip_ref) if hip_ref is not None else src_rest[pel_src][0]
    if k_hip is None:
        k_hip = rest["pelvis"]["head"].z / hip_src.z
    clip.meta.update({"source": src.label, "t_start": t_start, "t_end": t_end, "k_hip": k_hip,
                      "yaw_deg": math.degrees(yaw)})
    for i in range(n + 1):
        t = t_start + (t_end - t_start) * i / n
        now = src.sample(t)
        world = {}
        for b in BONES:
            p = rest[b]["parent"]
            if b in bmap:
                D = Y @ src_delta(bmap[b], now, src_rest)
                world[b] = D @ align[b] @ rest[b]["R"]
            else:
                # unmapped: keep rest local rotation (or the finger preset) under the parent
                local = finger_pose.get(b, Quaternion()) if finger_pose else Quaternion()
                if p is None:
                    world[b] = rest[b]["R"] @ local.to_matrix()
                else:
                    world[b] = world[p] @ rest[p]["R"].inverted() @ rest[b]["R"] @ local.to_matrix()
        q = world_to_local(rest, world)
        for b in BONES:
            clip.q[b][i] = q[b]
        ps = Y @ now[pel_src][0]
        clip.pelvis[i] = rest["pelvis"]["head"] + (ps - Y @ hip_src) * k_hip
    fix_signs(clip)
    return clip


# --------------------------------------------------------------------------------------------
# clip cleanup
# --------------------------------------------------------------------------------------------
def fix_signs(clip):
    for b in BONES:
        qs = clip.q[b]
        if qs[0].w < 0:
            qs[0] = -qs[0]
        for i in range(1, len(qs)):
            if qs[i].dot(qs[i - 1]) < 0:
                qs[i] = -qs[i]


def close_loop(clip, pelvis_xy=True):
    """Spread the end-vs-start residual linearly over the clip so frame n == frame 0 exactly."""
    n = clip.n
    err = {}
    for b in BONES:
        q0, qn = clip.q[b][0], clip.q[b][n]
        e = q0 @ qn.inverted()  # rotation taking frame n to frame 0 (left-multiplied)
        if e.w < 0:
            e = -e
        err[b] = qangle_deg(qn, q0)
        for i in range(n + 1):
            corr = Quaternion().slerp(e, i / n)
            clip.q[b][i] = (corr @ clip.q[b][i]).normalized()
    d = clip.pelvis[0] - clip.pelvis[n]
    perr = d.length
    for i in range(n + 1):
        clip.pelvis[i] = clip.pelvis[i] + d * (i / n)
    for b in BONES:
        clip.q[b][n] = clip.q[b][0].copy()
    clip.pelvis[n] = clip.pelvis[0].copy()
    fix_signs(clip)
    clip.meta["loop_fix_max_deg"] = round(max(err.values()), 3)
    clip.meta["loop_fix_worst_bone"] = max(err, key=err.get)
    clip.meta["loop_fix_pelvis_m"] = round(perr, 4)
    return err


def remove_root_motion(clip, rest, keep_mean=False):
    """In-place: subtract the linear horizontal trend of the pelvis (keeps bob and sway).

    Returns the removed horizontal travel per clip (metres, armature space)."""
    n = clip.n
    travel = clip.pelvis[n] - clip.pelvis[0]
    travel.z = 0
    xs = [p.copy() for p in clip.pelvis]
    mean = Vector((0, 0, 0))
    for i in range(n + 1):
        xs[i] = xs[i] - travel * (i / n)
        mean += xs[i]
    mean /= (n + 1)
    target = rest["pelvis"]["head"]
    for i in range(n + 1):
        p = xs[i]
        if not keep_mean:
            p = Vector((p.x - mean.x + target.x, p.y - mean.y + target.y, p.z))
        clip.pelvis[i] = p
    return travel


def smooth_bones(clip, bones, passes=1):
    """Light 1-2-1 smoothing of local rotations (CMU hands are noisy). Loop-aware."""
    n = clip.n
    for _ in range(passes):
        for b in bones:
            qs = clip.q[b]
            new = []
            for i in range(n + 1):
                if clip.loop:
                    a = qs[(i - 1) % n]
                    c = qs[(i + 1) % n]
                else:
                    a = qs[max(0, i - 1)]
                    c = qs[min(n, i + 1)]
                mid = qslerp(a, c, 0.5)
                new.append(qslerp(qs[i], mid, 0.5).normalized())
            if clip.loop:
                new[n] = new[0].copy()
            clip.q[b] = new
    fix_signs(clip)


def set_static(clip, pose):
    """Overwrite bones with a constant local rotation (e.g. relaxed fingers)."""
    for b, q in pose.items():
        clip.q[b] = [q.copy() for _ in range(clip.n + 1)]


# --------------------------------------------------------------------------------------------
# forward kinematics on the canonical rest (numpy-free, mathutils)
# --------------------------------------------------------------------------------------------
def fk(rest, clip, i):
    """World 4x4 for every bone at frame i (armature space)."""
    w = {}
    for b in BONES:
        r = rest[b]
        basis = clip.q[b][i].to_matrix().to_4x4()
        if b == "pelvis":
            # pelvis head placed at clip.pelvis[i]
            pass
        p = r["parent"]
        if p is None:
            m = r["M"] @ basis
        else:
            m = w[p] @ rest[p]["M"].inverted() @ r["M"] @ basis
        if b == "pelvis":
            m.translation = clip.pelvis[i]
        w[b] = m
    return w


def sole_points(rest):
    """Foot contact points in each foot bone's rest-local space: heel, ball, toe."""
    pts = {}
    for s in ("l", "r"):
        foot = rest["foot_" + s]
        inv = foot["M"].inverted()
        ankle = foot["head"]
        ball = rest["ball_" + s]["head"]
        toe = rest["ball_" + s]["tail"]
        heel = Vector((ankle.x, ankle.y + 0.035, 0.0))
        # heel and ball ride the foot bone; the toe tip rides the ball (toe) bone
        pts[s] = {"heel": inv @ heel, "ball": inv @ Vector((ball.x, ball.y, 0.0)),
                  "toe": rest["ball_" + s]["M"].inverted() @ Vector((toe.x, toe.y, 0.0))}
    return pts


def foot_track(rest, clip):
    """Per frame: world sole points per side + ankle head. Ground at z=0."""
    sp = sole_points(rest)
    out = []
    for i in range(clip.n + 1):
        w = fk(rest, clip, i)
        fr = {}
        for s in ("l", "r"):
            m = w["foot_" + s]
            fr[s] = {k: (w["ball_" + s] if k == "toe" else m) @ v for k, v in sp[s].items()}
            fr[s]["ankle"] = m.translation.copy()
        out.append(fr)
    return out


def ground_offset(rest, clip, mode="min"):
    """Shift the pelvis vertically so the feet meet the floor (z=0).

    mode 'min': lowest sole point (heel/ball/toe) over the clip touches z=0.
    mode 'min_hb': lowest heel/ball point touches z=0 (locomotion: the toe tip is handled by
        toe_floor, otherwise a rigid toe poking down at toe-off lifts the whole stance).
    mode 'planted': mean of the per-frame lowest sole point = 0 (idle / sit, feet planted)."""
    tr = foot_track(rest, clip)
    keys = ("heel", "ball") if mode == "min_hb" else ("heel", "ball", "toe")
    lows = [min(fr[s][k].z for s in ("l", "r") for k in keys) for fr in tr]
    dz = -min(lows) if mode in ("min", "min_hb") else -sum(lows) / len(lows)
    for i in range(clip.n + 1):
        clip.pelvis[i] = clip.pelvis[i] + Vector((0, 0, dz))
    clip.meta["ground_dz_m"] = round(dz, 4)
    return dz


def plant_feet(rest, clip):
    """Planted clips: pin each foot (IK) at its mean ankle position and orientation, moved
    vertically so that foot's mean lowest sole point sits exactly on the floor. Fixes a foot
    hovering above (or sinking into) the floor while the other one carries the ground offset."""
    tr = foot_track(rest, clip)
    tracks = [fk(rest, clip, i) for i in range(clip.n + 1)]
    targets = {}
    for s in ("l", "r"):
        low = sum(min(fr[s][k].z for k in ("heel", "ball", "toe")) for fr in tr) / len(tr)
        a = Vector((0, 0, 0))
        for w in tracks:
            a += w["foot_" + s].translation
        a /= len(tracks)
        R = mean_rotation([w["foot_" + s].to_3x3().normalized() for w in tracks])
        targets[s] = (a - Vector((0, 0, low)), R)
    pin_feet(rest, clip, targets=targets)
    return {s: round(-(targets[s][0].z - sum(w["foot_" + s].translation.z for w in tracks) / len(tracks)), 4)
            for s in ("l", "r")}


def toe_floor(rest, clip, max_deg=60.0):
    """Bend the toes (ball bone, about the foot's lateral axis) just enough that the toe tip never
    goes below the floor: at toe-off the foot rolls over the ball, the toes stay down."""
    tip_local = {}
    for s in ("l", "r"):
        b = rest["ball_" + s]
        toe = b["tail"]
        tip_local[s] = b["M"].inverted() @ Vector((toe.x, toe.y, 0.0))
    axis = {s: (rest["ball_" + s]["R"].inverted() @ Vector((1, 0, 0))).normalized() for s in ("l", "r")}
    bent = 0
    worst = 0.0
    for i in range(clip.n + 1):
        w = fk(rest, clip, i)
        for s in ("l", "r"):
            q0 = clip.q["ball_" + s][i]
            foot_w = w["foot_" + s]
            ball_rest_in_foot = rest["foot_" + s]["M"].inverted() @ rest["ball_" + s]["M"]

            def tip_z(theta):
                q = q0 @ Quaternion(axis[s], math.radians(theta))
                m = foot_w @ ball_rest_in_foot @ q.to_matrix().to_4x4()
                return (m @ tip_local[s]).z

            if tip_z(0.0) >= 0.0:
                continue
            # positive turn about +X lowers the toes (forward = -Y): search negative angles
            lo, hi = 0.0, -max_deg
            if tip_z(hi) < 0.0:
                theta = hi
            else:
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if tip_z(mid) < 0.0:
                        lo = mid
                    else:
                        hi = mid
                theta = hi
            clip.q["ball_" + s][i] = (q0 @ Quaternion(axis[s], math.radians(theta))).normalized()
            bent += 1
            worst = min(worst, theta)
    fix_signs(clip)
    return {"frames_bent": bent, "max_toe_bend_deg": round(-worst, 1)}


def foot_metrics(rest, clip):
    """Planted-foot slide (max horizontal excursion of each foot's sole) + floor penetration."""
    tr = foot_track(rest, clip)
    res = {}
    for s in ("l", "r"):
        ball = [fr[s]["ball"] for fr in tr]
        heel = [fr[s]["heel"] for fr in tr]
        slide = 0.0
        for pts in (ball, heel):
            cx = sum(p.x for p in pts) / len(pts)
            cy = sum(p.y for p in pts) / len(pts)
            slide = max(slide, max(math.hypot(p.x - cx, p.y - cy) for p in pts))
        res["slide_" + s] = round(slide, 4)
        res["min_z_" + s] = round(min(min(p.z for p in ball), min(p.z for p in heel)), 4)
        res["toe_min_z_" + s] = round(min(fr[s]["toe"].z for fr in tr), 4)
        res["max_lift_" + s] = round(max(min(b.z, h.z) for b, h in zip(ball, heel)), 4)
    return res


def max_step_deg(clip):
    """Largest frame-to-frame local rotation of any bone (flip detector)."""
    worst, wb = 0.0, None
    for b in BONES:
        qs = clip.q[b]
        for i in range(1, len(qs)):
            a = qangle_deg(qs[i - 1], qs[i])
            if a > worst:
                worst, wb = a, b
    return round(worst, 2), wb


def loop_error_deg(clip):
    worst = 0.0
    for b in BONES:
        worst = max(worst, qangle_deg(clip.q[b][0], clip.q[b][clip.n]))
    return round(worst, 4), round((clip.pelvis[0] - clip.pelvis[clip.n]).length, 5)


# --------------------------------------------------------------------------------------------
# two-bone leg IK (keeps the result rotation-only: rewrites thigh/calf/foot local rotations)
# --------------------------------------------------------------------------------------------
def pin_feet(rest, clip, frames=None, targets=None, blend=None):
    """Pin each ankle to a fixed world target (default: mean ankle over `frames`) and hold the
    foot's world orientation at its mean. blend[i] in 0..1 fades the pin per frame."""
    frames = list(range(clip.n + 1)) if frames is None else frames
    tracks = [fk(rest, clip, i) for i in range(clip.n + 1)]
    tg = {}
    for s in ("l", "r"):
        if targets and s in targets:
            tg[s] = targets[s]
            continue
        a = Vector((0, 0, 0))
        q = None
        qs = []
        for i in frames:
            a += tracks[i]["foot_" + s].translation
            qs.append(tracks[i]["foot_" + s].to_quaternion())
        a /= len(frames)
        q = qs[0]
        for k, qq in enumerate(qs[1:], 2):
            q = qslerp(q, qq, 1.0 / k)
        tg[s] = (a, q.to_matrix())
    L1 = {s: (rest["calf_" + s]["head"] - rest["thigh_" + s]["head"]).length for s in ("l", "r")}
    L2 = {s: (rest["foot_" + s]["head"] - rest["calf_" + s]["head"]).length for s in ("l", "r")}
    for i in range(clip.n + 1):
        w = tracks[i]
        f = 1.0 if blend is None else blend[i]
        if f <= 0:
            continue
        # a goal out of reach (leg already straight) would leave the foot hovering: lower the
        # pelvis just enough that both legs reach with a little bend left (0.995 of full length)
        drop = 0.0
        for s in ("l", "r"):
            hip = w["thigh_" + s].translation
            goal = w["foot_" + s].translation.lerp(tg[s][0], f)
            reach = (L1[s] + L2[s]) * 0.995
            horiz = math.hypot(goal.x - hip.x, goal.y - hip.y)
            if horiz < reach:
                need_z = goal.z + math.sqrt(reach * reach - horiz * horiz)
                drop = max(drop, hip.z - need_z)
        if drop > 1e-5:
            clip.pelvis[i] = clip.pelvis[i] - Vector((0, 0, drop))
            w = fk(rest, clip, i)
        world = {b: w[b].to_3x3().normalized() for b in BONES}
        for s in ("l", "r"):
            hip = w["thigh_" + s].translation
            knee = w["calf_" + s].translation
            ankle = w["foot_" + s].translation
            goal = ankle.lerp(tg[s][0], f)
            d = goal - hip
            dist = min(d.length, (L1[s] + L2[s]) * 0.9995)
            dn = d.normalized()
            # knee plane from the current pose (pole = current knee offset from the hip-ankle line)
            cur_axis = (ankle - hip)
            pole = (knee - hip) - cur_axis.normalized() * (knee - hip).dot(cur_axis.normalized())
            if pole.length < 1e-5:
                pole = Vector((0, -1, 0))
            pole = pole - dn * pole.dot(dn)
            pole.normalize()
            cos_a = (L1[s] ** 2 + dist ** 2 - L2[s] ** 2) / (2 * L1[s] * dist)
            cos_a = max(-1.0, min(1.0, cos_a))
            a = math.acos(cos_a)
            new_knee = hip + (dn * math.cos(a) + pole * math.sin(a)) * L1[s]
            new_ankle = hip + dn * dist
            th, ca = "thigh_" + s, "calf_" + s
            world[th] = swing(knee - hip, new_knee - hip) @ world[th]
            world[ca] = swing(ankle - knee, new_ankle - new_knee) @ world[ca]
            foot_goal = tg[s][1]
            world["foot_" + s] = qslerp(world["foot_" + s].to_quaternion(), foot_goal.to_quaternion(), f).to_matrix()
            # ball keeps its local rotation: recompute its world from the foot
            fb = "ball_" + s
            world[fb] = world["foot_" + s] @ rest["foot_" + s]["R"].inverted() @ rest[fb]["R"] @ clip.q[fb][i].to_matrix()
        q = world_to_local(rest, world)
        for s in ("l", "r"):
            for b in ("thigh_", "calf_", "foot_", "ball_"):
                clip.q[b + s][i] = q[b + s]
    fix_signs(clip)
    return tg


def flatten_feet(rest, clip, frames=None, max_deg=25.0):
    """Constant pitch fix on each foot so the sole (heel->ball) is level on average over
    `frames` (planted frames; a list, or {side: list}). Returns the correction in degrees."""
    frames = list(range(clip.n + 1)) if frames is None else frames
    sp = sole_points(rest)
    out = {}
    for s in ("l", "r"):
        pitches = []
        for i in (frames[s] if isinstance(frames, dict) else frames):
            w = fk(rest, clip, i)
            m = w["foot_" + s]
            h, b = m @ sp[s]["heel"], m @ sp[s]["ball"]
            v = b - h
            pitches.append(math.atan2(v.z, math.hypot(v.x, v.y)))
        avg = sum(pitches) / len(pitches)
        corr = max(-math.radians(max_deg), min(math.radians(max_deg), -avg))
        out[s] = round(math.degrees(corr), 2)
        # rotate about the foot's lateral axis (world X at rest, mapped into foot-local space)
        R = rest["foot_" + s]["R"]
        axis_local = (R.inverted() @ Vector((1, 0, 0))).normalized()
        # forward is -Y, so a positive turn about +X lowers the toes; raise them by `corr`
        rot = Quaternion(axis_local, -corr)
        for i in range(clip.n + 1):
            clip.q["foot_" + s][i] = (clip.q["foot_" + s][i] @ rot).normalized()
    fix_signs(clip)
    return out


def mean_rotation(mats):
    q = mats[0].to_quaternion()
    for k, m in enumerate(mats[1:], 2):
        q = qslerp(q, m.to_quaternion(), 1.0 / k)
    return q.to_matrix()


def level_head(rest, clip, frames=None, neck_share=0.5):
    """Remove the clip-mean deviation of the head's world orientation from its rest orientation,
    split between neck_01 (share) and head. Returns the removed angle in degrees."""
    frames = list(range(clip.n + 1)) if frames is None else frames
    devs = []
    for i in frames:
        w = local_to_world(rest, {b: clip.q[b][i] for b in BONES})
        devs.append(w["head"] @ rest["head"]["R"].inverted())
    M = mean_rotation(devs)
    C = M.inverted().to_quaternion()
    Cn = Quaternion().slerp(C, neck_share).to_matrix()
    Cq = C.to_matrix()
    for i in range(clip.n + 1):
        world = local_to_world(rest, {b: clip.q[b][i] for b in BONES})
        world["neck_01"] = Cn @ world["neck_01"]
        world["head"] = Cq @ world["head"]
        q = world_to_local(rest, world)
        clip.q["neck_01"][i] = q["neck_01"]
        clip.q["head"][i] = q["head"]
    fix_signs(clip)
    return round(math.degrees(C.angle), 2)


def damp_bones(clip, bones, keep=0.25):
    """Keep only `keep` of each bone's local-rotation deviation from its clip mean
    (q' = mean . slerp(I, mean^-1 . q, keep)). For noisy/fidgety source joints."""
    for b in bones:
        qs = clip.q[b]
        m = qs[0].copy()
        for k, q in enumerate(qs[1:], 2):
            m = qslerp(m, q, 1.0 / k)
        mi = m.inverted()
        for i, q in enumerate(qs):
            dev = mi @ q
            if dev.w < 0:
                dev = -dev
            qs[i] = (m @ Quaternion().slerp(dev, keep)).normalized()
    fix_signs(clip)


def swing_bones_world(rest, clip, bones, axis, deg):
    """Pre-rotate each bone's world orientation by `deg` about the world `axis` (children follow)."""
    R = Matrix.Rotation(math.radians(deg), 3, axis)
    for i in range(clip.n + 1):
        world = local_to_world(rest, {b: clip.q[b][i] for b in BONES})
        for b in bones:
            world[b] = R @ world[b]
        q = world_to_local(rest, world)
        for b in bones:
            clip.q[b][i] = q[b]
    fix_signs(clip)


def anchor_feet(rest, clip, frames=None):
    """Shift the pelvis horizontally so the mean ankle midpoint over `frames` sits where the
    rest ankles are (the character stands/sits on its root; a chair goes behind the feet)."""
    frames = list(range(clip.n + 1)) if frames is None else frames
    mid = Vector((0, 0, 0))
    for i in frames:
        w = fk(rest, clip, i)
        mid += (w["foot_l"].translation + w["foot_r"].translation) / 2
    mid /= len(frames)
    goal = (rest["foot_l"]["head"] + rest["foot_r"]["head"]) / 2
    d = Vector((goal.x - mid.x, goal.y - mid.y, 0))
    for i in range(clip.n + 1):
        clip.pelvis[i] = clip.pelvis[i] + d
    return d


def stance_frames(rest, clip, tol=0.02):
    """Per side: frames whose lowest sole point is within `tol` of that foot's clip minimum."""
    tr = foot_track(rest, clip)
    out = {}
    for s in ("l", "r"):
        lows = [min(fr[s][k].z for k in ("heel", "ball")) for fr in tr]
        m = min(lows)
        out[s] = [i for i, z in enumerate(lows) if z <= m + tol]
    return out


def walk_speed(rest, clip):
    """In-place locomotion: median backward speed (m/s) of the planted foot = walking speed."""
    tr = foot_track(rest, clip)
    st = stance_frames(rest, clip, tol=0.012)
    v = []
    for s in ("l", "r"):
        fr = set(st[s])
        for i in sorted(fr):
            j = i + 1
            if j in fr:
                a = (tr[i][s]["heel"] + tr[i][s]["ball"]) / 2
                b = (tr[j][s]["heel"] + tr[j][s]["ball"]) / 2
                v.append((b.y - a.y) * FPS)  # forward is -Y, so the planted foot moves +Y
    v.sort()
    return v[len(v) // 2] if v else 0.0, len(v)


# --------------------------------------------------------------------------------------------
# relaxed fingers
# --------------------------------------------------------------------------------------------
CURL_DEG = {  # per joint 01/02/03, a relaxed hanging hand
    "thumb": (4, 8, 8), "index": (14, 18, 10), "middle": (17, 22, 12),
    "ring": (20, 24, 13), "pinky": (23, 26, 14),
}


ADDUCT = {"index": 0.45, "ring": 0.45, "pinky": 0.35}  # fraction of the rest spread closed toward the middle finger


def relaxed_fingers(rest, scale=1.0):
    """Local rotations that curl every finger toward the palm (+ a slight thumb tuck), and close
    MakeHuman's rest finger spread partway (a relaxed hand keeps its fingers together)."""
    pose = {}
    for s in ("l", "r"):
        d_mid = (rest["middle_02_" + s]["head"] - rest["middle_01_" + s]["head"]).normalized()
        for f, frac in ADDUCT.items():
            b = "%s_01_%s" % (f, s)
            d = (rest[b]["tail"] - rest[b]["head"]).normalized()
            ax = d.cross(d_mid)
            if ax.length < 1e-6:
                continue
            a = math.acos(max(-1.0, min(1.0, d.dot(d_mid)))) * frac
            pose[b] = Quaternion((rest[b]["R"].inverted() @ ax.normalized()).normalized(), a)
        across = palm_vec(rest, s)
        fwd = rest["middle_01_" + s]["head"] - rest["hand_" + s]["head"]
        n = across.cross(fwd).normalized()
        # palm normal must point to the palm side: toward the body midline at rest (A-pose)
        hand_x = rest["hand_" + s]["head"].x
        if n.x * hand_x > 0:
            n = -n
        for f in FINGERS:
            for k in range(3):
                b = "%s_0%d_%s" % (f, k + 1, s)
                d = (rest[b]["tail"] - rest[b]["head"]).normalized()
                axis_w = d.cross(n)
                if axis_w.length < 1e-6:
                    continue
                axis_l = (rest[b]["R"].inverted() @ axis_w.normalized()).normalized()
                curl = Quaternion(axis_l, math.radians(CURL_DEG[f][k] * scale))
                pose[b] = (pose[b] @ curl) if b in pose else curl
    return pose


# --------------------------------------------------------------------------------------------
# Blender I/O
# --------------------------------------------------------------------------------------------
def write_action(rig, clip, name=None, frame_start=0):
    """Clip -> Blender action with quaternion keys on every bone + pelvis location."""
    name = name or clip.name
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    rest = rest_info(rig)
    pel_R = rest["pelvis"]["R"]
    nfr = clip.n + 1
    frames = [frame_start + i for i in range(nfr)]
    for b in BONES:
        dp = 'pose.bones["%s"].rotation_quaternion' % b
        for c in range(4):
            fc = act.fcurve_ensure_for_datablock(rig, dp, index=c, group_name=b)
            fc.keyframe_points.add(nfr)
            vals = [clip.q[b][i][c] for i in range(nfr)]
            co = [v for pair in zip(frames, vals) for v in pair]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [1] * nfr)  # LINEAR
            fc.update()
    dp = 'pose.bones["pelvis"].location'
    locs = [pel_R.inverted() @ (clip.pelvis[i] - rest["pelvis"]["head"]) for i in range(nfr)]
    for c in range(3):
        fc = act.fcurve_ensure_for_datablock(rig, dp, index=c, group_name="pelvis")
        fc.keyframe_points.add(nfr)
        co = [v for pair in zip(frames, [locs[i][c] for i in range(nfr)]) for v in pair]
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("interpolation", [1] * nfr)
        fc.update()
    act.frame_range = (frame_start, frame_start + clip.n)
    act.use_frame_range = True
    act.use_cyclic = bool(clip.loop)
    for k, v in clip.meta.items():
        try:
            act[k] = v
        except TypeError:
            act[k] = str(v)
    return act


def clip_to_json(clip):
    return {"name": clip.name, "n": clip.n, "loop": clip.loop, "meta": clip.meta,
            "q": {b: [[round(c, 7) for c in q] for q in clip.q[b]] for b in BONES},
            "pelvis": [[round(c, 6) for c in p] for p in clip.pelvis]}


def clip_from_json(d):
    c = Clip(d["name"], d["n"])
    c.loop = d["loop"]
    c.meta = d["meta"]
    c.q = {b: [Quaternion(v) for v in d["q"][b]] for b in BONES}
    c.pelvis = [Vector(p) for p in d["pelvis"]]
    return c
