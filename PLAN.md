# PLAN — Low-Poly Character System

Research and plan for a customizable character system for web 3D games
(Babylon.js 9 + Havok + Vite + TypeScript), built for a sandbox MMO life-sim.

> **Status:** plan v1.5, 2026-10-13. M0 is built: path C passes every scaled crowd gate
> (§8.2b), and the user picked style **S1 with smooth normals** (§5.5). **M1 is built and
> awaits the user's sign-off** (§11): the bake-off results are in `docs/bakeoff/M1.md`. The user's answers are folded in (§12): the audience is
> teen girls building families, so every age is in scope, including infants with a small
> option set; the UI is phone-first; the camera ranges from close city scenes to open
> countryside; performance gates are measured on this machine (its UHD 770 iGPU, and its
> CPU unthrottled × a tier factor). Babylon is upgraded to 9.30, and
> Blender 5.2.2 + the official MCP server are installed and verified. Production character
> code starts in M1. This file holds the reasoning,
> research and sources; `SPEC.md` holds the decisions in compressed form and is the file
> that gets updated as work proceeds. Where the two disagree, `SPEC.md` wins and this file
> is stale.

---

## 0. TL;DR — the decisions this plan commits to

1. **Prove quality in 3D before building anything at scale.** No catalog, no UI polish and
   no crowd work until the user signs off on a *rendered 3D* base body, three faces and
   three garments in motion (gate **M1**). Every earlier attempt in this workspace skipped
   this step, and that is where they failed (§2).
2. **Author assets in Blender; TypeScript only assembles them.** Blender runs headless
   here with full `bpy`: the apt 5.0.1, plus a pinned 5.2.2 LTS driven through the official
   MCP server, both verified (§3.2, §3.5). Body *shape* comes from real anatomical
   reference data projected onto a low-poly topology designed for the job. Shape does not
   come from parametric ring lofts (that approach failed twice, §2).
3. **One base mesh, one skeleton, one material, one draw call per character.** Every
   garment is authored once, on the neutral body, and fits every body.
4. **Sliders are morph targets plus a joint regressor, baked on the CPU when a character is
   assembled.** The skeleton is re-fitted to the morphed body. Animations are
   rotation-only, so they play on any proportions. **Zero morph targets at runtime.**
5. **All ages, one system, families by inheritance.** Infant → elder share one topology
   and one skeleton where the M1 probe proves it can (§5.6). A child's sliders are blended
   from the parents' plus variation, so families resemble each other, and aging a
   character keeps its identity. The audience is teen girls, so content rules are built
   into the data, not left to moderation (§5.7).
6. **Garments follow the body by surface binding** computed at build time.
   - Offsets live in the surface's local frame. Skirts and robes bind to a leg-bridged
     "robe proxy".
   - Skin weights are *inherited* from the surface underneath, never painted separately.
   - Each layer must stay inside a fixed offset shell.
   - Body hiding under clothes uses **authored cut-line bands whose hiding is measured,
     not declared**.
7. **Recolor** uses greyscale shading times an R/G/B mask: **R = primary, G = accent,
   B = detail**, the user's scheme from earlier projects. A per-character palette is
   indexed by slot. There are no per-item textures.
8. **Crowd budget, tiered by distance.** Measured on this box, 100 characters on
   Babylon's stock animation path would cost roughly 8–23 ms of CPU on target devices,
   which is too much.
   - **Animation:** our own sampler writes every character's bones into one shared
     texture. Update rate drops with distance and updates are staggered.
   - **Mesh:** the far tier is batched into a few draw calls. Skeleton and mesh LODs
     follow a fixed budget (§8.3).
   - **Shadows:** blob shadows for the crowd.
9. **Size.** The character core is ≤ 3 MB compressed. Items average ≤ 25 KB and stream on
   demand. An appearance descriptor is ≈ 150 bytes.
10. **Clipping: defense in depth** (§7). It has ten structural defenses plus automated
   stress-pose × body-extreme × outfit tests. Each test must be *proven able to fail*, and
   a human visual gate sits on top.
11. **Thin vertical slice first.** One body, a handful of items and the full pipeline end
    to end, measured on this machine's budget-class iGPU and unthrottled CPU × tier factor (§8.5),
    before scaling content. **The UI is phone-first** (§4.5).

---

## 1. Goals and measurable success criteria

| # | Requirement | Measured by | Target |
|---|---|---|---|
| G1 | Deep body + face customization via sliders | slider count; each slider visibly changes silhouette/face at 3 m; all combinations valid | ≥ 30 body + ≥ 30 face sliders plus macro sliders (sex, weight, muscle, age, height); every combination passes §7 tests |
| G2 | Hundreds of clothing pieces + accessories, mix-and-match | catalog entries; compatibility | ≥ 300 catalog entries from ~120 meshes (variants are data, §9); any item combination either fits or is auto-resolved by declared rules |
| G3 | Recolor, up to 3 colors per item | channels per item | 3 independent channels per item (R primary, G accent, B detail), plus skin, hair and eye colors |
| G4 | 100 unique characters on screen: budget laptops, midrange tablets **and phones** (phone-first) | `Plaza-100` (city) and `Meadow-100` (countryside) benchmark scenes, fixed camera paths | ≥ 30 fps on an Intel UHD 620-class laptop and a Mali-G57 / Adreno 6xx / Apple A13-class tablet or midrange phone; ≥ 60 fps desktop. Character system ≤ 40 % of frame time. Measured on this machine's UHD 770 iGPU and unthrottled CPU, scaled to those tiers (§8.5) |
| G5 | Small game size | bytes over the wire | core (body, morphs, skeleton, animations, shaders) ≤ 3 MB compressed; average item ≤ 25 KB incl. LODs |
| G6 | Quality bar | user sign-off on rendered 3D, every milestone | approved style frame; approved contact sheets; zero visible poke-through in the stress-pose suite |
| G7 | MMO-ready | descriptor size; assembly time | descriptor ≤ 200 B; assembly ≤ 30 ms per character in a Web Worker on a budget laptop; results cached |
| G8 | Families: every age, children that resemble their parents | age groups supported; inheritance | infant, toddler, child, teen, adult, elder; a child descriptor derived from two parents; aging keeps identity (§5.6) |
| G9 | Safe for a teen audience | rules enforced on descriptors | bounded body sliders, a non-removable base layer, age-eligibility on every item and animation, validated server-side (§5.7) |

---

## 2. Lessons from the earlier attempts in this workspace

The user flagged that the earlier character projects, built with older models, did not
reach the quality bar. They were reviewed only to find where they went wrong. No code or
assets are carried over.

| Project | What went wrong (evidence) | Root cause | Countermeasure in this plan |
|---|---|---|---|
| `character-generator` (procedural TS) | Hoodie sleeves balloon into boxy puffs (`fit: 1.9`, a radial scale, `src/core/wardrobe.ts:33`). Cone skirts, faceted-box heads with dot eyes and stick hair. Docs banned "global inflation" (`README.md:55`) yet the code used it | Humans built as ring lofts in code with no modeling tool; "loose" implemented as inflation; the target was a 2D AI image and no 3D render was ever approved | Author in Blender from anatomical reference (§3); silhouettes are authored, never inflated (§6); 3D sign-off at M1 (§11) |
| ″ | All 7 gates "passing" while the content was crude. The clearance gate (≥ 2 mm) passed a 1.9× balloon; the coverage test covered 8 of 41 items (`tests/outfit-coverage.test.ts:18`) | Gates measured numbers and covered a sample, never appearance | Gates run over **every** catalog item; every gate has a known-bad fixture proving it fires; a visual gate with user review (§7.5) |
| ″ | One material per (item, region) through a MultiMaterial, so one draw call per region; the profiler counted active meshes as "draw calls" (`tools/profile.mjs:43`) | Single-character "one live preview" architecture | One draw call per character by construction; draw calls read from Babylon's engine counter, not mesh counts (§8.5) |
| `character-generator-gpt` (procedural TS) | Tube limbs, cylinder skirt, box head; "arms/cuffs/waist/footwear fit failed in poses/layers despite clean neutral appearance" (SPEC B5); 11,568 sampled crossing checks passed crude garments | Same procedural approach; an intersection-free result says nothing about quality | Same as above; correctness tests and quality review are separate gates |
| `ai-character-creator` (Qwen-Image-Edit → TRELLIS.2 → auto-rig) | 29 MB, 972k-vertex GLBs; clothing fused into the body; hands bound to hip bones; feet below the floor; recolor key hue drifting; proportions uncontrollable ("petite is rendering as a child") | AI 3D gives unique fused topology and an inconsistent rig per character; every fix was a post-hoc patch | AI 3D is never used for body or garment runtime geometry. At most it supplies concept art, or *shape reference* for rigid props, after the §3 bake-off |
| World Forge (`world-builder-opus-5` + worktrees, asset-pack bodies) | No sliders possible (pack bodies had zero morph targets). Garments fit only the body they were authored on. Dominant-bone triangle hiding → "legless player", saw-tooth cuts. Full base body drawn under clothes. A push-out "relief" pass inflated sleeves and boots. Heels through boots. Dyes fought painted textures. Game and harness lighting drifted. 26–31k tris + 2048² maps per avatar, no LOD, 9 NPCs total | Picked a content pack before fixing requirements; heuristics (cuts, push-out) instead of authored structure; clipping gated only at bind pose | Own the base mesh and its morphs; cut lines are authored edge loops; hide sets are measured; no runtime push-out; greyscale + mask recolor; **one lighting rig shared by game, editor and tests**; budgets before assets |

**User statements from those projects carried forward as requirements** (to be confirmed,
§12):

- *"rendering the full base character under the clothing … with your own cuts. Let's stop
  that practice completely."* So covered body is not drawn, and the cuts must be clean.
- ~~Shoes are worn over the foot, and the foot is not removed (World Forge `0c2aa3b`).~~
  **Superseded 2026-10-12: "clip feet when possible".** Foot bands are hidden inside shoes
  whenever the shoe measurably covers them (§7.3 D1). The old rule likely came from World
  Forge's failure modes: claimed, unmeasured hiding and a "legless player" when a garment
  failed to build. Measured, failure-safe hiding removes both.
- Recolor: *"color 1 as primary, color 2 as accent, and color 3 as detail"*, and each
  item's colors are independent.
- Hands must be able to grip things, so there are finger bones and the hands are bound
  open.
- *"target is browser video games, not cinema"*: detail budgets are low.
- Proportion presets must read correctly: petite ≠ child, tall ≠ absurdly long legs.

**Never solved anywhere, so this plan must address them explicitly:** hair passing through
outer layers and hoods (§7.3 D8); garment-on-garment clipping *in motion*, such as boots vs
trousers and shorts at the hip mid-stride (§7.3 D7, D9); fit across body-slider extremes
(§7.3 D3); neck and face seams (§10); real-device crowd measurement (§8.5); artistic sign-off
on any 3D character (§11 M1).

**Process lessons:** scope sprawl (a 9-viewport accessibility gate while appearance had no
gate at all; 35k lines of avatar code), rushed finishes, parallel agents breaking each
other's work, and verification that silently checked nothing (cameras pointed at garment
backs, a nude NPC passing three reviews). The countermeasures:

- a thin vertical slice;
- gates proven able to fail;
- worktrees for parallel work (project `CLAUDE.md`);
- user review of real renders at every milestone.

---

## 3. Discovering which 3D tools I can use best

### 3.1 An honest self-assessment

I work through code, a shell and rendered images. There is no live viewport and no
sculpting hand.

- **Strengths:**
  - exact topology and dimensions;
  - perfectly repeatable batch work over hundreds of items;
  - numerical verification (penetration depth, budgets, weight sums);
  - reading APIs and file formats;
  - looking at rendered PNGs and comparing them against references.
- **Weaknesses:**
  - judging subtle organic form (faces, hands, the read of a silhouette) without an
    explicit side-by-side reference;
  - each look-and-adjust loop is slower than an artist's live viewport;
  - a tendency to accept "numerically correct" as "good". That last one is exactly how
    the earlier projects passed their gates with crude art (§2).

So the tool choice must turn precision into quality:

- **Start from real reference data** for anything organic, rather than from formulas.
- **Use modeling operators** (bevel, loop cut, solidify, shrinkwrap, surface deform, data
  transfer) rather than raw vertex math.
- **Compare every render against an approved reference**, side by side, from fixed
  cameras under the shared lighting rig.
- **Keep the user in the loop** at milestone gates.

### 3.2 Inventory (verified on this machine, 2026-10-12)

| Tool | Status | What was verified |
|---|---|---|
| **Blender 5.0.1** (apt, `/usr/bin/blender`, Python 3.14.4, numpy 2.3.5) | ✅ works headless | `blender -b -P`: built a mesh, 2-bone armature, `ARMATURE_AUTO` heat weights (4 ms), shape key, keyframed action, color attribute. glTF export (Khronos I/O 5.0.21) produced `POSITION/NORMAL/TEXCOORD_0/COLOR_0/JOINTS_0/WEIGHTS_0`, 1 morph target, 1 skin, 1 animation. Renders: Workbench 0.5 s, EEVEE 6 s, **Cycles on CUDA (RTX 4080)** 143 s first run (one-time `nvcc` kernel build for `sm_89`, now cached), fast afterwards. No OptiX or OpenImageDenoise in the Debian build. Bundled add-ons include glTF, FBX and Rigify |
| Babylon.js under Node (`NullEngine`) | ✅ works (tested on 8.56.2; the project is now on 9.30.0, smoke-tested in headless Chrome) | Loaded that GLB headlessly: skeleton (2 bones), morph target manager (1), animation group (6 channels). **Geometry gates can run as plain Node tests.** Note: pass a `Uint8Array`, not a `File` (Node has no `FileReader`) |
| Babylon loader extensions | ✅ present | `EXT_meshopt_compression`, `KHR_mesh_quantization`, `KHR_draco_mesh_compression`, `KHR_texture_basisu`, `MSFT_lod`, `EXT_mesh_gpu_instancing`; `BakedVertexAnimationManager`, `MaterialPluginBase`. **No `KHR_meshopt_compression`**, so use the EXT variant |
| Google Chrome 151 + Playwright browsers | ✅ installed | For real-WebGL screenshots and timing. Earlier projects found `--use-angle=vulkan` gives GPU rendering headless, 14× faster than SwiftShader |
| `@gltf-transform/cli` 4.5.1, `gltfpack` 1.3.0, `meshoptimizer` 1.3.0 (npm) | ✅ available | The meshoptimizer JS API has `simplify`, `simplifyWithAttributes`, `simplifySloppy`, `simplifyPrune` and a remesher. The simplifier outputs **index buffers only**, so LODs share vertex buffers, skin weights and morphs survive, and runtime LOD generation is viable |
| KTX-Software (`ktx`/`toktx`) | ⬜ not installed (install at M2) | Needed for KTX2 textures. GitHub release `.deb` v4.4.2 |
| ComfyUI with Hunyuan3D 2.0/2.1, TRELLIS.2, UniRig, Make-It-Animatable | ✅ installed (shared GPU service) | Licences in §3.3. **Hunyuan3D is excluded** |
| CUDA for PyTorch (`~/ml-env`) | ✅ works | `nvidia-smi` currently fails with a driver/library mismatch (userspace 595.91 vs kernel module 595.84; `/var/run/reboot-required` dated Oct 7). CUDA itself still works. A reboot will clear it |
| **Blender 5.2.2 LTS** (official tarball, `~/opt/blender-5.2.2-linux-x64/`) | ✅ installed 2026-10-12 | SHA-256 verified against `blender-5.2.2.sha256`. Pinned and portable, unaffected by apt upgrades. Adds meshopt export and faster animation export. Hosts the MCP server (§3.5) |
| **Blender Lab MCP v1.0.3** (`.mcp.json`, project scope) | ✅ verified end to end | Headless `--command blender_mcp` on `127.0.0.1:9876`. An MCP stdio handshake listed 26 tools; `execute_blender_code` round-trips in ~2 ms, and the scene persists between calls. Start/stop: `tools/blender-mcp.sh` |

### 3.3 Candidate tools per job, with licences

| Job | Candidates | Notes / licence |
|---|---|---|
| Body shape + morph targets | **MakeHuman/MPFB2** base mesh + targets, projected onto our low-poly topology; direct Blender modeling | MPFB code is GPL, but **assets (base mesh, targets, proxies, rigs, MHCLO clothes) are CC0** since the 2020 relicense, and output is unrestricted. MPFB 2.0.18 has a scriptable service API (`HumanService`, `add_builtin_rig(…, "game_engine")`) and its own MCP bridge (`makehumancommunity/mpfb-mcp`). Macro targets (sex/age/weight/muscle) are multilinear, so bake corner targets for linear glTF morphs. Joints are vertex-group means, so a joint regressor falls out directly |
| Low-poly topology | Blender modeling ops; QuadriFlow / Decimate as starting points; MakeHuman `proxy741` (741 verts) as a reference | Topology-changing modifiers can't be applied to meshes with shape keys, so reduce first and morph later |
| Garment fit | Body-offset shells, **Surface Deform** bound to the body (loop over body shape keys to bake per-garment morph deltas for review), Shrinkwrap, MakeClothes/MHCLO binding | Surface Deform fails on non-manifold or degenerate faces, so bind to a cleaned, triangulated body copy |
| Garment weights | Blender **Data Transfer** (`POLYINTERP_NEAREST`) then `vertex_group_limit_total(4)` + normalize; RobustSkinWeightsTransfer (MIT) for hard cases | Weights always come from the body (§7.3 D4) |
| Skeleton | MPFB `game_engine` rig, renamed to **VRM 1.0 humanoid** names | The VRM names are a canonical retarget map |
| Animation | **Mesh2Motion** (CC0 rigs and animations, MIT code), **KayKit** Character Animations (CC0, 133 clips), Kenney (CC0), CMU mocap (free incl. commercial, no finger data; its terms forbid reselling the data "even in converted form" and ask for a credit line), retargeted in Blender | **Quaternius** changed to the *Quaternius Asset License v1.0* on 2026-08-28, which forbids redistributing the assets. A web game serves its files to every player, so avoid it unless that is cleared. Mixamo forbids redistributing raw files, has no API and needs the user's Adobe login, so avoid it. LAFAN1, Bandai Namco and AMASS are non-commercial, so excluded |
| Rigid accessories / props | Blender modeling; **TRELLIS.2** (MIT) geometry as shape reference, then decimate to 300–2k tris, re-UV and flat-color | TRELLIS.2's texture bake uses **nvdiffrast, which is research-only**, so use geometry only. **Hunyuan3D 2.x is excluded**: its licence forbids distributing or displaying output in the EU, UK and South Korea, which a web game cannot honour. AI meshes are never used for bodies or garments (§2) |
| Auto-rigging | Not needed for body or garments (one skeleton + transfer). UniRig (MIT) / Make-It-Animatable (MIT) only for odd props or creatures | |
| Optimize / compress | gltf-transform (`dedup, prune, weld, quantize, meshopt, sparse, etc1s/uastc`), gltfpack `-cc`, `ktx` | EXT meshopt only (Babylon) |
| Verification | Babylon `NullEngine` in Node (geometry, budgets, clipping math); Playwright + Chrome for real-WebGL screenshots; Blender Workbench for deterministic sheets | |

**Pinning:** the apt Blender can change under us on any system upgrade, and the driver
just did exactly that. The build pipeline will pin **one portable Blender** (5.2.2 LTS),
record its version in `SPEC.md §C`, and check it at build start.

### 3.4 The bake-off: how the choice gets made

Each **probe** is a small, real piece of the final product. Each is attempted with two or
three approaches and scored. The probes run in M1, after the M0 style frame fixes what
"good" looks like.

| Probe | Content | Approaches compared |
|---|---|---|
| P1 Base body | adult unisex body, A-pose, ≤ 3.5k tris, loops at joints and cut lines | (A) direct Blender modeling from primitives with modifiers · (B) designed low-poly topology projected onto MakeHuman CC0 anatomy · (D) code-generated (control; expected to lose, §2) |
| P2 Faces | 6 distinct identities from one head via morphs; painted vs geometric features | (A) vs (B); decal treatment vs geometry |
| P3 Garments | tee, jeans, skirt, jacket over tee, boots — on 5 envelope bodies | (A) authored on the shell + Surface Deform · (C) MHCLO/MakeClothes binding · our build-step binding (§4.3) |
| P4 Deformation | stress poses: arms up, crouch, sit, run extremes, arms crossed, reach | weights from MPFB rig vs Blender heat vs transferred; ± twist bones |
| P5 Rigid accessory | hat, glasses, bag | (A) modeled · TRELLIS.2 geometry + decimate |
| P6 Animation | idle, walk, sit, wave on our rig | Mesh2Motion vs KayKit vs CMU, retargeted in Blender |
| P7 Pipeline | export → optimize → Babylon → merged character, one draw call | must work end to end; this one is pass/fail |
| P8 Interface | the same P2 iteration done twice | batch scripts (`blender -b -P`) vs a persistent Blender MCP session (§3.5): wall-clock per iteration, failure rate, reproducibility |

**Scoring.** For each (probe, approach):

| Criterion | Weight | How measured |
|---|---|---|
| Visual quality | 40 % | user review plus a **blind A/B** against the approved style frame; a different agent or the user holds the key (an idea from World Forge's `CRITIC.md`) |
| Deformation quality | 20 % | stress-pose sheet; penetration metrics (§7.5) |
| Automation / reproducibility | 15 % | a committed script regenerates it bit-for-bit |
| Budget compliance | 10 % | tris, bones, bytes |
| Iteration speed | 15 % | minutes per change → render → review loop |
| Licence | pass/fail | CC0 / MIT / own work only for anything shipped |

**Evidence:**

- contact sheets at `docs/bakeoff/<probe>/<approach>.png`: front, ¾, side and back, with
  neutral plus two envelope bodies plus two poses, all under the shared lighting rig;
- metrics as JSON next to each sheet;
- the decision per job recorded in `SPEC.md` (`§C` for the tool, `§R` for the facts
  behind it).

**Expected outcome (a hypothesis, to be proved or refuted):**

- (B) MakeHuman projection wins the body and head, because anatomy comes from data and
  topology from design.
- (A) direct Blender modeling wins garments and accessories, because silhouettes must be
  authored.
- Code generation is used only for runtime assembly.
- An MCP session wins exploration speed, and batch scripts remain the reproducible
  build path.

**Outcome (M1, 2026-10-13; details, scores and evidence in `docs/bakeoff/M1.md`):**

- **P1 body:** (B) wins in its proxy form. MakeHuman's CC0 `female1605` proxy is
  human-designed quads, bound linearly to the MakeHuman base, so all 658 targets transfer
  exactly. The 23 standard cut lines are authored onto it by plane cuts. The same topology
  covers ages 1→70. (A) and (D) were not run.
- **P2 faces:** geometric features (S1). Brows are authored strips; MakeHuman's brow cards
  read stern.
- **P3 garments:** (A) body-band shells with authored openings beat (C), MakeHuman's
  garments decimated and rebound. (C) leaves gaps at openings that don't land on cut lines.
  MakeHuman clothes stay as shape reference.
- **P4:** MakeHuman `game_engine` weights through the binding, plus twist drivers, hold in
  the stress clips. The one defect is self-contact in `arms_crossed` (D10, M4).
- **P6:** CMU 113 (idle, walk, arms up, wave) plus Mesh2Motion (sit, run, crouch, arms
  crossed). KayKit lost every clip.
- **P7:** pass. **P8:** the persistent Blender session for iteration; the same scripts are the
  build.
- **P5:** not run (M3).

### 3.5 Blender MCP (suggested by the user)

An MCP server keeps one Blender process alive. The scene persists between calls,
introspection tools are available, and stdout and tracebacks come back as structured
results. That removes the cold start and rebuild cost of one `blender -b -P` per step.
Options as of 2026-10-12:

| Option | Headless? | Blender | Telemetry / security | Licence | Verdict |
|---|---|---|---|---|---|
| **Blender Lab official** (`projects.blender.org/lab/blender_mcp` v1.0.3) | **Yes.** `blender -b --command blender_mcp --port N` runs a blocking loop built for background mode; screenshot tools are GUI-only, but render-to-path works. Also searches the bundled 5.x API docs | **≥ 5.1** | No telemetry found. The socket has no auth, so loopback only | GPL-3.0 (a tool; it does not encumber the assets) | **Recommended** |
| ahujasid `mcp-for-blender` (the popular one) | No. Refuses in `-b`; needs Xvfb (which means llvmpipe, not the 4080) | 3.0+ | **Telemetry on by default** (`DISABLE_TELEMETRY=true`); CVE-2026-10688 code injection via `execute_blender_code`; SSRF CVEs in its asset downloaders (patched) | MIT | Skip |
| `dcc-mcp-blender` | Yes (headless HTTP bootstrap) | 4.5+ | ? | MIT | Fallback: typed rigging and shape-key tools |
| `makehumancommunity/mpfb-mcp` | ? | MPFB | ? | ? | Evaluate in P1 alongside the official server |

**Caveats of the official server:**

- Python variables don't persist between calls; `bpy.data` does. Return values go in a
  `result` dict.
- Each request must finish synchronously, with a 300 s socket timeout. Long Cycles renders
  go through batch scripts.
- It needs `--online-mode` in background mode, and must not be started with
  `--factory-startup`.

**Setup (done 2026-10-12, with the user's OK):**

1. Blender 5.2.2 LTS is unpacked to `~/opt/blender-5.2.2-linux-x64/`.
2. The extension `mcp-1.0.3.zip` is installed with
   `blender --online-mode -b --command extension install-file -r user_default --enable`.
3. It runs headless under **nohup**, which the user allowed instead of systemd:
   `tools/blender-mcp.sh start|stop|status`. It binds `127.0.0.1:9876` and logs to
   `~/.local/state/blender-mcp/`. It does not survive a reboot, so run `start` again after
   one.
4. It is registered at **project** scope in `.mcp.json`. The command is
   `uvx --from "git+https://projects.blender.org/lab/blender_mcp.git@v1.0.3#subdirectory=mcp" blender-mcp`,
   because PyPI's `blender-mcp` is the ahujasid package. Its env sets `BLENDER_MCP_HOST`,
   `BLENDER_MCP_PORT` and `BLENDER_PATH`.

New Claude sessions in this project load it after approving the project MCP server.
Raw-socket clients must send `{"type": "execute", "code": …, "strict_json": true}`,
null-byte terminated. Probe P8 still measures whether it really is lower friction.

**Rule regardless of interface:** anything made interactively must end up reproducible.
Either the `.blend` source is committed under `assets-src/`, or the steps are captured as
a committed build script. An asset that exists only in a live MCP session does not exist.

---

## 4. Architecture

### 4.1 Pipeline

```
 AUTHORING  (offline, Blender 5 bpy)   BUILD  (Node CLI, deterministic)      RUNTIME  (browser)
 ───────────────────────────────────   ──────────────────────────────────    ─────────────────────────────────
 base body: topology, cut-line loops,  validate: budgets, weights ≤4 and     catalog manifest (tiny, versioned)
   regions, UVs, morphs, skeleton,       normalized, regions, UV cells,      items fetched lazily, HTTP cached
   joint regressor                       slot rules                          ── assembler (Web Worker) ──────
 items: garments, hair, shoes,   ───▶  bind: item verts → body anchors  ───▶ 1 bake morphs → body
   accessories, authored ON the          (fit data), inherit weights,        2 joints = regressor·verts → skel
   neutral body                          measure hide bands                  3 fit items to the morphed body
 animations: retargeted to our rig,    LODs per item; color-baked far LOD    4 drop hidden bands
   rotation-only                       compress: meshopt + quantize; KTX2    5 merge → 1 buffer set per LOD
 render sheets for review              clip tests; contact sheets; thumbs    ── main thread ──────────────────
                                                                             Mesh + shared material + skinning
                                                                             crowd animator · LOD · blob shadows
```

The split matters. **Authoring** is where quality comes from: Blender, reference data, and
human approval. **Build** is where correctness is enforced: every rule in §7 is a check
here, run on every item. **Runtime** does only cheap, predictable work. There are no
heuristics at runtime: no push-out, no auto-cuts, no inflation. Each of those was a
failure mode in §2.

### 4.2 Data model

- **Base body** (one unisex topology, adult). Per vertex: position, normal, UV,
  joints/weights, and a region-band id. It carries:
  - sparse morph targets grouped into sliders;
  - a **joint regressor**: each bone head is a fixed weighted average of body vertices;
  - **cut-line loops**: edge loops at the standard garment boundaries (§6.2).
- **Skeleton**: one canonical humanoid, about 60 bones at LOD0 (§5.4). It is bound in an
  open A-pose with fingers spread.
- **Item** (garment, hair, shoes, accessory):
  - identity: `id`, `slot`, `layer`;
  - geometry: mesh LODs; per-vertex *fit binding* and inherited skin weights. The binding
    is body or robe-proxy triangle(s), barycentrics, and a local-frame offset (§7.3 D3); a per-vertex recolor channel or mask UV; per-triangle region-band tags;
  - rules: measured `hides` (body bands, plus bands of lower-layer items), `covers`,
    compatibility tags (hair class, tuck mode, collar/hood class, rigid islands), and **age
    eligibility + content tags** (§5.7);
  - for accessories: an attach socket;
  - `bulk` (thickness per region, used by animation corrections, §7.3 D10);
  - default colors.
- **Catalog entry**: an item plus a *variant* (default colors, optional pattern, name,
  tags). Many entries share one mesh, which is how "hundreds of items" stays small (§9).
- **Appearance descriptor**: `{v, sliders: u8[], items: u16[], colors: u16[]}`, about
  150 bytes. Its hash is the cache key for the assembled character.

### 4.3 Assembly (Web Worker, deterministic, cached)

1. **Morph bake.** `body = neutral + Σ sliderᵢ · Δᵢ` (sparse) for each LOD.
2. **Skeleton fit.** Joints come from regressor × morphed vertices, giving bone rest
   transforms and inverse bind matrices. Clips are rotation-only, so they play on this
   skeleton unchanged. Hip translation is scaled by the hip-height ratio.
3. **Item fit.** `p' = Σ baryᵢ·v'ᵢ + Frame'·offset`, evaluated on the morphed body or
   robe proxy (§7.3 D3). The offset lives in the surface's local frame, so a garment keeps
   its authored thickness on any body and turns with the surface. Rigid islands (buckles,
   buttons, brims, glasses) take one rigid transform per island instead, so they never
   bend. Normals are recomputed *after* fitting.
4. **Hide.** Drop the body bands and lower-layer item bands hidden by items that
   *actually built*. If an item fails, its hides are not applied, so a failure shows skin,
   never a hole.
5. **Merge.** One vertex/index buffer set per LOD, with these attributes:
   - position, normal and atlas UV;
   - joints and weights;
   - a slot index and channel data for recolor.
6. **Hand-off.** Buffers are transferred zero-copy to the main thread. There, one Babylon
   `Mesh` per character is created, with the shared material and a per-character palette.

The same code runs in Node, which enables headless tests and pre-baking NPCs. It also runs
in the character creator, where it re-assembles on slider release; during a drag, only the
one preview character uses live morph targets.

### 4.4 Rendering

- **One material for every character**: a material plugin on a lightweight base material,
  or a small custom shader. Shared means one shader program and no compile hitch when new
  characters appear.
- **Color:** `albedo = shade(atlas luminance) × (mask.r·C[slot].primary + mask.g·C[slot].accent
  + mask.b·C[slot].detail)`, with an unmasked remainder from a fixed palette. Skin, hair and
  eyes are palette slots too. Colors are a per-character uniform array, or a row in a
  shared palette texture.
- **Faceted look without tripling vertices:** flat-shaded meshes must split every vertex
  per face, roughly 3× vertices, and skinning cost scales with vertices (verified: a
  130-triangle test cylinder exported 624 vertices). Two cheaper options:
  - keep shared vertices and derive face normals in the fragment shader with
    `cross(dFdx(p), dFdy(p))`;
  - use smooth normals on a low-poly mesh.

  The style frame at M0 (§11) chooses between them. **Chosen: smooth normals** (user,
  2026-10-13, §5.5), so the derivative-normal path stays only as a viewer toggle.
- **One lighting definition** (`lighting.ts`) used by the game, the creator and every
  screenshot harness. World Forge's face-shadow bug came from harness lighting drifting
  from game lighting.

### 4.5 Creator UI: phone first (user, 2026-10-12)

The creator is designed for **portrait phones first**, then scaled up to tablets and
desktops.

- **Layout:**
  - **Portrait phone:** the character fills the top ~55–60 % of the screen.
  - **Bottom sheet:** tabs (Body · Face · Hair · Clothes · Colors · Family), large-thumb
    sliders, swipe between slider groups, and an item grid of thumbnails recolored to the
    player's colors (§9.3).
  - **Colors:** palette swatches first, then a hue/saturation picker.
  - **Touch:** targets ≥ 44 px, with one-handed reach for the common actions.
  - **Larger screens:** tablets and desktops move the sheet into a side panel.
- **Camera:** full-body, face close-up and outfit presets; drag to rotate, pinch to zoom.
- **Foldables:** the Galaxy Z Fold-class cover screen (narrow portrait) and inner screen
  (near square) switch live on resize, without losing state.
- **Live preview:** only the creator's one preview character uses live morph targets while
  a slider is dragged. Release triggers a worker re-assembly (§4.3), so the in-game cost
  stays zero.
- **Mobile constraints:** mobile browsers kill tabs at far lower memory than desktops (?),
  so the character system budgets **≤ 64 MB GPU memory and ≤ 150 MB JS heap for 100
  characters**. Resolution follows a capped DPR with dynamic scaling (§8.3). Frame rate is
  capped at 30 fps on phones, which saves battery and heat.

---

## 5. Body and face customization

### 5.1 One unisex base mesh

All bodies share one topology, with a masculine↔feminine continuum as a slider; this is how
MakeHuman and SMPL-style body models work. That single choice is what lets every garment be
authored **once** and fit every body. A per-sex topology would double the authoring of every
garment. Breast, hip and shoulder differences are morphs.

### 5.2 Sliders

- **Macro sliders:** sex, weight, muscle, age (young adult → elder), height, and
  head-to-body ratio within the stylized range. These are *not* plain linear morphs.
  Following MakeHuman, they blend between authored key bodies with weights computed from
  the macro values. That keeps extremes and their combinations (heavy + muscular + elder)
  as designed shapes rather than accidental sums.
- **Region sliders (body):** shoulder width, chest, bust, waist, belly, hips, glutes,
  thigh, calf, upper-arm and forearm girth, arm length, leg length, torso length, neck
  length and girth, hand size, foot size.
- **Face sliders:**
  - head width, height and depth; forehead; brow ridge;
  - eye height, spacing, size and tilt;
  - nose length, width, bridge and tip;
  - cheekbones, cheek fullness, jaw width and angle;
  - chin height, width and protrusion;
  - mouth width, lip fullness, ear size and angle.
- **Discrete choices:** eye shape and color, brow style, facial hair, makeup, freckles and
  marks. These are decal-atlas entries plus palette colors.
- **Ranges are clamped to a tested envelope.** The corner set of the envelope is exactly
  what §7.5 tests against. A slider that can reach an untested shape is a bug.

### 5.3 Where the shapes come from

Earlier projects derived shape from parametric formulas and looked crude (§2). Here, shape
comes from **real anatomical data projected onto a designed low-poly topology**.

The candidate source is MakeHuman/MPFB's CC0 base mesh and targets (licence check in §3).
The method:

1. Design the low-poly topology in Blender (loops at joints and cut lines, §6.2).
2. Bind each low-poly vertex to the high-res reference surface.
3. Transfer each reference target by re-projecting.

Stylization (head scale, simplified hands, faceting) is applied as our own morphs on top.
The bake-off in §3 tests this against modeling the body directly in Blender.

### 5.4 Skeleton

- **Bone set:** about 60 bones at LOD0:
  - spine ×3, neck, head and jaw;
  - eyes ×2 for gaze, plus a few face bones (brows, lid, mouth corners) for expressions;
  - clavicles; upper arm, forearm and hand; one twist bone each per upper arm and forearm;
  - simplified fingers: thumb ×3, index ×3, middle ×3, and ring+pinky merged ×3 per hand,
    so hands can grip;
  - thigh, shin, foot and toe; optional twist bones on the thighs;
  - helper bones for skirts and coats (§7.3 D7).
- **Skeleton LOD:** LOD1 drops face, twist and finger bones (≈ 30). LOD2 keeps ≈ 18.
- **Bind pose:** open A-pose, arms about 45° and clear of the torso, fingers spread and
  slightly curled, feet hip-width apart. Hands near the hips get bound to hip bones; that
  was a real bug before (ai-character-creator B12).
- **Joint regressor** keeps bones inside the morphed body: a wider body moves the shoulder
  joints out, and a taller one lengthens the bones. Clips are rotation-only and therefore
  proportion-independent. Animation contact problems from varied proportions are handled
  in §7.3 D10.

### 5.5 Faces

Identity lives in the face, so it gets a disproportionate triangle share: about 25–30 % of
LOD0 body triangles are in the head.

- **Eyes:** small geometric eyes driven by eye bones, so characters can look at each
  other. That matters in a social game.
- **Expressions:** jaw and face bones at LOD0. No runtime morphs.
- **Features: geometry or texture, settled by seeing** (user, 2026-10-12). M0 renders the
  same test character three ways:

| Style | Form | Color and features | Textures |
|---|---|---|---|
| **S1 All vertex color** | everything modeled | per-face vertex colors only. Eyes, brows, lips, nostrils, hairline and clothing details are geometry with their own face colors. Recolor channels are per-face ids | **none** |
| **S2 Geometry + painted face** | same faceted geometry | the body and clothes as in S1; eyes, brows, lips, blush, freckles and stubble from a shared face-decal texture | face decal atlas only |
| **S3 Texture detail throughout** | same geometry | S2 plus greyscale detail/mask textures on clothes (seams, folds, prints) and hair (strand shading) | decal + detail/mask atlases |

  Each style is rendered with **flat facets** and **smooth normals** under the one shared
  lighting rig, next to the approved reference. The user sees a contact sheet plus a live
  page to orbit on a phone. S1 is the cheapest by far (no textures, no UV2, no atlas
  bleed), so it wins any tie.

  **Picked: S1 with smooth normals** (user, 2026-10-13, after the contact sheet and live
  page). Features are geometry with per-face vertex colors, and the base character ships no
  textures. The one correction was to the lips: four decimated triangles still counted as
  lip and drew pink wings past the mouth corners and spikes toward the nose. A face now
  takes a feature color only if **every** corner lies in that feature's vertex group, not
  just the corners' mean (SPEC V16, B4).

### 5.6 Ages and families

The audience is teen girls who want to build families (user, 2026-10-12), so every age is
in scope:

| Group | Age-macro range | Notes |
|---|---|---|
| Infant | 0–1 | a full character with **fewer customizations**: face identity mostly inherited; skin, hair and eye color; a couple of body sliders. **Several clothing options: onesie, diaper, and several baby versions of adult clothes** (user, 2026-10-12). Held, carried, crawling, sitting, lying |
| Toddler | 1–3 | own gait clips; short limbs, big head |
| Child | 4–12 | continuous within the group |
| Teen → adult → elder | 13–90 | continuous; teen–elder **share one garment catalog** (as The Sims does) |

- **One topology and one skeleton across all ages is the goal.** It gives one garment
  pipeline, aging that keeps identity, and inheritance in a single slider space.
  - MakeHuman's CC0 age macro already spans 1–90 years, so age proportions come from
    data, not guesses.
  - The risk is the infant and toddler end: head ≈ ¼ of height, no visible neck, and short
    limbs that stretch the topology and its triangle distribution.
  - So probe **P1 must build a toddler and a child from the same topology as the adult**.
  - Fallback: a separate "small" frame for infant and toddler that keeps the bone names
    and face sliders. That is the Sims 4 approach: infants and toddlers have their own
    frames.
- **Garments by age.** Every item declares the age groups it is eligible for.
  - **Children** get their own catalog. An adult garment may be auto-fitted to a child
    body as a *draft* (D3 binding, with offsets and rigid islands scaled by local body
    scale, so a toddler's buttons are smaller). Drafts are promoted only after review.
  - **Infants and toddlers** get onesies, diapers and sleepers, plus **baby versions of
    adult clothes**. The adult-garment auto-fit drafts are their natural source.
  - **Matching family outfits** come almost for free. One item family exists across age
    groups and shares the same color channels, so "mini-me" parent-and-baby outfits are a
    single click. That suits the audience.
- **Animation by age.** Bone names are shared. Rotation-only clips play on any proportions
  where the motion is the same; toddler walk, infant crawl and held poses are separate
  clips.
  - **Interactions between ages** pair two characters with root alignment plus
    contact-point IK computed from both bodies' heights: carrying an infant on an arm
    socket, holding hands, piggyback, hugging a child, reading together, pushing a
    stroller.
- **Inheritance ("make a family").**
  - **Sliders:** `child.sliderᵢ = lerp(parentA.sliderᵢ, parentB.sliderᵢ, wᵢ) + noise(σᵢ)`,
    with per-slider dominance weights and a sibling-specific seed. Siblings resemble their
    parents and each other but are not clones.
  - **Skin tone** blends in a perceptual space (OKLab). Hair and eye color, and discrete
    traits such as hair texture and brow style, come from the parents by simple
    probability rules.
  - **Identity sliders are stored as deviations from the age-mean shape.** So "wide jaw,
    big nose" at 5 maps to the same person at 40, and aging up is just moving the age
    macro and swapping to age-eligible clothes.
  - The descriptor stays ≈ 150 bytes; parent links live in game data, not in the
    appearance.
- **Testing:** clipping and quality suites run over **each age group's** envelope (§7.5).

### 5.7 Audience and content rules (teen players)

These rules live in the data and the assembler, so a modified client cannot break them for
other players:

- **A non-removable base layer.** Teen and older bodies always wear base underwear as a
  layer-1 skin-paint region. Children and toddlers wear a base outfit, and infants wear a
  diaper. The assembler adds it
  itself, and no descriptor can remove it.
- **Bounded sliders.** Bust, hip and glute ranges are capped at a non-sexualized range,
  set per age group. Child, toddler and infant groups have no sex-dimorphism body sliders;
  face sliders only.
- **Eligibility everywhere.**
  - Every catalog item and every animation or emote carries age eligibility and content
    tags.
  - A child can only wear child-eligible items.
  - The catalog contains no revealing or adult-themed items at all.
  - Adult–child interactions are limited to family-appropriate ones.
- **One validator, shared by client and server.** It clamps sliders and rejects
  ineligible items on every descriptor before other players ever see it. Any future
  user-made content goes through the same validator.
- **No personal data.** Descriptors are not PII, and there is no photo-to-avatar feature.
  The game as a whole will likely need COPPA / GDPR-K handling for under-13 players; that
  is outside this system, which collects nothing.

---

## 6. Clothing, hair and accessories

### 6.1 Slots and layers

| Layer | Examples | Geometry rule |
|---|---|---|
| 0 skin | body | base mesh |
| 1 skin-paint | tattoos, makeup, underwear, tights, stubble | **no geometry**: decal or palette regions on the body. It cannot clip or z-fight |
| 2 tight | tee, tank top, leggings, socks | shell at the layer-2 offset; may hide the body bands it fully covers |
| 3 regular | shirts, jeans, trousers, skirts, dresses | layer-3 offset |
| 4 outer | jackets, hoodies, vests, cardigans | layer-4 offset |
| 5 over | coats, aprons, belts, scarves | layer-5 offset; belts are rigid-island bands |
| feet | shoes, boots, sandals | worn over the foot; **foot bands are hidden when the shoe measurably covers them** (user, 2026-10-12: "clip feet when possible"). Open shoes such as sandals hide only what they cover, e.g. the sole. Its own offset rule |
| head | hair, hats, glasses, masks | hair classes + hat modes (§7.3 D8) |
| attach | earrings, watch, bag, backpack, held props | rigid, single-bone, merged into the character mesh |

Each layer has a **standard offset from the body surface**: a few millimetres per layer,
tuned at M2. The offsets are enforced at build time, not hoped for. This gives a total
ordering. Any two items either sit in different layers, or in the same layer and the same
slot, and so are mutually exclusive.

### 6.2 Standard cut lines

Every garment edge has to land somewhere, and the body must be cut at that exact place.
So the body topology has **edge loops at a fixed set of standard lines**. Garments are
authored so their openings sit just past one of these lines, overlapping the kept skin.

- **Neck:** crew, V, scoop, collar.
- **Arm:** shoulder cap, short sleeve (mid upper arm), elbow, three-quarter, wrist.
- **Torso:** under-bust (crop), natural waist, high hip, low hip.
- **Leg:** hot-pants, mid-thigh, knee, mid-calf, ankle.
- **Foot:** sole, toes, instep, heel, ankle. These let closed shoes hide the whole foot and
  sandals or flats hide only what they cover.
- **Boot shaft:** ankle boot, mid-calf boot, knee boot.

The band between two loops is the unit of hiding. A garment hides a band only if it covers
that band **end to end**, in every stress pose and on every envelope body. This is
*measured* at build time (§7.3 D1). This replaces World Forge's per-triangle
dominant-bone cuts, which produced saw-tooth edges and missing limbs.

### 6.3 Authoring a garment (Blender)

1. Start from the neutral body's layer shell (the body surface offset to the layer
   distance) for close-fitting parts.
2. **Author the silhouette** by hand-shaped modeling: collars, cuffs, hems, pockets,
   folds as facets. Loose fit is modeled, never inflated.
3. Snap openings to the standard cut lines.
4. Tag rigid islands. Assign recolor channels (R primary / G accent / B detail) by face,
   or by mask texture where detail needs it.
5. The build step does the rest: binding, inherited weights, hide measurement, LODs and
   checks. A garment that fails a check does not ship.

### 6.4 Recolor and patterns

- **Channels:** three per item, independent per item. Unmasked parts (metal buttons,
  zippers) use fixed palette colors.
- **Patterns** are optional tiling greyscale textures (stripes, plaid, dots) from a small
  shared atlas, applied inside one channel. They are a variant parameter, so one shirt mesh
  yields many catalog entries.
- **Color storage:** RGB565 (16 bits) in the descriptor. The creator offers a curated
  palette first and a free picker second.

---

## 7. Poke-through and clipping (the hard part)

### 7.1 Taxonomy: what actually clips

| Kind | Example | When |
|---|---|---|
| Body through garment | belly through a shirt on a heavy body; elbow through a sleeve when bent | shape-induced (sliders) or pose-induced (animation) |
| Garment through garment | trouser legs through boot shafts; shirt hem below a jacket; hoodie through a coat | both |
| Hair / accessory through garment | long hair through a coat collar or hood; hair through hats | both |
| Body through body | arms sinking into the torso on wide bodies; thighs merging on heavy bodies when walking | shape × pose |
| Deformation artifacts that *cause* clipping | candy-wrapper twist at the forearm, volume loss at the elbow, shoulder collapse with arms up | pose-induced, from linear blend skinning |
| Loose garment vs legs | a skirt's front cutting into the thighs; a coat tail cut by the back leg in stride | pose-induced |
| Z-fighting | tights, tattoos or underwear as geometry 1 mm off the skin | always; worst on mobile depth precision |

Every earlier attempt here gated clipping only at bind pose, or only on a sample of
items, and fixed the rest with runtime heuristics: cuts, push-out, inflation (§2). None of
those survived motion.

### 7.2 What shipped systems do, and what to take from each

| System | Mechanism | Take | Avoid |
|---|---|---|---|
| **Roblox Layered Clothing** | Body = WrapTarget (outer cage); garment = WrapLayer with inner + outer cage, paired by UV. Deformation runs **once at equip time**, then the result is plainly skinned; layers in ascending `Order`. Hidden-surface removal by rays from the cage after fitting (patent US12190427). AutoSkin copies weights from the nearest body part. 4k-tri cap, 4 influences | **Fit at equip time, then plain skinning.** Measure visibility *after* fitting | Free-form user cages: uneven spacing undulates the surface, an oversized outer cage wrecks the layers above, and AutoSkin binds to the wrong limb. Rebuild spikes on unrelated property changes |
| **Second Life** | System clothing = texture bakes (no clipping). Rigged mesh ignored sliders → "standard sizes" + alpha masks. Fitted Mesh: garments weighted to collision-volume bones the sliders move. Mesh bodies won, with onion-skin layers. Appearance = **218 one-byte params** + wearable IDs | Byte-quantized slider descriptor; skin-tight items as textures | A weak official body plus unenforced budgets → forked body standards, a fragmented catalog, and a 794k-tri body. **We own and enforce one body standard** |
| **The Sims 4** | Sliders = BGEO (morph geometry), bone deltas, and **DMAP deformer maps** sampled through a body-space UV1 on *every* mesh, so clothes deform with the body. Vertex color picks the **skin-tight vs robe** map set, and a skirt painted skin-tight sinks between the legs. "Asset pairing" decides which overlapping asset displays | **Robe mode:** loose garments follow a smoothed, leg-bridged body, not the legs themselves | Per-frame or global map sampling we don't need; a second mesh per body frame (one unisex topology avoids it) |
| **UMA (Unity)** | Slots + overlays combined into one skinned mesh + atlas per avatar. **MeshHideAsset**: per-triangle mask seeded by raycasts (out 0.1, in 0.02) with Strict / Weighted / Conservative rules; check shoulders, elbows, hips, knees. DNA drives bones. A body blendshape doesn't move clothes unless the garment has the same-named shape. **Clothing Conformer**: barycentric + normal offset + welded seams. Cache identical builds; SimpleLOD with hysteresis + staggered checks | Raycast-seeded hide masks; welded-seam fitting; build cache; staggered LOD checks | Live blendshapes at zero weight still cost; manual incompatibility lists |
| **MakeHuman / MPFB** | `.mhclo`: each garment vertex = 3 base vertices + barycentrics + offset (world axes, scaled by reference-vertex distances). The MH 1.2 proposal: a 4-vertex binding with a **local normal-space** delta, "more stable across poses". `delete_verts` masks the body; `z_depth` orders layers | Binding format; **use local-frame offsets**, which rotate with the surface | World-axis offsets distort on large shape changes |
| **WoW** | Geosets: the body has variant segments (gloves, boots, leg cuffs, pants, robe, cape) and each item picks variants. `HelmetGeosetVis` bitmasks hide hair, beard and ears per helmet | **Variant swaps** (tucked / untucked, hat-hair) selected by rules | — |
| **Cyberpunk 2077 garment support** | Each item gets a score (component prefix + tags: Tight −1000, Large +1000); higher-scored garments **squish** lower ones within painted caps. That is how pants tuck into boots | A total order of layers; a bounded *inward* squish of inner layers, never outward inflation | Works only when both items carry the data, so the build must enforce it |
| **Character Creator (AHMP)** | 55 body polygon groups; a garment's active groups hide body groups and same-named groups on lower cloth layers; **hiding flows downward only** | Named bands, downward-only hiding | — |
| **Unreal Mutable** | Remove Mesh Blocks (UV grid), Clip Mesh With Mesh, Mesh Reshape (neutral → morphed fit) | Equip-time reshape | Reshape combined with clip produced spikes (5.8): don't stack geometric heuristics |
| GW2 / ESO / FFXIV | Retreated from mix-and-match to full-body outfits or slot "removes" | Full outfits as an escape hatch for items that can't layer | Retreating is what happens without a grammar |
| s&box | Explicit layer rules: shirts layer 1, coats layer 2, shoes under trousers, torso swaps | A written slot/layer grammar | — |

**Babylon specifics:**

- No dual-quaternion skinning ("no we do not support that"). DQS would also fight bone
  scaling. Use **linear blend skinning with twist bones**.
- Morph targets in texture mode are memory-heavy per character (§8.2), so all shape work
  is baked.
- Spring bones exist in `babylon-vrm-loader` (VRM springs with sphere colliders) as a
  reference for near-LOD hair and capes.

### 7.3 Defenses (layered; each one removes a class of clipping)

**D1 — Don't draw what is covered (measured band hiding).**
The body and every garment carry region-band ids between authored cut-line loops (§6.2).

- **When an item may hide a band:** only if the band is fully covered **in every pose of
  the stress suite on every envelope body**.
- **How coverage is computed:** at build time, after fitting, by casting rays outward from
  the band's surface (the Roblox and UMA approach). An escaping ray means the band is
  visible.
- **What hiding applies to:** body bands and lower-layer item bands. Hiding flows
  **downward only**.

At runtime, hiding drops whole bands of items that *actually built*. This removes most
body-through-garment clipping outright, because what isn't drawn can't poke through, and
it cuts triangles. It cannot produce saw-tooth edges, because band edges are authored
loops. It cannot produce missing limbs, because a band is never hidden on a claim, only on
a measurement. Shoes follow the same rule: a closed shoe hides the foot bands it covers
(user, 2026-10-12: "clip feet when possible"). That also removes the heel poke-through
that World Forge never solved. If a shoe fails to build, the foot stays.

**D2 — The layer-shell grammar.**
Layer *k* has a standard offset envelope [dₖ₋₁, dₖ] from the body surface.

- **The rule:** every "close" vertex of a layer-*k* item must lie inside its envelope, on
  every envelope body. The build enforces it.
- **Loose parts** (skirt flare, hood, coat tail, cuffs) may leave their envelope only
  where flagged loose. Higher layers declare which loose classes they accept (D9).
- **Why it works:** the next layer up is always authored against the *maximum* of the
  layer below, never against one specific item. So any tight-layer item fits under any
  outer-layer item without per-pair tuning. This is the fixed-cage idea from Roblox,
  without user-authored cages.

**D3 — Fit by surface binding with local-frame offsets.**
Each item vertex binds offline to one or a few body triangles (barycentric coordinates),
plus an offset expressed in the triangle's **local tangent frame**. At assembly:
`p' = Σ baryᵢ·v'ᵢ + Frame'·offset`. The offset rotates with the surface, which is the
MH 1.2 and UMA Conformer approach.

- Vertices far from the surface average several triangles, which smooths the fit.
- Binding is restricted to the vertex's own limb chain. That prevents the Roblox AutoSkin
  "wrong limb" bug, such as a sleeve binding to the torso; the A-pose bind keeps limbs
  clear.
- Binding is computed per unique *position*, so UV-split seams stay welded.
- **Rigid islands** (buttons, buckles, brims, glasses frames) take one rigid transform
  per island.
- **Robe mode:** skirts, dresses, long coats and robes bind to a **robe proxy**, a
  smoothed copy of the body with the legs bridged into one volume, carrying the body's
  morphs. They never sink between the legs on any body (the Sims 4 robe maps). The author
  paints per vertex which target is used, skin-tight or robe.

**D4 — Weights are inherited, never painted separately.**
Item skin weights are the binding-weighted average of the bind target's weights: the body,
or the robe proxy for robe-mode vertices. Results are limited to 4 influences and
normalized. Two surfaces 5 mm apart with the same weights deform identically under linear
blend skinning, so the offset survives every pose. Most in-motion clipping comes from
garments weighted differently from the skin beneath them.

**D5 — Skin-tight means no geometry.**
Underwear, tights, tattoos, makeup and stubble are body palette regions or decals:

- palette regions run along cut lines, using a per-face channel on the body;
- decals are a small per-character stack of layers from a shared texture array, sampled
  through the body's UV2.

They cannot clip or z-fight, and they cost no triangles. This is how Second Life, WoW and
VRoid make skin-tight items clean.

**D6 — A rig and topology that deform cleanly.**

- LBS with **twist bones** in the upper arm and forearm (thighs optional) against
  candy-wrapper twisting.
- **Three edge loops at the elbows and knees**, two at the wrists and ankles, and
  shoulder loops designed for arms-up.
- An A-pose bind; the joint regressor keeps joints centred inside any body.
- Corrective shapes only if the P4 probe proves they're needed. They would be bone-driven
  helper bones (RBF pose-driver style) at LOD0, never runtime morphs.

**D7 — Loose garments: skirts, dresses, coats and capes.**

- **Binding and weights:** robe-mode binding and weights (D3, D4).
- **Skirt bones:**
  - 2–4 bones per skirt ring, driven procedurally by the **average** of the thigh
    rotations, never the sum, which doubles the lift.
  - Rotation limits, and a forward/back bias from the leading leg.
- **Length classes** (mini, knee, midi, maxi): each sets which stride amplitude the clip
  library may use while worn. Above that, the locomotion clip switches to a
  shorter-stride variant.
- **Capes and long coat tails:** spring bones with sphere colliders on the thighs and
  spine, near LOD only. Far LODs use the bone-driven pose.

**D8 — Hair and headwear.**
These were never solved in any earlier attempt.

- **Hair classes:** short, medium, long-down, long-tied, updo, volumetric. Each hair item
  ships a **hat variant**, compressed to the skull shell, and optionally a **tucked
  variant** for hoods and high collars.
- **Hat modes:** every hat declares `full` (hair untouched) / `hatHair` (swap to the hat
  variant) / `hideTop` / `hideAll` bands. This is WoW's `HelmetGeosetVis` and Sims
  hat-hair. Hoods behave as hats and declare their hair mode too.
- **Long hair vs coats and collars:**
  - the back strands are weighted to neck, upper-spine and spring bones;
  - collars and hoods declare a `hairClearance` class;
  - long-down hair worn with a high collar switches to the over-shoulder or tucked
    variant by rule.

**D9 — A slot/class grammar with variant swaps.**
Rules are written per **class**, never per item pair, so they scale linearly with the
catalog:

- **Boots × trousers:** trousers ship a `tucked` lower-leg variant. Boot height class
  (ankle / mid-calf / knee) selects tucked or over-boot, and over-boot trousers require a
  matching shaft clearance. WoW geosets work this way, and Cyberpunk does it with a
  squish.
- **Gloves × sleeves**, **tops × waistbands** (tucked / untucked hem variants), **belts**
  (a rigid band over layer 3–4 only).
- **Lower-body silhouette:** slim / wide pants, pencil / flared skirt, dress. Outer
  garments declare a hem length and which silhouettes they accept.
- **Bounded inward squish** (Cyberpunk-style) is allowed *only* where an authored cap is
  painted, as the last resort for inner-layer vertices at an outer layer's opening.
  **Outward push is forbidden** (it inflated sleeves in World Forge).
- **Full outfits** are a first-class item type for things that genuinely can't layer
  (costumes, mascots).
- **Conflict resolution:** deterministic, by layer then slot priority. The creator UI
  shows *why* an item displaced another.

**D10 — Body-shape-aware animation.**
These corrections are computed per character at assembly from the morphed body and the
`bulk` of the worn items:

- **Arm splay:** an additive abduction on the upper arms from torso, hip and arm girth
  plus jacket or coat bulk, so arms don't sink into wide bodies. The Sims-like effect.
- **Thigh splay and stride width** from thigh girth, against heavy-body inner-thigh
  merging.
- **Stride and playback** scaled by the leg-length ratio, against foot sliding.
- **Contact clips** (hands on hips, arms crossed, sitting, carrying): per-clip contact
  targets resolved by near-LOD IK, plus a seat-height root offset.

### 7.4 Where animation-time clipping comes from, and which defense handles it

| Cause | Defense |
|---|---|
| Garment weights ≠ skin weights | D4 inheritance; checked by the build |
| Linear blend skinning collapse (elbow, shoulder, wrist twist) | D6 twist bones, loops, A-pose; P4 probe |
| Clip authored for another body shape | D10 corrections; envelope × pose test |
| Loose fabric vs legs | D3 robe mode + D7 skirt bones + length classes |
| Hair dynamics | D8 classes + spring colliders (near only) |
| Two garments with different deformation | D2 shell grammar + D4 (both inherit the *same* body weights) |

### 7.5 Verification: proving it, not hoping

Everything runs in Node, on the **same assembly code** the game uses (§4.3), and it runs
on every build in CI.

- **Envelope bodies, per age group** (§5.6):
  - the neutral body;
  - every macro-slider corner (sex × weight × muscle × age × height extremes);
  - 32 Latin-hypercube samples of all sliders;
  - the 16 approved style presets.
- **Pose suite:**
  - every 4th frame of every shipped clip;
  - explicit range-of-motion stress poses: arms up, arms crossed, hands on hips, reach
    forward, sit, crouch, kneel, run extremes, hug, carry.
- **Tests:**
  - **Penetration.** CPU-skin the assembled character for each body × pose. For each
    *visible* vertex of a lower surface (body, inner item) under an upper item's coverage,
    take the signed distance to the upper surface along its normal (BVH ray). Penetration
    > 1 mm fails. The report is a per-item heatmap.
  - **Coverage.** The same rays produce the D1 hide bands, so hide sets are an *output*
    of the test, never a hand-written claim.
  - **Shell grammar** (D2), **weight inheritance** (D4), **budget** and **binding**
    checks.
  - **Self-intersection.** Arm vs torso and thigh vs thigh, after D10 corrections.
  - **Combinations.** Every item is tested against the **worst-case neighbors**: the
    maximum-bulk item of each adjacent layer, which the shell grammar makes
    representative. All real pairs in interacting slots are tested incrementally; only
    pairs involving changed items re-run. Low-poly CPU skinning is cheap, so the full
    matrix fits overnight on this box. Dauntless runs a similar automated test over every
    armour combination.
- **Every gate proves it can fail.** Each test has a known-bad fixture and CI asserts that
  the gate fires on it. Examples:
  - a garment with its offset shrunk by 3 mm;
  - a hide flag flipped on;
  - a sleeve with hand-painted weights.

  An earlier project's gates all "passed" while broken.
- **Visual review on top**, because a clean intersection report says nothing about
  beauty:
  - per-item **contact sheets** (front, ¾, side, back × 3 bodies × 3 poses) rendered by
    Babylon headless under the shared lighting rig;
  - a framing assertion, so the character fills the frame and faces the camera;
  - the user reviews at every milestone;
  - style decisions get a blind A/B.

---

## 8. Performance: 100 unique characters on budget hardware

### 8.1 Target hardware

| Class | Example | GPU FP32 | Notes |
|---|---|---|---|
| Budget laptop | Intel UHD 620 / Iris Xe | ~440 GFLOPS (UHD 620) | the CPU is 2–3× slower single-thread than this box's i7-14700K |
| Low midrange tablet | Mali-G52 MC2 / G57 MC3, Adreno 610 | 90–270 GFLOPS | CPU 5–7× slower (estimate); fill rate goes first; thermal throttling |
| Midrange tablet | Adreno 660, Apple A13–A14 | 0.7–1.4 TFLOPS | |
| **This machine's iGPU (the gate device)** | Intel UHD 770 (Raptor Lake-S GT1, 32 EU Xe-LP) | ~0.8 TFLOPS by arithmetic (32 EU × 16 × 1.6 GHz), about **1.9× UHD 620** | selected in headless Chrome with `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/intel_icd.json` + ANGLE-Vulkan. `EXT_disjoint_timer_query_webgl2` is available, so GPU ms is measurable (verified 2026-10-12) |
| User's device: mini PC | Ryzen 7 with **Radeon 780M** (confirmed) | ~8.6 TFLOPS dual-issue | optional sanity check only |
| User's device: Galaxy Z Fold 7 | Snapdragon 8 Elite for Galaxy, Adreno 830, 120 Hz, high-DPR inner screen | flagship | optional sanity check: touch, foldable resize, thermal feel |

**Phones are first-class** (user, 2026-10-12: "phone first"). The audience (teen girls)
lives on phones and school Chromebooks.

- **Midrange phones** (Galaxy A5x class) are the tablet tier.
- **Budget phones** (Mali-G57 MC2 class) and **low-end Chromebooks** (Celeron or MediaTek)
  sit *below* the budget laptop. They get the lowest preset: ~50 visible characters, the
  lowest resolution scale, and no real shadows.

**Capability floors** (web3dsurvey): WebGL2 on 99 % of Android and 98.4 % of iOS; vertex
texture units ≥ 16 everywhere; `EXT_color_buffer_float` 99.9 %. `MAX_VERTEX_UNIFORM_VECTORS`
is only guaranteed 256 on Android, which is about 50 bones in uniform mode, so bone
matrices go in **textures**, which is Babylon's default. `OES_texture_float_linear` is only
46 % on iOS, which doesn't matter because bone and animation textures use `texelFetch`.

**WebGL2 is the baseline.** WebGPU (Safari 26, Chrome 121+ on Android 12+, about 73–86 %
of devices) is an optional extra. In Babylon it cuts draw-submission CPU through snapshot
rendering, but there is no compute skinning, so it does not reduce animation CPU.

### 8.2 What was measured (this machine, 2026-10-12)

The test ran headless Chrome with ANGLE-Vulkan on the UHD 770 iGPU. Each character had
3k tris and 30 bones, with every bone animated. The figure is CPU ms per frame for
`scene.render`:

| Variant | CPU ms |
|---|---|
| 100 characters × 6 separate parts (600 draws) | 5.9 |
| 100 merged characters (100 draws) | **3.3** (animation 1.7 · active-mesh evaluation 1.1 · render 0.5) |
| merged, bones animated directly (no glTF TransformNodes) | 2.8 |
| merged, 20 bones | 1.9 |
| merged, animation at ¼ rate, staggered | 2.6 (animation 0.7) |
| 200 characters | 9.0 (super-linear) |

- In a Node run, blending two AnimationGroups made animation about **3× more expensive**.
  65 bones cost about 2.8× what 30 bones cost.
- Scaling by single-core ratios (an estimate, not a measurement), 100 merged characters
  on Babylon's standard animation path cost about **8–10 ms on a budget laptop and
  17–23 ms on a low-end tablet**. That is too much for a 33 ms frame that must also run
  the world and the game.
- Scene flags (`performancePriority`, freezing) gained ≈ 0 here. Morph targets in texture
  mode would cost about **1.9 MB of float texture per character** (3k verts × 20 targets),
  and changing the active-influence count recompiles shaders. Baking is mandatory.

### 8.2b M0 crowd bench, measured (2026-10-13)

`npm run bench`, branch `m0-bench`. Results are in `bench/results/2026-10-13/` (JSON per
run, `summary.md`, screenshots).

**Setup:** 100 placeholder characters at exactly the §8.3 budgets (3500/1400/500/150 tris,
60/30/18 bones). Each character has unique buffers and proportions and 2-layer blended
animation.

**Paths:**
- **A:** Babylon native, with a Skeleton and AnimationGroups.
- **B:** a custom sampler writing one shared bone texture.
- **C:** B plus tiering (LOD, LOD0 cap 14, animation LOD, skeleton LOD, far-tier
  batches, blob shadows).

**Method:** p95, measured on the UHD 770 and P-cores, then scaled (CPU ×2.5 / ×5, GPU ×2
/ ×4).

| Scene / tier | A CPU → scaled | B CPU → scaled | C CPU → scaled (net of floor) | GPU scaled A / B / C | draws A / B / C |
|---|---|---|---|---|---|
| Plaza, laptop | 8.15 → **20.4 ms** | 2.03 → **5.1** | 1.14 → **2.85** (2.0) | 5.1 / 3.4 / 2.4 | 38 / 36 / 13 |
| Plaza, phone | 8.45 → **42.3** | 1.84 → **9.2** | 1.10 → **5.5** (3.8) | 6.8 / 4.8 / 4.5 | 20 / 19 / 13 |
| Meadow, laptop | 7.97 → **19.9** | 1.93 → **4.8** | 1.11 → **2.8** (1.9) | 3.8 / 2.7 / 1.5 | 52 / 52 / 6 |
| Meadow, phone | 8.97 → **44.9** | 1.72 → **8.6** | 0.97 → **4.9** (3.2) | 3.9 / 3.1 / 2.6 | 17 / 17 / 6 |

Gate limits, with 30 % headroom: CPU ≤ 4.9 ms total (anim ≤ 2.1, upload+cull ≤ 1.4,
submit ≤ 1.4); GPU ≤ 9.3 ms.

**What the numbers say:**
- **GPU is not the constraint.** Every path passes GPU at every tier with placeholder
  shading. The real material, textures and faces will eat into that, so re-measure at
  M2.
- **A → B: 4–5× less CPU.**
  - **The cause:** Babylon's per-channel animation evaluation with 2 weighted groups
    costs about 6.5–8 ms raw for 100 × 60 bones. B's typed-array sampler plus compose
    costs about 1.1 ms raw.
  - **The shared texture:** one 302 KB upload per frame (about 0.1 ms raw) replaces 100
    per-skeleton uploads.
- **B → C: another ~1.7× CPU, 3–9× fewer draws.**
  - **Animation:** about 0.06–0.21 ms raw, from LOD, staggering and skeleton LOD.
  - **Uploads:** only dirty rows are uploaded.
  - **Mesh traversal:** Babylon is handed only the selected meshes (SPEC V15). In interim
    CDP-throttled runs that took C from 4.1 to 3.1 ms. That method was later invalidated
    (SPEC B3), so treat it as the direction of the effect, not its size.
- **C passes the laptop tier** net of the engine floor; strict, only `cpu.submit` fails.
  **At phone tier C passes the total net (3.2–3.8 ≤ 4.9)**, but `cpu.submit` misses:
  about 0.4 ms raw, × 5 = 2.0 ms, against 1.4. Strict, the total also misses (4.9–5.5),
  because the floor (about 2.4 ms at ×5) is counted in it.
- **Re-graded with the adopted split** (`node bench/regrade.mjs bench/results/2026-10-13`):
  path C **passes every scaled gate in both scenes at both tiers, net of the engine floor**.
  The tightest margin is Plaza-phone upload+cull, 1.32 ms against a 1.40 limit. Real
  materials and assembly will add cost, so the LOD1 batching and WebGPU snapshot savings
  below are queued, not optional.
- **The budget split needed revising, not the total.**
  - **Animation:** C spends at most 0.9 ms of its 3 ms animation budget.
  - **Submission:** Babylon's `scene.render()` takes about 0.35 ms raw for zero characters
    and about 0.4 ms more for C's 6–13 draws.
  - **Proposed split:** total ≤ 7 ms at the tier (unchanged); animation ≤ 1.5;
    upload + cull ≤ 1.5; submission ≤ 3 net of the engine floor. The floor itself is
    booked to the world/engine share.
  - **Further submit savings, if phones stay tight:** batch LOD1 like the far tiers
    (Plaza has 6 LOD1 draws), and use WebGPU snapshot rendering where available (§8.1).

### 8.3 Budgets

| Item | Budget |
|---|---|
| Triangles per character (visible after hiding) | **LOD0 ≤ 3.5k** · LOD1 ≤ 1.4k · LOD2 ≤ 500 (color-baked proxy) · LOD3 ≤ 150 (countryside distances) or hidden. Child, toddler and infant bodies have smaller budgets, scaled by screen size |
| LOD0 population | at most the **nearest 12–16** characters, chosen by screen coverage with hysteresis. **Close-up / conversation:** up to 4 "hero" characters keep LOD0 with face bones and fingers |
| View distance (camera ranges from close city to open countryside) | **city:** many characters near the camera, so the LOD0 cap and LOD1-even-when-near rules carry the load. **countryside:** long sight lines, so most characters are LOD2/LOD3 at 5–10 Hz animation and batched draws. Fade out beyond a configurable draw distance (~250 m) |
| Total character triangles in view | ≤ 120k on tablets, ≤ 300k on laptops |
| Bones | LOD0 ≈ 60 (fingers, face, twist; GPU cost only, CPU kept low by §8.4) · LOD1 ≈ 30 · LOD2 ≈ 18 |
| Influences per vertex | 4 at LOD0, 2 at LOD1+ |
| Draw calls, characters only | near tier: 1 per character; far tier: batched (§8.4 #4). **≤ 60 on tablets, ≤ 120 on laptops**. Measured (M0, path C): 13 in Plaza-100, 6 in Meadow-100 |
| Texture memory, all characters | ≤ 32 MB: shared atlases (≈ 1–2 MB with mips), one shared bone texture (100 × 60 × 3 texels ≈ 290 KB), no per-character textures |
| Animation update rate | near 60 Hz (≤ 4 active blends) · mid 30 Hz staggered · far 10–15 Hz · off-screen 0 |
| CPU per frame (tablet, 30 fps) | character system ≤ 7 ms total · game logic ≤ 4 ms · ≥ 30 % headroom. Split: ~~animation ≤ 3 · upload+cull ≤ 2 · submission ≤ 2~~ → **adopted after M0 (2026-10-13): animation ≤ 1.5 · upload+cull ≤ 2 · submission ≤ 3.5 net of the engine floor**. Path C measured at the phone tier: 0.9 / 1.3 / 2.0 ms; the floor ≈ 2.4 ms is booked to world/engine (§8.2b). The bench's first proposal of 1.5 / 1.5 / 3 failed Plaza-phone upload+cull. Re-grade: `bench/results/2026-10-13/regrade.md` |
| GPU per frame | characters ≤ 40 % · world 40 % · post/UI ≤ 20 % · plus 30–40 % thermal margin on tablets |
| Resolution | `limitDeviceRatio` 1–1.5 on tablets, plus dynamic resolution driven by frame time |

### 8.4 Optimizations, ranked by expected payoff

1. **Bake everything at assembly** (§4.3): morphs, fit and hiding. Runtime holds a plain
   skinned mesh with no morph manager, no per-frame fitting and no recompiles.
2. **One mesh, one material, one draw call per character.** Measured: 600 → 100 draws
   saved 2.6 of 5.9 ms CPU. Babylon's `MergeMeshes` with `multiMultiMaterials` still
   issues one draw per sub-mesh, so a single draw needs a single material. That is why
   recolor is a palette and a mask, not materials.
3. **Our own animation sampler instead of Babylon's per-channel `Animation` objects.**
   - **Clips:** dense, rotation-only, quantized arrays.
   - **Per frame:** a tight typed-array loop samples, blends and composes the hierarchy,
     then writes skin matrices for every character into **one shared bone texture**, a
     single upload per frame.
   - **Shading:** a material plugin does the skinning from that texture, with a
     per-character row offset.

   Measured at M0 (§8.2b): **4–5× less character CPU than Babylon's path** (A → B),
   which spends its time on per-channel evaluation, `computeWorldMatrix` and
   per-skeleton uploads. **Clip sampling is shared** across characters in the
   same state and phase; the per-character work is only the cheap hierarchy compose.
4. **Batch the far tier.** Because skinning reads a shared texture by character index,
   several far characters' LOD2 meshes can be merged into **one draw call** (the
   character index is a vertex attribute). Batches are rebuilt only when membership
   changes. Spatial clusters keep culling useful. 80 far characters become about 5–8
   draws. **Measured:** Meadow-100 went from 52 draws (A/B) to 6 (C).
   - The alternative is Babylon's `BakedVertexAnimationManager`: baked bone matrices on
     thin instances.
   - It bakes *proportions* into the matrices, so every body needs its own bake, and it
     has no blending and no frame interpolation.
   - It suits a crowd of identical NPCs, not unique players. It stays only as a fallback
     for background NPCs on body-type buckets.
5. **Animation LOD:** update rate by distance, staggered across frames, so no frame does
   every character. Measured: animation cost −57 % at ¼ rate. The three.js community
   found every 4th frame acceptable and every 12th choppy. Cap simultaneous blends.
6. **Skeleton LOD.** Measured: 30 → 20 bones = −32 % CPU. LOD1/LOD2 weights are remapped
   to the reduced skeleton offline.
7. **Mesh LOD built offline** (meshoptimizer `simplifyWithAttributes` + our checks). Babylon's
   built-in `simplify()` drops bone weights.
8. **Cheap shading and shadows.**
   - **Shading:** Lambert plus wrap/rim, a palette lookup in the material plugin, and no
     PBR on characters.
   - **Crowd shadows:** **blob shadows** as one thin-instanced quad draw.
   - **Real shadows:** at most one low-resolution, throttled shadow map for the near tier.

     Cascaded shadow maps redraw every caster per cascade with no culling.
9. **Resolution control:** cap the device-pixel ratio and use dynamic resolution. Fill
   rate dies first on Mali-G52-class GPUs.

**Gotchas recorded for later:**

- `scene.freezeActiveMeshes()` also stops `skeleton.prepare()`, so skinned characters
  freeze. The custom path avoids this, and it gives us the scheduling hook.
- Calling `refreshBoundingInfo(true)` on skinned meshes forces CPU skinning, so use padded
  static bounds.
- Shader warm-up must cover every LOD × feature combination.

### 8.5 How performance gets measured

- **Two deterministic benchmark scenes**, matching the camera range the game needs:
  - **`Plaza-100`** (city): dense, mostly near and mid characters, with a close-up
    conversation shot;
  - **`Meadow-100`** (countryside): long sight lines, mostly far tiers.

  Both use 100 characters with a seeded mix of ages, outfits and body shapes, a scripted
  camera path, and a mix of idle, walk, talk and family-interaction states.
- **What it reports:** frame-time p50/p95/p99 and CPU per subsystem (sampler, upload,
  culling, render). Draw calls come from Babylon's engine instrumentation
  (`drawCallsCounter`), never from counting meshes; one earlier project's profiler got
  this wrong. Active vertices and triangles are reported too.
- **Where it runs: this machine, by the user's decision** (2026-10-12: "focus on what you
  can measure on this machine"). No external calibration device or cloud lab is used.
  - **GPU gate on the Intel UHD 770 iGPU** in headless Chrome (ANGLE-Vulkan, Intel ICD
    pinned), with GPU frame time read from `EXT_disjoint_timer_query_webgl2` (Babylon
    `EngineInstrumentation.gpuFrameTimeCounter`).
    - **Budget laptop tier:** UHD 770 ms × **2** ≤ the GPU budget. That is the raw-FLOPS
      ratio to UHD 620.
    - **Tablet / midrange phone tier:** UHD 770 ms × **4**. This is an estimate from
      published FP32 figures (Mali-G57 MC3 ~0.18, Adreno 610 ~0.15–0.27 TFLOPS) and is
      flagged as one.
    - **Fill rate:** runs at the target devices' real pixel counts (a 1080×2340 phone at
      the capped DPR; a 1366×768 laptop).
  - **CPU gate (revised 2026-10-13, measured):** CPU ms are measured **unthrottled** and
    multiplied by **2.5×** for the budget laptop (i7-14700K vs i5-8250U-class
    single-thread) and **5×** for the phone, tablet and low-end Chromebook tier, the same
    way GPU is scaled.
    - **Why not CDP throttling:** the original plan used CDP
      `Emulation.setCPUThrottlingRate`, and the M0 bench proved it unusable here. At
      nominal 2.5×/5× it slowed sub-ms per-frame work only **0.6–1.2×**; path A's long
      frames slowed 1.6–2.7×; and a throttled empty scene measured *faster* than raw.
      Chrome suspends the main thread in coarse slices, so short intervals mostly miss the
      pauses. A throttled gate would pass anything light (SPEC B3, V14).
      `--cdp-throttle` remains as an informational flag.
    - **Pinning:** the runner and Chrome are pinned to the **P-cores** (`taskset 0-15`;
      CPUs 16–27 are E-cores). Unpinned runs of the same scene differed by up to ~2.8×;
      pinned runs repeat within ~7 %. The load average is recorded with every run,
      because other sessions share this machine.
    - **Engine floor:** the runner also measures an `empty` scene per tier: `scene.render()`
      with zero characters, about 0.34 ms p50 raw. A "net" verdict subtracts it, because
      the world pays it regardless of characters. The strict verdict is still reported.
  - **Margin:** every scaled gate must pass with **≥ 30 % headroom**, because the ratios are
    estimates, not measurements.
  - **Regression:** the same harness runs on every change. It is fast enough on the iGPU.
    The RTX 4080 currently falls back to SwiftShader in headless Chrome, probably until the
    pending NVIDIA driver reboot. RTX numbers never count as a pass anyway.
  - **The user's devices** (780M mini PC, Fold 7) are optional sanity checks of touch,
    foldable resize and feel, never the gate.

  A SwiftShader or RTX number is never a pass.
- **When:** at **M0, before any art exists**, with placeholder characters at the planned
  budgets. If the budgets fail the scaled gates, they are revised before assets are
  authored to the wrong numbers.

---

## 9. Modularity and download size

### 9.1 What is shared (downloaded once)

| Asset | Shared by | Estimated compressed size |
|---|---|---|
| Base body (3 LODs) + region bands + cut loops | every character | ~60 KB |
| Sparse morph targets (~60 sliders, ~120 targets, LOD0 only, LOD1/2 derived) | every character | ~200–400 KB |
| Skeleton + regressor | every character | < 10 KB |
| Animation library (~100 clips, rotation-only, 30 Hz, quantized quaternions, key-reduced) | every character | ~0.6–1.2 MB |
| Shared mask/detail atlas + pattern atlas + face decal atlas (KTX2) | every item | ~300–600 KB |
| Shader + runtime code | — | ~100 KB of our code (Babylon itself excluded) |
| **Core total** | | **≤ 3 MB** |

### 9.2 What is per item (streamed on demand)

A typical low-poly garment is ~800 tris and ~600 vertices at LOD0. With meshopt
compression and quantization it costs roughly **8–12 bytes per vertex**:

- position: 16-bit;
- normal: 8-bit oct;
- UV: 16-bit;
- joints and weights: 4 × 8-bit each;
- channel: 8-bit;
- fit binding: triangle id (u16) + 2 barycentrics (u8) + local offset (3 × i8, scaled).

Indices add about 1.5 bytes per triangle, and LOD1+LOD2 add about 40 %. That puts a
typical item at **≈ 10–25 KB**. Three hundred catalog entries over ~120 meshes come to
roughly **2–3 MB in total**, and a player only ever downloads what is worn nearby.

Weights do not need to ship per item if they are re-derived from the binding at assembly
(weights = barycentric-weighted average of the bound triangle's weights). That trades ~10 bytes per
vertex for a few microseconds. Decide at M3 by measuring.

### 9.3 Why it stays small

- **One body topology**: no per-sex or per-body-type garment variants. Age groups add a
  children's catalog (estimated +30–40 % meshes), and teen–elder share one catalog.
- **Variants are data.** Colors, patterns and names are catalog rows, not meshes.
- **No per-item textures**: shared atlases plus the recolor mask.
- **Lazy, cacheable files.** Content-hashed filenames give immutable caching; a service
  worker allows offline reuse.
- **Thumbnails** are rendered offline as greyscale + mask, so the UI recolors them to the
  player's chosen colors on a canvas. This avoids one thumbnail per color.

---

## 10. Other common problems and how this plan avoids them

| Problem | Why it happens | Mitigation |
|---|---|---|
| Seams at neck, wrists, waist (lighting crease, visible crack) | Normals computed per part; separate meshes; mismatched vertex positions | One base mesh (no head/body split); garments merged into the same buffer; normals computed *after* fitting; seam vertices welded by position on merge |
| Shader compile hitch when a new character appears | A new material or define combination per character | One shared material; every feature on for all characters (no per-character `#define` variation); warm up shaders at load |
| Texture bleeding / colored fringes at mask edges | Bilinear + mip sampling across atlas cells and mask channels | Atlas cells padded and dilated; channel boundaries preferably on geometry edges (per-face channel ids); mip chain built per cell |
| LOD popping | Silhouette changes at switch distance | Switch on screen-space size with hysteresis; same silhouette classes across LODs; optional dithered cross-fade only near the switch |
| Foot sliding with varied leg lengths | Root speed authored for one stride length | Playback rate scaled by the leg-length ratio; locomotion blend by speed |
| Contact points miss with varied proportions (hands on hips, sitting, holding props) | Clips authored on one body | Body-shape corrections, seat-height root offset, near-LOD IK (§7.3 D10) |
| Combinatorial compatibility explosion | Rules written per item pair | Layers, cut lines and classes (hair class, collar class, tuck mode) let rules scale linearly |
| GC churn / leaks with many characters | Per-frame allocations; meshes and textures not disposed | Preallocated typed arrays in the animator; pooled buffers; explicit dispose with a leak test (§11 M7) |
| Pop-in when 100 players arrive | Assembly + downloads on demand | Descriptor-hash cache (IndexedDB); a placeholder silhouette tinted with the outfit's main colors until the real one is ready; assembly queue in priority order (near first) |
| Network bloat | Full appearance sent repeatedly | ≈ 150-byte descriptor sent once per player per session; diffs on change |
| Catalog drift (items that no longer pass) | Rules change after an item is approved | Every item re-validated in CI on every build |
| Verification that checks nothing | A camera on garment backs; a gate that cannot fail | Every gate has a known-bad fixture; screenshots carry a framing assertion (character bounds fill ≥ X % of the frame) |
| Engine bundle bloat | Barrel imports (`import { … } from '@babylonjs/core'`) pull in the whole engine. Measured on the template with Babylon 9.30: a **7.2 MB main chunk (1.6 MB gzip)** | Deep imports (`@babylonjs/core/Meshes/mesh`) plus explicit side-effect imports for the features used; an engine-JS budget (≈ 1 MB gzip) checked by the build |
| Tool failure misreported | Agent shells here have a hard 512 open-file limit; Rollup's `EMFILE` surfaced as "failed to resolve import" (SPEC B1) | `maxParallelFileOps: 64` (SPEC V6); read the real error before "fixing" imports |

---

## 11. Roadmap and gates

Every milestone ends at three gates:

- **Visual:** the user signs off on renders.
- **Automated:** tests, each proven able to fail.
- **Performance:** benchmark numbers, from M0 on.

| M | Deliverable | Gate to pass |
|---|---|---|
| **M0** Foundations | Style frames: S1 all-vertex-color / S2 painted face / S3 texture detail × flat / smooth shading (§5.5), on one test character, rendered in Babylon with the shared lighting rig, plus a live phone page. `Plaza-100` + `Meadow-100` benchmarks with **placeholder** characters at the planned budgets, gated on this machine (UHD 770 iGPU + unthrottled CPU × tier factor, §8.5). Tool inventory done (§3.2). ✅ Blender 5.2.2 LTS pinned + official MCP server (§3.5). ✅ Babylon 9.30 | ✅ User picked **S1 smooth** (2026-10-13). User picks a style against the approved reference. The placeholder crowd passes the *scaled* gates (§8.5) in both `Plaza-100` and `Meadow-100`, or the budgets get revised *before* any art exists |
| **M1** Bake-off + base body (✅ built 2026-10-13, awaiting sign-off) | §3.4 probes. Base body, skeleton, cut-line loops, regions, regressor, ~20 sliders, **plus a child and a toddler from the same topology** (§5.6). Three faces, three garments (tee, jeans, jacket) in walk/sit/arms-up | **User signs off on the rendered 3D body, faces and garments in motion.** Nothing below starts before this |
| **M2** Assembler v1 | Worker assembly (§4.3), shared material, recolor, one draw call per character. The shared descriptor validator (§5.7). Family inheritance (§5.6). **Phone-first creator UI** (§4.5): sliders, item pick, 3 colors | Assembly ≤ 30 ms. Descriptor round-trip. Draw calls = characters. The validator rejects every known-bad descriptor fixture |
| **M3** Garment pipeline | Build step: binding, weight inheritance, hide measurement, LODs, validator, clip-test harness, contact sheets. 20 items across all slots and layers | Every item passes every §7 test on the full envelope × pose suite. The user approves the contact sheets |
| **M4** Animation | Retargeted clip library, custom sampler, layers, animation LOD, body-shape corrections (§7.3 D10), look-at, foot/hand IK near the camera. Age-specific clips and **cross-age interactions** (carry, hold hands, hug) (§5.6) | Stress suite in motion is clean. The user approves the motion |
| **M5** Crowd performance | Mesh LODs, skeleton LOD, far LOD, blob shadows, staggered updates, hardware scaling | `Plaza-100` and `Meadow-100` pass every scaled gate (§8.5) with ≥ 30 % headroom, phone tier included |
| **M6** Content scale-up | Item spec → asset tooling; 120 meshes / 300+ catalog entries across age groups (teen–elder shared, plus the children's, toddler and infant sets); thumbnails; CI validation | All items pass; size budgets hold |
| **M7** Game integration | Public API (`createCharacter(descriptor)`, streaming, caching, dispose), docs, example scene | API documented in `SPEC.md §I`; leak test (create/dispose 10k) |

---

## 12. Risks and open questions

### Answered by the user (2026-10-12)

| # | Question | Answer | Where it landed |
|---|---|---|---|
| 1 | Is the 16-character reference (`~/projects/character-generator/public/low-poly-character-reference.png`) still the look? | **Yes** | The M0 style frames are judged against it. It is a 2D AI image, so the 3D version must be proven, not assumed |
| 2 | Children and teens? | **Yes.** The audience is teen girls, and they will want to make families | §5.6 ages and inheritance; §5.7 content rules; G8, G9 |
| 3 | Test devices? | **A Ryzen 7 mini PC and a Galaxy Z Fold 7**: "we'll have to scale the expectations accordingly" | §8.1, §8.5 scaled gates |
| 4 | Camera distance? | **Everything from close-in city scenes to open countryside** | §8.3 view-distance row; the `Plaza-100` and `Meadow-100` scenes |
| 5 | Install Blender 5.2.2 + the official MCP server? | **Yes**; nohup is fine instead of systemd | Done (§3.2, §3.5) |
| 6 | Upgrade to Babylon 9? | **Yes** | Done: 9.30.0 (`SPEC.md` §C) |
| 7 | Which Ryzen 7 is the mini PC? | **780M** | §8.1 (an optional sanity device) |
| 8 | Infants? | **Fewer customizations, but several clothing options: onesie, diaper, and several baby versions of adult clothes** | §5.6, §5.7 (a diaper as the base layer) |
| 9 | Phone-first? | **Yes** | §4.5 creator UI; §8.1 phones as first-class tiers |
| 10 | A calibration device? | **No: focus on what can be measured on this machine** | §8.5: UHD 770 iGPU + unthrottled CPU × tier factor (CDP throttling was found invalid), scaled with ≥ 30 % headroom |
| 11 | Will the user do any Blender work? | **No: every asset is agent-authored** | §3.4 weighting unchanged; there is no human artist pass in the §12 risks, so M1 sign-off and reference data carry the quality risk |
| 12 | Feet under shoes? | **"Clip feet when possible"** | §7.3 D1 applies to shoes; foot bands in §6.2; the World Forge rule is superseded (§2) |

### Answered by the style frames (2026-10-13)

- **Faces: geometric**, with S1 all vertex color and smooth normals (§5.5). Expressions stay
  on jaw and face bones (§5.5).

### Still open

None block M1.

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Agent-authored organic shapes still look "programmer-made" | high, given §2; every asset is agent-authored (user, 2026-10-12) | Reference-data projection (§5.3), the MCP iteration loop (§3.5), side-by-side renders against the approved reference, M1 sign-off before scale, blind A/B critique |
| Hero outfits exceed the LOD0 triangle budget: the M1 default outfit is 4.7k visible vs 3.5k (hands 1.1k, tee drawn under the open jacket, crop band under the tee, hair 0.5k) | certain, measured at M1 | Hand simplification (merge ring+pinky, fewer finger rings), culling lower-item faces fully under an outer layer, more lenient-but-safe crease coverage, lighter hair; re-measure in the M5 crowd gate |
| Surface-binding fit distorts loose garments at extreme sliders | medium | Robe proxy, rigid islands, multi-triangle smoothing for far-off vertices, the envelope corner suite (§7.5) |
| JS animation evaluation for 100 skeletons exceeds the CPU budget on tablets | medium | Custom sampler, animation LOD, staggering, shared clip evaluation (§8) |
| Hundreds of items make compatibility rules explode | medium | Layers give a total order; rules are per *class*, not per item pair (§7.3 D9) |
| Licence trap in reference assets or AI models | low–medium | Licence column in the §3 inventory; CC0/MIT only for anything that ships |
| One topology cannot span infant → elder | medium | P1 builds a toddler and a child from the adult topology at M1; fallback: a separate small frame for infant and toddler sharing bone names and face sliders (§5.6) |
| The family/age scope roughly doubles content (children's catalog, age-specific clips, interactions) | high (certain) | Teen–elder share one catalog; adult garments auto-fit as children's *drafts*; infant scope kept small (open question 2) |
| A modified client shows other players a forbidden look | medium | The shared validator runs server-side on every descriptor; the assembler always adds the base layer (§5.7) |
| Estimated device ratios mislead the scaled gates (no real budget device) | medium | ≥ 30 % headroom on every scaled gate; prefer the throttled-CPU measurement, which is calibrated; re-check if a real low-end device ever becomes available |

---

## 13. Sources

Research done 2026-10-12. A `?` in the text marks a claim that could not be verified.

**Clipping, layering and customization systems**

- Roblox cages: https://create.roblox.com/docs/en-us/art/modeling/cage-meshes.md
- Roblox deformer beta: https://devforum.roblox.com/t/cage-mesh-deformer-studio-beta/1196727
- Roblox AutoSkin: https://create.roblox.com/docs/en-us/avatar/automatic-skinning-transfer.md
- Roblox HSR patent: https://patents.google.com/patent/US12190427
- Roblox specs: https://create.roblox.com/docs/en-us/avatar/layered-accessories/specifications.md
- Roblox caging best practices: https://create.roblox.com/docs/en-us/avatar/layered-accessories/caging-best-practices
- Roblox artifacts: https://devforum.roblox.com/t/layered-clothing-is-a-mess/2647718
- Second Life appearance: https://wiki.secondlife.com/wiki/Avatar_Appearance
- Second Life Fitted Mesh: https://wiki.secondlife.com/wiki/Mesh/Rigging_Fitted_Mesh
- Second Life fitted-mesh project: https://modemworld.me/2013/11/20/lab-looks-to-make-mesh-garments-fit-better-with-the-fitted-mesh-project-viewer/
- Second Life mesh-body triangle counts: https://ryanschultz.com/2019/10/22/34108/
- Second Life Bento: https://community.secondlife.com/t5/Featured-News/Introducing-Project-Bento/ba-p/2987206
- Sims 4 (GDC): https://gdcvault.com/play/1022085/Innovations-in-The-Sims-4
- Sims 4 DMAP / UV_1: https://sims4studio.com/thread/10806/
- Sims 4 robe vs skin-tight color: https://sims4studio.com/thread/34246/question-color-attributes-cc
- Sims 4 MorphMaker: https://simscommunity.info/2018/07/10/learning-your-tools-the-sims-4-morphmaker/
- UMA docs: https://github.com/umasteeringgroup/UMA/tree/master/UMAProject/Assets/UMA/Docs (MeshHideAssets, NewDNASystem, ClothingConformer, MeshCombiners, UMASimpleLOD)
- MakeHuman MHCLO: https://github.com/makehumancommunity/mpfb2/blob/master/docs/fileformats/mhclo.md
- MakeHuman technical notes: https://static.makehumancommunity.org/oldsite/uncategorized/technical_notes_on_makehuman.html
- WoW customization: https://wowdev.wiki/Character_Customization
- WoW helmet geoset visibility: https://wowdev.wiki/DB/HelmetGeosetVisData
- Cyberpunk garment support: https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-creators-theory/3d-modelling/garment-support-how-does-it-work
- Character Creator AHMP: https://wiki.reallusion.com/Content_Dev:CC_AHMP_Guide
- Unreal Mutable reshape issue: https://forums.unrealengine.com/t/mutable-plugin-5-8-mesh-reshape-works-correctly-with-body-morphs-but-modifiers-clip-mesh-with-mesh-produce-geometry-artifacts-on-the-reshaped-mesh/2836644
- s&box layering: https://sbox.game/dev/doc/assets/clothing/layering-clothing.md
- GW2 outfits: https://wiki.guildwars2.com/wiki/Outfit
- Kingdom Come (GDC): https://gdcvault.com/play/1022771/Adaptive-Clothing-System-in-Kingdom
- Dauntless (GDC): https://gdcvault.com/play/1028032/Gearing-Up-Millions-of-Armor
- Character clipping protector: https://github.com/unitycoder/CharacterClippingProtector
- Babylon has no DQS: https://forum.babylonjs.com/t/dual-quaternion-skinning/10595
- DQS: https://users.cs.utah.edu/~ladislav/dq/index.html
- Skirt rig, average not sum: https://blenderartists.org/t/skirt-rig-with-drivers-not-working/675134
- VRM spring bones for Babylon: https://app.unpkg.com/babylon-vrm-loader@2.0.0/files/dist/secondary-animation/vrm-spring-bone.d.ts

**Performance**

- Babylon bones and skeletons: https://doc.babylonjs.com/features/featuresDeepDive/mesh/bonesSkeletons
- Babylon baked texture animations: https://doc.babylonjs.com/features/featuresDeepDive/animation/baked_texture_animations
- Babylon morph targets: https://doc.babylonjs.com/features/featuresDeepDive/mesh/morphTargets
- Babylon LOD: https://doc.babylonjs.com/features/featuresDeepDive/mesh/LOD
- Babylon scene optimization: https://doc.babylonjs.com/features/featuresDeepDive/scene/optimize_your_scene
- Babylon WebGPU snapshot rendering: https://doc.babylonjs.com/setup/support/webGPU/webGPUOptimization/webGPUSnapshotRendering
- Babylon cascaded shadow maps: https://doc.babylonjs.com/features/featuresDeepDive/lights/shadows_csm
- Babylon forum threads:
  - https://forum.babylonjs.com/t/animations-and-performance-tips-and-tricks/20107
  - https://forum.babylonjs.com/t/instance-skinned-geometry/63515
  - https://forum.babylonjs.com/t/merging-glb-meshes-attaching-skeleton-mangles-animations/45784
  - https://forum.babylonjs.com/t/merged-meshes-multimaterials-and-draw-call-counts/23113
  - https://forum.babylonjs.com/t/baked-animation-performance/32023
  - https://forum.babylonjs.com/t/precompile-morph-target-shaders/42103
- three.js crowds: https://discourse.threejs.org/t/optimization-of-large-amounts-100-1000-of-skinned-meshes-cpu-bottlenecks/58196
- Device capability statistics:
  - https://web3dsurvey.com/webgl2
  - https://web3dsurvey.com/webgl2/parameters/MAX_VERTEX_UNIFORM_VECTORS
  - https://web3dsurvey.com/webgl2/parameters/MAX_TEXTURE_SIZE
  - https://web3dsurvey.com/webgpu
- PlayCanvas mobile guidelines: https://developer.playcanvas.com/user-manual/optimization/guidelines/
- Unity character guidance: https://docs.unity3d.com/520/Documentation/Manual/ModelingOptimizedCharacters.html
- Assassin's Creed Unity crowds (GDC): https://gdcvault.com/play/1022141/Massive-Crowd-on-Assassin-s
- meshopt vs Draco: https://github.com/KhronosGroup/glTF/pull/1830
- KTX artist guide: https://github.com/KhronosGroup/3D-Formats-Guidelines/blob/main/KTXArtistGuide.md
- WebGPU in Chrome 121: https://developer.chrome.com/blog/new-in-webgpu-121
- Local Babylon source read: `node_modules/@babylonjs/core/Bones/skeleton.js`, `BakedVertexAnimation/vertexAnimationBaker.js`, `Morph/morphTargetManager.js`, `Meshes/meshSimplification.js`, `scene.js`
- Benchmarks run on this machine: `bench/research-2026-10-12/` (scripts and how to rerun them)

**Tools and licences**

- Blender 5.0 Python API changes: https://developer.blender.org/docs/release_notes/5.0/python_api/
- Blender 5.0 import/export changes: https://developer.blender.org/docs/release_notes/5.0/pipeline_io/
- Blender 5.2 import/export changes: https://developer.blender.org/docs/release_notes/5.2/pipeline_io/
- Blender 3.4 headless EEVEE: https://developer.blender.org/docs/release_notes/3.4/eevee/
- MPFB licence: https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md
- MPFB in closed-source use: https://static.makehumancommunity.org/mpfb/faq/use_in_closed_source.html
- MakeHuman 2020 relicense: https://static.makehumancommunity.org/oldsite/faq/what_changed_regarding_the_license_in_2020.html
- MPFB versions: https://extensions.blender.org/add-ons/mpfb/versions/
- Quaternius licence: https://quaternius.com/license.html
- Kenney: https://kenney.nl/support
- KayKit animations: https://kaylousberg.itch.io/kaykit-character-animations
- Mesh2Motion: https://github.com/Mesh2Motion/mesh2motion-app
- Mixamo licensing FAQ: https://community.adobe.com/t5/mixamo-discussions/mixamo-faq-licensing-royalties-ownership-eula-and-tos/m-p/13234775
- CMU motion capture: http://mocap.cs.cmu.edu/
- VRM 1.0 humanoid bones: https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md
- UniRig: https://github.com/VAST-AI-Research/UniRig
- TRELLIS.2: https://github.com/microsoft/TRELLIS.2
- RobustSkinWeightsTransfer: https://github.com/rin-23/RobustSkinWeightsTransferCode
- meshoptimizer gltfpack: https://github.com/zeux/meshoptimizer/blob/master/gltf/README.md
- Hunyuan3D licence: local `LICENSE` files under `~/ComfyUI/custom_nodes/ComfyUI-Hunyuan3d*`
- nvdiffrast licence: local `~/ComfyUI/build-src/nvdiffrast/LICENSE.txt`

**Blender MCP**

- Blender Lab MCP server: https://www.blender.org/lab/mcp-server/
- Blender Lab MCP source: https://projects.blender.org/lab/blender_mcp
- mcp-for-blender: https://github.com/ahujasid/mcp-for-blender
- CVE-2026-10688: https://nvd.nist.gov/vuln/detail/CVE-2026-10688
- dcc-mcp-blender: https://github.com/dcc-mcp/dcc-mcp-blender
- mpfb-mcp: https://github.com/makehumancommunity/mpfb-mcp
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp

