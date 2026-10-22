"""Front/side closeups of the mouth region of the carved model with a metric grid. -- <tag> <cz> [scale]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz
from PIL import Image, ImageDraw
a = sys.argv[sys.argv.index("--") + 1:]
tag = a[0]; cz = float(a[1]); scale = float(a[2]) if len(a) > 2 else 0.12; cx = float(a[3]) if len(a) > 3 else 0.0; step_mm = float(a[4]) if len(a) > 4 else 5.0
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
# keep only the head region to avoid occlusion by hair strands etc. -> keep everything but render orthographic
viz.clear_scene()
me = arrays_to_mesh("m", co, F, uv)
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
mt.node_tree.links.new(tn.outputs["Color"], mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("m", me); bpy.context.scene.collection.objects.link(ob)
sc = viz.make_scene(1024, color_type="TEXTURE")
cam = viz.get_camera(sc)
c = (cx, -0.1, cz)
viz.aim_camera(cam, c, scale, 0, 0)
sc.render.filepath = f"{WORK}/dbg/{tag}_face_front_raw.png"
bpy.ops.render.render(write_still=True)
viz.aim_camera(cam, (0, 0, cz), scale * 1.6, 90, 0)
sc.render.filepath = f"{WORK}/dbg/{tag}_face_side_raw.png"
bpy.ops.render.render(write_still=True)
# grid overlay (front: x horizontal, z vertical; side camera at +x: horizontal = -y ... image right = +y?)
def grid(path, out, S, hlabel_offset=0.0, cy=0.0):
    im = Image.open(path).convert("RGB")
    dr = ImageDraw.Draw(im)
    st = step_mm / 1000.0
    for i in range(-80, 81):
        pos = i * st
        px = 512 + pos / S * 1024
        major = (i % 5 == 0)
        dr.line([(px, 0), (px, 1024)], fill=(255, 255, 0) if major else (110, 110, 0), width=1)
        if major: dr.text((px + 2, 2), f"{(pos + cx)*1000:+.0f}", fill=(255, 255, 255))
        pz = 512 - pos / S * 1024
        dr.line([(0, pz), (1024, pz)], fill=(0, 255, 255) if major else (0, 100, 100), width=1)
        if major: dr.text((2, pz + 1), f"{(cz+pos)*1000:.0f}", fill=(255, 255, 255))
    im.save(out)
grid(f"{WORK}/dbg/{tag}_face_front_raw.png", f"{WORK}/dbg/{tag}_face_front.png", scale)
grid(f"{WORK}/dbg/{tag}_face_side_raw.png", f"{WORK}/dbg/{tag}_face_side.png", scale * 1.6)
