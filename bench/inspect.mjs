#!/usr/bin/env node
// Print the per-subsystem breakdown of bench result JSON files.
//   node bench/inspect.mjs <result.json>...
import { readFileSync } from 'node:fs';

const f = (v) => (Number.isFinite(v) ? v.toFixed(3) : 'n/a');
for (const file of process.argv.slice(2)) {
  const r = JSON.parse(readFileSync(file, 'utf8'));
  const s = r.summary;
  console.log(`${r.scene}/${r.path}/${r.tier}: cpu ${f(s.cpuChar.p95)} = anim ${f(s.anim.p95)} + uploadCull ${f(s.uploadCull.p95)} (upload ${f(s.upload?.p95)}) + submit ${f(s.submit.p95)} | composed p50 ${s.composed.p50} | draws ${s.draws.p50} | gpu ${f(s.gpu.p95)} (n=${s.gpu.n}) | COI ${r.crossOriginIsolated} | render ${r.viewport.renderW}x${r.viewport.renderH}`);
  for (const [name, seg] of Object.entries(r.segments ?? {})) {
    console.log(`    ${name}: cpu ${f(seg.cpuChar.p95)} submit ${f(seg.submit.p95)} draws ${seg.draws.p50} gpu-n/a lod ${[seg.lod0.p50, seg.lod1.p50, seg.lod2.p50, seg.lod3.p50].join('/')}`);
  }
}
