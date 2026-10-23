"""Draw the skeleton (bones as thin tubes, joints as dots) over the x-rayed mesh to check joint placement.
blender -b rig.blend --python view_skeleton.py -- <outdir> [src_bones.json]   (the optional json = supplied reference joints, drawn in green)"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, rig_poses as rp
import bmesh
a = sys.argv[sys.argv.index("--") + 1:]
outdir = a[0]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
sc = viz.make_scene(900, color_type="MATERIAL", light="FLAT")
sh = sc.display.shading
sh.show_xray = True
sh.xray_alpha = 0.30
sh.single_color = (0.85, 0.85, 0.85)
mesh.hide_render = False
bb = np.array([(mesh.matrix_world @ Vector(c)).to_tuple() for c in mesh.bound_box])
center = tuple(((bb.min(0) + bb.max(0)) / 2).tolist())
scale = float(bb[:, 2].max() - bb[:, 2].min()) * 1.25

def tube_mesh(pairs, name, color, r=0.006):
    bm = bmesh.new()
    for p0, p1 in pairs:
        p0, p1 = Vector(p0), Vector(p1)
        d = (p1 - p0)
        if d.length < 1e-6:
            continue
        z = d.normalized()
        x = z.cross(Vector((0, 1, 0)) if abs(z.y) < 0.9 else Vector((1, 0, 0))).normalized()
        y = z.cross(x)
        vs = [bm.verts.new(p0 + (x * np.cos(t) + y * np.sin(t)) * r) for t in (0, np.pi / 2, np.pi, 3 * np.pi / 2)] + [bm.verts.new(p1 + (x * np.cos(t) + y * np.sin(t)) * r) for t in (0, np.pi / 2, np.pi, 3 * np.pi / 2)]
        for i in range(4):
            bm.faces.new((vs[i], vs[(i + 1) % 4], vs[4 + (i + 1) % 4], vs[4 + i]))
        # joint ball at the head
        for sx in (-1, 1):
            pass
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    mat = bpy.data.materials.new(name); mat.diffuse_color = (*color, 1)
    me.materials.append(mat)
    return ob
mw = arm.matrix_world
pairs = []
heads = []
for b in arm.data.bones:
    if any(k in b.name for k in ("Thumb", "Index", "Middle", "Ring", "Pinky")):
        continue
    pairs.append(((mw @ b.head_local).to_tuple(), (mw @ b.tail_local).to_tuple()))
    heads.append((mw @ b.head_local).to_tuple())
for m_ in mesh.data.materials:
    if m_:
        m_.diffuse_color = (0.75, 0.75, 0.78, 1)
tube_mesh(pairs, "bones", (0.9, 0.0, 0.0), 0.007)
# joints as short crosses
tube_mesh([((h[0] - 0.012, h[1], h[2]), (h[0] + 0.012, h[1], h[2])) for h in heads], "joints", (0.1, 0.1, 0.9), 0.009)
if len(a) > 1 and os.path.exists(a[1]):
    ref = json.load(open(a[1]))
    rp_ = [(v[0], v[1]) for k, v in ref.items()]
    tube_mesh(rp_, "ref", (0.1, 0.7, 0.1), 0.005)
for vn, az in (("front", 0), ("side", 90)):
    viz.aim_camera(viz.get_camera(sc), center, scale, az)
    sc.render.filepath = f"{outdir}/skel_{vn}.png"
    bpy.ops.render.render(write_still=True)
