# Re-grade of bench/results/2026-10-13 against current budgets

Limits with 30% headroom: CPU total ≤ 4.90 · anim ≤ 1.05 · upload+cull ≤ 1.40 · submit ≤ 2.45 ms (tier-scaled; CPU columns are net of the engine floor).

| scene | path | tier | cpu (net) | anim | upload+cull | submit (net) | gpu | strict | net |
|---|---|---|---|---|---|---|---|---|---|
| meadow | A | laptop | 19.07✗ | 16.02✗ | 4.10✗ | 0.37 | 3.81 | FAIL: cpu, cpu.anim, cpu.uploadCull | FAIL: cpu, cpu.anim, cpu.uploadCull |
| meadow | A | phone | 43.18✗ | 39.93✗ | 4.60✗ | 0.47 | 3.88 | FAIL: cpu, cpu.anim, cpu.uploadCull | FAIL: cpu, cpu.anim, cpu.uploadCull |
| meadow | B | laptop | 3.97 | 2.94✗ | 0.39 | 1.05 | 2.67 | FAIL: cpu.anim | FAIL: cpu.anim |
| meadow | B | phone | 6.95✗ | 5.40✗ | 0.78 | 1.15 | 3.11 | FAIL: cpu, cpu.anim, cpu.submit | FAIL: cpu, cpu.anim |
| meadow | C | laptop | 1.92 | 0.16 | 0.69 | 1.18 | 1.53 | PASS | PASS |
| meadow | C | phone | 3.18 | 0.25 | 1.05 | 2.02 | 2.57 | FAIL: cpu.submit | PASS |
| plaza | A | laptop | 19.52✗ | 16.23✗ | 5.79✗ | 0.59 | 5.13 | FAIL: cpu, cpu.anim, cpu.uploadCull | FAIL: cpu, cpu.anim, cpu.uploadCull |
| plaza | A | phone | 40.60✗ | 36.72✗ | 7.47✗ | 0.72 | 6.83 | FAIL: cpu, cpu.anim, cpu.uploadCull | FAIL: cpu, cpu.anim, cpu.uploadCull |
| plaza | B | laptop | 4.21 | 2.65✗ | 0.41 | 1.32 | 3.43 | FAIL: cpu, cpu.anim | FAIL: cpu.anim |
| plaza | B | phone | 7.53✗ | 5.37✗ | 0.82 | 1.65 | 4.83 | FAIL: cpu, cpu.anim, cpu.submit | FAIL: cpu, cpu.anim |
| plaza | C | laptop | 2.00 | 0.53 | 0.77 | 0.97 | 2.41 | PASS | PASS |
| plaza | C | phone | 3.82 | 0.88 | 1.32 | 1.97 | 4.54 | FAIL: cpu, cpu.submit | PASS |
