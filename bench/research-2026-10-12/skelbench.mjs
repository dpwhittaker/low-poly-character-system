// CPU benchmark: N characters x B bones, animated via AnimationGroup, NullEngine.
const B = '/home/david/projects/low-poly-character-system/node_modules/@babylonjs/core/';
const { NullEngine } = await import(B + 'Engines/nullEngine.js');
const { Scene } = await import(B + 'scene.js');
const { Skeleton } = await import(B + 'Bones/skeleton.js');
const { Bone } = await import(B + 'Bones/bone.js');
const { TransformNode } = await import(B + 'Meshes/transformNode.js');
const { Animation } = await import(B + 'Animations/animation.js');
const { AnimationGroup } = await import(B + 'Animations/animationGroup.js');
await import(B + 'Animations/animatable.js');
const { Vector3, Quaternion, Matrix } = await import(B + 'Maths/math.vector.js');

const [,, NCHAR = '100', NBONE = '30', MODE = 'bones', NGROUPS = '1'] = process.argv;
const N = +NCHAR, NB = +NBONE, G = +NGROUPS;
const engine = new NullEngine();
const scene = new Scene(engine);
scene.useConstantAnimationDeltaTime = true;

function makeAnims(name) {
  // 30 fps, 2 s clip, keys every frame: rotation + position channels per bone (like glTF Mixamo-ish)
  const rot = new Animation(name + 'r', 'rotationQuaternion', 30, Animation.ANIMATIONTYPE_QUATERNION, Animation.ANIMATIONLOOPMODE_CYCLE);
  const pos = new Animation(name + 'p', 'position', 30, Animation.ANIMATIONTYPE_VECTOR3, Animation.ANIMATIONLOOPMODE_CYCLE);
  const rk = [], pk = [];
  for (let f = 0; f <= 60; f++) {
    rk.push({ frame: f, value: Quaternion.RotationYawPitchRoll(Math.sin(f * 0.1 + name.length) * 0.3, 0.1 * f / 60, 0) });
    pk.push({ frame: f, value: new Vector3(0, 0.1 + 0.01 * Math.sin(f * 0.2), 0) });
  }
  rot.setKeys(rk); pos.setKeys(pk);
  return [rot, pos];
}
const skeletons = [];
const groups = [];
for (let c = 0; c < N; c++) {
  const sk = new Skeleton('sk' + c, 'sk' + c, scene);
  const gs = []; for (let g = 0; g < G; g++) gs.push(new AnimationGroup('g' + c + '_' + g, scene));
  let parentBone = null, parentNode = null;
  const root = MODE === 'gltf' ? new TransformNode('root' + c, scene) : null;
  for (let b = 0; b < NB; b++) {
    // tree: every 6th bone restarts from bone 0 (limbs)
    const pIdx = b === 0 ? -1 : (b % 6 === 1 ? 0 : b - 1);
    const pb = pIdx < 0 ? null : sk.bones[pIdx];
    const bone = new Bone('b' + b, sk, pb, Matrix.Translation(0, 0.1, 0));
    bone.rotationQuaternion = Quaternion.Identity();
    let target = bone;
    if (MODE === 'gltf') {
      const tn = new TransformNode('n' + c + '_' + b, scene);
      tn.parent = pIdx < 0 ? root : sk.bones[pIdx]._linkedTransformNode;
      tn.rotationQuaternion = Quaternion.Identity();
      bone.linkTransformNode(tn);
      target = tn;
    }
    for (let g = 0; g < G; g++) {
      for (const a of makeAnims('c' + c + 'b' + b + 'g' + g)) gs[g].addTargetedAnimation(a, target);
    }
  }
  sk.returnToRest?.();
  skeletons.push(sk);
  for (let g = 0; g < G; g++) {
    gs[g].start(true, 1.0, 0, 60);
    if (G > 1) { gs[g].weight = 1 / G; }
  }
  groups.push(gs);
}
const frames = 300;
let tAnim = 0, tPrep = 0;
// warmup
for (let i = 0; i < 60; i++) { scene.animate(); for (const s of skeletons) { s._markAsDirty(); s.prepare(true); } }
for (let i = 0; i < frames; i++) {
  const t0 = performance.now();
  scene.animate();
  if (MODE === 'gltf') { for (const tn of scene.transformNodes) tn.computeWorldMatrix(); }
  const t1 = performance.now();
  for (const s of skeletons) { s._markAsDirty(); s.prepare(true); }
  const t2 = performance.now();
  tAnim += t1 - t0; tPrep += t2 - t1;
}
console.log(JSON.stringify({ N, NB, MODE, groups: G, animMsPerFrame: +(tAnim / frames).toFixed(3), prepareMsPerFrame: +(tPrep / frames).toFixed(3), totalMs: +((tAnim + tPrep) / frames).toFixed(3), perCharUs: +(1000 * (tAnim + tPrep) / frames / N).toFixed(1) }));
