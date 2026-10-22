"""Debug / preview rendering helpers (Workbench, works headless with software GL)."""
import math
from common import *


def clear_scene():
    """Remove the default cube/light/camera that factory startup leaves behind."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def make_scene(res=1024, bg=(0.5, 0.5, 0.55), color_type="TEXTURE", light="FLAT", engine="BLENDER_WORKBENCH"):
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    if engine == "BLENDER_WORKBENCH":
        sh = sc.display.shading
        sh.light = light
        sh.color_type = color_type
        sh.show_cavity = False
        sh.show_shadows = False
        sh.show_specular_highlight = False
        sh.background_type = "WORLD"
        sc.display.render_aa = "8"
    sc.view_settings.view_transform = "Standard"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = False
    sc.world.color = bg
    return sc


def get_camera(sc, ortho=True):
    cam = bpy.data.objects.get("viz_cam")
    if cam is None:
        cd = bpy.data.cameras.new("viz_cam")
        cam = bpy.data.objects.new("viz_cam", cd)
        sc.collection.objects.link(cam)
    cam.data.type = "ORTHO" if ortho else "PERSP"
    cam.data.clip_start, cam.data.clip_end = 0.01, 50
    sc.camera = cam
    return cam


def aim_camera(cam, center, scale, azimuth_deg=0.0, elevation_deg=0.0, dist=5.0):
    """azimuth 0 = camera at -Y looking +Y (sees the character's front); 90 = camera at +X."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    c = Vector(center)
    cam.data.clip_start = 0.01
    off = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.location = c + off
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    if cam.data.type == "ORTHO":
        cam.data.ortho_scale = scale
    else:
        cam.data.lens = 50
        cam.data.sensor_width = 36
        cam.data.lens = 36 * dist / scale  # frame ~scale metres at the target distance


def render_specs(prefix, specs, res=1024, **scene_kw):
    """specs: list of (name, center(3), scale, azimuth[, elevation])"""
    sc = make_scene(res, **scene_kw)
    cam = get_camera(sc)
    outs = []
    for sp in specs:
        name, center, scale, az = sp[:4]
        el = sp[4] if len(sp) > 4 else 0.0
        aim_camera(cam, center, scale, az, el)
        sc.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)
        outs.append(sc.render.filepath)
    return outs


def build_debug_object(co, faces, uv=None, colors=None, name="dbg"):
    me = arrays_to_mesh(name, co, faces, uv if uv is not None else np.zeros((len(faces), 3, 2), np.float32))
    if colors is not None:
        attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        rgba = np.ones((len(co), 4), np.float32)
        rgba[:, :3] = colors
        attr.data.foreach_set("color", rgba.ravel())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def aim_dir(cam, center, scale, direction, up=(0, 0, 1), cut=None):
    """Camera placed along `direction` (unit vector from the target to the camera).
    cut: clip everything nearer to the camera than `cut` metres in front of the target (removes sleeves/body in the way)."""
    d = Vector(direction).normalized()
    c = Vector(center)
    cam.data.clip_start = 5.0 - cut if cut else 0.01
    cam.location = c + d * 5.0
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    if cam.data.type == "ORTHO":
        cam.data.ortho_scale = scale
