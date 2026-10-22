"""Textured closeups of the carved hands. -- <tag>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
viz.clear_scene()
me = arrays_to_mesh("carved", co, F, uv)
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
bsdf = mt.node_tree.nodes["Principled BSDF"]; mt.node_tree.links.new(tn.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("carved", me); bpy.context.scene.collection.objects.link(ob)
cR = np.array(cfg["hand_search"]["R"]["center"]); cL = np.array(cfg["hand_search"]["L"]["center"])
# hide the body in front of the hand: only render faces near the hand
sc = viz.make_scene(800, color_type="TEXTURE")
cam = viz.get_camera(sc)
for name, c, az, el in (("Ra", cR, 270, 0), ("Rb", cR, 90, 0), ("Rc", cR, 0, 0), ("Rd", cR, 0, 90), ("La", cL, 90, 0), ("Lb", cL, 270, 0)):
    viz.aim_camera(cam, c, 0.2, az, el)
    sc.render.filepath = f"{WORK}/dbg/{tag}_cv_{name}.png"
    bpy.ops.render.render(write_still=True)
