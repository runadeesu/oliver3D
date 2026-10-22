"""Landmark estimation + skeleton definition (Mixamo-style bone names + Jaw)."""
from common import *


def slice_centroid(co, z, dz=0.012, xmin=-9, xmax=9, ymin=-9, ymax=9, mask=None):
    m = (np.abs(co[:, 2] - z) < dz) & (co[:, 0] > xmin) & (co[:, 0] < xmax) & (co[:, 1] > ymin) & (co[:, 1] < ymax)
    if mask is not None:
        m &= mask
    if m.sum() < 20:
        return None
    return co[m].mean(0), m.sum()


def estimate_landmarks(co, frame, y_center, hands, cfg):
    """frame: MouthFrame, y_center: mouth surface y, hands: {'L': hand_analysis, 'R': ...}. Returns dict name->xyz."""
    zf, zt = float(co[:, 2].min()), float(co[:, 2].max())
    H = zt - zf
    sk = cfg.get("skeleton", {})
    z0 = frame.z0
    LM = {}
    # ---- head / neck (from the mouth landmarks)
    LM["head_pivot"] = np.array([frame.cx, y_center + 0.085, z0 - 0.030])
    LM["neck_base"] = np.array([frame.cx, y_center + 0.090, z0 - 0.100])
    LM["head_top"] = np.array([frame.cx, y_center + 0.080, zt - 0.005])
    LM["jaw_pivot"] = np.array([frame.cx, y_center + 0.095, z0 + 0.060])
    LM["chin"] = np.array([frame.cx, y_center + 0.012, z0 - 0.047])
    # ---- torso: median y of the core in several z slices
    def ycore(z):
        m = (np.abs(co[:, 2] - z) < 0.02) & (np.abs(co[:, 0]) < 0.10) & (co[:, 1] > -0.12) & (co[:, 1] < 0.12)
        return float(np.median(co[m, 1])) if m.sum() > 50 else 0.0
    z_hip = zf + sk.get("hip_frac", 0.525) * H
    z_sh = sk.get("shoulder_z", z0 - 0.115)
    y_hip, y_sh = ycore(z_hip + 0.06), ycore(z_sh)
    LM["neck_base"][1] = y_sh + 0.02
    z_sp = z_hip + 0.14
    z_sp1 = z_sp + 0.5 * (z_sh - z_sp)
    z_sp2 = z_sh - 0.04
    lerp_y = lambda z: y_hip + (y_sh - y_hip) * (z - (z_hip + 0.055)) / (z_sh - (z_hip + 0.055))
    LM["hips"] = np.array([0.0, y_hip, z_hip + 0.055])
    LM["spine"] = np.array([0.0, lerp_y(z_sp), z_sp])
    LM["spine1"] = np.array([0.0, lerp_y(z_sp1), z_sp1])
    LM["spine2"] = np.array([0.0, lerp_y(z_sp2), z_sp2])
    # ---- legs: hip joint, knee, ankle (x from slice centroids of each side)
    leg = {}
    for side, sgn in (("L", 1), ("R", -1)):
        hx = sk.get("hip_x", 0.088) * sgn
        zk = zf + sk.get("knee_frac", 0.285) * H
        za = zf + sk.get("ankle_frac", 0.045) * H
        ck = slice_centroid(co, zk, 0.02, 0.02 * sgn if sgn > 0 else -9, 9 if sgn > 0 else -0.02, -0.3, 0.3)
        ca = slice_centroid(co, za, 0.02, 0.02 * sgn if sgn > 0 else -9, 9 if sgn > 0 else -0.02, -0.3, 0.3)
        # slice centroids of clothed legs can be biased by outward-flared trousers: blend with anatomical x
        kx = 0.6 * hx + 0.4 * (ck[0][0] if ck else hx)
        ax = 0.5 * hx + 0.5 * (ca[0][0] if ca else hx)
        leg[side] = dict(hip=np.array([hx, ycore(z_hip), z_hip]),
                         knee=np.array([kx, ycore(zk) + 0.012, zk]),
                         ankle=np.array([ax, ycore(za) + 0.0, za]),
                         toe=np.array([ax, ycore(za) - 0.085, zf + 0.018]))
    LM["legs"] = leg
    # ---- arms: shoulder joint from proportion + wrist from hand analysis
    arm = {}
    for side, sgn in (("L", 1), ("R", -1)):
        W = hands[side]["W"]
        sx = sk.get("shoulder_x", 0.19) * sgn
        sh = np.array([sx, ycore(z_sh), z_sh])
        clav = np.array([0.05 * sgn, ycore(z_sh) + 0.01, z_sh + 0.01])
        wrist = np.asarray(W, float)
        v = wrist - sh
        elbow = sh + v * sk.get("elbow_frac", 0.48) + np.array([0, 0.012, 0])
        arm[side] = dict(clav=clav, shoulder=sh, elbow=elbow, wrist=wrist)
    LM["arms"] = arm
    LM["zf"], LM["zt"], LM["H"] = zf, zt, H
    return LM


FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


def build_bone_list(LM, hands_json, side_names=(("L", "Left"), ("R", "Right"))):
    """Returns list of dicts: name, head, tail, parent, group, roll (vector for align_roll or None)."""
    B = []

    def add(name, head, tail, parent, group, roll=None, seed=0.06, sigma=0.05):
        B.append(dict(name=name, head=np.asarray(head, float), tail=np.asarray(tail, float), parent=parent, group=group, roll=roll, seed=seed, sigma=sigma))
    add("Hips", LM["hips"], LM["spine"], None, "torso", seed=0.14, sigma=0.08)
    add("Spine", LM["spine"], LM["spine1"], "Hips", "torso", seed=0.14, sigma=0.08)
    add("Spine1", LM["spine1"], LM["spine2"], "Spine", "torso", seed=0.14, sigma=0.08)
    add("Spine2", LM["spine2"], LM["neck_base"], "Spine1", "torso", seed=0.14, sigma=0.08)
    add("Neck", LM["neck_base"], LM["head_pivot"], "Spine2", "head", seed=0.045, sigma=0.04)
    add("Head", LM["head_pivot"], LM["head_top"], "Neck", "head", seed=0.15, sigma=0.06)
    add("Jaw", LM["jaw_pivot"], LM["chin"], "Head", "jaw", seed=0.02, sigma=0.02)
    for s, Side in side_names:
        sgn = 1 if s == "L" else -1
        a = LM["arms"][s]
        l = LM["legs"][s]
        h = hands_json[s]
        n_palm = np.array(h["n"])
        add(f"{Side}Shoulder", a["clav"], a["shoulder"], "Spine2", "arm", seed=0.05, sigma=0.045)
        add(f"{Side}Arm", a["shoulder"], a["elbow"], f"{Side}Shoulder", "arm", seed=0.055, sigma=0.05)
        add(f"{Side}ForeArm", a["elbow"], a["wrist"], f"{Side}Arm", "arm", seed=0.05, sigma=0.05)
        mids = np.mean([np.array(d["joints"][0]) for d in h["digits"].values()], axis=0)
        add(f"{Side}Hand", a["wrist"], mids, f"{Side}ForeArm", "hand", roll=n_palm, seed=0.035, sigma=0.03)
        for fname, d in h["digits"].items():
            Jn = np.array(d["joints"])
            nm = fname.capitalize()
            for k in range(3):
                add(f"{Side}Hand{nm}{k+1}", Jn[k], Jn[k + 1], f"{Side}Hand" if k == 0 else f"{Side}Hand{nm}{k}", "finger", roll=n_palm, seed=0.0075, sigma=0.0065)
        th = h["thumb"]
        T = np.array(th["tip"]); dth = np.array(th["dir"])
        Lt = 0.64 * h["Lh"]
        cmc, mcp, ip = T - dth * Lt, T - dth * Lt * 0.52, T - dth * Lt * 0.26
        add(f"{Side}HandThumb1", cmc, mcp, f"{Side}Hand", "finger", roll=n_palm, seed=0.009, sigma=0.008)
        add(f"{Side}HandThumb2", mcp, ip, f"{Side}HandThumb1", "finger", roll=n_palm, seed=0.009, sigma=0.0075)
        add(f"{Side}HandThumb3", ip, T, f"{Side}HandThumb2", "finger", roll=n_palm, seed=0.009, sigma=0.0065)
        add(f"{Side}UpLeg", l["hip"], l["knee"], "Hips", "leg", seed=0.14, sigma=0.08)
        add(f"{Side}Leg", l["knee"], l["ankle"], f"{Side}UpLeg", "leg", seed=0.14, sigma=0.08)
        add(f"{Side}Foot", l["ankle"], l["toe"], f"{Side}Leg", "leg", seed=0.09, sigma=0.05)
        toe_end = l["toe"] + np.array([0, -0.06, 0])
        add(f"{Side}ToeBase", l["toe"], toe_end, f"{Side}Foot", "leg", seed=0.04, sigma=0.03)
    return B
