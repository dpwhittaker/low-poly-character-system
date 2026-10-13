# SPEC

Durable memory for this project — reload it at the start of every session.
Format, encoding & the maintenance protocol (how a new requirement retires an
old one): `~/projects/claude-hub/SDD.md`.

## §G GOAL

modular low-poly character system for web 3D games (sandbox MMO life-sim): body+face sliders, 100s of mix-and-match items × ≤3 recolor channels each, ≤100 unique animated chars on screen @ ≥30 fps on budget laptop / midrange tablet. reasoning, research, sources: `PLAN.md`.

## §C CONSTRAINTS

- Vite 7 + Babylon.js 8 + Havok physics (WASM) + TypeScript 5.9. inspector on the `i` key.
- dev server = `vite@low-poly-character-system.service` (systemd, `Restart=always`), owns port `5185`. ⊥ `npm run dev` by hand — 2nd process → `EADDRINUSE` or a stale instance the proxy hits instead.
- reverse-proxied at `/low-poly-character-system/` by claude-hub. `base` in `vite.config.ts` ! = `.project-meta.json` `proxyPrefix`.
- `server.allowedHosts` ! ⊇ `.ts.net`. hub proxies `changeOrigin: false` ∴ upstream sees CLIENT `Host`; Vite 7 403s unknown hosts.
- `strictPort: true` — port comes from the sentinel, ⊥ drift to a free one silently.
- Babylon `^8.0.0` (installed 8.56.2); 9.x upgrade decided in M0 (§T.4) before code depends on it. loader: EXT_meshopt ✓ KHR_meshopt ✗.
- WebGL2 = baseline; WebGPU optional extra, ⊥ required.
- perf floor: `Plaza-100` (100 chars) ≥30 fps on Intel UHD 620-class laptop & Mali-G57 / Adreno 6xx / A13-class tablet; char system ≤40% frame. pass = REAL device. ⊥ SwiftShader or RTX number as a pass.
- assets authored in Blender (version pinned here once chosen, §T.4); TS only assembles. ⊥ procedural ring-loft / inflated humans or garments (PLAN §2: failed twice). ⊥ AI-3D meshes as body/garment runtime geometry.
- shipped assets ! CC0 | MIT | own work. ⊥ Hunyuan3D output (EU/UK/KR excluded), ⊥ Quaternius (no-redistribution licence since 2026-08-28), ⊥ Mixamo, ⊥ non-commercial mocap (LAFAN1, AMASS, Bandai Namco), ⊥ nvdiffrast-baked textures (research-only).
- one body topology (unisex), one skeleton, one character material; near tier = 1 draw/char. 0 morph targets at runtime (baked at assembly).
- ⊥ runtime geometric heuristics: no push-out, no auto-cut, no inflation. fit, hiding & weights come from build-time data.
- recolor: R=primary G=accent B=detail (user's scheme), independent per item.
- carried user rules: covered body ⊥ drawn, cuts clean (authored bands); shoes worn OVER foot, foot kept; hands can grip (finger bones).
- quality gate: ⊥ catalog / UI / scale work before user signs off rendered 3D body + faces + garments in motion (M1, §T.5).
- one lighting definition shared by game, creator & every screenshot harness.

## §I INTERFACES

- url: `GET /low-poly-character-system/` → the app, through claude-hub
- `README.md` H1 → the project's title, ¶1 → its one-sentence description

## §R RESEARCH

id|topic|finding|src
---|---|---|---
R1|crowd CPU|100 merged chars × 30 bones, stock AnimationGroup = 3.3 ms CPU/frame on i7-14700K (6 unmerged parts: 5.9). est 8–10 ms budget laptop, 17–23 ms low tablet ∴ custom sampler + tiering|`bench/research-2026-10-12/`
R2|MergeMeshes|`multiMultiMaterials` still 1 draw/submesh; merged mesh gets no skeleton (set it)|`core/Meshes/mesh.js:4083-4230`; forum.babylonjs.com/t/45784
R3|morph cost|texture mode ≈1.9 MB/char (3k verts × 20 targets); influencer-count change → shader recompile ∴ bake at assembly|`core/Morph/morphTargetManager.js`
R4|VAT|`VertexAnimationBaker` bakes bone matrices → proportions baked in, no blend, no frame interp ∴ ⊥ for unique players|`core/BakedVertexAnimation/vertexAnimationBaker.js`
R5|freeze|`scene.freezeActiveMeshes()` stops `skeleton.prepare()` → skinned chars freeze|`core/scene.js:3771-3800`
R6|auto LOD|`Mesh.simplify` drops bone weights ∴ offline LODs (meshoptimizer keeps vertex buffers)|`core/Meshes/meshSimplification.js:442-504`
R7|DQS|Babylon has no dual-quaternion skinning ∴ LBS + twist bones|forum.babylonjs.com/t/dual-quaternion-skinning/10595
R8|device floors|WebGL2 99% Android / 98.4% iOS; `MAX_VERTEX_UNIFORM_VECTORS` only ≥256 on Android (~50 bones uniform mode) ∴ bone textures|web3dsurvey.com
R9|MakeHuman|MPFB assets (base mesh, targets, rigs, MHCLO) CC0 since 2020; code GPL; `game_engine` rig; mpfb-mcp exists|github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md
R10|anim sources|Mesh2Motion (CC0 anims), KayKit (CC0, 133 clips), CMU (free incl. commercial, no fingers)|github.com/Mesh2Motion/mesh2motion-app; mocap.cs.cmu.edu
R11|Blender local|apt 5.0.1 headless ✓: bpy, heat weights, shape keys, glTF skin+morph+anim, Workbench/EEVEE/Cycles-CUDA (no OptiX/OIDN). Node `NullEngine` loads the GLB|PLAN §3.2
R12|Blender MCP|Blender Lab official v1.0.3: headless `-b --command blender_mcp`, needs ≥5.1, no telemetry, no auth (loopback only). ahujasid: GUI/Xvfb only, telemetry default-on, CVE-2026-10688|projects.blender.org/lab/blender_mcp
R13|clipping prior art|Roblox equip-time cage fit + post-fit ray HSR; UMA raycast MeshHideAsset; Sims robe-vs-skintight DMAP; MH1.2 local-frame offsets; CC AHMP downward-only hiding; Cyberpunk inward squish|PLAN §7.2, §13

## §V INVARIANTS

- V1: `base` in `vite.config.ts` = `/low-poly-character-system/` = sentinel `proxyPrefix`. any ≠ → assets 404 through the proxy while `127.0.0.1:5185` looks fine.
- V2: `server.allowedHosts` ⊇ `['.ts.net', 'localhost']`. ⊥ a concrete FQDN (commits the machine's tailnet name). loopback passes while the tailnet URL 403s ∴ test through the REAL url.
- V3: the dev server is `vite@low-poly-character-system.service`'s alone. ⊥ 2nd process on `5185`.
- V4: `README.md` H1/¶1 = the project's title/description. ⊥ let them drift from §G.
- V5: `optimizeDeps.exclude` ⊇ `['@babylonjs/havok']`. Havok is a WASM module; pre-bundling it breaks `.wasm` asset resolution.

## §T TASKS

id|status|task|cites
---|---|---|---
T1|x|agree §G w/ user; rewrite §G + `README.md` H1/¶1 to match|V4
T2|.|first feature. add §I rows for surface it adds, §V for rules it must hold|-
T3|x|research + plan → `PLAN.md` (tool discovery, perf budgets, modularity, clipping); seeds §G §C §R|-
T4|.|M0: style frames (2–3 looks, shared lighting rig); `Plaza-100` placeholder bench on user's real devices; pin Blender 5.2.2 + Blender MCP (needs user OK); Babylon 9 decision|PLAN §11
T5|.|M1: bake-off PLAN §3.4 P1–P8 + base body; user signs off rendered 3D body/faces/garments in motion|PLAN §3.4
T6|.|M2: worker assembler (morph bake → skeleton fit → item fit → hide → merge), shared material, recolor, minimal creator|PLAN §4.3
T7|.|M3: garment build pipeline + clip-test harness; every gate ships w/ a known-bad fixture|PLAN §7.5
T8|.|M4: custom animation sampler + shared bone texture, layers, D10 body-shape corrections|PLAN §8.4
T9|.|M5: crowd perf — LODs, far-tier batching, blob shadows, real-device gate|PLAN §8
T10|.|M6: content scale-up → ~120 meshes / 300+ catalog entries|PLAN §9
T11|.|M7: game-facing API (`createCharacter(descriptor)`), streaming, cache, dispose leak test|-

## §B BUGS

id|date|cause|fix
---|---|---|---
B1|2026-10-12|local `npm run build` → rollup can't resolve `@griffel/react` (inspector → fluentui) though file exists; CI's clean `npm ci` build passes ∴ local `node_modules` drifted from lockfile. fix pending: `npm ci` + restart unit|-
B2|2026-10-12|Pages deploy fails @ `actions/configure-pages` 404: Pages not enabled in repo settings (Source: GitHub Actions). build step itself passes|-
