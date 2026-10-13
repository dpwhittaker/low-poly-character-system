// Skeleton fit (PLAN §4.3 step 2, §5.4): every body keeps the CANONICAL rest rotations of
// `skeleton.glb` and only moves bone heads to its own joints, so rotation-only clips play
// on any proportions (SPEC V20). Babylon math only, with `.js` deep imports so this module
// also runs under Node's ESM resolver (tests).

import { Matrix, Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import type { BodyPack } from './bodyPack.ts';

export interface RestSkeleton {
  /** Local rest rotation per bone name (glTF space, x y z w). */
  rot: Map<string, [number, number, number, number]>;
}

/** Reads bone rest rotations from skeleton.glb's JSON chunk (no loader needed). */
export async function loadRestSkeleton(url: string): Promise<RestSkeleton> {
  const buf = await (await fetch(url)).arrayBuffer();
  return parseRestSkeleton(buf);
}

export function parseRestSkeleton(buf: ArrayBuffer): RestSkeleton {
  const dv = new DataView(buf);
  const len = dv.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, len))) as {
    nodes: Array<{ name: string; rotation?: number[]; translation?: number[]; children?: number[] }>;
    skins: Array<{ joints: number[] }>;
  };
  const joints = new Set(json.skins[0].joints);
  const rot = new Map<string, [number, number, number, number]>();
  json.nodes.forEach((n, i) => {
    if (joints.has(i)) rot.set(n.name, (n.rotation ?? [0, 0, 0, 1]) as [number, number, number, number]);
    else if (n.rotation && Math.abs(n.rotation[3]) < 0.9999) throw new Error(`skeleton.glb: armature node ${n.name} is rotated`);
  });
  return { rot };
}


/** Parent-first bone order (Blender's edit-bone order is alphabetical, not topological). */
export function topoOrder(pack: BodyPack): number[] {
  const out: number[] = [];
  const seen = new Set<number>();
  const visit = (i: number) => {
    if (seen.has(i)) return;
    const p = pack.meta.bones[i].parent;
    if (p >= 0) visit(p);
    seen.add(i); out.push(i);
  };
  pack.meta.bones.forEach((_, i) => visit(i));
  return out;
}

/** Local bone matrices for a body: canonical rest rotation + this body's head offsets. */
export function fitBoneMatrices(pack: BodyPack, rest: RestSkeleton, heads: Float32Array): Matrix[] {
  const n = pack.meta.bones.length;
  const worldRot: Matrix[] = new Array(n);
  const local: Matrix[] = new Array(n);
  for (const i of topoOrder(pack)) {
    const b = pack.meta.bones[i];
    const r = rest.rot.get(b.name);
    if (!r) throw new Error(`skeleton.glb has no bone ${b.name}`);
    const q = new Quaternion(r[0], r[1], r[2], r[3]);
    const rotM = Matrix.Identity();
    q.toRotationMatrix(rotM);
    const h = new Vector3(heads[i * 3], heads[i * 3 + 1], heads[i * 3 + 2]);
    let t: Vector3;
    if (b.parent < 0) {
      t = h;
      worldRot[i] = rotM;
    } else {
      const p = b.parent;
      const d = h.subtract(new Vector3(heads[p * 3], heads[p * 3 + 1], heads[p * 3 + 2]));
      // row-vector convention: world = local × parentWorld, so local offset = d × parentWorld⁻¹
      t = Vector3.TransformNormal(d, worldRot[p].clone().transpose());
      worldRot[i] = rotM.multiply(worldRot[p]);
    }
    local[i] = Matrix.Compose(Vector3.One(), q, t);
  }
  return local;
}
