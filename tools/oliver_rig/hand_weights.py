"""Explicit skin weights for the hand region (palm / 4 fingers / thumb) from the digit chains."""
from common import *


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


def hand_weights(co, vids, side_name, hand, bone_pos, bone_index, nbones):
    """Returns (rows (len(vids), nbones), gate (len(vids),)) where gate = how much the explicit hand weights replace the
    generic body weights (0 at the forearm side of the wrist, 1 in the hand)."""
    P = co[vids].astype(np.float64)
    K = len(vids)
    Wx = np.zeros((K, nbones), np.float32)
    S = side_name
    fingers = ["Index", "Middle", "Ring", "Pinky"]
    comp_sum = np.zeros(K)
    memb = {}
    gates = {}
    arcs = {}
    for fi, f in enumerate(fingers):
        J = np.array([bone_pos[f"{S}Hand{f}1"][0], bone_pos[f"{S}Hand{f}2"][0], bone_pos[f"{S}Hand{f}3"][0], bone_pos[f"{S}Hand{f}3"][1]])
        d, s, cum = chain_params(P, J)
        r = hand["digits"][f.lower()]["radius"]
        r = max(r, 0.0085)
        m = 1 - smoothstep(1.15 * r, 2.0 * r, d)
        gate = smoothstep(-0.012, 0.006, s)
        memb[f] = m * gate
        arcs[f] = (s, cum)
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
