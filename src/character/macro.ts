// MakeHuman macro sliders → weights of the macro corner targets: a port of MPFB 2.0.18
// `TargetService.calculate_target_stack_from_macro_info_dict` (GPL code; this is an
// independent re-implementation of its arithmetic, tested against MPFB's own output in
// tests/m1_body.test.mjs). Extremes and their combinations are MakeHuman's designed
// shapes, not sums of independent morphs (PLAN §5.2).

import type { MacroParts } from './bodyPack.ts';

export interface Macro {
  gender: number; // 0 female … 1 male
  age: number; // MakeHuman age macro: 0 = 1 y, 0.1875 = 11 y, 0.5 = 25 y, 1 = 90 y
  muscle: number;
  weight: number;
  proportions: number;
  height: number;
  cupsize: number;
  firmness: number;
  race: { african: number; asian: number; caucasian: number };
}

export const DEFAULT_MACRO: Macro = {
  gender: 0.5, age: 0.5, muscle: 0.5, weight: 0.5, proportions: 0.5, height: 0.5, cupsize: 0.5, firmness: 0.5,
  race: { african: 0.33, asian: 0.33, caucasian: 0.33 },
};

type Comp = Array<[string, number]>;

const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

function components(parts: MacroParts[string], value: number): Comp {
  const out: Comp = [];
  for (const [lowest, highest, low, high] of parts) {
    if (value > lowest && value < highest) {
      const t = (value - lowest) / (highest - lowest);
      if (low) out.push([low, r4(1 - t)]);
      if (high) out.push([high, r4(t)]);
    }
  }
  return out;
}

/** [target name, weight] for every macro corner target with weight > cutoff. */
export function macroStack(m: Macro, parts: MacroParts, cutoff = 0): Array<[string, number]> {
  const c = (k: keyof Omit<Macro, 'race'>) => components(parts[k], m[k]);
  const g = c('gender'), a = c('age'), mu = c('muscle'), w = c('weight');
  const pr = c('proportions'), h = c('height'), cup = c('cupsize'), fi = c('firmness');
  const out: Array<[string, number]> = [];
  for (const [race, rw] of Object.entries(m.race)) {
    if (rw <= 0.0001) continue;
    for (const [an, aw] of a) for (const [gn, gw] of g) {
      const wt = rw * gw * aw;
      if (wt > cutoff) out.push([`macrodetails/${race}-${gn}-${an}`, wt]);
    }
  }
  for (const [gn, gw] of g) for (const [an, aw] of a) for (const [mn, mw] of mu) for (const [wn, ww] of w) {
    const wt = gw * aw * mw * ww;
    if (wt > cutoff) out.push([`macrodetails/universal-${gn}-${an}-${mn}-${wn}`, wt]);
  }
  for (const [gn, gw] of g) for (const [an, aw] of a) for (const [mn, mw] of mu) for (const [wn, ww] of w)
    for (const [hn, hw] of h) {
      const wt = gw * aw * mw * ww * hw;
      if (wt > cutoff) out.push([`macrodetails/height/${gn}-${an}-${mn}-${wn}-${hn}`, wt]);
    }
  // breast: MPFB applies these without the gender factor (no male complements), and skips
  // the average/average "zero" corner and every baby combination
  for (const [gn] of g) {
    if (gn !== 'female') continue;
    for (const [an, aw] of a) for (const [mn, mw] of mu) for (const [wn, ww] of w)
      for (const [cn, cw] of cup) for (const [fn, fw] of fi) {
        const wt = aw * mw * ww * cw * fw;
        const name = `breast/${gn}-${an}-${mn}-${wn}-${cn}-${fn}`;
        if (wt > cutoff && !name.includes('averagecup-averagefirmness') && an !== 'baby') out.push([name, wt]);
      }
  }
  for (const [gn, gw] of g) for (const [an, aw] of a) for (const [mn, mw] of mu) for (const [wn, ww] of w)
    for (const [pn, pw] of pr) {
      const wt = gw * aw * mw * ww * pw;
      if (wt > cutoff && an !== 'baby') out.push([`macrodetails/proportions/${gn}-${an}-${mn}-${wn}-${pn}`, wt]);
    }
  return out;
}

/** Years → MakeHuman age macro via the growth-chart curve in body.json (per gender, lerped). */
export function ageMacro(years: number, gender: number, curve: Record<'female' | 'male', { years_to_macro: Array<[number, number]> }>): number {
  if (years >= 25) return Math.min(1, 0.5 + ((years - 25) / 65) * 0.5);
  const at = (tab: Array<[number, number]>) => {
    if (years <= tab[0][0]) return tab[0][1];
    for (let i = 1; i < tab.length; i++) {
      if (years <= tab[i][0]) {
        const [y0, a0] = tab[i - 1], [y1, a1] = tab[i];
        return a0 + ((years - y0) / (y1 - y0)) * (a1 - a0);
      }
    }
    return 0.5; // 18–25 y: adult
  };
  const f = at(curve.female.years_to_macro), m = at(curve.male.years_to_macro);
  return f + (m - f) * gender;
}
