import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, mouth_build
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
fr = mouth_build.MouthFrame(cfg)
t = timer()
out = mouth_build.cut_lips(co, F, uv, fr)
log(tag, "cut done", round(t(), 1), "s; chain length", len(out["upper"]), "verts; faces", len(out["faces"]))
up, lo = out["upper"], out["lower"]
c2 = out["co"]
log("upper chain x range", c2[up][:, 0].min().round(4), c2[up][:, 0].max().round(4), "z spread", np.ptp(c2[up][:, 2] - fr.zc(c2[up][:, 0])).round(5))
# manifoldness check of the opened mesh near the slit: boundary edges count
Fm = out["faces"]
E = np.concatenate([Fm[:, [0, 1]], Fm[:, [1, 2]], Fm[:, [2, 0]]])
key = np.sort(E, 1)
u, cnt = np.unique(key[:, 0].astype(np.int64) * len(c2) + key[:, 1], return_counts=True)
log("boundary edges (should be the slit: ~2x chain length)", int((cnt == 1).sum()), "non-manifold", int((cnt > 2).sum()))
# test render: lower lip shifted down 1.5 mm to reveal the slit
c3 = c2.copy()
low_only = np.setdiff1d(lo, up)
c3[low_only, 2] -= 0.0015
viz.clear_scene()
me = arrays_to_mesh("m", c3, Fm, out["uv"])
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("m", me); bpy.context.scene.collection.objects.link(ob)
sc = viz.make_scene(1024, color_type="TEXTURE")
cam = viz.get_camera(sc)
viz.aim_camera(cam, (fr.cx, -0.1, fr.z0), 0.07, 0, 0)
sc.render.filepath = f"{WORK}/dbg/{tag}_cut_test.png"
bpy.ops.render.render(write_still=True)
