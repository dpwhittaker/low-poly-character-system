// Gate logic tests (SPEC V10, V11, V14) + LOD hysteresis. Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { grade, gradeNet, isGradableRenderer, TIERS, GPU_BUDGET_MS, CPU_BUDGET, HEADROOM } from '../../src/bench/gates.ts';
import { pickLod, LOD_PX, HYSTERESIS } from '../../src/bench/pathC.ts';

const INTEL = 'ANGLE (Intel, Vulkan 1.4.335 (Intel(R) Graphics (RPL-S) (0x0000A780)), Intel open-source Mesa driver)';
const s = (p95) => ({ n: 600, p50: p95 * 0.8, p95 });
const good = () => ({
  renderer: INTEL, frames: 600, cpuThrottle: 1,
  summary: { cpuChar: s(1.0), anim: s(0.3), uploadCull: s(0.2), submit: s(0.4), gpu: s(1.0) },
});
const L = TIERS.laptop;
/** a measured value whose tier-scaled value lands inside the 30 % headroom band (85 % of budget) */
const band = (budget, scale) => (budget * (1 - HEADROOM / 2)) / scale;

test('V10: the runner refuses SwiftShader, llvmpipe and NVIDIA renderers as a gate', () => {
  for (const r of [
    'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)',
    'ANGLE (Mesa, llvmpipe (LLVM 19.1.7, 256 bits), OpenGL 4.5)',
    'ANGLE (NVIDIA, Vulkan 1.4 (NVIDIA GeForce RTX 4080 (0x00002704)), NVIDIA-595.91)',
    'unknown',
  ]) {
    assert.equal(isGradableRenderer(r), false, r);
    const g = grade({ ...good(), renderer: r }, L);
    assert.equal(g.valid, false);
    assert.equal(g.pass, false);
  }
  assert.equal(isGradableRenderer(INTEL), true);
  assert.equal(grade(good(), L).pass, true);
});

test('V11: every gate fails on its known-bad fixture, and 30% headroom is enforced (CPU and GPU both tier-scaled)', () => {
  const fixtures = {
    gpu: (r) => { r.summary.gpu = s(band(GPU_BUDGET_MS, L.gpuScale)); },
    cpu: (r) => { r.summary.cpuChar = s(band(CPU_BUDGET.total, L.cpuScale)); },
    'cpu.anim': (r) => { r.summary.anim = s(band(CPU_BUDGET.anim, L.cpuScale)); },
    'cpu.uploadCull': (r) => { r.summary.uploadCull = s(band(CPU_BUDGET.uploadCull, L.cpuScale)); },
    'cpu.submit': (r) => { r.summary.submit = s(band(CPU_BUDGET.submit, L.cpuScale)); },
  };
  for (const [name, mutate] of Object.entries(fixtures)) {
    const r = good();
    mutate(r);
    const g = grade(r, L);
    const failed = g.gates.filter((x) => !x.pass).map((x) => x.name);
    assert.deepEqual(failed, [name], `fixture for ${name} failed ${failed}`);
    assert.equal(g.pass, false);
  }
  // The phone tier scales harder: a value that passes at laptop fails at phone.
  const r = good();
  r.summary.gpu = s((GPU_BUDGET_MS * (1 - HEADROOM)) / 3);
  assert.equal(grade(r, L).pass, true);
  assert.equal(grade(r, TIERS.phone).pass, false);
  const r3 = good();
  r3.summary.cpuChar = s((CPU_BUDGET.total * (1 - HEADROOM)) / 3);
  assert.equal(grade(r3, L).pass, true);
  assert.equal(grade(r3, TIERS.phone).pass, false);
  // Too few GPU samples → invalid, never a pass.
  const r2 = good();
  r2.summary.gpu = { n: 3, p50: 0.1, p95: 0.1 };
  assert.equal(grade(r2, L).valid, false);
});

test('V14: a CPU result measured under CDP throttling is never graded (throttling does not scale sub-ms intervals)', () => {
  const r = good();
  r.cpuThrottle = 2.5;
  const g = grade(r, L);
  assert.equal(g.valid, false);
  assert.equal(g.pass, false);
  assert.match(g.reason, /CDP throttle/);
});

test('V11: net grade subtracts the engine floor (empty scene) and never touches the strict grade', () => {
  const r = good();
  r.path = 'C';
  r.summary.submit = s(band(CPU_BUDGET.submit, L.cpuScale) * 1.2); // strict: fails cpu.submit
  r.summary.renderWall = r.summary.submit;
  const floor = good();
  floor.summary.renderWall = { n: 600, p50: r.summary.submit.p95 * 0.8, p95: r.summary.submit.p95 * 0.9 };
  floor.summary.submit = { n: 600, p50: 0.01, p95: 0.01 };
  assert.equal(grade(r, L).pass, false);
  assert.equal(gradeNet(r, floor, L).gates.find((g) => g.name === 'cpu.submit').pass, true, 'B/C subtract the floor renderWall');
  r.path = 'A';
  assert.equal(gradeNet(r, floor, L).gates.find((g) => g.name === 'cpu.submit').pass, false, 'A subtracts the floor submit (renderTimeCounter)');
});

test('pickLod: thresholds with hysteresis (no flicker at the boundary)', () => {
  assert.equal(pickLod(LOD_PX[0] * 2, -1), 0);
  assert.equal(pickLod(LOD_PX[0] * 1.05, 1), 1, 'must exceed threshold × (1+H) to promote');
  assert.equal(pickLod(LOD_PX[0] * (1 + HYSTERESIS) + 1, 1), 0);
  assert.equal(pickLod(LOD_PX[0] * 0.95, 0), 0, 'stays until threshold × (1−H)');
  assert.equal(pickLod(LOD_PX[0] * (1 - HYSTERESIS) - 1, 0), 1);
  assert.equal(pickLod(LOD_PX[3] * 0.5, 3), -1);
});
