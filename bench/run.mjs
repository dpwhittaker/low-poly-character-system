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
import { join, extname, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';
import { TIERS, grade, isGradableRenderer } from '../src/bench/gates.ts';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'dist-bench');
const INTEL_ICD = '/usr/share/vulkan/icd.d/intel_icd.json';
const CHROME_ARGS = ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.wasm': 'application/wasm', '.json': 'application/json', '.png': 'image/png' };

function parseArgs(argv) {
  const a = { scenes: ['plaza', 'meadow'], paths: ['A', 'B', 'C'], tiers: ['raw', 'laptop', 'phone'], frames: 600, warmup: 120, build: true, selftest: false, out: null, seed: 1234 };
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

export async function launch() {
  return chromium.launch({ headless: true, env: { ...process.env, VK_ICD_FILENAMES: INTEL_ICD }, args: CHROME_ARGS });
}

export async function runOne(browser, port, { scene, path, tier, frames, warmup, seed, shadows = true, screenshot = null }) {
  const t = TIERS[tier];
  const ctx = await browser.newContext({ viewport: { width: t.viewport.width, height: t.viewport.height }, deviceScaleFactor: t.viewport.dpr });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: t.cpuThrottle });
  const qs = new URLSearchParams({ scene, path, frames: String(frames), warmup: String(warmup), seed: String(seed), shadows: shadows ? '1' : '0' });
  await page.goto(`http://127.0.0.1:${port}/index.html?${qs}`, { waitUntil: 'load', timeout: 300000 });
  await page.waitForFunction(() => window.__benchResult || window.__benchError, null, { timeout: 1800000, polling: 1000 });
  const err = await page.evaluate(() => window.__benchError);
  if (err) { await ctx.close(); throw new Error(`${scene}/${path}/${tier}: ${err}\n${errors.join('\n')}`); }
  const result = await page.evaluate(() => window.__benchResult);
  if (screenshot) await page.screenshot({ path: screenshot });
  await ctx.close();
  result.tier = tier;
  result.cpuThrottle = t.cpuThrottle;
  result.gpuScale = t.gpuScale;
  result.grade = grade(result, t);
  result.pageErrors = errors;
  return result;
}

const f2 = (v) => (Number.isFinite(v) ? v.toFixed(2) : 'n/a');

export function summaryTable(results) {
  const rows = ['| scene | path | tier | CPU p95 ms (anim / upl+cull / submit) | GPU p95 ms (UHD 770 → scaled) | draws p50 | tris p50 (visible) | LOD mix p50 | verdict |', '|---|---|---|---|---|---|---|---|---|'];
  for (const r of results) {
    const s = r.summary, g = r.grade;
    const verdict = !g.valid ? `INVALID (${g.reason})` : !g.graded ? 'info' : g.pass ? 'PASS' : `FAIL (${g.gates.filter((x) => !x.pass).map((x) => x.name).join(', ')})`;
    rows.push(`| ${r.scene} | ${r.path} | ${r.tier} | ${f2(s.cpuChar.p95)} (${f2(s.anim.p95)} / ${f2(s.uploadCull.p95)} / ${f2(s.submit.p95)}) | ${f2(s.gpu.p95)} → ${f2(s.gpu.p95 * r.gpuScale)} | ${s.draws.p50} | ${Math.round(s.activeTris.p50)} (${Math.round(s.visibleTris.p50)}) | ${[s.lod0.p50, s.lod1.p50, s.lod2.p50, s.lod3.p50].join('/')} | ${verdict} |`);
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
      for (const scene of a.scenes) {
        for (const path of a.paths) {
          const t0 = Date.now();
          const shot = tier === 'raw' ? join(outDir, `${scene}-${path}.png`) : null;
          const r = await runOne(browser, port, { scene, path, tier, frames: a.frames, warmup: a.warmup, seed: a.seed, screenshot: shot });
          results.push(r);
          await writeFile(join(outDir, `${scene}-${path}-${tier}.json`), JSON.stringify(r, null, 2));
          const g = r.grade;
          console.log(`${scene}/${path}/${tier}: cpu p95 ${f2(r.summary.cpuChar.p95)} ms, gpu p95 ${f2(r.summary.gpu.p95)}×${r.gpuScale}, draws ${r.summary.draws.p50} → ${!g.valid ? 'INVALID ' + g.reason : !g.graded ? 'info' : g.pass ? 'PASS' : 'FAIL'} (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
          for (const x of g.gates) if (g.graded && g.valid) console.log(`    ${x.pass ? 'PASS' : 'FAIL'} ${x.name}: ${f2(x.value)} ≤ ${f2(x.limit)}${x.note ? '  (' + x.note + ')' : ''}`);
        }
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  const md = `# M0 crowd bench — ${day}\n\nRenderer: ${results[0]?.renderer}\n\nGates (PLAN §8.5): p95 values; GPU = UHD 770 ms × tier scale ≤ ${f2(0.4 * 1000 / 30 * 0.7)} ms; CPU ≤ ${f2(7 * 0.7)} ms total (anim ≤ ${f2(3 * 0.7)}, upload+cull ≤ ${f2(2 * 0.7)}, submit ≤ ${f2(2 * 0.7)}) under the tier's CPU throttle — all with 30 % headroom. Tier "raw" is informational.\n\n${summaryTable(results)}\n`;
  await writeFile(join(outDir, 'summary.md'), md);
  console.log('\n' + summaryTable(results));
  console.log(`\nwrote ${outDir}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
