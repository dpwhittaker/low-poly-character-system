"""M1 body: which MakeHuman targets become runtime data, and the slider definitions.

Pure data, imported by the Blender scripts in this folder and copied into
`public/m1/body.json` so the runtime and the pipeline agree on one definition.

Three kinds of shape data:
  macro   MakeHuman's macro corner targets (race x gender x age, gender x age x muscle x
          weight [x height | proportions | cup x firmness]). The runtime weights them with
          MakeHuman's own tent functions (MACRO_PARTS, copied from MPFB's macro.json), so
          extremes and their combinations are MakeHuman's designed shapes, not sums.
  slider  region / face sliders: value in [-1, 1] → weight of the `neg` or `pos` targets.
  style   the house stylization toward the approved reference (from M0), always on.
"""

# MPFB 2.0.18 data/targets/macrodetails/macro.json "macrotargets" (CC0 data). Each part is a
# tent between `lowest` and `highest`; the slightly-out-of-range ends (-0.01, 1.01) are
# MakeHuman's, kept so our weights match its bodies exactly.
MACRO_PARTS = {
    "gender": [(-0.01, 1.01, "female", "male")],
    "age": [(-0.01, 0.1874998, "baby", "child"), (0.1874999, 0.49998, "child", "young"),
            (0.49999, 1.01, "young", "old")],
    "muscle": [(-0.01, 0.49998, "minmuscle", "averagemuscle"), (0.49999, 1.01, "averagemuscle", "maxmuscle")],
    "weight": [(-0.01, 0.49998, "minweight", "averageweight"), (0.49999, 1.01, "averageweight", "maxweight")],
    "proportions": [(-0.01, 0.4999, "uncommonproportions", ""), (0.5, 1.01, "", "idealproportions")],
    "height": [(-0.01, 0.49, "minheight", ""), (0.51, 1.01, "", "maxheight")],
    "cupsize": [(-0.01, 0.49998, "mincup", "averagecup"), (0.49999, 1.01, "averagecup", "maxcup")],
    "firmness": [(-0.01, 0.4998, "minfirmness", "averagefirmness"), (0.4999, 1.01, "averagefirmness", "maxfirmness")],
}
RACES = ("african", "asian", "caucasian")

# MakeHuman age macro ↔ years: 0 = 1 y, 0.1875 = 11 y, 0.5 = 25 y, 1 = 90 y, linear between.
AGE_KEYS = [(1, 0.0), (11, 0.1875), (25, 0.5), (90, 1.0)]

# MakeHuman's child keys run short: its "11 y" body is 1.26 m, its "16 y" 1.37 m (SPEC R19),
# against ~1.44 m and ~1.62–1.73 m in growth charts. So years → age macro goes through
# height instead: a child of age y gets the MakeHuman age whose height, as a fraction of
# that gender's adult (macro 0.5) height, matches the growth chart's fraction at y.
# CDC 2000 stature-for-age, 50th percentile, metres (rounded). Adult ≥ 18 y → macro 0.5
# until 25 y, then MakeHuman's own young → old ramp to 90 y.
GROWTH_M = {
    "female": [(0, 0.49), (0.5, 0.66), (1, 0.74), (1.5, 0.80), (2, 0.86), (3, 0.95), (4, 1.01), (5, 1.08),
               (6, 1.15), (7, 1.21), (8, 1.27), (9, 1.33), (10, 1.38), (11, 1.44), (12, 1.51), (13, 1.57),
               (14, 1.60), (15, 1.62), (16, 1.62), (17, 1.63), (18, 1.63)],
    "male": [(0, 0.50), (0.5, 0.68), (1, 0.76), (1.5, 0.82), (2, 0.88), (3, 0.96), (4, 1.03), (5, 1.10),
             (6, 1.16), (7, 1.22), (8, 1.28), (9, 1.34), (10, 1.39), (11, 1.44), (12, 1.49), (13, 1.56),
             (14, 1.64), (15, 1.70), (16, 1.73), (17, 1.75), (18, 1.76)],
}

# Region and face sliders, value in [-1, 1]. Each side lists (target, weight at |value| = 1).
# {s} expands to l and r (symmetric pairs). `group` orders them in the creator UI.
SLIDERS = [
    # body
    {"id": "shoulders", "group": "body", "neg": ["torso/measure-shoulder-dist-decr"], "pos": ["torso/measure-shoulder-dist-incr"]},
    {"id": "waist", "group": "body", "neg": ["torso/measure-waist-circ-decr"], "pos": ["torso/measure-waist-circ-incr"]},
    {"id": "hips", "group": "body", "neg": ["torso/measure-hips-circ-decr"], "pos": ["torso/measure-hips-circ-incr"]},
    {"id": "legLength", "group": "body", "neg": ["legs/measure-upperleg-height-decr", "legs/measure-lowerleg-height-decr"],
     "pos": ["legs/measure-upperleg-height-incr", "legs/measure-lowerleg-height-incr"]},
    {"id": "armLength", "group": "body", "neg": ["arms/measure-upperarm-length-decr", "arms/measure-lowerarm-length-decr"],
     "pos": ["arms/measure-upperarm-length-incr", "arms/measure-lowerarm-length-incr"]},
    {"id": "neckLength", "group": "body", "neg": ["neck/measure-neck-height-decr"], "pos": ["neck/measure-neck-height-incr"]},
    {"id": "headSize", "group": "body", "neg": ["head/head-scale-horiz-decr", "head/head-scale-vert-decr", "head/head-scale-depth-decr"],
     "pos": ["head/head-scale-horiz-incr", "head/head-scale-vert-incr", "head/head-scale-depth-incr"]},
    # face
    {"id": "faceRound", "group": "face", "neg": ["head/head-oval"], "pos": ["head/head-round"]},
    {"id": "faceSquare", "group": "face", "neg": ["head/head-invertedtriangular"], "pos": ["head/head-square"]},
    {"id": "jawWidth", "group": "face", "neg": ["chin/chin-bones-decr"], "pos": ["chin/chin-bones-incr"]},
    {"id": "chinLength", "group": "face", "neg": ["chin/chin-height-decr"], "pos": ["chin/chin-height-incr"]},
    {"id": "cheeks", "group": "face", "neg": ["cheek/{s}-cheek-volume-decr"], "pos": ["cheek/{s}-cheek-volume-incr"]},
    {"id": "eyeSize", "group": "face", "neg": ["eyes/{s}-eye-scale-decr"], "pos": ["eyes/{s}-eye-scale-incr"]},
    {"id": "eyeSpacing", "group": "face", "neg": ["eyes/{s}-eye-trans-in"], "pos": ["eyes/{s}-eye-trans-out"]},
    {"id": "eyeTilt", "group": "face", "neg": ["eyes/{s}-eye-eyefold-angle-down"], "pos": ["eyes/{s}-eye-eyefold-angle-up"]},
    {"id": "browHeight", "group": "face", "neg": ["eyebrows/eyebrows-trans-down"], "pos": ["eyebrows/eyebrows-trans-up"]},
    {"id": "noseWidth", "group": "face", "neg": ["nose/nose-scale-horiz-decr"], "pos": ["nose/nose-scale-horiz-incr"]},
    {"id": "noseLength", "group": "face", "neg": ["nose/nose-scale-vert-decr"], "pos": ["nose/nose-scale-vert-incr"]},
    {"id": "noseTip", "group": "face", "neg": ["nose/nose-point-down"], "pos": ["nose/nose-point-up"]},
    {"id": "mouthWidth", "group": "face", "neg": ["mouth/mouth-scale-horiz-decr"], "pos": ["mouth/mouth-scale-horiz-incr"]},
    {"id": "lips", "group": "face", "neg": ["mouth/mouth-upperlip-volume-decr", "mouth/mouth-lowerlip-volume-decr"],
     "pos": ["mouth/mouth-upperlip-volume-incr", "mouth/mouth-lowerlip-volume-incr"]},
    {"id": "smile", "group": "face", "neg": ["mouth/mouth-angles-down"], "pos": ["mouth/mouth-angles-up"]},
    {"id": "earSize", "group": "face", "neg": ["ears/{s}-ear-scale-decr"], "pos": ["ears/{s}-ear-scale-incr"]},
]

# House style toward the approved reference (M0 style frames, user-approved S1): a slightly
# big, round head; a younger, fuller, friendlier face; bigger eyes; a hint of a smile.
STYLE_TARGETS = {
    "head/head-age-decr": 0.45, "head/head-round": 0.3, "head/head-fat-incr": 0.2,
    "head/head-scale-vert-incr": 0.3, "head/head-scale-horiz-incr": 0.25, "head/head-scale-depth-incr": 0.15,
    "cheek/{s}-cheek-volume-incr": 0.45, "cheek/{s}-cheek-bones-decr": 0.25,
    "eyes/{s}-eye-scale-incr": 0.4, "eyes/{s}-eye-bag-decr": 0.6, "eyes/{s}-eye-height2-incr": 0.25,
    "mouth/mouth-angles-up": 0.25, "mouth/mouth-scale-horiz-decr": 0.1, "mouth/mouth-scale-depth-decr": 0.25,
    "eyebrows/eyebrows-trans-up": 0.35, "eyebrows/eyebrows-angle-up": 0.6,
    "chin/chin-prominent-decr": 0.25, "chin/chin-bones-decr": 0.2, "chin/chin-width-decr": 0.15,
    "nose/nose-scale-horiz-decr": 0.2, "nose/nose-point-up": 0.25, "nose/nose-volume-decr": 0.2,
}


def expand(name):
    """'cheek/{s}-cheek-volume-incr' → both sides; plain names unchanged."""
    return [name.format(s=s) for s in ("l", "r")] if "{s}" in name else [name]


def macro_target_names():
    """Every macro corner target file (relative to data/targets, without .target.gz)."""
    ages = ("baby", "child", "young", "old")
    mus = ("minmuscle", "averagemuscle", "maxmuscle")
    wts = ("minweight", "averageweight", "maxweight")
    out = []
    for r in RACES:
        for g in ("female", "male"):
            for a in ages:
                out.append("macrodetails/{}-{}-{}".format(r, g, a))
    for g in ("female", "male"):
        for a in ages:
            for m in mus:
                for w in wts:
                    out.append("macrodetails/universal-{}-{}-{}-{}".format(g, a, m, w))
                    for h in ("minheight", "maxheight"):
                        out.append("macrodetails/height/{}-{}-{}-{}-{}".format(g, a, m, w, h))
                    for p in ("uncommonproportions", "idealproportions"):
                        out.append("macrodetails/proportions/{}-{}-{}-{}-{}".format(g, a, m, w, p))
                    if g == "female":
                        for c in ("mincup", "averagecup", "maxcup"):
                            for f in ("minfirmness", "averagefirmness", "maxfirmness"):
                                out.append("breast/{}-{}-{}-{}-{}-{}".format(g, a, m, w, c, f))
    return out


def slider_target_names():
    names = []
    for s in SLIDERS:
        for side in ("neg", "pos"):
            for t in s[side]:
                for e in expand(t):
                    if e not in names:
                        names.append(e)
    return names
