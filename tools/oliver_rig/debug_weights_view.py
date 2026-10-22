"""Colour the mesh by dominant bone (and a second view by weight of selected bones). blender -b rig.blend --python ... -- <outdir>"""
import sys, os, colorsys
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, rig_poses as rp
outdir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
me = mesh.data
n = len(me.vertices)
names = [vg.name for vg in mesh.vertex_groups]
W = np.zeros((n, len(names)), np.float32)
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
dom = W.argmax(1)
pal = np.array([colorsys.hsv_to_rgb((i * 0.61803) % 1.0, 0.75, 0.95) for i in range(len(names))])
col = pal[dom]
attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
rgba = np.ones((n, 4), np.float32); rgba[:, :3] = col
attr.data.foreach_set("color", rgba.ravel())
me.color_attributes.active_color = attr
sc = viz.make_scene(900, color_type="VERTEX", light="FLAT")
cam = viz.get_camera(sc)
hands = rp.hand_info(arm)
nR = np.array(hands["R"]["n"]); uR = np.array(hands["R"]["u"])
hc = np.array((arm.matrix_world @ arm.pose.bones["RightHand"].head).to_tuple()) + np.array(hands["R"]["a"]) * 0.08
for nm, dr in (("palm", nR), ("back", -nR), ("thumbside", uR)):
    viz.aim_dir(cam, hc, 0.2, dr)
    sc.render.filepath = f"{outdir}/wcol_{nm}.png"
    bpy.ops.render.render(write_still=True)
# legend
print("legend:", {names[i]: np.round(pal[i], 2).tolist() for i in range(len(names)) if names[i].startswith("RightHand")})
# also fist pose with colours
rp.reset_pose(arm); rp.fist(arm, "R"); bpy.context.view_layer.update()
for nm, dr in (("palm", nR), ("back", -nR), ("thumbside", uR)):
    viz.aim_dir(cam, hc, 0.2, dr)
    sc.render.filepath = f"{outdir}/wcol_fist_{nm}.png"
    bpy.ops.render.render(write_still=True)
