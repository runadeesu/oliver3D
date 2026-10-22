"""Geometry-only shaded closeups (studio light + cavity) of the mouth region. -- <tag> <cz> <cx> <scale>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz
a = sys.argv[sys.argv.index("--") + 1:]
tag = a[0]; cz = float(a[1]); cx = float(a[2]); scale = float(a[3])
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv = d["co"], d["faces"], d["uv"]
viz.clear_scene()
me = arrays_to_mesh("m", co, F, uv)
ob = bpy.data.objects.new("m", me); bpy.context.scene.collection.objects.link(ob)
sc = viz.make_scene(1024, color_type="SINGLE", light="STUDIO")
sh = sc.display.shading
sh.single_color = (0.8, 0.75, 0.72)
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.cavity_ridge_factor = 1.0
sh.cavity_valley_factor = 2.0
sh.show_specular_highlight = False
cam = viz.get_camera(sc)
for name, az, el, cen, sc_ in (("front", 0, 0, (cx, -0.1, cz), scale), ("front_up", 0, 25, (cx, -0.1, cz), scale), ("side", 270, 0, (0, -0.12, cz), scale * 1.5)):
    viz.aim_camera(cam, cen, sc_, az, el)
    sc.render.filepath = f"{WORK}/dbg/{tag}_geo_{name}.png"
    bpy.ops.render.render(write_still=True)
