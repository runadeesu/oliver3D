"""Find finger vertices that do not follow a fist pose. blender -b rig.blend --python debug_stuck.py -- <tag>"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import rig_poses as rp
tag = sys.argv[sys.argv.index("--") + 1]
arm, mesh = rp.find_rig()
hands = rp.hand_info(arm)
rp.reset_pose(arm)
dg = bpy.context.evaluated_depsgraph_get()
def evalco():
    dg = bpy.context.evaluated_depsgraph_get()
    me = mesh.evaluated_get(dg).to_mesh()
    co = np.array([v.co[:] for v in me.vertices]) 
    mesh.evaluated_get(dg).to_mesh_clear()
    return co
rest = evalco()
for s in "RL":
    rp.reset_pose(arm)
    for pose in ("fist",):
        getattr(rp, pose)(arm, s)
    bpy.context.view_layer.update()
    co = evalco()
    d = np.linalg.norm(co - rest, axis=1)
    wr = np.array(arm.matrix_world @ arm.pose.bones[f"{rp.SIDES[s]}Hand"].head)
    h = hands[s]
    a = np.array(h["a"])
    r = rest - wr
    along = r @ a
    near = (np.linalg.norm(r, axis=1) < 0.21)
    # classify hand verts: any weight in this side's Hand* (incl. finger) group
    names = [vg.name for vg in mesh.vertex_groups]
    fing = [i for i, n in enumerate(names) if n.startswith(rp.SIDES[s] + "Hand") and n != rp.SIDES[s] + "Hand"]
    wsum = np.zeros(len(rest))
    dom = np.full(len(rest), "", dtype=object)
    best = np.zeros(len(rest))
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.group in fing:
                wsum[v.index] += g.weight
    # stuck: far along axis (> 0.045 beyond wrist), weights low on finger bones, skin close to hand
    mask = near & (along > 0.05)
    print(f"[{tag} {s}] hand-near verts {mask.sum()}  moved<2mm: {(mask & (d < 0.002)).sum()}  (wsum<0.5: {(mask & (wsum < 0.5)).sum()})")
    stuck = mask & (d < 0.004) & (along > 0.09)
    print("   stuck far verts", stuck.sum())
    if stuck.sum():
        idx = np.where(stuck)[0]
        c = rest[idx]
        print("   centroid", c.mean(0).round(3), "extent", c.min(0).round(3), c.max(0).round(3), "mean wsum", wsum[idx].mean().round(3))
        groups = {}
        for i in idx[:2000]:
            for g in mesh.data.vertices[i].groups:
                groups[names[g.group]] = groups.get(names[g.group], 0) + g.weight
        print("   groups", sorted(groups.items(), key=lambda kv: -kv[1])[:6])
rp.reset_pose(arm)
