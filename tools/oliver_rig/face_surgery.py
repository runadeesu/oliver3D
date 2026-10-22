"""Face geometry surgery on <WORK>/<tag>_arrays.npz (run BEFORE build_hands.py):
  1. landmark-driven warp of the face (thin-plate spline in the front plane, lips / nose anchored) towards the reference photo
  2. remove broken glasses geometry (detected as everything standing >2.5 mm in front of the head surface in a cylindrical depth map)
     and close the holes
  3. build a clean pair of glasses (lens discs, wire rims, bridge, nose pads, temples) at the lens positions seen in the photo
blender -b --factory-startup --python face_surgery.py -- <tag> <model_landmarks.json> <front_render.png.json> <photo_landmarks_x3.json>
Settings: tools/configs/<tag>.json ["surgery"]. The original arrays are kept as <tag>_arrays_orig.npz.
New faces get material index 4 (frame) / 5 (lens); everything else is unchanged."""
import sys, os, json, math, shutil
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

MAT_FRAME, MAT_LENS = 4, 5
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
NOSE = [1, 2, 3, 4, 5, 6, 19, 44, 45, 51, 94, 97, 98, 99, 125, 134, 141, 168, 195, 197, 220, 236, 237, 238, 239, 240, 241, 242, 274, 275, 281, 326, 327, 328, 354, 363, 370, 456, 457, 458, 459, 460, 461, 462, 20, 79, 166, 218, 219, 235, 250, 309, 392, 438, 439, 455]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
CENT = [1, 2, 4, 5, 6, 195, 197, 61, 291, 13, 14, 0, 17, 33, 133, 362, 263, 168]


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def points_in_polygon(P, poly):
    """Even-odd ray casting; P (N,2), poly (K,2)."""
    x, y = P[:, 0], P[:, 1]
    inside = np.zeros(len(P), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = poly[i, 0], poly[i, 1], poly[j, 0], poly[j, 1]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        inside ^= cond
        j = i
    return inside


def fit_similarity(A, B):
    ma, mb = A.mean(0), B.mean(0)
    A0, B0 = A - ma, B - mb
    U, S, Vt = np.linalg.svd(A0.T @ B0)
    R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = (U @ Vt).T
    s = S.sum() / (A0 ** 2).sum()
    return s, R, mb - s * (R @ ma)


def tps_fit(X, Y, lam):
    n = len(X)
    d2 = ((X[:, None] - X[None]) ** 2).sum(-1)
    K = 0.5 * d2 * np.log(d2 + 1e-9) + lam * np.eye(n)
    P = np.hstack([np.ones((n, 1)), X])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, P, P.T
    rhs = np.zeros((n + 3, Y.shape[1]))
    rhs[:n] = Y
    return np.linalg.solve(A, rhs)


def tps_eval(X, coef, Q):
    n = len(X)
    d2 = ((Q[:, None] - X[None]) ** 2).sum(-1)
    return (0.5 * d2 * np.log(d2 + 1e-9)) @ coef[:n] + coef[n] + Q @ coef[n + 1:]


def model_landmarks_mm(path, cam):
    P = np.array(json.load(open(path)))[:, :2]
    res, scale = cam["res"], cam["scale"]
    x = (cam["cx"] + (P[:, 0] + 0.5 - res / 2) / res * scale) * 1000
    z = (cam["cz"] - (P[:, 1] + 0.5 - res / 2) / res * scale) * 1000
    return np.stack([x, z], 1)


# ----------------------------------------------------------------------------------------------------------------------
def warp_face(co, M, Qm, cfg):
    """co (N,3) metres; M model landmarks (mm, x/z); Qm photo landmarks mapped into model mm. Returns displaced co."""
    strength = cfg.get("strength", 1.0)
    clip = cfg.get("max_mm", 10.0)
    d = (Qm - M) * strength
    anchor = set(LIPS) | set(NOSE) | set(cfg.get("anchor_extra", []))
    for i in anchor:
        d[i] = 0.0
    n = np.linalg.norm(d, axis=1)
    d *= np.minimum(1.0, clip / np.maximum(n, 1e-6))[:, None]
    # far anchors (zero displacement) on a ring around the face and on the forehead / neck
    c = M[CENT].mean(0)
    rx, rz = cfg.get("ring_mm", [135.0, 185.0])
    ang = np.linspace(0, 2 * np.pi, 28, endpoint=False)
    ring = np.stack([c[0] + rx * np.cos(ang), c[1] + 25 + rz * np.sin(ang)], 1)
    X = np.vstack([M, ring])
    D = np.vstack([d, np.zeros((len(ring), 2))])
    coef = tps_fit(X, D, cfg.get("lambda", 150.0))
    P = co[:, [0, 2]] * 1000
    # region weights: inside the oval polygon 1, fading outwards; depth: only the front surface
    poly = M[FACE_OVAL]
    inside = points_in_polygon(P, poly)
    from scipy.spatial import cKDTree as KD
    tree = KD(poly)
    dist, _ = tree.query(P)
    w_xz = np.where(inside, 1.0, 1 - smoothstep(0.0, cfg.get("fade_mm", 22.0), dist))
    cell = (np.floor(P / 3.0)).astype(np.int64)
    key = cell[:, 0] * 100000 + cell[:, 1]
    ymin = {}
    for k, y in sorted(zip(key, co[:, 1]), key=lambda t: t[1], reverse=True):
        ymin[k] = y
    yf = np.array([ymin[k] for k in key])
    w_dep = 1 - smoothstep(0.03, 0.09, co[:, 1] - yf)
    w = w_xz * w_dep * (co[:, 1] < 0.0)
    sel = w > 1e-3
    disp = np.zeros((len(co), 2))
    disp[sel] = tps_eval(X, coef, P[sel]) * w[sel, None]
    out = co.copy()
    out[:, 0] += disp[:, 0] / 1000
    out[:, 2] += disp[:, 1] / 1000
    print("warp: max displacement %.1f mm, vertices moved >0.5mm: %d" % (np.abs(disp).max(), (np.abs(disp).max(1) > 0.5).sum()))
    return out


# ----------------------------------------------------------------------------------------------------------------------
def select_glasses(co, F, zc, cx, cfg):
    y0 = cfg.get("axis_y", -0.055)
    band_lo, band_hi = cfg.get("band_mm", [25.0, 95.0])
    band = (co[:, 2] > zc + band_lo / 1000) & (co[:, 2] < zc + band_hi / 1000)
    rel = co - np.array([cx, y0, 0])
    theta = np.degrees(np.arctan2(rel[:, 0], -rel[:, 1]))
    r = np.hypot(rel[:, 0], rel[:, 1])
    front = band & (np.abs(theta) < cfg.get("theta_deg", 80)) & (co[:, 1] < y0 + 0.02)
    tb = np.floor((theta + 90) / 1.5).astype(np.int64)
    zb = np.floor((co[:, 2] - zc) / 0.002).astype(np.int64)
    key = tb * 1000 + zb
    idx = np.where(front)[0]
    r_skin = {}
    for i in idx[np.argsort(r[idx])]:
        r_skin.setdefault(key[i], r[i])
    off = np.zeros(len(co))
    off[idx] = r[idx] - np.array([r_skin[key[i]] for i in idx])
    n = len(co)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    strong = front & (off > cfg.get("strong_mm", 2.5) / 1000)
    weak = front & (off > cfg.get("weak_mm", 0.8) / 1000)
    ok = strong[E[:, 0]] & strong[E[:, 1]]
    g = coo_matrix((np.ones(ok.sum()), (E[ok, 0], E[ok, 1])), shape=(n, n))
    nc, lab = connected_components(g, directed=False)
    cnt = np.bincount(lab[strong], minlength=nc)
    keep = strong & (cnt[lab] > cfg.get("min_comp", 30))
    # hysteresis: weak vertices connected to the kept set
    sel = keep.copy()
    for _ in range(12):
        grow = np.zeros(n, bool)
        grow[E[:, 0][sel[E[:, 1]]]] = True
        grow[E[:, 1][sel[E[:, 0]]]] = True
        new = grow & weak & ~sel
        if not new.any():
            break
        sel |= new
    # dilate (attachment fringes)
    for _ in range(cfg.get("dilate", 2)):
        grow = np.zeros(n, bool)
        grow[E[:, 0][sel[E[:, 1]]]] = True
        grow[E[:, 1][sel[E[:, 0]]]] = True
        sel |= grow & front
    print("glasses: selected %d vertices (strong %d)" % (sel.sum(), keep.sum()))
    return sel, r_skin, (theta, r, key)


BOX_SCALE = 0.85


def fill_holes(co, F, uv, mat, vc, sel, region_box, patch_uv=None):
    """Remove faces touching `sel`, close the resulting holes inside region_box with smooth patches. Returns new arrays."""
    keep_f = ~sel[F].any(1)
    F2, uv2, mat2 = F[keep_f], uv[keep_f], mat[keep_f]
    # boundary edges of the remaining mesh that lie inside the region
    E = np.concatenate([F2[:, [0, 1]], F2[:, [1, 2]], F2[:, [2, 0]]])
    Es = np.sort(E, 1)
    key = Es[:, 0].astype(np.int64) * len(co) + Es[:, 1]
    uq, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    bnd = cnt[inv] == 1
    be = E[bnd]
    lo, hi = region_box
    inbox = ((co[be[:, 0]] >= lo) & (co[be[:, 0]] <= hi)).all(1) & ((co[be[:, 1]] >= lo) & (co[be[:, 1]] <= hi)).all(1)
    be = be[inbox]
    # chain boundary edges into loops (directed as they appear in the faces)
    nxt = {}
    for a, b in be:
        nxt.setdefault(int(a), []).append(int(b))
    loops, seen = [], set()
    for a in list(nxt):
        if a in seen:
            continue
        loop, cur = [a], a
        seen.add(a)
        while True:
            ns = [x for x in nxt.get(cur, []) if x not in seen or x == a]
            if not ns:
                break
            cur = ns[0]
            if cur == a:
                break
            loop.append(cur)
            seen.add(cur)
        if len(loop) >= 4:
            loops.append(loop)
    print("hole loops to fill:", len(loops), "sizes", [len(l) for l in loops][:12])
    # corner uv per vertex of the remaining mesh (first corner)
    cuv = {}
    for fi in range(len(F2)):
        for k in range(3):
            cuv.setdefault(int(F2[fi, k]), uv2[fi, k])
    newco = [co]
    newF = []
    patch_info = []
    vuv = dict(cuv)
    nv = len(co)
    newvc = [vc]
    for loop in loops:
        ring = co[loop]
        c = ring.mean(0)
        bu = np.array([cuv.get(int(v), (0.0, 0.0)) for v in loop])
        # keep the patch inside ONE uv chart: the patch uses the uv of the boundary vertex nearest to the loop centre for all inner vertices,
        # boundary corners keep their own uv only when they are close to it (otherwise they belong to another chart)
        j0 = int(np.argmin(np.linalg.norm(ring - c, axis=1)))
        ref = bu[j0].copy()
        far = np.linalg.norm(bu - ref, axis=1) > 0.02
        bu = bu.copy()
        bu[far] = ref
        if patch_uv == "local":                        # flat colour: every corner of the patch samples the skin texel just outside the hole
            dist_c = np.linalg.norm(co - c, axis=1)
            cand = np.where((dist_c > 0.008) & (dist_c < 0.022) & ~sel & (np.abs(co[:, 1] - c[1]) < 0.02))[0]
            cand = cand[np.isin(cand, np.unique(F2))]
            if len(cand):
                vv = cand[np.argmin(dist_c[cand])]
                fi_ = np.where((F2 == vv).any(1))[0][0]
                ref = uv2[fi_, int(np.where(F2[fi_] == vv)[0][0])].copy()
                bu[:] = ref
        elif patch_uv is not None and patch_uv not in ("affine", "skin", "box"):
            ref = np.array(patch_uv, np.float32)
            bu[:] = ref
        for k, v in enumerate(loop):
            vuv[int(v)] = bu[k]
        rings = [np.array(loop)]
        for sc_ in (0.66, 0.33):
            pts = c + (ring - c) * sc_
            ids = np.arange(nv, nv + len(pts))
            nv += len(pts)
            newco.append(pts)
            newvc.append(np.tile(vc[loop].mean(0), (len(pts), 1)))
            tr_ = cKDTree(ring)
            _, nn = tr_.query(pts)
            for k, v in enumerate(ids):
                vuv[int(v)] = bu[nn[k]]
            rings.append(ids)
        cid = nv
        nv += 1
        newco.append(c[None])
        newvc.append(vc[loop].mean(0)[None])
        vuv[cid] = bu[int(np.argmin(np.linalg.norm(ring - c, axis=1)))]
        n = len(loop)
        patch_info.append(dict(uv=[float(ref[0]), float(ref[1])], x_mm=float(c[0] * 1000), z_mm=float(c[2] * 1000), n=n, loop=[int(v) for v in loop],
                               inner=[int(v) for r_ in rings[1:] for v in r_] + [cid], ref=[float(ref[0]), float(ref[1])]))
        # the loop runs in the direction of the surviving faces' edges -> patch faces use the opposite direction
        for ri in range(len(rings) - 1):
            A_, B_ = rings[ri], rings[ri + 1]
            for i in range(n):
                j = (i + 1) % n
                newF.append((A_[j], A_[i], B_[i])); newF.append((A_[j], B_[i], B_[j]))
        last = rings[-1]
        for i in range(n):
            newF.append((last[(i + 1) % n], last[i], cid))
    newuv = [[vuv[int(v)] for v in f] for f in newF]
    co2 = np.concatenate(newco)
    vc2 = np.concatenate(newvc)
    nF = np.array(newF, np.int64).reshape(-1, 3)
    nuv = np.array(newuv, np.float32).reshape(-1, 3, 2)
    # relax the patch interiors (keep the original vertices fixed)
    if len(nF):
        fixed = np.arange(len(co2)) < len(co)
        Ee = np.concatenate([nF[:, [0, 1]], nF[:, [1, 2]], nF[:, [2, 0]]])
        nbr = coo_matrix((np.ones(len(Ee)), (Ee[:, 0], Ee[:, 1])), shape=(len(co2), len(co2))).tocsr()
        nbr = ((nbr + nbr.T) > 0).astype(np.float64)
        deg = np.asarray(nbr.sum(1)).ravel()
        for _ in range(60):
            avg = (nbr @ co2) / np.maximum(deg, 1)[:, None]
            co2 = np.where(fixed[:, None] | (deg == 0)[:, None], co2, avg)
    if patch_uv == "box":
        dens = 4.2 / 8192.0 / 0.001 * BOX_SCALE          # uv per metre (texel density ~ the skin's, 8K atlas)
        sizes, boxes = [], []
        for pi in patch_info:
            P = co2[pi["loop"]]
            ext = max(np.ptp(P[:, 0]), np.ptp(P[:, 2])) * 1.05
            sizes.append(ext * dens)
            boxes.append((P[:, 0].min() - 0.0005, P[:, 2].min() - 0.0005))
        all_uv = np.concatenate([uv2, np.zeros((0, 3, 2))]) if len(uv2) else uv2
        slots = free_uv_squares(all_uv, sizes)
        nuv_map = {}
        pj = []
        for pi, (u0, v0), (x0, z0), sz in zip(patch_info, slots, boxes, sizes):
            for v in pi["loop"] + pi["inner"]:
                nuv_map[int(v)] = np.array([u0 + (co2[v, 0] - x0) * dens, v0 + (co2[v, 2] - z0) * dens])
            pj.append(dict(u0=u0, v0=v0, size=float(sz), x_mm=pi["x_mm"], z_mm=pi["z_mm"], ref=pi["ref"], loop_uv=[cuv.get(int(v), [0, 0]) if not hasattr(cuv.get(int(v), [0, 0]), "tolist") else cuv[int(v)].tolist() for v in pi["loop"]]))
            print("patch box uv origin (%.4f, %.4f) size %.4f (%d texels)" % (u0, v0, sz, sz * 8192))
        fill_holes.boxes = pj
        for fi_, f in enumerate(newF):
            for k, v in enumerate(f):
                nuv[fi_, k] = nuv_map[int(v)]
    if patch_uv == "affine":
        # continuous texture: uv = A (x, z, 1) fitted on the surrounding skin of the same uv chart (like the lip band of the mouth)
        pos_of = {}
        for fi_ in range(len(nF)):
            pass
        corner_pos = co2
        nuv_map = {}
        radius = 0.03
        in_skin = np.zeros(len(co), bool)
        in_skin[np.unique(F2)] = True
        for pi in patch_info:
            c_ = co2[pi["inner"][-1]]
            ref = np.array(pi["ref"])
            sel_f = np.where(((np.abs(co[F2][:, :, 0] - c_[0]) < radius) & (np.abs(co[F2][:, :, 2] - c_[2]) < radius)).all(1) & (np.abs(co[F2][:, :, 1] - c_[1]).max(1) < 0.03))[0]
            P_, U_ = [], []
            for fi_ in sel_f:
                if np.abs(uv2[fi_] - ref).max() < 0.03:
                    for k in range(3):
                        v = F2[fi_, k]
                        P_.append([co[v, 0], co[v, 2], 1.0]); U_.append(uv2[fi_, k])
            P_, U_ = np.array(P_), np.array(U_)
            if len(P_) < 30:
                print("patch uv fit: too few samples", len(P_)); continue
            sol, *_ = np.linalg.lstsq(P_, U_, rcond=None)
            res_ = np.abs(P_ @ sol - U_).max()
            print("patch uv fit: %d samples, max residual %.4f" % (len(P_), res_))
            for v in pi["inner"]:
                nuv_map[v] = np.array([co2[v, 0], co2[v, 2], 1.0]) @ sol
            for v in pi["loop"]:
                pred = np.array([co2[v, 0], co2[v, 2], 1.0]) @ sol
                own = np.array(cuv.get(int(v), pred))
                nuv_map[v] = own if np.abs(own - pred).max() < 0.004 else pred
        for fi_, f in enumerate(newF):
            for k, v in enumerate(f):
                if int(v) in nuv_map:
                    nuv[fi_, k] = nuv_map[int(v)]
    F3 = np.concatenate([F2, nF])
    uv3 = np.concatenate([uv2, nuv])
    mat3 = np.concatenate([mat2, np.zeros(len(nF), mat2.dtype)])
    fill_holes.info = patch_info
    return co2, F3, uv3, mat3, vc2


def free_uv_squares(uv_all, sizes_uv, N=2048, margin_px=6):
    """Find non-overlapping empty squares (side in uv units) in the uv atlas. uv_all (F,3,2). Returns list of (u0, v0)."""
    from PIL import Image, ImageDraw
    from scipy.ndimage import distance_transform_cdt, binary_dilation
    img = Image.new("L", (N, N), 0)
    dr = ImageDraw.Draw(img)
    pts = uv_all.reshape(-1, 3, 2) * N
    for t in pts:
        dr.polygon([(float(a), float(b)) for a, b in t], fill=255)
    occ = np.array(img) > 0
    occ = binary_dilation(occ, iterations=margin_px)
    out = [None] * len(sizes_uv)
    for idx in np.argsort(sizes_uv)[::-1]:
        need = int(math.ceil(sizes_uv[idx] * N)) + 2 * margin_px
        dist = distance_transform_cdt(~occ, metric="chessboard")           # distance to the nearest occupied cell
        ok = dist * 2 >= need
        ys, xs = np.where(ok)
        if len(ys) == 0:
            raise RuntimeError("no free uv square of size %.3f" % sizes_uv[idx])
        k = int(np.argmin(dist[ys, xs]))                                      # tightest fit
        cy, cx_ = ys[k], xs[k]
        half = need // 2
        occ[max(cy - half, 0):cy + half + 1, max(cx_ - half, 0):cx_ + half + 1] = True
        u0 = (cx_ - half + margin_px) / N
        v0 = 1.0 - (cy + half - margin_px) / N               # image row grows downwards, v upwards
        out[idx] = (float(u0), float(v0))
    return out


def compact(co, F, vc):
    used = np.unique(F)
    remap = -np.ones(len(co), np.int64)
    remap[used] = np.arange(len(used))
    return co[used], remap[F], vc[used]


# ----------------------------------------------------------------------------------------------------------------------
def tube(poly, radius, seg=8):
    """Tube mesh along a polyline (K,3) -> (verts, faces)."""
    poly = np.asarray(poly, float)
    K = len(poly)
    tang = np.gradient(poly, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
    up = np.array([0, 0, 1.0])
    V, Fc = [], []
    prev_n = None
    for k in range(K):
        t = tang[k]
        n = np.cross(t, up)
        if np.linalg.norm(n) < 1e-6:
            n = np.cross(t, np.array([1.0, 0, 0]))
        n /= np.linalg.norm(n)
        if prev_n is not None and n @ prev_n < 0:
            n = -n
        prev_n = n
        b = np.cross(t, n)
        for s in range(seg):
            a = 2 * math.pi * s / seg
            V.append(poly[k] + radius * (math.cos(a) * n + math.sin(a) * b))
    for k in range(K - 1):
        for s in range(seg):
            a, b_, c, d = k * seg + s, k * seg + (s + 1) % seg, (k + 1) * seg + (s + 1) % seg, (k + 1) * seg + s
            Fc += [(a, b_, c), (a, c, d)]
    return np.array(V), np.array(Fc)


def sphere(c, r, nu=10, nv=6):
    V, Fc = [], []
    for j in range(nv + 1):
        phi = math.pi * j / nv
        for i in range(nu):
            th = 2 * math.pi * i / nu
            V.append(c + r * np.array([math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)]))
    for j in range(nv):
        for i in range(nu):
            a, b = j * nu + i, j * nu + (i + 1) % nu
            Fc += [(a, b, b + nu), (a, b + nu, a + nu)]
    return orient_closed(np.array(V), np.array(Fc))


def orient_closed(V, F):
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    vol = np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0
    return (V, F[:, ::-1].copy()) if vol < 0 else (V, F)


def lens(c, R, thick, seg=48, rings=6, dome=0.0015):
    """Round lens disc facing -y (the camera side): front dome, flat back, rim. Closed, outward oriented."""
    def layer(y_of):
        V = [c + np.array([0.0, y_of(0.0), 0.0])]
        for j in range(1, rings + 1):
            rr = R * j / rings
            for i in range(seg):
                a = 2 * math.pi * i / seg
                V.append(c + np.array([rr * math.cos(a), y_of(rr), rr * math.sin(a)]))
        return V
    front = layer(lambda rr: -(dome * (1 - (rr / R) ** 2)) - thick / 2)
    back = layer(lambda rr: thick / 2)
    V = front + back
    off = len(front)
    Fc = []
    for base in (0, off):
        for i in range(seg):
            Fc.append((base, base + 1 + i, base + 1 + (i + 1) % seg))
        for j in range(rings - 1):
            for i in range(seg):
                a, b = base + 1 + j * seg + i, base + 1 + j * seg + (i + 1) % seg
                Fc += [(a, b, b + seg), (a, b + seg, a + seg)]
    # the back layer must face the other way
    nf = len(Fc) // 2
    Fc = Fc[:nf] + [(f[0], f[2], f[1]) for f in Fc[nf:]]
    for i in range(seg):                                                          # rim
        a, b = 1 + (rings - 1) * seg + i, 1 + (rings - 1) * seg + (i + 1) % seg
        Fc += [(a, off + a, off + b), (a, off + b, b)]
    return orient_closed(np.array(V), np.array(Fc))


def build_glasses(cx, zl, yl, sep, R, ear_y, ear_x, ear_z, y_bridge, pads, frame_r=0.00055):
    """All lengths in metres. cx: face midline x, zl: lens centre z, yl: lens plane y, sep: lens centre separation."""
    parts_frame, parts_lens = [], []
    for sgn in (-1, 1):
        c = np.array([cx + sgn * sep / 2, yl, zl])
        parts_lens.append(lens(c, R * 0.97, 0.0016))
        a = np.linspace(0, 2 * math.pi, 64, endpoint=False)
        ring = np.stack([c[0] + R * np.cos(a), np.full_like(a, yl), c[2] + R * np.sin(a)], 1)
        ring = np.vstack([ring, ring[:1]])
        parts_frame.append(tube(ring, frame_r * 1.15, 6))
        # temple: from the outer rim, straight back to the ear, slightly bent down at the end
        start = c + np.array([sgn * R, 0, 0])
        end = np.array([cx + sgn * ear_x, ear_y, ear_z])
        mid = start + (end - start) * 0.82
        tp = np.array([start + (end - start) * t for t in np.linspace(0, 0.82, 14)] +
                      [mid + (end - mid) * t + np.array([0, 0, -0.012 * t * t]) for t in np.linspace(0.12, 1.0, 5)])
        parts_frame.append(tube(tp, frame_r, 6))
        parts_frame.append(sphere(c + np.array([sgn * R, 0, 0]), 0.0011, 8, 5))
        # nose pad: small ball on a short wire from the inner rim, towards the nose
        pad = np.array([cx + sgn * pads[0], yl + pads[1], zl + pads[2]])
        wire = np.array([c + np.array([-sgn * R, 0, -0.002]) + (pad - (c + np.array([-sgn * R, 0, -0.002]))) * t for t in np.linspace(0, 1, 6)])
        parts_frame.append(tube(wire, frame_r * 0.9, 6))
        parts_frame.append(sphere(pad, 0.0022, 10, 6))
    # bridge: arc over the nose between the two inner rims
    p0 = np.array([cx - sep / 2 + R, yl, zl + 0.001])
    p1 = np.array([cx + sep / 2 - R, yl, zl + 0.001])
    t = np.linspace(0, 1, 16)
    arc = np.array([p0 * (1 - u) + p1 * u + np.array([0, y_bridge * math.sin(math.pi * u), 0.0035 * math.sin(math.pi * u)]) for u in t])
    parts_frame.append(tube(arc, frame_r * 1.1, 6))
    return parts_frame, parts_lens


def merge(parts):
    V, Fc, off = [], [], 0
    for v, f in parts:
        V.append(v); Fc.append(f + off); off += len(v)
    return np.concatenate(V), np.concatenate(Fc)


# ----------------------------------------------------------------------------------------------------------------------
def main():
    tag, mlm_path, cam_path, plm_path = sys.argv[sys.argv.index("--") + 1:][:4]
    cfg_all = load_config(tag)
    cfg = cfg_all["surgery"]
    mouth = cfg_all["mouth"]
    src = f"{WORK}/{tag}_arrays.npz"
    orig = f"{WORK}/{tag}_arrays_orig.npz"
    if not os.path.exists(orig):
        shutil.copyfile(src, orig)
    d = np.load(orig)
    co, F, uv, mat, vc = d["co"].astype(np.float64), d["faces"], d["uv"], d["mat"], d["vcol"]
    zc = np.polyval(mouth["poly4_mm"], mouth["cx_mm"]) / 1000
    cx = mouth["cx_mm"] / 1000
    cam = json.load(open(cam_path))
    M = model_landmarks_mm(mlm_path, cam)
    Qp = np.array(json.load(open(plm_path)))[:, :2].copy()
    Qp[:, 1] *= -1
    s, R, t = fit_similarity(Qp[CENT], M[CENT])
    Qm = (s * (R @ Qp.T)).T + t
    print("photo->model similarity: scale %.4f mm/px, rotation %.1f deg, central rms %.1f mm" % (s, math.degrees(math.atan2(R[1, 0], R[0, 0])), np.sqrt(((Qm[CENT] - M[CENT]) ** 2).sum(1).mean())))
    if cfg.get("warp"):
        co = warp_face(co, M, Qm, cfg["warp"])
        Mw = Qm.copy()                              # after the warp the model's landmarks sit on the photo's
    else:
        Mw = M
    g = cfg.get("glasses")
    if g:
        sel, r_skin, (theta, r, key) = select_glasses(co, F, zc, cx, g.get("select", {}))
        lo = np.array([cx - 0.14, -0.2, zc + 0.02]); hi = np.array([cx + 0.14, 0.02, zc + 0.10])
        pu = g.get("patch_mode", "affine")
        if g.get("patch_skin_mm") and pu == "skin":
            pu = None
            px_, pz_ = g["patch_skin_mm"]
            cand = np.where((np.abs(co[:, 0] - px_ / 1000) < 0.004) & (np.abs(co[:, 2] - pz_ / 1000) < 0.004) & (co[:, 1] < -0.09) & ~sel)[0]
            if len(cand):
                vsel = cand[np.argmin(co[cand, 1])]
                fi = np.where((F == vsel).any(1))[0][0]
                pu = uv[fi, int(np.where(F[fi] == vsel)[0][0])]
                print("patch uv from cheek vertex", vsel, pu)
        co, F, uv, mat, vc = fill_holes(co, F, uv, mat, vc, sel, (lo, hi), pu)
        # --- new glasses: lens centres from the photo's iris landmarks (mapped to model mm)
        iris_l, iris_r = Qm[468], Qm[473]
        sep = abs(iris_r[0] - iris_l[0]) / 1000 * g.get("sep_scale", 1.0)
        mid_x = 0.5 * (iris_l[0] + iris_r[0]) / 1000
        zl = 0.5 * (iris_l[1] + iris_r[1]) / 1000 + g.get("dz_mm", 0.0) / 1000
        R_l = g.get("lens_radius_mm", 13.0) / 1000
        # head surface y at the lens position (deepest-front skin vertex in a small window)
        rel_y = []
        for sgn in (-1, 1):
            m_ = (np.abs(co[:, 0] - (mid_x + sgn * sep / 2)) < 0.012) & (np.abs(co[:, 2] - zl) < 0.012) & (co[:, 1] < -0.04)
            rel_y.append(co[m_, 1].min() if m_.any() else -0.14)
        y_skin = float(np.mean(rel_y))
        yl = y_skin - g.get("stand_off_mm", 9.0) / 1000
        ear = g.get("ear_mm", [82.0, -72.0, 24.0])      # x offset from the midline, y, z above the lens centre
        pf, pl = build_glasses(mid_x, zl, yl, sep, R_l, ear[1] / 1000, ear[0] / 1000, zl + ear[2] / 1000, g.get("bridge_arc_mm", 5.0) / 1000,
                               tuple(x / 1000 for x in g.get("pad_mm", [7.5, 5.0, -4.0])))
        print("glasses: midline x %.1f mm, lens z %.1f mm, separation %.1f mm, lens plane y %.1f mm (skin %.1f)" % (mid_x * 1000, zl * 1000, sep * 1000, yl * 1000, y_skin * 1000))
        for parts, mid in ((pf, MAT_FRAME), (pl, MAT_LENS)):
            V, Fc = merge(parts)
            # outward orientation: faces point away from the part's centroid is not guaranteed -> fix by signed volume sampling per tube/lens is overkill; use double-sided materials
            co = np.concatenate([co, V])
            vc = np.concatenate([vc, np.tile(vc.mean(0), (len(V), 1))]).astype(np.float32)
            F = np.concatenate([F, Fc + (len(co) - len(V))])
            uv = np.concatenate([uv, np.zeros((len(Fc), 3, 2), np.float32)])
            mat = np.concatenate([mat, np.full(len(Fc), mid, mat.dtype)])
    if g and g.get("patch_mode") == "box" and getattr(fill_holes, "boxes", None):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        tex = np.array(Image.open(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png").convert("RGB"))
        H_, W_ = tex.shape[:2]
        for b_ in fill_holes.boxes:
            lu = np.array(b_["loop_uv"])
            tc = np.clip((lu[:, 0] * W_).astype(int), 0, W_ - 1); tr_ = np.clip(((1 - lu[:, 1]) * H_).astype(int), 0, H_ - 1)
            colr = np.median(tex[tr_, tc], axis=0)
            x0 = int(b_["u0"] * W_) - 2; x1 = int((b_["u0"] + b_["size"]) * W_) + 3
            y1 = int((1 - b_["v0"]) * H_) + 2; y0 = int((1 - b_["v0"] - b_["size"]) * H_) - 3
            tex[max(y0, 0):y1, max(x0, 0):x1] = colr.astype(np.uint8)
        Image.fromarray(tex).save(f"{WORK}/{tag}_tex_prefilled.png", compress_level=3)
        print("prefilled texture ->", f"{WORK}/{tag}_tex_prefilled.png")
    elif os.path.exists(f"{WORK}/{tag}_tex_prefilled.png"):
        os.remove(f"{WORK}/{tag}_tex_prefilled.png")
    if g and getattr(fill_holes, "info", None) is not None and g.get("patch_mode", "affine") in ("local", "skin"):
        json.dump([dict(uv=i["uv"], x_mm=i["x_mm"], z_mm=i["z_mm"]) for i in fill_holes.info], open(f"{WORK}/{tag}_patches.json", "w"))
    elif os.path.exists(f"{WORK}/{tag}_patches.json"):
        os.remove(f"{WORK}/{tag}_patches.json")
    co, F, vc = compact(co, F, vc)
    np.savez(src, co=co.astype(np.float32), faces=F.astype(np.int32), uv=uv.astype(np.float32), mat=mat.astype(np.int32), vcol=vc.astype(np.float32))
    print("saved", src, co.shape, F.shape)


if __name__ == "__main__":
    main()
