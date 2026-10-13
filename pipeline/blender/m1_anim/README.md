# M1 probe P6: animation clips on the canonical `game_engine` rig

Rotation-only clips retargeted from three free sources onto our skeleton, with the bake-off
evidence in `docs/bakeoff/P6/` (decisions and scores: `docs/bakeoff/P6/P6.md`).

Output: **`public/m1/anim/clips.glb`** (830 KB): the canonical armature (53 bones), the
MakeHuman `female1605` proxy body skinned to it (CC0, 1605 vertices, the T22 base-body
candidate) and nine named animations. `public/m1/anim/clips.json` has the per-clip metadata
(also stored as `extras` on each glTF animation).

| clip | source | frames @30 fps | s | kind | notes |
|---|---|---|---|---|---|
| `idle` | CMU 113_21 "Standing Still" | 92 | 3.03 | loop | relaxed stand, breathing sway |
| `walk` | CMU 113_25 "Walk" | 39 | 1.27 | loop | one gait cycle (2 steps), in place |
| `sit` | Mesh2Motion `Sitting_Idle` | 63 | 2.07 | loop | seated, hands on knees |
| `sit_down` | Mesh2Motion `Sitting_Enter` | 50 | 1.63 | once | ends exactly on `sit` frame 0 |
| `arms_up` | CMU 113_23 "Stretch and yawn" | 229 | 7.60 | once | both arms overhead and back down |
| `wave` | CMU 113_27 "Wave" | 19 | 0.60 | loop | one right-hand wave oscillation |
| `run` | Mesh2Motion `Run_Female` | 26 | 0.83 | loop | optional |
| `crouch` | Mesh2Motion `Crouch_Idle` | 111 | 3.67 | loop | optional |
| `arms_crossed` | Mesh2Motion `Idle_FoldArms` | 76 | 2.50 | loop | optional |

## Regenerate

```bash
pipeline/blender/m1_anim/run_all.sh          # everything below, in order
```

| step | command | does |
|---|---|---|
| 0 | `~/ml-env/bin/python -I fetch_sources.py` | downloads pinned files into `_downloads/<source>/` (git-ignored), sha256-checked |
| 1 | `blender -b --python 10_retarget.py -- [--only idle,walk] [--source cmu]` | every job in `jobs.py` -> `_work/clips/*.json`, `_work/metrics.json`, `canonical_rest.json` |
| 2 | `gpu-lease run m1-anim -- blender -b --python 20_render.py` | filmstrips (front + side) of every clip on the skinned default body, Cycles CUDA |
| 2b | `22_closeups.py`, `preview.py refpose:*` | hand/foot close-ups; our rig posed into each source's rest |
| 3 | `~/ml-env/bin/python -I 21_compose.py` | contact sheets -> `docs/bakeoff/P6/*.jpg` |
| 4 | `blender -b --python 30_export.py` | winners (`jobs.WINNERS`) -> `public/m1/anim/clips.glb` + `clips.json` |
| 5 | `node check_glb.mjs` | loads the GLB in Babylon (NullEngine): names, durations, channels, FK pose check |

Blender = the pinned portable 5.2.2 (`~/opt/blender-5.2.2-linux-x64/blender`), batch mode,
MPFB 2.0.18 from the user config. Nothing here touches the persistent MCP Blender. Each step is
deterministic for the same downloads. A full run takes a few minutes; the Cycles renders
dominate (RTX 4080).

Files: `lib_anim.py` (canonical rig, source readers, retarget, cleanup, FK, metrics),
`maps.py` (bone maps), `jobs.py` (every candidate clip + its cleanup recipe + the winners),
`lib_stage.py` (filmstrip renders under the shared stage lights of `../lib_render.py`).

## Sources and licences

Downloads are data: parsed by our own GLB and ASF/AMC readers, never executed, kept out of git.

| source | what we use | licence (where the text is) |
|---|---|---|
| **Mesh2Motion** `github.com/Mesh2Motion/mesh2motion-app` @ `653a969` | `static/animations/human-base-animations.glb`, `human-addon-animations.glb` | art (models, rigs, animations) **CC0 1.0** (`LICENSE-CC0.MD`; README "Licenses"); code MIT (`LICENSE-MIT.MD`, not used). Not used: `human-mocap-animations.glb` (its CMU sample folder points at a third-party itch pack; provenance unclear) |
| **KayKit** Character Pack: Adventurers 1.0, Kay Lousberg, `github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0` @ `672074b` | `Characters/gltf/Rogue.glb` (75 clips on the KayKit rig) | **CC0 1.0** (`LICENSE.txt`). The separate 133-clip "KayKit Character Animations" pack is itch.io-only (no scripted download); it uses the same chibi rig family, so the verdict below should carry over |
| **CMU Graphics Lab Motion Capture Database** `mocap.cs.cmu.edu` | original ASF/AMC of subject 113 (female): trials 07, 15, 21, 23, 25, 27 | home page: "This dataset of motions is free for all uses ... You may include this data in commercially-sold products, but you may not resell this data directly, even in converted form." Acknowledgement requested: "The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217." |

Not used (licence): Quaternius, Mixamo, LAFAN1, AMASS, Bandai Namco.

### CMU frame rate (measured, not trusted)

The CMU site lists every trial used here at 120 fps. That is right for subject 113 (its walk:
94 steps/min, 1.0 m/s) but **not** for subject 141 (explored first): at 120 fps its walks run at
220 steps/min and 2.4 m/s; at 60 fps they are 111 steps/min, 1.23 m/s, 1.33 m stride. The
reader therefore takes the rate per subject (`lib_anim.CMU_FPS`), measured from walk cadence.

## Conventions

**Canonical rest.** `HumanService.create_human(mask_helpers=True, detailed_helpers=True,
extra_vertex_groups=True, feet_on_ground=True, scale=0.1)` with no macro dict (MPFB defaults),
then `HumanService.add_builtin_rig(basemesh, "game_engine")`. Its bind pose is MakeHuman's
A-pose. `canonical_rest.json` records every bone's head/tail and parent-relative rotation and
translation (Blender armature space: +Z up, character faces -Y, left = +X). Bones are never
edited.

**Clip channels.** Every clip carries a rotation channel for all 53 bones, absolute local
rotations against that rest (glTF node rotation = rest rotation x pose), and a translation
channel on `pelvis` only. No scale channels, no other translations: the runtime keeps each
body's own bone translations. In the GLB, child joints are stored in their parent bone's frame
exactly as in Blender; the parent-less `Root` joint carries the Z-up -> Y-up conversion
(rotation `Rx(-90 deg)`, constant in every clip). Root never moves: the runtime places the
character by the node above the skeleton.

**Pelvis translation** (the only root motion). Channel value = pelvis local translation
relative to `Root`, in Root's frame (= Blender armature space, Z up) on the neutral body.
Rest value `T_rest = (0, -0.013217, 0.874449)`; hip height (pelvis head) 0.8739 m; leg length
(hip -> ankle) 0.8020 m. For another body with hip height `h`:

    T_body(t) = T_body_rest + (h / 0.8739) * (T_clip(t) - T_rest)

The source's pelvis displacement was scaled onto the neutral body by the leg-length ratio
(target 0.802 m / source leg).

**Bone maps** (`maps.py`). Each target bone takes the world-space rotation delta of one source
joint (or a slerp blend of two), applied on top of an alignment that maps our rest onto the
source rest:
- `identity` for pelvis, spine, neck, head, clavicles, toes: both rests are "standing upright,
  relaxed"; their bone *directions* are rig-arbitrary (our pelvis bone points up-and-back).
- `swing` for upper arm, thigh, calf, foot, fingers: rotate our bone so its direction matches the
  source rest direction (their T-pose vs our A-pose).
- `frame` for forearm and hand: swing plus twist, matching the across-palm vector (pinky_01 ->
  index_01 knuckles) to the source's (Mesh2Motion: the same knuckles; KayKit and CMU, which have
  no fingers: forward, i.e. palms down in their T-pose).

| ours | Mesh2Motion | KayKit | CMU |
|---|---|---|---|
| pelvis | pelvis | hips | root |
| spine_01 / 02 / 03 | spine_01 / 02 / 03 | spine / spine+chest blend / chest | lowerback / upperback / thorax |
| neck_01, head | neck_01, head | chest+head blend, head | lowerneck+upperneck blend, head |
| clavicle | clavicle | (none) | clavicle |
| upperarm, lowerarm, hand | same | upperarm, lowerarm, wrist | humerus, **wrist** (CMU's radius is a pure hinge; the wrist bone holds forearm twist), hand |
| fingers (15/side) | same | (none: relaxed preset) | (not captured: relaxed preset) |
| thigh, calf, foot, ball | same | upperleg, lowerleg, foot, toes | femur, tibia, foot, (toes: noise, left at rest) |

Fingers without source data get a relaxed preset: a light per-joint curl toward the palm plus
part of MakeHuman's rest finger spread closed (`lib_anim.relaxed_fingers`), never rigid-flat.
`docs/bakeoff/P6/alignment.jpg` shows our rig posed into each source's rest pose.

**Cleanup** (recipes per job in `jobs.py`): in-place locomotion (linear horizontal trend removed,
bob and sway kept); feet anchored under the root; leg two-bone IK pins planted feet (idle, sit,
wave, arms_up); per-foot constant pitch so soles are level when planted; vertical offset so the
sole meets z = 0; head damping + re-levelling for CMU 113 (its head swings 50-100 deg against
the thorax in the "standing still" take); loop closure (best-matching window by joint
rotations + limb velocities, then the residual spread linearly so frame n == frame 0);
quaternion sign continuity; `sit_down` pinned to and eased into `sit` frame 0.

## Numbers the runtime needs (neutral body)

- **Stride (walk):** 1.306 m per 1.267 s cycle (two steps, 0.65 m each) = **1.03 m/s** at 1x
  playback, measured from the planted foot's backward speed. Scale the stride by the body's
  leg-length (or hip-height) ratio; playback rate = desired speed / (1.03 m/s x ratio).
  `run`: 2.31 m per 0.833 s cycle = 2.77 m/s.
- **Seat (sit, sit_down end):** seat surface **0.415 m** above the floor (lowest point of the
  thigh/buttock underside on the skinned default body); buttock contact spans 0.30-0.40 m behind
  the root (+Y), hip joints 0.38 m behind; feet stay where the standing feet are. Offset the
  root vertically by (chair seat height - 0.415 m) x body ratio.

## Known limits

See `docs/bakeoff/P6/P6.md` ("Known defects"). In short: CMU head motion is mostly synthetic
(damped + levelled); `wave` is a single 0.6 s oscillation; `sit_down` starts from a wide stance;
`arms_up` starts with the hands at the chest (source take); `arms_crossed` forearms touch the
default bust (arms swung 10 deg forward to clear most of it).
