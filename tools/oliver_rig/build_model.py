"""Stage 2+3: mouth, skeleton, weights, shape keys -> rigged .blend.
blender -b --factory-startup --python build_model.py -- <tag> <out.blend> <textures_dir>"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import mouth_build as mb, mouth_keys as mk, skeleton as sk, skin_weights as sw, materials as mtl, hand_weights as hw, rig_poses as rp

args = sys.argv[sys.argv.index("--") + 1:]
tag, out_blend, tex_dir = args[0], args[1], args[2]
cfg = load_config(tag)
prefix = MODELS[tag]["title"]
t = timer()
d = np.load(f"{WORK}/{tag}_carved.npz")
co, F, uv, mat = d["co"], d["faces"], d["uv"], d["mat"]
hands = json.load(open(f"{WORK}/{tag}_hands.json"))
fr = mb.MouthFrame(cfg)
# ---- mouth
asm = mb.fit_inside(mb.assemble(co, F, uv, mat, fr))
mb.clearance_report(asm, label=tag)
fld = mk.MouthFields(asm)
keys = mk.build_keys(fld)
log("mouth done", round(t(), 1))
# ---- skeleton
CO, FA, UV, MAT, PART = asm["co"], asm["faces"], asm["uv"], asm["mat"], asm["part"]
hd = {s: dict(W=np.array(hands[s]["W"])) for s in "LR"}
LM = sk.estimate_landmarks(CO[: asm["n_skin"]], fr, asm["y_center"], hd, cfg)
bones = sk.build_bone_list(LM, hands)
# ---- weights (skin graph only), mouth parts explicit
nskin, nsf = asm["n_skin"], asm["n_skin_faces"]
Wk = sw.geodesic_weights(CO[:nskin].astype(np.float64), FA[:nsf], bones)
W = np.zeros((len(CO), len(bones)), np.float32)
W[:nskin] = Wk
# explicit hand weights (palm / fingers / thumb) blended in across the wrist
bone_pos = {b["name"]: (b["head"], b["tail"]) for b in bones}
bone_index = {b["name"]: i for i, b in enumerate(bones)}
skin_graph = sw.mesh_graph(CO[:nskin].astype(np.float64), FA[:nsf])
for side, Side in (("L", "Left"), ("R", "Right")):
    vids = d[f"hand_{side}"]
    Wx, gate = hw.hand_weights(CO, vids, Side, hands[side], bone_pos, bone_index, len(bones), graph=skin_graph)
    cur = W[vids]
    W[vids] = cur * (1 - gate[:, None]) + Wx * gate[:, None]
mouth_mask = PART > 0
w_jaw = fld.w_jaw
W = sw.apply_jaw(W, bones, w_jaw, PART, mouth_mask, co=CO, z_mouth=fr.z0)
# rebuilt glasses (material slots 4/5) are rigid on the head
gl_faces = FA[MAT >= 4]
if len(gl_faces):
    gl_v = np.unique(gl_faces)
    W[gl_v] = 0
    W[gl_v, bone_index["Head"]] = 1.0
    log("glasses vertices bound to Head:", len(gl_v))
log("weights done", round(t(), 1), "rows with zero weight:", int((W.sum(1) < 0.5).sum()))
# ---- blender objects
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
me = arrays_to_mesh(prefix, CO, FA, UV, MAT)
skin_mat = mtl.make_skin_material(f"{prefix}_Skin", tex_dir, prefix)
me.materials.append(skin_mat)
for m_ in mtl.mouth_materials():
    me.materials.append(m_)
has_glasses = bool((MAT >= 4).any())
if has_glasses:
    for m_ in mtl.glasses_materials():
        me.materials.append(m_)
ob = bpy.data.objects.new(prefix, me)
bpy.context.scene.collection.objects.link(ob)
# vertex groups
names = [b["name"] for b in bones]
for bi, nm in enumerate(names):
    vg = ob.vertex_groups.new(name=nm)
    idx = np.where(W[:, bi] > 1e-4)[0]
    if len(idx) == 0:
        log("bone without influence:", nm)
        continue
    # vertex group assignment grouped by weight value is slow; use per-weight batches of rounded values
    wr = np.round(W[idx, bi], 3)
    order = np.argsort(wr)
    wr_s, idx_s = wr[order], idx[order]
    bounds = np.flatnonzero(np.diff(wr_s)) + 1
    for chunk_i, chunk_w in zip(np.split(idx_s, bounds), np.split(wr_s, bounds)):
        vg.add(chunk_i.tolist(), float(chunk_w[0]), "REPLACE")
log("vertex groups done", round(t(), 1))
# armature
arm_d = bpy.data.armatures.new(f"{prefix}_Armature")
arm_ob = bpy.data.objects.new(f"{prefix}_Rig", arm_d)
bpy.context.scene.collection.objects.link(arm_ob)
bpy.context.view_layer.objects.active = arm_ob
bpy.ops.object.mode_set(mode="EDIT")
eb = {}
for b in bones:
    e = arm_d.edit_bones.new(b["name"])
    e.head = Vector(b["head"])
    tail = Vector(b["tail"])
    if (tail - e.head).length < 1e-3:
        tail = e.head + Vector((0, 0, 0.01))
    e.tail = tail
    eb[b["name"]] = e
for b in bones:
    if b["parent"]:
        eb[b["name"]].parent = eb[b["parent"]]
for b in bones:
    if b["roll"] is not None:
        eb[b["name"]].align_roll(Vector(b["roll"]))
bpy.ops.object.mode_set(mode="OBJECT")
arm_d.display_type = "OCTAHEDRAL"
ob.parent = arm_ob
arm_ob["oliver_hands"] = json.dumps({s_: dict(n=hands[s_]["n"], a=hands[s_]["a"], u=hands[s_]["u"], thumb_dir=hands[s_]["thumb"]["dir"]) for s_ in "LR"})
bpy.context.view_layer.update()
thumb = {s_: rp.solve_thumb_fist(arm_ob, s_) for s_ in "LR"}
arm_ob["oliver_thumb"] = json.dumps(thumb)
log("thumb fist solutions", {s_: {k: round(v, 1) for k, v in thumb[s_].items()} for s_ in thumb})
mod = ob.modifiers.new("Armature", "ARMATURE")
mod.object = arm_ob
mod.use_vertex_groups = True
# shape keys
ob.shape_key_add(name="Basis", from_mix=False)
base = CO.astype(np.float32)
for kname in mk.KEY_NAMES:
    skb = ob.shape_key_add(name=kname, from_mix=False)
    skb.data.foreach_set("co", (base + keys[kname]).ravel())
    skb.slider_min, skb.slider_max = 0.0, 1.0
log("shape keys done", round(t(), 1))
# store metadata for later stages
meta = dict(tag=tag, prefix=prefix, bones=names, keys=mk.KEY_NAMES, n_verts=len(CO), n_faces=len(FA),
            part_counts=np.bincount(PART).tolist(), jaw_max_deg=mk.JAW_MAX_DEG)
ob["oliver_meta"] = json.dumps(meta)
arm_ob["oliver_hands"] = json.dumps({s_: dict(n=hands[s_]["n"], a=hands[s_]["a"], u=hands[s_]["u"], thumb_dir=hands[s_]["thumb"]["dir"]) for s_ in "LR"})
bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=True)
np.savez(f"{WORK}/{tag}_rigdata.npz", W=W, part=PART, keys=np.stack([keys[k] for k in mk.KEY_NAMES]).astype(np.float16), w_jaw=w_jaw)
log(tag, "build_model done", round(t(), 1), "s ->", out_blend)
