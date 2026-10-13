const { chromium } = require('/home/david/projects/world-builder-opus-5/node_modules/playwright');
(async () => {
  for (const icd of ['intel_icd.json', 'nvidia_icd.json']) {
    const browser = await chromium.launch({ headless: true, env: { ...process.env, VK_ICD_FILENAMES: '/usr/share/vulkan/icd.d/' + icd },
      args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan', '--enable-features=Vulkan'] });
    const page = await browser.newPage();
    await page.setContent('<canvas id=c></canvas>');
    const probe = () => page.evaluate(() => {
      const gl = document.getElementById('c').getContext('webgl2');
      const d = gl.getExtension('WEBGL_debug_renderer_info');
      const t0 = performance.now(); let x = 0; for (let i = 0; i < 2e7; i++) x += Math.sqrt(i); const ms = performance.now() - t0;
      return { renderer: d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : '?', timerQuery: !!gl.getExtension('EXT_disjoint_timer_query_webgl2'), loopMs: +ms.toFixed(1), x: x > 0 };
    });
    const base = await probe();
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    const thr = await probe();
    console.log(icd, JSON.stringify({ renderer: base.renderer, timerQuery: base.timerQuery, loopMs: base.loopMs, loopMsAt4x: thr.loopMs, ratio: +(thr.loopMs / base.loopMs).toFixed(2) }));
    await browser.close();
  }
})();
