// Path C — path B plus tiering (PLAN §8.3/§8.4):
//  • LOD by on-screen height with hysteresis; LOD0 capped at LOD0_CAP characters
//  • animation LOD: compose every 1/2/4/8 frames at LOD0/1/2/3 (60/30/15/7.5 Hz), staggered by id; hidden → 0 Hz
//  • skeleton LOD: 60 / 30 / 18 / 18 bones
//  • far tiers batched: every character's LOD2+LOD3 geometry lives in a static per-cell batch mesh;
//    a character is shown in a tier by writing its root into that tier's root slot (zero = collapsed)
//  • blob shadows: one thin-instanced quad draw
//  • draw-distance fade: dithered discard between fade[0] and fade[1] metres; hidden beyond

import { BoundingInfo, Color3, Constants, MeshBuilder, RawTexture, StandardMaterial, Vector3, type Camera, type Mesh, type Scene } from '@babylonjs/core';
import { PoseCache, composeCharacter, writeRoot, zeroSlot } from './sampler.ts';
import { BASE_CLIPS, GESTURE } from './clips.ts';
import { LOD_SKELETON } from './skeleton.ts';
import { LOD_TRIS, type MeshData } from './geometry.ts';
import { charPose, type SceneSpec } from './scenes.ts';
import { meshFromData, constantAttr, FrustumTester, ActiveList, type BenchChar, type PathRuntime, type FrameStats } from './common.ts';
import { texSkinMaterial } from './shaders.ts';
import { createBoneTexture, uploadDirtyRows, OVERLAY_WEIGHT } from './pathB.ts';

/** minimum on-screen height (render px) for LOD k */
export const LOD_PX = [260, 110, 36, 8] as const;
export const LOD0_CAP = 14;
export const HYSTERESIS = 0.15;
/** frames between composes at each LOD (60 / 30 / 15 / 7.5 Hz at 60 fps) */
export const ANIM_PERIOD = [1, 2, 4, 8] as const;

/** LOD for an on-screen height `px`, given the current LOD `cur` (-1 = hidden). Exported for tests. */
export function pickLod(px: number, cur: number): number {
  for (let L = 0; L < 4; L++) {
    const f = L < cur || cur < 0 ? 1 + HYSTERESIS : L === cur ? 1 - HYSTERESIS : 1;
    if (px >= LOD_PX[L] * (cur < 0 && L === 3 ? 1 : f)) return L;
  }
  return -1;
}

export function createPathC(scene: Scene, spec: SceneSpec, chars: BenchChar[], opts: { shadows: boolean; camera: Camera }): PathRuntime {
  const n = chars.length;
  const { tex, data } = createBoneTexture(scene, n);
  const fade = spec.fade;
  const mat4 = texSkinMaterial(scene, tex, { influences: 4, fade });
  const mat2 = texSkinMaterial(scene, tex, { influences: 2, fade });
  const matBatch = texSkinMaterial(scene, tex, { influences: 2, batch: true, fade });
  const cache = new PoseCache(BASE_CLIPS, GESTURE, OVERLAY_WEIGHT);
  const frustum = new FrustumTester();
  const statics = scene.meshes.slice(); // ground etc., created before the characters
  const active = new ActiveList();
  active.install(scene);

  const near: Mesh[][] = [[], []];
  chars.forEach((c, i) => {
    for (const L of [0, 1]) {
      const md = c.lods[L];
      const m = meshFromData(`charC${L}_${c.spec.id}`, scene, md, [{ kind: 'charRow', data: constantAttr(md.vertices, i), stride: 1 }]);
      m.material = L === 0 ? mat4 : mat2;
      m.alwaysSelectAsActiveMesh = true;
      m.doNotSyncBoundingInfo = true;
      m.freezeWorldMatrix();
      m.isVisible = false;
      near[L].push(m);
    }
  });

  // Static far-tier batches, one per spatial cell of home positions.
  const cellOf = new Int32Array(n);
  const cellKeys = new Map<string, number>();
  const members: number[][] = [];
  chars.forEach((c, i) => {
    const key = `${Math.floor(c.spec.hx / spec.cell)},${Math.floor(c.spec.hz / spec.cell)}`;
    let k = cellKeys.get(key);
    if (k === undefined) { k = members.length; cellKeys.set(key, k); members.push([]); }
    members[k].push(i);
    cellOf[i] = k;
  });
  const batches = members.map((ids, k) => {
    const parts: { md: MeshData; row: number; slot: number }[] = [];
    for (const i of ids) { parts.push({ md: chars[i].lods[2], row: i, slot: 1 }, { md: chars[i].lods[3], row: i, slot: 2 }); }
    const nv = parts.reduce((s, p) => s + p.md.vertices, 0);
    const ni = parts.reduce((s, p) => s + p.md.indices.length, 0);
    const merged: MeshData = {
      positions: new Float32Array(nv * 3), normals: new Float32Array(nv * 3), colors: new Float32Array(nv * 4),
      indices: new Uint32Array(ni), boneIndices: new Float32Array(nv * 4), boneWeights: new Float32Array(nv * 4),
      triangles: ni / 3, vertices: nv,
    };
    const charRow = new Float32Array(nv), rootSlot = new Float32Array(nv);
    let v = 0, x = 0;
    for (const p of parts) {
      merged.positions.set(p.md.positions, v * 3); merged.normals.set(p.md.normals, v * 3); merged.colors.set(p.md.colors, v * 4);
      merged.boneIndices.set(p.md.boneIndices, v * 4); merged.boneWeights.set(p.md.boneWeights, v * 4);
      for (let j = 0; j < p.md.indices.length; j++) merged.indices[x + j] = p.md.indices[j] + v;
      charRow.fill(p.row, v, v + p.md.vertices); rootSlot.fill(p.slot, v, v + p.md.vertices);
      v += p.md.vertices; x += p.md.indices.length;
    }
    const m = meshFromData(`farBatch${k}`, scene, merged, [{ kind: 'charRow', data: charRow, stride: 1 }, { kind: 'rootSlot', data: rootSlot, stride: 1 }]);
    m.material = matBatch;
    let minX = Infinity, minZ = Infinity, maxX = -Infinity, maxZ = -Infinity;
    for (const i of ids) {
      const s = chars[i].spec, r = (s.walk?.r ?? 0) + 1.5;
      minX = Math.min(minX, s.hx - r); maxX = Math.max(maxX, s.hx + r); minZ = Math.min(minZ, s.hz - r); maxZ = Math.max(maxZ, s.hz + r);
    }
    m.setBoundingInfo(new BoundingInfo(new Vector3(minX, 0, minZ), new Vector3(maxX, 2.4, maxZ)));
    m.doNotSyncBoundingInfo = true;
    m.freezeWorldMatrix();
    m.isVisible = false;
    return m;
  });
  const batchCount = new Int32Array(batches.length);

  // Blob shadows: one thin-instanced quad.
  let blob: Mesh | null = null;
  let blobBuf: Float32Array | null = null;
  if (opts.shadows) {
    blob = MeshBuilder.CreateGround('blobShadow', { width: 1, height: 1 }, scene);
    const size = 32, px = new Uint8Array(size * size * 4);
    for (let y = 0; y < size; y++) for (let xx = 0; xx < size; xx++) {
      const d = Math.hypot(xx - size / 2 + 0.5, y - size / 2 + 0.5) / (size / 2);
      px[(y * size + xx) * 4 + 3] = Math.round(255 * 0.55 * Math.max(0, 1 - d * d));
    }
    const sm = new StandardMaterial('blobMat', scene);
    sm.disableLighting = true;
    sm.emissiveColor = Color3.Black();
    sm.diffuseColor = Color3.Black();
    sm.opacityTexture = new RawTexture(px, size, size, Constants.TEXTUREFORMAT_RGBA, scene, false, false, Constants.TEXTURE_BILINEAR_SAMPLINGMODE);
    sm.disableDepthWrite = true;
    blob.material = sm;
    blob.isPickable = false;
    blob.alwaysSelectAsActiveMesh = true;
    blobBuf = new Float32Array(16 * n); // scale 0 = every shadow collapsed until shown
    for (let i = 0; i < n; i++) blobBuf[i * 16 + 15] = 1;
    blob.thinInstanceSetBuffer('matrix', blobBuf, 16, false);
    statics.push(blob);
  }

  const lod = new Int8Array(n).fill(-1);
  const dirty = new Uint8Array(n).fill(1);
  const target = new Int8Array(n);
  const px = new Float32Array(n);
  const due = new Int32Array(n);
  const camPos = new Vector3();
  let stats: FrameStats = { visibleChars: 0, visibleTris: 0, lod: [0, 0, 0, 0], composed: 0 };
  const engine = scene.getEngine();
  const cand: number[] = [];

  return {
    name: 'C',
    step(frame, time, camera) {
      const t0 = performance.now();
      frustum.update(camera);
      camPos.copyFrom(camera.globalPosition);
      const fov = (camera as unknown as { fov: number }).fov ?? 0.8;
      const k = engine.getRenderHeight() / (2 * Math.tan(fov / 2));
      cand.length = 0;
      for (let i = 0; i < n; i++) {
        const c = chars[i];
        if (c.spec.walk) { const [x, z, yaw] = charPose(c.spec, time); c.x = x; c.z = z; c.yaw = yaw; }
        const h = 1.75 * c.skel.props.height;
        const dx = c.x - camPos.x, dy = h * 0.5 - camPos.y, dz = c.z - camPos.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        const vis = dist < fade[1] && frustum.visible(c.x, h * 0.5, c.z, h * 0.65);
        px[i] = (h * k) / Math.max(dist, 0.01);
        const L = vis ? pickLod(px[i], lod[i]) : -1;
        target[i] = L;
        if (L === 0) cand.push(i);
      }
      if (cand.length > LOD0_CAP) {
        cand.sort((a, b) => px[b] - px[a]);
        for (let j = LOD0_CAP; j < cand.length; j++) target[cand[j]] = 1;
      }
      let nd = 0;
      active.reset();
      for (const m of statics) active.push(m);
      const counts: [number, number, number, number] = [0, 0, 0, 0];
      let visTris = 0;
      for (let i = 0; i < n; i++) {
        const c = chars[i];
        const L = target[i], prev = lod[i];
        near[0][i].isVisible = L === 0;
        near[1][i].isVisible = L === 1;
        // Roots: rewrite only what moved or changed tier (static characters cost nothing here).
        const moved = c.spec.walk !== undefined;
        if (L !== prev) {
          dirty[i] = 1;
          if (prev === 2) zeroSlot(data, i, 1);
          if (prev === 3) zeroSlot(data, i, 2);
          if (prev >= 2) batchCount[cellOf[i]]--;
          if (L >= 2) batchCount[cellOf[i]]++;
        }
        if (L >= 0 && (moved || L !== prev)) { writeRoot(data, i, L <= 1 ? 0 : L - 1, c.x, 0, c.z, c.yaw); dirty[i] = 1; }
        if (L === 0) active.push(near[0][i]);
        else if (L === 1) active.push(near[1][i]);
        if (L >= 0) {
          counts[L]++;
          visTris += LOD_TRIS[L];
          if (L !== prev || (frame + i) % ANIM_PERIOD[L] === 0) due[nd++] = i;
        }
        lod[i] = L;
        if (blobBuf && (moved || (L >= 0) !== (prev >= 0))) {
          // Babylon row-vector matrix: scale on the diagonal, translation in 12..14.
          const s = L >= 0 ? 0.75 * c.skel.props.girth : 0, o = i * 16;
          blobBuf[o] = s; blobBuf[o + 5] = L >= 0 ? 1 : 0; blobBuf[o + 10] = s; blobBuf[o + 15] = 1;
          blobBuf[o + 12] = c.x; blobBuf[o + 13] = 0.02; blobBuf[o + 14] = c.z;
        }
      }
      for (let b = 0; b < batches.length; b++) {
        const on = batchCount[b] > 0;
        batches[b].isVisible = on;
        if (on) active.push(batches[b]);
      }
      const t1 = performance.now();
      for (let j = 0; j < nd; j++) {
        const i = due[j];
        const s = chars[i].spec;
        const pose = cache.get(frame, time, s.state, s.phase, s.ophase, PoseCache.key(s.state, s.bucket, s.obucket));
        composeCharacter(pose, chars[i].skel, LOD_SKELETON[lod[i]], data, i);
        dirty[i] = 1;
      }
      const t2 = performance.now();
      uploadDirtyRows(scene, tex, data, dirty);
      const tu = performance.now();
      if (blob) blob.thinInstanceBufferUpdated('matrix');
      const t3 = performance.now();
      stats = { visibleChars: counts[0] + counts[1] + counts[2] + counts[3], visibleTris: visTris, lod: counts, composed: nd };
      return { animMs: t2 - t1, uploadCullMs: (t1 - t0) + (t3 - t2), uploadMs: tu - t2 };
    },
    stats: () => stats,
  };
}
