"""After carving: are the fingers topologically separate in the free (distal) zone? blender -b --factory-startup --python ... -- <tag>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import hands_seg, hands_digits
from scipy.sparse.csgraph import connected_components
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d0 = np.load(f"{WORK}/{tag}_arrays.npz"); co0, F0, uv0, vc0 = d0["co"], d0["faces"], d0["uv"], d0["vcol"]
adj0 = hands_seg.build_adj(F0, len(co0))
d1 = np.load(f"{WORK}/{tag}_carved.npz"); co1, F1 = d1["co"], d1["faces"]
adj1 = hands_seg.build_adj(F1, len(co1))
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m0, seed, col = hands_seg.segment_hand(co0, vc0, adj0, sgn, h["center"], h["radius"], h["shoulder"])
    res = hands_digits.analyze_hand(co0, F0, m0, adj0, side, finger_tips=cfg.get("finger_tips", {}).get(side))
    dig = res["digits"]
    # region of interest in the carved mesh: vertices near the hand (bounding sphere)
    c = np.array(h["center"]); near = np.linalg.norm(co1 - c, axis=1) < 0.2
    for label, mesh_co, adj in (("orig", co0, adj0), ("carved", co1, adj1)):
        near = np.linalg.norm(mesh_co - c, axis=1) < 0.2
        # distal zone: distance back from the nearest finger tip along its axis < 0.7 L, restricted to finger tubes
        zone = np.zeros(len(mesh_co), bool)
        lab = -np.ones(len(mesh_co), int)
        best = np.full(len(mesh_co), 1e9)
        for k, (name, dg) in enumerate(dig.items()):
            rel = mesh_co - dg["tip"]
            t = -(rel @ dg["dir"])
            lat = np.linalg.norm(rel + np.outer(t, dg["dir"]), axis=1)
            L = np.linalg.norm(dg["tip"] - dg["joints"][0])
            ok = near & (t > -0.01) & (t < 0.64 * L) & (lat < 0.013)
            upd = ok & (lat < best)
            best[upd] = lat[upd]; lab[upd] = k
        zone = lab >= 0
        sub = adj[zone][:, zone]
        nc, cl = connected_components(sub, directed=False)
        sizes = np.bincount(cl)
        big = (sizes > 150).sum()
        names_ = list(dig.keys())
        for ci in np.argsort(-sizes)[:4]:
            if sizes[ci] > 150:
                labs = np.bincount(lab[np.where(zone)[0][cl == ci]], minlength=len(names_))
                print(f"      comp size {sizes[ci]}: finger vertex counts " + ", ".join(f"{names_[k]}={labs[k]}" for k in range(len(names_))))
        print(f"[{tag} {side}] {label}: distal-zone components >150 verts: {big} (sizes {sorted(sizes.tolist(), reverse=True)[:8]}); fingers expected {len(dig)}")
