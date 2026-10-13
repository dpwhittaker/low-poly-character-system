// PLACEHOLDER skeleton for the M0 crowd bench — not the real rig.
// 60 bones at LOD0, reduced to 30 (LOD1) and 18 (LOD2/LOD3) per PLAN §8.3.
// Rest rotations are identity: a bone's rest transform is a pure offset from
// its parent, so bind matrices are translations. That keeps the placeholder
// simple without changing the per-frame cost being measured.

import { type Rng, range } from './rng.ts';

export interface BoneDef {
  name: string;
  parent: number;
  offset: [number, number, number];
  /** kept at LOD1 (30 bones) */
  lod1: boolean;
  /** kept at LOD2/LOD3 (18 bones) */
  lod2: boolean;
  /** affected by the upper-body overlay layer */
  upper: boolean;
  /** which proportion knob scales this offset */
  group: 'core' | 'arm' | 'leg' | 'shoulder' | 'hip' | 'face' | 'finger';
}

const defs: BoneDef[] = [];
function bone(name: string, parent: number, offset: [number, number, number], lod1: boolean, lod2: boolean, upper: boolean, group: BoneDef['group']): number {
  defs.push({ name, parent, offset, lod1, lod2, upper, group });
  return defs.length - 1;
}

const root = bone('root', -1, [0, 0, 0], true, true, false, 'core');
const hips = bone('hips', root, [0, 0.95, 0], true, true, false, 'core');
const spine1 = bone('spine1', hips, [0, 0.1, 0], true, true, true, 'core');
const spine2 = bone('spine2', spine1, [0, 0.12, 0], true, false, true, 'core');
const chest = bone('chest', spine2, [0, 0.14, 0], true, true, true, 'core');
const neck = bone('neck', chest, [0, 0.16, 0], true, true, true, 'core');
const head = bone('head', neck, [0, 0.1, 0], true, true, true, 'core');
const jaw = bone('jaw', head, [0, 0.02, 0.04], true, false, true, 'face');
bone('eyeL', head, [-0.032, 0.09, 0.07], true, false, true, 'face');
bone('eyeR', head, [0.032, 0.09, 0.07], true, false, true, 'face');
bone('browL', head, [-0.035, 0.12, 0.075], false, false, true, 'face');
bone('browR', head, [0.035, 0.12, 0.075], false, false, true, 'face');
bone('lidL', head, [-0.032, 0.1, 0.075], false, false, true, 'face');
bone('lidR', head, [0.032, 0.1, 0.075], false, false, true, 'face');
bone('mouthL', jaw, [-0.025, 0.0, 0.05], false, false, true, 'face');
bone('mouthR', jaw, [0.025, 0.0, 0.05], false, false, true, 'face');

for (const s of [-1, 1]) {
  const side = s < 0 ? 'L' : 'R';
  const clav = bone('clav' + side, chest, [s * 0.03, 0.12, 0], true, false, true, 'shoulder');
  const upper = bone('upperArm' + side, clav, [s * 0.15, 0, 0], true, true, true, 'shoulder');
  const upperTwist = bone('upperTwist' + side, upper, [s * 0.13, 0, 0], false, false, true, 'arm');
  const fore = bone('forearm' + side, upperTwist, [s * 0.13, 0, 0], true, true, true, 'arm');
  const foreTwist = bone('foreTwist' + side, fore, [s * 0.12, 0, 0], false, false, true, 'arm');
  const hand = bone('hand' + side, foreTwist, [s * 0.12, 0, 0], true, true, true, 'arm');
  const fingers: [string, [number, number, number]][] = [
    ['thumb', [s * 0.02, -0.01, 0.03]],
    ['index', [s * 0.08, 0, 0.025]],
    ['middle', [s * 0.085, 0, 0]],
    ['ring', [s * 0.08, 0, -0.025]],
  ];
  for (const [f, off] of fingers) {
    const keep1 = f !== 'ring';
    const f1 = bone(f + '1' + side, hand, off, keep1, false, true, 'finger');
    const f2 = bone(f + '2' + side, f1, [s * 0.03, 0, 0], false, false, true, 'finger');
    bone(f + '3' + side, f2, [s * 0.025, 0, 0], false, false, true, 'finger');
  }
}
for (const s of [-1, 1]) {
  const side = s < 0 ? 'L' : 'R';
  const thigh = bone('thigh' + side, hips, [s * 0.09, -0.05, 0], true, true, false, 'hip');
  const shin = bone('shin' + side, thigh, [0, -0.43, 0], true, true, false, 'leg');
  const foot = bone('foot' + side, shin, [0, -0.42, 0], true, true, false, 'leg');
  bone('toe' + side, foot, [0, -0.05, 0.13], false, false, false, 'leg');
}

export const BONES: readonly BoneDef[] = defs;
export const BONE_COUNT = defs.length; // 60
export const BONE = Object.fromEntries(defs.map((d, i) => [d.name, i])) as Record<string, number>;

export const LOD_COUNT = 4;
/** LOD → which skeleton it uses: 0 → full, 1 → lod1 set, 2/3 → lod2 set */
export const LOD_SKELETON = [0, 1, 2, 2] as const;

export interface LodSkeleton {
  /** LOD0 bone index for each LOD slot, in topological order */
  bones: Int32Array;
  /** parent slot (-1 for root) */
  parents: Int32Array;
  /** LOD0 bone → slot of itself or its nearest kept ancestor */
  remap: Int32Array;
}

function buildLodSkeleton(keep: (d: BoneDef) => boolean): LodSkeleton {
  const bones: number[] = [];
  const remap = new Int32Array(BONE_COUNT);
  for (let i = 0; i < BONE_COUNT; i++) {
    if (keep(defs[i])) {
      remap[i] = bones.length;
      bones.push(i);
    } else {
      remap[i] = remap[defs[i].parent];
    }
  }
  const parents = new Int32Array(bones.length);
  for (let k = 0; k < bones.length; k++) {
    const p = defs[bones[k]].parent;
    parents[k] = p < 0 ? -1 : remap[p];
  }
  return { bones: Int32Array.from(bones), parents, remap };
}

export const SKELETONS: readonly LodSkeleton[] = [
  buildLodSkeleton(() => true),
  buildLodSkeleton((d) => d.lod1),
  buildLodSkeleton((d) => d.lod2),
];

export interface Proportions {
  height: number;
  arm: number;
  leg: number;
  shoulder: number;
  hip: number;
  girth: number;
}

export function randomProportions(rng: Rng): Proportions {
  return {
    height: range(rng, 0.88, 1.08),
    arm: range(rng, 0.92, 1.08),
    leg: range(rng, 0.92, 1.1),
    shoulder: range(rng, 0.9, 1.15),
    hip: range(rng, 0.9, 1.2),
    girth: range(rng, 0.85, 1.35),
  };
}

export interface CharacterSkeleton {
  props: Proportions;
  /** LOD0 rest offsets, 3 floats per bone */
  offsets: Float32Array;
  /** rest world (character space) positions, 3 floats per bone */
  restWorld: Float32Array;
  /** per skeleton LOD: rest offsets per slot (accumulated over removed bones) */
  lodOffsets: Float32Array[];
}

export function characterSkeleton(props: Proportions): CharacterSkeleton {
  const offsets = new Float32Array(BONE_COUNT * 3);
  const restWorld = new Float32Array(BONE_COUNT * 3);
  for (let i = 0; i < BONE_COUNT; i++) {
    const d = defs[i];
    let sx = props.height, sy = props.height, sz = props.height;
    if (d.group === 'arm' || d.group === 'finger') { sx *= d.group === 'arm' ? props.arm : 1; }
    if (d.group === 'shoulder') { sx *= props.shoulder; }
    if (d.group === 'hip') { sx *= props.hip; }
    if (d.group === 'leg') { sy *= props.leg; }
    offsets[i * 3] = d.offset[0] * sx;
    offsets[i * 3 + 1] = d.offset[1] * sy * (i === BONE.hips ? props.leg : 1);
    offsets[i * 3 + 2] = d.offset[2] * sz;
    const p = d.parent;
    for (let c = 0; c < 3; c++) restWorld[i * 3 + c] = offsets[i * 3 + c] + (p < 0 ? 0 : restWorld[p * 3 + c]);
  }
  const lodOffsets = SKELETONS.map((sk) => {
    const o = new Float32Array(sk.bones.length * 3);
    for (let k = 0; k < sk.bones.length; k++) {
      const b = sk.bones[k];
      const pk = sk.parents[k];
      for (let c = 0; c < 3; c++) o[k * 3 + c] = restWorld[b * 3 + c] - (pk < 0 ? 0 : restWorld[sk.bones[pk] * 3 + c]);
    }
    return o;
  });
  return { props, offsets, restWorld, lodOffsets };
}
