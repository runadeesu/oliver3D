"""Measure the lip crease curve from face geometry (depth valley) and plot the vertical profile.
blender -b --factory-startup --python mouth_measure.py -- <tag> <cx> <cz>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw
a = sys.argv[sys.argv.index("--") + 1:]
tag, cx, cz = a[0], float(a[1]), float(a[2])
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F = d["co"], d["faces"]
# head region only (keeps BVH small)
near = (np.abs(co[:, 0] - cx) < 0.12) & (co[:, 2] > cz - 0.12) & (co[:, 2] < cz + 0.12) & (co[:, 1] < 0.0)
fm = near[F].all(1)
bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in co], [tuple(map(int, f)) for f in F[fm]], epsilon=0.0)

def depth(x, z):
    h = bvh.ray_cast(Vector((x, -0.5, z)), Vector((0, 1, 0)))
    return h[0].y if h[0] is not None else np.nan

zs = np.arange(cz - 0.020, cz + 0.020, 0.00025)
xs = np.arange(cx - 0.040, cx + 0.040 + 1e-9, 0.002)
Y = np.array([[depth(x, z) for z in zs] for x in xs])     # (nx, nz)
# smooth along z (moving average 1.5 mm) and find valley = local max of y (most recessed) near cz
k = 6
ker = np.ones(k) / k
res = []
for i, x in enumerate(xs):
    y = Y[i]
    ok = ~np.isnan(y)
    if ok.sum() < len(y) * 0.9:
        res.append(np.nan); continue
    ys = np.convolve(y, ker, mode="same")
    # second derivative (concavity): valley -> y has a local maximum with large negative curvature
    d2 = np.gradient(np.gradient(ys, zs), zs)
    win = (zs > cz - 0.0045) & (zs < cz + 0.0045)
    cand = np.where(win & (d2 < 0))[0]
    if len(cand) == 0:
        res.append(np.nan); continue
    j = cand[np.argmin(d2[cand])]
    res.append(zs[j])
res = np.array(res)
good = ~np.isnan(res)
print(tag, "valley found at", good.sum(), "/", len(xs), "columns")
xm = xs[good] * 1000; zm = res[good] * 1000
p = np.polyfit(xm, zm, 2)
for _ in range(3):
    r = zm - np.polyval(p, xm)
    m = np.abs(r) < max(0.5, 2 * r.std())
    p = np.polyfit(xm[m], zm[m], 2)
print(tag, "fit z(x) = %.5f x^2 + %.4f x + %.3f (mm); centre z %.2f at x=%.1f; inliers %d" % (p[0], p[1], p[2], np.polyval(p, cx * 1000), cx * 1000, m.sum()))
print("  per-column valley z (mm):", " ".join(f"{x:.0f}:{z:.1f}" for x, z in zip(xm, zm)))
# profile at the centre column and plot
ic = int(np.argmin(np.abs(xs - cx)))
prof = Y[ic] * 1000
im = Image.new("RGB", (900, 420), (255, 255, 255)); dr = ImageDraw.Draw(im)
y0, y1 = np.nanmin(prof), np.nanmax(prof)
for j in range(len(zs) - 1):
    xa = 20 + (zs[j] - zs[0]) / (zs[-1] - zs[0]) * 860; xb = 20 + (zs[j + 1] - zs[0]) / (zs[-1] - zs[0]) * 860
    ya = 20 + (prof[j] - y0) / (y1 - y0 + 1e-9) * 380; yb = 20 + (prof[j + 1] - y0) / (y1 - y0 + 1e-9) * 380
    dr.line([(xa, ya), (xb, yb)], fill=(0, 0, 0), width=2)
zc = np.polyval(p, cx * 1000) / 1000
xv = 20 + (zc - zs[0]) / (zs[-1] - zs[0]) * 860
dr.line([(xv, 0), (xv, 420)], fill=(255, 0, 0))
dr.text((5, 5), f"{tag}: profile y(z) at x={cx*1000:.0f}mm, z {zs[0]*1000:.0f}..{zs[-1]*1000:.0f}mm (down=recessed); red = detected valley z={zc*1000:.2f}", fill=(0, 0, 0))
im.save(f"{WORK}/dbg/{tag}_profile.png")

# save a smoothed curve (quartic fit over inliers) for the config
p4 = np.polyfit(xm[m], zm[m], 4)
import json
curve = {"cx": cx, "poly4_mm": p4.tolist(), "fit_range_mm": [float(xm[m].min()), float(xm[m].max())]}
json.dump(curve, open(f"{WORK}/{tag}_mouth_curve.json", "w"))
print(tag, "quartic z(x) coeffs (mm, x in mm):", np.round(p4, 7).tolist())
