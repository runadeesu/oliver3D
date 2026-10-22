import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import hands_seg, hands_reeb
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
tag = sys.argv[1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
res = {}
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    used, f, fm = hands_reeb.hand_submesh(co, F, m)
    P = co[used].astype(np.float64)
    G, E = hands_reeb.weighted_graph(P, f)
    # sources: the hand-region boundary vertices closest to the sleeve = vertices adjacent to a non-region neighbour in the full mesh
    nonm = ~m
    border_full = np.asarray((adj[:, nonm]).sum(1)).ravel() > 0
    bidx = np.where(border_full[used])[0]
    dist = dijkstra(G, directed=False, indices=bidx, min_only=True)
    tree = cKDTree(P)
    nb = tree.query_ball_point(P, 0.012)
    ismax = np.array([dist[i] >= max(dist[j] for j in nb[i]) - 1e-9 for i in range(len(P))])
    tips = np.where(ismax)[0]
    tips = tips[np.argsort(-dist[tips])]
    print(f"== {tag} {side}: border verts {len(bidx)}, geodesic max {dist.max():.3f}, tips found {len(tips)}")
    for t in tips[:8]:
        print("   tip", P[t].round(3), "geo", round(dist[t], 3))
