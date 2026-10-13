// Scaled performance gates (PLAN §8.3 budgets, §8.5 method). Pure functions:
// the runner and the tests share them. Measured on THIS machine's Intel UHD 770
// iGPU with CPU throttling, scaled to the target tiers, with ≥30 % headroom.

export const FRAME_MS = 1000 / 30;
/** characters may use ≤ 40 % of a 30 fps frame on the GPU */
export const GPU_BUDGET_MS = 0.4 * FRAME_MS;
/** character-system CPU per frame: animation ≤ 3 + upload/culling ≤ 2 + submission ≤ 2 */
export const CPU_BUDGET = { total: 7, anim: 3, uploadCull: 2, submit: 2 } as const;
export const HEADROOM = 0.3;

export interface Tier {
  name: 'raw' | 'laptop' | 'phone';
  /** CDP Emulation.setCPUThrottlingRate */
  cpuThrottle: number;
  /** UHD 770 GPU ms × this ≈ the tier's GPU ms */
  gpuScale: number;
  viewport: { width: number; height: number; dpr: number };
  graded: boolean;
}

export const TIERS: Record<Tier['name'], Tier> = {
  raw: { name: 'raw', cpuThrottle: 1, gpuScale: 1, viewport: { width: 1366, height: 768, dpr: 1 }, graded: false },
  laptop: { name: 'laptop', cpuThrottle: 2.5, gpuScale: 2, viewport: { width: 1366, height: 768, dpr: 1 }, graded: true },
  phone: { name: 'phone', cpuThrottle: 5, gpuScale: 4, viewport: { width: 412, height: 915, dpr: 1.5 }, graded: true },
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
  summary: { cpuChar: SeriesLike; anim: SeriesLike; uploadCull: SeriesLike; submit: SeriesLike; gpu: SeriesLike };
}

export interface Gate { name: string; value: number; limit: number; pass: boolean; note?: string }
export interface Grade { tier: Tier['name']; graded: boolean; valid: boolean; reason?: string; pass: boolean; gates: Gate[] }

const gate = (name: string, value: number, budget: number, note?: string): Gate => {
  const limit = budget * (1 - HEADROOM);
  return { name, value, limit, pass: Number.isFinite(value) && value <= limit, note };
};

/** Grade one run at one tier. CPU values are already measured under the tier's throttle; GPU is scaled here. p95 everywhere. */
export function grade(r: ResultLike, tier: Tier): Grade {
  const valid = isGradableRenderer(r.renderer);
  const s = r.summary;
  const gates: Gate[] = [
    gate('gpu', s.gpu.n > 0 ? s.gpu.p95 * tier.gpuScale : NaN, GPU_BUDGET_MS, `UHD 770 p95 ${fmt(s.gpu.p95)} ms × ${tier.gpuScale}`),
    gate('cpu', s.cpuChar.p95, CPU_BUDGET.total),
    gate('cpu.anim', s.anim.p95, CPU_BUDGET.anim),
    gate('cpu.uploadCull', s.uploadCull.p95, CPU_BUDGET.uploadCull),
    gate('cpu.submit', s.submit.p95, CPU_BUDGET.submit),
  ];
  let reason: string | undefined;
  if (!valid) reason = `renderer not gradable: ${r.renderer}`;
  else if (s.gpu.n < Math.min(30, r.frames / 10)) reason = `too few GPU timer samples (${s.gpu.n})`;
  const ok = valid && !reason;
  return { tier: tier.name, graded: tier.graded, valid: ok, reason, pass: ok && gates.every((g) => g.pass), gates };
}

function fmt(v: number) { return Number.isFinite(v) ? v.toFixed(2) : 'n/a'; }
