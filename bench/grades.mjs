#!/usr/bin/env node
// Print strict and net gate values for bench result files.
//   node bench/grades.mjs <result.json>...
import { readFileSync } from 'node:fs';

const f = (v) => (Number.isFinite(v) ? v.toFixed(2) : 'n/a');
for (const file of process.argv.slice(2)) {
  const r = JSON.parse(readFileSync(file, 'utf8'));
  for (const [label, g] of [['strict', r.grade], ['net', r.gradeNet]]) {
    if (!g) continue;
    console.log(`${r.scene}/${r.path}/${r.tier} ${label}: ${g.pass ? 'PASS' : 'FAIL'}  ` + g.gates.map((x) => `${x.name} ${f(x.value)}/${f(x.limit)}${x.pass ? '' : '✗'}`).join('  '));
  }
}
