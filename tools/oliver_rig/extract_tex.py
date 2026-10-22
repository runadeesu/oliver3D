"""Write the packed images of the current .blend to a directory.
blender -b <tag>_raw.blend --python extract_tex.py -- <out_dir>"""
import bpy, sys, os, hashlib
out = sys.argv[sys.argv.index('--')+1]
os.makedirs(out, exist_ok=True)
for im in bpy.data.images:
    if im.packed_file:
        name = im.name if im.name.endswith('.png') else im.name + '.png'
        p = os.path.join(out, name)
        data = im.packed_file.data
        open(p,'wb').write(data)
        print("TEX", p, len(data), hashlib.md5(data).hexdigest())
