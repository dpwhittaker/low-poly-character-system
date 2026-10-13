// Rotation-only clips (probe P6, `public/m1/anim/clips.glb`) on fitted characters.
// Clips are authored against the canonical rest (SPEC V20), so rotation channels apply to
// any body unchanged; the pelvis translation is rescaled by the body's hip height:
//   T = T_rest_body + (h_body / h_clip) · (T_clip − T_rest_clip)      (P6.md)
// Twist bones (not in the clips) are driven here: the forearm twist takes half of the
// hand's roll, the upper-arm twist counter-rotates half of the upper arm's roll (D6).

import { LoadAssetContainerAsync } from '@babylonjs/core/Loading/sceneLoader';
import { AnimationGroup } from '@babylonjs/core/Animations/animationGroup';
import { Animation } from '@babylonjs/core/Animations/animation';
import { Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';
import type { Bone } from '@babylonjs/core/Bones/bone';
import type { TransformNode } from '@babylonjs/core/Meshes/transformNode';
import '@babylonjs/loaders/glTF/2.0';

import type { CharacterParts } from './babylonCharacter.ts';

export interface ClipLibrary {
  groups: AnimationGroup[];
  /** Canonical pelvis rest translation in the clips (parent-local). */
  pelvisRest: Vector3;
}

export async function loadClips(scene: Scene, url: string): Promise<ClipLibrary> {
  const c = await LoadAssetContainerAsync(url, scene);
  const pelvis = c.transformNodes.find((n) => n.name === 'pelvis');
  if (!pelvis) throw new Error('clips.glb: no pelvis');
  for (const g of c.animationGroups) g.stop();
  return { groups: c.animationGroups, pelvisRest: pelvis.position.clone() };
}

export interface Playing { group: AnimationGroup; dispose(): void }

/** Retarget one clip onto a character's bones and play it. */
export function playClip(lib: ClipLibrary, name: string, parts: CharacterParts, speed = 1, loop?: boolean): Playing | null {
  const src = lib.groups.find((g) => g.name === name);
  if (!src) return null;
  const group = new AnimationGroup(`${parts.mesh.name}_${name}`, parts.mesh.getScene());
  const pelvis = parts.bones.get('pelvis')!;
  const pelvisRest = pelvis.getRestMatrix().getTranslation();
  const scale = pelvisHeight(parts) / pelvisHeightOf(lib.pelvisRest);
  for (const ta of src.targetedAnimations) {
    const node = ta.target as TransformNode;
    const bone = parts.bones.get(node.name);
    if (!bone) continue;
    const a = ta.animation;
    if (a.targetProperty === 'rotationQuaternion') {
      group.addTargetedAnimation(a, bone);
    } else if (a.targetProperty === 'position' && node.name === 'pelvis') {
      const b = new Animation(`${a.name}_fit`, 'position', a.framePerSecond, Animation.ANIMATIONTYPE_VECTOR3, a.loopMode);
      b.setKeys(a.getKeys().map((k) => ({
        frame: k.frame,
        value: pelvisRest.add((k.value as Vector3).subtract(lib.pelvisRest).scale(scale)),
      })));
      group.addTargetedAnimation(b, bone);
    }
  }
  const once = ['sit_down', 'arms_up'].includes(name);
  group.speedRatio = speed;
  group.start(loop ?? !once, speed);
  const driver = driveTwist(parts);
  return { group, dispose: () => { group.stop(); group.dispose(); driver(); parts.skeleton.returnToRest(); } };
}

/** Height of the pelvis head in the character's grounded rest (glTF y). */
function pelvisHeight(parts: CharacterParts): number {
  const b = parts.bones.get('pelvis')!;
  return b.getAbsoluteInverseBindMatrix().clone().invert().getTranslation().y;
}

/** The clip's canonical pelvis height: Root is the identity-positioned parent in clips.glb. */
function pelvisHeightOf(rest: Vector3): number {
  // Root carries the Z-up → Y-up conversion (−90° about X): local z is world up
  return Math.abs(rest.z) > Math.abs(rest.y) ? Math.abs(rest.z) : Math.abs(rest.y);
}

/** Swing–twist: the part of `q` that rotates about the local Y (bone) axis. */
function twistY(q: Quaternion): Quaternion {
  const t = new Quaternion(0, q.y, 0, q.w);
  const l = Math.hypot(t.y, t.w);
  return l < 1e-6 ? Quaternion.Identity() : new Quaternion(0, t.y / l, 0, t.w / l);
}

function restRot(b: Bone): Quaternion {
  const q = new Quaternion();
  b.getRestMatrix().decompose(undefined, q);
  return q;
}

/** Per frame after animations: forearm twist follows ½ hand roll, upper-arm twist ½ counter-roll. */
export function driveTwist(parts: CharacterParts): () => void {
  const scene = parts.mesh.getScene();
  const pairs: Array<[Bone, Bone, number]> = [];
  for (const s of ['l', 'r']) {
    const hand = parts.bones.get(`hand_${s}`), lo = parts.bones.get(`lowerarm_twist_01_${s}`);
    const up = parts.bones.get(`upperarm_${s}`), upT = parts.bones.get(`upperarm_twist_01_${s}`);
    if (hand && lo) pairs.push([hand, lo, 0.5]);
    if (up && upT) pairs.push([up, upT, -0.5]);
  }
  const rests = new Map(pairs.flatMap(([a, b]) => [[a, restRot(a)], [b, restRot(b)]] as Array<[Bone, Quaternion]>));
  const obs = scene.onAfterAnimationsObservable.add(() => {
    for (const [driver, twist, k] of pairs) {
      const cur = driver.rotationQuaternion ?? Quaternion.Identity();
      const delta = Quaternion.Inverse(rests.get(driver)!).multiply(cur);
      const tw = Quaternion.Slerp(Quaternion.Identity(), twistY(delta), Math.abs(k));
      twist.rotationQuaternion = rests.get(twist)!.multiply(k < 0 ? Quaternion.Inverse(tw) : tw);
    }
  });
  return () => scene.onAfterAnimationsObservable.remove(obs);
}
