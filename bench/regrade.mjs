#!/usr/bin/env node
// Re-grade stored bench results against the CURRENT budgets (src/bench/gates.ts) without
// re-measuring. Measurements are never edited; this prints, and writes <dir>/regrade.md.
//   node bench/regrade.mjs bench/results/<date>
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { TIERS, grade, gradeNet, CPU_BUDGET, HEADROOM } from '../src/bench/gates.ts';

const dir = process.argv[2];
const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
const load = (f) => JSON.parse(readFileSync(join(dir, f), 'utf8'));
const f2 = (v) => (Number.isFinite(v) ? v.toFixed(2) : 'n/a');
const verdict = (g) => (!g ? '—' : !g.valid ? `INVALID (${g.reason})` : g.pass ? 'PASS' : 'FAIL: ' + g.gates.filter((x) => !x.pass).map((x) => x.name).join(', '));
const rows = [];
for (const f of files.filter((x) => !x.startsWith('empty-')).sort()) {
  const r = load(f);
  const tier = TIERS[r.tier];
  if (!tier || r.tier === 'raw') continue;
  const floorFile = `empty-floor-${r.tier}.json`;
  const floor = files.includes(floorFile) ? load(floorFile) : null;
  const g = grade(r, tier);
  const n = floor ? gradeNet(r, floor, tier) : null;
  const cell = (gg, name) => { const x = gg?.gates.find((y) => y.name === name); return x ? `${f2(x.value)}${x.pass ? '' : '✗'}` : '—'; };
  rows.push(`| ${r.scene} | ${r.path} | ${r.tier} | ${cell(n, 'cpu')} | ${cell(n, 'cpu.anim')} | ${cell(n, 'cpu.uploadCull')} | ${cell(n, 'cpu.submit')} | ${cell(g, 'gpu')} | ${verdict(g)} | ${verdict(n)} |`);
}
const lim = (b) => f2(b * (1 - HEADROOM));
const md = `# Re-grade of ${dir} against current budgets\n\nLimits with ${HEADROOM * 100}% headroom: CPU total ≤ ${lim(CPU_BUDGET.total)} · anim ≤ ${lim(CPU_BUDGET.anim)} · upload+cull ≤ ${lim(CPU_BUDGET.uploadCull)} · submit ≤ ${lim(CPU_BUDGET.submit)} ms (tier-scaled; CPU columns are net of the engine floor).\n\n| scene | path | tier | cpu (net) | anim | upload+cull | submit (net) | gpu | strict | net |\n|---|---|---|---|---|---|---|---|---|---|\n${rows.join('\n')}\n`;
writeFileSync(join(dir, 'regrade.md'), md);
console.log(md);
