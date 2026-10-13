# Crowd benchmarks behind PLAN.md §8.2 (2026-10-12)

These are throwaway research scripts. They are kept so the numbers in `PLAN.md` §8.2 can be
reproduced. They are not the M0 `Plaza-100` benchmark, which will live in `bench/` proper.
The paths are hard-coded to this machine.

- `web/index.html` measures real WebGL CPU cost: N characters × B bones × P parts, with
  optional merging, materials and animation rate.
  - Query parameters: `n`, `bones`, `parts`, `tris`, `merge=1`, `mat=std|pbr`, `umat=0`,
    `tn=0` (animate bones directly), `lod=4` (¼-rate staggered), `opt=freeze|aggr`.
  - Setup: serve this directory with `core` symlinked to
    `node_modules/@babylonjs/core`.
  - Run: `node run.cjs <port> 'n=100&merge=1' …`. It uses headless Chromium with ANGLE
    Vulkan, and Playwright is borrowed from another project's `node_modules`.
- `skelbench.mjs` measures AnimationGroup + `Skeleton.prepare` CPU under NullEngine.
  - Usage: `node skelbench.mjs <chars> <bones> bones|gltf <groups>`.
- `drawbench.mjs` measures Babylon's JS cost per mesh under NullEngine. GL calls are
  stubs there, so treat the result as a lower bound.
- `gpu-select.cjs` pins headless Chrome to one GPU through `VK_ICD_FILENAMES`. It prints
  the WebGL renderer, whether `EXT_disjoint_timer_query_webgl2` is available, and the
  measured slowdown under CDP `Emulation.setCPUThrottlingRate` 4. This is how SPEC §R14
  was verified: Intel UHD 770 ✓ with the timer query available, while the NVIDIA ICD fell
  back to SwiftShader.
