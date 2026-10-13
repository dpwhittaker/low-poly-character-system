import { Engine } from '@babylonjs/core/Engines/engine';
import { Scene } from '@babylonjs/core/scene';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
import { Vector3, Color4 } from '@babylonjs/core/Maths/math';
import { LoadAssetContainerAsync } from '@babylonjs/core/Loading/sceneLoader';
import type { AssetContainer } from '@babylonjs/core/assetContainer';
import type { AbstractMesh } from '@babylonjs/core/Meshes/abstractMesh';
import type { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import type { ShaderMaterial } from '@babylonjs/core/Materials/shaderMaterial';
import type { BaseTexture } from '@babylonjs/core/Materials/Textures/baseTexture';
import { CreateDisc } from '@babylonjs/core/Meshes/Builders/discBuilder';
import { DynamicTexture } from '@babylonjs/core/Materials/Textures/dynamicTexture';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import '@babylonjs/loaders/glTF/2.0';

import { STUDIO } from '../render/lighting';
import { createCharacterMaterial, setFlatShading, type TexMode } from '../render/characterMaterial';

// M0.1 style-frame viewer (SPEC §T.19, PLAN §5.5): one test character in three surface
// treatments, flat or smooth facets, under the shared lighting rig. Phone-first UI.
// URL state for screenshots: ?style=S1|S2|S3|all&shade=flat|smooth&view=body|face&spin=0|1&yaw=deg&ui=0

type StyleId = 'S1' | 'S2' | 'S3';
const STYLES: Record<StyleId, { label: string; blurb: string }> = {
  S1: { label: 'S1', blurb: 'All vertex color · features are geometry · no textures' },
  S2: { label: 'S2', blurb: 'Geometry + painted face (decal texture)' },
  S3: { label: 'S3', blurb: 'Texture detail throughout (face + cloth/hair detail)' },
};
const BASE = import.meta.env.BASE_URL + 'm0/';

interface Loaded {
  container: AssetContainer;
  meshes: AbstractMesh[];
  tris: number;
  bytes: number;
  textures: number;
}

const params = new URLSearchParams(location.search);
const state = {
  style: (params.get('style') ?? 'all') as StyleId | 'all',
  flat: (params.get('shade') ?? 'flat') !== 'smooth',
  view: (params.get('view') ?? 'body') as 'body' | 'face',
  spin: params.get('spin') === '1',
  ui: params.get('ui') !== '0',
  yaw: params.has('yaw') ? Number(params.get('yaw')) : 0,
};

export async function startStyleViewer(canvas: HTMLCanvasElement): Promise<void> {
  const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: false, antialias: true });
  engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio || 1, 2));
  const scene = new Scene(engine);
  const bg = Color3.FromHexString(STUDIO.background);
  scene.clearColor = new Color4(bg.r, bg.g, bg.b, 1);

  const camera = new ArcRotateCamera('cam', Math.PI / 2, Math.PI / 2.15, 3.4, new Vector3(0, 0.85, 0), scene);
  camera.fov = 0.45;
  camera.minZ = 0.05;
  camera.lowerRadiusLimit = 0.35;
  camera.upperRadiusLimit = 9;
  camera.wheelDeltaPercentage = 0.02;
  camera.pinchDeltaPercentage = 0.004;
  camera.attachControl(canvas, true);

  // soft contact shadow under each character (radial gradient on a disc)
  const shadowTex = new DynamicTexture('contact', { width: 128, height: 128 }, scene, false);
  const ctx = shadowTex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  g.addColorStop(0, 'rgba(0,0,0,0.35)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  shadowTex.update();
  shadowTex.hasAlpha = true;
  const shadowMat = new StandardMaterial('contactMat', scene);
  shadowMat.diffuseTexture = shadowTex;
  shadowMat.useAlphaFromDiffuseTexture = true;
  shadowMat.disableLighting = true;
  shadowMat.emissiveColor = new Color3(1, 1, 1);

  const materials: ShaderMaterial[] = [];
  const loaded = {} as Record<StyleId, Loaded>;
  for (const id of Object.keys(STYLES) as StyleId[]) {
    const url = `${BASE}${id}.glb`;
    const bytes = Number((await fetch(url, { method: 'HEAD' })).headers.get('content-length') ?? 0);
    const container = await LoadAssetContainerAsync(url, scene);
    let tris = 0;
    const textures = new Set<BaseTexture>();
    const meshes = container.meshes.filter((m) => m.getTotalVertices() > 0);
    for (const m of meshes) {
      const extras = (m.metadata?.gltf?.extras ?? {}) as { texMode?: TexMode };
      const texMode: TexMode = extras.texMode ?? 'none';
      const src = m.material as PBRMaterial | null;
      const tex = texMode !== 'none' ? (src?.albedoTexture ?? null) : null;
      if (tex) textures.add(tex);
      const mat = createCharacterMaterial(`${id}_${m.name}`, scene, { rig: STUDIO, texture: tex, texMode });
      materials.push(mat);
      m.material = mat;
      // COLOR_0.a is baked AO, not opacity. Left as vertex alpha, Babylon draws the mesh in
      // the transparent pass with no depth write: inner faces then cover the outer skin
      // (dark shards) and eyeballs show through the lids (first M0 render, 2026-10-12).
      m.hasVertexAlpha = false;
      tris += (m.getTotalIndices() || m.getTotalVertices()) / 3;
    }
    const disc = CreateDisc(`shadow_${id}`, { radius: 0.45, tessellation: 32 }, scene);
    disc.rotation.x = Math.PI / 2;
    disc.position.y = 0.002;
    disc.material = shadowMat;
    container.meshes.push(disc);
    loaded[id] = { container, meshes, tris: Math.round(tris), bytes, textures: textures.size };
  }

  const root = (id: StyleId) => loaded[id].container.meshes.find((m) => m.name === '__root__')!;
  const disc = (id: StyleId) => loaded[id].container.meshes.find((m) => m.name === `shadow_${id}`)!;
  for (const id of Object.keys(STYLES) as StyleId[]) loaded[id].container.addAllToScene();

  const info = document.createElement('div');

  function apply(): void {
    const ids = Object.keys(STYLES) as StyleId[];
    const shown = state.style === 'all' ? ids : [state.style];
    ids.forEach((id) => {
      const on = shown.includes(id);
      // camera looks down -Z, so screen-right is world -X: negate to read S1 → S3 left to right
      const x = state.style === 'all' ? -(ids.indexOf(id) - 1) * 0.95 : 0;
      root(id).setEnabled(on);
      disc(id).setEnabled(on);
      root(id).position.x = x;
      disc(id).position.x = x;
    });
    materials.forEach((m) => setFlatShading(m, state.flat));
    const multi = state.style === 'all';
    // fov is vertical; on portrait screens width is the limit, so back off accordingly
    const portrait = Math.min(1, engine.getAspectRatio(camera) / 0.75);
    if (state.view === 'face') {
      camera.target = new Vector3(0, 1.5, 0);
      camera.radius = (multi ? 2.6 : 0.85) / portrait;
    } else {
      // fit the 1.67 m figure vertically at fov 0.45, with headroom for portrait phones
      camera.target = new Vector3(0, 0.86, 0);
      camera.radius = multi ? 5.4 : 4.4;
    }
    camera.alpha = Math.PI / 2 + (state.yaw * Math.PI) / 180;
    camera.beta = Math.PI / 2.1;
    camera.useAutoRotationBehavior = state.spin;
    const one = state.style === 'all' ? null : loaded[state.style];
    info.textContent = one
      ? `${STYLES[state.style as StyleId].blurb} · ${one.tris.toLocaleString()} tris · ${(one.bytes / 1024).toFixed(0)} KB · ${one.textures} texture${one.textures === 1 ? '' : 's'}`
      : 'S1 all vertex color  ·  S2 painted face  ·  S3 texture detail';
    syncButtons();
  }

  const buttons: Array<{ el: HTMLButtonElement; active: () => boolean }> = [];
  function syncButtons(): void {
    for (const b of buttons) b.el.classList.toggle('on', b.active());
  }
  function row(label: string, items: Array<[string, () => void, () => boolean]>): HTMLElement {
    const r = document.createElement('div');
    r.className = 'row';
    const l = document.createElement('span');
    l.textContent = label;
    r.appendChild(l);
    for (const [text, act, active] of items) {
      const b = document.createElement('button');
      b.textContent = text;
      b.onclick = () => { act(); apply(); };
      buttons.push({ el: b, active });
      r.appendChild(b);
    }
    return r;
  }

  if (state.ui) {
    const style = document.createElement('style');
    style.textContent = `
      #sheet { position: fixed; left: 0; right: 0; bottom: 0; padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
        background: rgba(250,250,252,0.92); backdrop-filter: blur(8px); border-radius: 16px 16px 0 0;
        font: 14px/1.3 system-ui, sans-serif; color: #222; box-shadow: 0 -2px 16px rgba(0,0,0,0.12); }
      #sheet .row { display: flex; align-items: center; gap: 6px; margin: 6px 0; flex-wrap: wrap; }
      #sheet .row span { width: 64px; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #666; }
      #sheet button { min-height: 44px; min-width: 52px; padding: 0 14px; border-radius: 22px; border: 1px solid #ccc;
        background: #fff; font: inherit; color: #222; }
      #sheet button.on { background: #2f5fd0; border-color: #2f5fd0; color: #fff; }
      #sheet .info { font-size: 12px; color: #555; margin-top: 4px; }
      #ref { position: fixed; top: 10px; left: 10px; width: 96px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,.25);
        transition: width .2s; cursor: zoom-in; }
      #ref.big { width: min(92vw, 560px); cursor: zoom-out; }
      @media (min-width: 900px) { #sheet { left: auto; top: 10px; bottom: 10px; width: 330px; border-radius: 16px; right: 10px; } }
    `;
    document.head.appendChild(style);
    const sheet = document.createElement('div');
    sheet.id = 'sheet';
    sheet.appendChild(row('Style', [
      ['S1', () => (state.style = 'S1'), () => state.style === 'S1'],
      ['S2', () => (state.style = 'S2'), () => state.style === 'S2'],
      ['S3', () => (state.style = 'S3'), () => state.style === 'S3'],
      ['All', () => (state.style = 'all'), () => state.style === 'all'],
    ]));
    sheet.appendChild(row('Facets', [
      ['Flat', () => (state.flat = true), () => state.flat],
      ['Smooth', () => (state.flat = false), () => !state.flat],
    ]));
    sheet.appendChild(row('View', [
      ['Body', () => (state.view = 'body'), () => state.view === 'body'],
      ['Face', () => (state.view = 'face'), () => state.view === 'face'],
      ['Spin', () => (state.spin = !state.spin), () => state.spin],
    ]));
    info.className = 'info';
    sheet.appendChild(info);
    document.body.appendChild(sheet);
    const ref = document.createElement('img');
    ref.id = 'ref';
    ref.src = `${BASE}reference.webp`;
    ref.alt = 'Approved reference';
    ref.onclick = () => ref.classList.toggle('big');
    document.body.appendChild(ref);
  }

  apply();
  engine.runRenderLoop(() => scene.render());
  window.addEventListener('resize', () => { engine.resize(); apply(); }); // foldable cover ↔ inner
  await scene.whenReadyAsync();
  (window as unknown as { __ready: boolean }).__ready = true;
}
