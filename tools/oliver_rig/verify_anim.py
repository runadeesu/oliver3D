"""Play the animation of a re-imported FBX/GLB in an EMPTY scene and check that every finger / the jaw really moves the mesh.
blender -b --factory-startup --python verify_anim.py -- <file.fbx|glb>
Prints, per timeline segment, the peak mean displacement (mm) of the vertices owned by each finger / the jaw / the lips."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *

path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
if path.lower().endswith(".fbx"):
    bpy.ops.import_scene.fbx(filepath=path)
else:
    bpy.ops.import_scene.gltf(filepath=path)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"], key=lambda o: len(o.data.vertices))
nv = len(mesh.data.vertices)
names = [g.name for g in mesh.vertex_groups]
W = np.zeros((nv, len(names)), np.float32)
for v in mesh.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
gi = {n: i for i, n in enumerate(names)}
# the imported file keeps the timeline in the (single) action of the armature / of the shape keys; make sure both are active
for a in bpy.data.actions:
    print("ACTION", a.name, [int(x) for x in a.frame_range])
if arm.animation_data and arm.animation_data.action is None and bpy.data.actions:
    arm.animation_data.action = [a for a in bpy.data.actions if "Rig" in a.name or a.name == "Animation"][0]
import anim
SEG = anim.segment_table()
groups = {}
for S, side in (("Left", "L"), ("Right", "R")):
    for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        idx = [gi[n] for n in names if n.startswith(f"{S}Hand{f}")]
        groups[f"{side}_{f}"] = W[:, idx].sum(1) > 0.5
groups["Jaw"] = W[:, gi["Jaw"]] > 0.5
sc = bpy.context.scene


def evaluated():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    m = ev.to_mesh()
    c = np.empty(len(m.vertices) * 3, np.float32)
    m.vertices.foreach_get("co", c)
    ev.to_mesh_clear()
    return c.reshape(-1, 3)


sc.frame_set(1)
rest = evaluated()
print("VANIM", os.path.basename(path), "fps", sc.render.fps, "action frame range", min(int(a.frame_range[0]) for a in bpy.data.actions), max(int(a.frame_range[1]) for a in bpy.data.actions))
for seg, a, b in SEG:
    peak = {k: 0.0 for k in groups}
    for fr in range(a, b + 1, 2):
        sc.frame_set(fr)
        d = np.linalg.norm(evaluated() - rest, axis=1)
        for k, m in groups.items():
            if m.any():
                peak[k] = max(peak[k], float(d[m].mean()) * 1000)
    fing = " ".join(f"{k}={v:.0f}" for k, v in peak.items() if k != "Jaw")
    print(f"VANIM {seg:20s} frames {a}-{b}  peak mean move (mm): {fing}  Jaw={peak['Jaw']:.1f}")
# the very last keyed frame must be back at rest (animation ends in the neutral A-pose)
last = int(max(a.frame_range[1] for a in bpy.data.actions))
sc.frame_set(last)
print("VANIM last frame vs frame 1: max vertex difference %.2f mm (frame %d)" % (np.linalg.norm(evaluated() - rest, axis=1).max() * 1000, last))
