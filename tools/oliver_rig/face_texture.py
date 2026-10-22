"""Correct the face texture of a model from a reference photo (texture only, geometry and UVs untouched).

python3 face_texture.py <tag> <photo> <model_landmarks.json> <photo_landmarks.json> <front_render.png> <old_texture.png> <out_texture.png> [debug_dir]

1. thin-plate-spline warp of the photo into the model's front view (478 face-mesh landmarks of the photo -> of the model render)
2. in that front-view plane: swap the low frequencies (colour / shading / facial features / beard shape) of the model's skin for the
   photo's and keep the model's fine detail where the two agree
3. bake the difference back into the UV texture for every visible, camera-facing face texel (hair, glasses, hat, clothes untouched)
Needs numpy + opencv + Pillow (env OLIVER_MPLIBS adds a pip --target dir to the path). Settings come from tools/configs/<tag>.json ["face"].
"""
import sys, os, json
if os.environ.get("OLIVER_MPLIBS"):
    sys.path.insert(0, os.environ["OLIVER_MPLIBS"])
import numpy as np
import cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

ROOT = os.environ.get("OLIVER_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
WORK = os.environ.get("OLIVER_WORK", "/tmp/oliver_work")
LIPS_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58,
             132, 93, 234, 127, 162, 21, 54, 103, 67, 109]


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def phi(r2):
    return 0.5 * r2 * np.log(r2 + 1e-9)                      # r^2 log r


def tps_fit(X, Y, lam):
    n = len(X)
    d2 = ((X[:, None] - X[None]) ** 2).sum(-1)
    K = phi(d2) + lam * np.eye(n)
    P = np.hstack([np.ones((n, 1)), X])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, P, P.T
    rhs = np.zeros((n + 3, Y.shape[1]))
    rhs[:n] = Y
    return np.linalg.solve(A, rhs)


def tps_eval(X, coef, Q):
    n = len(X)
    d2 = ((Q[:, None] - X[None]) ** 2).sum(-1)
    return phi(d2) @ coef[:n] + coef[n] + Q @ coef[n + 1:]


def gauss(img, sigma):
    k = int(sigma * 3) * 2 + 1
    return cv2.GaussianBlur(img, (k, k), sigma, borderType=cv2.BORDER_REPLICATE)


def masked_blur(img, m, sigma):
    num = gauss(img * m[..., None], sigma)
    den = gauss(m, sigma)[..., None]
    return num / np.maximum(den, 1e-4)


def colour_class(rgb, beard_zone=None, hue_max=38.0):
    """boolean mask of skin (and, inside beard_zone, brown beard) coloured pixels; rgb uint8 (H,W,3)"""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    h, s, v = hsv[..., 0] * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0
    skin = ((h <= hue_max) | (h >= 340)) & (s >= 0.08) & (s <= 0.66) & (v >= 0.36)
    if beard_zone is not None:
        skin |= beard_zone & (h >= 4) & (h <= 36) & (s >= 0.30) & (s <= 0.95) & (v >= 0.10) & (v <= 0.58)
    return skin


def main():
    a = sys.argv[1:]
    tag, photo_path, mlm_path, plm_path, front_path, tex_in, tex_out = a[:7]
    dbg = a[7] if len(a) > 7 else None
    if dbg:
        os.makedirs(dbg, exist_ok=True)
    cfg = json.load(open(f"{ROOT}/tools/configs/{tag}.json")).get("face", {})
    beard = bool(cfg.get("beard", False))
    sigma_mm = cfg.get("sigma_mm", 2.0)
    strength = cfg.get("strength", 1.0)
    lam = cfg.get("tps_lambda", 300.0)
    cam = json.load(open(front_path + ".json"))
    res, scale, cx, cz = cam["res"], cam["scale"], cam["cx"], cam["cz"]
    mm_px = scale * 1000.0 / res
    # ---- landmarks -> model plane coordinates (mm)
    M = np.array(json.load(open(mlm_path)))[:, :2]
    Mmm = np.stack([(cx + (M[:, 0] + 0.5 - res / 2) / res * scale) * 1000, (cz - (M[:, 1] + 0.5 - res / 2) / res * scale) * 1000], 1)
    Q = np.array(json.load(open(plm_path)))[:, :2]
    coef = tps_fit(Mmm, Q, lam)
    fit = tps_eval(Mmm, coef, Mmm)
    print(tag, "tps landmark residual (photo px): mean %.2f max %.2f" % (np.linalg.norm(fit - Q, axis=1).mean(), np.linalg.norm(fit - Q, axis=1).max()))
    # ---- photo in the model's front view
    step = 7
    gy, gx = np.meshgrid(np.arange(0, res + step, step), np.arange(0, res + step, step), indexing="ij")
    gxmm = (cx + (gx + 0.5 - res / 2) / res * scale) * 1000
    gzmm = (cz - (gy + 0.5 - res / 2) / res * scale) * 1000
    ph = tps_eval(Mmm, coef, np.stack([gxmm.ravel(), gzmm.ravel()], 1)).reshape(gx.shape + (2,)).astype(np.float32)
    mapx = cv2.resize(ph[..., 0], (res + step, res + step), interpolation=cv2.INTER_LINEAR)[:res, :res]
    mapy = cv2.resize(ph[..., 1], (res + step, res + step), interpolation=cv2.INTER_LINEAR)[:res, :res]
    photo = np.array(Image.open(photo_path).convert("RGB"))
    aligned = cv2.remap(photo, mapx - 0.5, mapy - 0.5, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    old = np.array(Image.open(front_path).convert("RGB"))
    # ---- face region (model oval, feathered)
    poly = np.round(M[FACE_OVAL]).astype(np.int32)
    reg = np.zeros((res, res), np.uint8)
    cv2.fillPoly(reg, [poly], 255)
    dist = cv2.distanceTransform(reg, cv2.DIST_L2, 5)
    w_region = smoothstep(cfg.get("edge_in_mm", 2.0) / mm_px, cfg.get("edge_out_mm", 7.0) / mm_px, dist)
    # forehead: the detected oval stops below the fringe -> a lifted copy of the polygon for the tone-only zone
    eye_row0 = 0.5 * (M[159, 1] + M[386, 1])
    poly_t = poly.copy()
    poly_t[poly_t[:, 1] < eye_row0, 1] -= int(40 / mm_px)
    reg_t = np.zeros((res, res), np.uint8)
    cv2.fillPoly(reg_t, [poly_t], 255)
    dist_t = cv2.distanceTransform(reg_t, cv2.DIST_L2, 5)
    w_region_t = smoothstep(cfg.get("edge_in_mm", 2.0) / mm_px, cfg.get("edge_out_mm", 7.0) / mm_px, dist_t)
    # ---- skin classes
    hue_max = cfg.get("skin_hue_max", 38.0)
    zone = None
    if beard:
        zone = np.zeros((res, res), bool)
        zone[int(M[1, 1] + cfg.get("beard_below_nose_mm", 4.0) / mm_px):, :] = True
    old_ok_b = colour_class(old, zone, hue_max)
    lips = np.zeros((res, res), np.uint8)
    cv2.fillPoly(lips, [np.round(M[LIPS_OUTER]).astype(np.int32)], 255)
    lips = cv2.dilate(lips, np.ones((3, 3), np.uint8), iterations=int(round(cfg.get("lip_margin_mm", 1.5) / mm_px))) > 0
    old_ok = old_ok_b | lips
    old_ok = cv2.erode(old_ok.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=int(round(cfg.get("erode_mm", 1.2) / mm_px))).astype(np.float32)
    ph_ok = colour_class(aligned, zone, hue_max) | lips
    bad = cv2.dilate((~ph_ok & (reg > 0)).astype(np.uint8), np.ones((3, 3), np.uint8), iterations=int(round(1.5 / mm_px)))
    x0, y0, x1, y1 = [int(v) for v in (poly[:, 0].min() - 20, poly[:, 1].min() - 20, poly[:, 0].max() + 20, poly[:, 1].max() + 20)]
    filled = aligned.copy()
    sub = cv2.inpaint(np.ascontiguousarray(aligned[y0:y1, x0:x1]), np.ascontiguousarray(bad[y0:y1, x0:x1] * 255), 9, cv2.INPAINT_TELEA)
    filled[y0:y1, x0:x1] = sub
    sig = sigma_mm / mm_px
    oldf = old.astype(np.float32)
    lab_o = cv2.cvtColor(old.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    # photo colour cast / exposure -> shift towards the model's skin statistics in Lab (keeps the photo's local shading and features)
    lam_c = cfg.get("tone_match", 0.7)
    inner = (w_region > 0.95)
    s_old = colour_class(old, None, hue_max) & inner
    s_ph = colour_class(filled, None, hue_max) & inner
    lab_p = cv2.cvtColor(filled.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    gap = lab_o[s_old].mean(0) - lab_p[s_ph].mean(0)           # model skin minus photo skin
    lab_p = lab_p + lam_c * gap
    print(tag, "skin mean Lab model/photo:", np.round(lab_o[s_old].mean(0), 1).tolist(), np.round(lab_p[s_ph].mean(0) - lam_c * gap, 1).tolist(),
          "-> final mean", np.round(lab_o[s_old].mean(0) - (1 - lam_c) * gap, 1).tolist())
    sh = cfg.get("photo_sharpen", 0.0)
    if sh:
        lab_p[..., 0] = lab_p[..., 0] + sh * (lab_p[..., 0] - gauss(lab_p[..., 0], cfg.get("sharpen_mm", 1.5) / mm_px))
    lp_old = masked_blur(lab_o, old_ok, sig)
    lp_ph = gauss(lab_p, sig)
    d = np.linalg.norm((lp_ph - lp_old) * np.array([1.0, 1.0, 1.0], np.float32), axis=2) * 2.55
    g = np.maximum(cfg.get("hp_floor", 0.2), np.exp(-(d / cfg.get("hp_tau", 45.0)) ** 2))[..., None]
    ch = cfg.get("chroma_gain", 1.0)
    gain = np.array([1.0, ch, ch], np.float32)
    new_lab = lp_old + gain * (lp_ph - lp_old) + g * (lab_o - lp_old)
    new = cv2.cvtColor(new_lab, cv2.COLOR_LAB2RGB) * 255.0
    # tone-only correction (constant Lab offset towards the photo's skin) for zones where the photo's structure is not trusted
    tone_lab = lab_o - (1 - lam_c) * gap
    tone_rgb = cv2.cvtColor(tone_lab, cv2.COLOR_LAB2RGB) * 255.0
    # structure weight: fade the photo's structure out above the eyes (hair line / fringe) -> tone only there
    eye_row = 0.5 * (M[159, 1] + M[386, 1])
    cut = eye_row - cfg.get("top_cut_mm", 12.0) / mm_px
    rows = np.arange(res, dtype=np.float32)[:, None] * np.ones((1, res), np.float32)
    w_struct = smoothstep(cut - 6.0 / mm_px, cut + 3.0 / mm_px, rows)[..., None]
    # keep the model's own texture next to non-skin parts (hair, hat, glasses): fade the correction in over a few mm
    dnon = cv2.distanceTransform((old_ok_b | lips).astype(np.uint8), cv2.DIST_L2, 5)
    e0, e1 = cfg.get("edge_fade_mm", [1.0, 6.0])
    w_edge = smoothstep(e0 / mm_px, e1 / mm_px, dnon)
    w_str = w_region * gauss(old_ok, 1.5) * strength
    w_ton = w_region_t * gauss(old_ok, 1.5) * strength
    delta = (w_struct * (new - oldf) * (w_str * w_edge)[..., None] + (1 - w_struct) * (tone_rgb - oldf) * w_ton[..., None])
    w = (w_struct * w_str[..., None] + (1 - w_struct) * w_ton[..., None])
    if dbg:
        Image.fromarray(aligned).save(f"{dbg}/{tag}_aligned.png")
        Image.fromarray(filled).save(f"{dbg}/{tag}_filled.png")
        Image.fromarray(np.clip(oldf + delta, 0, 255).astype(np.uint8)).save(f"{dbg}/{tag}_front_new.png")
        Image.fromarray((w[..., 0] * 255).astype(np.uint8)).save(f"{dbg}/{tag}_weight.png")
    # ---- model geometry in the front window
    d_ = np.load(f"{WORK}/{tag}_arrays.npz")
    co, F, uv = d_["co"].astype(np.float64), d_["faces"], d_["uv"]
    c3 = co[F]
    nrm = np.cross(c3[:, 1] - c3[:, 0], c3[:, 2] - c3[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.maximum(ln, 1e-20)[:, None]
    half = 0.5 * scale
    cen = c3.mean(1)
    win = (np.abs(cen[:, 0] - cx) < half) & (np.abs(cen[:, 2] - cz) < half) & (cen[:, 1] < 0.0) & (ln > 1e-14)
    tri = np.where(win & (nrm[:, 1] < -0.02))[0]
    # z-buffer (depth = -y, nearest wins) by painting far -> near
    def to_px(P):
        return np.stack([(P[..., 0] - cx) / scale * res + res / 2 - 0.5, (cz - P[..., 2]) / scale * res + res / 2 - 0.5], -1)
    depth = -cen[tri, 1]
    order = np.argsort(depth)
    zbuf = np.full((res, res), -1.0, np.float32)
    P2 = to_px(c3[tri])
    SH = 4
    for k in order:
        cv2.fillConvexPoly(zbuf, np.round(P2[k] * (1 << SH)).astype(np.int32), float(depth[k]), lineType=cv2.LINE_8, shift=SH)
    # ---- texel pass: rasterise the candidate triangles in UV space
    tex = np.array(Image.open(tex_in).convert("RGB"))
    H, W = tex.shape[:2]
    # restrict to triangles under the face region (+margin)
    inreg = cv2.dilate(reg, np.ones((3, 3), np.uint8), iterations=int(8 / mm_px)) > 0
    cp = np.clip(np.round(to_px(cen[tri])).astype(int), 0, res - 1)
    tri = tri[inreg[cp[:, 1], cp[:, 0]]]
    print(tag, "candidate triangles", len(tri))
    idx_l, pos_l, ny_l = [], [], []
    for k in tri:
        u = uv[k].astype(np.float64)
        t = np.stack([u[:, 0] * W, (1.0 - u[:, 1]) * H], 1)
        lo = np.floor(t.min(0)).astype(int)
        hi = np.ceil(t.max(0)).astype(int)
        jj, ii = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        pc = np.stack([jj.ravel() + 0.5, ii.ravel() + 0.5], 1)
        v0, v1, v2 = t
        den = (v1[1] - v2[1]) * (v0[0] - v2[0]) + (v2[0] - v1[0]) * (v0[1] - v2[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((v1[1] - v2[1]) * (pc[:, 0] - v2[0]) + (v2[0] - v1[0]) * (pc[:, 1] - v2[1])) / den
        l1 = ((v2[1] - v0[1]) * (pc[:, 0] - v2[0]) + (v0[0] - v2[0]) * (pc[:, 1] - v2[1])) / den
        l2 = 1 - l0 - l1
        ok = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
        if not ok.any():
            continue
        l = np.stack([l0[ok], l1[ok], l2[ok]], 1)
        idx_l.append((ii.ravel()[ok] * W + jj.ravel()[ok]).astype(np.int64))
        pos_l.append(l @ c3[k])
        ny_l.append(np.full(ok.sum(), nrm[k, 1]))
    idx = np.concatenate(idx_l)
    pos = np.concatenate(pos_l)
    ny = np.concatenate(ny_l)
    xy = to_px(pos)
    xi = np.clip(np.round(xy[:, 0]).astype(int), 0, res - 1)
    yi = np.clip(np.round(xy[:, 1]).astype(int), 0, res - 1)
    vis = np.abs((-pos[:, 1]) - zbuf[yi, xi]) < 0.0035
    w_view = smoothstep(0.01, 0.12, -ny)
    n_t = len(xy)
    rows = (n_t + 1023) // 1024
    mx = np.zeros(rows * 1024, np.float32); my = np.zeros(rows * 1024, np.float32)
    mx[:n_t], my[:n_t] = xy[:, 0], xy[:, 1]
    dl = cv2.remap(delta.astype(np.float32), mx.reshape(rows, 1024), my.reshape(rows, 1024), cv2.INTER_LINEAR,
                   borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)).reshape(-1, 3)[:n_t]
    upd = np.where(vis & (w_view > 0))[0]
    flat = tex.reshape(-1, 3)
    # a texel can be hit by several triangles: keep one correction per texel (the most camera-facing)
    ord2 = np.argsort(w_view[upd])
    upd = upd[ord2]
    tgt = idx[upd]
    corr = dl[upd] * w_view[upd, None]
    # also spread the correction into the atlas gutter (texels outside every triangle that bilinear filtering blends in)
    ty, tx = tgt // W, tgt % W
    y0t, y1t, x0t, x1t = ty.min() - 12, ty.max() + 13, tx.min() - 12, tx.max() + 13
    y0t, x0t = max(y0t, 0), max(x0t, 0)
    y1t, x1t = min(y1t, H), min(x1t, W)
    dmap = np.zeros((y1t - y0t, x1t - x0t, 3), np.float32)
    mmap = np.zeros(dmap.shape[:2], np.float32)
    dmap[ty - y0t, tx - x0t] = corr
    mmap[ty - y0t, tx - x0t] = 1.0
    covered = np.zeros(dmap.shape[:2], bool)
    covered[ty - y0t, tx - x0t] = True
    ring_total = 0
    for _ in range(int(cfg.get("gutter_px", 10))):
        k3 = np.ones((3, 3), np.float32)
        num = cv2.filter2D(dmap, -1, k3, borderType=cv2.BORDER_CONSTANT)
        den = cv2.filter2D(mmap, -1, k3, borderType=cv2.BORDER_CONSTANT)
        ring = (mmap == 0) & (den > 0)
        if not ring.any():
            break
        dmap[ring] = num[ring] / den[ring, None]
        mmap[ring] = 1.0
        ring_total += int(ring.sum())
    sel = mmap > 0
    sub = tex[y0t:y1t, x0t:x1t]
    sub[sel] = np.clip(sub[sel].astype(np.float32) + dmap[sel], 0, 255).astype(np.uint8)
    print(tag, "texels corrected:", int(covered.sum()), "+ gutter", ring_total, "of", len(np.unique(idx)), "face texels; mean |delta| %.1f" % np.abs(corr).mean())
    Image.fromarray(tex).save(tex_out, compress_level=3)
    print(tag, "wrote", tex_out)


if __name__ == "__main__":
    main()
