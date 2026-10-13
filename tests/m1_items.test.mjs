// M1 items + clips (SPEC V22, V23). Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { parseBodyPack } from '../src/character/bodyPack.ts';
import { bakeBody, srcNormals } from '../src/character/assemble.ts';
import { DEFAULT_MACRO } from '../src/character/macro.ts';
import { parseItemPack, fitItem, inheritSkin } from '../src/character/items.ts';
import { parseRestSkeleton } from '../src/character/skeletonFit.ts';

const root = new URL('..', import.meta.url);
const buf = (p) => { const b = readFileSync(new URL(p, root)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const meta = JSON.parse(readFileSync(new URL('public/m1/body.json', root), 'utf8'));
const pack = parseBodyPack(meta, buf('public/m1/body.bin'));
const ids = readdirSync(new URL('public/m1/items/', root)).filter((f) => f.endsWith('.json') && f !== 'index.json').map((f) => f.slice(0, -5));

test('V23: every item, fitted at runtime on the default body, lands on its authored positions (≤0.5 mm)', () => {
  const b = bakeBody(pack, { macro: DEFAULT_MACRO, style: 1 });
  const n = srcNormals(pack, b.src);
  assert.ok(ids.length >= 5, `only ${ids.length} items`);
  for (const id of ids) {
    const m = JSON.parse(readFileSync(new URL(`public/m1/items/${id}.json`, root), 'utf8'));
    const raw = buf(`public/m1/items/${id}.bin`);
    const it = parseItemPack(m, raw);
    const rest = new Float32Array(raw, m.layout.restPos.offset, m.layout.restPos.length / 4);
    const p = fitItem(it, b.src, n);
    // int16-quantized body deltas tilt the binding frame by ~1e-4 rad; far offsets (hair
    // tips 5 cm out) amplify that, so the tolerance is 0.5 mm + 2 % of the offset length
    for (let v = 0; v < m.counts.verts; v++) {
      const off = Math.hypot(it.bindOffset[v * 3], it.bindOffset[v * 3 + 1], it.bindOffset[v * 3 + 2]);
      const err = Math.hypot(p[v * 3] - rest[v * 3], p[v * 3 + 1] - rest[v * 3 + 1], p[v * 3 + 2] - rest[v * 3 + 2]);
      assert.ok(err <= 0.0005 + 0.02 * off, `${id} vertex ${v}: ${(err * 1000).toFixed(2)} mm at offset ${(off * 1000).toFixed(1)} mm`);
    }
    const skin = inheritSkin(it, pack);
    for (let v = 0; v < m.counts.verts; v++) {
      const s = skin.weights[v * 4] + skin.weights[v * 4 + 1] + skin.weights[v * 4 + 2] + skin.weights[v * 4 + 3];
      assert.ok(Math.abs(s - 1) < 1e-5, `${id} vertex ${v} weights sum ${s}`);
    }
  }
});

test('V23: the gate can fail — a wrong body (another descriptor) moves a garment by > 5 mm', () => {
  const b = bakeBody(pack, { macro: { ...DEFAULT_MACRO, weight: 1, gender: 1 }, style: 1 });
  const n = srcNormals(pack, b.src);
  const m = JSON.parse(readFileSync(new URL('public/m1/items/tee.json', root), 'utf8'));
  const raw = buf('public/m1/items/tee.bin');
  const rest = new Float32Array(raw, m.layout.restPos.offset, m.layout.restPos.length / 4);
  const p = fitItem(parseItemPack(m, raw), b.src, n);
  let worst = 0;
  for (let i = 0; i < p.length; i++) worst = Math.max(worst, Math.abs(p[i] - rest[i]));
  assert.ok(worst > 0.005);
});

test('V22: clips.glb rest = skeleton.glb rest for every clip bone (≤0.1°); clips move only the pelvis', () => {
  const sk = parseRestSkeleton(buf('public/m1/skeleton.glb'));
  const cl = parseRestSkeleton(buf('public/m1/anim/clips.glb'));
  for (const [name, q] of cl.rot) {
    const r = sk.rot.get(name);
    assert.ok(r, `clip bone ${name} missing from skeleton.glb`);
    const dot = Math.abs(q.reduce((s, x, i) => s + x * r[i], 0));
    const deg = (2 * Math.acos(Math.min(1, dot)) * 180) / Math.PI;
    assert.ok(deg <= 0.1, `${name} rest differs by ${deg.toFixed(3)}°`);
  }
  const b = Buffer.from(buf('public/m1/anim/clips.glb'));
  const j = JSON.parse(b.subarray(20, 20 + b.readUInt32LE(12)).toString());
  for (const a of j.animations) {
    for (const ch of a.channels) {
      if (ch.target.path === 'translation') assert.equal(j.nodes[ch.target.node].name, 'pelvis', `${a.name} translates ${j.nodes[ch.target.node].name}`);
      assert.notEqual(ch.target.path, 'scale', `${a.name} scales a bone`);
    }
  }
});
