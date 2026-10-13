#!/usr/bin/env node
// Screenshot one bench scene/path for a visual check (uses dist-bench/; a bench run or `npm test` builds it).
//   node bench/shot.mjs <scene> <path> <frames> <out.png> [tier] [hold]
// `hold` (0..1) freezes the camera at that fraction of the scene's camera path,
// e.g. plaza 0.15 = conversation shot, 0.5 = street, 0.9 = overview.
import { serve, launch, runOne } from './run.mjs';

const [, , scene = 'single', path = 'B', frames = '20', out = 'shot.png', tier = 'raw', hold = null] = process.argv;
const { server, port } = await serve();
const browser = await launch();
try {
  const r = await runOne(browser, port, { scene, path, tier, frames: +frames, warmup: 5, seed: 1234, screenshot: out, hold: hold === null ? null : +hold });
  console.log(JSON.stringify({ draws: r.summary.draws.p50, lod: [r.summary.lod0.p50, r.summary.lod1.p50, r.summary.lod2.p50, r.summary.lod3.p50], renderer: r.renderer }));
} finally {
  await browser.close();
  server.close();
}
