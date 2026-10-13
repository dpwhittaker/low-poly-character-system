// Babylon-side JS cost per draw call (NullEngine: GL calls are stubs, so this is a lower bound).
const B = '/home/david/projects/low-poly-character-system/node_modules/@babylonjs/core/';
const { NullEngine } = await import(B + 'Engines/nullEngine.js');
const { Scene } = await import(B + 'scene.js');
const { FreeCamera } = await import(B + 'Cameras/freeCamera.js');
const { HemisphericLight } = await import(B + 'Lights/hemisphericLight.js');
const { CreateBox } = await import(B + 'Meshes/Builders/boxBuilder.js');
const { StandardMaterial } = await import(B + 'Materials/standardMaterial.js');
const { Vector3, Color3 } = await import(B + 'Maths/math.vector.js').then(async m => ({ ...m, ...(await import(B + 'Maths/math.color.js')) }));
const [,, NMESH = '600', MODE = 'plain'] = process.argv;
const engine = new NullEngine();
const scene = new Scene(engine);
const cam = new FreeCamera('c', new Vector3(0, 5, -40), scene); cam.setTarget(Vector3.Zero());
new HemisphericLight('h', new Vector3(0, 1, 0), scene);
const mats = []; for (let i = 0; i < 8; i++) { const m = new StandardMaterial('m' + i, scene); m.diffuseColor = new Color3(i / 8, 0.5, 0.5); mats.push(m); }
const meshes = [];
for (let i = 0; i < +NMESH; i++) {
  const b = CreateBox('b' + i, { size: 0.5 }, scene);
  b.position.set((i % 30) - 15, 0, Math.floor(i / 30) - 10);
  b.material = mats[i % 8];
  meshes.push(b);
}
if (MODE === 'frozen' || MODE === 'aggressive') {
  for (const m of mats) m.freeze();
  for (const b of meshes) { b.freezeWorldMatrix(); b.doNotSyncBoundingInfo = true; b.isPickable = false; }
  scene.skipPointerMovePicking = true;
}
if (MODE === 'aggressive') scene.freezeActiveMeshes();
for (let i = 0; i < 60; i++) scene.render();
const frames = 300; const t0 = performance.now();
for (let i = 0; i < frames; i++) { if (MODE === 'moving') for (const b of meshes) b.position.y = Math.sin(i * 0.1); scene.render(); }
const ms = (performance.now() - t0) / frames;
console.log("active", scene.getActiveMeshes().length, "draws", engine._drawCalls?.current, "ready", scene.isReady());
console.log(JSON.stringify({ NMESH: +NMESH, MODE, msPerFrame: +ms.toFixed(3), usPerMesh: +(1000 * ms / +NMESH).toFixed(2) }));
