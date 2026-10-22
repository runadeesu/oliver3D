"""Re-import an exported FBX/GLB into an EMPTY scene and verify rig / weights / morphs / textures / animation.
blender -b --factory-startup --python verify_export.py -- <file> <ref_rigdata.npz or ''> <tag>"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import rig_poses as rp
from mathutils import Quaternion

path, ref, tag = sys.argv[sys.argv.index("--") + 1:][:3]
bpy.ops.wm.read_factory_settings(use_empty=True)
t = timer()
if path.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=path)
else:
    bpy.ops.import_scene.gltf(filepath=path)
log("imported", os.path.basename(path), round(t(), 1), "s")
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print("VERIFY objects:", [(o.name, o.type) for o in bpy.data.objects])
arm = arms[0]
mesh = max(meshes, key=lambda o: len(o.data.vertices))
me = mesh.data
nv = len(me.vertices)
print("VERIFY mesh", mesh.name, "verts", nv, "polys", len(me.polygons), "materials", [m.name if m else None for m in me.materials])
bone_names = [b.name for b in arm.data.bones]
need = []
for S in ("Left", "Right"):
    for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        for k in (1, 2, 3):
            need.append(f"{S}Hand{f}{k}")
    need += [f"{S}Hand", f"{S}ForeArm", f"{S}Arm", f"{S}Shoulder", f"{S}UpLeg", f"{S}Leg", f"{S}Foot"]
need += ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "Jaw"]
def norm(n):
    return n.split(":")[-1].replace(".", "_") if False else n
missing = [n for n in need if n not in bone_names]
print("VERIFY bones", len(bone_names), "missing required:", missing)
# vertex groups / weights
vg_names = [g.name for g in mesh.vertex_groups]
print("VERIFY vertex groups", len(vg_names), "finger groups present:", sum(1 for n in vg_names if any(k in n for k in ("Thumb", "Index", "Middle", "Ring", "Pinky"))))
W = np.zeros((nv, len(vg_names)), np.float32)
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
print("VERIFY weighted vertices: %d / %d (sum>0.99: %d)" % ((W.sum(1) > 0).sum(), nv, (W.sum(1) > 0.99).sum()))
# shape keys
sk = me.shape_keys
keys = [k.name for k in sk.key_blocks] if sk else []
print("VERIFY shape keys:", keys)
# textures
for m in me.materials:
    if m and m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                im = n.image
                ok = im.size[0] > 0 and (im.has_data or im.packed_file is not None)
                print("VERIFY texture", m.name, n.label or n.name, im.name, tuple(im.size), "has_data", im.has_data, "packed", im.packed_file is not None, "path", im.filepath[-60:])
# actions
print("VERIFY actions:", [(a.name, int(a.frame_range[0]), int(a.frame_range[1])) for a in bpy.data.actions])
# --- deformation tests on the re-imported rig
def evaluated(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    c = np.empty(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("co", c)
    ev.to_mesh_clear()
    return c.reshape(-1, 3)
if arm.animation_data:
    arm.animation_data.action = None
if sk and sk.animation_data:
    sk.animation_data.action = None
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion((1, 0, 0, 0)); pb.location = (0, 0, 0)
for k in sk.key_blocks:
    k.value = 0
bpy.context.view_layer.update()
mw = mesh.matrix_world
rest = evaluated(mesh)
co_rest = np.array([ (mw @ Vector(p)).to_tuple() for p in rest[:1]]) if False else rest
# finger fist: rotate finger bones about their local X by +80/+90/+60 deg and measure movement of weighted vertices
def bone_set(name, deg):
    pb = arm.pose.bones[name]
    pb.rotation_mode = "XYZ"; pb.rotation_euler = (np.radians(deg), 0, 0)
for S in ("Right",):
    for f in ("Index", "Middle", "Ring", "Pinky"):
        for k, deg in zip((1, 2, 3), (70, 90, 60)):
            bone_set(f"{S}Hand{f}{k}", deg)
bpy.context.view_layer.update()
posed = evaluated(mesh)
mv = np.linalg.norm(posed - rest, axis=1)
gidx = {n: i for i, n in enumerate(vg_names)}
fing = [gidx[n] for n in vg_names if n.startswith("RightHand") and any(k in n for k in ("Index", "Middle", "Ring", "Pinky"))]
fw = W[:, fing].sum(1)
print("VERIFY fist(R): vertices with finger weight>0.5: %d, their mean move %.1f mm (min %.1f); vertices with zero finger weight moving >0.5mm: %d" % ((fw > 0.5).sum(), mv[fw > 0.5].mean() * 1000, mv[fw > 0.5].min() * 1000, ((fw < 1e-4) & (mv > 5e-4)).sum()))
# sleeve / torso must not move with finger rotation
arm_idx = [gidx[n] for n in ("RightForeArm", "RightArm") if n in gidx]
sl = W[:, arm_idx].sum(1) > 0.9
print("VERIFY sleeve/upper-arm vertices (ForeArm/Arm weight>0.9): %d, max move under finger fist: %.3f mm" % (sl.sum(), mv[sl].max() * 1000 if sl.any() else 0))
for pb in arm.pose.bones:
    pb.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
# mouth shape keys
for kname in ("jawOpen", "mouthClose", "viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O", "mouthSmile"):
    if kname not in sk.key_blocks:
        print("VERIFY mouth key missing:", kname); continue
    for k in sk.key_blocks: k.value = 0
    sk.key_blocks[kname].value = 1.0
    bpy.context.view_layer.update()
    ev = evaluated(mesh)
    d = np.linalg.norm(ev - rest, axis=1)
    print("VERIFY key %-11s moves %5d verts, max %.1f mm" % (kname, (d > 1e-4).sum(), d.max() * 1000))
for k in sk.key_blocks: k.value = 0
if ref:
    r = np.load(ref)
    print("VERIFY reference rig data: W", r["W"].shape, "part counts", np.bincount(r["part"]).tolist())
print("VERIFY done")
