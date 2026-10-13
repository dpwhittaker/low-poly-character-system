// M0 crowd bench page (PLAN §8.5). Query params:
//   scene=plaza|meadow|single  path=A|B|C  frames=600  warmup=120  seed=1234
//   shadows=1 (path C blob shadows)  drain=24 (extra frames to collect late GPU timer results)
// Writes the result object to `window.__benchResult` for bench/run.mjs.

import { Engine, Scene, FreeCamera, HemisphericLight, Vector3, Color3, Color4, MeshBuilder, StandardMaterial, SceneInstrumentation, EngineInstrumentation } from '@babylonjs/core';
import { makeScene, type SceneName } from './scenes.ts';
import { buildChars, type PathRuntime } from './common.ts';
import { createPathA } from './pathA.ts';
import { createPathB } from './pathB.ts';
import { createPathC } from './pathC.ts';
import { summarize, type Series } from './stats.ts';

declare global { interface Window { __benchResult?: unknown; __benchError?: string } }

const q = new URLSearchParams(location.search);
const sceneName = (q.get('scene') ?? 'plaza') as SceneName;
const pathName = (q.get('path') ?? 'B') as 'A' | 'B' | 'C';
const FRAMES = +(q.get('frames') ?? 600);
const WARMUP = +(q.get('warmup') ?? 120);
const DRAIN = +(q.get('drain') ?? 24);
const SEED = +(q.get('seed') ?? 1234);
const SHADOWS = q.get('shadows') !== '0';
const HOLD = q.has('hold') ? +(q.get('hold') as string) : -1; // freeze the camera at this fraction of the path (screenshots)

async function run() {
  const canvas = document.getElementById('c') as HTMLCanvasElement;
  const engine = new Engine(canvas, false, { preserveDrawingBuffer: false, stencil: false, antialias: false, powerPreference: 'high-performance', limitDeviceRatio: 1.5 }, true);
  const scene = new Scene(engine);
  scene.clearColor = new Color4(0.62, 0.74, 0.86, 1);
  scene.skipPointerMovePicking = true;
  scene.useConstantAnimationDeltaTime = true;
  const spec = makeScene(sceneName, SEED);
  const cam = new FreeCamera('cam', new Vector3(0, 2, -5), scene);
  cam.fov = 0.9;
  cam.minZ = 0.1;
  cam.maxZ = 1500;
  new HemisphericLight('sky', new Vector3(0.3, 1, 0.2), scene); // lights the ground only; character shaders carry their own light
  if (spec.groundSize > 0) {
    const g = MeshBuilder.CreateGround('ground', { width: spec.groundSize, height: spec.groundSize }, scene);
    const gm = new StandardMaterial('gm', scene);
    gm.diffuseColor = spec.name === 'meadow' ? new Color3(0.38, 0.52, 0.28) : new Color3(0.55, 0.53, 0.5);
    gm.specularColor = Color3.Black();
    g.material = gm;
    g.isPickable = false;
    gm.freeze();
    g.freezeWorldMatrix();
  }
  const tSetup0 = performance.now();
  const chars = buildChars(spec, pathName === 'C' ? [0, 1, 2, 3] : [0]);
  let rt: PathRuntime;
  if (chars.length === 0) rt = { name: pathName, step: () => ({ animMs: 0, uploadCullMs: 0, uploadMs: 0 }), stats: () => ({ visibleChars: 0, visibleTris: 0, lod: [0, 0, 0, 0], composed: 0 }) };
  else if (pathName === 'A') rt = createPathA(scene, spec, chars);
  else if (pathName === 'B') rt = createPathB(scene, spec, chars);
  else rt = createPathC(scene, spec, chars, { shadows: SHADOWS, camera: cam });
  await scene.whenReadyAsync();
  const setupMs = performance.now() - tSetup0;

  const si = new SceneInstrumentation(scene);
  si.captureActiveMeshesEvaluationTime = true;
  si.captureRenderTime = true;
  si.captureAnimationsTime = true;
  const ei = new EngineInstrumentation(engine);
  ei.captureGPUFrameTime = true;

  const gl = (engine as unknown as { _gl: WebGL2RenderingContext })._gl;
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer = dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : 'unknown';

  const S: Record<string, number[]> = { cpuChar: [], anim: [], uploadCull: [], upload: [], submit: [], renderWall: [], draws: [], activeTris: [], visibleTris: [], visibleChars: [], composed: [], gpu: [], lod0: [], lod1: [], lod2: [], lod3: [] };
  const perSegment: Record<string, Record<string, number[]>> = {};
  let gpuCount = ei.gpuFrameTimeCounter.count;
  let frame = 0;
  const total = WARMUP + FRAMES + DRAIN;

  await new Promise<void>((resolve) => {
    engine.runRenderLoop(() => {
      const mf = frame - WARMUP; // measurement frame index (camera path)
      const pose = spec.camera(HOLD >= 0 ? HOLD * FRAMES : Math.max(0, Math.min(FRAMES - 1, mf)), FRAMES);
      cam.position.set(pose.pos[0], pose.pos[1], pose.pos[2]);
      cam.setTarget(new Vector3(pose.target[0], pose.target[1], pose.target[2]));
      cam.getViewMatrix(true);
      const time = frame / 60;
      const t0 = performance.now();
      const st = rt.step(frame, time, cam);
      const t1 = performance.now();
      scene.render();
      const t2 = performance.now();
      const measuring = mf >= 0 && mf < FRAMES;
      if (measuring) {
        const isA = rt.name === 'A';
        const fs = rt.stats();
        const rec: Record<string, number> = {
          cpuChar: (t1 - t0) + (t2 - t1),
          anim: isA ? si.animationsTimeCounter.current : st.animMs,
          uploadCull: isA ? si.activeMeshesEvaluationTimeCounter.current : st.uploadCullMs,
          upload: st.uploadMs,
          submit: isA ? si.renderTimeCounter.current : t2 - t1,
          renderWall: t2 - t1,
          draws: si.drawCallsCounter.current,
          activeTris: scene.getActiveIndices() / 3,
          visibleTris: fs.visibleTris,
          visibleChars: fs.visibleChars,
          composed: fs.composed,
          lod0: fs.lod[0], lod1: fs.lod[1], lod2: fs.lod[2], lod3: fs.lod[3],
        };
        const seg = spec.segments.find((s) => mf / FRAMES >= s.from && mf / FRAMES < s.to)?.name ?? 'all';
        perSegment[seg] ??= {};
        for (const [k, v] of Object.entries(rec)) { S[k].push(v); (perSegment[seg][k] ??= []).push(v); }
      }
      if (mf >= 0 && ei.gpuFrameTimeCounter.count !== gpuCount) {
        gpuCount = ei.gpuFrameTimeCounter.count;
        if (mf < FRAMES + DRAIN) S.gpu.push(ei.gpuFrameTimeCounter.current * 1e-6);
      }
      frame++;
      if (frame >= total) { engine.stopRenderLoop(); resolve(); }
    });
  });

  const summary: Record<string, Series> = {};
  for (const [k, v] of Object.entries(S)) summary[k] = summarize(v);
  const segments: Record<string, Record<string, Series>> = {};
  for (const [name, rec] of Object.entries(perSegment)) {
    segments[name] = {};
    for (const [k, v] of Object.entries(rec)) segments[name][k] = summarize(v);
  }
  window.__benchResult = {
    schema: 1,
    scene: spec.name, path: rt.name, seed: SEED, frames: FRAMES, warmup: WARMUP,
    characters: chars.length,
    viewport: { cssW: innerWidth, cssH: innerHeight, dpr: devicePixelRatio, renderW: engine.getRenderWidth(), renderH: engine.getRenderHeight() },
    renderer, timerQuery: !!engine.getCaps().timerQuery, crossOriginIsolated: self.crossOriginIsolated,
    setupMs,
    summary, segments,
  };
}

run().catch((e) => { window.__benchError = String(e?.stack ?? e); console.error(e); });
