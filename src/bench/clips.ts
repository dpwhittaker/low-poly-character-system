// PLACEHOLDER animation clips for the M0 crowd bench: synthetic, dense,
// rotation-only tracks at 30 Hz for every one of the 60 bones (PLAN §8.4 #3:
// clips are dense rotation-only arrays). The motion only has to be plausible
// enough to read in a screenshot; the cost is what is being measured.

import { BONE, BONE_COUNT, BONES } from './skeleton.ts';

export const CLIP_FPS = 30;

export interface Clip {
  name: string;
  frames: number;
  /** frames × BONE_COUNT × 4 (x, y, z, w) */
  quats: Float32Array;
  /** overlay clips only drive `upper` bones */
  upperOnly: boolean;
}

type Euler = [number, number, number];
type Pose = (theta: number, set: (bone: string, e: Euler) => void) => void;

export function quatFromEuler(x: number, y: number, z: number, out: Float32Array | number[], o = 0) {
  // q = qy * qx * qz (yaw, pitch, roll), the order Babylon's RotationYawPitchRoll uses.
  const cx = Math.cos(x / 2), sx = Math.sin(x / 2);
  const cy = Math.cos(y / 2), sy = Math.sin(y / 2);
  const cz = Math.cos(z / 2), sz = Math.sin(z / 2);
  out[o] = cy * sx * cz + sy * cx * sz;
  out[o + 1] = sy * cx * cz - cy * sx * sz;
  out[o + 2] = cy * cx * sz - sy * sx * cz;
  out[o + 3] = cy * cx * cz + sy * sx * sz;
}

function makeClip(name: string, frames: number, upperOnly: boolean, pose: Pose): Clip {
  const quats = new Float32Array(frames * BONE_COUNT * 4);
  for (let f = 0; f < frames; f++) {
    const base = f * BONE_COUNT * 4;
    for (let b = 0; b < BONE_COUNT; b++) quats[base + b * 4 + 3] = 1;
    const theta = (f / frames) * Math.PI * 2;
    pose(theta, (bone, e) => {
      const b = BONE[bone];
      if (b === undefined) throw new Error('unknown bone ' + bone);
      quatFromEuler(e[0], e[1], e[2], quats, base + b * 4);
    });
  }
  return { name, frames, quats, upperOnly };
}

const ARM_DOWN = 1.15; // radians from T-pose towards the body
const fingersCurl = (set: (b: string, e: Euler) => void, side: string, curl: number) => {
  for (const f of ['index', 'middle', 'ring']) {
    for (const k of ['1', '2', '3']) set(f + k + side, [0, 0, (side === 'L' ? -1 : 1) * curl]);
  }
  set('thumb1' + side, [0.3, 0, 0]);
};

export const IDLE = makeClip('idle', 120, false, (t, set) => {
  set('spine1', [0.02 * Math.sin(t), 0, 0]);
  set('chest', [0.015 * Math.sin(t + 0.5), 0, 0]);
  set('neck', [0.04 * Math.sin(2 * t), 0, 0]);
  set('head', [0, 0.25 * Math.sin(t), 0]);
  for (const [side, s] of [['L', -1], ['R', 1]] as const) {
    set('upperArm' + side, [0, 0, s * (-ARM_DOWN + 0.03 * Math.sin(t))]);
    set('forearm' + side, [0, s * 0.15, 0]);
    fingersCurl(set, side, 0.3);
    set('thigh' + side, [0, 0, s * 0.02 * Math.sin(t)]);
  }
});

export const WALK = makeClip('walk', 32, false, (t, set) => {
  set('hips', [0, 0.08 * Math.sin(t), 0]);
  set('spine1', [0.05, -0.06 * Math.sin(t), 0]);
  set('chest', [0, -0.04 * Math.sin(t), 0]);
  set('head', [0, 0.04 * Math.sin(t), 0]);
  for (const [side, s] of [['L', -1], ['R', 1]] as const) {
    const ph = side === 'L' ? 0 : Math.PI;
    set('thigh' + side, [0.5 * Math.sin(t + ph), 0, 0]);
    set('shin' + side, [-0.7 * Math.max(0, Math.sin(t + ph + 1.2)), 0, 0]);
    set('foot' + side, [0.2 * Math.sin(t + ph + 0.5), 0, 0]);
    set('upperArm' + side, [-0.4 * Math.sin(t + ph), 0, s * -ARM_DOWN]);
    set('forearm' + side, [0, s * (0.3 + 0.15 * Math.sin(t + ph)), 0]);
    fingersCurl(set, side, 0.4);
  }
});

export const TALK = makeClip('talk', 90, false, (t, set) => {
  set('spine1', [0.02 * Math.sin(t), 0.05 * Math.sin(t), 0]);
  set('head', [0.1 * Math.sin(3 * t), 0.15 * Math.sin(t), 0.05 * Math.sin(2 * t)]);
  set('jaw', [0.15 * Math.max(0, Math.sin(6 * t)), 0, 0]);
  set('mouthL', [0, 0.1 * Math.sin(6 * t), 0]);
  set('mouthR', [0, -0.1 * Math.sin(6 * t), 0]);
  set('browL', [0.1 * Math.sin(3 * t), 0, 0]);
  set('browR', [0.1 * Math.sin(3 * t + 0.3), 0, 0]);
  for (const [side, s] of [['L', -1], ['R', 1]] as const) {
    set('upperArm' + side, [-0.3, 0, s * (-ARM_DOWN + 0.2 + 0.1 * Math.sin(2 * t))]);
    set('forearm' + side, [0, s * (0.9 + 0.3 * Math.sin(2 * t + (side === 'L' ? 0 : 1))), 0]);
    set('hand' + side, [0.3 * Math.sin(3 * t), 0, 0]);
    fingersCurl(set, side, 0.2 + 0.2 * Math.sin(2 * t));
  }
});

export const GESTURE = makeClip('gesture', 60, true, (t, set) => {
  set('chest', [0, 0.15 * Math.sin(t), 0]);
  set('head', [0, 0, 0.08 * Math.sin(t)]);
  set('upperArmR', [-0.6 * Math.sin(t) ** 2, 0, -ARM_DOWN + 0.5 * Math.sin(t) ** 2]);
  set('forearmR', [0, 0.8, 0]);
});

export const BASE_CLIPS = [IDLE, WALK, TALK] as const;
export const STATE = { idle: 0, walk: 1, talk: 2 } as const;
export type StateId = 0 | 1 | 2;

/** 1 for bones the upper-body overlay may drive */
export const UPPER_MASK = Uint8Array.from(BONES.map((d) => (d.upper ? 1 : 0)));
