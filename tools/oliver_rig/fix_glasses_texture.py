"""Remove the colour bleeding between the glasses and the skin in the base-colour texture (UV space, geometry is untouched).
python3 fix_glasses_texture.py <tag> <arrays.npz> <glasses_faces.npz> <texture_in.png> <texture_out.png> [debug_dir]
Settings: tools/configs/<tag>.json ["glasses_tex"].
 1. rasterise the glasses faces (label 2) and the skin faces around them (label 1) into UV space
 2. texels of glasses faces that do not look like glasses (skin / pink mixtures) are replaced by the surrounding glasses colour,
    texels of skin faces that look like glasses (red frame, black lens, dark blue lens) are replaced by the surrounding skin colour
    (normalised-convolution filling from the good texels of the same label, a 2 px safety margin around every bad region)
 3. the changed region is extended into the atlas gutter so that bilinear filtering does not bring the old colours back
Needs numpy + opencv (OLIVER_MPLIBS) + Pillow."""
import sys, os, json
if os.environ.get("OLIVER_MPLIBS"):
    sys.path.insert(0, os.environ["OLIVER_MPLIBS"])
import numpy as np
import cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

ROOT = os.environ.get("OLIVER_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def hsv_of(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    return hsv[..., 0] * 2.0, hsv[..., 1] / 255.0, hsv[..., 2] / 255.0


def rasterize(uv, faces_mask, H, W, value, img):
    sc = 16
    for t in uv[faces_mask]:
        p = np.stack([t[:, 0] * W, (1.0 - t[:, 1]) * H], 1)
        cv2.fillConvexPoly(img, np.round(p * sc).astype(np.int32), value, lineType=cv2.LINE_8, shift=4)


def fill_from_good(img, good, bad, fallback, sigmas=(2, 4, 8, 16, 32, 64)):
    """Fill `bad` texels with the normalised Gaussian average of the good texels (growing sigma until everything is reached)."""
    out = img.astype(np.float32).copy()
    todo = bad.copy()
    g = good.astype(np.float32)
    src = img.astype(np.float32) * g[..., None]
    for s in sigmas:
        if not todo.any():
            break
        k = int(s * 3) * 2 + 1
        num = cv2.GaussianBlur(src, (k, k), s, borderType=cv2.BORDER_CONSTANT)
        den = cv2.GaussianBlur(g, (k, k), s, borderType=cv2.BORDER_CONSTANT)
        ok = todo & (den > 0.02)
        out[ok] = num[ok] / den[ok, None]
        todo &= ~ok
    if todo.any():
        out[todo] = fallback
    return out


def classes(rgb, cfg):
    h, s, v = hsv_of(rgb)
    red = ((h <= cfg.get("red_hue_max", 14.0)) | (h >= 340.0)) & (s >= cfg.get("red_sat_min", 0.55)) & (v >= 0.28)
    dark = (v < cfg.get("dark_v_max", 0.18)) & (s < 0.85)
    navy = (h >= 170.0) & (h <= 270.0) & (v < cfg.get("navy_v_max", 0.42)) & (s > 0.15)      # dark blue lens colour
    skin = (h >= 5.0) & (h <= 42.0) & (s >= 0.10) & (s <= 0.62) & (v >= 0.42) & ~red
    hair = (h >= 5.0) & (h <= 50.0) & (s >= 0.12) & (s <= 0.80) & (v >= 0.09) & (v < 0.55) & ~skin      # hair, brows, beard: never touched
    return red, dark, navy, skin, hair


def main():
    a = sys.argv[1:]
    tag, arr_path, gf_path, tex_in, tex_out = a[:5]
    dbg = a[5] if len(a) > 5 else None
    cfg = json.load(open(f"{ROOT}/tools/configs/{tag}.json"))["glasses_tex"]
    d = np.load(arr_path)
    uv, F, co = d["uv"], d["faces"], d["co"].astype(np.float64)
    gf = np.load(gf_path)
    tex = np.array(Image.open(tex_in).convert("RGB"))
    H, W = tex.shape[:2]
    label = np.zeros((H, W), np.uint8)
    # labels: 1 skin faces around the glasses, 4 transition ring (loose glasses faces that are not clearly protruding), 2 glasses core, 3 lens (cowboy)
    rasterize(uv, gf["skin_roi"], H, W, 1, label)
    glass = gf["glasses"].copy()
    core = gf["core"].copy()
    rasterize(uv, glass & ~core, H, W, 4, label)
    rasterize(uv, core, H, W, 2, label)
    if cfg.get("lens_discs"):
        cen = co[F].mean(1) * 1000
        lens = np.zeros(len(F), bool)
        for (lx, lz, lr) in cfg["lens_discs"]:
            lens |= core & (np.hypot(cen[:, 0] - lx, cen[:, 2] - lz) < lr)
        rasterize(uv, lens, H, W, 3, label)
    red, dark, navy, skin, hair = classes(tex, cfg)
    mode = cfg["mode"]
    k5 = np.ones((3, 3), np.uint8)
    margin = int(cfg.get("margin_px", 2))
    if mode == "frame_and_lens":                       # Turbo: red frame + black lenses
        good_g = (red | dark)
        bad_g = (label == 2) & ~good_g & ~hair        # frame body: only red / black is allowed (hair that the depth test caught is left alone)
        bad_s = (label == 1) & (red | (dark & (tex.max(2) < cfg.get("lens_black_max", 28))))
        mixed = (label == 4) & ~(red | dark | skin | hair)   # transition ring: only colours that are neither class (blends) are repaired
        # thin temple arms are only partly "core": skin-coloured holes that sit inside a red area of the ring faces are paint bleed too
        dens = cv2.GaussianBlur(red.astype(np.float32), (0, 0), cfg.get("hole_sigma_px", 5.0))
        arm = np.zeros((H, W), np.uint8)               # only the temple arms (outer part of the glasses), never the nose bridge
        cen_all = co[F].mean(1) * 1000
        rasterize(uv, glass & ~core & (np.abs(cen_all[:, 0] - cfg.get("axis_x_mm", 0.0)) > cfg.get("arm_x_mm", 58.0)), H, W, 1, arm)
        bad_g |= (arm > 0) & (label == 4) & ~(red | dark | hair) & (dens > cfg.get("hole_red_density", 0.5))
    else:                                              # Cowboy: dark blue lenses (+ thin metal wire that is left alone)
        good_g = dark | navy
        bad_g = (label == 3) & ~good_g
        # lens rim / thickness faces outside the lens disc: skin-coloured holes inside a dark area are paint bleed (the thin metal wire stays)
        ddens = cv2.GaussianBlur((dark | navy).astype(np.float32) * (label > 1), (0, 0), cfg.get("hole_sigma_px", 4.0))
        bad_g |= ((label == 2) | (label == 4)) & ~(dark | navy) & (ddens > cfg.get("hole_dark_density", 0.5))
        bad_s = (label == 1) & (navy | dark & (tex.max(2) < 45))
        mixed = np.zeros((H, W), bool)
    bad_g = cv2.dilate(bad_g.astype(np.uint8), k5, iterations=margin) > 0
    bad_s = cv2.dilate(bad_s.astype(np.uint8), k5, iterations=margin) > 0
    if mode == "frame_and_lens":
        bad_g &= (label == 2) | (label == 4)
    else:
        bad_g &= (label >= 2)
    bad_s &= (label == 1)
    # ring texels: snap blends to the nearest good colour (red / dark / skin) so that no mixed colour remains
    good_any = (red | dark | skin | hair) & ((label == 4) | (label == 2) | (label == 1)) & ~bad_g & ~bad_s
    if mixed.any() and good_any.any():
        dist, lbl = cv2.distanceTransformWithLabels((~good_any).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.where(good_any)
        lut = np.zeros(lbl.max() + 1, np.int64)
        lut[lbl[ys, xs]] = ys * W + xs
        flat = tex.reshape(-1, 3)
        snapped = flat[lut[lbl]].reshape(H, W, 3)
    else:
        snapped = tex
    # the glasses fill must not be fed by skin and vice versa
    good_glass = good_g & ~bad_g & ((label == 2) | (label == 3) | (label == 4 if mode == "frame_and_lens" else False))
    good_skin = skin & ~bad_s & (label == 1)
    fb_g = np.median(tex[good_glass], axis=0) if good_glass.any() else np.array(cfg.get("fallback_glass", [150, 20, 20]), np.float32)
    fb_s = np.median(tex[good_skin], axis=0) if good_skin.any() else np.array([225, 165, 140], np.float32)
    print(tag, "texels: glasses core labelled", int(((label == 2) | (label == 3)).sum()), "bad", int(bad_g.sum()), "| skin labelled", int((label == 1).sum()), "bad", int(bad_s.sum()), "| ring mixed", int(mixed.sum()))
    print(tag, "fallback colours glass", fb_g.round(0).tolist(), "skin", fb_s.round(0).tolist())
    out = tex.astype(np.float32)
    fg = fill_from_good(tex, good_glass, bad_g, fb_g)
    out[bad_g] = fg[bad_g]
    fs = fill_from_good(tex, good_skin, bad_s, fb_s)
    out[bad_s] = fs[bad_s]
    out[mixed] = snapped[mixed]
    changed = bad_g | bad_s | mixed
    # gutter: extend the repaired colours 6 px outwards over texels that belong to no face
    nolab = (label == 0)
    cur = changed.copy()
    for _ in range(6):
        grow = cv2.dilate(cur.astype(np.uint8), k5) > 0
        ring = grow & ~cur & nolab
        if not ring.any():
            break
        num = cv2.filter2D(out * cur[..., None], -1, np.ones((3, 3), np.float32) / 9.0)
        den = cv2.filter2D(cur.astype(np.float32), -1, np.ones((3, 3), np.float32) / 9.0)
        out[ring] = num[ring] / np.maximum(den[ring, None], 1e-6)
        cur |= ring
    res = np.clip(out + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(res).save(tex_out, compress_level=3)
    print(tag, "wrote", tex_out)
    if dbg:
        os.makedirs(dbg, exist_ok=True)
        lab_rgb = np.zeros((H, W, 3), np.uint8)
        lab_rgb[label == 1] = (60, 200, 60); lab_rgb[label == 2] = (230, 60, 60); lab_rgb[label == 3] = (60, 60, 230); lab_rgb[label == 4] = (200, 120, 40)
        lab_rgb[bad_g] = (255, 255, 0); lab_rgb[bad_s] = (0, 255, 255)
        ys, xs = np.where(label > 0)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        Image.fromarray(lab_rgb[y0:y1 + 1, x0:x1 + 1]).resize(((x1 - x0 + 1) // 2, (y1 - y0 + 1) // 2)).save(f"{dbg}/{tag}_labels.png")
        before = Image.fromarray(tex[y0:y1 + 1, x0:x1 + 1]); after = Image.fromarray(res[y0:y1 + 1, x0:x1 + 1])
        before.resize((before.width // 2, before.height // 2)).save(f"{dbg}/{tag}_uv_before.png")
        after.resize((after.width // 2, after.height // 2)).save(f"{dbg}/{tag}_uv_after.png")


if __name__ == "__main__":
    main()
