"""Diagnose the hand segmentation / tip detection of one model. blender -b --factory-startup --python debug_hand_stage.py -- <tag>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import hands_seg, hands_digits
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    P = co[m]
    log(tag, side, "mask verts", int(m.sum()), "bbox", P.min(0).round(3), P.max(0).round(3), "mean colour", col.round(2), "seed", co[seed].round(3))
    used, f, Pm, G, bidx, dist = hands_digits.geodesic_field(co, F, m, adj)
    log(tag, side, "submesh verts", len(Pm), "border verts", len(bidx), "dist max %.3f" % dist[np.isfinite(dist)].max())
    tips = hands_digits.find_tips(Pm, dist)
    log(tag, side, "tip candidates", len(tips), [ (Pm[t].round(3).tolist(), round(float(dist[t]),3)) for t in tips][:8])
    # also save the mask as vertex colour image
    np.save(f"{WORK}/{tag}_dbg_mask_{side}.npy", m)
