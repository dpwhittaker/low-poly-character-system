// Assembly step 1–2 (PLAN §4.3): morph bake and joint positions for one descriptor.
// body = basis + Σ wᵢ·Δᵢ over the active targets (sparse), joints = basis + Σ wᵢ·ΔJᵢ.
// Pure TypeScript, no Babylon, so it runs in a Web Worker and in Node tests.

import type { BodyPack } from './bodyPack.ts';
import { macroStack, type Macro } from './macro.ts';

export interface Descriptor {
  macro: Macro;
  /** Region / face sliders by id, each in [-1, 1]. Missing = 0. */
  sliders?: Record<string, number>;
  /** House stylization strength (PLAN §5.5); 1 = the approved look. */
  style?: number;
}

export interface Baked {
  src: Float32Array; // src × 3, glTF metres, not yet grounded
  joints: Float32Array; // pack joints × 3
  /** Lift that puts the ground joint at y = 0 (add to every y). */
  groundLift: number;
  active: Array<[number, number]>; // [target index, weight]
}

/** Every target weight a descriptor implies: macro corners + sliders + house style. */
export function activeTargets(pack: BodyPack, d: Descriptor): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  for (const [name, w] of macroStack(d.macro, pack.meta.macroParts)) {
    const t = pack.targetByName.get(name);
    if (t !== undefined) out.push([t, w]); // MakeHuman ships no baby proportions/breast files
  }
  for (const s of pack.meta.sliders) {
    const v = Math.max(-1, Math.min(1, d.sliders?.[s.id] ?? 0));
    if (v === 0) continue;
    for (const t of v > 0 ? s.pos : s.neg) out.push([t, Math.abs(v)]);
  }
  const style = d.style ?? 1;
  if (style !== 0) for (const [t, w] of pack.meta.style) out.push([t, w * style]);
  return out;
}

export function bakeBody(pack: BodyPack, d: Descriptor): Baked {
  const { meta } = pack;
  const q = meta.quant;
  const src = new Float32Array(pack.srcBasis);
  const joints = new Float32Array(pack.jointBasis);
  const J = meta.joints.length;
  const active = activeTargets(pack, d);
  for (const [t, w] of active) {
    const [off, cnt] = meta.targetRanges[t];
    const s = w * q;
    for (let k = 0; k < cnt; k++) {
      const i = pack.targetIndex[off + k] * 3, o = (off + k) * 3;
      src[i] += s * pack.targetDelta[o];
      src[i + 1] += s * pack.targetDelta[o + 1];
      src[i + 2] += s * pack.targetDelta[o + 2];
    }
    const jo = t * J * 3;
    for (let k = 0; k < J * 3; k++) joints[k] += s * pack.jointDelta[jo + k];
  }
  return { src, joints, groundLift: -joints[meta.groundJoint * 3 + 1], active };
}

/** Bone head positions (glTF metres) from baked joints, per meta.bones. */
export function boneHeads(pack: BodyPack, joints: Float32Array, lift = 0): Float32Array {
  const out = new Float32Array(pack.meta.bones.length * 3);
  pack.meta.bones.forEach((b, i) => {
    if ('joint' in b.head) {
      const j = b.head.joint * 3;
      out[i * 3] = joints[j]; out[i * 3 + 1] = joints[j + 1] + lift; out[i * 3 + 2] = joints[j + 2];
    } else {
      const [a, c, t] = b.head.lerp;
      for (let k = 0; k < 3; k++) out[i * 3 + k] = joints[a * 3 + k] + (joints[c * 3 + k] - joints[a * 3 + k]) * t;
      out[i * 3 + 1] += lift;
    }
  });
  return out;
}

/** Smooth normals on the src topology (area-weighted), so region splits never crease. */
export function srcNormals(pack: BodyPack, src: Float32Array): Float32Array {
  const n = new Float32Array(src.length);
  const { indices, renderSrc } = pack;
  for (let f = 0; f < indices.length; f += 3) {
    const a = renderSrc[indices[f]] * 3, b = renderSrc[indices[f + 1]] * 3, c = renderSrc[indices[f + 2]] * 3;
    const ux = src[b] - src[a], uy = src[b + 1] - src[a + 1], uz = src[b + 2] - src[a + 2];
    const vx = src[c] - src[a], vy = src[c + 1] - src[a + 1], vz = src[c + 2] - src[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const v of [a, b, c]) { n[v] += nx; n[v + 1] += ny; n[v + 2] += nz; }
  }
  for (let i = 0; i < n.length; i += 3) {
    const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1;
    n[i] /= l; n[i + 1] /= l; n[i + 2] /= l;
  }
  return n;
}
