import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, mouth_build as mb, skeleton as sk
import bmesh as bm_
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
hands = json.load(open(f"{WORK}/{tag}_hands.json"))
fr = mb.MouthFrame(cfg)
bvh = mb.face_bvh(co, F, fr)
yc = mb.surface_y(bvh, fr.cx, fr.z0)
hd = {s: dict(W=np.array(hands[s]["W"])) for s in "LR"}
LM = sk.estimate_landmarks(co, fr, yc, hd, cfg)
B = sk.build_bone_list(LM, hands)
log(tag, "bones:", len(B), "zf", round(LM["zf"], 3), "H", round(LM["H"], 3))
viz.clear_scene()
me = arrays_to_mesh("m", co, F, uv)
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("m", me); bpy.context.scene.collection.objects.link(ob)
ob.show_transparent = True
mt.blend_method = "BLEND"; mt.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.35
cols = {"torso": (1, 0.6, 0), "head": (1, 0, 0), "jaw": (1, 0, 1), "arm": (0, 0.8, 0), "hand": (0, 0.8, 0.8), "finger": (0.2, 0.2, 1), "leg": (0.9, 0.9, 0)}
def cyl(p0, p1, r, color, name):
    p0, p1 = Vector(p0), Vector(p1)
    me2 = bpy.data.meshes.new(name); b = bm_.new()
    bm_.ops.create_cone(b, cap_ends=True, segments=6, radius1=r, radius2=r, depth=max((p1 - p0).length, 1e-4))
    b.to_mesh(me2); b.free()
    o = bpy.data.objects.new(name, me2); o.location = (p0 + p1) / 2
    o.rotation_euler = (p1 - p0).to_track_quat('Z', 'Y').to_euler()
    m = bpy.data.materials.new(name); m.diffuse_color = (*color, 1); o.data.materials.append(m)
    o.show_in_front = True; bpy.context.scene.collection.objects.link(o)
for b in B:
    r = 0.004 if b["group"] != "finger" else 0.0018
    cyl(b["head"], b["tail"], r, cols[b["group"]], b["name"])
sc = viz.make_scene(1100, color_type="MATERIAL", light="FLAT")
cam = viz.get_camera(sc)
out = f"{WORK}/dbg/{tag}_skel"
for name, az, el, cen, scale in (("front", 0, 0, (0, 0, 0), 2.1), ("side", 90, 0, (0, 0, 0), 2.1), ("head_side", 90, 0, (0, -0.02, 0.76), 0.5), ("hand", 0, 0, tuple(np.array(hands["R"]["W"])), 0.3)):
    viz.aim_camera(cam, cen, scale, az, el)
    sc.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)
