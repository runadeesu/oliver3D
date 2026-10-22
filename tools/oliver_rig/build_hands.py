"""Stage 1: separate the fingers. Reads <WORK>/<tag>_arrays.npz, writes <tag>_carved.npz + <tag>_hands.json.
blender -b --factory-startup --python build_hands.py -- <tag>"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import hands_seg, hands_digits, hands_carve

tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc, mat = d["co"], d["faces"], d["uv"], d["vcol"], d["mat"]
adj = hands_seg.build_adj(F, len(co))
t = timer()
hands_json = {}
hand_vids = {}
wall_all = None
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    res = hands_digits.analyze_hand(co, F, m, adj, side, finger_tips=cfg.get("finger_tips", {}).get(side), guide=cfg.get("hand_guide", {}).get(side))
    carved = hands_carve.carve_hand(co, F, uv, m, res, log_prefix=f"{tag}{side}")
    co, F, uv, mat, wtag, hvids = hands_carve.reintegrate(co, F, uv, mat, m, carved, prev_tag=wall_all)
    hand_vids[side] = hvids
    hmask = np.zeros(len(co), bool); hmask[hvids] = True
    hand_faces = hmask[F].all(1)                       # the colour of the new walls comes from this hand only (hands rest against jackets / jeans)
    uv = hands_carve.fix_wall_uvs(co, F, uv, wtag, hand_faces, hand_faces)
    wall_all = wtag
    vc = np.concatenate([vc, np.tile(vc.mean(0, keepdims=True), (len(co) - len(vc), 1))]).astype(np.float32)
    adj = hands_seg.build_adj(F, len(co))
    hands_json[side] = dict(
        W=res["W"].tolist(), a=res["a"].tolist(), u=res["u"].tolist(), n=res["n"].tolist(), w=res["w"].tolist(), Lh=res["Lh"],
        digits={k: dict(tip=v["tip"].tolist(), dir=v["dir"].tolist(), radius=v["radius"], joints=v["joints"].tolist(), fused=bool(v["fused"]))
                for k, v in res["digits"].items()},
        thumb=dict(tip=res["thumb"]["tip"].tolist(), dir=res["thumb"]["dir"].tolist(), radius=res["thumb"]["radius"]),
        synthesized=bool(res["synthesized"]))
    log(tag, side, "hand carved", round(t(), 1), "s")
tex_path = os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png"
if os.path.exists(tex_path):
    wall_f = wall_all == 1
    hv_all = np.unique(np.concatenate([hand_vids["R"], hand_vids["L"]]))
    uv, n_fix = hands_carve.repair_gap_uvs(co, F, uv, wall_f, hv_all, load_texture(tex_path))
    log(tag, "finger-gap faces recoloured to skin:", n_fix)
np.savez(f"{WORK}/{tag}_carved.npz", co=co, faces=F, uv=uv, mat=mat, hand_R=hand_vids["R"], hand_L=hand_vids["L"], wall=(wall_all == 1))
json.dump(hands_json, open(f"{WORK}/{tag}_hands.json", "w"))
log(tag, "stage 1 done: verts", len(co), "faces", len(F))
