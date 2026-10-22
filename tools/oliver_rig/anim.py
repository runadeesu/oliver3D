"""Named check animations (hands / fingers / mouth) as Blender actions + one concatenated timeline."""
from common import *
import rig_poses as rp

FPS = 24
FINGER_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


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
ORDER = ["Hands_OpenCloseOpen", "Fingers_Individual", "Point_Peace", "Mouth_OpenClose", "Vowels_AIUEO", "Smile_Normal"]
ARM_ACTIONS = ["Hands_OpenCloseOpen", "Fingers_Individual", "Point_Peace"]
KEY_ACTIONS = ["Mouth_OpenClose", "Vowels_AIUEO", "Smile_Normal"]
KEY_NAMES = ["jawOpen", "mouthClose", "viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O", "mouthSmile"]


def seg_length(name):
    return max(f for f, _ in SEGMENTS[name])


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


def build_actions(arm, mesh):
    """Create all actions. Returns dict name->(arm_action or None, key_action or None)."""
    bones = finger_bones(arm)
    kb = mesh.data.shape_keys
    if arm.animation_data is None:
        arm.animation_data_create()
    if kb.animation_data is None:
        kb.animation_data_create()
    out = {}

    def write(seg_names, names, offset_list, arm_name, key_name):
        a_act = bpy.data.actions.new(arm_name) if arm_name else None
        k_act = bpy.data.actions.new(key_name) if key_name else None
        if a_act:
            arm.animation_data.action = a_act
        if k_act:
            kb.animation_data.action = k_act
        for seg, off in zip(seg_names, offset_list):
            for fr, st in SEGMENTS[seg]:
                apply_state(arm, mesh, st)
                f = off + fr + 1
                if a_act:
                    for pb in bones:
                        pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
                if k_act:
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

    for name in ARM_ACTIONS:
        out[name] = write([name], None, [0], name, None)
    for name in KEY_ACTIONS:
        out[name] = write([name], None, [0], None, name + "_Keys")
    # concatenated timeline for the export / video
    offs, t = [], 0
    for name in ORDER:
        offs.append(t)
        t += seg_length(name) + 1
    out["Check_All"] = write(ORDER, None, offs, "Check_All", "Check_All_Keys")
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
