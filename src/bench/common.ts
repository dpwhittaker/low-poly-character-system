// Shared pieces of the three bench paths: per-character data (deterministic
// from the scene seed), Babylon mesh creation, frustum tests and the runtime
// interface every path implements.

import { Mesh, VertexData, VertexBuffer, Frustum, Plane, type Scene, type Camera } from '@babylonjs/core';
import { characterSkeleton, randomProportions, type CharacterSkeleton } from './skeleton.ts';
import { buildCharacterLod, randomPalette, type MeshData, type Palette } from './geometry.ts';
import { hashSeed, mulberry32 } from './rng.ts';
import type { CharSpec, SceneSpec } from './scenes.ts';

export interface BenchChar {
  spec: CharSpec;
  skel: CharacterSkeleton;
  pal: Palette;
  lods: MeshData[];
  /** current world position / yaw (walkers move) */
  x: number;
  z: number;
  yaw: number;
}

export function buildChars(spec: SceneSpec, lods: number[]): BenchChar[] {
  return spec.chars.map((c) => {
    const rng = mulberry32(hashSeed(spec.seed, c.id, 0x5eed));
    const skel = characterSkeleton(randomProportions(rng));
    const pal = randomPalette(rng);
    const meshes: MeshData[] = [];
    for (const l of lods) meshes[l] = buildCharacterLod(skel, l, pal);
    return { spec: c, skel, pal, lods: meshes, x: c.hx, z: c.hz, yaw: c.yaw };
  });
}

export interface ExtraAttr { kind: string; data: Float32Array; stride: number }

export function meshFromData(name: string, scene: Scene, md: MeshData, extra: ExtraAttr[] = [], skin = true): Mesh {
  const m = new Mesh(name, scene);
  const vd = new VertexData();
  vd.positions = md.positions;
  vd.normals = md.normals;
  vd.colors = md.colors;
  vd.indices = md.indices;
  vd.applyToMesh(m, false);
  if (skin) {
    m.setVerticesData(VertexBuffer.MatricesIndicesKind, md.boneIndices, false, 4);
    m.setVerticesData(VertexBuffer.MatricesWeightsKind, md.boneWeights, false, 4);
  }
  for (const e of extra) m.setVerticesData(e.kind, e.data, false, e.stride);
  m.isPickable = false;
  return m;
}

export function constantAttr(vertices: number, value: number): Float32Array {
  return new Float32Array(vertices).fill(value);
}

export interface StepTimes {
  /** sampler + compose (B/C); 0 for A, whose animation runs inside scene.render() */
  animMs: number;
  /** LOD + culling + bone-texture upload + shadow buffer (B/C); 0 for A */
  uploadCullMs: number;
}

export interface FrameStats {
  visibleChars: number;
  visibleTris: number;
  lod: [number, number, number, number];
  composed: number;
}

export interface PathRuntime {
  readonly name: 'A' | 'B' | 'C';
  /** advance to `frame` (simulation time `time` s); camera already positioned */
  step(frame: number, time: number, camera: Camera): StepTimes;
  stats(): FrameStats;
}

export class FrustumTester {
  private planes: Plane[] = [];
  update(camera: Camera) {
    if (this.planes.length === 0) this.planes = Frustum.GetPlanes(camera.getTransformationMatrix());
    else Frustum.GetPlanesToRef(camera.getTransformationMatrix(), this.planes);
  }
  /** sphere test */
  visible(x: number, y: number, z: number, r: number): boolean {
    for (const p of this.planes) {
      if (p.normal.x * x + p.normal.y * y + p.normal.z * z + p.d < -r) return false;
    }
    return true;
  }
}
