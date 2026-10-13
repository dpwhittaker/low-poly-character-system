// Assembly hand-off (PLAN §4.3 step 6): baked body → one Babylon Mesh + Skeleton.
//
// Skeleton fit: every body keeps the CANONICAL rest rotations of `skeleton.glb` (MPFB
// `game_engine` + jaw/eyes/twist on the MakeHuman default body) and only moves bone heads
// to its own joint positions. Rotation-only clips authored on that rest therefore play on
// any proportions (PLAN §5.4). Everything is in glTF space (Y up, RH); a root node does the
// same RH→LH conversion as Babylon's glTF loader, so clips from GLBs line up untouched.

import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer';
import { TransformNode } from '@babylonjs/core/Meshes/transformNode';
import { Skeleton } from '@babylonjs/core/Bones/skeleton';
import { Bone } from '@babylonjs/core/Bones/bone';
import { Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';
import type { ShaderMaterial } from '@babylonjs/core/Materials/shaderMaterial';

import type { BodyPack } from './bodyPack.ts';
import { boneHeads, srcNormals, type Baked } from './assemble.ts';
import { fitBoneMatrices, topoOrder, type RestSkeleton } from './skeletonFit.ts';
import { fitItem, inheritSkin, itemNormals, itemPaletteBase, FIRST_ITEM_SLOT, type ItemPack } from './items.ts';

export { loadRestSkeleton, parseRestSkeleton, type RestSkeleton } from './skeletonFit.ts';

export interface CharacterParts {
  root: TransformNode;
  mesh: Mesh;
  skeleton: Skeleton;
  bones: Map<string, Bone>;
  items: ItemPack[];
  /** Babylon bone index per pack bone index. */
  remap: Uint8Array;
}

/** Bands hidden on the body / on lower-layer items by the worn items (D1: downward only). */
function hiddenBands(items: ItemPack[], aboveLayer: number): Set<number> {
  const out = new Set<number>();
  for (const it of items) if (it.meta.layer > aboveLayer) for (const b of it.meta.hides) out.add(b);
  return out;
}

/** Static arrays of the merged mesh: body (minus hidden bands) + every item. */
function mergedStatic(pack: BodyPack, items: ItemPack[], remap: Uint8Array) {
  const R = pack.meta.counts.render;
  const total = R + items.reduce((s, it) => s + it.meta.counts.verts, 0);
  const region = new Float32Array(total), ao = new Float32Array(total);
  const bi = new Float32Array(total * 4), bw = new Float32Array(total * 4);
  const indices: number[] = [];
  for (let v = 0; v < R; v++) {
    const s = pack.renderSrc[v];
    for (let k = 0; k < 4; k++) { bi[v * 4 + k] = remap[pack.skinBones[s * 4 + k]]; bw[v * 4 + k] = pack.skinWeights[s * 4 + k] / 255; }
    region[v] = pack.renderRegion[v];
    ao[v] = pack.renderAO[v] / 255;
  }
  const bodyHidden = hiddenBands(items, 0);
  for (let t = 0; t < pack.indices.length / 3; t++) {
    if (pack.triBand[t] !== 255 && bodyHidden.has(pack.triBand[t])) continue;
    indices.push(pack.indices[t * 3], pack.indices[t * 3 + 1], pack.indices[t * 3 + 2]);
  }
  let base = R, garment = 0;
  for (const it of items) {
    const n = it.meta.counts.verts;
    const pal = itemPaletteBase(it, garment);
    if (pal >= FIRST_ITEM_SLOT) garment++;
    const skin = inheritSkin(it, pack);
    for (let v = 0; v < n; v++) {
      for (let k = 0; k < 4; k++) { bi[(base + v) * 4 + k] = remap[skin.bones[v * 4 + k]]; bw[(base + v) * 4 + k] = skin.weights[v * 4 + k]; }
      region[base + v] = pal + it.channel[v];
      ao[base + v] = it.ao[v] / 255;
    }
    const hide = hiddenBands(items, it.meta.layer);
    for (let t = 0; t < it.indices.length / 3; t++) {
      if (hide.has(it.triBand[t])) continue;
      indices.push(base + it.indices[t * 3], base + it.indices[t * 3 + 1], base + it.indices[t * 3 + 2]);
    }
    base += n;
  }
  return { total, region, ao, bi, bw, indices: new Uint32Array(indices) };
}

export function buildCharacter(scene: Scene, pack: BodyPack, rest: RestSkeleton, baked: Baked, material: ShaderMaterial,
  name = 'character', items: ItemPack[] = []): CharacterParts {
  const root = new TransformNode(`${name}_root`, scene);
  root.rotationQuaternion = Quaternion.FromEulerAngles(0, Math.PI, 0); // = Babylon glTF loader's __root__
  root.scaling = new Vector3(1, 1, -1);

  const { meta } = pack;
  const skeleton = new Skeleton(`${name}_skel`, `${name}_skel`, scene);
  const bones = new Map<string, Bone>();
  const heads = boneHeads(pack, baked.joints, baked.groundLift);
  const local = fitBoneMatrices(pack, rest, heads);
  const byIndex: Bone[] = new Array(meta.bones.length);
  for (const i of topoOrder(pack)) {
    const b = meta.bones[i];
    const parent = b.parent >= 0 ? byIndex[b.parent] : null;
    byIndex[i] = new Bone(b.name, skeleton, parent, local[i].clone(), local[i].clone(), local[i].clone());
    bones.set(b.name, byIndex[i]);
  }
  // Babylon indexes bones by creation order; remap the pack's bone indices to it.
  const remap = new Uint8Array(meta.bones.length);
  byIndex.forEach((bone, i) => (remap[i] = skeleton.bones.indexOf(bone)));

  const mesh = new Mesh(name, scene);
  mesh.parent = root;
  mesh.skeleton = skeleton;
  mesh.numBoneInfluencers = 4;
  mesh.material = material;
  const parts: CharacterParts = { root, mesh, skeleton, bones, items, remap };
  setOutfit(parts, pack, rest, baked, items);
  return parts;
}

/** Change what the character wears: rebuilds the merged mesh's static arrays + indices. */
export function setOutfit(parts: CharacterParts, pack: BodyPack, rest: RestSkeleton, baked: Baked, items: ItemPack[]): void {
  parts.items = [...items].sort((a, b) => a.meta.layer - b.meta.layer);
  const st = mergedStatic(pack, parts.items, parts.remap);
  const vd = new VertexData();
  vd.positions = new Float32Array(st.total * 3);
  vd.normals = new Float32Array(st.total * 3);
  vd.indices = st.indices;
  vd.matricesIndices = st.bi;
  vd.matricesWeights = st.bw;
  vd.applyToMesh(parts.mesh, true);
  parts.mesh.setVerticesData('region', st.region, false, 1);
  parts.mesh.setVerticesData('ao', st.ao, false, 1);
  updateCharacter(parts, pack, rest, baked);
}

/** Re-apply a new bake: body + item positions/normals and the fitted rest skeleton. */
export function updateCharacter(parts: CharacterParts, pack: BodyPack, rest: RestSkeleton, baked: Baked): void {
  const { meta } = pack;
  const R = meta.counts.render;
  const n = srcNormals(pack, baked.src);
  // shoe soles lift the whole character (items are authored with the sole below the foot)
  baked = { ...baked, groundLift: baked.groundLift + Math.max(0, ...parts.items.map((it) => it.meta.lift ?? 0)) };
  const total = parts.mesh.getTotalVertices();
  const unindexedDebug = total === pack.indices.length && parts.items.length === 0;
  const pos = new Float32Array(unindexedDebug ? R * 3 : total * 3), nor = new Float32Array(pos.length);
  for (let v = 0; v < R; v++) {
    const s = pack.renderSrc[v] * 3;
    pos[v * 3] = baked.src[s]; pos[v * 3 + 1] = baked.src[s + 1] + baked.groundLift; pos[v * 3 + 2] = baked.src[s + 2];
    nor[v * 3] = n[s]; nor[v * 3 + 1] = n[s + 1]; nor[v * 3 + 2] = n[s + 2];
  }
  let base = R;
  for (const it of parts.items) {
    const p = fitItem(it, baked.src, n, baked.groundLift);
    pos.set(p, base * 3);
    nor.set(itemNormals(it, p), base * 3);
    base += it.meta.counts.verts;
  }
  let p = pos, q = nor;
  if (unindexedDebug) {
    // unindexed debug mesh (convertToFlatShadedMesh): one vertex per triangle corner
    p = new Float32Array(pack.indices.length * 3); q = new Float32Array(pack.indices.length * 3);
    pack.indices.forEach((v, k) => { p.set(pos.subarray(v * 3, v * 3 + 3), k * 3); q.set(nor.subarray(v * 3, v * 3 + 3), k * 3); });
  }
  parts.mesh.updateVerticesData(VertexBuffer.PositionKind, p, false, false);
  parts.mesh.updateVerticesData(VertexBuffer.NormalKind, q, false, false);
  parts.mesh.refreshBoundingInfo();
  const local = fitBoneMatrices(pack, rest, boneHeads(pack, baked.joints, baked.groundLift));
  meta.bones.forEach((b, i) => {
    const bone = parts.bones.get(b.name)!;
    bone.setBindMatrix(local[i].clone()); // also refreshes the subtree's inverse binds
    bone.setRestMatrix(local[i].clone());
  });
  parts.skeleton.returnToRest();
}
