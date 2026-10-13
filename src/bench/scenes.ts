// Deterministic bench scenes (PLAN §8.5): Plaza-100 (city, dense, near) and
// Meadow-100 (countryside, scattered, far), plus `single` for the draw-call
// self-test. Everything derives from a seed and the frame index, never from
// wall-clock time, so every path and every run sees the same scene.

import { mulberry32, range, type Rng } from './rng.ts';
import { BASE_CLIPS, GESTURE, CLIP_FPS, type StateId } from './clips.ts';

export type SceneName = 'plaza' | 'meadow' | 'single';

export interface CharSpec {
  id: number;
  /** home position (walk circle centre for walkers) */
  hx: number;
  hz: number;
  yaw: number;
  state: StateId;
  /** clip phase offset in seconds, quantized to one of PHASE_BUCKETS (shared sampling) */
  phase: number;
  ophase: number;
  bucket: number;
  obucket: number;
  walk?: { r: number; omega: number; a0: number };
}

export interface CameraPose { pos: [number, number, number]; target: [number, number, number] }

export interface SceneSpec {
  name: SceneName;
  seed: number;
  chars: CharSpec[];
  groundSize: number;
  /** spatial cell size for far-tier batches (path C) */
  cell: number;
  fade: [number, number];
  segments: { name: string; from: number; to: number }[];
  camera: (frame: number, measureFrames: number) => CameraPose;
}

export const PHASE_BUCKETS = 8;
export const OVERLAY_BUCKETS = 4;

function makeChar(rng: Rng, id: number, hx: number, hz: number, yaw: number, state: StateId, walk?: CharSpec['walk']): CharSpec {
  const bucket = Math.floor(rng() * PHASE_BUCKETS);
  const obucket = Math.floor(rng() * OVERLAY_BUCKETS);
  const clip = BASE_CLIPS[state];
  return {
    id, hx, hz, yaw, state, walk, bucket, obucket,
    phase: (bucket / PHASE_BUCKETS) * (clip.frames / CLIP_FPS),
    ophase: (obucket / OVERLAY_BUCKETS) * (GESTURE.frames / CLIP_FPS),
  };
}

/** Character position and yaw at simulation time t (walkers move on circles). */
export function charPose(c: CharSpec, t: number): [number, number, number] {
  if (!c.walk) return [c.hx, c.hz, c.yaw];
  const a = c.walk.a0 + c.walk.omega * t;
  const x = c.hx + c.walk.r * Math.cos(a);
  const z = c.hz + c.walk.r * Math.sin(a);
  // facing the direction of travel (tangent), Babylon yaw about +Y with +Z forward
  const dx = -Math.sin(a) * Math.sign(c.walk.omega), dz = Math.cos(a) * Math.sign(c.walk.omega);
  return [x, z, Math.atan2(dx, dz)];
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerp3 = (a: number[], b: number[], t: number): [number, number, number] => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

function plaza(seed: number): SceneSpec {
  const rng = mulberry32(seed);
  const chars: CharSpec[] = [];
  // Talk groups: group 0 is the conversation-shot pair near the centre.
  const groups: [number, number, number][] = [[0, 2, 2]];
  for (let g = 1; g < 8; g++) groups.push([range(rng, -16, 16), range(rng, -16, 16), rng() < 0.5 ? 2 : 3]);
  for (const [gx, gz, n] of groups) {
    for (let k = 0; k < n; k++) {
      const a = (k / n) * Math.PI * 2 + (gx === 0 ? Math.PI / 2 : rng());
      const x = gx + Math.cos(a) * 0.55, z = gz + Math.sin(a) * 0.55;
      chars.push(makeChar(rng, chars.length, x, z, Math.atan2(gx - x, gz - z), 2));
    }
  }
  while (chars.length < 65) chars.push(makeChar(rng, chars.length, range(rng, -19, 19), range(rng, -19, 19), range(rng, -Math.PI, Math.PI), 0));
  while (chars.length < 100) {
    const r = range(rng, 3, 10);
    chars.push(makeChar(rng, chars.length, range(rng, -14, 14), range(rng, -14, 14), 0, 1, { r, omega: (rng() < 0.5 ? -1 : 1) * range(rng, 1.2, 1.5) / r, a0: range(rng, 0, 6.283) }));
  }
  const pair = groups[0];
  return {
    name: 'plaza', seed, chars, groundSize: 60, cell: 20, fade: [220, 250],
    segments: [{ name: 'conversation', from: 0, to: 1 / 3 }, { name: 'street', from: 1 / 3, to: 2 / 3 }, { name: 'overview', from: 2 / 3, to: 1 }],
    camera: (frame, n) => {
      const u = Math.min(1, Math.max(0, frame / n));
      if (u < 1 / 3) {
        const s = u * 3, a = lerp(-0.35, 0.35, s) - Math.PI / 2;
        return { pos: [pair[0] + Math.cos(a) * 2.4, 1.6, pair[1] + Math.sin(a) * 2.4], target: [pair[0], 1.45, pair[1]] };
      }
      if (u < 2 / 3) {
        const s = (u - 1 / 3) * 3;
        const p = lerp3([-18, 1.7, -16], [16, 1.7, 14], s);
        return { pos: p, target: [p[0] + 8, 1.5, p[2] + 7] };
      }
      const s = (u - 2 / 3) * 3, a = lerp(0.2, 0.8, s);
      return { pos: [Math.cos(a) * 30, 22, Math.sin(a) * 30], target: [0, 0, 0] };
    },
  };
}

function meadow(seed: number): SceneSpec {
  const rng = mulberry32(seed);
  const chars: CharSpec[] = [];
  const farms: [number, number][] = [];
  for (let f = 0; f < 6; f++) farms.push([range(rng, -170, 170), range(rng, -170, 170)]);
  for (const [fx, fz] of farms) {
    for (let k = 0; k < 8; k++) {
      const state = (rng() < 0.5 ? 2 : 0) as StateId;
      chars.push(makeChar(rng, chars.length, fx + range(rng, -6, 6), fz + range(rng, -6, 6), range(rng, -Math.PI, Math.PI), state));
    }
  }
  while (chars.length < 80) chars.push(makeChar(rng, chars.length, range(rng, -195, 195), range(rng, -195, 195), range(rng, -Math.PI, Math.PI), 0));
  while (chars.length < 100) {
    const r = range(rng, 8, 30);
    chars.push(makeChar(rng, chars.length, range(rng, -120, 120), range(rng, -60, 60), 0, 1, { r, omega: (rng() < 0.5 ? -1 : 1) * 1.4 / r, a0: range(rng, 0, 6.283) }));
  }
  return {
    name: 'meadow', seed, chars, groundSize: 500, cell: 100, fade: [220, 250],
    segments: [{ name: 'eye-height', from: 0, to: 0.5 }, { name: 'elevated', from: 0.5, to: 1 }],
    camera: (frame, n) => {
      const u = Math.min(1, Math.max(0, frame / n));
      if (u < 0.5) {
        const s = u * 2;
        const p = lerp3([-160, 1.7, -12], [-40, 1.7, -4], s);
        return { pos: p, target: [p[0] + 200, 1.2, p[2] + 30 * Math.sin(s * 3)] };
      }
      const s = (u - 0.5) * 2, a = lerp(3.6, 4.4, s);
      return { pos: [Math.cos(a) * 170, 45, Math.sin(a) * 170], target: [0, 0, 0] };
    },
  };
}

function single(seed: number): SceneSpec {
  const rng = mulberry32(seed);
  return {
    name: 'single', seed, chars: [makeChar(rng, 0, 0, 0, Math.PI, 0)], groundSize: 0, cell: 20, fade: [220, 250],
    segments: [{ name: 'all', from: 0, to: 1 }],
    camera: () => ({ pos: [0, 1.4, -3.2], target: [0, 1.0, 0] }),
  };
}

export function makeScene(name: SceneName, seed: number): SceneSpec {
  if (name === 'plaza') return plaza(seed);
  if (name === 'meadow') return meadow(seed);
  return single(seed);
}
