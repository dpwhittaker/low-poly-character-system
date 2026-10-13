// Unit tests for the M0 crowd bench's custom sampler and texture skinning
// (SPEC V7, V8, V12). Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { NullEngine, Scene, Animation, Quaternion, Skeleton, Bone, Matrix, Mesh, VertexData, VertexBuffer } from '@babylonjs/core';
import { WALK, TALK, CLIP_FPS } from '../../src/bench/clips.ts';
import { sampleClip, composeCharacter, writeRoot, skinVertexCPU, FLOATS_PER_ROW } from '../../src/bench/sampler.ts';
import { BONES, BONE_COUNT, BONE, SKELETONS, characterSkeleton, randomProportions } from '../../src/bench/skeleton.ts';
import { buildCharacterLod, randomPalette, LOD_TRIS, LOD_INFLUENCES } from '../../src/bench/geometry.ts';
import { mulberry32 } from '../../src/bench/rng.ts';

test('V7: custom sampler matches Babylon Animation evaluation of the same dense clip (≤1e-4)', () => {
  for (const clip of [WALK, TALK]) {
    for (const boneName of ['thighL', 'upperArmR', 'head', 'forearmL']) {
      const b = BONE[boneName];
      const anim = new Animation('t', 'rotationQuaternion', CLIP_FPS, Animation.ANIMATIONTYPE_QUATERNION, Animation.ANIMATIONLOOPMODE_CYCLE);
      const keys = [];
      for (let f = 0; f <= clip.frames; f++) {
        const o = (f % clip.frames) * BONE_COUNT * 4 + b * 4;
        keys.push({ frame: f, value: new Quaternion(clip.quats[o], clip.quats[o + 1], clip.quats[o + 2], clip.quats[o + 3]) });
      }
      anim.setKeys(keys);
      const out = new Float32Array(BONE_COUNT * 4);
      for (const frame of [0, 0.25, 3.5, 7.9, clip.frames - 0.3]) {
        const q = anim.evaluate(frame);
        sampleClip(clip, frame / CLIP_FPS, out);
        const s = Math.sign(q.x * out[b * 4] + q.y * out[b * 4 + 1] + q.z * out[b * 4 + 2] + q.w * out[b * 4 + 3]) || 1;
        for (const [i, v] of [q.x, q.y, q.z, q.w].entries()) {
          assert.ok(Math.abs(s * out[b * 4 + i] - v) < 1e-4, `${clip.name}/${boneName}@${frame} comp ${i}: ${out[b * 4 + i]} vs ${v}`);
        }
      }
    }
  }
});

test('V8: shared-texture skinning (CPU mirror of the GLSL) matches Babylon skinning (≤1e-4 m)', () => {
  const engine = new NullEngine();
  const scene = new Scene(engine);
  const rng = mulberry32(42);
  const skel = characterSkeleton(randomProportions(rng));
  const md = buildCharacterLod(skel, 0, randomPalette(rng));
  // Babylon skeleton with identical rest offsets.
  const bsk = new Skeleton('s', 's', scene);
  const bones = [];
  for (let i = 0; i < BONE_COUNT; i++) {
    const p = BONES[i].parent;
    bones.push(new Bone(BONES[i].name, bsk, p < 0 ? null : bones[p], Matrix.Translation(skel.offsets[i * 3], skel.offsets[i * 3 + 1], skel.offsets[i * 3 + 2])));
  }
  const mesh = new Mesh('m', scene);
  const vd = new VertexData();
  vd.positions = md.positions; vd.indices = md.indices; vd.normals = md.normals;
  vd.applyToMesh(mesh);
  mesh.setVerticesData(VertexBuffer.MatricesIndicesKind, md.boneIndices, false, 4);
  mesh.setVerticesData(VertexBuffer.MatricesWeightsKind, md.boneWeights, false, 4);
  mesh.skeleton = bsk;
  mesh.numBoneInfluencers = 4;
  // A real pose from the walk clip.
  const pose = new Float32Array(BONE_COUNT * 4);
  sampleClip(WALK, 0.37, pose);
  for (let i = 0; i < BONE_COUNT; i++) bones[i].rotationQuaternion = new Quaternion(pose[i * 4], pose[i * 4 + 1], pose[i * 4 + 2], pose[i * 4 + 3]);
  bsk.prepare(true);
  const ref = mesh.getPositionData(true, false);
  const tex = new Float32Array(FLOATS_PER_ROW * 2);
  writeRoot(tex, 1, 0, 0, 0, 0, 0);
  composeCharacter(pose, skel, 0, tex, 1);
  let maxErr = 0;
  for (let v = 0; v < md.vertices; v++) {
    const p = skinVertexCPU(tex, 1, 0, md.positions.subarray(v * 3, v * 3 + 3), md.boneIndices.subarray(v * 4, v * 4 + 4), md.boneWeights.subarray(v * 4, v * 4 + 4), 4);
    for (let c = 0; c < 3; c++) maxErr = Math.max(maxErr, Math.abs(p[c] - ref[v * 3 + c]));
  }
  assert.ok(maxErr < 1e-4, `max error ${maxErr} m`);
  // Sanity: the pose actually moved the mesh (the test can fail).
  let moved = 0;
  for (let i = 0; i < ref.length; i++) moved = Math.max(moved, Math.abs(ref[i] - md.positions[i]));
  assert.ok(moved > 0.05, `pose barely moved the mesh (${moved})`);
  engine.dispose();
});

test('V12: placeholder LODs hit the §8.3 budgets exactly (tris 3500/1400/500/150, bones 60/30/18, influences 4/2/2/2)', () => {
  assert.deepEqual(SKELETONS.map((s) => s.bones.length), [60, 30, 18]);
  const rng = mulberry32(9);
  for (let c = 0; c < 5; c++) {
    const skel = characterSkeleton(randomProportions(rng));
    const pal = randomPalette(rng);
    for (let lod = 0; lod < 4; lod++) {
      const md = buildCharacterLod(skel, lod, pal);
      assert.equal(md.triangles, LOD_TRIS[lod]);
      const maxSlot = SKELETONS[[0, 1, 2, 2][lod]].bones.length;
      for (let v = 0; v < md.vertices; v++) {
        let sum = 0, used = 0;
        for (let k = 0; k < 4; k++) {
          const w = md.boneWeights[v * 4 + k];
          sum += w;
          if (w > 0) used++;
          assert.ok(md.boneIndices[v * 4 + k] < maxSlot);
        }
        assert.ok(Math.abs(sum - 1) < 1e-5, 'weights normalized');
        assert.ok(used <= LOD_INFLUENCES[lod], `LOD${lod} vertex uses ${used} influences`);
      }
    }
  }
});
