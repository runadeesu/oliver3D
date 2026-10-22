"""Dump mesh arrays + per-vertex texture colour of a normalized raw import to .npz (for numpy-only analysis).
blender -b raw.blend --python prep_arrays.py -- <tag> <base_color_png>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *

tag, texpath = sys.argv[sys.argv.index("--") + 1:][:2]
obj = [o for o in bpy.data.objects if o.type == "MESH"][0]
co, faces, uv, mat = mesh_to_arrays(obj)
tex = load_texture(texpath)
vc = vertex_colors(co, faces, uv, tex)
out = os.path.join(WORK, f"{tag}_arrays.npz")
np.savez(out, co=co, faces=faces, uv=uv, mat=mat, vcol=vc)
log("saved", out, co.shape, faces.shape)
