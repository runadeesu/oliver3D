"""Colour the hand by dominant finger-bone weight and render cut-away views with the finger bones.
blender -b rig.blend --python debug_handweights.py -- <tag> <outdir> [pose]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import bmesh as bm_
import viz, rig_poses as rp
args = sys.argv[sys.argv.index("--") + 1:]
tag, outdir = args[:2]
pose = args[2] if len(args) > 2 else "rest"
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
hands = rp.hand_info(arm)
rp.reset_pose(arm)
if pose != "rest":
    for s in "LR":
        getattr(rp, pose)(arm, s)
bpy.context.view_layer.update()
names = [vg.name for vg in mesh.vertex_groups]
fam = {"Index": (1, .1, .1), "Middle": (.1, .8, .1), "Ring": (.2, .3, 1), "Pinky": (1, .9, .1), "Thumb": (1, .1, 1)}
base = {}
for i, n in enumerate(names):
    col = None
    for k, c in fam.items():
        if k in n:
            j = int(n[-1])
            f = (0.55, 0.8, 1.0)[j - 1]
            col = tuple(np.array(c) * f)
    if col is None:
        col = (0.75, 0.75, 0.75) if "Hand" in n else (0.35, 0.35, 0.35)
    base[i] = col
dg = bpy.context.evaluated_depsgraph_get()
ev = mesh.evaluated_get(dg)
me = ev.to_mesh()
co = np.array([v.co[:] for v in me.vertices])
F = np.array([p.vertices[:] for p in me.polygons])
cols = np.zeros((len(co), 3))
src = mesh.data.vertices
for v in src:
    acc = np.zeros(3); wt = 0.0
    for g in v.groups:
        acc += np.array(base[g.group]) * g.weight; wt += g.weight
    cols[v.index] = acc / max(wt, 1e-6)
ev.to_mesh_clear()
viz.clear_scene() if False else None
for o in list(bpy.data.objects):
    if o.type == "MESH":
        o.hide_render = True
ob = viz.build_debug_object(co, F, None, cols, "wcol")
mt = bpy.data.materials.new("vc"); mt.use_nodes = True
nd = mt.node_tree.nodes
vc = nd.new("ShaderNodeVertexColor"); vc.layer_name = "Col"
mt.node_tree.links.new(vc.outputs["Color"], nd["Principled BSDF"].inputs["Base Color"])
ob.data.materials.append(mt)
sc = viz.make_scene(900, color_type="VERTEX", light="FLAT")
cam = viz.get_camera(sc)
for s in args[3:4] or ["R"]:
    pass
for s in "R":
    h = hands[s]
    wrist = np.array((arm.matrix_world @ arm.data.bones["RightHand"].head_local)[:])
    a, n, u = np.array(h["a"]), np.array(h["n"]), np.array(h["u"])
    c = wrist + a * 0.08
    for nm, d in (("palm", n), ("back", -n), ("thumb", u), ("tip", a)):
        viz.aim_dir(cam, c, 0.26, d, cut=0.12)
        sc.render.filepath = f"{outdir}/w_{s}_{pose}_{nm}.png"
        bpy.ops.render.render(write_still=True)
