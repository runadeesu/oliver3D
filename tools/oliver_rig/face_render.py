"""Render the head of the original (un-rigged) model from the front, orthographic, for landmark detection / comparison.
blender -b --factory-startup --python face_render.py -- <tag> <out.png> [scale] [res] [arrays_suffix]
Writes <out>.json with the camera mapping (center xz, scale, res)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz
a = sys.argv[sys.argv.index("--") + 1:]
tag, out = a[0], a[1]
scale = float(a[2]) if len(a) > 2 else 0.38
res = int(a[3]) if len(a) > 3 else 1400
suffix = a[4] if len(a) > 4 else ""
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays{suffix}.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
mat = d["mat"]
show_glasses = os.environ.get("FACE_GLASSES", "0") == "1"
if not show_glasses:                                    # rebuilt glasses (material >= 4) are left out so the skin below them can be corrected
    keepf = mat < 4
    F, uv, mat = F[keepf], uv[keepf], mat[keepf]
zm = np.polyval(cfg["mouth"]["poly4_mm"], cfg["mouth"]["cx_mm"]) / 1000.0
cx = cfg["mouth"]["cx_mm"] / 1000.0
cz = zm + 0.055
viz.clear_scene()
near = (np.abs(co[:, 0] - cx) < scale) & (np.abs(co[:, 2] - cz) < scale) & (co[:, 2] > cz - 0.5 * scale) & (co[:, 2] < cz + 0.5 * scale) & (co[:, 1] < 0.02)
fm = near[F].all(1)
sub = F[fm]
mat_sub = mat[fm]
ids = np.unique(sub)
remap = -np.ones(len(co), np.int64); remap[ids] = np.arange(len(ids))
me = arrays_to_mesh("head", co[ids], remap[sub], uv[fm], mat_sub)
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ.get("FACE_TEX", os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png"))
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
me.materials.append(mt)
for _ in range(3):
    me.materials.append(mt)
if show_glasses:
    import materials as _mt
    for g_ in _mt.glasses_materials():
        me.materials.append(g_)
ob = bpy.data.objects.new("head", me)
bpy.context.scene.collection.objects.link(ob)
sc = viz.make_scene(res, color_type="TEXTURE", light="FLAT")
cam = viz.get_camera(sc)
viz.aim_camera(cam, (cx, -0.1, cz), scale, 0, 0)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
json.dump(dict(cx=cx, cz=cz, scale=scale, res=res), open(out + ".json", "w"))
log(tag, "face render", out)
