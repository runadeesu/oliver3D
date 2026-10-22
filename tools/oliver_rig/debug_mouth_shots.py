"""Mouth shape-key close-ups of a rigged .blend.
blender -b rig.blend --python debug_mouth_shots.py -- <outdir>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, rig_poses as rp
outdir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
sc = viz.make_scene(700, color_type="TEXTURE", light="FLAT")
cam = viz.get_camera(sc)
head = arm.data.bones["Jaw"].head_local
center = (arm.matrix_world @ head).to_tuple()
mc = (center[0], -0.11, center[2] - 0.06)
for nm in ("rest", "jawOpen", "viseme_I", "viseme_U", "viseme_O", "mouthSmile"):
    rp.set_keys(mesh, **({} if nm == "rest" else {nm: 1.0}))
    bpy.context.view_layer.update()
    viz.aim_camera(cam, mc, 0.07, 0, 0)
    sc.render.filepath = f"{outdir}/{nm}.png"
    bpy.ops.render.render(write_still=True)
