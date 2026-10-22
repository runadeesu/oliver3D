"""Search thumb rotations so that in a fist the thumb tip rests on the folded index/middle fingers.
blender -b rig.blend --python thumb_search.py -- <tag>"""
import sys, os, json, itertools
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import rig_poses as rp
from mathutils import Matrix, Quaternion, Vector
tag = sys.argv[sys.argv.index("--") + 1]
arm, mesh = rp.find_rig()
hands = rp.hand_info(arm)
rp.reset_pose(arm)
bpy.context.view_layer.update()

def rest_mat(name):
    return arm.data.bones[name].matrix_local.copy()      # armature space

def fk_tail(chain, quats, root_pose=None):
    """chain: list of bone names (parent->child). quats: local rotation quaternion per bone (rest-local space).
    Returns list of (head, tail) in armature space."""
    out = []
    parent_pose = rest_mat(arm.data.bones[chain[0]].parent.name) if arm.data.bones[chain[0]].parent else Matrix.Identity(4)
    parent_rest = parent_pose.copy()
    for nm, q in zip(chain, quats):
        b = arm.data.bones[nm]
        rest = rest_mat(nm)
        # pose matrix = parent_pose @ (parent_rest^-1 @ rest) @ rot
        local = parent_rest.inverted() @ rest
        pose = parent_pose @ local @ q.to_matrix().to_4x4()
        length = (b.tail_local - b.head_local).length
        head = pose.translation.copy()
        tail = pose @ Vector((0, length, 0))
        out.append((head, tail))
        parent_pose, parent_rest = pose, rest
    return out

def quat_about_world(nm, axis_world, deg):
    m = rest_mat(nm).to_3x3().inverted()
    ax = (m @ Vector(axis_world)).normalized()
    return Quaternion(ax, np.radians(deg))

result = {}
for side, S in (("R", "Right"), ("L", "Left")):
    n = Vector(hands[side]["n"])
    fing = {}
    # fist pose of index/middle chains
    for f in ("Index", "Middle"):
        chain = [f"{S}Hand{f}{k}" for k in (1, 2, 3)]
        qs = []
        for k, nm in enumerate(chain):
            v = (arm.data.bones[nm].tail_local - arm.data.bones[nm].head_local).normalized()
            ax = v.cross(n).normalized()
            qs.append(quat_about_world(nm, ax, rp.FIST[f][k]))
        fing[f] = fk_tail(chain, qs)
    # fist poses chain the parent: hand bone not rotated -> parent_pose = rest of Hand
    target = (fing["Index"][2][0] + fing["Middle"][2][0]) / 2 + n * 0.014      # DIP region of index/middle, outside the folded fingers
    tchain = [f"{S}HandThumb{k}" for k in (1, 2, 3)]
    tb = [arm.data.bones[x] for x in tchain]
    tdir = [(b.tail_local - b.head_local).normalized() for b in tb]
    best = None
    rng = np.random.default_rng(1)
    for it in range(6000):
        o1 = rng.uniform(-70, 70); f1 = rng.uniform(-10, 70); tw1 = rng.uniform(-50, 50)
        f2 = rng.uniform(0, 65); f3 = rng.uniform(0, 80); o2 = rng.uniform(-20, 20)
        r1 = quat_about_world(tchain[0], n, o1) @ quat_about_world(tchain[0], tdir[0].cross(n).normalized(), f1) @ quat_about_world(tchain[0], tdir[0], tw1)
        r2 = quat_about_world(tchain[1], tdir[1].cross(n).normalized(), f2) @ quat_about_world(tchain[1], n, o2)
        r3 = quat_about_world(tchain[2], tdir[2].cross(n).normalized(), f3)
        ht = fk_tail(tchain, [r1, r2, r3])
        tip = ht[2][1]
        d = (tip - target).length
        # penalise the thumb passing through the palm: tip should stay on the +n side of the index MCP plane
        if best is None or d < best[0]:
            best = (d, dict(o1=o1, f1=f1, tw1=tw1, f2=f2, o2=o2, f3=f3))
    result[side] = best
    print("THUMB", side, "best dist (mm)", round(best[0] * 1000, 1), {k: round(v, 1) for k, v in best[1].items()}, "target", [round(x, 3) for x in target])
json.dump({s: dict(dist=r[0], **r[1]) for s, r in result.items()}, open(os.path.join(WORK, f"{tag}_thumb_fist.json"), "w"))
