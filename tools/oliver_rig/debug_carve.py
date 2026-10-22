import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, hands_seg, hands_digits, hands_carve
tag = sys.argv[sys.argv.index("--") + 1]
cfg = load_config(tag)
d = np.load(f"{WORK}/{tag}_arrays.npz")
co, F, uv, vc = d["co"], d["faces"], d["uv"], d["vcol"]
mat = np.zeros(len(F), np.int32)
adj = hands_seg.build_adj(F, len(co))
t = timer()
for side, sgn in (("R", -1), ("L", 1)):
    h = cfg["hand_search"][side]
    m, seed, col = hands_seg.segment_hand(co, vc, adj, sgn, h["center"], h["radius"], h["shoulder"])
    res = hands_digits.analyze_hand(co, F, m, adj, side, finger_tips=cfg.get("finger_tips", {}).get(side))
    carved = hands_carve.carve_hand(co, F, uv, m, res, log_prefix=f"{tag}{side}")
    co, F, uv, mat, wtag = hands_carve.reintegrate(co, F, uv, mat, m, carved)
    uv = hands_carve.fix_wall_uvs(co, F, uv, wtag, np.ones(len(F), bool))
    log(tag, side, "done", round(t(), 1), "s; verts", len(co), "faces", len(F), "wall faces", int(wtag.sum()))
    # new arrays have extra faces appended -> vertex colours for debug: reuse nearest original colour
    vc = np.concatenate([vc, np.tile(np.array([[0.9, 0.5, 0.5]], np.float32), (len(co) - len(vc), 1))])
    adj = hands_seg.build_adj(F, len(co))
np.savez(f"{WORK}/{tag}_carved.npz", co=co, faces=F, uv=uv, mat=mat)
# render
viz.clear_scene()
me = arrays_to_mesh("carved", co, F, uv)
mt = bpy.data.materials.new("tex"); mt.use_nodes = True
img = bpy.data.images.load(os.environ["OLIVER_TEX"] + f"/{tag}/texture_0.png")
tn = mt.node_tree.nodes.new("ShaderNodeTexImage"); tn.image = img
bsdf = mt.node_tree.nodes["Principled BSDF"]; mt.node_tree.links.new(tn.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.append(mt)
ob = bpy.data.objects.new("carved", me); bpy.context.scene.collection.objects.link(ob)
cR = np.array(cfg["hand_search"]["R"]["center"]); cL = np.array(cfg["hand_search"]["L"]["center"])
specs = [("R_a", cR, 0.28, 270), ("R_b", cR, 0.28, 90), ("L_a", cL, 0.28, 90), ("L_b", cL, 0.28, 270)]
viz.render_specs(f"{WORK}/dbg/{tag}_carve", specs, 700, color_type="TEXTURE")
