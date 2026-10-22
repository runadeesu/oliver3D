"""Hand segmentation: grow the skin-coloured surface from the fingertip, derive a hand frame."""
from common import *
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import breadth_first_order


def build_adj(faces, n):
    E = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    a = csr_matrix((np.ones(len(E), np.float32), (E[:, 0], E[:, 1])), shape=(n, n))
    return (a + a.T).tocsr()


def grow_region(adj, ok, seed):
    sub = adj.multiply(ok[:, None]).multiply(ok[None, :]).tocsr()
    order = breadth_first_order(sub, seed, directed=False, return_predecessors=False)
    m = np.zeros(adj.shape[0], bool)
    m[order] = True
    return m & ok


def skin_predicate(vc, hue=(-12.0, 48.0), sat=(0.16, 0.9), val=0.16):
    """Hue/saturation based skin test on albedo colours (robust to dark skin and texture noise)."""
    hsv = rgb_to_hsv(vc)
    h = hsv[:, 0]
    h = np.where(h > 180, h - 360, h)
    return (h > hue[0]) & (h < hue[1]) & (hsv[:, 1] > sat[0]) & (hsv[:, 1] < sat[1]) & (hsv[:, 2] > val)


def close_mask(adj, m, ok, iters=3):
    """Morphological closing on the mesh graph restricted to `ok` (fills texture-noise holes)."""
    mf = m.astype(np.float32)
    for _ in range(iters):  # dilate
        mf = ((adj @ mf) > 0).astype(np.float32).clip(0, 1) * ok + mf
        mf = (mf > 0).astype(np.float32)
    for _ in range(iters):  # erode
        deg = np.asarray(adj.sum(1)).ravel()
        nb = adj @ mf
        mf = ((mf > 0) & (nb >= deg - 0.5)).astype(np.float32)
    return mf > 0


def fill_enclosed(adj, m, near):
    """Add every connected non-hand patch that lies completely inside the search sphere (nails, wrinkles, texture noise whose colour
    is not skin-like). Patches connected to the rest of the body outside the sphere (sleeve, trousers) stay out."""
    from scipy.sparse.csgraph import connected_components
    rest = near & ~m
    idx = np.where(rest)[0]
    if len(idx) == 0:
        return m
    sub = adj[idx][:, idx]
    nc, lab = connected_components(sub, directed=False)
    outside = np.asarray(adj[:, ~near].sum(1)).ravel() > 0          # vertices that have a neighbour outside the sphere
    touches = np.zeros(nc, bool)
    np.logical_or.at(touches, lab, outside[idx])
    m = m.copy()
    add = idx[~touches[lab]]
    m[add] = True
    return m


def segment_hand(co, vc, adj, side, search_center, search_radius, shoulder, **skin_kw):
    """Return boolean vertex mask of the skin-coloured hand region of one side."""
    c = np.asarray(search_center, np.float64)
    near = np.linalg.norm(co - c, axis=1) < search_radius
    d = c - np.asarray(shoulder, np.float64)
    d /= np.linalg.norm(d)
    skin = skin_predicate(vc, **skin_kw)
    ok = near & skin
    idx = np.where(ok)[0]
    seed = idx[np.argmax(co[idx] @ d)]
    m = grow_region(adj, ok, seed)
    # fill holes caused by texture noise, but never leave the search sphere
    m = close_mask(adj, m, near, iters=3)
    m = fill_enclosed(adj, m, near)
    m = grow_region(adj, m | (near & skin & False), seed) if m[seed] else m
    return m, seed, vc[m].mean(0)


def hand_frame(P, tip_hint=None):
    """PCA frame of the hand point cloud: origin centroid, axis (proximal->distal) first."""
    c = P.mean(0)
    u, s, vt = np.linalg.svd(P - c, full_matrices=False)
    a = vt[0]
    proj = (P - c) @ a
    if tip_hint is not None and (np.asarray(tip_hint) - c) @ a < 0:
        a = -a
    return c, vt, s
