# SPEC

Durable memory for this project — reload it at the start of every session.
Format, encoding & the maintenance protocol (how a new requirement retires an
old one): `~/projects/claude-hub/SDD.md`.

## §G GOAL

modular low-poly character system for web 3D games (sandbox MMO life-sim, audience: teen girls building families): every age infant→elder, body+face sliders, children inherit parents' looks, 100s of mix-and-match items × ≤3 recolor channels each, ≤100 unique animated chars on screen @ ≥30 fps on budget laptop / midrange tablet. reasoning, research, sources: `PLAN.md`.

## §C CONSTRAINTS

- Vite 7 + Babylon.js 9 (`^9.30.0`) + Havok `^1.3.14` (WASM) + TypeScript 5.9. inspector on the `i` key (lazy chunk).
- dev server = `vite@low-poly-character-system.service` (systemd, `Restart=always`), owns port `5185`. ⊥ `npm run dev` by hand — 2nd process → `EADDRINUSE` or a stale instance the proxy hits instead.
- reverse-proxied at `/low-poly-character-system/` by claude-hub. `base` in `vite.config.ts` ! = `.project-meta.json` `proxyPrefix`.
- `server.allowedHosts` ! ⊇ `.ts.net`. hub proxies `changeOrigin: false` ∴ upstream sees CLIENT `Host`; Vite 7 403s unknown hosts.
- `strictPort: true` — port comes from the sentinel, ⊥ drift to a free one silently.
- Babylon 8 → 9 upgraded 2026-10-12 (user OK) before any code depended on 8. loader: EXT_meshopt ✓; KHR_meshopt ✗ as of 8.56, recheck on 9.
- agent shells: hard `RLIMIT_NOFILE` = 512 (`ulimit -Hn`), so tools that open files in parallel must cap it (see V6). systemd units & CI have higher limits.
- WebGL2 = baseline; WebGPU optional extra, ⊥ required.
- perf floor (revised 2026-10-12): `Plaza-100` + `Meadow-100` (100 chars) ≥30 fps on Intel UHD 620-class laptop & Mali-G57 / Adreno 6xx / A13-class tablet **& midrange phone** (phone-first); char system ≤40% frame. pass = scaled gate measured ON THIS MACHINE (user decision): GPU ms on Intel UHD 770 iGPU (`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/intel_icd.json`, ANGLE-Vulkan, `EXT_disjoint_timer_query_webgl2`) ×2 laptop / ×4 tablet-phone; CPU via CDP `Emulation.setCPUThrottlingRate` 2.5× laptop / 5× tablet-phone-Chromebook; ≥30% headroom. ⊥ the previous 'pass = real device' rule — no external calibration device (user 2026-10-12). ⊥ SwiftShader or RTX number as a pass.
- assets authored in Blender (version pinned here once chosen, §T.4); TS only assembles. ⊥ procedural ring-loft / inflated humans or garments (PLAN §2: failed twice). ⊥ AI-3D meshes as body/garment runtime geometry.
- shipped assets ! CC0 | MIT | own work. ⊥ Hunyuan3D output (EU/UK/KR excluded), ⊥ Quaternius (no-redistribution licence since 2026-08-28), ⊥ Mixamo, ⊥ non-commercial mocap (LAFAN1, AMASS, Bandai Namco), ⊥ nvdiffrast-baked textures (research-only).
- one body topology (unisex), one skeleton, one character material; near tier = 1 draw/char. 0 morph targets at runtime (baked at assembly).
- ⊥ runtime geometric heuristics: no push-out, no auto-cut, no inflation. fit, hiding & weights come from build-time data.
- recolor: R=primary G=accent B=detail (user's scheme), independent per item.
- user rules: covered body ⊥ drawn, cuts clean (authored bands); hands can grip (finger bones). feet (revised 2026-10-12): foot bands hidden inside shoes when measured covered ("clip feet when possible"); shoe fails to build → foot stays. ⊥ World Forge rule "foot always kept inside shoes".
- all assets agent-authored (user 2026-10-12); no human artist pass ∴ M1 sign-off + reference data carry quality.
- quality gate: ⊥ catalog / UI / scale work before user signs off rendered 3D body + faces + garments in motion (M1, §T.5).
- one lighting definition shared by game, creator & every screenshot harness.
- art target = 16-char faceted low-poly reference `~/projects/character-generator/public/low-poly-character-reference.png` (approved 2026-09-06, re-confirmed 2026-10-12). 2D AI image ∴ 3D must be proven against it, ⊥ assumed.
- ages: infant 0–1 · toddler 1–3 · child 4–12 · teen→elder 13–90 (teen–elder share one garment catalog). one topology + one skeleton across ages = goal, proven in M1 P1 (child + toddler from adult topology); fallback small frame for infant/toddler w/ same bone names + face sliders.
- identity sliders stored as deviation from age-mean shape → aging keeps identity; child = lerp(parents) + seeded noise.
- content rules (teen audience): non-removable base layer added by assembler; body sliders capped to non-sexualized ranges per age group; child/toddler/infant: no sex-dimorphism body sliders; ∀ item & animation carry age eligibility + content tags; one descriptor validator shared client+server. ⊥ revealing/adult-themed catalog items. ⊥ PII / photo-to-avatar.
- user devices: Ryzen 7 mini PC (Radeon 780M) + Galaxy Z Fold 7 (Adreno 830) = optional sanity checks (touch, foldable resize), ⊥ the gate.
- UI: phone-portrait first (§4.5 PLAN); tablet/desktop = side panel; foldable cover↔inner live resize. mobile budget: char system ≤64 MB GPU, ≤150 MB JS heap @100 chars; phones capped 30 fps.
- infants: few sliders (face mostly inherited; skin/hair/eye color), clothes = onesie, diaper (base layer), baby versions of adult clothes (auto-fit drafts → review).
- camera: close city scenes → open countryside ∴ bench scenes `Plaza-100` (city, dense near) + `Meadow-100` (countryside, far tiers); LOD3 + draw-distance fade.
- Blender: apt 5.0.1 (`/usr/bin/blender`) for quick batch; pinned 5.2.2 LTS `~/opt/blender-5.2.2-linux-x64/blender` for the pipeline + MCP. MCP server runs under nohup (user OK 2026-10-12, ⊥ systemd needed) → ⊥ survives reboot; `tools/blender-mcp.sh start`.

## §I INTERFACES

- url: `GET /low-poly-character-system/` → the app, through claude-hub
- `README.md` H1 → the project's title, ¶1 → its one-sentence description
- MCP: `.mcp.json` server `blender` = `uvx --from git+https://projects.blender.org/lab/blender_mcp.git@v1.0.3#subdirectory=mcp blender-mcp`, env `BLENDER_MCP_HOST=127.0.0.1` `BLENDER_MCP_PORT=9876` `BLENDER_PATH`. backend: headless Blender 5.2.2 `--command blender_mcp` on `127.0.0.1:9876` (no auth ∴ loopback only). raw socket: null-terminated JSON `{"type":"execute","code":…,"strict_json":true}`.
- `tools/blender-mcp.sh start|stop|status|restart` → manages that backend; log `~/.local/state/blender-mcp/blender-mcp.log`.

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
R14|perf rig|headless Chrome can be pinned to Intel UHD 770 via `VK_ICD_FILENAMES=…/intel_icd.json` + `--use-angle=vulkan`; `EXT_disjoint_timer_query_webgl2` ✓. NVIDIA ICD → SwiftShader fallback (pending driver reboot?). CDP throttle 4 → 3.4–4.2× measured|PLAN §8.1 §8.5

## §V INVARIANTS

- V1: `base` in `vite.config.ts` = `/low-poly-character-system/` = sentinel `proxyPrefix`. any ≠ → assets 404 through the proxy while `127.0.0.1:5185` looks fine.
- V2: `server.allowedHosts` ⊇ `['.ts.net', 'localhost']`. ⊥ a concrete FQDN (commits the machine's tailnet name). loopback passes while the tailnet URL 403s ∴ test through the REAL url.
- V3: the dev server is `vite@low-poly-character-system.service`'s alone. ⊥ 2nd process on `5185`.
- V4: `README.md` H1/¶1 = the project's title/description. ⊥ let them drift from §G.
- V5: `optimizeDeps.exclude` ⊇ `['@babylonjs/havok']`. Havok is a WASM module; pre-bundling it breaks `.wasm` asset resolution.
- V6: `build.rollupOptions.maxParallelFileOps` ≤ 64 in `vite.config.ts`. agent shell fd limit 512 → Rollup EMFILE, which the resolver swallows → bogus "failed to resolve import". ⊥ "fix" by guarding/removing imports (B1). proof: `npm run build` passes from an agent shell.

## §T TASKS

id|status|task|cites
---|---|---|---
T1|x|agree §G w/ user; rewrite §G + `README.md` H1/¶1 to match|V4
T2|.|first feature. add §I rows for surface it adds, §V for rules it must hold|-
T3|x|research + plan → `PLAN.md` (tool discovery, perf budgets, modularity, clipping); seeds §G §C §R|-
T4|~|M0 (Babylon 9 ✓, Blender 5.2.2 + MCP ✓ 2026-10-12): style frames (2–3 looks, shared lighting rig); `Plaza-100` placeholder bench on user's real devices; pin Blender 5.2.2 + Blender MCP (needs user OK); Babylon 9 decision|PLAN §11
T5|.|M1: bake-off PLAN §3.4 P1–P8 + base body; user signs off rendered 3D body/faces/garments in motion|PLAN §3.4
T6|.|M2: worker assembler (morph bake → skeleton fit → item fit → hide → merge), shared material, recolor, minimal creator|PLAN §4.3
T7|.|M3: garment build pipeline + clip-test harness; every gate ships w/ a known-bad fixture|PLAN §7.5
T8|.|M4: custom animation sampler + shared bone texture, layers, D10 body-shape corrections|PLAN §8.4
T9|.|M5: crowd perf — LODs, far-tier batching, blob shadows, real-device gate|PLAN §8
T10|.|M6: content scale-up → ~120 meshes / 300+ catalog entries|PLAN §9
T11|.|M7: game-facing API (`createCharacter(descriptor)`), streaming, cache, dispose leak test|-
T12|x|fold user answers (ages/families, teen content rules, devices + scaled gates, camera range) into PLAN v1.1 + §G §C|-
T13|.|M1 add-on: P1 builds child + toddler from the adult topology; decide one-topology vs small frame|PLAN §5.6
T14|.|M2 add-on: shared descriptor validator (§5.7 rules) + family inheritance (lerp + seeded noise, OKLab skin)|PLAN §5.6 §5.7
T15|.|M0 add-on: `Meadow-100` countryside bench + scaled-gate harness on this machine (UHD 770 iGPU GPU timer × tier ratio, CDP CPU throttling, ≥30% headroom)|PLAN §8.5
T16|x|fold answers round 2 (780M, infants, phone-first, measure-on-this-machine) into PLAN v1.2 + §C; revises perf-floor §C rule|-
T17|.|M2 add-on: phone-first creator UI (bottom sheet, foldable resize, recolored thumbnails)|PLAN §4.5
T18|x|answers round 3: agent-authored assets; clip feet when measured covered (revises §C feet rule; foot bands added to cut lines)|PLAN §6.2 §7.3
T19|~|M0.1 style frames: S1 all-vertex-color / S2 geometry + painted face / S3 texture detail × flat/smooth; one test character; shared lighting rig `src/render/lighting.ts`; contact sheet + live page `?style=`; user picks|PLAN §5.5
T20|~|M0.2 crowd bench (worktree `m0-bench`): placeholder chars @ §8.3 budgets; Babylon-native vs custom sampler + shared bone texture + tiering; `Plaza-100` + `Meadow-100`; scaled gates on UHD 770 + CDP throttle|PLAN §8.4 §8.5

## §B BUGS

id|date|cause|fix
---|---|---|---
B1|2026-10-12|local `npm run build` → "failed to resolve `@griffel/react`". first blamed on node_modules drift (wrong). real cause: agent shell hard fd limit 512 → Rollup EMFILE swallowed by resolver (surfaced as EMFILE once the import moved). CI passes (higher limit)|V6
B2|2026-10-12|Pages deploy fails @ `actions/configure-pages` 404: Pages not enabled in repo settings (Source: GitHub Actions). build step itself passes|-
