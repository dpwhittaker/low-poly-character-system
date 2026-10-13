#!/usr/bin/env node
// M0 crowd bench runner (PLAN §8.5, SPEC §I bench). Builds bench/index.html,
// serves it on a temporary loopback port (5390–5399), runs every
// scene × path × tier in headless Chrome pinned to the Intel UHD 770 iGPU,
// grades each run against the scaled gates and writes JSON + a markdown table.
//
//   npm run bench                         # everything (2 scenes × 3 paths × 3 tiers)
//   npm run bench -- --scenes plaza --paths A,B --tiers laptop --frames 300
//   npm run bench -- --no-build           # reuse dist-bench/
//   npm run bench -- --selftest           # single-character draw-call check (SPEC V9)
import { spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { loadavg, cpus } from 'node:os';
import { join, extname, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';
import { TIERS, grade, gradeNet, isGradableRenderer, CPU_BUDGET } from '../src/bench/gates.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist-bench');
const INTEL_ICD = '/usr/share/vulkan/icd.d/intel_icd.json';
const CHROME_ARGS = ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.wasm': 'application/wasm', '.json': 'application/json', '.png': 'image/png' };

function parseArgs(argv) {
  const a = { scenes: ['plaza', 'meadow'], paths: ['A', 'B', 'C'], tiers: ['raw', 'laptop', 'phone'], frames: 600, warmup: 120, build: true, selftest: false, out: null, seed: 1234, cdpThrottle: false, shadows: true };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i], v = argv[i + 1];
    if (k === '--scenes') { a.scenes = v.split(','); i++; }
    else if (k === '--paths') { a.paths = v.split(','); i++; }
    else if (k === '--tiers') { a.tiers = v.split(','); i++; }
    else if (k === '--frames') { a.frames = +v; i++; }
    else if (k === '--warmup') { a.warmup = +v; i++; }
    else if (k === '--seed') { a.seed = +v; i++; }
    else if (k === '--out') { a.out = v; i++; }
    else if (k === '--no-build') a.build = false;
    else if (k === '--selftest') a.selftest = true;
    else if (k === '--cdp-throttle') a.cdpThrottle = true; // informational only: such runs are never graded (gates.ts)
    else if (k === '--no-shadows') a.shadows = false; // diagnostic: path C without blob shadows
    else throw new Error(`unknown arg ${k}`);
  }
  return a;
}

export function buildBench() {
  const r = spawnSync(join(ROOT, 'node_modules/.bin/vite'), ['build', '--config', 'bench/vite.bench.config.ts', '--logLevel', 'warn'], { cwd: ROOT, stdio: 'inherit' });
  if (r.status !== 0) throw new Error('bench build failed');
}

export async function serve() {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, 'http://x');
    const p = join(DIST, decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
    if (!p.startsWith(DIST)) { res.writeHead(403).end(); return; }
    try {
      const body = await readFile(p);
      // Cross-origin isolation → 5 µs performance.now() resolution instead of 100 µs.
      res.writeHead(200, { 'Content-Type': MIME[extname(p)] ?? 'application/octet-stream', 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp', 'Cache-Control': 'no-store' });
      res.end(body);
    } catch { res.writeHead(404).end(); }
  });
  for (let port = 5390; port <= 5399; port++) {
    const ok = await new Promise((r) => { server.once('error', () => r(false)); server.listen(port, '127.0.0.1', () => r(true)); });
    if (ok) return { server, port };
  }
  throw new Error('no free port in 5390–5399');
}

/**
 * Pin this process (and so the Chrome it launches) to the P-cores. The i7-14700K
 * is hybrid: CPUs 0–15 are P-cores (5.5 GHz), 16–27 E-cores (4.3 GHz, lower IPC).
 * Unpinned, the same run measured up to ~2.8× apart depending on where the
 * renderer landed; the tier CPU factors (×2.5 / ×5) are defined against a P-core.
 */
export const P_CORES = '0-15';
export function pinToPCores() {
  const r = spawnSync('taskset', ['-a', '-cp', P_CORES, String(process.pid)], { encoding: 'utf8' });
  return r.status === 0 ? P_CORES : `unpinned (${(r.stderr || '').trim()})`;
}
let affinity = null;

export async function launch() {
  affinity ??= pinToPCores();
  return chromium.launch({ headless: true, env: { ...process.env, VK_ICD_FILENAMES: INTEL_ICD }, args: CHROME_ARGS });
}

export async function runOne(browser, port, { scene, path, tier, frames, warmup, seed, shadows = true, screenshot = null, hold = null, cdpThrottle = false }) {
  const t = TIERS[tier];
  const ctx = await browser.newContext({ viewport: { width: t.viewport.width, height: t.viewport.height }, deviceScaleFactor: t.viewport.dpr });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const rate = cdpThrottle ? t.cdpThrottle : 1;
  if (rate !== 1) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate });
  }
  const loadBefore = loadavg()[0];
  const qs = new URLSearchParams({ scene, path, frames: String(frames), warmup: String(warmup), seed: String(seed), shadows: shadows ? '1' : '0', ...(hold === null ? {} : { hold: String(hold) }) });
  await page.goto(`http://127.0.0.1:${port}/index.html?${qs}`, { waitUntil: 'load', timeout: 300000 });
  await page.waitForFunction(() => window.__benchResult || window.__benchError, null, { timeout: 1800000, polling: 1000 });
  const err = await page.evaluate(() => window.__benchError);
  if (err) { await ctx.close(); throw new Error(`${scene}/${path}/${tier}: ${err}\n${errors.join('\n')}`); }
  const result = await page.evaluate(() => window.__benchResult);
  if (screenshot) await page.screenshot({ path: screenshot });
  await ctx.close();
  result.tier = tier;
  result.cpuThrottle = rate;
  result.cpuScale = t.cpuScale;
  result.gpuScale = t.gpuScale;
  // Other sessions share this box; a busy machine inflates CPU numbers, so record the load.
  result.load = { before: loadBefore, after: loadavg()[0], cores: cpus().length };
  result.affinity = affinity;
  result.grade = grade(result, t);
  result.pageErrors = errors;
  return result;
}

const f2 = (v) => (Number.isFinite(v) ? v.toFixed(2) : 'n/a');

const verdictOf = (g) => !g ? '—' : !g.valid ? `INVALID (${g.reason})` : !g.graded ? 'info' : g.pass ? 'PASS' : `FAIL (${g.gates.filter((x) => !x.pass).map((x) => x.name).join(', ')})`;

export function summaryTable(results) {
  const rows = ['| scene | path | tier | CPU p95 ms measured → scaled (anim / upl+cull / submit, measured) | GPU p95 ms UHD 770 → scaled | draws p50 | tris p50 (visible) | LOD mix p50 | load | strict verdict | net of engine floor |', '|---|---|---|---|---|---|---|---|---|---|---|'];
  for (const r of results) {
    const s = r.summary;
    rows.push(`| ${r.scene} | ${r.path} | ${r.tier} | ${f2(s.cpuChar.p95)} → ${f2(s.cpuChar.p95 * r.cpuScale)} (${f2(s.anim.p95)} / ${f2(s.uploadCull.p95)} / ${f2(s.submit.p95)}) | ${f2(s.gpu.p95)} → ${f2(s.gpu.p95 * r.gpuScale)} | ${s.draws.p50} | ${Math.round(s.activeTris.p50)} (${Math.round(s.visibleTris.p50)}) | ${[s.lod0.p50, s.lod1.p50, s.lod2.p50, s.lod3.p50].join('/')} | ${f2(r.load?.before)} | ${verdictOf(r.grade)} | ${r.scene === 'empty' ? 'floor' : verdictOf(r.gradeNet)} |`);
  }
  return rows.join('\n');
}

export async function runSelfTest({ build = true } = {}) {
  if (build) buildBench();
  const { server, port } = await serve();
  const browser = await launch();
  try {
    const out = {};
    for (const path of ['A', 'B', 'C']) {
      const r = await runOne(browser, port, { scene: 'single', path, tier: 'raw', frames: 40, warmup: 20, seed: 1, shadows: false });
      out[path] = { drawsP50: r.summary.draws.p50, drawsMax: r.summary.draws.max, lod0: r.summary.lod0.p50, renderer: r.renderer, gradable: isGradableRenderer(r.renderer) };
    }
    return out;
  } finally {
    await browser.close();
    server.close();
  }
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.selftest) { console.log(JSON.stringify(await runSelfTest({ build: a.build }), null, 2)); return; }
  if (a.build || !existsSync(join(DIST, 'index.html'))) buildBench();
  const { server, port } = await serve();
  const browser = await launch();
  const day = new Date().toISOString().slice(0, 10);
  const outDir = a.out ?? join(ROOT, 'bench/results', day);
  await mkdir(outDir, { recursive: true });
  const results = [];
  try {
    for (const tier of a.tiers) {
      // Engine floor: scene.render() with zero characters at this tier (see gradeNet).
      const floor = await runOne(browser, port, { scene: 'empty', path: 'A', tier, frames: a.frames, warmup: a.warmup, seed: a.seed, cdpThrottle: a.cdpThrottle });
      results.push(floor);
      await writeFile(join(outDir, `empty-floor-${tier}.json`), JSON.stringify(floor, null, 2));
      console.log(`floor/${tier}: cpu p50 ${f2(floor.summary.cpuChar.p50)} p95 ${f2(floor.summary.cpuChar.p95)} ms, submit p50 ${f2(floor.summary.submit.p50)}, gpu p50 ${f2(floor.summary.gpu.p50)}`);
      for (const scene of a.scenes) {
        for (const path of a.paths) {
          const t0 = Date.now();
          const shot = tier === 'raw' ? join(outDir, `${scene}-${path}.png`) : null;
          const r = await runOne(browser, port, { scene, path, tier, frames: a.frames, warmup: a.warmup, seed: a.seed, screenshot: shot, cdpThrottle: a.cdpThrottle, shadows: a.shadows });
          r.floor = { cpuCharP50: floor.summary.cpuChar.p50, submitP50: floor.summary.submit.p50, renderWallP50: floor.summary.renderWall.p50, gpuP50: floor.summary.gpu.p50 };
          r.gradeNet = gradeNet(r, floor, TIERS[tier]);
          results.push(r);
          await writeFile(join(outDir, `${scene}-${path}-${tier}.json`), JSON.stringify(r, null, 2));
          const g = r.grade;
          console.log(`${scene}/${path}/${tier}: cpu p95 ${f2(r.summary.cpuChar.p95)}×${r.cpuScale} ms, gpu p95 ${f2(r.summary.gpu.p95)}×${r.gpuScale}, load ${f2(r.load.before)}, draws ${r.summary.draws.p50} → ${!g.valid ? 'INVALID ' + g.reason : !g.graded ? 'info' : g.pass ? 'PASS' : 'FAIL'} (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
          for (const x of g.gates) if (g.graded && g.valid) console.log(`    ${x.pass ? 'PASS' : 'FAIL'} ${x.name}: ${f2(x.value)} ≤ ${f2(x.limit)}${x.note ? '  (' + x.note + ')' : ''}`);
        }
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  const md = `# M0 crowd bench — ${day}\n\nRenderer: ${results[0]?.renderer}\n\nGates (PLAN §8.5): p95 values measured unthrottled on this box, then scaled — CPU × 2.5 (laptop) / × 5 (phone), GPU (UHD 770) × 2 / × 4. Limits: GPU ≤ ${f2(0.4 * 1000 / 30 * 0.7)} ms; CPU ≤ ${f2(CPU_BUDGET.total * 0.7)} ms total (anim ≤ ${f2(CPU_BUDGET.anim * 0.7)}, upload+cull ≤ ${f2(CPU_BUDGET.uploadCull * 0.7)}, submit ≤ ${f2(CPU_BUDGET.submit * 0.7)}) — all with 30 % headroom. Tier "raw" is informational. "load" = 1-min load average when the run started (${cpus().length} threads; other sessions share this machine).\n\n"strict" grades absolute p95 values. "net of engine floor" grades the same gates after subtracting the \`empty\` scene's p50 (scene.render() with zero characters: clear, camera, ground, instrumentation), which the world pays regardless of characters (\`gradeNet\` in src/bench/gates.ts).\n\n${summaryTable(results)}\n`;
  await writeFile(join(outDir, 'summary.md'), md);
  console.log('\n' + summaryTable(results));
  console.log(`\nwrote ${outDir}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
