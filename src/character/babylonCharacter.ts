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

export { loadRestSkeleton, parseRestSkeleton, type RestSkeleton } from './skeletonFit.ts';

export interface CharacterParts {
  root: TransformNode;
  mesh: Mesh;
  skeleton: Skeleton;
  bones: Map<string, Bone>;
}

export function buildCharacter(scene: Scene, pack: BodyPack, rest: RestSkeleton, baked: Baked, material: ShaderMaterial,
  name = 'character'): CharacterParts {
  const root = new TransformNode(`${name}_root`, scene);
  root.rotationQuaternion = Quaternion.FromEulerAngles(0, Math.PI, 0); // = Babylon glTF loader's __root__
  root.scaling = new Vector3(1, 1, -1);

  const { meta } = pack;
  const R = meta.counts.render;
  const skeleton = new Skeleton(`${name}_skel`, `${name}_skel`, scene);
  const bones = new Map<string, Bone>();
  const heads = boneHeads(pack, baked.joints, baked.groundLift);
  const local = fitBoneMatrices(pack, rest, heads);
  const order = topoOrder(pack);
  const byIndex: Bone[] = new Array(meta.bones.length);
  for (const i of order) {
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
  const idx = new Float32Array(R * 4), wts = new Float32Array(R * 4);
  const region = new Float32Array(R), ao = new Float32Array(R);
  for (let v = 0; v < R; v++) {
    const s = pack.renderSrc[v];
    for (let k = 0; k < 4; k++) {
      idx[v * 4 + k] = remap[pack.skinBones[s * 4 + k]];
      wts[v * 4 + k] = pack.skinWeights[s * 4 + k] / 255;
    }
    region[v] = pack.renderRegion[v];
    ao[v] = pack.renderAO[v] / 255;
  }
  const vd = new VertexData();
  vd.positions = new Float32Array(R * 3);
  vd.normals = new Float32Array(R * 3);
  vd.indices = pack.indices;
  vd.matricesIndices = idx;
  vd.matricesWeights = wts;
  vd.applyToMesh(mesh, true);
  mesh.setVerticesData('region', region, false, 1);
  mesh.setVerticesData('ao', ao, false, 1);
  mesh.skeleton = skeleton;
  mesh.numBoneInfluencers = 4;
  mesh.material = material;
  const parts = { root, mesh, skeleton, bones };
  updateCharacter(parts, pack, rest, baked);
  return parts;
}

/** Re-apply a new bake: positions, normals and the fitted rest skeleton (bind poses). */
export function updateCharacter(parts: CharacterParts, pack: BodyPack, rest: RestSkeleton, baked: Baked): void {
  const { meta } = pack;
  const R = meta.counts.render;
  const n = srcNormals(pack, baked.src);
  const pos = new Float32Array(R * 3), nor = new Float32Array(R * 3);
  for (let v = 0; v < R; v++) {
    const s = pack.renderSrc[v] * 3;
    pos[v * 3] = baked.src[s]; pos[v * 3 + 1] = baked.src[s + 1] + baked.groundLift; pos[v * 3 + 2] = baked.src[s + 2];
    nor[v * 3] = n[s]; nor[v * 3 + 1] = n[s + 1]; nor[v * 3 + 2] = n[s + 2];
  }
  let p = pos, q = nor;
  if (parts.mesh.getTotalVertices() === pack.indices.length) {
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
