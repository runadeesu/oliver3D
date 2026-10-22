"""Whole-body + mouth pose tests through the real armature / shape keys. blender -b rig.blend --python test_body.py -- <outdir>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, rig_poses as rp
from mathutils import Quaternion
outdir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
_bb = np.array([(mesh.matrix_world @ Vector(c)).to_tuple() for c in mesh.bound_box])
body_center = tuple(((_bb.min(0) + _bb.max(0)) / 2).tolist())      # models stand with their feet on z = 0
body_scale = float(_bb[:, 2].max() - _bb[:, 2].min()) * 1.3
sc = viz.make_scene(900, color_type="TEXTURE", light="FLAT")
cam = viz.get_camera(sc)

def rot(name, axis, deg):
    pb = arm.pose.bones[name]
    pb.rotation_mode = "QUATERNION"
    rp.set_rot_world(pb, axis, deg)

def shot(name, center, scale, az, el=0):
    viz.aim_camera(cam, center, scale, az, el)
    sc.render.filepath = f"{outdir}/{name}.png"
    bpy.ops.render.render(write_still=True)

poses = {
    "rest": [],
    "arms_up": [("LeftArm", (0, 1, 0), 55), ("RightArm", (0, 1, 0), -55), ("LeftForeArm", (0, 1, 0), 30), ("RightForeArm", (0, 1, 0), -30)],
    "arms_fwd": [("LeftArm", (1, 0, 0), -70), ("RightArm", (1, 0, 0), -70)],
    "legs": [("LeftUpLeg", (1, 0, 0), -35), ("LeftLeg", (1, 0, 0), 50), ("RightUpLeg", (1, 0, 0), 20), ("RightLeg", (1, 0, 0), 25)],
    "twist": [("Spine1", (0, 0, 1), 25), ("Spine2", (0, 0, 1), 20), ("Neck", (0, 0, 1), 20), ("Head", (0, 0, 1), 20)],
    "bend": [("Spine", (1, 0, 0), -20), ("Spine1", (1, 0, 0), -20), ("Head", (1, 0, 0), 15)],
}
for name, ops in poses.items():
    rp.reset_pose(arm)
    for nm, ax, deg in ops:
        rot(nm, ax, deg)
    bpy.context.view_layer.update()
    shot(f"body_{name}_front", body_center, body_scale, 0)
    shot(f"body_{name}_side", body_center, body_scale, 90)
rp.reset_pose(arm)
# mouth via shape keys and via jaw bone
fr_z = None
head = arm.data.bones["Jaw"].head_local
center = (arm.matrix_world @ head).to_tuple()
mc = (center[0], -0.11, center[2] - 0.06)
for nm in ("jawOpen", "mouthClose", "viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O", "mouthSmile"):
    rp.set_keys(mesh, **{nm: 1.0})
    bpy.context.view_layer.update()
    shot(f"key_{nm}_front", mc, 0.1, 0)
    shot(f"key_{nm}_quarter", mc, 0.12, 40, 8)
rp.set_keys(mesh)
for deg in (0, 13):
    rp.jaw_pose(arm, deg)
    bpy.context.view_layer.update()
    shot(f"jawbone_{deg}_front", mc, 0.1, 0)
    shot(f"jawbone_{deg}_quarter", mc, 0.12, 40, 8)
rp.reset_pose(arm)
