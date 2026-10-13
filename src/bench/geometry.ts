// PLACEHOLDER character geometry for the M0 crowd bench — deliberately crude
// tubes and spheres, NOT art (PLAN §2: procedural humans are banned as art).
// What matters here is that every LOD hits its §8.3 triangle budget exactly,
// that vertices are shared (indexed, smooth), and that skin weights look like
// a real rig's: 4 influences at LOD0, 2 at LOD1+.

import { BONE, SKELETONS, LOD_SKELETON, type CharacterSkeleton } from './skeleton.ts';
import { type Rng, range } from './rng.ts';

export const LOD_TRIS = [3500, 1400, 500, 150] as const;
export const LOD_INFLUENCES = [4, 2, 2, 2] as const;

export interface MeshData {
  positions: Float32Array;
  normals: Float32Array;
  colors: Float32Array;
  indices: Uint32Array;
  /** slot indices into the LOD skeleton, 4 per vertex */
  boneIndices: Float32Array;
  boneWeights: Float32Array;
  triangles: number;
  vertices: number;
}

interface PartCfg { sides: number; frac: number }
interface LodCfg { headSides: number; headBands: number; torso: PartCfg; arm: PartCfg; leg: PartCfg; fingers: boolean }

const CFG: LodCfg[] = [
  { headSides: 18, headBands: 14, torso: { sides: 16, frac: 0.3 }, arm: { sides: 10, frac: 0.17 }, leg: { sides: 12, frac: 0.18 }, fingers: true },
  { headSides: 12, headBands: 9, torso: { sides: 10, frac: 0.3 }, arm: { sides: 6, frac: 0.17 }, leg: { sides: 8, frac: 0.18 }, fingers: false },
  { headSides: 8, headBands: 6, torso: { sides: 7, frac: 0.3 }, arm: { sides: 5, frac: 0.17 }, leg: { sides: 6, frac: 0.18 }, fingers: false },
  { headSides: 5, headBands: 4, torso: { sides: 5, frac: 0.3 }, arm: { sides: 3, frac: 0.17 }, leg: { sides: 4, frac: 0.18 }, fingers: false },
];

const FINGER_SIDES = 5;
const FINGER_RINGS = 4;

export interface Palette { skin: number[]; shirt: number[]; pants: number[]; shoes: number[] }

export function randomPalette(rng: Rng): Palette {
  const skinT = rng();
  const skin = [0.36 + 0.55 * skinT, 0.24 + 0.45 * skinT, 0.16 + 0.38 * skinT];
  const hue = () => [range(rng, 0.1, 0.9), range(rng, 0.1, 0.9), range(rng, 0.1, 0.9)];
  return { skin, shirt: hue(), pants: hue(), shoes: [0.15, 0.12, 0.1].map((c) => c + 0.3 * rng()) };
}

class Builder {
  pos: number[] = [];
  nrm: number[] = [];
  col: number[] = [];
  idx: number[] = [];
  bi: number[] = [];
  bw: number[] = [];
  readonly influences: number;
  readonly remap: Int32Array;
  constructor(influences: number, remap: Int32Array) {
    this.influences = influences;
    this.remap = remap;
  }
  get vcount() { return this.pos.length / 3; }
  get tris() { return this.idx.length / 3; }
  /** influences: [bone(LOD0 index), weight][] — remapped, merged, truncated, normalized */
  vertex(p: number[], n: number[], c: number[], inf: [number, number][]) {
    const merged = new Map<number, number>();
    for (const [b, w] of inf) {
      const s = this.remap[b];
      merged.set(s, (merged.get(s) ?? 0) + w);
    }
    const list = [...merged.entries()].sort((a, b) => b[1] - a[1]).slice(0, this.influences);
    let sum = 0;
    for (const [, w] of list) sum += w;
    for (let k = 0; k < 4; k++) {
      const e = list[k];
      this.bi.push(e ? e[0] : 0);
      this.bw.push(e ? e[1] / sum : 0);
    }
    this.pos.push(p[0], p[1], p[2]);
    const l = Math.hypot(n[0], n[1], n[2]) || 1;
    this.nrm.push(n[0] / l, n[1] / l, n[2] / l);
    this.col.push(c[0], c[1], c[2], 1);
    return this.vcount - 1;
  }
  tri(a: number, b: number, c: number) { this.idx.push(a, b, c); }
}

const sub = (a: number[], b: number[]) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a: number[], b: number[]) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: number[]) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const lerp3 = (a: number[], b: number[], t: number) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

interface Poly { pts: number[][]; radii: number[]; bones: number[]; color: (t: number) => number[] }

/** Tube along a polyline: `rings` rings spaced by arc length, optional end caps. Returns tris added. */
function tube(B: Builder, poly: Poly, sides: number, rings: number, capStart: boolean, capEnd: boolean) {
  const { pts, radii, bones } = poly;
  const segLen: number[] = [];
  let total = 0;
  for (let i = 0; i + 1 < pts.length; i++) { const l = Math.hypot(...sub(pts[i + 1], pts[i])); segLen.push(l); total += l; }
  const ringIdx: number[][] = [];
  const centers: number[][] = [];
  const tangents: number[][] = [];
  const ringBones: [number, number][][] = [];
  for (let r = 0; r < rings; r++) {
    let d = (r / (rings - 1)) * total;
    let k = 0;
    while (k < segLen.length - 1 && d > segLen[k]) { d -= segLen[k]; k++; }
    const u = Math.min(1, d / (segLen[k] || 1));
    const c = lerp3(pts[k], pts[k + 1], u);
    const rad = radii[k] + (radii[k + 1] - radii[k]) * u;
    const t = norm(sub(pts[k + 1], pts[k]));
    const ref = Math.abs(t[1]) < 0.9 ? [0, 1, 0] : [0, 0, 1];
    const a = norm(cross(t, ref));
    const b = norm(cross(a, t));
    const inf: [number, number][] = [[bones[k], 1]];
    if (u < 0.25 && k > 0) { const w = 0.5 * (1 - u / 0.25); inf[0][1] = 1 - w; inf.push([bones[k - 1], w]); }
    if (u > 0.75 && k + 1 < bones.length) { const w = 0.5 * ((u - 0.75) / 0.25); inf[0][1] -= w; inf.push([bones[k + 1], w]); }
    // A small share for the parent chain makes LOD0 use all 4 slots, as real weights do.
    inf.push([bones[Math.max(0, k - 1)], 0.04], [BONE.hips, 0.01]);
    const color = poly.color((r / (rings - 1)));
    const ring: number[] = [];
    for (let s = 0; s < sides; s++) {
      const ang = (s / sides) * Math.PI * 2;
      const n = [a[0] * Math.cos(ang) + b[0] * Math.sin(ang), a[1] * Math.cos(ang) + b[1] * Math.sin(ang), a[2] * Math.cos(ang) + b[2] * Math.sin(ang)];
      ring.push(B.vertex([c[0] + n[0] * rad, c[1] + n[1] * rad, c[2] + n[2] * rad], n, color, inf));
    }
    ringIdx.push(ring);
    centers.push(c);
    tangents.push(t);
    ringBones.push(inf);
  }
  for (let r = 0; r + 1 < rings; r++) {
    for (let s = 0; s < sides; s++) {
      const s2 = (s + 1) % sides;
      const a0 = ringIdx[r][s], a1 = ringIdx[r][s2], b0 = ringIdx[r + 1][s], b1 = ringIdx[r + 1][s2];
      B.tri(a0, b0, a1);
      B.tri(a1, b0, b1);
    }
  }
  const cap = (r: number, flip: boolean) => {
    const t = tangents[r];
    const n = flip ? [-t[0], -t[1], -t[2]] : t;
    const c = B.vertex(centers[r], n, poly.color(r === 0 ? 0 : 1), ringBones[r]);
    for (let s = 0; s < sides; s++) {
      const s2 = (s + 1) % sides;
      if (flip) B.tri(c, ringIdx[r][s], ringIdx[r][s2]);
      else B.tri(c, ringIdx[r][s2], ringIdx[r][s]);
    }
  };
  if (capStart) cap(0, true);
  if (capEnd) cap(rings - 1, false);
}

function tubeTris(sides: number, rings: number, caps: number) { return 2 * sides * (rings - 1) + caps * sides; }
function ringsFor(budget: number, sides: number, caps: number) { return Math.max(2, Math.floor((budget - caps * sides) / (2 * sides)) + 1); }

function sphere(B: Builder, center: number[], radius: number, sides: number, bands: number, bone: number, color: number[]) {
  const inf: [number, number][] = [[bone, 0.95], [BONE.neck, 0.05]];
  const top = B.vertex([center[0], center[1] + radius, center[2]], [0, 1, 0], color, inf);
  const rows: number[][] = [];
  for (let l = 1; l < bands; l++) {
    const phi = (l / bands) * Math.PI;
    const row: number[] = [];
    for (let s = 0; s < sides; s++) {
      const th = (s / sides) * Math.PI * 2;
      const n = [Math.sin(phi) * Math.cos(th), Math.cos(phi), Math.sin(phi) * Math.sin(th)];
      row.push(B.vertex([center[0] + n[0] * radius, center[1] + n[1] * radius * 1.1, center[2] + n[2] * radius], n, color, inf));
    }
    rows.push(row);
  }
  const bottom = B.vertex([center[0], center[1] - radius * 1.1, center[2]], [0, -1, 0], color, inf);
  for (let s = 0; s < sides; s++) {
    const s2 = (s + 1) % sides;
    B.tri(top, rows[0][s2], rows[0][s]);
    B.tri(bottom, rows[rows.length - 1][s], rows[rows.length - 1][s2]);
  }
  for (let r = 0; r + 1 < rows.length; r++) {
    for (let s = 0; s < sides; s++) {
      const s2 = (s + 1) % sides;
      B.tri(rows[r][s], rows[r][s2], rows[r + 1][s]);
      B.tri(rows[r][s2], rows[r + 1][s2], rows[r + 1][s]);
    }
  }
}
const sphereTris = (sides: number, bands: number) => 2 * sides * (bands - 1);

/** Build one LOD of a placeholder character, exactly LOD_TRIS[lod] triangles. */
export function buildCharacterLod(skel: CharacterSkeleton, lod: number, pal: Palette): MeshData {
  const cfg = CFG[lod];
  const sk = SKELETONS[LOD_SKELETON[lod]];
  const B = new Builder(LOD_INFLUENCES[lod], sk.remap);
  const W = (name: string) => { const i = BONE[name] * 3; return [skel.restWorld[i], skel.restWorld[i + 1], skel.restWorld[i + 2]]; };
  const g = skel.props.girth;
  const budget = LOD_TRIS[lod];
  let rest = budget - sphereTris(cfg.headSides, cfg.headBands) - (cfg.fingers ? 8 * tubeTris(FINGER_SIDES, FINGER_RINGS, 1) : 0);
  const share = rest;

  // Head
  const headC = W('head');
  sphere(B, [headC[0], headC[1] + 0.1 * skel.props.height, headC[2] + 0.015], 0.105 * skel.props.height, cfg.headSides, cfg.headBands, BONE.head, pal.skin);

  // Torso: pelvis bottom → neck top
  const hipsW = W('hips');
  const torso: Poly = {
    pts: [[hipsW[0], hipsW[1] - 0.1, hipsW[2]], hipsW, W('spine1'), W('spine2'), W('chest'), W('neck'), W('head')],
    radii: [0.13, 0.15, 0.14, 0.145, 0.16, 0.06, 0.055].map((r, i) => r * (i < 2 ? g * skel.props.hip : i < 5 ? g : 1)),
    bones: [BONE.hips, BONE.hips, BONE.spine1, BONE.spine2, BONE.chest, BONE.neck],
    color: (t) => (t > 0.86 ? pal.skin : t < 0.22 ? pal.pants : pal.shirt),
  };
  const torsoB = Math.floor(share * cfg.torso.frac);
  const torsoR = ringsFor(torsoB, cfg.torso.sides, 1);
  tube(B, torso, cfg.torso.sides, torsoR, true, false);
  rest -= tubeTris(cfg.torso.sides, torsoR, 1);

  for (const side of ['L', 'R']) {
    const hand = W('hand' + side);
    const dir = side === 'L' ? -1 : 1;
    const arm: Poly = {
      pts: [W('upperArm' + side), W('upperTwist' + side), W('forearm' + side), W('foreTwist' + side), hand, [hand[0] + dir * 0.09 * skel.props.height, hand[1], hand[2]]],
      radii: [0.058, 0.052, 0.046, 0.04, 0.036, 0.028].map((r) => r * Math.sqrt(g)),
      bones: [BONE['upperArm' + side], BONE['upperTwist' + side], BONE['forearm' + side], BONE['foreTwist' + side], BONE['hand' + side]],
      color: (t) => (t > 0.78 ? pal.skin : t < 0.3 ? pal.shirt : pal.skin),
    };
    const armB = Math.floor(share * cfg.arm.frac);
    const armR = ringsFor(armB, cfg.arm.sides, 1);
    tube(B, arm, cfg.arm.sides, armR, false, true);
    rest -= tubeTris(cfg.arm.sides, armR, 1);

    if (cfg.fingers) {
      for (const f of ['thumb', 'index', 'middle', 'ring']) {
        const f1 = W(f + '1' + side), f2 = W(f + '2' + side), f3 = W(f + '3' + side);
        const tip = lerp3(f2, f3, 1.9);
        tube(B, { pts: [f1, f2, f3, tip], radii: [0.011, 0.01, 0.009, 0.008], bones: [BONE[f + '1' + side], BONE[f + '2' + side], BONE[f + '3' + side]], color: () => pal.skin }, FINGER_SIDES, FINGER_RINGS, false, true);
      }
    }

    const foot = W('foot' + side), toe = W('toe' + side);
    const leg: Poly = {
      pts: [W('thigh' + side), W('shin' + side), foot, toe, [toe[0], toe[1], toe[2] + 0.07 * skel.props.height]],
      radii: [0.085, 0.06, 0.045, 0.045, 0.035].map((r, i) => r * (i < 2 ? g : 1)),
      bones: [BONE['thigh' + side], BONE['shin' + side], BONE['foot' + side], BONE['toe' + side]],
      color: (t) => (t > 0.72 ? pal.shoes : pal.pants),
    };
    const legB = Math.floor(share * cfg.leg.frac);
    const legR = ringsFor(legB, cfg.leg.sides, 1);
    tube(B, leg, cfg.leg.sides, legR, false, true);
    rest -= tubeTris(cfg.leg.sides, legR, 1);
  }

  // Filler: a tiny fan hidden inside the chest so the count is exact.
  const fill = budget - B.tris;
  if (fill < 0) throw new Error(`LOD${lod} over budget by ${-fill}`);
  if (fill > 0) {
    const c = W('chest');
    const inf: [number, number][] = [[BONE.chest, 1]];
    const center = B.vertex(c, [0, 0, 1], pal.shirt, inf);
    const ring: number[] = [];
    for (let s = 0; s <= fill; s++) {
      const ang = (s / (fill + 1)) * Math.PI * 2;
      ring.push(B.vertex([c[0] + 0.02 * Math.cos(ang), c[1] + 0.02 * Math.sin(ang), c[2]], [0, 0, 1], pal.shirt, inf));
    }
    for (let s = 0; s < fill; s++) B.tri(center, ring[s], ring[s + 1]);
  }
  void rest;
  if (B.tris !== budget) throw new Error(`LOD${lod}: ${B.tris} tris ≠ ${budget}`);
  return {
    positions: Float32Array.from(B.pos),
    normals: Float32Array.from(B.nrm),
    colors: Float32Array.from(B.col),
    indices: Uint32Array.from(B.idx),
    boneIndices: Float32Array.from(B.bi),
    boneWeights: Float32Array.from(B.bw),
    triangles: B.tris,
    vertices: B.vcount,
  };
}
