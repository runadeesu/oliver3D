"""Prepare a Meshy FBX that already carries an (auto-)rig for the pipeline: take the bind-pose mesh in world metres, drop the supplied
skeleton / skin weights / animations, extract the textures and dump <WORK>/<tag>_arrays.npz (+ the supplied joints for reference).
blender -b --factory-startup --python prep_rigged_fbx.py -- <file.fbx> <tag> <tex_out_dir>
Textures are written as <tex_out_dir>/texture_0.png (base colour) and texture_0_normal.png (+ _roughness / _metallic when present)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *

fbx, tag, tex_out = sys.argv[sys.argv.index("--") + 1:][:3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
assert len(meshes) == 1, [o.name for o in meshes]
mesh = meshes[0]
if arms:
    arms[0].data.pose_position = "REST"
    if arms[0].animation_data:
        arms[0].animation_data.action = None
bpy.context.view_layer.update()
mw = np.array(mesh.matrix_world)
co, faces, uv, mat = mesh_to_arrays(mesh)
co = (co.astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]).astype(np.float32)
# Meshy exports split vertices along UV seams (and flat parts): weld vertices at identical positions so that the surface is connected
q = np.round(co.astype(np.float64) * 1e6).astype(np.int64)
uq, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
nv0 = len(co)
co = co[first]
faces = inv[faces].astype(np.int32)
good = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
if not good.all():
    log(tag, "dropping", int((~good).sum()), "degenerate faces after welding")
    faces, uv, mat = faces[good], uv[good], mat[good]
log(tag, "welded vertices", nv0, "->", len(co))
log(tag, "world bbox", co.min(0).round(3), co.max(0).round(3), "verts", len(co), "faces", len(faces))
# supplied joints (reference only)
if arms:
    a = arms[0]
    A = np.array(a.matrix_world)
    bones = {b.name: [(A[:3, :3] @ np.array(b.head_local) + A[:3, 3]).tolist(), (A[:3, :3] @ np.array(b.tail_local) + A[:3, 3]).tolist()] for b in a.data.bones}
    json.dump(bones, open(f"{WORK}/{tag}_src_bones.json", "w"))
# textures
os.makedirs(tex_out, exist_ok=True)
node_tex = {}
for m in mesh.data.materials:
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            for o in n.outputs:
                for l in o.links:
                    node_tex[l.to_socket.name if l.to_node.type != "NORMAL_MAP" else "Normal"] = n.image
for key, name in (("Base Color", "texture_0.png"), ("Normal", "texture_0_normal.png"), ("Roughness", "texture_0_roughness.png"), ("Metallic", "texture_0_metallic.png")):
    im = node_tex.get(key)
    if im is None:
        log(tag, "no image for", key)
        continue
    im.filepath_raw = os.path.join(tex_out, name)
    im.file_format = "PNG"
    im.save()
    log(tag, "wrote", name, tuple(im.size))
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
tex = load_texture(os.path.join(tex_out, "texture_0.png"))
vc = vertex_colors(co, faces, uv, tex)
np.savez(f"{WORK}/{tag}_arrays.npz", co=co, faces=faces, uv=uv, mat=mat, vcol=vc)
log(tag, "saved arrays", co.shape, faces.shape)
