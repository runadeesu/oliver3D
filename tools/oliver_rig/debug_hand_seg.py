"""blender -b --factory-startup --python debug_hand_seg.py -- <tag> : segment both hands, render closeups with region in red."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg

tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
colors = vc.copy()
info = {}
for side in ("R", "L"):
    h = cfg["hand_search"][side]
    sgn = -1 if side == "R" else 1
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    colors[m] = colors[m] * 0.3 + np.array([0.7, 0, 0])
    P = co[m]
    cen, vt, s = hands_seg.hand_frame(P, co[seed])
    info[side] = dict(n=int(m.sum()), seed=co[seed].tolist(), centroid=cen.tolist(), axes=vt.tolist(), ext=((P - cen) @ vt.T).ptp(0).tolist())
    log(tag, side, "n", m.sum(), "seed", co[seed].round(3), "extent", np.round(info[side]["ext"], 3))
viz.clear_scene()
ob = viz.build_debug_object(co, F, uv, colors)
out = os.path.join(WORK, "dbg")
os.makedirs(out, exist_ok=True)
specs = []
for side in ("R", "L"):
    c = cfg["hand_search"][side]["center"]
    specs += [(f"seg{side}_f", c, 0.35, 0), (f"seg{side}_b", c, 0.35, 180)]
viz.render_specs(f"{out}/{tag}", specs, 640, color_type="VERTEX")
