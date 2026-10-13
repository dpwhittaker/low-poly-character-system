import { defineConfig } from 'vite';

// Build config for the M0 crowd bench page only (bench/index.html → dist-bench/).
// Kept separate from the app's vite.config.ts so the bench never ships in the
// game build. maxParallelFileOps: same 512-fd agent-shell limit as SPEC V6.
export default defineConfig({
  root: 'bench',
  base: './',
  build: {
    outDir: '../dist-bench',
    emptyOutDir: true,
    chunkSizeWarningLimit: 10000,
    rollupOptions: { maxParallelFileOps: 64 },
  },
});
