"""Copy the original textures of a model into <deliver>/<tag>/textures with the delivered names (+ merged metallic/roughness).
python prep_textures.py <tag> <src_tex_dir> <dst_dir>"""
import sys, os, shutil
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from common import MODELS
import materials
tag, src, dst = sys.argv[1:4]
prefix = MODELS[tag]["title"]
os.makedirs(dst, exist_ok=True)
for srcname, dstname in (("texture_0.png", "base_color"), ("texture_0_normal.png", "normal"), ("texture_0_roughness.png", "roughness"), ("texture_0_metallic.png", "metallic")):
    d = os.path.join(dst, f"{prefix}_{dstname}.png")
    if not os.path.exists(os.path.join(src, srcname)):
        print("no source texture for", dstname, "(skipped)")
        continue
    if not os.path.exists(d):
        shutil.copyfile(os.path.join(src, srcname), d)
if os.path.exists(os.path.join(dst, f"{prefix}_roughness.png")) and os.path.exists(os.path.join(dst, f"{prefix}_metallic.png")):
    materials.merge_metal_rough(os.path.join(dst, f"{prefix}_roughness.png"), os.path.join(dst, f"{prefix}_metallic.png"), os.path.join(dst, f"{prefix}_metallic_roughness.png"))
print("textures ready:", sorted(os.listdir(dst)))
