"""Named check animations (hands / fingers / mouth / expressions / speech) as Blender actions + one concatenated timeline.
Pose segments (SEGMENTS) are keyed from a few states and eased with Bezier curves; the fingers close with a natural cascade (index first,
little finger last, the knuckle joint before the middle and tip joints). The speech segment is procedural (speech.py): per-frame curves
with co-articulation plus breathing, weight shift, nods, a bow and hand gestures."""
from common import *
import rig_poses as rp
import speech
from mouth_keys import KEY_NAMES
from mathutils import Euler, Quaternion

FPS = 24
FINGER_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
FINGER_DELAY = {"Thumb": 0, "Index": 0, "Middle": 1, "Ring": 2, "Pinky": 3}      # frames
JOINT_DELAY = (0, 1, 2)                                                           # knuckle, middle joint, tip joint


def neutral():
    return dict(R=dict(Thumb=0, Index=0, Middle=0, Ring=0, Pinky=0, spread=0), L=dict(Thumb=0, Index=0, Middle=0, Ring=0, Pinky=0, spread=0), keys={})


def state(**kw):
    s = neutral()
    for k, v in kw.items():
        if k == "keys":
            s["keys"] = dict(v)
        else:
            s[k] = v
    return s


def fist_state(amount=1.0):
    h = dict(Thumb=amount, Index=amount, Middle=amount, Ring=amount, Pinky=amount, spread=0)
    return dict(R=dict(h), L=dict(h), keys={})


def single_finger(side, finger, amount=1.0):
    s = neutral()
    s[side][finger] = amount
    return s


def point_state():
    h = dict(Thumb=0.8, Index=0, Middle=1, Ring=1, Pinky=1, spread=0)
    return dict(R=dict(h), L=dict(h), keys={})


def peace_state():
    h = dict(Thumb=0.9, Index=0, Middle=0, Ring=1, Pinky=1, spread=9.0)
    return dict(R=dict(h), L=dict(h), keys={})


def keys_state(**k):
    s = neutral()
    s["keys"] = k
    return s


# every segment: list of (frame_offset, state); the first key is always the neutral A-pose
SEGMENTS = {}


def _seg(name, keys):
    SEGMENTS[name] = keys


_seg("Hands_OpenCloseOpen", [(0, neutral()), (10, neutral()), (22, fist_state()), (32, fist_state()), (46, neutral()), (56, neutral())])
fi = []
t = 0
fi.append((0, neutral()))
t = 6
for side in ("R", "L"):
    for f in FINGER_ORDER:
        fi.append((t, neutral()))
        fi.append((t + 6, single_finger(side, f)))
        fi.append((t + 10, single_finger(side, f)))
        fi.append((t + 16, neutral()))
        t += 18
fi.append((t + 6, neutral()))
_seg("Fingers_Individual", fi)
_seg("Point_Peace", [(0, neutral()), (6, neutral()), (18, point_state()), (34, point_state()), (46, neutral()), (52, neutral()),
                     (64, peace_state()), (84, peace_state()), (96, neutral()), (102, neutral())])
_seg("Mouth_OpenClose", [(0, neutral()), (6, neutral()), (16, keys_state(jawOpen=1.0)), (26, keys_state(jawOpen=1.0)), (36, neutral()),
                         (42, neutral()), (50, keys_state(mouthClose=1.0)), (58, keys_state(mouthClose=1.0)), (66, neutral()),
                         (72, keys_state(jawOpen=0.12)), (80, keys_state(jawOpen=0.12, mouthClose=1.0)), (88, keys_state(jawOpen=0.12, mouthClose=1.0)), (96, neutral()), (102, neutral())])
vk = []
tt = 6
vk.append((0, neutral()))
vk.append((6, neutral()))
for v in ("viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O"):
    vk.append((tt + 6, keys_state(**{v: 1.0})))
    vk.append((tt + 14, keys_state(**{v: 1.0})))
    vk.append((tt + 20, neutral()))
    tt += 22
vk.append((tt + 6, neutral()))
_seg("Vowels_AIUEO", vk)
_seg("Smile_Normal", [(0, neutral()), (6, neutral()), (18, keys_state(mouthSmile=1.0)), (36, keys_state(mouthSmile=1.0)), (48, neutral()), (56, neutral())])
# facial expression tour: every step eases in (5 frames), holds (5) and eases out (5)
EXPR_STEPS = [
    dict(mouthSmileLeft=1.0), dict(mouthSmileRight=1.0), dict(mouthSmileLeft=1.0, mouthSmileRight=1.0),
    dict(mouthFrownLeft=1.0), dict(mouthFrownRight=1.0), dict(mouthFrownLeft=1.0, mouthFrownRight=1.0),
    dict(mouthStretchLeft=1.0, mouthStretchRight=1.0, jawOpen=0.18),
    dict(mouthPucker=1.0), dict(mouthFunnel=1.0),
    dict(mouthLeft=1.0, jawOpen=0.28), dict(mouthRight=1.0, jawOpen=0.28),
    dict(mouthUpperUpLeft=1.0, mouthUpperUpRight=1.0, jawOpen=0.25), dict(mouthLowerDownLeft=1.0, mouthLowerDownRight=1.0, jawOpen=0.25),
    dict(jawForward=1.0, jawOpen=0.3), dict(jawLeft=1.0, jawOpen=0.3), dict(jawRight=1.0, jawOpen=0.3),
    dict(cheekPuff=1.0), dict(jawOpen=0.8, tongueOut=1.0), dict(jawOpen=0.8, tongueUp=1.0),
]
ex = [(0, neutral()), (6, neutral())]
t = 6
for stp in EXPR_STEPS:
    ex.append((t + 5, keys_state(**stp)))
    ex.append((t + 10, keys_state(**stp)))
    ex.append((t + 15, neutral()))
    t += 16
ex.append((t + 2, neutral()))
_seg("Expressions", ex)

ORDER = ["Hands_OpenCloseOpen", "Fingers_Individual", "Point_Peace", "Mouth_OpenClose", "Vowels_AIUEO", "Smile_Normal", "Expressions", "Speech_Gestures"]
PROCEDURAL = {"Speech_Gestures"}
ARM_ACTIONS = ["Hands_OpenCloseOpen", "Fingers_Individual", "Point_Peace", "Speech_Gestures"]
KEY_ACTIONS = ["Mouth_OpenClose", "Vowels_AIUEO", "Smile_Normal", "Expressions", "Speech_Gestures"]
TITLES = {"Hands_OpenCloseOpen": "Hands: open -> fist -> open", "Fingers_Individual": "Fingers: bend each finger", "Point_Peace": "Index point / Peace sign",
          "Mouth_OpenClose": "Mouth: close -> open -> close", "Vowels_AIUEO": "Vowels: A I U E O", "Smile_Normal": "Smile -> normal",
          "Expressions": "Mouth expressions (fine controls)", "Speech_Gestures": "Speech + gestures + breathing"}
BODY_BONES = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand"]
_SPEECH = {}


def speech_data():
    if "d" not in _SPEECH:
        _SPEECH["d"] = speech.build()
    return _SPEECH["d"]


def seg_length(name):
    if name in PROCEDURAL:
        return speech_data()["n"] - 1
    return max(f for f, _ in SEGMENTS[name])


def segment_table():
    """[(name, first_frame, last_frame)] of the concatenated timeline (1-based, inclusive)."""
    out, t = [], 0
    for name in ORDER:
        out.append((name, t + 1, t + seg_length(name) + 1))
        t += seg_length(name) + 1
    return out


def apply_state(arm, mesh, st):
    rp.reset_pose(arm)
    hand_info = rp.hand_info(arm)
    for side in "LR":
        h = st[side]
        for f in rp.FINGERS:
            rp.finger_pose(arm, side, f, h[f], spread_deg=(h["spread"] if f == "Index" else (-h["spread"] if f == "Middle" else 0.0)), hand=hand_info[side])
        rp.thumb_pose(arm, side, h["Thumb"])
    rp.set_keys(mesh, **st["keys"])


def finger_bones(arm):
    return [pb for pb in arm.pose.bones if "Hand" in pb.name and any(k in pb.name for k in ("Thumb", "Index", "Middle", "Ring", "Pinky"))]


def key_delay(name):
    """Frames by which the keys of a finger bone are delayed: little finger after the index finger, tip joint after the knuckle."""
    for f, d in FINGER_DELAY.items():
        if f in name:
            return d + JOINT_DELAY[min(2, max(0, int(name[-1]) - 1))] if name[-1] in "123" else d
    return 0


def set_euler_world(pb, rx, ry, rz, twist=0.0):
    """Rotation of a pose bone: Euler angles (degrees) about the world x / y / z axes, expressed in the bone's rest frame, then an optional
    twist (degrees) about the bone's own long axis."""
    m = pb.bone.matrix_local.to_3x3()
    q_w = Euler((np.radians(rx), np.radians(ry), np.radians(rz)), "XYZ").to_matrix()
    q = (m.inverted() @ q_w @ m).to_quaternion()
    if twist:
        q = q @ Quaternion((0, 1, 0), np.radians(twist))
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = q


def apply_frame(arm, mesh, hand_info, d, i):
    """Pose for frame i of the procedural speech data."""
    rp.reset_pose(arm)
    for side in "LR":
        for f in rp.FINGERS:
            sp = d["hands"][(side, "spread")][i]
            rp.finger_pose(arm, side, f, float(d["hands"][(side, f)][i]), spread_deg=(sp if f == "Index" else (-sp if f == "Middle" else 0.0)), hand=hand_info[side])
        rp.thumb_pose(arm, side, float(d["hands"][(side, "Thumb")][i]))
    for bone, arr in d["body"].items():
        pb = arm.pose.bones[bone]
        tw = 0.0
        if bone == "RightForeArm":
            tw = float(d["roll"]["R"][i])
        elif bone == "LeftForeArm":
            tw = -float(d["roll"]["L"][i])
        if bone in ("RightHand", "LeftHand"):
            # the hand follows the finger pose written above; add the body rotation on top of the (identity) bone pose
            pass
        set_euler_world(pb, *[float(x) for x in arr[i]], twist=tw)
    rp.set_keys(mesh, **{k: float(v[i]) for k, v in d["keys"].items()})


def build_actions(arm, mesh):
    """Create all actions. Returns dict name->(arm_action or None, key_action or None)."""
    fbones = finger_bones(arm)
    bbones = [arm.pose.bones[n] for n in BODY_BONES]
    kb = mesh.data.shape_keys
    hand_info = rp.hand_info(arm)
    if arm.animation_data is None:
        arm.animation_data_create()
    if kb.animation_data is None:
        kb.animation_data_create()
    out = {}

    def write(seg_names, offset_list, arm_name, key_name):
        a_act = bpy.data.actions.new(arm_name) if arm_name else None
        k_act = bpy.data.actions.new(key_name) if key_name else None
        if a_act:
            arm.animation_data.action = a_act
        if k_act:
            kb.animation_data.action = k_act
        for seg, off in zip(seg_names, offset_list):
            if seg in PROCEDURAL:
                d = speech_data()
                for i in range(d["n"]):
                    apply_frame(arm, mesh, hand_info, d, i)
                    f = off + i + 1
                    if a_act:
                        for pb in fbones + bbones:
                            pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
                    if k_act:
                        for kname in KEY_NAMES:
                            kb.key_blocks[kname].keyframe_insert("value", frame=f)
                continue
            for fr, st in SEGMENTS[seg]:
                apply_state(arm, mesh, st)
                f = off + fr + 1
                if a_act and seg in ARM_ACTIONS:
                    for pb in fbones:
                        pb.keyframe_insert("rotation_quaternion", frame=f + key_delay(pb.name), group=pb.name)
                if k_act and seg in KEY_ACTIONS:
                    for kname in KEY_NAMES:
                        kb.key_blocks[kname].keyframe_insert("value", frame=f)
        for act in (a_act, k_act):
            if act:
                act.use_fake_user = True
                for fc in act.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "BEZIER"
                        kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        return a_act, k_act

    for name in ORDER:
        out[name] = write([name], [0], name if name in ARM_ACTIONS else None, (name + "_Keys") if name in KEY_ACTIONS else None)
    # concatenated timeline for the export / video
    offs, t = [], 0
    for name in ORDER:
        offs.append(t)
        t += seg_length(name) + 1
    out["Check_All"] = write(ORDER, offs, "Check_All", "Check_All_Keys")
    arm.animation_data.action = None
    kb.animation_data.action = None
    rp.reset_pose(arm)
    rp.set_keys(mesh)
    return out, offs, t


def build_nla(arm, mesh, actions):
    """One NLA track per named animation (strips start at frame 1) on the armature and on the shape keys. Muted so that the model
    opens in the A-pose."""
    kb = mesh.data.shape_keys
    for name in ORDER:
        a_act, k_act = actions[name]
        if a_act:
            tr = arm.animation_data.nla_tracks.new()
            tr.name = name
            st = tr.strips.new(name, 1, a_act)
            tr.mute = True
        if k_act:
            tr = kb.animation_data.nla_tracks.new()
            tr.name = name
            st = tr.strips.new(name, 1, k_act)
            tr.mute = True
