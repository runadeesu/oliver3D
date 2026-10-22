"""Apply object transforms so the mesh is Z-up in world space and save the raw .blend again.
blender <tag>_raw.blend --background --python normalize_raw.py"""
import bpy, sys
# apply object transforms so mesh is Z-up in world, saves back
for o in bpy.data.objects:
    o.select_set(False)
for o in bpy.data.objects:
    if o.type=='MESH':
        bpy.context.view_layer.objects.active=o
        o.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        me=o.data
        import numpy as np
        co=np.empty(len(me.vertices)*3,dtype=np.float32); me.vertices.foreach_get('co',co); co=co.reshape(-1,3)
        print("NORM", o.name, "bbox", co.min(0).round(3), co.max(0).round(3))
bpy.ops.wm.save_mainfile()
