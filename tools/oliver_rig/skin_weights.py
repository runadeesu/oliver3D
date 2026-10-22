"""Skin weights from surface (geodesic) distance to the bones + explicit mouth weights."""
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
