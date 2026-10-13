"""Bone maps: target game_engine bone -> source joint, and how the two rest poses are aligned.

align:
  identity  both rests are the same posture for this bone (upright torso, relaxed shoulders):
            source rest maps to our rest untouched. Used where bone *directions* are rig-arbitrary
            (pelvis/spine bones point in different directions in every rig).
  swing     rotate our rest bone so its direction (head -> TGT_TIP joint) matches the source rest
            direction (src joint -> `tip`). Limbs: T-pose (sources) vs A-pose (ours).
  frame     swing + twist: also match a secondary vector. Forearm/hand twist uses the palm
            across-vector (pinky_01 -> index_01 knuckles); `sec_src` is a source joint pair or a
            constant (palms-down T-pose: across-palm = forward = -Y).
src may be [[joint_a, w_a], [joint_b, w_b]]: world deltas blended (slerp by w_b). Unmapped target
bones keep their rest local rotation (fingers: the relaxed-curl preset).
`{s}` = our side (l/r); `{S}` = KayKit side token; `{c}` = CMU side prefix.
"""
from lib_anim import FINGERS, expand_map

FWD = [0.0, -1.0, 0.0]

# Mesh2Motion human rig: Unreal-mannequin names like ours, T-pose rest, fingers, leaf joints.
_M2M = {
    "pelvis": {"src": "pelvis"},
    "spine_01": {"src": "spine_01"}, "spine_02": {"src": "spine_02"}, "spine_03": {"src": "spine_03"},
    "neck_01": {"src": "neck_01"}, "head": {"src": "head"},
    "clavicle_{s}": {"src": "clavicle_{s}"},
    "upperarm_{s}": {"src": "upperarm_{s}", "align": "swing", "tip": "lowerarm_{s}"},
    "lowerarm_{s}": {"src": "lowerarm_{s}", "align": "frame", "tip": "hand_{s}",
                     "sec_tgt": "palm_{s}", "sec_src": ["index_01_{s}", "pinky_01_{s}"]},
    "hand_{s}": {"src": "hand_{s}", "align": "frame", "tip": "middle_01_{s}",
                 "sec_tgt": "palm_{s}", "sec_src": ["index_01_{s}", "pinky_01_{s}"]},
    "thigh_{s}": {"src": "thigh_{s}", "align": "swing", "tip": "calf_{s}"},
    "calf_{s}": {"src": "calf_{s}", "align": "swing", "tip": "foot_{s}"},
    "foot_{s}": {"src": "foot_{s}", "align": "swing", "tip": "ball_{s}"},
    "ball_{s}": {"src": "ball_{s}"},
}
for _f in FINGERS:
    for _k in (1, 2, 3):
        _tip = "%s_0%d_{s}" % (_f, _k + 1) if _k < 3 else "%s_04_leaf_{s}" % _f
        _M2M["%s_0%d_{s}" % (_f, _k)] = {"src": "%s_0%d_{s}" % (_f, _k), "align": "swing", "tip": _tip}
M2M = expand_map(_M2M)

# KayKit Adventurers rig ("Rig"): hips/spine/chest/head, upperarm/lowerarm/wrist/hand, no neck,
# no fingers (mitten hands). Chibi proportions (hips 0.41 m).
_KK = {
    "pelvis": {"src": "hips"},
    "spine_01": {"src": "spine"},
    "spine_02": {"src": [["spine", 0.5], ["chest", 0.5]]},
    "spine_03": {"src": "chest"},
    "neck_01": {"src": [["chest", 0.5], ["head", 0.5]]},
    "head": {"src": "head"},
    "upperarm_{s}": {"src": "upperarm.{S}", "align": "swing", "tip": "lowerarm.{S}"},
    "lowerarm_{s}": {"src": "lowerarm.{S}", "align": "frame", "tip": "wrist.{S}",
                     "sec_tgt": "palm_{s}", "sec_src": FWD},
    "hand_{s}": {"src": "wrist.{S}", "align": "frame", "tip": "hand.{S}",
                 "sec_tgt": "palm_{s}", "sec_src": FWD},
    "thigh_{s}": {"src": "upperleg.{S}", "align": "swing", "tip": "lowerleg.{S}"},
    "calf_{s}": {"src": "lowerleg.{S}", "align": "swing", "tip": "foot.{S}"},
    "foot_{s}": {"src": "foot.{S}", "align": "swing", "tip": "toes.{S}"},
    "ball_{s}": {"src": "toes.{S}"},
}
KAYKIT = expand_map(_KK)

# CMU ASF (Vicon): root/lowerback/upperback/thorax/lowerneck/upperneck/head, clavicle/humerus/
# radius/wrist(twist)/hand, femur/tibia/foot/toes. Fingers/thumb are not captured (CMU note).
_CMU = {
    "pelvis": {"src": "root"},
    "spine_01": {"src": "lowerback"}, "spine_02": {"src": "upperback"}, "spine_03": {"src": "thorax"},
    "neck_01": {"src": [["lowerneck", 0.5], ["upperneck", 0.5]]},
    "head": {"src": "head"},
    "clavicle_{s}": {"src": "{c}clavicle"},
    "upperarm_{s}": {"src": "{c}humerus", "align": "swing", "tip": "{c}humerus.tail"},
    # CMU's radius is a pure hinge; forearm twist lives in the 'wrist' bone (collinear with it)
    "lowerarm_{s}": {"src": "{c}wrist", "align": "frame", "tip": "{c}wrist.tail",
                     "sec_tgt": "palm_{s}", "sec_src": FWD},
    "hand_{s}": {"src": "{c}hand", "align": "frame", "tip": "{c}hand.tail",
                 "sec_tgt": "palm_{s}", "sec_src": FWD},
    "thigh_{s}": {"src": "{c}femur", "align": "swing", "tip": "{c}femur.tail"},
    "calf_{s}": {"src": "{c}tibia", "align": "swing", "tip": "{c}tibia.tail"},
    "foot_{s}": {"src": "{c}foot", "align": "swing", "tip": "{c}foot.tail"},
    "ball_{s}": {"src": "{c}toes"},
}
CMU = expand_map(_CMU)

MAPS = {"m2m": M2M, "kaykit": KAYKIT, "cmu": CMU}

# Joints compared by the loop finder (first = root; positions taken relative to it).
LOOP_JOINTS = {
    "m2m": ["pelvis", "hand_l", "hand_r", "middle_01_l", "middle_01_r", "head", "head_leaf", "foot_l", "foot_r",
            "ball_l", "ball_r", "spine_03", "lowerarm_l", "lowerarm_r", "calf_l", "calf_r"],
    "cmu": ["root", "lhand", "rhand", "lhand.tail", "rhand.tail", "head", "head.tail", "lfoot", "rfoot",
            "lfoot.tail", "rfoot.tail", "thorax", "lradius", "rradius", "ltibia", "rtibia"],
    "kaykit": ["hips", "hand.l", "hand.r", "handslot.l", "handslot.r", "head", "foot.l", "foot.r", "toes.l",
               "toes.r", "chest", "lowerarm.l", "lowerarm.r", "lowerleg.l", "lowerleg.r"],
}


def leg_length(mname, src):
    """Hip -> ankle chain length of a source at rest (m), for the pelvis displacement scale."""
    r = src.rest()
    if mname == "cmu":
        return (r["lfemur.tail"][0] - r["lfemur"][0]).length + (r["ltibia.tail"][0] - r["ltibia"][0]).length
    j = {"m2m": ("thigh_l", "calf_l", "foot_l"), "kaykit": ("upperleg.l", "lowerleg.l", "foot.l")}[mname]
    return (r[j[1]][0] - r[j[0]][0]).length + (r[j[2]][0] - r[j[1]][0]).length
