import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, mouth_build as mb
tag = sys.argv[sys.argv.index("--") + 1]
theta = float(sys.argv[sys.argv.index("--") + 2]) if len(sys.argv) > sys.argv.index("--") + 2 else 13.0
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv, mat = d["co"], d["faces"], d["uv"], d["mat"]
fr = mb.MouthFrame(cfg)
t = timer()
asm = mb.fit_inside(mb.assemble(co, F, uv, mat, fr))
log(tag, "mouth assembled", round(t(), 1), "s; verts", len(asm["co"]), "faces", len(asm["faces"]))
w = mb.jaw_weights(asm)
piv = mb.jaw_pivot(fr, asm["y_center"])
viz.clear_scene()
mats = []
mt = bpy.data.materials.new("skin"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"]); mats.append(mt)
for nm, col in (("inside", (0.22, 0.04, 0.05, 1)), ("teeth", (0.92, 0.88, 0.78, 1)), ("tongue", (0.75, 0.25, 0.28, 1))):
    m_ = bpy.data.materials.new(nm); m_.diffuse_color = col; m_.use_nodes = False; mats.append(m_)
sc = viz.make_scene(900, color_type="MATERIAL", light="STUDIO")
cam = viz.get_camera(sc)
for pose, th in (("closed", 0.0), ("open", theta), ("wide", theta * 1.5)):
    viz.clear_scene() if False else None
    for o in list(bpy.data.objects):
        if o.name.startswith("m_"):
            bpy.data.objects.remove(o, do_unlink=True)
    c2 = mb.rotate_jaw(asm["co"].astype(np.float64), w, piv, th)
    me = arrays_to_mesh("m_" + pose, c2, asm["faces"], asm["uv"], asm["mat"])
    for m_ in mats: me.materials.append(m_)
    ob = bpy.data.objects.new("m_" + pose, me); bpy.context.scene.collection.objects.link(ob)
    # sunglasses etc. not needed; render front + side + 3/4
    for name, az, el, scale in (("front", 0, 0, 0.09), ("quarter", 35, 10, 0.10), ("side", 270, 0, 0.13)):
        viz.aim_camera(cam, (fr.cx, -0.11, fr.z0 - 0.005), scale, az, el)
        sc.render.filepath = f"{WORK}/dbg/{tag}_mouth_{pose}_{name}.png"
        bpy.ops.render.render(write_still=True)
