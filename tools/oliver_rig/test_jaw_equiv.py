"""Compare jaw bone rotation (13 deg) with the jawOpen shape key. blender -b rig.blend --python test_jaw_equiv.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import rig_poses as rp, mouth_keys as mk
arm, mesh = rp.find_rig()
dg = bpy.context.evaluated_depsgraph_get()
def evaluated():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    m = ev.to_mesh()
    n = len(m.vertices)
    c = np.empty(n * 3, np.float32); m.vertices.foreach_get("co", c)
    ev.to_mesh_clear()
    return c.reshape(-1, 3)
rp.reset_pose(arm); rp.set_keys(mesh)
bpy.context.view_layer.update()
rest = evaluated()
rp.jaw_pose(arm, mk.JAW_MAX_DEG); bpy.context.view_layer.update()
bone = evaluated()
rp.reset_pose(arm); rp.set_keys(mesh, jawOpen=1.0); bpy.context.view_layer.update()
key = evaluated()
mv = np.linalg.norm(key - rest, axis=1)
mb_ = np.linalg.norm(bone - rest, axis=1)
sel = mv > 1e-4
diff = np.linalg.norm(bone - key, axis=1)
print("EQUIV vertices moved by key:", int(sel.sum()), "by bone:", int((mb_ > 1e-4).sum()))
print("EQUIV max move key %.1f mm bone %.1f mm; mean |bone-key| over moved verts %.2f mm, 95th pct %.2f mm, max %.2f mm" % (mv.max() * 1000, mb_.max() * 1000, diff[sel].mean() * 1000, np.percentile(diff[sel], 95) * 1000, diff[sel].max() * 1000))
d = np.load(os.path.join(WORK, "turbo_rigdata.npz"))
part, w_jaw, Wm = d["part"], d["w_jaw"], d["W"]
names = [vg.name for vg in mesh.vertex_groups]
ij = names.index("Jaw"); ih = names.index("Head"); in_ = names.index("Neck")
order = np.argsort(-diff)[:8]
for v in order:
    print("EQV vtx", v, "part", int(part[v]), "w_jaw %.3f" % w_jaw[v], "W[Jaw] %.3f W[Head] %.3f W[Neck] %.3f" % (Wm[v, ij], Wm[v, ih], Wm[v, in_]), "rest", (rest[v] * 1000).round(1).tolist(), "key", (key[v] * 1000).round(1).tolist(), "bone", (bone[v] * 1000).round(1).tolist())
# statistics by part
for pid in range(7):
    m = (part == pid) & sel
    if m.sum():
        print("EQV part", pid, "n", int(m.sum()), "mean diff %.2f mm" % (diff[m].mean() * 1000))
