"""Import a source FBX/GLB into an empty scene, print object / mesh / image / material info and save <WORK>/<tag>_raw.blend.
blender -b --factory-startup --python import_fbx.py -- <file.fbx> <tag>"""
import bpy, sys, time, os, numpy as np
argv = sys.argv[sys.argv.index('--')+1:]
src, tag = argv[0], argv[1]
t=time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
if src.lower().endswith('.fbx'):
    bpy.ops.import_scene.fbx(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)
print(f"[{tag}] import {time.time()-t:.1f}s")
for o in bpy.data.objects:
    print(f"[{tag}] OBJ {o.name!r} type={o.type} parent={o.parent.name if o.parent else None} loc={tuple(round(v,3) for v in o.location)} rot={tuple(round(v,3) for v in o.rotation_euler)} scale={tuple(round(v,4) for v in o.scale)} dims={tuple(round(v,3) for v in o.dimensions)}")
    if o.type=='MESH':
        me=o.data
        me.calc_loop_triangles()
        print(f"[{tag}]   verts={len(me.vertices)} faces={len(me.polygons)} tris={len(me.loop_triangles)} uv={[u.name for u in me.uv_layers]} mats={[m.name if m else None for m in me.materials]} vgroups={len(o.vertex_groups)} shapekeys={me.shape_keys is not None} attrs={[a.name for a in me.attributes]}")
        co=np.empty(len(me.vertices)*3,dtype=np.float32); me.vertices.foreach_get('co',co); co=co.reshape(-1,3)
        print(f"[{tag}]   bbox min={co.min(0).round(3)} max={co.max(0).round(3)}")
for im in bpy.data.images:
    print(f"[{tag}] IMG {im.name!r} size={tuple(im.size)} packed={im.packed_file is not None} filepath={im.filepath!r} colorspace={im.colorspace_settings.name}")
for m in bpy.data.materials:
    print(f"[{tag}] MAT {m.name!r} nodes={[ (n.type, n.name) for n in m.node_tree.nodes] if m.use_nodes else None}")
out=os.path.join(os.environ.get('OLIVER_WORK', '/tmp/oliver_work'), f'{tag}_raw.blend')
os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out), compress=False)
print(f"[{tag}] saved {out} total {time.time()-t:.1f}s")
