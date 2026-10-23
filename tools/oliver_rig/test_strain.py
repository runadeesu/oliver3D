"""Body pose stress test: how badly are triangles stretched / squashed in extreme poses?
blender -b rig.blend --python test_strain.py -- <tag> [outdir]
For every pose prints STRAIN lines: 99.9th percentile / max of the edge length ratio (posed / rest), the number of edges stretched more than 1.8x
and squashed below 0.5x, and (with outdir) renders front + side views. The pose list is shared with the renders of test_body.py."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import rig_poses as rp
from mathutils import Euler, Quaternion

a = sys.argv[sys.argv.index("--") + 1:]
tag = a[0]
outdir = a[1] if len(a) > 1 else None
arm, mesh = rp.find_rig()

# (bone, rx, ry, rz) degrees about the WORLD axes, in the bone's rest frame; left arm abduction = negative y rotation, right arm = positive y
POSES = {
    "arms_fwd60": [("LeftArm", -60, 0, 0), ("RightArm", -60, 0, 0)],
    "arms_fwd90": [("LeftArm", -90, 0, 0), ("RightArm", -90, 0, 0)],
    "arms_fwd120": [("LeftArm", -120, 0, 0), ("RightArm", -120, 0, 0)],
    "arms_side": [("LeftArm", 0, -55, 0), ("RightArm", 0, 55, 0)],
    "arms_overhead": [("LeftArm", 0, -125, 0), ("RightArm", 0, 125, 0)],
    "arms_back": [("LeftArm", 40, 0, 0), ("RightArm", 40, 0, 0)],
    "elbows_90": [("LeftArm", -30, 0, 0), ("RightArm", -30, 0, 0), ("LeftForeArm", -90, 0, 0), ("RightForeArm", -90, 0, 0)],
    "leg_fwd45": [("LeftUpLeg", -45, 0, 0)],
    "leg_fwd80": [("LeftUpLeg", -80, 0, 0), ("RightUpLeg", 20, 0, 0)],
    "leg_side30": [("LeftUpLeg", 0, -30, 0), ("RightUpLeg", 0, 30, 0)],
    "knee_70": [("LeftUpLeg", -40, 0, 0), ("LeftLeg", 70, 0, 0)],
    "spine_fwd30": [("Spine", -10, 0, 0), ("Spine1", -10, 0, 0), ("Spine2", -10, 0, 0)],
    "spine_twist40": [("Spine", 0, 0, 13), ("Spine1", 0, 0, 13), ("Spine2", 0, 0, 14)],
    "head_turn60": [("Neck", 0, 0, 25), ("Head", 0, 0, 35)],
}


def set_world_euler(pb, rx, ry, rz):
    m = pb.bone.matrix_local.to_3x3()
    q_w = Euler((np.radians(rx), np.radians(ry), np.radians(rz)), "XYZ").to_matrix()
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = (m.inverted() @ q_w @ m).to_quaternion()


def apply_pose(name):
    rp.reset_pose(arm)
    for bone, rx, ry, rz in POSES[name]:
        set_world_euler(arm.pose.bones[bone], rx, ry, rz)
    bpy.context.view_layer.update()


def evaluated():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    m = ev.to_mesh()
    c = np.empty(len(m.vertices) * 3, np.float32)
    m.vertices.foreach_get("co", c)
    ev.to_mesh_clear()
    return c.reshape(-1, 3).astype(np.float64)


def main():
    me = mesh.data
    E = np.empty(len(me.edges) * 2, np.int32)
    me.edges.foreach_get("vertices", E)
    E = E.reshape(-1, 2)
    rp.reset_pose(arm)
    rp.set_keys(mesh)
    bpy.context.view_layer.update()
    rest = evaluated()
    l0 = np.linalg.norm(rest[E[:, 0]] - rest[E[:, 1]], axis=1)
    ok = l0 > 1e-5
    if outdir:
        import viz
        os.makedirs(outdir, exist_ok=True)
        sc = viz.make_scene(700, color_type="TEXTURE", light="FLAT")
        cam = viz.get_camera(sc)
        bb = np.array([(mesh.matrix_world @ Vector(c)).to_tuple() for c in mesh.bound_box])
        center = tuple(((bb.min(0) + bb.max(0)) / 2).tolist())
        scale = float(bb[:, 2].max() - bb[:, 2].min()) * 1.3
    for name in POSES:
        apply_pose(name)
        p = evaluated()
        l1 = np.linalg.norm(p[E[:, 0]] - p[E[:, 1]], axis=1)
        r = l1[ok] / l0[ok]
        print(f"STRAIN {tag} {name:14s} p99.9 {np.percentile(r, 99.9):5.2f}  max {r.max():6.2f}  n>1.8: {int((r > 1.8).sum()):6d}  n<0.5: {int((r < 0.5).sum()):6d}  edges {len(r)}")
        if outdir:
            for vn, az in (("front", 0), ("side", 90)):
                viz.aim_camera(cam, center, scale, az)
                sc.render.filepath = f"{outdir}/{name}_{vn}.png"
                bpy.ops.render.render(write_still=True)
    rp.reset_pose(arm)


main()
