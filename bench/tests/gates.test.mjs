// Gate logic tests (SPEC V10, V11) + LOD hysteresis. Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { grade, isGradableRenderer, TIERS, GPU_BUDGET_MS, CPU_BUDGET, HEADROOM } from '../../src/bench/gates.ts';
import { pickLod, LOD_PX, HYSTERESIS } from '../../src/bench/pathC.ts';

const INTEL = 'ANGLE (Intel, Vulkan 1.4.335 (Intel(R) Graphics (RPL-S) (0x0000A780)), Intel open-source Mesa driver)';
const s = (p95) => ({ n: 600, p50: p95 * 0.8, p95 });
const good = () => ({
  renderer: INTEL, frames: 600,
  summary: { cpuChar: s(1.0), anim: s(0.3), uploadCull: s(0.2), submit: s(0.5), gpu: s(1.0) },
});

test('V10: the runner refuses SwiftShader, llvmpipe and NVIDIA renderers as a gate', () => {
  for (const r of [
    'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)',
    'ANGLE (Mesa, llvmpipe (LLVM 19.1.7, 256 bits), OpenGL 4.5)',
    'ANGLE (NVIDIA, Vulkan 1.4 (NVIDIA GeForce RTX 4080 (0x00002704)), NVIDIA-595.91)',
    'unknown',
  ]) {
    assert.equal(isGradableRenderer(r), false, r);
    const g = grade({ ...good(), renderer: r }, TIERS.laptop);
    assert.equal(g.valid, false);
    assert.equal(g.pass, false);
  }
  assert.equal(isGradableRenderer(INTEL), true);
  assert.equal(grade(good(), TIERS.laptop).pass, true);
});

test('V11: every gate fails on its known-bad fixture, and 30% headroom is enforced', () => {
  // GPU: scaled value inside the raw budget but inside the 30% headroom band must FAIL.
  const gpuBand = (GPU_BUDGET_MS * (1 - HEADROOM / 2)) / TIERS.laptop.gpuScale;
  const fixtures = {
    gpu: (r) => { r.summary.gpu = s(gpuBand); },
    cpu: (r) => { r.summary.cpuChar = s(CPU_BUDGET.total * (1 - HEADROOM / 2)); },
    'cpu.anim': (r) => { r.summary.anim = s(CPU_BUDGET.anim * 0.9); },
    'cpu.uploadCull': (r) => { r.summary.uploadCull = s(CPU_BUDGET.uploadCull * 0.9); },
    'cpu.submit': (r) => { r.summary.submit = s(CPU_BUDGET.submit * 0.9); },
  };
  for (const [name, mutate] of Object.entries(fixtures)) {
    const r = good();
    mutate(r);
    const g = grade(r, TIERS.laptop);
    const failed = g.gates.filter((x) => !x.pass).map((x) => x.name);
    assert.deepEqual(failed, [name], `fixture for ${name} failed ${failed}`);
    assert.equal(g.pass, false);
  }
  // The phone tier scales GPU ×4: a value that passes at laptop (×2) fails at phone.
  const r = good();
  r.summary.gpu = s((GPU_BUDGET_MS * (1 - HEADROOM)) / 3);
  assert.equal(grade(r, TIERS.laptop).pass, true);
  assert.equal(grade(r, TIERS.phone).pass, false);
  // Too few GPU samples → invalid, never a pass.
  const r2 = good();
  r2.summary.gpu = { n: 3, p50: 0.1, p95: 0.1 };
  assert.equal(grade(r2, TIERS.laptop).valid, false);
});

test('pickLod: thresholds with hysteresis (no flicker at the boundary)', () => {
  assert.equal(pickLod(LOD_PX[0] * 2, -1), 0);
  assert.equal(pickLod(LOD_PX[0] * 1.05, 1), 1, 'must exceed threshold × (1+H) to promote');
  assert.equal(pickLod(LOD_PX[0] * (1 + HYSTERESIS) + 1, 1), 0);
  assert.equal(pickLod(LOD_PX[0] * 0.95, 0), 0, 'stays until threshold × (1−H)');
  assert.equal(pickLod(LOD_PX[0] * (1 - HYSTERESIS) - 1, 0), 1);
  assert.equal(pickLod(LOD_PX[3] * 0.5, 3), -1);
});
