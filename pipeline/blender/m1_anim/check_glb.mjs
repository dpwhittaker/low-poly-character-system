// P6 GLB check: load public/m1/anim/clips.glb in Babylon (NullEngine, Node) and verify the
// animation groups against the canonical game_engine skeleton.
//
//   node pipeline/blender/m1_anim/check_glb.mjs [path/to/clips.glb]
//
// Prints group names, durations (s), frame counts, channel counts; fails (exit 1) if a target
// is not one of the 53 canonical bones, a group lacks a bone's rotation, or any translation
// targets something other than `pelvis`.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { NullEngine, Scene } from '@babylonjs/core';
import { LoadAssetContainerAsync } from '@babylonjs/core/Loading/sceneLoader.js';
import '@babylonjs/loaders/glTF/2.0/index.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '..', '..', '..');
const file = process.argv[2] ?? path.join(repo, 'public', 'm1', 'anim', 'clips.glb');
const canon = JSON.parse(readFileSync(path.join(here, 'canonical_rest.json'), 'utf8')).bones.map((b) => b.name);

const engine = new NullEngine();
const scene = new Scene(engine);
const bytes = new Uint8Array(readFileSync(file));
const c = await LoadAssetContainerAsync(bytes, scene, { pluginExtension: '.glb' });

const errors = [];
const skel = c.skeletons[0];
const boneNames = new Set(skel ? skel.bones.map((b) => b.name) : []);
for (const n of canon) if (!boneNames.has(n)) errors.push(`skeleton lacks bone ${n}`);
if (skel && skel.bones.length !== canon.length) errors.push(`skeleton has ${skel.bones.length} bones, want ${canon.length}`);

const rows = [];
for (const g of c.animationGroups) {
  const fps = g.targetedAnimations[0]?.animation.framePerSecond ?? 60; // the glTF loader keys at 60/s
  const dur = (g.to - g.from) / fps;
  const rot = new Set();
  let tr = 0;
  for (const ta of g.targetedAnimations) {
    const name = ta.target?.name;
    if (!canon.includes(name)) errors.push(`${g.name}: target ${name} is not a canonical bone`);
    const prop = ta.animation.targetProperty;
    if (prop === 'rotationQuaternion') rot.add(name);
    else if (prop === 'position') {
      tr++;
      if (name !== 'pelvis') errors.push(`${g.name}: translation on ${name}`);
    } else errors.push(`${g.name}: unexpected channel ${prop} on ${name}`);
  }
  for (const n of canon) if (!rot.has(n)) errors.push(`${g.name}: no rotation channel for ${n}`);
  const keys = g.targetedAnimations[0]?.animation.getKeys().length ?? 0;
  rows.push({ name: g.name, duration_s: +dur.toFixed(4), keys, rotation: rot.size, translation: tr });
  if (Math.abs((keys - 1) / 30 - dur) > 1e-3) errors.push(`${g.name}: ${keys} keys over ${dur}s is not 30 fps`);
}
// End-to-end pose check: play each group in Babylon and compare joint heights with the
// Blender FK reference written by 30_export.py (animation extras `probe_heights`).
c.addAllToScene();
const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + new DataView(bytes.buffer, bytes.byteOffset).getUint32(12, true))));
const extras = Object.fromEntries((gltf.animations ?? []).map((a) => [a.name, a.extras ?? {}]));
const nodes = Object.fromEntries(c.transformNodes.map((t) => [t.name, t]));
let maxErr = 0;
for (const g of c.animationGroups) g.stop();
for (const g of c.animationGroups) {
  const probe = extras[g.name]?.probe_heights;
  if (!probe) { errors.push(`${g.name}: no probe_heights extras`); continue; }
  const fps = g.targetedAnimations[0].animation.framePerSecond;
  for (const [f, want] of Object.entries(probe)) {
    g.start(false, 1, g.from, g.to);
    g.goToFrame(g.from + (Number(f) / 30) * fps);
    g.pause();
    for (const t of c.transformNodes) t.computeWorldMatrix(true);
    for (const n of c.rootNodes) n.computeWorldMatrix(true);
    for (const [bone, z] of Object.entries(want)) {
      const node = nodes[bone];
      node.computeWorldMatrix(true);
      const y = node.getAbsolutePosition().y;
      const e = Math.abs(y - z);
      maxErr = Math.max(maxErr, e);
      if (e > 0.002) errors.push(`${g.name} f${f} ${bone}: babylon y ${y.toFixed(4)} vs blender z ${z}`);
    }
    g.stop();
  }
}
console.log(`pose check: max |babylon height - blender FK height| = ${(maxErr * 1000).toFixed(3)} mm`);
const meshes = c.meshes.filter((m) => m.getTotalVertices() > 0).map((m) => ({ name: m.name, verts: m.getTotalVertices(), skinned: !!m.skeleton }));
console.log(JSON.stringify({ file: path.relative(repo, file), bones: skel?.bones.length, meshes, groups: rows }, null, 1));
if (errors.length) {
  console.error('FAIL\n' + errors.slice(0, 40).join('\n'));
  process.exit(1);
}
console.log('OK: every target is a canonical bone; 53 rotation channels per group; translation only on pelvis');
