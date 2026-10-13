import { defineConfig } from 'vite';

// `base` matches the claude-hub proxy prefix so asset URLs resolve correctly
// when the dev server is reverse-proxied at /low-poly-character-system/. SPEC §V.20.
// Havok ships as a WASM module; exclude it from pre-bundling so the .wasm
// asset resolves correctly.
export default defineConfig({
  base: '/low-poly-character-system/',
  optimizeDeps: { exclude: ['@babylonjs/havok'] },
  server: {
    host: '127.0.0.1',
    port: 5185,
    strictPort: true,
    // The hub forwards the original Host header, and Vite 7 rejects any host it
    // doesn't recognise with a 403 "Blocked request. This host is not allowed."
    // A loopback test passes while the tailnet URL 403s, so this is invisible
    // until you open the real link. The leading dot is a suffix wildcard for
    // any MagicDNS name — it keeps this machine's FQDN out of the repo.
    // SPEC §V66.
    allowedHosts: ['.ts.net', 'localhost'],
  },
  build: {
    rollupOptions: {
      // Agent shells on this box run with a hard RLIMIT_NOFILE of 512. Rollup's
      // default parallelism opens Babylon's thousands of modules at once and hits
      // EMFILE, which the resolver swallows and reports as a bogus "failed to
      // resolve import @griffel/react". Capping file ops keeps `vite build`
      // working under that limit and costs little elsewhere. SPEC §B1.
      maxParallelFileOps: 64,
    },
  },
});
