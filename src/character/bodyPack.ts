// The M1 body pack (`public/m1/body.json` + `body.bin`), written by
// pipeline/blender/m1_body/03_pack.py. Pure data: no Babylon imports, so the assembler
// runs in a worker or in Node tests unchanged (PLAN §4.3).
//
// Coordinates are glTF (Y up, character faces +Z), metres — the same space as
// `skeleton.glb`. Two vertex sets: `src` (shape vertices; morphs, joints and skin weights
// live here) and `render` (src split where the per-face color region changes).

export type MacroParts = Record<string, Array<[number, number, string, string]>>;

export interface BoneDef {
  name: string;
  parent: number; // -1 for the root
  head: { joint: number } | { lerp: [number, number, number] };
}

export interface SliderDef {
  id: string;
  group: 'body' | 'face';
  neg: number[]; // target indices applied at |value| when value < 0
  pos: number[];
}

export interface BodyMeta {
  version: number;
  counts: { src: number; body: number; eyes: number; render: number; tris: number; targets: number };
  quant: number;
  layout: Record<string, { offset: number; length: number; dtype: string; shape: number[] }>;
  targetRanges: Array<[number, number]>; // [offset, count] into targetIndex / targetDelta rows
  targets: string[];
  regions: string[];
  paletteSrgb: string[];
  bones: BoneDef[];
  joints: string[];
  groundJoint: number;
  macroParts: MacroParts;
  races: string[];
  ageKeys: Array<[number, number]>;
  ageCurve: Record<'female' | 'male', { years_to_macro: Array<[number, number]> }>;
  sliders: SliderDef[];
  style: Array<[number, number]>; // [target index, weight], always applied
  cuts: Record<string, { closed: boolean; verts: number }>;
  bands: { count: number; baseTop: number; baseBottom: number; bounds: Record<string, string[]> };
}

export interface BodyPack {
  meta: BodyMeta;
  srcBasis: Float32Array; // src × 3
  renderSrc: Uint16Array; // render → src
  renderRegion: Uint8Array; // render → palette slot
  renderAO: Uint8Array; // render → baked AO × 255
  indices: Uint16Array; // render triangles
  triBand: Uint8Array; // per triangle: band between cut lines (PLAN §6.2), 255 = eyes
  skinBones: Uint8Array; // src × 4 bone indices (meta.bones order)
  skinWeights: Uint8Array; // src × 4, sums to 255
  jointBasis: Float32Array; // joints × 3
  targetIndex: Uint16Array; // sparse src indices, all targets concatenated
  targetDelta: Int16Array; // × 3 per index, × quant metres
  jointDelta: Int16Array; // targets × joints × 3, × quant metres
  targetByName: Map<string, number>;
}

const CTORS = {
  float32: Float32Array,
  uint16: Uint16Array,
  uint8: Uint8Array,
  int16: Int16Array,
} as const;

function view<K extends keyof typeof CTORS>(meta: BodyMeta, buf: ArrayBuffer, name: string, dtype: K): InstanceType<(typeof CTORS)[K]> {
  const l = meta.layout[name];
  if (!l) throw new Error(`body pack: missing buffer ${name}`);
  if (l.dtype !== dtype) throw new Error(`body pack: ${name} is ${l.dtype}, expected ${dtype}`);
  const C = CTORS[dtype];
  return new C(buf, l.offset, l.length / C.BYTES_PER_ELEMENT) as InstanceType<(typeof CTORS)[K]>;
}

export function parseBodyPack(meta: BodyMeta, buf: ArrayBuffer): BodyPack {
  return {
    meta,
    srcBasis: view(meta, buf, 'srcBasis', 'float32'),
    renderSrc: view(meta, buf, 'renderSrc', 'uint16'),
    renderRegion: view(meta, buf, 'renderRegion', 'uint8'),
    renderAO: view(meta, buf, 'renderAO', 'uint8'),
    indices: view(meta, buf, 'indices', 'uint16'),
    triBand: view(meta, buf, 'triBand', 'uint8'),
    skinBones: view(meta, buf, 'skinBones', 'uint8'),
    skinWeights: view(meta, buf, 'skinWeights', 'uint8'),
    jointBasis: view(meta, buf, 'jointBasis', 'float32'),
    targetIndex: view(meta, buf, 'targetIndex', 'uint16'),
    targetDelta: view(meta, buf, 'targetDelta', 'int16'),
    jointDelta: view(meta, buf, 'jointDelta', 'int16'),
    targetByName: new Map(meta.targets.map((n, i) => [n, i])),
  };
}

export async function loadBodyPack(baseUrl: string): Promise<BodyPack> {
  const [meta, buf] = await Promise.all([
    fetch(`${baseUrl}body.json`).then((r) => r.json() as Promise<BodyMeta>),
    fetch(`${baseUrl}body.bin`).then((r) => r.arrayBuffer()),
  ]);
  return parseBodyPack(meta, buf);
}
