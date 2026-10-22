"""Render pose tests from a rigged .blend. blender -b rig.blend --python test_poses.py -- <tag> <outdir>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, rig_poses as rp
tag, outdir = sys.argv[sys.argv.index("--") + 1:][:2]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
hands = rp.hand_info(arm)
sc = viz.make_scene(700, color_type="TEXTURE", light="FLAT")
cam = viz.get_camera(sc)
Wr = np.array(hands["R"]["a"])
def hand_center(side):
    b = arm.pose.bones[f"{rp.SIDES[side]}Hand"]
    return (arm.matrix_world @ b.head).to_tuple()
def shot(name, center, scale, az, el=0):
    viz.aim_camera(cam, center, scale, az, el)
    sc.render.filepath = f"{outdir}/{name}.png"
    bpy.ops.render.render(write_still=True)
hc = {s: np.array(hand_center(s)) + np.array(hands[s]["a"]) * 0.08 for s in "LR"}
# camera azimuth looking at the R hand from outside (270) / L hand from outside (90)
az = {"R": 270, "L": 90}
rp.reset_pose(arm)
def shot_dir(name, center, scale, direction):
    viz.aim_dir(cam, center, scale, direction, cut=0.12)
    sc.render.filepath = f"{outdir}/{name}.png"
    bpy.ops.render.render(write_still=True)
nR = np.array(hands["R"]["n"]); aR = np.array(hands["R"]["a"]); uR = np.array(hands["R"]["u"])
for name, fn in (("rest", lambda: None), ("fist", lambda: [rp.fist(arm, s) for s in "LR"]), ("point", lambda: [rp.point(arm, s) for s in "LR"]), ("peace", lambda: [rp.peace(arm, s) for s in "LR"])):
    rp.reset_pose(arm)
    fn()
    bpy.context.view_layer.update()
    for s in "R":
        shot(f"hand{s}_{name}_side", hc[s], 0.26, az[s])
        shot(f"hand{s}_{name}_front", hc[s], 0.26, 0)
        shot_dir(f"hand{s}_{name}_palm", hc[s], 0.22, nR)
        shot_dir(f"hand{s}_{name}_back", hc[s], 0.22, -nR)
        shot_dir(f"hand{s}_{name}_tip", hc[s], 0.22, aR)
        shot_dir(f"hand{s}_{name}_thumbside", hc[s], 0.22, uR)
for f in rp.FINGERS:
    rp.reset_pose(arm)
    rp.finger_pose(arm, "R", f, 1.0)
    bpy.context.view_layer.update()
    shot_dir(f"handR_only_{f}_palm", hc["R"], 0.22, nR)
    shot_dir(f"handR_only_{f}_thumbside", hc["R"], 0.22, uR)
rp.reset_pose(arm)
