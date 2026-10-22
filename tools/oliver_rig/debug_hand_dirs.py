"""Isolated hand (skin region only) rendered along +-x,+-y,+-z with the real texture. -- <tag> <R|L> [scale]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg
a = sys.argv[sys.argv.index("--") + 1:]
tag, side = a[0], a[1]
scale = float(a[2]) if len(a) > 2 else 0.22
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
h = cfg["hand_search"][side]
m, seed, col = hands_seg.segment_hand(co, vc, adj, -1 if side == "R" else 1, h["center"], h["radius"], h["shoulder"])
fm = m[F].all(1)
viz.clear_scene()
me = arrays_to_mesh("hand", co, F[fm], uv[fm])
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("hand", me); bpy.context.scene.collection.objects.link(ob)
c = co[m].mean(0)
sc = viz.make_scene(700, color_type="TEXTURE")
cam = viz.get_camera(sc)
for name, az, el in (("front", 0, 0), ("back", 180, 0), ("left", 270, 0), ("right", 90, 0), ("top", 0, 89), ("bottom", 0, -89)):
    viz.aim_camera(cam, c, scale, az, el)
    sc.render.filepath = f"{WORK}/dbg/{tag}_hd{side}_{name}.png"
    bpy.ops.render.render(write_still=True)
