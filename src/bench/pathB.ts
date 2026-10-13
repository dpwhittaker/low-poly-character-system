// Path B — custom sampler + ONE shared bone texture (PLAN §8.4 #3), no tiering.
// Every character: LOD0 mesh, one draw, full-rate compose every frame. The
// character's row in the shared texture is a constant per-vertex attribute
// (`charRow`), so all characters share one material with no per-mesh uniforms.

import { Constants, RawTexture, type Scene } from '@babylonjs/core';
import { PoseCache, composeCharacter, writeRoot, FLOATS_PER_ROW, TEXELS_PER_ROW } from './sampler.ts';
import { BASE_CLIPS, GESTURE } from './clips.ts';
import { charPose, type SceneSpec } from './scenes.ts';
import { meshFromData, constantAttr, FrustumTester, type BenchChar, type PathRuntime, type FrameStats } from './common.ts';
import { texSkinMaterial } from './shaders.ts';
import { LOD_TRIS } from './geometry.ts';

export const OVERLAY_WEIGHT = 0.3 / 1.3; // Babylon-normalized equivalent of path A's weights 1 + 0.3

export function createBoneTexture(scene: Scene, rows: number): { tex: RawTexture; data: Float32Array } {
  const data = new Float32Array(rows * FLOATS_PER_ROW);
  const tex = new RawTexture(data, TEXELS_PER_ROW, rows, Constants.TEXTUREFORMAT_RGBA, scene, false, false, Constants.TEXTURE_NEAREST_SAMPLINGMODE, Constants.TEXTURETYPE_FLOAT);
  tex.wrapU = Constants.TEXTURE_CLAMP_ADDRESSMODE;
  tex.wrapV = Constants.TEXTURE_CLAMP_ADDRESSMODE;
  return { tex, data };
}

export function createPathB(scene: Scene, spec: SceneSpec, chars: BenchChar[]): PathRuntime {
  const { tex, data } = createBoneTexture(scene, chars.length);
  const mat = texSkinMaterial(scene, tex, { influences: 4 });
  const cache = new PoseCache(BASE_CLIPS, GESTURE, OVERLAY_WEIGHT);
  const frustum = new FrustumTester();
  const meshes = chars.map((c, i) => {
    const md = c.lods[0];
    const m = meshFromData(`charB${c.spec.id}`, scene, md, [{ kind: 'charRow', data: constantAttr(md.vertices, i), stride: 1 }]);
    m.material = mat;
    m.alwaysSelectAsActiveMesh = true;
    m.doNotSyncBoundingInfo = true;
    m.freezeWorldMatrix();
    return m;
  });
  let visible = 0;
  void spec;
  return {
    name: 'B',
    step(frame, time, camera) {
      const t0 = performance.now();
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i];
        const s = c.spec;
        const pose = cache.get(frame, time, s.state, s.phase, s.ophase, PoseCache.key(s.state, s.bucket, s.obucket));
        composeCharacter(pose, c.skel, 0, data, i);
      }
      const t1 = performance.now();
      frustum.update(camera);
      visible = 0;
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i];
        if (c.spec.walk) { const [x, z, yaw] = charPose(c.spec, time); c.x = x; c.z = z; c.yaw = yaw; }
        writeRoot(data, i, 0, c.x, 0, c.z, c.yaw);
        const vis = frustum.visible(c.x, 0.9, c.z, 1.2);
        meshes[i].isVisible = vis;
        if (vis) visible++;
      }
      tex.update(data);
      const t2 = performance.now();
      return { animMs: t1 - t0, uploadCullMs: t2 - t1 };
    },
    stats(): FrameStats {
      return { visibleChars: visible, visibleTris: visible * LOD_TRIS[0], lod: [visible, 0, 0, 0], composed: chars.length };
    },
  };
}
