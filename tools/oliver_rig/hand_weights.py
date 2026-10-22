"""Explicit skin weights for the hand region (palm / 4 fingers / thumb) from the digit chains."""
from common import *


FUSED_THICKNESS_SCALE = 0.3
GEO_TAU = 0.8


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def chain_params(P, J):
    """Distance of points to the polyline J (K+1,3) and arc-length parameter of the closest point.
    Before J0 the parameter continues linearly (negative values)."""
    seg = J[1:] - J[:-1]
    L = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0], np.cumsum(L)])
    best_d = np.full(len(P), np.inf)
    best_s = np.zeros(len(P))
    for k in range(len(seg)):
        a = J[k]
        ab = seg[k]
        t = ((P - a) @ ab) / (ab @ ab)
        tc = np.clip(t, 0, 1)
        if k == 0:
            tc = np.minimum(t, 1.0)          # allow t<0 for the first segment (palm side)
        q = a + np.outer(tc, ab)
        d = np.linalg.norm(P - q, axis=1)
        upd = d < best_d
        best_d[upd] = d[upd]
        best_s[upd] = cum[k] + tc[upd] * L[k]
    return best_d, best_s, cum


def hand_weights(co, vids, side_name, hand, bone_pos, bone_index, nbones, graph=None):
    """Returns (rows (len(vids), nbones), gate (len(vids),)) where gate = how much the explicit hand weights replace the
    generic body weights (0 at the forearm side of the wrist, 1 in the hand)."""
    P = co[vids].astype(np.float64)
    K = len(vids)
    Wx = np.zeros((K, nbones), np.float32)
    S = side_name
    n_palm = np.array(hand["n"], float)
    n_palm /= np.linalg.norm(n_palm)
    fingers = ["Index", "Middle", "Ring", "Pinky"]
    comp_sum = np.zeros(K)
    memb = {}
    gates = {}
    arcs = {}
    seeds = {}
    for fi, f in enumerate(fingers):
        J = np.array([bone_pos[f"{S}Hand{f}1"][0], bone_pos[f"{S}Hand{f}2"][0], bone_pos[f"{S}Hand{f}3"][0], bone_pos[f"{S}Hand{f}3"][1]])
        dg = hand["digits"][f.lower()]
        if dg.get("fused"):
            # fused (webbed) fingers are flat paddles whose synthesized axis does not sit mid-thickness:
            # measure the distance mostly across the finger (palm-plane), not through its thickness
            k = FUSED_THICKNESS_SCALE
            Tm = np.eye(3) + (k - 1.0) * np.outer(n_palm, n_palm)
            d, s, cum = chain_params(P @ Tm, J @ Tm)
        else:
            d, s, cum = chain_params(P, J)
        r = dg["radius"]
        r = max(r, 0.0085)
        wide = 1.6 if dg.get("fused") else 1.0
        m = 1 - smoothstep(1.15 * wide * r, 2.0 * wide * r, d)
        gate = smoothstep(-0.012, 0.006, s)
        memb[f] = m * gate
        arcs[f] = (s, cum)
        if dg.get("fused"):
            core = (d < 0.75 * r) & (s > 0.0)
            if core.sum() < 8:
                core = np.zeros(K, bool)
                core[np.argsort(np.where(s > 0, d, np.inf))[:8]] = True
            seeds[f] = vids[core]
    if graph is not None and len(seeds) == len(fingers):
        # Fused fingers: the carved slits only separate the flesh through the mesh topology (the two walls of a slit are
        # ~1 mm apart, so Euclidean distance to the finger axes cannot tell them apart). Partition by geodesic distance
        # to each finger's core so every slit wall follows its own finger, blending only where the fingers are joined.
        from scipy.sparse.csgraph import dijkstra
        G = np.stack([dijkstra(graph, directed=False, indices=seeds[f], min_only=True, limit=0.2)[vids] for f in fingers], 1)
        G = np.where(np.isfinite(G), G, 1.0)
        tau = GEO_TAU * np.mean([max(hand["digits"][f.lower()]["radius"], 0.0085) for f in fingers])
        wg = np.exp(-(((G - G.min(1, keepdims=True)) / tau) ** 2))
        wg /= wg.sum(1, keepdims=True)
        m_any = np.max(np.stack([memb[f] for f in fingers], 1), 1)
        for fi, f in enumerate(fingers):
            memb[f] = m_any * wg[:, fi]
    # thumb
    Jt = np.array([bone_pos[f"{S}HandThumb1"][0], bone_pos[f"{S}HandThumb2"][0], bone_pos[f"{S}HandThumb3"][0], bone_pos[f"{S}HandThumb3"][1]])
    dt, st, cumt = chain_params(P, Jt)
    rt = max(hand["thumb"]["radius"], 0.011)
    mt = 1 - smoothstep(1.2 * rt, 2.4 * rt, dt)
    tot = sum(memb.values()) + mt
    norm = np.maximum(tot, 1.0)
    for f in fingers:
        memb[f] = memb[f] / norm
    mt = mt / norm
    # distribute along the bones
    h = 0.0055
    for f in fingers:
        s, cum = arcs[f]
        c1, c2 = cum[1], cum[2]
        b1 = 1 - smoothstep(c1 - h, c1 + h, s)
        b3 = smoothstep(c2 - h, c2 + h, s)
        b2 = np.clip(1 - b1 - b3, 0, 1)
        for k, b in enumerate((b1, b2, b3)):
            Wx[:, bone_index[f"{S}Hand{f}{k+1}"]] = memb[f] * b
    c1, c2 = cumt[1], cumt[2]
    b1 = 1 - smoothstep(c1 - h, c1 + h, st)
    b3 = smoothstep(c2 - h, c2 + h, st)
    b2 = np.clip(1 - b1 - b3, 0, 1)
    for k, b in enumerate((b1, b2, b3)):
        Wx[:, bone_index[f"{S}HandThumb{k+1}"]] = mt * b
    used = Wx.sum(1)
    Wx[:, bone_index[f"{S}Hand"]] = np.clip(1 - used, 0, 1)
    # gate across the wrist: forearm side -> generic weights
    Wp = np.array(hand["W"], float)
    a = np.array(hand["a"], float)
    sw = (P - Wp) @ a
    gate = smoothstep(-0.008, 0.016, sw)
    return Wx, gate
