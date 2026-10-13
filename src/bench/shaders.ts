// Shaders for the M0 crowd bench. Every path shades the same way (vertex
// color × wrapped Lambert), so the paths differ only in skinning and
// submission, which is what the bench compares.
//
// Paths B/C use a ShaderMaterial, not a material plugin. Why: the skinning
// source is our own texture layout (3 texels per affine matrix, a per-vertex
// character row, root slots for far-tier batches), which a plugin would have
// to bolt onto StandardMaterial's own bone path. A ShaderMaterial also keeps
// the shading identical to path A's. The cost is that the real character
// material will need this code ported into its plugin/NodeMaterial. That is
// M2 work.

import { Effect, ShaderMaterial, Vector2, Vector3, type Scene, type Texture } from '@babylonjs/core';
import { TEXELS_PER_ROW, ROOT_SLOTS } from './sampler.ts';

const FRAG = /* glsl */ `
precision highp float;
varying vec3 vColor;
varying vec3 vNormal;
varying vec3 vWorld;
uniform vec3 lightDir;
#ifdef FADE
uniform vec3 cameraPosition;
uniform vec2 fade;
#endif
void main(void) {
#ifdef FADE
  float d = distance(vWorld, cameraPosition);
  float f = clamp((d - fade.x) / (fade.y - fade.x), 0.0, 1.0);
  // 4×4 ordered dither: a draw-distance fade without alpha blending or sorting.
  ivec2 p = ivec2(mod(gl_FragCoord.xy, 4.0));
  int i = p.x + p.y * 4;
  float th = float((i * 7) % 16) / 16.0 + 0.03125;
  if (f > th) discard;
#endif
  vec3 n = normalize(vNormal);
  float wrap = clamp((dot(n, -lightDir) + 0.4) / 1.4, 0.0, 1.0);
  gl_FragColor = vec4(vColor * (0.35 + 0.65 * wrap), 1.0);
}`;

const VERT_TEX = /* glsl */ `
precision highp float;
precision highp sampler2D;
attribute vec3 position;
attribute vec3 normal;
attribute vec4 color;
attribute vec4 matricesIndices;
attribute vec4 matricesWeights;
attribute float charRow;
#ifdef BATCH
attribute float rootSlot;
#endif
uniform mat4 viewProjection;
uniform sampler2D boneTex;
varying vec3 vColor;
varying vec3 vNormal;
varying vec3 vWorld;
mat4 readSlot(int row, int slot) {
  int x = slot * 3;
  vec4 a = texelFetch(boneTex, ivec2(x, row), 0);
  vec4 b = texelFetch(boneTex, ivec2(x + 1, row), 0);
  vec4 c = texelFetch(boneTex, ivec2(x + 2, row), 0);
  return mat4(a.x, b.x, c.x, 0.0,  a.y, b.y, c.y, 0.0,  a.z, b.z, c.z, 0.0,  a.w, b.w, c.w, 1.0);
}
void main(void) {
  int row = int(charRow + 0.5);
  mat4 skin = readSlot(row, ${ROOT_SLOTS} + int(matricesIndices.x + 0.5)) * matricesWeights.x;
  skin += readSlot(row, ${ROOT_SLOTS} + int(matricesIndices.y + 0.5)) * matricesWeights.y;
#if INFLUENCES > 2
  skin += readSlot(row, ${ROOT_SLOTS} + int(matricesIndices.z + 0.5)) * matricesWeights.z;
  skin += readSlot(row, ${ROOT_SLOTS} + int(matricesIndices.w + 0.5)) * matricesWeights.w;
#endif
#ifdef BATCH
  mat4 root = readSlot(row, int(rootSlot + 0.5));
#else
  mat4 root = readSlot(row, 0);
#endif
  mat4 m = root * skin;
  vec4 wp = m * vec4(position, 1.0);
  vWorld = wp.xyz;
  vNormal = mat3(m) * normal;
  vColor = color.rgb;
  gl_Position = viewProjection * wp;
}`;

const VERT_NATIVE = /* glsl */ `
precision highp float;
attribute vec3 position;
attribute vec3 normal;
attribute vec4 color;
#include<bonesDeclaration>
uniform mat4 world;
uniform mat4 viewProjection;
varying vec3 vColor;
varying vec3 vNormal;
varying vec3 vWorld;
void main(void) {
  mat4 finalWorld = world;
#include<bonesVertex>
  vec4 wp = finalWorld * vec4(position, 1.0);
  vWorld = wp.xyz;
  vNormal = mat3(finalWorld) * normal;
  vColor = color.rgb;
  gl_Position = viewProjection * wp;
}`;

Effect.ShadersStore['benchTexVertexShader'] = VERT_TEX;
Effect.ShadersStore['benchTexFragmentShader'] = FRAG;
Effect.ShadersStore['benchNativeVertexShader'] = VERT_NATIVE;
Effect.ShadersStore['benchNativeFragmentShader'] = FRAG;

export const LIGHT_DIR = [-0.35, -0.85, 0.4];

/** Path B/C material: texture skinning. One instance per variant, shared by every character. */
export function texSkinMaterial(scene: Scene, boneTex: Texture, opts: { influences: 2 | 4; batch?: boolean; fade?: [number, number] }): ShaderMaterial {
  const defines = [`#define INFLUENCES ${opts.influences}`];
  const attributes = ['position', 'normal', 'color', 'matricesIndices', 'matricesWeights', 'charRow'];
  if (opts.batch) { defines.push('#define BATCH'); attributes.push('rootSlot'); }
  const uniforms = ['viewProjection', 'lightDir'];
  if (opts.fade) { defines.push('#define FADE'); uniforms.push('cameraPosition', 'fade'); }
  const m = new ShaderMaterial(`benchTex${opts.influences}${opts.batch ? 'B' : ''}`, scene, 'benchTex', {
    attributes, uniforms, samplers: ['boneTex'], defines,
  });
  m.setTexture('boneTex', boneTex);
  m.setVector3('lightDir', norm3(LIGHT_DIR));
  if (opts.fade) m.setVector2('fade', new Vector2(opts.fade[0], opts.fade[1]));
  m.backFaceCulling = true;
  return m;
}

/** Path A material: Babylon's own bone texture skinning, same shading. One per character (see pathA.ts). */
export function nativeSkinMaterial(scene: Scene, name: string): ShaderMaterial {
  const m = new ShaderMaterial(name, scene, 'benchNative', {
    attributes: ['position', 'normal', 'color'],
    uniforms: ['world', 'viewProjection', 'lightDir'],
  });
  m.setVector3('lightDir', norm3(LIGHT_DIR));
  m.backFaceCulling = true;
  return m;
}

function norm3(v: number[]) {
  const l = Math.hypot(v[0], v[1], v[2]);
  return new Vector3(v[0] / l, v[1] / l, v[2] / l);
}

export const BONE_TEX_WIDTH = TEXELS_PER_ROW;
