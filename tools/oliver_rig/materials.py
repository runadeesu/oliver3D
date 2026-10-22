"""Materials for the rigged model: original PBR textures + simple mouth materials."""
from common import *
import os


def merge_metal_rough(rough_path, metal_path, out_path):
    """glTF packs roughness into G and metallic into B of one image."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    if os.path.exists(out_path):
        return out_path
    r = np.asarray(Image.open(rough_path).convert("RGB"))[..., 0]
    m = np.asarray(Image.open(metal_path).convert("RGB"))[..., 0]
    if r.shape != m.shape:
        m = np.asarray(Image.fromarray(m).resize(r.shape[::-1], Image.BILINEAR))
    out = np.stack([np.full_like(r, 255), r, m], -1)
    Image.fromarray(out).save(out_path, optimize=False, compress_level=3)
    return out_path


def make_skin_material(name, tex_dir, prefix):
    base = os.path.join(tex_dir, f"{prefix}_base_color.png")
    nrm = os.path.join(tex_dir, f"{prefix}_normal.png")
    mr = os.path.join(tex_dir, f"{prefix}_metallic_roughness.png")
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (400, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def tex(path, cs, loc, label):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.image.colorspace_settings.name = cs
        n.location = loc
        n.label = label
        n.name = label
        return n
    tb = tex(base, "sRGB", (-500, 300), "BaseColor")
    nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    if os.path.exists(mr):
        tm = tex(mr, "Non-Color", (-700, -50), "MetallicRoughness")
        sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-380, -50)
        nt.links.new(tm.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:                                              # sources without roughness / metallic maps (remade Meshy exports)
        bsdf.inputs["Roughness"].default_value = 0.6
        bsdf.inputs["Metallic"].default_value = 0.0
    tn = tex(nrm, "Non-Color", (-700, -400), "Normal")
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-300, -400)
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_flat_material(name, color, rough=0.5, spec=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    mat.diffuse_color = (*color, 1)
    return mat


def mouth_materials():
    return [
        make_flat_material("Mouth_Inside", (0.30, 0.055, 0.065), 0.55),
        make_flat_material("Teeth", (0.90, 0.86, 0.76), 0.38),
        make_flat_material("Tongue", (0.72, 0.24, 0.27), 0.45),
    ]
