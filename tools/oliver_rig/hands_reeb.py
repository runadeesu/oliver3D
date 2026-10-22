"""Geodesic level-set (Reeb graph) analysis of a segmented hand: reveals how many digits are topologically separate."""
from common import *
from scipy.sparse import csr_matrix, coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components


def hand_submesh(co, faces, mask):
    fm = mask[faces].all(1)
    f = faces[fm]
    used = np.unique(f)
    remap = -np.ones(len(co), np.int64)
    remap[used] = np.arange(len(used))
    return used, remap[f], fm


def weighted_graph(P, F):
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    E = np.unique(np.sort(E, 1), axis=0)
    w = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
    n = len(P)
    g = coo_matrix((w, (E[:, 0], E[:, 1])), shape=(n, n))
    return (g + g.T).tocsr(), E


def level_components(P, G, dist, step=0.003, width=0.003):
    """For every level of geodesic distance, connected components of the band [d, d+width]."""
    out = []
    dmax = dist[np.isfinite(dist)].max()
    d0 = 0.0
    while d0 < dmax:
        band = np.where((dist >= d0) & (dist < d0 + width))[0]
        if len(band) > 3:
            sub = G[band][:, band]
            nc, lab = connected_components(sub, directed=False)
            comps = []
            for c in range(nc):
                idx = band[lab == c]
                if len(idx) >= 4:
                    comps.append((len(idx), P[idx].mean(0)))
            out.append((d0, comps))
        d0 += step
    return out
