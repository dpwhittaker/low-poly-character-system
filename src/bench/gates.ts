// Scaled performance gates (PLAN §8.3 budgets, §8.5 method). Pure functions:
// the runner and the tests share them. Measured on THIS machine (Intel UHD 770
// iGPU + i7-14700K), then scaled to the target tiers, with ≥30 % headroom.
//
// CPU is scaled the same way as GPU: measured UNthrottled, × tier factor.
// ⊥ CDP Emulation.setCPUThrottlingRate as the gate: measured 2026-10-13 it
// slowed sub-ms per-frame intervals by only 0.6–1.2× at nominal 2.5×/5× (it
// suspends the main thread in coarse slices, so short intervals mostly miss
// the pauses), while long frames (path A) slowed 1.6–2.7×. It stays available
// as an informational cross-check (`--cdp-throttle`).

export const FRAME_MS = 1000 / 30;
/** characters may use ≤ 40 % of a 30 fps frame on the GPU */
export const GPU_BUDGET_MS = 0.4 * FRAME_MS;
/** character-system CPU per frame: animation ≤ 3 + upload/culling ≤ 2 + submission ≤ 2 */
export const CPU_BUDGET = { total: 7, anim: 3, uploadCull: 2, submit: 2 } as const;
export const HEADROOM = 0.3;

export interface Tier {
  name: 'raw' | 'laptop' | 'phone';
  /** measured CPU ms × this ≈ the tier's CPU ms (i7-14700K single-thread vs the tier) */
  cpuScale: number;
  /** UHD 770 GPU ms × this ≈ the tier's GPU ms */
  gpuScale: number;
  /** CDP Emulation.setCPUThrottlingRate when the runner is given --cdp-throttle (informational only) */
  cdpThrottle: number;
  viewport: { width: number; height: number; dpr: number };
  graded: boolean;
}

export const TIERS: Record<Tier['name'], Tier> = {
  raw: { name: 'raw', cpuScale: 1, gpuScale: 1, cdpThrottle: 1, viewport: { width: 1366, height: 768, dpr: 1 }, graded: false },
  laptop: { name: 'laptop', cpuScale: 2.5, gpuScale: 2, cdpThrottle: 2.5, viewport: { width: 1366, height: 768, dpr: 1 }, graded: true },
  phone: { name: 'phone', cpuScale: 5, gpuScale: 4, cdpThrottle: 5, viewport: { width: 412, height: 915, dpr: 1.5 }, graded: true },
};

/** Only a real Intel iGPU result may be graded (SPEC V10). */
export function isGradableRenderer(renderer: string): boolean {
  if (/swiftshader|llvmpipe|lavapipe|softpipe|nvidia|geforce|microsoft basic|software/i.test(renderer)) return false;
  return /intel/i.test(renderer);
}

export interface SeriesLike { n: number; p50: number; p95: number }
export interface ResultLike {
  renderer: string;
  frames: number;
  path?: string;
  /** CDP throttle the run was measured under; must be 1 for a gradable CPU result */
  cpuThrottle?: number;
  summary: { cpuChar: SeriesLike; anim: SeriesLike; uploadCull: SeriesLike; submit: SeriesLike; gpu: SeriesLike; renderWall?: SeriesLike };
}

export interface Gate { name: string; value: number; limit: number; pass: boolean; note?: string }
export interface Grade { tier: Tier['name']; graded: boolean; valid: boolean; reason?: string; pass: boolean; gates: Gate[] }

const gate = (name: string, value: number, budget: number, note?: string): Gate => {
  const limit = budget * (1 - HEADROOM);
  return { name, value, limit, pass: Number.isFinite(value) && value <= limit, note };
};

/** Grade one unthrottled run at one tier: CPU and GPU p95 are both scaled by the tier's factors here. */
export function grade(r: ResultLike, tier: Tier): Grade {
  const valid = isGradableRenderer(r.renderer);
  const s = r.summary;
  const c = tier.cpuScale;
  const gates: Gate[] = [
    gate('gpu', s.gpu.n > 0 ? s.gpu.p95 * tier.gpuScale : NaN, GPU_BUDGET_MS, `UHD 770 p95 ${fmt(s.gpu.p95)} ms × ${tier.gpuScale}`),
    gate('cpu', s.cpuChar.p95 * c, CPU_BUDGET.total, `p95 ${fmt(s.cpuChar.p95)} ms × ${c}`),
    gate('cpu.anim', s.anim.p95 * c, CPU_BUDGET.anim),
    gate('cpu.uploadCull', s.uploadCull.p95 * c, CPU_BUDGET.uploadCull),
    gate('cpu.submit', s.submit.p95 * c, CPU_BUDGET.submit),
  ];
  let reason: string | undefined;
  if (!valid) reason = `renderer not gradable: ${r.renderer}`;
  else if ((r.cpuThrottle ?? 1) !== 1) reason = `CPU measured under CDP throttle ${r.cpuThrottle}× (informational only; grade unthrottled runs)`;
  else if (s.gpu.n < Math.min(30, r.frames / 10)) reason = `too few GPU timer samples (${s.gpu.n})`;
  const ok = valid && !reason;
  return { tier: tier.name, graded: tier.graded, valid: ok, reason, pass: ok && gates.every((g) => g.pass), gates };
}

/**
 * "Net" grade: the same gates after subtracting the engine floor, i.e. what
 * `scene.render()` costs with ZERO characters (the `empty` scene: clear, camera,
 * ground, instrumentation) at the same tier. That floor is real, but the world
 * pays it whether or not characters exist, so it belongs in the world/engine
 * share of the frame, not the character system's. Reported next to the strict grade, never instead of it.
 */
export function gradeNet(r: ResultLike, floor: ResultLike, tier: Tier): Grade {
  const fs = floor.summary;
  const sub = (a: SeriesLike, b: SeriesLike): SeriesLike => ({ n: a.n, p50: Math.max(0, a.p50 - b.p50), p95: Math.max(0, a.p95 - b.p50) });
  // Path A's `submit` is Babylon's renderTimeCounter; B/C's is the scene.render() wall time. Subtract the matching floor.
  const floorSubmit = r.path === 'A' ? fs.submit : (fs.renderWall ?? fs.submit);
  const net: ResultLike = {
    ...r,
    summary: { ...r.summary, cpuChar: sub(r.summary.cpuChar, fs.cpuChar), submit: sub(r.summary.submit, floorSubmit), gpu: sub(r.summary.gpu, fs.gpu) },
  };
  return grade(net, tier);
}

function fmt(v: number) { return Number.isFinite(v) ? v.toFixed(2) : 'n/a'; }
