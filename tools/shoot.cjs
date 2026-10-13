// Screenshot pages of the running dev server in headless Chrome pinned to the Intel UHD
// 770 iGPU (the M0 gate device, SPEC §R14). Waits for `window.__ready`, then a settle delay.
//   node tools/shoot.cjs <out.png> '<query>' [<out2.png> '<query2>' ...] [--size=WxH] [--dpr=N]
const { chromium } = require('/home/david/projects/world-builder-opus-5/node_modules/playwright');
(async () => {
  const args = process.argv.slice(2);
  const size = (args.find((a) => a.startsWith('--size=')) || '--size=900x1200').slice(7).split('x').map(Number);
  const dpr = Number((args.find((a) => a.startsWith('--dpr=')) || '--dpr=1').slice(6));
  const jobs = args.filter((a) => !a.startsWith('--'));
  const browser = await chromium.launch({
    headless: true,
    env: { ...process.env, VK_ICD_FILENAMES: '/usr/share/vulkan/icd.d/intel_icd.json' },
    args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'],
  });
  const page = await browser.newPage({ viewport: { width: size[0], height: size[1] }, deviceScaleFactor: dpr });
  const errs = [];
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  for (let i = 0; i + 1 < jobs.length; i += 2) {
    await page.goto('http://127.0.0.1:5185/low-poly-character-system/?' + jobs[i + 1], { waitUntil: 'load', timeout: 90000 });
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 90000 });
    await page.waitForTimeout(700);
    await page.screenshot({ path: jobs[i] });
  }
  console.log(JSON.stringify({ shots: jobs.length / 2, errors: errs.slice(0, 8) }));
  await browser.close();
})();
