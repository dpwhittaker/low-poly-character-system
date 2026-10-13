const { chromium } = require('/home/david/projects/world-builder-opus-5/node_modules/playwright');
(async () => {
  const port = process.argv[2];
  for (const qs of process.argv.slice(3)) {
    const browser = await chromium.launch({ headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'] });
    const page = await browser.newPage();
    page.on('console', m => { if (m.type() === 'error') console.error('PAGE', m.text()); });
    try {
      await page.goto(`http://127.0.0.1:${port}/web/index.html?${qs}`, { timeout: 180000, waitUntil: 'commit' });
      await page.waitForFunction(() => window.__result, null, { timeout: 240000, polling: 1000 });
      console.log(qs, JSON.stringify(await page.evaluate(() => window.__result)).replace(/"renderer":"[^"]*",/, ''));
    } catch (e) { console.log(qs, 'ERR', e.message.split('\n')[0]); }
    await browser.close();
  }
})();
