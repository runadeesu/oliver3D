"""Side / top views of the segmented R hand (texture shown, region tinted). blender -b --factory-startup --python ... -- <tag>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
h = cfg["hand_search"]["R"]
m, seed, col = hands_seg.segment_hand(co, vc, adj, -1, h["center"], h["radius"], h["shoulder"])
colors = vc.copy()
colors[m] = colors[m] * 0.6 + np.array([0.4, 0, 0])
viz.clear_scene()
viz.build_debug_object(co, F, uv, colors)
c = np.array(h["center"])
specs = [("side", c, 0.4, 270), ("top", c, 0.4, 0, 90), ("front", c, 0.4, 0)]
viz.render_specs(f"{WORK}/dbg/{tag}_hv", specs, 600, color_type="VERTEX")
