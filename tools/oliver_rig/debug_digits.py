import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg, hands_digits
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
adj = hands_seg.build_adj(F, len(co))
viz.clear_scene()
info = {}
keep = np.zeros(len(co), bool)
hand_data = {}
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    keep |= m
    used, f, P, G, bidx, dist = hands_digits.geodesic_field(co, F, m, adj)
    tips = hands_digits.find_tips(P, dist)
    W, a, u, n, thumb, others = hands_digits.hand_frame_from_tips(P, bidx, tips, dist, side)
    hand_data[side] = dict(P=P, tips=tips, W=W, a=a, u=u, n=n, thumb=thumb, others=others, dist=dist)
    log(tag, side, "W", W.round(3), "a", a.round(2), "u(thumb)", u.round(2), "n(palm)", n.round(2), "tips", len(tips))
fm = keep[F].all(1)
viz.build_debug_object(co, F[fm], uv[fm], vc)

def marker(p, r, color, name):
    me = bpy.data.meshes.new(name)
    import bmesh as bm_
    b = bm_.new(); bm_.ops.create_uvsphere(b, u_segments=12, v_segments=8, radius=r); b.to_mesh(me); b.free()
    ob = bpy.data.objects.new(name, me); ob.location = p
    mat = bpy.data.materials.new(name); mat.diffuse_color = (*color, 1)
    ob.data.materials.append(mat); ob.show_in_front = True
    bpy.context.scene.collection.objects.link(ob); return ob

for side, hd in hand_data.items():
    for k, t in enumerate(hd["tips"]):
        col = (0, 0, 1) if t == hd["thumb"] else (1, 0, 0)
        marker(hd["P"][t], 0.004, col, f"tip{side}{k}")
    marker(hd["W"], 0.006, (0, 1, 0), f"W{side}")
    marker(hd["W"] + hd["n"] * 0.03, 0.004, (1, 1, 0), f"n{side}")   # yellow = palm side
    marker(hd["W"] + hd["u"] * 0.03, 0.004, (0, 1, 1), f"u{side}")   # cyan = thumb side
c = np.array(cfg["hand_search"]["R"]["center"])
cl = np.array(cfg["hand_search"]["L"]["center"])
specs = [("R_pm", c, 0.3, 270), ("R_pp", c, 0.3, 90), ("L_pm", cl, 0.3, 90), ("L_pp", cl, 0.3, 270)]
viz.render_specs(f"{WORK}/dbg/{tag}_dg", specs, 700, color_type="MATERIAL" if False else "TEXTURE")
