"""Find the faces of the glasses (frame, lenses, temples) on a single-mesh head and the skin faces around them.
The glasses stand out of the head: in a cylindrical depth map around the head axis (angle x height cells) every vertex that sits more than
`strong_mm` in front of the deepest surface of its cell is glasses; weak candidates (> weak_mm) are added when they touch strong ones.
blender -b --factory-startup --python glasses_select.py -- <tag> [arrays_npz]
Settings: tools/configs/<tag>.json ["glasses"] = {"axis_xy": [x, y], "z_range_mm": [lo, hi], "strong_mm": 2.0, "weak_mm": 0.6, "theta_deg": 100,
                                                  "min_comp": 30, "dilate": 1, "nose_exclude": {"x_half_mm": 15, "z_below_mm": 1556}}
Writes <WORK>/<tag>_glasses_faces.npz: glasses (bool per face, loose), core (clearly protruding faces), skin_roi (skin faces around the glasses), vert, foff (mean protrusion per face)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def select_glasses(co, F, cfg):
    cx, y0 = cfg["axis_xy"]
    zlo, zhi = [v / 1000.0 for v in cfg["z_range_mm"]]
    band = (co[:, 2] > zlo) & (co[:, 2] < zhi)
    rel = co - np.array([cx, y0, 0.0])
    theta = np.degrees(np.arctan2(rel[:, 0], -rel[:, 1]))
    r = np.hypot(rel[:, 0], rel[:, 1])
    front = band & (np.abs(theta) < cfg.get("theta_deg", 100)) & (co[:, 1] < y0 + 0.03)
    tb = np.floor((theta + 180) / 1.5).astype(np.int64)
    zb = np.floor((co[:, 2] - zlo) / 0.002).astype(np.int64)
    key = tb * 1000 + zb
    idx = np.where(front)[0]
    r_skin = {}
    for i in idx[np.argsort(r[idx])]:
        r_skin.setdefault(key[i], r[i])
    off = np.zeros(len(co))
    off[idx] = r[idx] - np.array([r_skin[key[i]] for i in idx])
    n = len(co)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    strong = front & (off > cfg.get("strong_mm", 2.0) / 1000)
    weak = front & (off > cfg.get("weak_mm", 0.6) / 1000)
    ok = strong[E[:, 0]] & strong[E[:, 1]]
    g = coo_matrix((np.ones(ok.sum()), (E[ok, 0], E[ok, 1])), shape=(n, n))
    nc, lab = connected_components(g, directed=False)
    cnt = np.bincount(lab[strong], minlength=nc)
    sel = strong & (cnt[lab] > cfg.get("min_comp", 30))
    ne = cfg.get("nose_exclude")                      # the nose bridge also stands out of the cylinder: keep it out of the glasses
    if ne:
        nose = (np.abs(co[:, 0] - cx) < ne["x_half_mm"] / 1000) & (co[:, 2] < ne["z_below_mm"] / 1000)
        sel &= ~nose
        weak = weak & ~nose
        front = front & ~nose
    core = sel.copy()                                       # frame body, lenses, temples: clearly protruding, grown a little over the thin temple arms
    cand = front & (off > cfg.get("core_mm", 1.0) / 1000)
    if ne:
        cand &= ~nose
    for _ in range(cfg.get("core_grow", 0)):
        grow = np.zeros(n, bool)
        grow[E[:, 0][core[E[:, 1]]]] = True
        grow[E[:, 1][core[E[:, 0]]]] = True
        core |= grow & cand
    for _ in range(12):                                     # hysteresis: weak vertices attached to strong ones
        grow = np.zeros(n, bool)
        grow[E[:, 0][sel[E[:, 1]]]] = True
        grow[E[:, 1][sel[E[:, 0]]]] = True
        new = grow & weak & ~sel
        if not new.any():
            break
        sel |= new
    for _ in range(cfg.get("dilate", 1)):
        grow = np.zeros(n, bool)
        grow[E[:, 0][sel[E[:, 1]]]] = True
        grow[E[:, 1][sel[E[:, 0]]]] = True
        sel |= grow & front
    return sel, off, core


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:]
    tag = a[0]
    src = a[1] if len(a) > 1 else f"{WORK}/{tag}_arrays.npz"
    cfg = load_config(tag)["glasses"]
    d = np.load(src)
    co, F = d["co"].astype(np.float64), d["faces"]
    sel, off, core = select_glasses(co, F, cfg)
    fg = sel[F].all(1)
    fcore = core[F].all(1)
    # skin faces around: any face within `roi_mm` of a glasses vertex that is not glasses itself
    from scipy.spatial import cKDTree
    tree = cKDTree(co[sel])
    cen = co[F].mean(1)
    dist, _ = tree.query(cen)
    roi = (dist < cfg.get("roi_mm", 12.0) / 1000) & ~fg
    log(tag, "glasses vertices", int(sel.sum()), "glasses faces", int(fg.sum()), "core faces", int(fcore.sum()), "skin faces in the region of interest", int(roi.sum()))
    foff = off[F].mean(1)                                   # mean protrusion (m) of every face: separates thin temple arms from skin
    np.savez(f"{WORK}/{tag}_glasses_faces.npz", glasses=fg, core=fcore, skin_roi=roi, vert=sel, foff=foff)
    P = co[sel]
    log(tag, "glasses bbox mm", (P.min(0) * 1000).round(0), (P.max(0) * 1000).round(0))
