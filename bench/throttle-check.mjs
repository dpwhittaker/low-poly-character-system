#!/usr/bin/env node
// Compare raw vs CDP-throttled timing distributions in a results directory:
// does throttling scale per-frame sub-ms intervals uniformly, or only in coarse pauses?
//   node bench/throttle-check.mjs <results-dir>
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2];
const load = (f) => JSON.parse(readFileSync(join(dir, f), 'utf8'));
const files = readdirSync(dir).filter((f) => f.endsWith('-raw.json'));
for (const raw of files) {
  const base = raw.replace(/-raw\.json$/, '');
  const r = load(raw);
  for (const tier of ['laptop', 'phone']) {
    let t;
    try { t = load(`${base}-${tier}.json`); } catch { continue; }
    const m = (k) => [r.summary[k], t.summary[k]];
    const line = ['cpuChar', 'anim', 'submit'].map((k) => {
      const [a, b] = m(k);
      return `${k}: mean ×${(b.mean / a.mean).toFixed(2)} p50 ×${(b.p50 / a.p50).toFixed(2)} p95 ×${(b.p95 / a.p95).toFixed(2)}`;
    }).join(' | ');
    console.log(`${base} ${tier} (rate ${t.cpuThrottle}): ${line}`);
  }
}
