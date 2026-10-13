"""P6 job table: every (clip, source) candidate, its source window and its cleanup recipe.

src:     ("glb", <path under _downloads>, <animation name>) | ("cmu", "<subject>_<trial>")
wrap:    glTF clip is cyclic without a duplicated end key (Mesh2Motion "addon" set): sample
         past the last key back into the first, loop period = key count x dt
window:  None = whole glTF animation | (t0, t1) seconds | ("find", t_lo, t_hi, p_min, p_max)
         = best-matching loop (lib_anim.find_loop) with start in [t_lo, t_hi], period in [p_min, p_max]
yaw:     "none" | "auto" (mean pelvis facing -> -Y) | "travel" (walk direction -> -Y) | degrees
kind:    "loop" | "once"
clean:   ordered cleanup ops (10_retarget.py `apply_clean`). Loops close BEFORE any IK / ground /
         toe step: those are deterministic per frame, so frame n stays == frame 0, while spreading
         a loop residual after IK would un-pin the feet.
         inplace      remove horizontal travel (walk/run), keep bob + sway
         anchor_feet  shift the clip horizontally so the planted feet sit where the rest feet are
         level_head   remove the clip-mean head/neck tilt (CMU subjects look up/down in the lab)
         damp_head:k  keep only k of the neck/head local deviation from the clip mean (CMU 113's
                      head swings 50-100 deg vs the thorax while "standing still": neck rolls or a
                      poor head solve)
         flatten      constant per-foot pitch fix so the sole is level when planted
         pin_feet     two-bone leg IK: ankles + foot orientation held at their mean (planted clips)
         pin_rest     same, but to the canonical rest stance
         pin_under    hip-width rest stance centred under the clip-mean pelvis (CMU wave: her right
                      ankle sits ~10 cm above her left one throughout the take)
         arms_fwd:d   swing both upper arms forward by d degrees (world X axis at the shoulder)
         ground_min   lowest sole point (heel/ball/toe) over the clip touches z = 0
         ground_min_hb  lowest heel/ball point touches z = 0 (locomotion; then toe_floor)
         toe_floor    bend the toes so the toe tip never dips below the floor (toe-off roll)
         plant_feet   per-foot IK pin so EACH planted foot's mean lowest sole point is on the floor
         ground_mean  mean lowest sole point = 0 (planted clips)
         close_loop   spread the end-vs-start residual so frame n == frame 0
         pin_to:K     pin the feet where clip K (built earlier) has them on its first frame
         blend_end_to:K:k  ease the last k frames into clip K's first frame (seamless hand-over)
         smooth_hands 1-2-1 smoothing of hand rotations (CMU hands are noisy)
winner:  the source whose result is exported under the clip's name (see docs/bakeoff/P6/P6.md).
"""

M2M_BASE = "m2m/human-base-animations.glb"
M2M_ADDON = "m2m/human-addon-animations.glb"
KK = "kaykit/Rogue.glb"

LOOP_CLEAN = ["anchor_feet", "flatten", "close_loop", "pin_feet", "ground_mean", "plant_feet"]
CMU_LOOP_CLEAN = ["anchor_feet", "damp_head:0.2", "level_head", "smooth_hands", "flatten", "close_loop", "pin_feet",
                  "ground_mean", "plant_feet"]
WALK_CLEAN = ["inplace", "flatten_stance", "close_loop", "ground_min_hb", "toe_floor"]
CMU_WALK_CLEAN = ["inplace", "level_head", "smooth_hands", "flatten_stance", "close_loop", "ground_min_hb", "toe_floor"]

JOBS = [
    # ---- idle --------------------------------------------------------------------------------
    {"clip": "idle", "source": "cmu", "src": ("cmu", "113_21"), "window": ("find", 0.5, 6.0, 3.0, 4.0),
     "yaw": "auto", "kind": "loop", "clean": CMU_LOOP_CLEAN},
    {"clip": "idle", "source": "m2m", "src": ("glb", M2M_ADDON, "Idle_Subtle"), "wrap": True, "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "idle", "source": "m2m_a", "src": ("glb", M2M_BASE, "Idle_A"), "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "idle", "source": "kaykit", "src": ("glb", KK, "Idle"), "kind": "loop", "clean": LOOP_CLEAN},
    # ---- walk --------------------------------------------------------------------------------
    {"clip": "walk", "source": "cmu", "src": ("cmu", "113_25"), "window": ("find", 0.9, 1.4, 1.15, 1.40),
     "yaw": "travel", "kind": "loop", "clean": CMU_WALK_CLEAN},
    {"clip": "walk", "source": "m2m", "src": ("glb", M2M_BASE, "Walk"), "kind": "loop", "clean": WALK_CLEAN},
    {"clip": "walk", "source": "m2m_female", "src": ("glb", M2M_ADDON, "Walk_Female"), "wrap": True, "kind": "loop", "clean": WALK_CLEAN},
    {"clip": "walk", "source": "kaykit", "src": ("glb", KK, "Walking_A"), "kind": "loop", "clean": WALK_CLEAN},
    # ---- sit (seated idle) + sit_down --------------------------------------------------------
    {"clip": "sit", "source": "m2m", "src": ("glb", M2M_BASE, "Sitting_Idle"), "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "sit", "source": "cmu", "src": ("cmu", "113_15"), "window": ("find", 2.8, 3.3, 1.0, 1.6),
     "yaw": "auto", "kind": "loop", "clean": CMU_LOOP_CLEAN},
    {"clip": "sit", "source": "kaykit", "src": ("glb", KK, "Sit_Chair_Idle"), "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "sit_down", "source": "m2m", "src": ("glb", M2M_BASE, "Sitting_Enter"), "kind": "once",
     "clean": ["anchor_feet_end", "flatten", "pin_to:sit__m2m", "ground_mean", "blend_end_to:sit__m2m:8"]},
    {"clip": "sit_down", "source": "cmu", "src": ("cmu", "113_15"), "window": (1.4, 2.8), "yaw": "end",
     "kind": "once", "clean": ["anchor_feet_end", "damp_head:0.3", "level_head_end", "smooth_hands", "flatten", "pin_feet", "ground_mean"]},
    {"clip": "sit_down", "source": "kaykit", "src": ("glb", KK, "Sit_Chair_Down"), "kind": "once",
     "clean": ["anchor_feet_end", "flatten", "pin_feet", "ground_mean"]},
    # ---- arms_up (stress pose, one-shot) -----------------------------------------------------
    {"clip": "arms_up", "source": "cmu", "src": ("cmu", "113_23"), "window": (0.0, 7.6), "yaw": "auto",
     "kind": "once", "clean": ["anchor_feet", "damp_head:0.3", "level_head", "smooth_hands", "flatten", "pin_feet", "ground_mean",
                               "plant_feet"]},
    {"clip": "arms_up", "source": "kaykit", "src": ("glb", KK, "Cheer"), "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "arms_up", "source": "m2m", "src": ("glb", M2M_ADDON, "Jumping Jacks"), "wrap": True, "kind": "loop",
     "clean": ["anchor_feet", "close_loop", "ground_min_hb", "toe_floor"]},
    # ---- wave (loop) -------------------------------------------------------------------------
    {"clip": "wave", "source": "m2m", "src": ("glb", M2M_ADDON, "Greeting"), "window": ("find", 1.4, 2.6, 0.5, 1.4),
     "kind": "loop", "clean": LOOP_CLEAN},
    {"clip": "wave", "source": "cmu", "src": ("cmu", "113_27"), "window": ("find", 0.75, 0.95, 0.6, 0.85),
     "yaw": "auto", "kind": "loop", "clean": ["damp_head:0.3", "level_head", "smooth_hands", "close_loop", "pin_under", "anchor_feet", "ground_mean",
               "plant_feet"]},
    # ---- optional ----------------------------------------------------------------------------
    {"clip": "run", "source": "m2m", "src": ("glb", M2M_ADDON, "Run_Female"), "wrap": True, "kind": "loop", "clean": WALK_CLEAN},
    {"clip": "run", "source": "cmu", "src": ("cmu", "113_07"), "window": ("find", 0.8, 2.0, 0.55, 0.85),
     "yaw": "travel", "kind": "loop", "clean": CMU_WALK_CLEAN},
    {"clip": "run", "source": "kaykit", "src": ("glb", KK, "Running_A"), "kind": "loop", "clean": WALK_CLEAN},
    {"clip": "crouch", "source": "m2m", "src": ("glb", M2M_BASE, "Crouch_Idle"), "kind": "loop",
     "clean": ["anchor_feet", "close_loop", "pin_feet", "ground_min", "plant_feet"]},  # back foot on its toes: no flatten
    {"clip": "arms_crossed", "source": "m2m", "src": ("glb", M2M_BASE, "Idle_FoldArms"), "kind": "loop",
     "clean": ["arms_fwd:10"] + LOOP_CLEAN},  # source mannequin is flat-chested: clear the default bust
]

# Filled in from the bake-off (docs/bakeoff/P6/P6.md). Exported clip name -> source key.
WINNERS = {
    "idle": "cmu", "walk": "cmu", "sit": "m2m", "sit_down": "m2m", "arms_up": "cmu", "wave": "cmu",
    "run": "m2m", "crouch": "m2m", "arms_crossed": "m2m",
}
