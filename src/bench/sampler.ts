// Custom animation sampler + hierarchy compose for paths B and C
// (PLAN §8.4 #3). Clips are dense typed arrays; sampling is shared by every
// character in the same (state, phase bucket); the per-character work is only
// the hierarchy compose, which writes skin matrices straight into one shared
// float texture (one upload per frame for all characters).
//
// Matrix convention: column vectors, affine 3×4 stored row-major as 12 floats
// [r00 r01 r02 tx | r10 r11 r12 ty | r20 r21 r22 tz]. One matrix = 3 RGBA
// texels, so the GLSL reads 3 texelFetch per matrix (Babylon reads 4).

import { BONE_COUNT, SKELETONS, type CharacterSkeleton } from './skeleton.ts';
import { type Clip, CLIP_FPS, UPPER_MASK } from './clips.ts';

/** Row layout: slot 0 = root (per-character meshes), 1 = root for LOD2 batches,
 *  2 = root for LOD3 batches, then one slot per skeleton bone. */
export const ROOT_SLOTS = 3;
export const SLOTS_PER_ROW = ROOT_SLOTS + BONE_COUNT;
export const TEXELS_PER_ROW = SLOTS_PER_ROW * 3;
export const FLOATS_PER_ROW = TEXELS_PER_ROW * 4;

/** Sample a looping clip at `time` seconds into `out` (BONE_COUNT × 4), nlerp between frames. */
export function sampleClip(clip: Clip, time: number, out: Float32Array) {
  const fpos = (((time * CLIP_FPS) % clip.frames) + clip.frames) % clip.frames;
  const f0 = Math.floor(fpos);
  const f1 = (f0 + 1) % clip.frames;
  const t = fpos - f0;
  const q = clip.quats;
  const a = f0 * BONE_COUNT * 4, b = f1 * BONE_COUNT * 4;
  for (let i = 0; i < BONE_COUNT * 4; i += 4) {
    let x1 = q[b + i], y1 = q[b + i + 1], z1 = q[b + i + 2], w1 = q[b + i + 3];
    const x0 = q[a + i], y0 = q[a + i + 1], z0 = q[a + i + 2], w0 = q[a + i + 3];
    if (x0 * x1 + y0 * y1 + z0 * z1 + w0 * w1 < 0) { x1 = -x1; y1 = -y1; z1 = -z1; w1 = -w1; }
    const x = x0 + (x1 - x0) * t, y = y0 + (y1 - y0) * t, z = z0 + (z1 - z0) * t, w = w0 + (w1 - w0) * t;
    const l = 1 / Math.sqrt(x * x + y * y + z * z + w * w);
    out[i] = x * l; out[i + 1] = y * l; out[i + 2] = z * l; out[i + 3] = w * l;
  }
}

/** out = nlerp(base, overlay, w) on upper-body bones, base elsewhere. */
export function blendUpper(base: Float32Array, overlay: Float32Array, w: number, out: Float32Array) {
  for (let b = 0; b < BONE_COUNT; b++) {
    const i = b * 4;
    if (!UPPER_MASK[b]) { out[i] = base[i]; out[i + 1] = base[i + 1]; out[i + 2] = base[i + 2]; out[i + 3] = base[i + 3]; continue; }
    let x1 = overlay[i], y1 = overlay[i + 1], z1 = overlay[i + 2], w1 = overlay[i + 3];
    const x0 = base[i], y0 = base[i + 1], z0 = base[i + 2], w0 = base[i + 3];
    if (x0 * x1 + y0 * y1 + z0 * z1 + w0 * w1 < 0) { x1 = -x1; y1 = -y1; z1 = -z1; w1 = -w1; }
    const x = x0 + (x1 - x0) * w, y = y0 + (y1 - y0) * w, z = z0 + (z1 - z0) * w, ww = w0 + (w1 - w0) * w;
    const l = 1 / Math.sqrt(x * x + y * y + z * z + ww * ww);
    out[i] = x * l; out[i + 1] = y * l; out[i + 2] = z * l; out[i + 3] = ww * l;
  }
}

/**
 * Shared pose cache: one sampled+blended pose per (state, phase bucket,
 * overlay bucket) key, recomputed once per frame no matter how many characters
 * use it.
 */
export class PoseCache {
  private poses = new Map<number, Float32Array>();
  private stamp = new Map<number, number>();
  private tmpBase = new Float32Array(BONE_COUNT * 4);
  private tmpOver = new Float32Array(BONE_COUNT * 4);
  samples = 0;
  readonly clips: readonly Clip[];
  readonly overlay: Clip;
  readonly overlayWeight: number;
  constructor(clips: readonly Clip[], overlay: Clip, overlayWeight: number) {
    this.clips = clips;
    this.overlay = overlay;
    this.overlayWeight = overlayWeight;
  }
  static key(state: number, bucket: number, obucket: number) { return (state * 64 + bucket) * 64 + obucket; }
  get(frame: number, time: number, state: number, phase: number, ophase: number, key: number): Float32Array {
    let p = this.poses.get(key);
    if (!p) { p = new Float32Array(BONE_COUNT * 4); this.poses.set(key, p); }
    if (this.stamp.get(key) !== frame) {
      this.stamp.set(key, frame);
      sampleClip(this.clips[state], time + phase, this.tmpBase);
      sampleClip(this.overlay, time + ophase, this.tmpOver);
      blendUpper(this.tmpBase, this.tmpOver, this.overlayWeight, p);
      this.samples++;
    }
    return p;
  }
}

/** Write an affine root transform (yaw about +Y, then translate) into `slot` of `row`. */
export function writeRoot(tex: Float32Array, row: number, slot: number, x: number, y: number, z: number, yaw: number, scale = 1) {
  const o = row * FLOATS_PER_ROW + slot * 12;
  const c = Math.cos(yaw) * scale, s = Math.sin(yaw) * scale;
  // Rotation about Y (column vectors): [c 0 s; 0 1 0; -s 0 c]
  tex[o] = c; tex[o + 1] = 0; tex[o + 2] = s; tex[o + 3] = x;
  tex[o + 4] = 0; tex[o + 5] = scale; tex[o + 6] = 0; tex[o + 7] = y;
  tex[o + 8] = -s; tex[o + 9] = 0; tex[o + 10] = c; tex[o + 11] = z;
}

export function zeroSlot(tex: Float32Array, row: number, slot: number) {
  tex.fill(0, row * FLOATS_PER_ROW + slot * 12, row * FLOATS_PER_ROW + slot * 12 + 12);
}

const scratchWorld = new Float32Array(BONE_COUNT * 12);

/**
 * Compose the hierarchy of skeleton LOD `skelLod` for one character from a
 * local pose (LOD0 bone quaternions) and write skin matrices (world × invBind,
 * character space) into the character's row, starting at slot ROOT_SLOTS.
 * Bones dropped at this LOD contribute rest offsets only (their rotation is
 * not applied), exactly as a baked reduced-skeleton clip would.
 */
export function composeCharacter(pose: Float32Array, skel: CharacterSkeleton, skelLod: number, tex: Float32Array, row: number) {
  const sk = SKELETONS[skelLod];
  const off = skel.lodOffsets[skelLod];
  const rest = skel.restWorld;
  const W = scratchWorld;
  const base = row * FLOATS_PER_ROW + ROOT_SLOTS * 12;
  const n = sk.bones.length;
  for (let k = 0; k < n; k++) {
    const b = sk.bones[k];
    const qi = b * 4;
    const x = pose[qi], y = pose[qi + 1], z = pose[qi + 2], w = pose[qi + 3];
    // Local rotation (column-vector convention; same as Babylon's quaternion).
    const xx = x * x, yy = y * y, zz = z * z, xy = x * y, xz = x * z, yz = y * z, wx = w * x, wy = w * y, wz = w * z;
    const l00 = 1 - 2 * (yy + zz), l01 = 2 * (xy - wz), l02 = 2 * (xz + wy);
    const l10 = 2 * (xy + wz), l11 = 1 - 2 * (xx + zz), l12 = 2 * (yz - wx);
    const l20 = 2 * (xz - wy), l21 = 2 * (yz + wx), l22 = 1 - 2 * (xx + yy);
    const tx = off[k * 3], ty = off[k * 3 + 1], tz = off[k * 3 + 2];
    const o = k * 12;
    const p = sk.parents[k];
    if (p < 0) {
      W[o] = l00; W[o + 1] = l01; W[o + 2] = l02; W[o + 3] = tx;
      W[o + 4] = l10; W[o + 5] = l11; W[o + 6] = l12; W[o + 7] = ty;
      W[o + 8] = l20; W[o + 9] = l21; W[o + 10] = l22; W[o + 11] = tz;
    } else {
      const q = p * 12;
      const p00 = W[q], p01 = W[q + 1], p02 = W[q + 2], p03 = W[q + 3];
      const p10 = W[q + 4], p11 = W[q + 5], p12 = W[q + 6], p13 = W[q + 7];
      const p20 = W[q + 8], p21 = W[q + 9], p22 = W[q + 10], p23 = W[q + 11];
      W[o] = p00 * l00 + p01 * l10 + p02 * l20;
      W[o + 1] = p00 * l01 + p01 * l11 + p02 * l21;
      W[o + 2] = p00 * l02 + p01 * l12 + p02 * l22;
      W[o + 3] = p00 * tx + p01 * ty + p02 * tz + p03;
      W[o + 4] = p10 * l00 + p11 * l10 + p12 * l20;
      W[o + 5] = p10 * l01 + p11 * l11 + p12 * l21;
      W[o + 6] = p10 * l02 + p11 * l12 + p12 * l22;
      W[o + 7] = p10 * tx + p11 * ty + p12 * tz + p13;
      W[o + 8] = p20 * l00 + p21 * l10 + p22 * l20;
      W[o + 9] = p20 * l01 + p21 * l11 + p22 * l21;
      W[o + 10] = p20 * l02 + p21 * l12 + p22 * l22;
      W[o + 11] = p20 * tx + p21 * ty + p22 * tz + p23;
    }
    // skin = world × invBind, invBind = translate(−restWorld) (rest rotations are identity)
    const rx = rest[b * 3], ry = rest[b * 3 + 1], rz = rest[b * 3 + 2];
    const d = base + k * 12;
    tex[d] = W[o]; tex[d + 1] = W[o + 1]; tex[d + 2] = W[o + 2];
    tex[d + 3] = W[o + 3] - (W[o] * rx + W[o + 1] * ry + W[o + 2] * rz);
    tex[d + 4] = W[o + 4]; tex[d + 5] = W[o + 5]; tex[d + 6] = W[o + 6];
    tex[d + 7] = W[o + 7] - (W[o + 4] * rx + W[o + 5] * ry + W[o + 6] * rz);
    tex[d + 8] = W[o + 8]; tex[d + 9] = W[o + 9]; tex[d + 10] = W[o + 10];
    tex[d + 11] = W[o + 11] - (W[o + 8] * rx + W[o + 9] * ry + W[o + 10] * rz);
  }
}

/**
 * CPU mirror of the GLSL skinning in shaders.ts, used by tests to prove the
 * texture layout and the math (V8). Returns the world position.
 */
export function skinVertexCPU(tex: Float32Array, row: number, rootSlot: number, p: ArrayLike<number>, bi: ArrayLike<number>, bw: ArrayLike<number>, influences: number): [number, number, number] {
  let x = 0, y = 0, z = 0;
  for (let i = 0; i < influences; i++) {
    const w = bw[i];
    const o = row * FLOATS_PER_ROW + (ROOT_SLOTS + bi[i]) * 12;
    x += w * (tex[o] * p[0] + tex[o + 1] * p[1] + tex[o + 2] * p[2] + tex[o + 3]);
    y += w * (tex[o + 4] * p[0] + tex[o + 5] * p[1] + tex[o + 6] * p[2] + tex[o + 7]);
    z += w * (tex[o + 8] * p[0] + tex[o + 9] * p[1] + tex[o + 10] * p[2] + tex[o + 11]);
  }
  const r = row * FLOATS_PER_ROW + rootSlot * 12;
  return [
    tex[r] * x + tex[r + 1] * y + tex[r + 2] * z + tex[r + 3],
    tex[r + 4] * x + tex[r + 5] * y + tex[r + 6] * z + tex[r + 7],
    tex[r + 8] * x + tex[r + 9] * y + tex[r + 10] * z + tex[r + 11],
  ];
}
