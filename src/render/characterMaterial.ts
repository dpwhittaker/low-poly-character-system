import { ShaderMaterial } from '@babylonjs/core/Materials/shaderMaterial';
import { Effect } from '@babylonjs/core/Materials/effect';
import type { BaseTexture } from '@babylonjs/core/Materials/Textures/baseTexture';
import type { Scene } from '@babylonjs/core/scene';
import { Vector3, Color3 } from '@babylonjs/core/Maths/math';
import type { LightingRig } from './lighting';

// Character surface shader (M0 prototype of the shared character material, PLAN §4.4).
//   albedo = COLOR_0.rgb (palette color, linear) × texture, where the texture is
//            either an albedo decal (texMode 1, sRGB-encoded) or a greyscale detail map
//            (texMode 2, 0.5 = neutral)
//   ao     = COLOR_0.a (baked ambient occlusion)
//   facets = flat normals from screen-space derivatives (flat = 1). Vertices stay
//            shared, so faceting costs no vertex splits (PLAN §4.4: flat-shaded export
//            would triple vertex count).
// Lighting comes only from the shared rig (lighting.ts).

const NAME = 'lpCharacter';

Effect.ShadersStore[`${NAME}VertexShader`] = /* glsl */ `
precision highp float;
attribute vec3 position;
attribute vec3 normal;
attribute vec4 color;
#ifdef HAS_UV
attribute vec2 uv;
varying vec2 vUV;
#endif
uniform mat4 world;
uniform mat4 viewProjection;
varying vec3 vWorldPos;
varying vec3 vNormal;
varying vec4 vColor;
void main(void) {
  vec4 wp = world * vec4(position, 1.0);
  vWorldPos = wp.xyz;
  vNormal = normalize(mat3(world) * normal);
  vColor = color;
#ifdef HAS_UV
  vUV = uv;
#endif
  gl_Position = viewProjection * wp;
}`;

Effect.ShadersStore[`${NAME}FragmentShader`] = /* glsl */ `
precision highp float;
varying vec3 vWorldPos;
varying vec3 vNormal;
varying vec4 vColor;
#ifdef HAS_UV
varying vec2 vUV;
uniform sampler2D tex;
#endif
uniform vec3 cameraPos;
uniform float flatShading;
uniform float texMode;
uniform float texHwSrgb;
uniform vec3 skyColor;
uniform vec3 groundColor;
uniform float ambient;
uniform vec3 keyDir;
uniform vec3 keyColor;
uniform vec3 fillDir;
uniform vec3 fillColor;
uniform vec3 rimDir;
uniform vec3 rimColor;
uniform float wrap;

void main(void) {
  vec3 n = flatShading > 0.5 ? normalize(cross(dFdx(vWorldPos), dFdy(vWorldPos))) : normalize(vNormal);
  vec3 v = normalize(cameraPos - vWorldPos);
  if (dot(n, v) < 0.0) n = -n;

  vec3 albedo = vColor.rgb;
  float ao = vColor.a;
#ifdef HAS_UV
  // Babylon uploads glTF color textures as sRGB buffers when it can, so the sampler may
  // already return linear values. Decoding again made S2/S3 skin orange and S3 detail dark.
  vec3 t = texture2D(tex, vUV).rgb;
  if (texMode > 0.5 && texMode < 1.5) albedo *= texHwSrgb > 0.5 ? t : pow(t, vec3(2.2));
  if (texMode > 1.5) albedo *= 2.0 * (texHwSrgb > 0.5 ? pow(t.r, 1.0 / 2.2) : t.r);
#endif

  vec3 amb = mix(groundColor, skyColor, n.y * 0.5 + 0.5) * ambient;
  float kd = max(0.0, (dot(n, -keyDir) + wrap) / (1.0 + wrap));
  float fd = max(0.0, (dot(n, -fillDir) + wrap) / (1.0 + wrap));
  float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0) * max(0.0, dot(n, -rimDir) * 0.5 + 0.5);

  vec3 lit = albedo * (amb * mix(1.0, ao, 0.9) + keyColor * kd * mix(1.0, ao, 0.45) + fillColor * fd * ao)
           + rimColor * rim * 0.22 * ao;
  gl_FragColor = vec4(pow(lit, vec3(1.0 / 2.2)), 1.0);
}`;

export type TexMode = 'none' | 'albedo' | 'detail';

export interface CharacterMaterialOptions {
  rig: LightingRig;
  texture?: BaseTexture | null;
  texMode?: TexMode;
}

export function createCharacterMaterial(name: string, scene: Scene, opts: CharacterMaterialOptions): ShaderMaterial {
  const hasTex = !!opts.texture && opts.texMode !== 'none';
  const mat = new ShaderMaterial(name, scene, { vertex: NAME, fragment: NAME }, {
    attributes: hasTex ? ['position', 'normal', 'color', 'uv'] : ['position', 'normal', 'color'],
    uniforms: ['world', 'viewProjection', 'cameraPos', 'flatShading', 'texMode', 'skyColor', 'groundColor',
      'ambient', 'keyDir', 'keyColor', 'fillDir', 'fillColor', 'rimDir', 'rimColor', 'wrap', 'texHwSrgb'],
    samplers: hasTex ? ['tex'] : [],
    defines: hasTex ? ['#define HAS_UV'] : [],
  });
  const r = opts.rig;
  const v3 = (a: [number, number, number]) => new Vector3(a[0], a[1], a[2]);
  const c3 = (a: [number, number, number]) => new Color3(a[0], a[1], a[2]);
  mat.setColor3('skyColor', c3(r.sky));
  mat.setColor3('groundColor', c3(r.ground));
  mat.setFloat('ambient', r.ambient);
  mat.setVector3('keyDir', v3(r.key.dir));
  mat.setColor3('keyColor', c3(r.key.color));
  mat.setVector3('fillDir', v3(r.fill.dir));
  mat.setColor3('fillColor', c3(r.fill.color));
  mat.setVector3('rimDir', v3(r.rim.dir));
  mat.setColor3('rimColor', c3(r.rim.color));
  mat.setFloat('wrap', r.wrap);
  mat.setFloat('flatShading', 1);
  mat.setFloat('texMode', hasTex ? (opts.texMode === 'detail' ? 2 : 1) : 0);
  if (hasTex && opts.texture) {
    mat.setTexture('tex', opts.texture);
    const hw = (opts.texture.getInternalTexture() as unknown as { _useSRGBBuffer?: boolean } | null)?._useSRGBBuffer;
    mat.setFloat('texHwSrgb', hw ? 1 : 0);
  } else {
    mat.setFloat('texHwSrgb', 0);
  }
  mat.backFaceCulling = false; // garment shells are single-sided; inside faces must render
  mat.onBindObservable.add(() => {
    const cam = scene.activeCamera;
    if (cam) mat.getEffect()?.setVector3('cameraPos', cam.globalPosition);
  });
  return mat;
}

export function setFlatShading(mat: ShaderMaterial, flat: boolean): void {
  mat.setFloat('flatShading', flat ? 1 : 0);
}
