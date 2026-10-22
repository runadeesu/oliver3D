"""Digit (finger/thumb) detection for a segmented hand: tips, hand frame, thumb side."""
from common import *
import hands_seg, hands_reeb
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree


def geodesic_field(co, faces, mask, adj):
    used, f, fm = hands_reeb.hand_submesh(co, faces, mask)
    P = co[used].astype(np.float64)
    G, E = hands_reeb.weighted_graph(P, f)
    border_full = np.asarray((adj[:, ~mask]).sum(1)).ravel() > 0
    bidx = np.where(border_full[used])[0]
    dist = dijkstra(G, directed=False, indices=bidx, min_only=True)
    return used, f, P, G, bidx, dist


def find_tips(P, dist, radius=0.007, min_frac=0.40, min_sep=0.013):
    """Fingertip candidates = local maxima of the geodesic distance from the wrist. Small neighbourhood so that tightly
    packed fingers are found; near-duplicates (closer than min_sep) are pruned keeping the farther one."""
    tree = cKDTree(P)
    nb = tree.query_ball_point(P, radius)
    ismax = np.array([dist[i] >= max(dist[j] for j in nb[i]) - 1e-9 for i in range(len(P))])
    cand = np.where(ismax & (dist > min_frac * dist.max()))[0]
    cand = cand[np.argsort(-dist[cand])]
    kept = []
    for c in cand:
        if all(np.linalg.norm(P[c] - P[k]) >= min_sep for k in kept):
            kept.append(c)
    return np.array(kept, dtype=int)


def select_digits(P, dist, tips, W, iso=0.055, lat_sep=0.010, min_frac=0.60):
    """Split tip candidates into (thumb, fingers). Thumb = isolated candidate (nearest other candidate >= iso away)
    with the largest geodesic distance. Fingers = remaining candidates, de-duplicated by lateral separation."""
    T = P[tips]
    nn = np.array([min(np.linalg.norm(T[i] - T[j]) for j in range(len(tips)) if j != i) for i in range(len(tips))])
    iso_idx = [i for i in range(len(tips)) if nn[i] >= iso]
    if iso_idx:
        thumb_i = max(iso_idx, key=lambda i: dist[tips[i]])
    else:                                    # fall back: farthest from centroid of the others
        thumb_i = int(np.argmax([np.linalg.norm(T[i] - np.delete(T, i, 0).mean(0)) for i in range(len(tips))]))
    rest = [i for i in range(len(tips)) if i != thumb_i]
    gmax = max(dist[tips[i]] for i in rest)
    rest = [i for i in rest if dist[tips[i]] >= min_frac * gmax and nn[i] < iso]
    rest.sort(key=lambda i: -dist[tips[i]])
    a0 = T[rest[:3]].mean(0) - W
    a0 /= np.linalg.norm(a0)
    kept = []
    for i in rest:
        lat = lambda p, q: np.linalg.norm((p - q) - ((p - q) @ a0) * a0)
        if all(lat(T[i], T[k]) > lat_sep for k in kept):
            kept.append(i)
    return tips[thumb_i], [tips[i] for i in kept]


def hand_frame_from_tips(P, bidx, tips, dist, side):
    """Wrist centre W, axis a (wrist->fingers), thumb dir u, palm normal n (right-handed per side)."""
    W = P[bidx].mean(0)
    thumb, others = select_digits(P, dist, tips, W)
    fingers_c = P[others].mean(0)
    a = fingers_c - W
    a /= np.linalg.norm(a)
    u = (P[thumb] - fingers_c)
    u -= (u @ a) * a
    u /= np.linalg.norm(u)
    # palm normal: left hand (+x) n = a x u ; right hand (-x) n = u x a  (derived from the anatomical position)
    n = np.cross(a, u) if side == "L" else np.cross(u, a)
    n /= np.linalg.norm(n)
    return W, a, u, n, thumb, others


# ----------------------------------------------------------------------------
# digit axes + joints
# ----------------------------------------------------------------------------
# lengths from MCP joint centre to the fingertip, as a fraction of hand length (wrist -> middle fingertip)
FINGER_LEN = {"index": 0.50, "middle": 0.53, "ring": 0.51, "pinky": 0.42}
# bone split of a finger (proximal, middle, distal) as cumulative fractions from MCP
FINGER_SPLIT = (0.0, 0.47, 0.76, 1.0)
FINGER_NAMES = ["index", "middle", "ring", "pinky"]


def plane_loops(P, F, origin, nrm, e1, e2):
    """Closed loops of the intersection between a triangle mesh and a plane. Returns list of (N,2) arrays in (e1,e2)."""
    d = (P - origin) @ nrm
    dd = d[F]
    cross = (dd.min(1) < 0) & (dd.max(1) >= 0)
    f = F[cross]
    if len(f) == 0:
        return []
    # crossing edges
    segs = []
    pts = {}

    def xp(i, j):
        key = (i, j) if i < j else (j, i)
        if key not in pts:
            t = d[i] / (d[i] - d[j])
            pts[key] = P[i] + (P[j] - P[i]) * t
        return key
    for tri in f:
        ks = []
        for k in range(3):
            i, j = tri[k], tri[(k + 1) % 3]
            if (d[i] < 0) != (d[j] < 0):
                ks.append(xp(i, j))
        if len(ks) == 2:
            segs.append(ks)
    nb = {}
    for a_, b_ in segs:
        nb.setdefault(a_, []).append(b_)
        nb.setdefault(b_, []).append(a_)
    seen = set()
    loops = []
    for start in nb:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxts = [n for n in nb[cur] if n != prev and n not in seen]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) >= 6:
            q = np.array([pts[k] for k in loop]) - origin
            loops.append(np.stack([q @ e1, q @ e2], 1))
    return loops


def poly_area_centroid(L):
    x, y = L[:, 0], L[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cr = x * y1 - x1 * y
    A = cr.sum() / 2
    if abs(A) < 1e-12:
        return 0.0, L.mean(0)
    cx = ((x + x1) * cr).sum() / (6 * A)
    cy = ((y + y1) * cr).sum() / (6 * A)
    return abs(A), np.array([cx, cy])


def fit_axis(P, F, tip, g, e1, e2, t_range=(0.005, 0.050), step=0.004, area_max=7.5e-4, jump=0.0075):
    """Centre line of a finger from cross-section loops. Each loop's area centroid is tracked from the tip towards the
    base; tracking stops when the loop merges with a neighbour (area jump) or jumps laterally.
    Returns (centre_point, dir(base->tip), radius, n_planes)."""
    g = g / np.linalg.norm(g)
    centers, areas = [], []
    prev = None
    for t in np.arange(t_range[0], t_range[1] + 1e-9, step):
        o = tip - g * t
        loops = plane_loops(P, F, o, g, e1, e2)
        best = None
        for L in loops:
            A, c = poly_area_centroid(L)
            if A < 4e-5:
                continue
            ref = np.zeros(2) if prev is None else prev
            dist = np.linalg.norm(c - ref)
            if best is None or dist < best[0]:
                best = (dist, A, c, o)
        if best is None:
            break
        dist, A, c, o = best
        if prev is None and dist > 0.012:      # the loop nearest the tip axis must really be the tip's finger
            break
        if A > area_max or (prev is not None and dist > jump):
            break
        if areas and A > 1.7 * np.median(areas):
            break
        prev = c
        areas.append(A)
        centers.append(o + c[0] * e1 + c[1] * e2)
        # keep the 2D reference consistent as the plane origin moves along g: express in the same (e1,e2) basis relative
        # to the *new* origin (centre of the next plane lies on the previous centre line)
        prev = np.zeros(2) if len(centers) < 2 else None
        if len(centers) >= 2:
            # predict next centre by linear extrapolation, expressed relative to the next origin
            dirv = centers[-1] - centers[-2]
            nxt = centers[-1] + dirv
            o_next = tip - g * (t + step)
            q = nxt - o_next
            prev = np.array([q @ e1, q @ e2])
        else:
            q = centers[-1] - (tip - g * (t + step))
            prev = np.array([q @ e1, q @ e2])
    if len(centers) < 3:
        return tip - g * 0.02, g, 0.009, len(centers)
    C = np.array(centers)
    c0 = C.mean(0)
    _, _, vt = np.linalg.svd(C - c0)
    dd = vt[0]
    if dd @ g < 0:
        dd = -dd
    r = float(np.sqrt(np.median(areas) / np.pi))
    return c0, dd, r, len(centers)


def complete_fingers(P, W, a, u, n, finger_tip_pts, thumb_pt, dist, n_fingers=4):
    """If fewer than n_fingers tips were found (fused fingers), divide the width of the fingertip rim into equal parts
    and create the missing tips there. Returns list of tip points sorted index -> pinky."""
    w = np.cross(n, a)
    w /= np.linalg.norm(w)
    s_all = (P - W) @ a
    pts = sorted([np.asarray(p) for p in finger_tip_pts], key=lambda p: -(p - W) @ u)
    if len(pts) >= n_fingers:
        return pts[:n_fingers], False
    s_tip = max((p - W) @ a for p in pts)
    rim = (s_all > s_tip - 0.028) & (s_all < s_tip + 0.005)
    # exclude anything that belongs to the thumb
    rim &= np.linalg.norm(P - thumb_pt, axis=1) > 0.045
    q = (P - W) @ u
    qmin, qmax = np.percentile(q[rim], 1), np.percentile(q[rim], 99)
    S = (qmax - qmin) / n_fingers
    centers = [qmax - (k + 0.5) * S for k in range(n_fingers)]     # index (thumb side) first
    out = []
    used = set()
    for k, qc in enumerate(centers):
        # existing tip close to this centre?
        best = None
        for i, p in enumerate(pts):
            if i in used:
                continue
            dq = abs((p - W) @ u - qc)
            if dq < 0.6 * S and (best is None or dq < best[0]):
                best = (dq, i)
        if best is not None:
            used.add(best[1])
            out.append(pts[best[1]])
        else:
            sel = rim & (np.abs(q - qc) < 0.35 * S)
            idx = np.where(sel)[0]
            j = idx[np.argmax(s_all[idx])]
            out.append(P[j].copy())
    return out, True


def guided_digits(P, side, guide, n_fingers=4):
    """Hand frame and fingertips for hands whose fingers are fused / pressed together (tip detection by geodesic maxima fails).
    guide: dict(axis=hand axis hint (wrist -> fingers), thumb_dir=lateral direction pointing to the thumb side, thumb_tip=optional point).
    The wrist centre is the centroid of the proximal ring of the hand mask; the fingers are found from the lateral profile of the
    distal extent: the profile run that reaches > 55 % of the longest finger (thumb excluded) is divided into four equal windows
    (index = thumb side .. pinky) and the farthest point in each window is its tip.
    Returns W, a, u, n, thumb_index, [4 tip points index..pinky]."""
    a0 = np.asarray(guide["axis"], float); a0 /= np.linalg.norm(a0)
    u0 = np.asarray(guide["thumb_dir"], float); u0 -= (u0 @ a0) * a0; u0 /= np.linalg.norm(u0)
    s0 = P @ a0
    ring = s0 < np.percentile(s0, 1.0) + 0.008
    W = P[ring].mean(0)
    s = (P - W) @ a0
    q = (P - W) @ u0
    # thumb tip: given, else the most lateral point on the thumb side among the farthest 60 % of the hand
    if "thumb_tip" in guide:
        thumb = int(np.argmin(np.linalg.norm(P - np.asarray(guide["thumb_tip"], float), axis=1)))
    else:
        far = s > 0.35 * s.max()
        idx = np.where(far)[0]
        thumb = int(idx[np.argmax(q[idx])])
    T = P[thumb]
    not_thumb = np.linalg.norm(P - T, axis=1) > 0.04
    bins = np.floor(q / 0.002).astype(int)
    prof = {}
    for b_, ss, ok in zip(bins, s, not_thumb):
        if ok and ss > prof.get(b_, -1e9):
            prof[b_] = ss
    bk = np.array(sorted(prof))
    pv = np.array([prof[b_] for b_ in bk])
    smax = pv.max()
    valid = pv > 0.55 * smax
    # largest contiguous run of valid bins (gaps of up to 2 bins allowed)
    best, cur = (0, 0, -1), None
    for i in range(len(bk)):
        if valid[i]:
            if cur is None or bk[i] - bk[cur[1]] > 3:
                cur = [i, i]
            else:
                cur[1] = i
            if cur[1] - cur[0] > best[0]:
                best = (cur[1] - cur[0], cur[0], cur[1])
    qlo, qhi = bk[best[1]] * 0.002, (bk[best[2]] + 1) * 0.002
    S = (qhi - qlo) / n_fingers
    tips = []
    for k in range(n_fingers):
        qc = qhi - (k + 0.5) * S
        sel = np.where(not_thumb & (np.abs(q - qc) < 0.35 * S) & (s > 0.5 * smax))[0]
        tips.append(P[sel[np.argmax(s[sel])]].copy())
    fc = np.mean(tips, 0)
    a = fc - W; a /= np.linalg.norm(a)
    u = T - fc; u -= (u @ a) * a; u /= np.linalg.norm(u)
    n = np.cross(a, u) if side == "L" else np.cross(u, a)
    n /= np.linalg.norm(n)
    return W, a, u, n, thumb, tips


def analyze_hand(co, faces, mask, adj, side, thumb_hint=None, finger_tips=None, guide=None):
    """Full digit analysis. finger_tips (optional): dict name->xyz overriding detected tips. guide: see guided_digits."""
    used, f, P, G, bidx, dist = geodesic_field(co, faces, mask, adj)
    f_tri = f
    if guide is not None:
        W, a, u, n, thumb, ft = guided_digits(P, side, guide)
        tips = np.array([thumb], int)
        synthesized = False
    else:
        tips = find_tips(P, dist)
        W, a, u, n, thumb, others = hand_frame_from_tips(P, bidx, tips, dist, side)
        # sort finger tips: index (closest to thumb side) .. pinky; synthesize missing ones for fused hands
        ft, synthesized = complete_fingers(P, W, a, u, n, [P[t] for t in others], P[thumb], dist)
    names = FINGER_NAMES[: len(ft)]
    tipmap = dict(zip(names, ft))
    if finger_tips:
        tipmap.update({k: np.asarray(v, float) for k, v in finger_tips.items()})
    w = np.cross(n, a)
    w /= np.linalg.norm(w)
    mid_tip = tipmap.get("middle", list(tipmap.values())[0])
    Lh = float(np.linalg.norm(mid_tip - W))
    digits = {}
    xs = sorted(tipmap.items(), key=lambda kv: -(kv[1] - W) @ u)
    spacing = np.median([abs((xs[i][1] - xs[i + 1][1]) @ u) for i in range(len(xs) - 1)]) if len(xs) > 1 else 0.02
    for name, T in tipmap.items():
        e1 = w
        e2 = n
        c0, d, r, nu = fit_axis(P, f_tri, T, a, e1, e2)
        fused = nu < 4            # cross-sections merge right behind the tip -> fingers are fused / pressed together
        if fused:
            # fall back to a line through the tip parallel to the hand axis
            c0, d, r = T - a * 0.03, a.copy(), 0.009
        # centre line = line through c0 with direction d; the tip joint sits where the line leaves the surface
        Tc = c0 + d * ((T - c0) @ d)
        Lf = FINGER_LEN[name] * Lh
        MCP = Tc - d * Lf
        j = [MCP + (Tc - MCP) * t for t in FINGER_SPLIT]
        digits[name] = dict(tip=Tc, tip_surface=T, dir=d, radius=r, joints=np.array(j), n_used=nu, fused=fused)
    # thumb
    T = P[thumb]
    tg = (T - W)
    tg /= np.linalg.norm(tg)
    e1t = np.cross(tg, n); e1t /= np.linalg.norm(e1t); e2t = np.cross(tg, e1t)
    c0, d, r, nu = fit_axis(P, f_tri, T, tg, e1t, e2t, t_range=(0.006, 0.040), area_max=1.4e-3)
    th = dict(tip=c0 + d * ((T - c0) @ d), tip_surface=T, dir=d, radius=r, n_used=nu)
    out = dict(synthesized=synthesized, P=P, used=used, W=W, a=a, u=u, n=n, w=w, Lh=Lh, digits=digits, thumb=th, spacing=spacing, dist=dist, tips=tips, bidx=bidx)
    return out
