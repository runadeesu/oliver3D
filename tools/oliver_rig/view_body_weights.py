"""Render the body skin weights: every vertex coloured by its dominant bone (front / back / side) and the LeftArm weight as a heat map.
blender -b rig.blend --python view_body_weights.py -- <outdir>"""
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
bodyfirst = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "Jaw", "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand", "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase", "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]
# merge finger groups into their hand for the colour view
gid = {nm: i for i, nm in enumerate(names)}
Wb = np.zeros((n, len(bodyfirst)), np.float32)
for j, nm in enumerate(bodyfirst):
    Wb[:, j] = W[:, gid[nm]] if nm in gid else 0
    if nm in ("LeftHand", "RightHand"):
        side = nm[:-4]
        for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
            for k in (1, 2, 3):
                g = f"{side}Hand{f}{k}"
                if g in gid:
                    Wb[:, j] += W[:, gid[g]]
pal = np.array([colorsys.hsv_to_rgb((i * 0.61803) % 1.0, 0.8, 0.95) for i in range(len(bodyfirst))])
dom = Wb.argmax(1)
col = pal[dom]
attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
rgba = np.ones((n, 4), np.float32)
bb = np.array([(mesh.matrix_world @ Vector(c)).to_tuple() for c in mesh.bound_box])
center = tuple(((bb.min(0) + bb.max(0)) / 2).tolist())
scale = float(bb[:, 2].max() - bb[:, 2].min()) * 1.3
sc = viz.make_scene(900, color_type="VERTEX", light="FLAT")
cam = viz.get_camera(sc)
def shoot(tag):
    me.color_attributes.active_color = attr
    for vn, az in (("front", 0), ("side", 90), ("back", 180)):
        viz.aim_camera(cam, center, scale, az)
        sc.render.filepath = f"{outdir}/{tag}_{vn}.png"
        bpy.ops.render.render(write_still=True)
rgba[:, :3] = col
attr.data.foreach_set("color", rgba.ravel())
shoot("dom")
w = Wb[:, bodyfirst.index("LeftArm")]
heat = np.stack([np.clip(2 * w, 0, 1), np.clip(2 - 2 * np.abs(w - 0.5) * 2, 0, 1) * 0.8, np.clip(1 - 2 * w, 0, 1)], 1)
rgba[:, :3] = heat
attr.data.foreach_set("color", rgba.ravel())
shoot("leftarm")
print("legend:", {nm: np.round(pal[i], 2).tolist() for i, nm in enumerate(bodyfirst)})
