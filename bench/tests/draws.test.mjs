// Browser test (SPEC V9): a near-tier character costs exactly 1 draw call on
// every path, read from Babylon's engine draw counter (never a mesh count).
// Builds the bench page and launches headless Chrome on the Intel iGPU (~1–2 min).
import test from 'node:test';
import assert from 'node:assert/strict';
import { runSelfTest } from '../run.mjs';

test('V9: one near-tier character = exactly 1 draw call (engine counter) on paths A, B and C', { timeout: 600000 }, async () => {
  const r = await runSelfTest({ build: process.env.BENCH_NO_BUILD !== '1' });
  for (const path of ['A', 'B', 'C']) {
    assert.equal(r[path].gradable, true, `renderer ${r[path].renderer}`);
    assert.equal(r[path].lod0, 1, `${path}: character not at LOD0`);
    assert.equal(r[path].drawsP50, 1, `${path}: ${r[path].drawsP50} draws`);
    assert.equal(r[path].drawsMax, 1, `${path}: max ${r[path].drawsMax} draws`);
  }
});
