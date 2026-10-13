// Items (garments, hair, brows): assembly step 3 "item fit" (PLAN §4.3, §7.3 D3/D4).
// An item vertex is bound to three body src vertices + barycentrics + an offset in the
// surface's local frame, authored once on the default body
// (pipeline/blender/m1_items/lib_items.py). On any baked body:
//   q = Σ bᵢ·vᵢ,  n = normalize(Σ bᵢ·nᵢ),  t = normalize(e₀₁ − (e₀₁·n)n),  p' = q + o.x·t + o.y·(n×t) + o.z·n
// so garments keep their authored clearance on every body and turn with the surface.
// Skin weights are inherited from the body through the same binding (D4).
// Pure TypeScript (worker / Node safe).

import type { BodyPack } from './bodyPack.ts';

export interface ItemMeta {
  id: string;
  name: string;
  slot: string; // top | bottom | outer | shoes | hair | brows …
  layer: number;
  colors: string[]; // default sRGB per channel (R primary, G accent, B detail)
  hides: number[]; // body bands measured as fully covered (D1)
  lift?: number; // metres the item raises the character (shoe soles)
  counts: { verts: number; tris: number };
  layout: Record<string, { offset: number; length: number; dtype: string; shape: number[] }>;
}

export interface ItemPack {
  meta: ItemMeta;
  bindSrc: Uint16Array; // verts × 3
  bindBary: Float32Array; // verts × 2 (third = 1 − a − b)
  bindOffset: Float32Array; // verts × 3, local frame (t, n×t, n)
  bindArea: Float32Array; // rest area of the binding triangle (offsets scale by √(A/A₀), PLAN §5.6)
  channel: Uint8Array; // verts
  ao: Uint8Array; // verts
  indices: Uint16Array;
  triBand: Uint8Array; // body band under each triangle (for hiding by upper layers)
  /** Vertices that share a position (split only by color channel): one normal per group. */
  weld: Uint32Array;
}

export function parseItemPack(meta: ItemMeta, buf: ArrayBuffer): ItemPack {
  const v = <T>(name: string, C: { new(b: ArrayBuffer, o: number, n: number): T; BYTES_PER_ELEMENT: number }) => {
    const l = meta.layout[name];
    return new C(buf, l.offset, l.length / C.BYTES_PER_ELEMENT);
  };
  const rest = v('restPos', Float32Array);
  const weld = new Uint32Array(meta.counts.verts);
  const seen = new Map<string, number>();
  for (let i = 0; i < weld.length; i++) {
    const k = `${rest[i * 3].toFixed(6)},${rest[i * 3 + 1].toFixed(6)},${rest[i * 3 + 2].toFixed(6)}`;
    if (!seen.has(k)) seen.set(k, i);
    weld[i] = seen.get(k)!;
  }
  return {
    meta, weld,
    bindSrc: v('bindSrc', Uint16Array), bindBary: v('bindBary', Float32Array), bindOffset: v('bindOffset', Float32Array),
    bindArea: v('bindArea', Float32Array),
    channel: v('channel', Uint8Array), ao: v('ao', Uint8Array), indices: v('indices', Uint16Array), triBand: v('triBand', Uint8Array),
  };
}

export async function loadItemPack(baseUrl: string, id: string): Promise<ItemPack> {
  const [meta, buf] = await Promise.all([
    fetch(`${baseUrl}items/${id}.json`).then((r) => r.json() as Promise<ItemMeta>),
    fetch(`${baseUrl}items/${id}.bin`).then((r) => r.arrayBuffer()),
  ]);
  return parseItemPack(meta, buf);
}

/** Item positions on a baked body (src positions + src normals, glTF space). */
export function fitItem(item: ItemPack, src: Float32Array, srcN: Float32Array, lift = 0): Float32Array {
  const n = item.meta.counts.verts;
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const a = item.bindSrc[i * 3] * 3, b = item.bindSrc[i * 3 + 1] * 3, c = item.bindSrc[i * 3 + 2] * 3;
    const w0 = item.bindBary[i * 2], w1 = item.bindBary[i * 2 + 1], w2 = 1 - w0 - w1;
    let nx = w0 * srcN[a] + w1 * srcN[b] + w2 * srcN[c];
    let ny = w0 * srcN[a + 1] + w1 * srcN[b + 1] + w2 * srcN[c + 1];
    let nz = w0 * srcN[a + 2] + w1 * srcN[b + 2] + w2 * srcN[c + 2];
    const nl = Math.hypot(nx, ny, nz) || 1; nx /= nl; ny /= nl; nz /= nl;
    let tx = src[b] - src[a], ty = src[b + 1] - src[a + 1], tz = src[b + 2] - src[a + 2];
    const d = tx * nx + ty * ny + tz * nz;
    tx -= d * nx; ty -= d * ny; tz -= d * nz;
    const tl = Math.hypot(tx, ty, tz) || 1; tx /= tl; ty /= tl; tz /= tl;
    const bx = ny * tz - nz * ty, by = nz * tx - nx * tz, bz = nx * ty - ny * tx;
    // offsets follow local body scale (a child's hair / jacket is proportionally as thick)
    const ux = src[b] - src[a], uy = src[b + 1] - src[a + 1], uz = src[b + 2] - src[a + 2];
    const vx = src[c] - src[a], vy = src[c + 1] - src[a + 1], vz = src[c + 2] - src[a + 2];
    const area = 0.5 * Math.hypot(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx);
    const k = item.bindArea[i] > 0 ? Math.sqrt(area / item.bindArea[i]) : 1;
    const o0 = item.bindOffset[i * 3] * k, o1 = item.bindOffset[i * 3 + 1] * k, o2 = item.bindOffset[i * 3 + 2] * k;
    out[i * 3] = w0 * src[a] + w1 * src[b] + w2 * src[c] + o0 * tx + o1 * bx + o2 * nx;
    out[i * 3 + 1] = w0 * src[a + 1] + w1 * src[b + 1] + w2 * src[c + 1] + o0 * ty + o1 * by + o2 * ny + lift;
    out[i * 3 + 2] = w0 * src[a + 2] + w1 * src[b + 2] + w2 * src[c + 2] + o0 * tz + o1 * bz + o2 * nz;
  }
  return out;
}

/** D4: item skin = binding-weighted blend of the three body vertices' skins, top 4, normalized. */
export function inheritSkin(item: ItemPack, body: BodyPack): { bones: Uint8Array; weights: Float32Array } {
  const n = item.meta.counts.verts;
  const bones = new Uint8Array(n * 4), weights = new Float32Array(n * 4);
  const acc = new Map<number, number>();
  for (let i = 0; i < n; i++) {
    acc.clear();
    const w0 = item.bindBary[i * 2], w1 = item.bindBary[i * 2 + 1];
    const bw = [w0, w1, 1 - w0 - w1];
    for (let k = 0; k < 3; k++) {
      const s = item.bindSrc[i * 3 + k];
      for (let j = 0; j < 4; j++) {
        const w = body.skinWeights[s * 4 + j] / 255;
        if (w > 0) acc.set(body.skinBones[s * 4 + j], (acc.get(body.skinBones[s * 4 + j]) ?? 0) + w * bw[k]);
      }
    }
    const top = [...acc.entries()].sort((x, y) => y[1] - x[1]).slice(0, 4);
    const sum = top.reduce((s, [, w]) => s + w, 0) || 1;
    top.forEach(([b, w], j) => { bones[i * 4 + j] = b; weights[i * 4 + j] = w / sum; });
  }
  return { bones, weights };
}

/** Smooth normals over the item's triangles, shared across channel splits (weld groups). */
export function itemNormals(item: ItemPack, pos: Float32Array): Float32Array {
  const n = new Float32Array(pos.length);
  const { indices, weld } = item;
  for (let f = 0; f < indices.length; f += 3) {
    const a = indices[f] * 3, b = indices[f + 1] * 3, c = indices[f + 2] * 3;
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const v of [indices[f], indices[f + 1], indices[f + 2]]) {
      const w = weld[v] * 3;
      n[w] += nx; n[w + 1] += ny; n[w + 2] += nz;
    }
  }
  for (let i = 0; i < weld.length; i++) {
    const w = weld[i] * 3;
    const l = Math.hypot(n[w], n[w + 1], n[w + 2]) || 1;
    n[i * 3] = n[w] / l; n[i * 3 + 1] = n[w + 1] / l; n[i * 3 + 2] = n[w + 2] / l;
  }
  return n;
}

/** Palette slots: body regions 0–8, hair 9, brows 10, then 3 channels per worn garment. */
export const HAIR_SLOT = 9, BROW_SLOT = 10, FIRST_ITEM_SLOT = 11;
export function itemPaletteBase(item: ItemPack, garmentIndex: number): number {
  if (item.meta.slot === 'hair') return HAIR_SLOT;
  if (item.meta.slot === 'brows') return BROW_SLOT;
  return FIRST_ITEM_SLOT + garmentIndex * 3;
}
