// Path A — the Babylon-native baseline (PLAN §8.2): one merged mesh per
// character, a Babylon Skeleton (bones animated directly, the faster of the
// two native options measured in §8.2) and two weighted AnimationGroups per
// character (base clip + upper-body overlay = 2-layer blending).
//
// Each character gets its own ShaderMaterial instance. A single shared
// ShaderMaterial would be WRONG here: ShaderMaterial.bind() only re-binds
// (bones included) when `scene.getCachedMaterial() !== this`, so consecutive
// characters would all be skinned with the first one's bone texture.

import { Animation, AnimationGroup, Bone, Matrix, Quaternion, Skeleton, TransformNode, type Scene } from '@babylonjs/core';
import { BONES, BONE_COUNT } from './skeleton.ts';
import { BASE_CLIPS, GESTURE, CLIP_FPS, UPPER_MASK, type Clip } from './clips.ts';
import { charPose, type SceneSpec } from './scenes.ts';
import { meshFromData, type BenchChar, type PathRuntime, type FrameStats } from './common.ts';
import { nativeSkinMaterial } from './shaders.ts';
import { LOD_TRIS } from './geometry.ts';

function clipAnimations(clip: Clip): Animation[] {
  const out: Animation[] = [];
  for (let b = 0; b < BONE_COUNT; b++) {
    const a = new Animation(`${clip.name}_${b}`, 'rotationQuaternion', CLIP_FPS, Animation.ANIMATIONTYPE_QUATERNION, Animation.ANIMATIONLOOPMODE_CYCLE);
    const keys = [];
    for (let f = 0; f <= clip.frames; f++) {
      const o = (f % clip.frames) * BONE_COUNT * 4 + b * 4;
      keys.push({ frame: f, value: new Quaternion(clip.quats[o], clip.quats[o + 1], clip.quats[o + 2], clip.quats[o + 3]) });
    }
    a.setKeys(keys);
    out.push(a);
  }
  return out;
}

export function createPathA(scene: Scene, _spec: SceneSpec, chars: BenchChar[]): PathRuntime {
  const baseAnims = BASE_CLIPS.map(clipAnimations);
  const overAnims = clipAnimations(GESTURE);
  const roots: TransformNode[] = [];
  for (const c of chars) {
    const root = new TransformNode(`root${c.spec.id}`, scene);
    root.position.set(c.x, 0, c.z);
    root.rotation.y = c.yaw;
    const sk = new Skeleton(`sk${c.spec.id}`, `sk${c.spec.id}`, scene);
    const bones: Bone[] = [];
    for (let i = 0; i < BONE_COUNT; i++) {
      const p = BONES[i].parent;
      const o = c.skel.offsets;
      bones.push(new Bone(BONES[i].name, sk, p < 0 ? null : bones[p], Matrix.Translation(o[i * 3], o[i * 3 + 1], o[i * 3 + 2])));
      bones[i].rotationQuaternion = Quaternion.Identity();
    }
    const md = c.lods[0];
    const mesh = meshFromData(`charA${c.spec.id}`, scene, md);
    mesh.skeleton = sk;
    mesh.numBoneInfluencers = 4;
    mesh.parent = root;
    mesh.material = nativeSkinMaterial(scene, `matA${c.spec.id}`);
    mesh.metadata = { benchChar: true };
    const base = new AnimationGroup(`base${c.spec.id}`, scene);
    const clip = BASE_CLIPS[c.spec.state];
    for (let b = 0; b < BONE_COUNT; b++) base.addTargetedAnimation(baseAnims[c.spec.state][b], bones[b]);
    const over = new AnimationGroup(`over${c.spec.id}`, scene);
    for (let b = 0; b < BONE_COUNT; b++) if (UPPER_MASK[b]) over.addTargetedAnimation(overAnims[b], bones[b]);
    base.weight = 1;
    over.weight = 0.3;
    base.start(true, 1, 0, clip.frames);
    base.goToFrame(c.spec.phase * CLIP_FPS);
    over.start(true, 1, 0, GESTURE.frames);
    over.goToFrame(c.spec.ophase * CLIP_FPS);
    roots.push(root);
  }
  return {
    name: 'A',
    step(_frame, time) {
      // Walkers move; Babylon animates and skins inside scene.render().
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i];
        if (!c.spec.walk) continue;
        const [x, z, yaw] = charPose(c.spec, time);
        c.x = x; c.z = z; c.yaw = yaw;
        roots[i].position.set(x, 0, z);
        roots[i].rotation.y = yaw;
      }
      return { animMs: 0, uploadCullMs: 0 };
    },
    stats(): FrameStats {
      const active = scene.getActiveMeshes();
      let visible = 0;
      for (let i = 0; i < active.length; i++) if (active.data[i].metadata?.benchChar) visible++;
      return { visibleChars: visible, visibleTris: visible * LOD_TRIS[0], lod: [visible, 0, 0, 0], composed: chars.length };
    },
  };
}
