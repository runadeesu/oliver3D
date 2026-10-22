"""Locally refine a coarse (decimated) mesh around the hands and the mouth so that fingers / lips can be cut and deformed cleanly.
Linear 1-to-4 subdivision (positions, UVs unchanged in shape; T-junctions are closed by Blender's edge subdivision) of every triangle whose
centroid lies in a sphere around a hand or the mouth, repeated `levels` times.
blender -b --factory-startup --python refine_regions.py -- <tag> [levels=2]
Reads <WORK>/<tag>_arrays.npz (keeps the original as <tag>_arrays_unrefined.npz), settings from tools/configs/<tag>.json ["refine"]:
  {"hand_radius": 0.12, "mouth_center_mm": [x, y, z], "mouth_radius": 0.12, "levels": 2}"""
import sys, os, shutil
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import bmesh

a = sys.argv[sys.argv.index("--") + 1:]
tag = a[0]
cfg = load_config(tag)
rc = cfg.get("refine", {})
levels = int(a[1]) if len(a) > 1 else rc.get("levels", 2)
src = f"{WORK}/{tag}_arrays.npz"
bak = f"{WORK}/{tag}_arrays_unrefined.npz"
if not os.path.exists(bak):
    shutil.copyfile(src, bak)
d = np.load(bak)
co, F, uv, mat = d["co"], d["faces"], d["uv"], d["mat"]
centers = [(np.array(cfg["hand_search"][s]["center"]), rc.get("hand_radius", 0.12)) for s in "RL"]
mc = np.array(rc["mouth_center_mm"], float) / 1000.0
centers.append((mc, rc.get("mouth_radius", 0.12)))
log(tag, "refine: faces", len(F), "levels", levels)
me = arrays_to_mesh("m", co, F, uv, mat)
bm = bmesh.new()
bm.from_mesh(me)
uvl = bm.loops.layers.uv.active
for lvl in range(levels):
    bm.faces.ensure_lookup_table()
    sel_edges = set()
    nsel = 0
    for f in bm.faces:
        c = f.calc_center_median()
        cp = np.array(c[:])
        if any(np.linalg.norm(cp - cc) < r for cc, r in centers):
            nsel += 1
            for e in f.edges:
                sel_edges.add(e)
    res = bmesh.ops.subdivide_edges(bm, edges=list(sel_edges), cuts=1, use_grid_fill=True, use_single_edge=False, smooth=0.0)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
    log(tag, "level", lvl + 1, "selected", nsel, "-> faces", len(bm.faces))
bm.to_mesh(me)
bm.free()
ob_ = bpy.data.objects.new('m', me)
bpy.context.scene.collection.objects.link(ob_)
co2, F2, uv2, mat2 = mesh_to_arrays(ob_)
tex = load_texture(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
vc = vertex_colors(co2, F2, uv2, tex)
ext0 = (uv.max(1) - uv.min(1)).max(1)
ext1 = (uv2.max(1) - uv2.min(1)).max(1)
log(tag, "uv extent median before/after (texels @4096):", float(np.median(ext0) * 4096), float(np.median(ext1) * 4096))
np.savez(src, co=co2, faces=F2, uv=uv2, mat=mat2, vcol=vc)
log(tag, "saved", src, co2.shape, F2.shape)
