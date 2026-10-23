"""Skin weights: surface heat diffusion with visibility (heat_weights) or surface (geodesic) distance to the bones (geodesic_weights) + explicit mouth weights."""
from common import *
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra


def point_segment_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab + 1e-12), 0, 1)
    q = a + np.outer(t, ab)
    return np.linalg.norm(P - q, axis=1), t


def mesh_graph(co, faces):
    E = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    E = np.unique(np.sort(E, 1), axis=0)
    w = np.linalg.norm(co[E[:, 0]] - co[E[:, 1]], axis=1)
    n = len(co)
    g = coo_matrix((w, (E[:, 0], E[:, 1])), shape=(n, n))
    return (g + g.T).tocsr()


def geodesic_weights(co, faces, bones, valid=None, topk=4, log_fn=log):
    """Returns (N, B) float32 weight matrix (rows sum to 1 over the bones with name != 'Jaw').
    valid: boolean mask of vertices taking part (others get zero rows)."""
    n = len(co)
    G = mesh_graph(co, faces)
    B = len(bones)
    score = np.full((n, B), -np.inf, np.float32)
    eu_best = np.full(n, np.inf)
    eu_arg = np.zeros(n, np.int32)
    t = timer()
    for bi, b in enumerate(bones):
        if b["name"] == "Jaw" or b["group"] in ("hand", "finger"):
            continue                                            # Jaw / hand / fingers use explicit weights
        d_eu, tproj = point_segment_dist(co, b["head"], b["tail"])
        upd = d_eu < eu_best
        eu_best[upd] = d_eu[upd]
        eu_arg[upd] = bi
        min_seeds = {"torso": 400, "leg": 300, "head": 300, "arm": 120, "hand": 80, "finger": 25, "jaw": 10}.get(b["group"], 50)
        r = b["seed"]
        if (d_eu <= r).sum() < min_seeds:                      # bone buried inside the volume -> grow the seed radius
            r = max(r, float(np.partition(d_eu, min_seeds)[min_seeds]) * 1.15)
        # do not let the seed cylinder extend past the bone ends (would make neighbouring bones tie)
        along = np.linalg.norm(b["tail"] - b["head"])
        t_unc = ((co - b["head"]) @ (b["tail"] - b["head"])) / (along ** 2 + 1e-12)
        cap = 0.35 * r / (along + 1e-9)
        seeds = np.where((d_eu <= r) & (t_unc > -cap) & (t_unc < 1 + cap))[0]
        if len(seeds) < 5:
            seeds = np.where(d_eu <= r)[0]
        if len(seeds) == 0:
            continue
        lim = 6.0 * b["sigma"]
        g = dijkstra(G, directed=False, indices=seeds, min_only=True, limit=lim)
        fin = np.isfinite(g)
        score[fin, bi] = -(g[fin] / b["sigma"]) ** 2
    log_fn("geodesic fields done", round(t(), 1), "s for", B, "bones")
    # softmax over bones
    mx = score.max(1)
    has = np.isfinite(mx)
    Wm = np.zeros((n, B), np.float32)
    sc = score[has] - mx[has, None]
    e = np.exp(np.where(np.isfinite(sc), sc, -1e9))
    Wm[has] = e / e.sum(1, keepdims=True)
    # fallback: vertices reached by no bone -> nearest bone (euclid) with a soft blend of the 2 nearest
    nof = np.where(~has)[0]
    if len(nof):
        log_fn("fallback (euclid nearest bone) for", len(nof), "vertices")
        names = [b["name"] for b in bones]
        d_all = np.stack([point_segment_dist(co[nof], b["head"], b["tail"])[0] if b["name"] != "Jaw" else np.full(len(nof), np.inf) for b in bones], 1)
        inv = 1.0 / (d_all + 0.01) ** 3
        Wm[nof] = (inv / inv.sum(1, keepdims=True)).astype(np.float32)
    # top-k
    if topk:
        idx = np.argsort(-Wm, axis=1)[:, topk:]
        np.put_along_axis(Wm, idx, 0, axis=1)
        s = Wm.sum(1, keepdims=True)
        Wm = Wm / np.maximum(s, 1e-9)
    if valid is not None:
        Wm[~valid] = 0
    return Wm


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def apply_jaw(W, bones, w_jaw, part, mouth_mask, co=None, z_mouth=None):
    """Head region -> Head bone (blending into the generic neck/torso weights over the throat), then split Head/Neck with the
    Jaw bone using the explicit jaw weights; explicit Head/Jaw weights for the mouth parts."""
    names = [b["name"] for b in bones]
    ih, ij, in_ = names.index("Head"), names.index("Jaw"), names.index("Neck")
    W = W.copy()
    sk = ~mouth_mask
    lam = smoothstep(0.0, 0.5, w_jaw)
    if co is not None:
        lam = np.maximum(lam, smoothstep(z_mouth - 0.075, z_mouth - 0.020, co[:, 2]))
    onehot = np.zeros_like(W)
    onehot[:, ih] = 1.0
    W[sk] = W[sk] * (1 - lam[sk, None]) + onehot[sk] * lam[sk, None]
    share = w_jaw
    head_group = W[:, ih] + W[:, in_]
    W[sk, ij] = head_group[sk] * share[sk]
    W[sk, ih] = W[sk, ih] * (1 - share[sk])
    W[sk, in_] = W[sk, in_] * (1 - share[sk])
    # pocket / teeth / tongue: explicit
    W[mouth_mask] = 0
    W[mouth_mask, ih] = 1 - w_jaw[mouth_mask]
    W[mouth_mask, ij] = w_jaw[mouth_mask]
    return W


# ----------------------------------------------------------------------------------------------------------------------
# surface heat diffusion ("bone heat" on the mesh surface)
# ----------------------------------------------------------------------------------------------------------------------
def vertex_normals(co, faces):
    fn = np.cross(co[faces[:, 1]] - co[faces[:, 0]], co[faces[:, 2]] - co[faces[:, 0]])
    vn = np.zeros_like(co)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def cotan_laplacian(co, faces):
    """Symmetric cotangent weights (clamped to >= 0 so that the system stays an M-matrix) and the lumped vertex areas."""
    n = len(co)
    I, J, V = [], [], []
    area = np.zeros(n)
    for k in range(3):
        i, j, l = faces[:, k], faces[:, (k + 1) % 3], faces[:, (k + 2) % 3]
        u, v = co[j] - co[i], co[l] - co[i]
        cr = np.linalg.norm(np.cross(u, v), axis=1)
        cot = np.einsum("ij,ij->i", u, v) / np.maximum(cr, 1e-14)
        cot = np.clip(cot, 0.0, 20.0)
        I.append(j); J.append(l); V.append(0.5 * cot)            # edge (j, l) is opposite to vertex i
        if k == 0:
            tri_area = 0.5 * cr
    for k in range(3):
        np.add.at(area, faces[:, k], tri_area / 3.0)
    Wm = coo_matrix((np.concatenate(V), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsr()
    Wm = Wm + Wm.T
    d = np.asarray(Wm.sum(1)).ravel()
    from scipy.sparse import diags
    L = diags(d) - Wm
    return L.tocsc(), np.maximum(area, 1e-12)


def heat_weights(co, faces, bones, valid=None, topk=4, c_heat=1.0, visible_slack=0.0, smooth_iter=0, log_fn=log):
    """Bone-heat weights on the mesh surface: for every bone solve (L + M H) w = M H p, where p marks the vertices whose nearest *visible* bone
    it is (the bone must lie inside the surface seen from the vertex: normal . (nearest bone point - vertex) < 0, so that the torso beside a
    baggy sleeve is not claimed by the arm bone) and H = c / d^2 (d = distance to that bone). Surface diffusion keeps the weights smooth,
    follows the connectivity of the garment (a sleeve is only joined to the torso at the shoulder) and gives gradual transitions at joints.
    Returns (N, B) float32, rows sum to 1 over the bones taking part (not Jaw / hand / finger bones)."""
    from scipy.sparse import diags
    from scipy.sparse.linalg import splu
    n = len(co)
    t = timer()
    B = len(bones)
    use = [bi for bi, b in enumerate(bones) if b["name"] != "Jaw" and b["group"] not in ("hand", "finger")]
    nrm = vertex_normals(co, faces)
    D = np.full((n, len(use)), np.inf)
    Q = np.zeros((len(use), n, 3), np.float32)
    for k, bi in enumerate(use):
        b = bones[bi]
        a_, b_ = np.asarray(b["head"], float), np.asarray(b["tail"], float)
        ab = b_ - a_
        tt = np.clip(((co - a_) @ ab) / (ab @ ab + 1e-12), 0, 1)
        q = a_ + np.outer(tt, ab)
        D[:, k] = np.linalg.norm(co - q, axis=1)
        Q[k] = (q - co).astype(np.float32)
    inside = np.stack([np.einsum("ij,ij->i", nrm, Q[k]) < visible_slack * D[:, k] for k in range(len(use))], 1)
    Dv = np.where(inside, D, np.inf)
    none_vis = ~np.isfinite(Dv.min(1))
    Dv[none_vis] = D[none_vis]                                      # nothing visible (inverted normals, thin sheets): plain nearest bone
    near = Dv.argmin(1)
    dmin = np.maximum(Dv.min(1), 0.01)
    log_fn("heat: vertices without a visible bone:", int(none_vis.sum()), "of", n)
    L, area = cotan_laplacian(co, faces)
    H = c_heat / dmin ** 2
    A = (L + diags(area * H)).tocsc()
    lu = splu(A)
    log_fn("heat: factorised", round(t(), 1), "s")
    Wm = np.zeros((n, B), np.float32)
    for k, bi in enumerate(use):
        sel = near == k
        if not sel.any():
            continue
        rhs = np.where(sel, area * H, 0.0)
        Wm[:, bi] = np.clip(lu.solve(rhs), 0.0, 1.0)
    s = Wm.sum(1, keepdims=True)
    Wm = Wm / np.maximum(s, 1e-12)
    if smooth_iter:                                              # remove the ragged patches left by the per-vertex nearest-bone seeds
        G = mesh_graph(co, faces)
        deg = np.asarray((G > 0).sum(1)).ravel().astype(np.float64)
        Aadj = (G > 0).astype(np.float64)
        Aadj = diags(1.0 / np.maximum(deg, 1)) @ Aadj
        for _ in range(smooth_iter):
            Wm = (0.5 * Wm + 0.5 * (Aadj @ Wm)).astype(np.float32)
    if topk:
        idx = np.argsort(-Wm, axis=1)[:, topk:]
        np.put_along_axis(Wm, idx, 0, axis=1)
        Wm = Wm / np.maximum(Wm.sum(1, keepdims=True), 1e-12)
    if valid is not None:
        Wm[~valid] = 0
    log_fn("heat weights done", round(t(), 1), "s")
    return Wm
