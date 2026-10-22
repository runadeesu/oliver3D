"""Close-ups of the R hand along the palm normal direction (camera at -X), plain texture. -- <tag> [scale]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg
tag = sys.argv[sys.argv.index("--") + 1]
scale = float(sys.argv[sys.argv.index("--") + 2]) if len(sys.argv) > sys.argv.index("--") + 2 else 0.26
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
h = cfg["hand_search"]["R"]
m, seed, col = hands_seg.segment_hand(co, vc, adj, -1, h["center"], h["radius"], h["shoulder"])
c = co[m].mean(0)
# remove everything except the hand region + a little margin so the sleeve/body does not occlude
keep = np.zeros(len(co), bool)
keep[np.where(m)[0]] = True
fm = keep[F].all(1)
viz.clear_scene()
viz.build_debug_object(co, F[fm], uv[fm], vc)
specs = [("a_m90", c, scale, 270), ("b_p90", c, scale, 90), ("c_front", c, scale, 0), ("d_back", c, scale, 180), ("e_top", c, scale, 0, 90), ("f_bot", c, scale, 0, -90)]
viz.render_specs(f"{WORK}/dbg/{tag}_hc", specs, 700, color_type="VERTEX")
