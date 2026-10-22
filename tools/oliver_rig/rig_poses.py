"""Pose helpers for the rigged model (finger fist/point/peace, mouth keys, body) usable for tests and for building actions."""
import json
from common import *
from mathutils import Quaternion

SIDES = {"L": "Left", "R": "Right"}
FINGERS = ["Index", "Middle", "Ring", "Pinky"]
FIST = {"Index": (78, 100, 62), "Middle": (80, 102, 62), "Ring": (82, 100, 60), "Pinky": (84, 98, 58)}


def find_rig():
    arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    mesh = [o for o in bpy.data.objects if o.type == "MESH"][0]
    return arm, mesh


def hand_info(arm):
    return json.loads(arm["oliver_hands"])


def set_rot_world(pb, axis_world, angle_deg):
    """Rotate pose bone about a world-space axis (valid for the REST orientation of its parent chain)."""
    m = pb.bone.matrix_local.to_3x3().inverted()
    ax = (m @ Vector(axis_world)).normalized()
    pb.rotation_mode = "QUATERNION"
    q = Quaternion(ax, np.radians(angle_deg))
    pb.rotation_quaternion = q


def rest_dir(pb):
    return (pb.bone.tail_local - pb.bone.head_local).normalized()


def flex_axis(pb, n_palm):
    """World axis about which a positive rotation curls the bone towards the palm."""
    v = rest_dir(pb)
    return v.cross(Vector(n_palm)).normalized()


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion((1, 0, 0, 0))
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)


def finger_pose(arm, side, finger, amount, spread_deg=0.0, hand=None):
    """Flex a finger (0..1 = open..fist) and optionally spread it in the palm plane."""
    hand = hand or hand_info(arm)[side]
    n = hand["n"]
    S = SIDES[side]
    angs = FIST[finger]
    for k in range(3):
        pb = arm.pose.bones[f"{S}Hand{finger}{k+1}"]
        q_flex = Quaternion(((pb.bone.matrix_local.to_3x3().inverted()) @ flex_axis(pb, n)).normalized(), np.radians(angs[k] * amount))
        q = q_flex
        if k == 0 and spread_deg:
            ax_l = (pb.bone.matrix_local.to_3x3().inverted() @ Vector(n)).normalized()
            q = Quaternion(ax_l, np.radians(spread_deg)) @ q_flex
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = q


def _rest_mat(arm, name):
    return arm.data.bones[name].matrix_local.copy()


def _fk(arm, chain, quats):
    from mathutils import Matrix
    b0 = arm.data.bones[chain[0]]
    parent_pose = _rest_mat(arm, b0.parent.name) if b0.parent else Matrix.Identity(4)
    parent_rest = parent_pose.copy()
    out = []
    for nm, q in zip(chain, quats):
        b = arm.data.bones[nm]
        rest = _rest_mat(arm, nm)
        pose = parent_pose @ (parent_rest.inverted() @ rest) @ q.to_matrix().to_4x4()
        head = pose.translation.copy()
        tail = pose @ Vector((0, (b.tail_local - b.head_local).length, 0))
        out.append((head, tail))
        parent_pose, parent_rest = pose, rest
    return out


def _q_world(arm, nm, axis_world, deg):
    m = _rest_mat(arm, nm).to_3x3().inverted()
    return Quaternion((m @ Vector(axis_world)).normalized(), np.radians(deg))


def _thumb_quats(arm, side, P):
    S = SIDES[side]
    n = Vector(hand_info(arm)[side]["n"])
    tch = [f"{S}HandThumb{k}" for k in (1, 2, 3)]
    tdir = [(arm.data.bones[x].tail_local - arm.data.bones[x].head_local).normalized() for x in tch]
    r1 = _q_world(arm, tch[0], n, P["o1"]) @ _q_world(arm, tch[0], tdir[0].cross(n).normalized(), P["f1"]) @ _q_world(arm, tch[0], tdir[0], P["tw1"])
    r2 = _q_world(arm, tch[1], tdir[1].cross(n).normalized(), P["f2"]) @ _q_world(arm, tch[1], n, P["o2"])
    r3 = _q_world(arm, tch[2], tdir[2].cross(n).normalized(), P["f3"])
    return tch, [r1, r2, r3]


def solve_thumb_fist(arm, side, samples=5000, seed=1):
    """Find thumb rotations (about the rest axes) so that in a fist the thumb tip rests on the folded index/middle fingers."""
    S = SIDES[side]
    n = Vector(hand_info(arm)[side]["n"])
    fing = {}
    for f in ("Index", "Middle"):
        chain = [f"{S}Hand{f}{k}" for k in (1, 2, 3)]
        qs = []
        for k, nm in enumerate(chain):
            v = (arm.data.bones[nm].tail_local - arm.data.bones[nm].head_local).normalized()
            qs.append(_q_world(arm, nm, v.cross(n).normalized(), FIST[f][k]))
        fing[f] = _fk(arm, chain, qs)
    target = (fing["Index"][2][0] + fing["Middle"][2][0]) / 2 + n * 0.014
    rng = np.random.default_rng(seed)
    keys = ["o1", "f1", "tw1", "f2", "o2", "f3"]
    lo = dict(o1=-70, f1=-10, tw1=-50, f2=0, o2=-20, f3=0)
    hi = dict(o1=70, f1=70, tw1=50, f2=65, o2=20, f3=80)

    def cost(P):
        tch, qs = _thumb_quats(arm, side, P)
        tip = _fk(arm, tch, qs)[2][1]
        # prefer small total rotation among equally good solutions
        reg = 1e-6 * (abs(P["o1"]) + abs(P["tw1"]) + abs(P["o2"]))
        return (tip - target).length + reg
    best, bp = 1e9, None
    for _ in range(samples):
        P = {k: rng.uniform(lo[k], hi[k]) for k in keys}
        c = cost(P)
        if c < best:
            best, bp = c, P
    step = 10.0
    for it in range(1500):
        P = {k: float(np.clip(bp[k] + rng.normal(0, step), lo[k], hi[k])) for k in keys}
        c = cost(P)
        if c < best:
            best, bp = c, P
        if it % 300 == 299:
            step *= 0.5
    bp = {k: float(v) for k, v in bp.items()}
    bp["dist_mm"] = float(best * 1000)
    return bp


def thumb_pose(arm, side, amount, hand=None):
    S = SIDES[side]
    P = json.loads(arm["oliver_thumb"])[side]
    sc = {k: P[k] * amount for k in ("o1", "f1", "tw1", "f2", "o2", "f3")}
    tch, qs = _thumb_quats(arm, side, sc)
    for nm, q in zip(tch, qs):
        pb = arm.pose.bones[nm]
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = q


def fist(arm, side, amount=1.0):
    for f in FINGERS:
        finger_pose(arm, side, f, amount)
    thumb_pose(arm, side, amount)


def point(arm, side):
    for f in FINGERS:
        finger_pose(arm, side, f, 0.0 if f == "Index" else 1.0)
    thumb_pose(arm, side, 0.8)


def peace(arm, side, spread=9.0):
    sg = 1.0
    finger_pose(arm, side, "Index", 0.0, spread_deg=+spread * sg)
    finger_pose(arm, side, "Middle", 0.0, spread_deg=-spread * sg)
    finger_pose(arm, side, "Ring", 1.0)
    finger_pose(arm, side, "Pinky", 1.0)
    thumb_pose(arm, side, 0.9)


def set_keys(mesh, **vals):
    kb = mesh.data.shape_keys.key_blocks
    for k in kb:
        if k.name != "Basis":
            k.value = vals.get(k.name, 0.0)


def jaw_pose(arm, deg):
    """Open the jaw: positive rotation about the world +X axis (chin goes down and back), same as the jawOpen shape key."""
    pb = arm.pose.bones["Jaw"]
    set_rot_world(pb, (1, 0, 0), deg)
