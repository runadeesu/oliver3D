import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, mouth_build as mb, mouth_keys as mk
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv, mat = d["co"], d["faces"], d["uv"], d["mat"]
fr = mb.MouthFrame(cfg)
asm = mb.fit_inside(mb.assemble(co, F, uv, mat, fr))
fld = mk.MouthFields(asm)
keys = mk.build_keys(fld)
log(tag, "keys built:", {k: float(np.abs(v).max() * 1000) for k, v in keys.items()})
mats = []
mt = bpy.data.materials.new("skin"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"]); mats.append(mt)
for nm, col in (("inside", (0.22, 0.04, 0.05, 1)), ("teeth", (0.92, 0.88, 0.78, 1)), ("tongue", (0.75, 0.25, 0.28, 1))):
    m_ = bpy.data.materials.new(nm); m_.diffuse_color = col; m_.use_nodes = False; mats.append(m_)
viz.clear_scene()
sc = viz.make_scene(700, color_type="TEXTURE", light="STUDIO")
sc.display.shading.color_type = "MATERIAL"
cam = viz.get_camera(sc)
out = os.path.join(WORK, "dbg", f"{tag}_keys"); os.makedirs(out, exist_ok=True)
base = asm["co"].astype(np.float64)
poses = [("rest", None)] + [(k, k) for k in mk.KEY_NAMES]
for name, key in poses:
    for o in list(bpy.data.objects):
        if o.name.startswith("m_"): bpy.data.objects.remove(o, do_unlink=True)
    c2 = base + (keys[key] if key else 0)
    me = arrays_to_mesh("m_" + name, c2, asm["faces"], asm["uv"], asm["mat"])
    for m_ in mats: me.materials.append(m_)
    ob = bpy.data.objects.new("m_" + name, me); bpy.context.scene.collection.objects.link(ob)
    viz.aim_camera(cam, (fr.cx, -0.11, fr.z0 - 0.004), 0.085, 0, 0)
    sc.render.filepath = f"{out}/{name}_front.png"
    bpy.ops.render.render(write_still=True)
    viz.aim_camera(cam, (fr.cx, -0.11, fr.z0 - 0.004), 0.10, 40, 8)
    sc.render.filepath = f"{out}/{name}_quarter.png"
    bpy.ops.render.render(write_still=True)
from PIL import Image
W = 350
im = Image.new("RGB", (W * 3, W * 6))
for i, (name, key) in enumerate(poses):
    r, c = i // 3, i % 3
    a = Image.open(f"{out}/{name}_front.png").convert("RGB").resize((W, W))
    im.paste(a, (c * W, r * 2 * W // 1 if False else (r * 2) * W))
    b = Image.open(f"{out}/{name}_quarter.png").convert("RGB").resize((W, W))
    im.paste(b, (c * W, (r * 2 + 1) * W))
im.save(f"{WORK}/dbg/{tag}_keys_sheet.png")
