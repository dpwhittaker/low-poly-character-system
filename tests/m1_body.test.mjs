// M1 body assembler vs MakeHuman itself (SPEC V17, V18). The fixtures come from MPFB in
// pipeline/blender/m1_body/03_pack.py: its own macro stack and our numpy fit of the
// low-poly body for random descriptors. Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseBodyPack } from '../src/character/bodyPack.ts';
import { macroStack } from '../src/character/macro.ts';
import { bakeBody, boneHeads } from '../src/character/assemble.ts';

const root = new URL('..', import.meta.url);
const meta = JSON.parse(readFileSync(new URL('public/m1/body.json', root), 'utf8'));
const bin = readFileSync(new URL('public/m1/body.bin', root));
const pack = parseBodyPack(meta, bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength));
const { cases } = JSON.parse(readFileSync(new URL('tests/fixtures/m1_body_reference.json', root), 'utf8'));

test('V17: macro weights = MPFB calculate_target_stack_from_macro_info_dict (≤2e-4)', () => {
  for (const c of cases) {
    const ours = new Map(macroStack(c.macro, meta.macroParts).filter(([n]) => pack.targetByName.has(n)));
    const theirs = new Map(c.stack);
    assert.deepEqual([...ours.keys()].sort(), [...theirs.keys()].sort());
    for (const [n, w] of theirs) assert.ok(Math.abs(ours.get(n) - w) <= 2e-4, `${n}: ${ours.get(n)} vs ${w}`);
  }
});

test('V18: baked low-poly body + joints = MakeHuman proxy fit (≤0.25 mm)', () => {
  let worst = 0;
  for (const c of cases) {
    const b = bakeBody(pack, { macro: c.macro, sliders: c.sliders, style: 1 });
    for (const [i, p] of Object.entries(c.probe)) {
      for (let k = 0; k < 3; k++) worst = Math.max(worst, Math.abs(b.src[+i * 3 + k] - p[k]));
    }
    for (const [name, p] of Object.entries(c.joints)) {
      const j = meta.joints.indexOf(name);
      for (let k = 0; k < 3; k++) worst = Math.max(worst, Math.abs(b.joints[j * 3 + k] - p[k]));
    }
  }
  assert.ok(worst <= 0.00025, `worst ${(worst * 1000).toFixed(3)} mm`);
});

test('V18: the gate can fail — a dropped target moves the body by > 1 mm', () => {
  const c = cases[3];
  const b = bakeBody(pack, { macro: c.macro, sliders: { ...c.sliders, noseWidth: 0, eyeSize: 0, hips: 0 }, style: 1 });
  let worst = 0;
  for (const [i, p] of Object.entries(c.probe)) for (let k = 0; k < 3; k++) worst = Math.max(worst, Math.abs(b.src[+i * 3 + k] - p[k]));
  assert.ok(worst > 0.001, `only ${(worst * 1000).toFixed(3)} mm`);
});

test('every bone head is finite and every src vertex is skinned', () => {
  const b = bakeBody(pack, { macro: cases[0].macro });
  const h = boneHeads(pack, b.joints, b.groundLift);
  assert.ok(h.every(Number.isFinite));
  for (let v = 0; v < meta.counts.src; v++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += pack.skinWeights[v * 4 + k];
    assert.equal(s, 255, `vertex ${v}`);
  }
});

test('V20: every body keeps the canonical rest rotations; only bone offsets change', async () => {
  const { parseRestSkeleton, fitBoneMatrices } = await import('../src/character/skeletonFit.ts');
  const { Quaternion, Vector3 } = await import('@babylonjs/core');
  const glb = readFileSync(new URL('public/m1/skeleton.glb', root));
  const rest = parseRestSkeleton(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength));
  const heads = (c) => { const b = bakeBody(pack, { macro: c.macro, sliders: c.sliders }); return boneHeads(pack, b.joints, b.groundLift); };
  const A = fitBoneMatrices(pack, rest, heads(cases[0])), B = fitBoneMatrices(pack, rest, heads(cases[4]));
  let moved = 0;
  meta.bones.forEach((b, i) => {
    const qa = new Quaternion(), qb = new Quaternion(), ta = new Vector3(), tb = new Vector3();
    A[i].decompose(undefined, qa, ta); B[i].decompose(undefined, qb, tb);
    const r = rest.rot.get(b.name);
    assert.ok(Math.abs(Math.abs(Quaternion.Dot(qa, new Quaternion(...r))) - 1) < 1e-5, `${b.name} rest rotation changed`);
    assert.ok(Math.abs(Math.abs(Quaternion.Dot(qa, qb)) - 1) < 1e-5, `${b.name} rotation differs between bodies`);
    moved = Math.max(moved, ta.subtract(tb).length());
  });
  assert.ok(moved > 0.01, 'different bodies must move bone heads');
});

test('V21: the skinned character shader registers its bone includes (deep imports)', () => {
  const src = readFileSync(new URL('src/render/characterMaterial.ts', root), 'utf8');
  for (const inc of ['bonesDeclaration', 'bonesVertex']) {
    assert.ok(src.includes(`@babylonjs/core/Shaders/ShadersInclude/${inc}'`), `missing import of ${inc}`);
  }
});

test('V19: every standard cut line is one closed loop, and the base layer bands are bounded', () => {
  for (const [id, c] of Object.entries(meta.cuts)) assert.ok(c.closed, `cut ${id} is open`);
  const sizes = new Map();
  for (const b of pack.triBand) sizes.set(b, (sizes.get(b) ?? 0) + 1);
  const bodyTris = pack.triBand.filter((b) => b !== 255).length;
  for (const b of [meta.bands.baseTop, meta.bands.baseBottom]) assert.ok(sizes.get(b) < 0.2 * bodyTris, `band ${b} leaked`);
});
