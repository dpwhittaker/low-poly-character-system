// The one lighting definition for every character view: game, creator, style frames,
// screenshot harnesses (SPEC §C, PLAN §4.4). World Forge's face-shadow bug came from a
// harness whose lighting had drifted from the game's, so nothing defines its own lights.
//
// Directions point FROM the light INTO the scene, in Babylon world space (y up). The
// character material reads these values as uniforms; it does not use Babylon lights.

export interface DirLight {
  dir: [number, number, number];
  color: [number, number, number]; // linear RGB, intensity folded in
}

export interface LightingRig {
  sky: [number, number, number]; // hemispheric ambient, linear
  ground: [number, number, number];
  ambient: number;
  key: DirLight;
  fill: DirLight;
  rim: DirLight;
  /** Wrap-diffuse amount: 0 = Lambert, higher = softer terminator on low-poly facets. */
  wrap: number;
  /** Background clear color, sRGB hex. Matches the approved reference's light grey. */
  background: string;
}

function norm(v: [number, number, number]): [number, number, number] {
  const l = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / l, v[1] / l, v[2] / l];
}

export const STUDIO: LightingRig = {
  sky: [0.78, 0.8, 0.86],
  ground: [0.4, 0.36, 0.33],
  ambient: 0.5,
  key: { dir: norm([0.55, -0.7, -0.45]), color: [1.08, 1.02, 0.94] },
  fill: { dir: norm([-0.7, -0.25, -0.5]), color: [0.32, 0.35, 0.42] },
  rim: { dir: norm([-0.3, -0.35, 0.9]), color: [0.55, 0.55, 0.6] },
  wrap: 0.3,
  background: '#d8d8da',
};
