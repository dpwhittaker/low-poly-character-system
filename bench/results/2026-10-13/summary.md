# M0 crowd bench — 2026-10-13

Renderer: ANGLE (Intel, Vulkan 1.4.335 (Intel(R) Graphics (RPL-S) (0x0000A780)), Intel open-source Mesa driver)

Gates (PLAN §8.5): p95 values measured unthrottled on this box, then scaled — CPU × 2.5 (laptop) / × 5 (phone), GPU (UHD 770) × 2 / × 4. Limits: GPU ≤ 9.33 ms; CPU ≤ 4.90 ms total (anim ≤ 2.10, upload+cull ≤ 1.40, submit ≤ 1.40) — all with 30 % headroom. Tier "raw" is informational. "load" = 1-min load average when the run started (28 threads; other sessions share this machine).

"strict" grades absolute p95 values. "net of engine floor" grades the same gates after subtracting the `empty` scene's p50 (scene.render() with zero characters: clear, camera, ground, instrumentation), which the world pays regardless of characters (`gradeNet` in src/bench/gates.ts).

| scene | path | tier | CPU p95 ms measured → scaled (anim / upl+cull / submit, measured) | GPU p95 ms UHD 770 → scaled | draws p50 | tris p50 (visible) | LOD mix p50 | load | strict verdict | net of engine floor |
|---|---|---|---|---|---|---|---|---|---|---|
| empty | A | raw | 0.48 → 0.48 (0.01 / 0.06 / 0.23) | 0.74 → 0.74 | 1 | 2 (0) | 0/0/0/0 | 1.27 | info | floor |
| plaza | A | raw | 8.74 → 8.74 (6.84 / 2.32 / 0.38) | 2.58 → 2.58 | 38 | 129502 (129500) | 37/0/0/0 | 0.99 | info | info |
| plaza | B | raw | 2.15 → 2.15 (1.19 / 0.18 / 0.90) | 1.72 → 1.72 | 36 | 122502 (122500) | 35/0/0/0 | 0.99 | info | info |
| plaza | C | raw | 1.17 → 1.17 (0.21 / 0.30 / 0.72) | 1.20 → 1.20 | 13 | 69052 (35850) | 3/6/20/0 | 1.07 | info | info |
| meadow | A | raw | 8.51 → 8.51 (6.78 / 1.56 / 0.28) | 1.89 → 1.89 | 52 | 178502 (178500) | 51/0/0/0 | 1.06 | info | info |
| meadow | B | raw | 1.92 → 1.92 (1.05 / 0.16 / 0.77) | 1.33 → 1.33 | 52 | 178502 (178500) | 51/0/0/0 | 0.97 | info | info |
| meadow | C | raw | 1.03 → 1.03 (0.06 / 0.27 / 0.74) | 0.76 → 0.76 | 6 | 21002 (3150) | 0/0/0/20 | 0.82 | info | info |
| empty | A | laptop | 0.45 → 1.11 (0.01 / 0.06 / 0.21) | 0.74 → 1.48 | 1 | 2 (0) | 0/0/0/0 | 0.72 | PASS | floor |
| plaza | A | laptop | 8.15 → 20.38 (6.49 / 2.32 / 0.39) | 2.57 → 5.13 | 38 | 129502 (129500) | 37/0/0/0 | 0.63 | FAIL (cpu, cpu.anim, cpu.uploadCull) | FAIL (cpu, cpu.anim, cpu.uploadCull) |
| plaza | B | laptop | 2.03 → 5.06 (1.06 / 0.16 / 0.86) | 1.71 → 3.43 | 36 | 122502 (122500) | 35/0/0/0 | 0.69 | FAIL (cpu, cpu.anim, cpu.submit) | FAIL (cpu.anim) |
| plaza | C | laptop | 1.14 → 2.85 (0.21 / 0.31 / 0.72) | 1.21 → 2.41 | 13 | 69052 (35850) | 3/6/20/0 | 0.62 | FAIL (cpu.submit) | PASS |
| meadow | A | laptop | 7.97 → 19.92 (6.41 / 1.64 / 0.30) | 1.90 → 3.81 | 52 | 178502 (178500) | 51/0/0/0 | 0.62 | FAIL (cpu, cpu.anim, cpu.uploadCull) | FAIL (cpu, cpu.anim, cpu.uploadCull) |
| meadow | B | laptop | 1.93 → 4.82 (1.18 / 0.15 / 0.75) | 1.34 → 2.67 | 52 | 178502 (178500) | 51/0/0/0 | 0.53 | FAIL (cpu.anim, cpu.submit) | FAIL (cpu.anim) |
| meadow | C | laptop | 1.11 → 2.78 (0.07 / 0.28 / 0.81) | 0.76 → 1.53 | 6 | 21002 (3150) | 0/0/0/20 | 0.94 | FAIL (cpu.submit) | PASS |
| empty | A | phone | 0.49 → 2.43 (0.01 / 0.06 / 0.23) | 0.64 → 2.58 | 1 | 2 (0) | 0/0/0/0 | 0.73 | PASS | floor |
| plaza | A | phone | 8.45 → 42.27 (7.34 / 1.49 / 0.30) | 1.71 → 6.83 | 20 | 66502 (66500) | 19/0/0/0 | 0.62 | FAIL (cpu, cpu.anim, cpu.uploadCull, cpu.submit) | FAIL (cpu, cpu.anim, cpu.uploadCull) |
| plaza | B | phone | 1.84 → 9.20 (1.07 / 0.16 / 0.66) | 1.21 → 4.83 | 19 | 63002 (63000) | 18/0/0/0 | 0.79 | FAIL (cpu, cpu.anim, cpu.submit) | FAIL (cpu, cpu.anim, cpu.submit) |
| plaza | C | phone | 1.10 → 5.50 (0.18 / 0.26 / 0.72) | 1.13 → 4.54 | 13 | 58252 (28500) | 4/4/5/0 | 0.68 | FAIL (cpu, cpu.submit) | FAIL (cpu.submit) |
| meadow | A | phone | 8.97 → 44.85 (7.99 / 0.92 / 0.24) | 0.97 → 3.88 | 17 | 56002 (56000) | 16/0/0/0 | 1.10 | FAIL (cpu, cpu.anim, cpu.uploadCull) | FAIL (cpu, cpu.anim, cpu.uploadCull) |
| meadow | B | phone | 1.72 → 8.62 (1.08 / 0.16 / 0.56) | 0.78 → 3.11 | 17 | 56002 (56000) | 16/0/0/0 | 1.17 | FAIL (cpu, cpu.anim, cpu.submit) | FAIL (cpu, cpu.anim) |
| meadow | C | phone | 0.97 → 4.85 (0.05 / 0.21 / 0.74) | 0.64 → 2.57 | 6 | 21002 (1500) | 0/0/0/10 | 0.91 | FAIL (cpu.submit) | FAIL (cpu.submit) |
