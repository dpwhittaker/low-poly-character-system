// Percentile summaries for bench series.

export interface Series { n: number; mean: number; p50: number; p95: number; p99: number; max: number }

export function summarize(values: number[]): Series {
  const n = values.length;
  if (n === 0) return { n: 0, mean: NaN, p50: NaN, p95: NaN, p99: NaN, max: NaN };
  const s = [...values].sort((a, b) => a - b);
  const pct = (p: number) => s[Math.min(n - 1, Math.max(0, Math.ceil((p / 100) * n) - 1))];
  let sum = 0;
  for (const v of s) sum += v;
  return { n, mean: sum / n, p50: pct(50), p95: pct(95), p99: pct(99), max: s[n - 1] };
}
