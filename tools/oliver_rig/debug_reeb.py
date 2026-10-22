import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import hands_seg, hands_reeb
from scipy.sparse.csgraph import dijkstra
tag = sys.argv[1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    used, f, fm = hands_reeb.hand_submesh(co, F, m)
    P = co[used].astype(np.float64)
    G, E = hands_reeb.weighted_graph(P, f)
    # axis: from shoulder->hand centre; wrist = vertices with smallest projection
    a = np.asarray(h["center"]) - np.asarray(h["shoulder"]); a /= np.linalg.norm(a)
    s = P @ a
    src = np.where(s < s.min() + 0.006)[0]
    dist = dijkstra(G, directed=False, indices=src, min_only=True)
    lv = hands_reeb.level_components(P, G, dist)
    print(f"== {tag} {side}: verts {len(P)} geodesic max {np.nanmax(dist[np.isfinite(dist)]):.3f}")
    line = ""
    for d0, comps in lv:
        line += f"{int(d0*1000)}:{len(comps)} "
    print("  comps per 3mm level:", line)
