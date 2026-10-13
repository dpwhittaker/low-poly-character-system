import { Engine } from '@babylonjs/core/Engines/engine';
import { Scene } from '@babylonjs/core/scene';
import { ArcRotateCamera } from '@babylonjs/core/Cameras/arcRotateCamera';
import { Vector3, Color4, Color3 } from '@babylonjs/core/Maths/math';
import { Space } from '@babylonjs/core/Maths/math.axis';
import { CreateDisc } from '@babylonjs/core/Meshes/Builders/discBuilder';
import { DynamicTexture } from '@babylonjs/core/Materials/Textures/dynamicTexture';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import type { ShaderMaterial } from '@babylonjs/core/Materials/shaderMaterial';
import type { Mesh } from '@babylonjs/core/Meshes/mesh';

import { STUDIO } from '../render/lighting';
import { createBodyMaterial, setPalette, setFlatShading, PALETTE_SIZE } from '../render/characterMaterial';
import { loadBodyPack, type BodyPack } from '../character/bodyPack';
import { bakeBody, boneHeads, type Descriptor } from '../character/assemble';
import { ageMacro, DEFAULT_MACRO } from '../character/macro';
import { buildCharacter, loadRestSkeleton, updateCharacter, type CharacterParts } from '../character/babylonCharacter';

// M1 creator preview (SPEC T22/T27, PLAN §4.5): the real assembler path — CPU morph bake +
// skeleton fit — behind phone-first sliders. URL state for screenshots:
//   ?years=&gender=&weight=&muscle=&height=&cup=&af=&as=&ca=&s.<slider>=&skin=&view=body|face
//   &yaw=&spin=1&ui=0&shade=flat|smooth&pose=rest|relaxed|armsup&lineup=ages|genders|faces

const BASE = import.meta.env.BASE_URL + 'm1/';
const SKIN_TONES = ['F2D3BE', 'E8BB9C', 'D9A07E', 'C68863', 'A86B4A', '8A5236', '6B3E28', '4C2B1D'];
const EYE_COLORS = ['4E7A5E', '5B4030', '3F6A9A', '7A6A3A', '2E2420'];

interface Look {
  years: number; gender: number; weight: number; muscle: number; height: number; cup: number;
  race: { african: number; asian: number; caucasian: number };
  sliders: Record<string, number>;
  skin: number; eyes: number;
}

const params = new URLSearchParams(location.search);
const num = (k: string, d: number) => (params.has(k) ? Number(params.get(k)) : d);

function lookFromParams(): Look {
  const sliders: Record<string, number> = {};
  for (const [k, v] of params) if (k.startsWith('s.')) sliders[k.slice(2)] = Number(v);
  return {
    years: num('years', 16), gender: num('gender', 0.1), weight: num('weight', 0.5), muscle: num('muscle', 0.5),
    height: num('height', 0.5), cup: num('cup', 0.5),
    race: { african: num('af', 0.33), asian: num('as', 0.33), caucasian: num('ca', 0.34) },
    sliders, skin: num('skin', 2), eyes: num('eyes', 0),
  };
}

const ui = {
  view: (params.get('view') ?? 'body') as 'body' | 'face',
  yaw: num('yaw', 0),
  spin: params.get('spin') === '1',
  show: params.get('ui') !== '0',
  flat: params.get('shade') === 'flat',
  pose: (params.get('pose') ?? 'rest') as 'rest' | 'relaxed' | 'armsup',
  lineup: params.get('lineup') as null | 'ages' | 'genders' | 'faces',
  debug: params.get('debug') as null | 'bands',
  wire: params.get('wire') === '1',
};

/** Content rules (PLAN §5.7): no sex-dimorphism body sliders under 13; capped cup range. */
function descriptor(pack: BodyPack, l: Look): Descriptor {
  const child = l.years < 13;
  const age = ageMacro(l.years, l.gender, pack.meta.ageCurve);
  return {
    macro: {
      ...DEFAULT_MACRO, gender: l.gender, age, weight: l.weight, muscle: child ? 0.5 : l.muscle, height: l.height,
      cupsize: child ? 0.5 : Math.min(0.65, Math.max(0.3, l.cup)), firmness: 0.5, race: l.race,
    },
    sliders: l.sliders,
    style: 1,
  };
}

const srgbToLin = (hex: string) => [0, 2, 4].map((i) => Math.pow(parseInt(hex.slice(i, i + 2), 16) / 255, 2.2));

function palette(pack: BodyPack, l: Look): Float32Array {
  const p = new Float32Array(PALETTE_SIZE * 3);
  pack.meta.paletteSrgb.forEach((hex, i) => p.set(srgbToLin(hex), i * 3));
  const skin = srgbToLin(SKIN_TONES[l.skin] ?? SKIN_TONES[2]);
  p.set(skin, 0);
  p.set([skin[0] * 0.78, skin[1] * 0.42, skin[2] * 0.45], 3 * pack.meta.regions.indexOf('lips'));
  p.set(srgbToLin(EYE_COLORS[l.eyes] ?? EYE_COLORS[0]), 3 * pack.meta.regions.indexOf('iris'));
  return p;
}

function bandPalette(): Float32Array {
  const p = new Float32Array(PALETTE_SIZE * 3);
  for (let i = 0; i < PALETTE_SIZE; i++) {
    const h = (i * 0.618034) % 1, l = 0.45 + 0.25 * (i % 3) / 2;
    const c = Color3.FromHSV(h * 360, 0.55, l);
    p.set([c.r, c.g, c.b].map((x) => Math.pow(x, 2.2)), i * 3);
  }
  p.set([0.9, 0.9, 0.9], (PALETTE_SIZE - 1) * 3);
  return p;
}

interface Char { look: Look; parts: CharacterParts; mat: ShaderMaterial; height: number; headY: number; disc: Mesh }

export async function startCreator(canvas: HTMLCanvasElement): Promise<void> {
  const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: false, antialias: true });
  engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio || 1, 2));
  const scene = new Scene(engine);
  const bg = Color3.FromHexString(STUDIO.background);
  scene.clearColor = new Color4(bg.r, bg.g, bg.b, 1);
  const camera = new ArcRotateCamera('cam', Math.PI / 2, Math.PI / 2.1, 4, new Vector3(0, 0.85, 0), scene);
  camera.fov = 0.45; camera.minZ = 0.05; camera.lowerRadiusLimit = 0.3; camera.upperRadiusLimit = 14;
  camera.wheelDeltaPercentage = 0.02; camera.pinchDeltaPercentage = 0.004;
  camera.attachControl(canvas, true);

  const shadowTex = new DynamicTexture('contact', { width: 128, height: 128 }, scene, false);
  const ctx = shadowTex.getContext() as CanvasRenderingContext2D;
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 64);
  grad.addColorStop(0, 'rgba(0,0,0,0.35)'); grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad; ctx.fillRect(0, 0, 128, 128); shadowTex.update(); shadowTex.hasAlpha = true;
  const shadowMat = new StandardMaterial('contactMat', scene);
  shadowMat.diffuseTexture = shadowTex; shadowMat.useAlphaFromDiffuseTexture = true;
  shadowMat.disableLighting = true; shadowMat.emissiveColor = new Color3(1, 1, 1);

  const [pack, rest] = await Promise.all([loadBodyPack(BASE), loadRestSkeleton(`${BASE}skeleton.glb`)]);

  const chars: Char[] = [];
  function addChar(look: Look): Char {
    const baked = bakeBody(pack, descriptor(pack, look));
    const mat = createBodyMaterial(`body${chars.length}`, scene, STUDIO);
    const parts = buildCharacter(scene, pack, rest, baked, mat, `char${chars.length}`);
    const disc = CreateDisc(`shadow${chars.length}`, { radius: 0.4, tessellation: 32 }, scene);
    disc.rotation.x = Math.PI / 2; disc.position.y = 0.002; disc.material = shadowMat;
    const c: Char = { look, parts, mat, height: 0, headY: 0, disc };
    if (ui.debug === 'bands') bandDebug(c);
    refresh(c, baked);
    chars.push(c);
    return c;
  }
  let lastBakeMs = 0;
  function refresh(c: Char, baked = bakeBody(pack, descriptor(pack, c.look))): void {
    const t0 = performance.now();
    updateCharacter(c.parts, pack, rest, baked);
    lastBakeMs = performance.now() - t0;
    setPalette(c.mat, ui.debug === 'bands' ? bandPalette() : palette(pack, c.look));
    setFlatShading(c.mat, ui.flat);
    const heads = boneHeads(pack, baked.joints, baked.groundLift);
    const hi = pack.meta.bones.findIndex((b) => b.name === 'head');
    c.headY = heads[hi * 3 + 1];
    let top = 0;
    for (let i = 1; i < baked.src.length; i += 3) top = Math.max(top, baked.src[i] + baked.groundLift);
    c.height = top;
    c.disc.scaling.setAll(Math.max(0.35, c.height / 1.65));
    applyPose(c);
  }

  /** Debug: one flat color per band (cut-line check). Unindexes the mesh so bands stay crisp. */
  function bandDebug(c: Char): void {
    const m = c.parts.mesh;
    m.convertToFlatShadedMesh();
    const region = new Float32Array(m.getTotalVertices());
    for (let t = 0; t < region.length / 3; t++) {
      const b = pack.triBand[t];
      region.fill(b === 255 ? PALETTE_SIZE - 1 : b % (PALETTE_SIZE - 1), t * 3, t * 3 + 3);
    }
    m.setVerticesData('region', region, false, 1);
    if (ui.wire) {
      const w = m.clone(`${m.name}_wire`, m.parent);
      const wm = new StandardMaterial('wire', scene);
      wm.wireframe = true; wm.disableLighting = true; wm.emissiveColor = new Color3(0.05, 0.05, 0.08);
      w.material = wm; w.skeleton = m.skeleton;
    }
  }

  function applyPose(c: Char): void {
    c.parts.skeleton.returnToRest();
    if (ui.pose === 'rest') return;
    const b = (n: string) => c.parts.bones.get(n)!;
    const m = c.parts.mesh;
    for (const [s, sign] of [['l', 1], ['r', -1]] as const) {
      if (ui.pose === 'relaxed') {
        b(`upperarm_${s}`).rotate(new Vector3(0, 0, 1), sign * 0.62, Space.WORLD, m);
        b(`lowerarm_${s}`).rotate(new Vector3(1, 0, 0), -0.35, Space.WORLD, m);
      } else {
        b(`upperarm_${s}`).rotate(new Vector3(0, 0, 1), -sign * 1.9, Space.WORLD, m);
      }
    }
  }

  // ---- characters: one editable, or a review line-up
  const base = lookFromParams();
  if (ui.lineup === 'ages') {
    for (const years of [1, 3, 6, 10, 14, 18, 35, 70]) addChar({ ...base, years });
  } else if (ui.lineup === 'genders') {
    for (const gender of [0, 0.25, 0.5, 0.75, 1]) addChar({ ...base, years: 25, gender });
  } else if (ui.lineup === 'faces') {
    addChar({ ...base, skin: 1, sliders: { faceRound: 0.6, eyeSize: 0.5, noseTip: 0.5, cheeks: 0.4, smile: 0.4 } });
    addChar({ ...base, skin: 4, race: { african: 0.8, asian: 0.1, caucasian: 0.1 }, eyes: 1,
      sliders: { faceSquare: 0.4, lips: 0.7, noseWidth: 0.5, jawWidth: 0.3, eyeTilt: 0.3 } });
    addChar({ ...base, skin: 2, race: { african: 0.1, asian: 0.8, caucasian: 0.1 }, eyes: 4,
      sliders: { faceRound: -0.3, eyeTilt: 0.6, noseLength: -0.4, chinLength: 0.4, browHeight: 0.4 } });
  } else {
    addChar(base);
  }

  function layout(): void {
    let x = 0;
    const widths = chars.map((c) => Math.max(0.42, c.height * 0.36));
    const total = widths.reduce((a, b) => a + b, 0);
    chars.forEach((c, i) => {
      const cx = -(x + widths[i] / 2 - total / 2); // camera looks down -Z: screen-right is world -X
      c.parts.root.position.x = cx; c.disc.position.x = cx;
      x += widths[i];
    });
    const tallest = Math.max(...chars.map((c) => c.height));
    const portrait = Math.min(1, engine.getAspectRatio(camera) / 0.75);
    if (ui.view === 'face') {
      const headY = chars.reduce((a, c) => a + c.headY, 0) / chars.length;
      camera.target = new Vector3(0, headY + 0.09 * (tallest / 1.65), 0);
      camera.radius = Math.max(0.8 * (tallest / 1.65), total * 1.1) / portrait;
    } else {
      camera.target = new Vector3(0, tallest * 0.52, 0);
      const fitH = tallest * 1.25 / (2 * Math.tan(camera.fov / 2));
      const fitW = total * 1.1 / (2 * Math.tan(camera.fov / 2) * engine.getAspectRatio(camera));
      camera.radius = Math.max(fitH, fitW, 1.2);
    }
    camera.alpha = Math.PI / 2 + (ui.yaw * Math.PI) / 180;
    camera.beta = Math.PI / 2.08;
    camera.useAutoRotationBehavior = ui.spin;
  }

  // ---- phone-first bottom sheet
  const info = document.createElement('div');
  info.className = 'info';
  function setInfo(): void {
    const c = chars[0];
    info.textContent = `${pack.meta.counts.tris.toLocaleString()} tris · ${pack.meta.bones.length} bones · ` +
      `${c.height.toFixed(2)} m · bake ${lastBakeMs.toFixed(1)} ms`;
  }
  if (ui.show && !ui.lineup) buildSheet();

  function buildSheet(): void {
    const c = chars[0];
    const style = document.createElement('style');
    style.textContent = `
      #sheet { position: fixed; left: 0; right: 0; bottom: 0; max-height: 46vh; overflow-y: auto;
        padding: 8px 12px calc(10px + env(safe-area-inset-bottom)); background: rgba(250,250,252,0.94);
        backdrop-filter: blur(8px); border-radius: 16px 16px 0 0; font: 14px/1.3 system-ui, sans-serif; color: #222;
        box-shadow: 0 -2px 16px rgba(0,0,0,0.12); }
      #sheet .tabs { display: flex; gap: 6px; overflow-x: auto; position: sticky; top: -8px; padding: 6px 0;
        background: rgba(250,250,252,0.96); z-index: 1; }
      #sheet button { min-height: 40px; min-width: 48px; padding: 0 12px; border-radius: 20px; border: 1px solid #ccc;
        background: #fff; font: inherit; color: #222; white-space: nowrap; }
      #sheet button.on { background: #2f5fd0; border-color: #2f5fd0; color: #fff; }
      #sheet label { display: grid; grid-template-columns: 96px 1fr 38px; align-items: center; gap: 8px; margin: 4px 0; font-size: 13px; }
      #sheet input[type=range] { width: 100%; height: 32px; accent-color: #2f5fd0; }
      #sheet .val { font-variant-numeric: tabular-nums; color: #666; text-align: right; font-size: 12px; }
      #sheet .swatches { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0; }
      #sheet .sw { width: 36px; height: 36px; border-radius: 18px; border: 2px solid #fff; box-shadow: 0 0 0 1px #bbb; padding: 0; min-width: 0; }
      #sheet .sw.on { box-shadow: 0 0 0 3px #2f5fd0; }
      #sheet .info { font-size: 12px; color: #555; margin-top: 6px; }
      @media (min-width: 900px) { #sheet { left: auto; top: 10px; bottom: 10px; width: 360px; max-height: none; border-radius: 16px; right: 10px; } }`;
    document.head.appendChild(style);
    const sheet = document.createElement('div');
    sheet.id = 'sheet';
    const tabs = document.createElement('div');
    tabs.className = 'tabs';
    const body = document.createElement('div');
    sheet.append(tabs, body, info);
    document.body.appendChild(sheet);

    let pending = false;
    const rebake = () => {
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; refresh(c); layout(); setInfo(); });
    };
    const range = (label: string, min: number, max: number, step: number, get: () => number, set: (v: number) => void,
      fmt = (v: number) => v.toFixed(2)) => {
      const l = document.createElement('label');
      const span = document.createElement('span'); span.textContent = label;
      const input = document.createElement('input');
      input.type = 'range'; input.min = String(min); input.max = String(max); input.step = String(step); input.value = String(get());
      const val = document.createElement('span'); val.className = 'val'; val.textContent = fmt(get());
      input.oninput = () => { set(Number(input.value)); val.textContent = fmt(Number(input.value)); rebake(); };
      l.append(span, input, val);
      return l;
    };
    const swatches = (colors: string[], get: () => number, set: (i: number) => void) => {
      const row = document.createElement('div'); row.className = 'swatches';
      colors.forEach((hex, i) => {
        const b = document.createElement('button'); b.className = 'sw' + (get() === i ? ' on' : '');
        b.style.background = '#' + hex;
        b.onclick = () => { set(i); row.querySelectorAll('.sw').forEach((x, j) => x.classList.toggle('on', j === i)); rebake(); };
        row.appendChild(b);
      });
      return row;
    };
    const L = c.look;
    const pages: Record<string, () => HTMLElement[]> = {
      Age: () => {
        const presets = document.createElement('div'); presets.className = 'swatches';
        for (const [name, y] of [['Toddler', 2], ['Child', 7], ['Teen', 15], ['Adult', 30], ['Elder', 72]] as const) {
          const b = document.createElement('button'); b.textContent = name;
          b.onclick = () => { L.years = y; show('Age'); rebake(); };
          presets.appendChild(b);
        }
        return [presets, range('Age (years)', 1, 90, 1, () => L.years, (v) => (L.years = v), (v) => String(v))];
      },
      Body: () => [
        range('Feminine ↔ masculine', 0, 1, 0.01, () => L.gender, (v) => (L.gender = v)),
        range('Weight', 0, 1, 0.01, () => L.weight, (v) => (L.weight = v)),
        range('Muscle', 0, 1, 0.01, () => L.muscle, (v) => (L.muscle = v)),
        range('Height', 0, 1, 0.01, () => L.height, (v) => (L.height = v)),
        range('Bust', 0.3, 0.65, 0.01, () => L.cup, (v) => (L.cup = v)),
        ...pack.meta.sliders.filter((s) => s.group === 'body')
          .map((s) => range(s.id, -1, 1, 0.01, () => L.sliders[s.id] ?? 0, (v) => (L.sliders[s.id] = v))),
      ],
      Face: () => pack.meta.sliders.filter((s) => s.group === 'face')
        .map((s) => range(s.id, -1, 1, 0.01, () => L.sliders[s.id] ?? 0, (v) => (L.sliders[s.id] = v))),
      Skin: () => {
        const races = (['african', 'asian', 'caucasian'] as const).map((r) =>
          range(r[0].toUpperCase() + r.slice(1), 0, 1, 0.01, () => L.race[r], (v) => {
            L.race[r] = v;
            const sum = L.race.african + L.race.asian + L.race.caucasian || 1;
            for (const k of ['african', 'asian', 'caucasian'] as const) L.race[k] /= sum;
          }));
        return [swatches(SKIN_TONES, () => L.skin, (i) => (L.skin = i)),
          swatches(EYE_COLORS, () => L.eyes, (i) => (L.eyes = i)), ...races];
      },
      View: () => {
        const row = document.createElement('div'); row.className = 'swatches';
        const btn = (t: string, act: () => void, on: () => boolean) => {
          const b = document.createElement('button'); b.textContent = t; b.classList.toggle('on', on());
          b.onclick = () => { act(); show('View'); layout(); chars.forEach((x) => { setFlatShading(x.mat, ui.flat); applyPose(x); }); };
          row.appendChild(b);
        };
        btn('Body', () => (ui.view = 'body'), () => ui.view === 'body');
        btn('Face', () => (ui.view = 'face'), () => ui.view === 'face');
        btn('Spin', () => (ui.spin = !ui.spin), () => ui.spin);
        btn('Smooth', () => (ui.flat = !ui.flat), () => !ui.flat);
        btn('A-pose', () => (ui.pose = 'rest'), () => ui.pose === 'rest');
        btn('Relaxed', () => (ui.pose = 'relaxed'), () => ui.pose === 'relaxed');
        btn('Arms up', () => (ui.pose = 'armsup'), () => ui.pose === 'armsup');
        return [row];
      },
    };
    function show(name: string): void {
      tabs.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.textContent === name));
      body.replaceChildren(...pages[name]());
    }
    for (const name of Object.keys(pages)) {
      const b = document.createElement('button'); b.textContent = name; b.onclick = () => show(name);
      tabs.appendChild(b);
    }
    show('Age');
  }

  layout();
  setInfo();
  engine.runRenderLoop(() => scene.render());
  window.addEventListener('resize', () => { engine.resize(); layout(); });
  await scene.whenReadyAsync();
  (window as unknown as { __ready: boolean }).__ready = true;
}
