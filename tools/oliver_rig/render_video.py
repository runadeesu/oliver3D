"""Render the check animation of a delivered .blend to an MP4 (full body + hand / face close-ups + captions).
blender -b model.blend --python render_video.py -- <tag> <out.mp4> [frame_step] [first] [last]"""
import sys, os, json, subprocess, shutil
sys.path.insert(0, os.path.dirname(__file__))
from common import *
import viz, anim, rig_poses as rp
from PIL import Image, ImageDraw, ImageFont

a = sys.argv[sys.argv.index("--") + 1:]
tag, out_mp4 = a[0], a[1]
step = int(a[2]) if len(a) > 2 else 1
first = int(a[3]) if len(a) > 3 else None
last = int(a[4]) if len(a) > 4 else None
encode = (len(a) <= 5) or a[5] != "noencode"
frames_root = os.path.join(WORK, f"vid_{tag}", "frames")
arm, mesh = rp.find_rig()
meta = json.loads(arm["oliver_anim"])
order, offs, total = meta["order"], meta["offsets"], meta["total"]
hands = rp.hand_info(arm)
kb = mesh.data.shape_keys
if arm.animation_data is None: arm.animation_data_create()
if kb.animation_data is None: kb.animation_data_create()
for t_ in list(arm.animation_data.nla_tracks): t_.mute = True
for t_ in list(kb.animation_data.nla_tracks): t_.mute = True
arm.animation_data.action = bpy.data.actions["Check_All"]
kb.animation_data.action = bpy.data.actions["Check_All_Keys"]

# speed: render with 2K copies of the textures (the delivered files keep their full resolution)
for im in bpy.data.images:
    if im.size[0] > 2048:
        im.scale(2048, 2048)
sc0 = bpy.context.scene
sc0.display.render_aa = "5"
# fonts
def font(sz):
    for p in ("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except Exception: pass
    return ImageFont.load_default()
F_BIG, F_MID = font(30), font(22)
JP = {"viseme_A": "あ (A)", "viseme_I": "い (I)", "viseme_U": "う (U)", "viseme_E": "え (E)", "viseme_O": "お (O)", "mouthSmile": "笑顔 (smile)", "jawOpen": "jawOpen", "mouthClose": "mouthClose"}
FNAME = {"Thumb": "Thumb", "Index": "Index", "Middle": "Middle", "Ring": "Ring", "Pinky": "Pinky"}

def lerp_state(seg, lf):
    ks = anim.SEGMENTS[seg]
    lf = min(max(lf, 0), ks[-1][0])
    for (f0, s0), (f1, s1) in zip(ks[:-1], ks[1:]):
        if f0 <= lf <= f1:
            u = 0 if f1 == f0 else (lf - f0) / (f1 - f0)
            out = {"R": {}, "L": {}, "keys": {}}
            for side in "RL":
                for k in s0[side]:
                    out[side][k] = s0[side][k] + (s1[side][k] - s0[side][k]) * u
            for k in set(s0["keys"]) | set(s1["keys"]):
                out["keys"][k] = s0["keys"].get(k, 0) + (s1["keys"].get(k, 0) - s0["keys"].get(k, 0)) * u
            return out
    return ks[-1][1]

def caption(frame):
    f = frame - 1
    seg_i = max(i for i, o in enumerate(offs) if o <= f)
    seg = order[seg_i]
    lf = f - offs[seg_i]
    st = lerp_state(seg, lf)
    title = {"Hands_OpenCloseOpen": "Hands: open -> fist -> open", "Fingers_Individual": "Fingers: bend each finger", "Point_Peace": "Index point / Peace sign",
             "Mouth_OpenClose": "Mouth: close -> open -> close", "Vowels_AIUEO": "Vowels: A I U E O", "Smile_Normal": "Smile -> normal"}[seg]
    sub = ""
    if seg == "Fingers_Individual":
        act = [(s, k) for s in "RL" for k in FNAME if st[s][k] > 0.3]
        if act:
            sub = ", ".join(f"{'Right' if s=='R' else 'Left'} {FNAME[k]}" for s, k in act)
    elif seg in ("Mouth_OpenClose", "Vowels_AIUEO", "Smile_Normal"):
        act = [(k, v) for k, v in st["keys"].items() if v > 0.05]
        sub = ", ".join(f"{JP.get(k, k)} {v:.2f}" for k, v in act)
    elif seg == "Point_Peace":
        sub = "peace" if st["R"]["spread"] > 3 else ("point" if st["R"]["Middle"] > 0.5 else "")
    return seg, title, sub

# cameras / scene
sc = viz.make_scene(640, color_type="TEXTURE", light="STUDIO")
sc.display.shading.show_cavity = False
sc.display.render_aa = "5"
sc.render.resolution_percentage = 100
cam = viz.get_camera(sc)
def hand_center(side):
    """Centre of the hand = mean of the wrist and all fingertip positions (rest pose)."""
    S = rp.SIDES[side]
    pts = [arm.pose.bones[f"{S}Hand"].head]
    for f in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        pts.append(arm.pose.bones[f"{S}Hand{f}3"].tail)
    return np.mean([np.array((arm.matrix_world @ p).to_tuple()) for p in pts], axis=0)
jaw_c = np.array((arm.matrix_world @ arm.pose.bones["Jaw"].head).to_tuple())
mouth_c = np.array([jaw_c[0], -0.11, jaw_c[2] - 0.06])
def render(cen, scale, w, h, direction=None, az=0, el=0, name="p"):
    sc.render.resolution_x, sc.render.resolution_y = w, h
    if direction is not None:
        viz.aim_dir(cam, cen, scale, direction)
    else:
        viz.aim_camera(cam, cen, scale, az, el)
    sc.render.filepath = os.path.join(tmp, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    return Image.open(sc.render.filepath).convert("RGB")

tmp = os.path.join(WORK, f"vid_{tag}_tmp_{os.getpid()}")
shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
frames_dir = frames_root; os.makedirs(frames_dir, exist_ok=True)
body_cache = {}
f0 = first or 1
f1 = last or total
t = timer()
count = 0
nR = np.array(hands["R"]["n"]); nL = np.array(hands["L"]["n"])
for fr in range(f0, f1 + 1, step):
    sc.frame_set(fr)
    seg, title, sub = caption(fr)
    if seg not in body_cache:
        body_cache[seg] = render((0, 0, 0), 2.1, 640, 720, az=0, el=0, name="body")
    body = body_cache[seg]
    if seg in ("Hands_OpenCloseOpen", "Fingers_Individual", "Point_Peace"):
        p1 = render(hand_center("R"), 0.34, 640, 360, direction=nR, name="p1")
        p2 = render(hand_center("L"), 0.34, 640, 360, direction=nL, name="p2")
        lab1, lab2 = "Right hand (palm side)", "Left hand (palm side)"
    else:
        p1 = render(mouth_c, 0.17, 640, 360, az=0, el=0, name="p1")
        p2 = render(mouth_c, 0.17, 640, 360, az=40, el=8, name="p2")
        lab1, lab2 = "Face front", "Face 3/4 view"
    im = Image.new("RGB", (1280, 720), (30, 30, 34))
    im.paste(body, (0, 0))
    im.paste(p1, (640, 0))
    im.paste(p2, (640, 360))
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, 640, 78], fill=(20, 20, 24))
    dr.text((14, 8), f"{tag.upper()}  {title}", fill=(255, 255, 255), font=F_MID)
    dr.text((14, 42), sub, fill=(255, 210, 90), font=F_BIG)
    dr.text((652, 4), lab1, fill=(255, 255, 255), font=F_MID)
    dr.text((652, 364), lab2, fill=(255, 255, 255), font=F_MID)
    im.save(os.path.join(frames_dir, f"f{fr:05d}.png"))
    count += 1
    if count % 25 == 0:
        log("rendered", count, "frames", round(t(), 1), "s")
log("render done", count, "frames in", round(t(), 1), "s")
if encode:
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(max(1, anim.FPS // step)), "-pattern_type", "glob", "-i", os.path.join(frames_dir, "f*.png"),
                    "-vf", "fps=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", out_mp4], check=True)
    log("mp4", out_mp4, os.path.getsize(out_mp4) // 1000, "kB")
shutil.rmtree(tmp, ignore_errors=True)
