"""Add the check animations, save the final .blend, export FBX + GLB.
blender -b rig.blend --python build_anim_export.py -- <tag> <outdir> <tex_dir>"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import anim, rig_poses as rp

tag, outdir, tex_dir = sys.argv[sys.argv.index("--") + 1:][:3]
prefix = MODELS[tag]["title"]
os.makedirs(outdir, exist_ok=True)
arm, mesh = rp.find_rig()
actions, offs, total = anim.build_actions(arm, mesh)
anim.build_nla(arm, mesh, actions)
sc = bpy.context.scene
sc.render.fps = anim.FPS
sc.frame_start, sc.frame_end = 1, total
sc.frame_set(1)
log("actions:", [a.name for a in bpy.data.actions], "total frames", total)
arm["oliver_anim"] = json.dumps(dict(order=anim.ORDER, offsets=offs, total=total, fps=anim.FPS))
# --- .blend (textures stay external, relative paths)
blend_path = os.path.join(outdir, f"{prefix}_rigged.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True, relative_remap=True)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
log("saved", blend_path, os.path.getsize(blend_path) // 1000000, "MB")

# --- exports: the concatenated Check_All timeline is the active animation
def activate_all():
    arm.animation_data.action = bpy.data.actions["Check_All"]
    mesh.data.shape_keys.animation_data.action = bpy.data.actions["Check_All_Keys"]
    for t in arm.animation_data.nla_tracks: t.mute = True
    for t in mesh.data.shape_keys.animation_data.nla_tracks: t.mute = True
activate_all()
bpy.ops.object.select_all(action="DESELECT")
arm.select_set(True); mesh.select_set(True)
bpy.context.view_layer.objects.active = arm
fbx_path = os.path.join(outdir, f"{prefix}.fbx")
bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=True, object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                         bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
                         bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0, bake_anim_step=1.0,
                         path_mode="RELATIVE", embed_textures=False, mesh_smooth_type="FACE", use_tspace=True, primary_bone_axis="Y", secondary_bone_axis="X")
log("FBX", fbx_path, os.path.getsize(fbx_path) // 1000000, "MB")
glb_path = os.path.join(outdir, f"{prefix}.glb")
bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB", use_selection=True, export_image_format="JPEG", export_jpeg_quality=92,
                          export_morph=True, export_skins=True, export_animations=True, export_animation_mode="ACTIVE_ACTIONS",
                          export_apply=False, export_yup=True)
log("GLB", glb_path, os.path.getsize(glb_path) // 1000000, "MB")
