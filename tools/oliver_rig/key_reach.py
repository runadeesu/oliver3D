"""How far do the mouth shape keys reach? Max displacement of the vertices that are `above_mm` or more above the mouth (nose, glasses, hair, hat)
and of the vertices that are far to the side / behind. blender -b rig.blend --python key_reach.py -- <tag> [above_mm=50]
Prints KEYREACH lines (read by make_readmes.py)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
tag = sys.argv[sys.argv.index("--") + 1:][0]
above = float(sys.argv[sys.argv.index("--") + 2]) if len(sys.argv) > sys.argv.index("--") + 2 else 50.0
cfg = load_config(tag)
m = cfg["mouth"]
z0 = np.polyval(m["poly4_mm"], m["cx_mm"]) / 1000.0
ob = [o for o in bpy.data.objects if o.type == "MESH"][0]
sk = ob.data.shape_keys.key_blocks
n = len(ob.data.vertices)
base = np.empty(n * 3, np.float32); sk["Basis"].data.foreach_get("co", base); base = base.reshape(-1, 3)
sel = base[:, 2] > z0 + above / 1000.0
worst = (0.0, "")
for k in sk:
    if k.name == "Basis":
        continue
    a = np.empty(n * 3, np.float32); k.data.foreach_get("co", a)
    d = np.linalg.norm(a.reshape(-1, 3) - base, axis=1) * 1000
    mx = float(d[sel].max())
    print(f"KEYREACH {k.name} above {above:.0f} mm: max {mx:.2f} mm ({int((d[sel] > 0.01).sum())} vertices > 0.01 mm)")
    if mx > worst[0]:
        worst = (mx, k.name)
print(f"KEYREACH max {worst[0]:.2f} mm by {worst[1]}")
# the Jaw bone: weight on the vertices far above the mouth (the bone moves them by weight * rotation)
jg = ob.vertex_groups.get("Jaw")
wj = np.zeros(n, np.float32)
for v in ob.data.vertices:
    for g in v.groups:
        if g.group == jg.index:
            wj[v.index] = g.weight
print(f"KEYREACH Jaw-bone weight above {above:.0f} mm: max {wj[sel].max():.3f} ({int((wj[sel] > 0.01).sum())} vertices > 0.01)")
