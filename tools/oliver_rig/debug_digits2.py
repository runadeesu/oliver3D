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
keep = np.zeros(len(co), bool)
res = {}
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    keep |= m
    ov = cfg.get("finger_tips", {}).get(side)
    res[side] = hands_digits.analyze_hand(co, F, m, adj, side, finger_tips=ov)
    r = res[side]
    log(tag, side, "synth", r["synthesized"], "Lh", round(r["Lh"], 3), "spacing", round(r["spacing"], 4), "digits", {k: (round(v["radius"], 4), v["n_used"]) for k, v in r["digits"].items()}, "thumb", round(r["thumb"]["radius"], 4), r["thumb"]["n_used"])
fm = keep[F].all(1)
mat = bpy.data.materials.new("skin"); mat.diffuse_color = (0.9, 0.7, 0.6, 1)
ob = viz.build_debug_object(co, F[fm], uv[fm], None); ob.data.materials.append(mat)
ob.display_type = 'SOLID'
import bmesh as bm_

def cyl(p0, p1, r, color, name):
    p0, p1 = Vector(p0), Vector(p1)
    me = bpy.data.meshes.new(name); b = bm_.new()
    bm_.ops.create_cone(b, cap_ends=True, segments=8, radius1=r, radius2=r, depth=(p1 - p0).length)
    b.to_mesh(me); b.free()
    o = bpy.data.objects.new(name, me); o.location = (p0 + p1) / 2
    o.rotation_euler = (p1 - p0).to_track_quat('Z', 'Y').to_euler()
    m = bpy.data.materials.new(name); m.diffuse_color = (*color, 1); o.data.materials.append(m)
    o.show_in_front = True; bpy.context.scene.collection.objects.link(o)

def dot(p, r, color, name):
    me = bpy.data.meshes.new(name); b = bm_.new(); bm_.ops.create_uvsphere(b, u_segments=10, v_segments=6, radius=r); b.to_mesh(me); b.free()
    o = bpy.data.objects.new(name, me); o.location = p
    m = bpy.data.materials.new(name); m.diffuse_color = (*color, 1); o.data.materials.append(m)
    o.show_in_front = True; bpy.context.scene.collection.objects.link(o)

cols = {"index": (1, 0, 0), "middle": (1, 0.5, 0), "ring": (0, 0.8, 0), "pinky": (0, 0.6, 1)}
for side, r in res.items():
    dot(r["W"], 0.006, (1, 1, 0), f"W{side}")
    for name, dg in r["digits"].items():
        J = dg["joints"]
        for k in range(3):
            cyl(J[k], J[k + 1], 0.002, cols[name], f"{side}{name}{k}")
        for k in range(4):
            dot(J[k], 0.0035, (1, 1, 1), f"{side}{name}j{k}")
    th = r["thumb"]
    cyl(th["tip"] - th["dir"] * 0.09, th["tip"], 0.002, (0.7, 0, 1), f"{side}thumb")
    dot(th["tip"], 0.0045, (0.7, 0, 1), f"{side}thumbtip")
c = np.array(cfg["hand_search"]["R"]["center"]); cl = np.array(cfg["hand_search"]["L"]["center"])
specs = [("R_pm", c, 0.3, 270), ("R_pp", c, 0.3, 90), ("L_pm", cl, 0.3, 90), ("L_pp", cl, 0.3, 270)]
viz.render_specs(f"{WORK}/dbg/{tag}_d2", specs, 700, color_type="MATERIAL")
