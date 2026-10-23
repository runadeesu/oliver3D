"""Mouth shape keys as per-vertex deltas on the assembled mouth mesh: jawOpen, mouthClose, viseme_A/I/U/E/O, mouthSmile (the original eight)
plus finer controls (left / right smile, frown and stretch, pucker, funnel, mouth shift, upper-lip raise, lower-lip drop, jaw forward / sideways,
cheek puff, tongue out / up) for natural, speech-like mouth motion. Left / Right are the character's own sides (+x = left)."""
from common import *
import mouth_build as mb
from mouth_build import smoothstep, PART_SKIN, PART_UP_WALL, PART_LO_WALL, PART_UP_TEETH, PART_LO_TEETH, PART_TONGUE, PART_BACK

JAW_MAX_DEG = 13.0
BASE_KEYS = ["jawOpen", "mouthClose", "viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O", "mouthSmile"]
EXTRA_KEYS = ["mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthStretchLeft", "mouthStretchRight",
              "mouthPucker", "mouthFunnel", "mouthLeft", "mouthRight", "mouthUpperUpLeft", "mouthUpperUpRight",
              "mouthLowerDownLeft", "mouthLowerDownRight", "jawForward", "jawLeft", "jawRight", "cheekPuff", "tongueOut", "tongueUp"]
KEY_NAMES = BASE_KEYS + EXTRA_KEYS
UP_FOLLOW = 0.0022           # the upper lip rises with the opening jaw (m at full opening)

# viseme / expression recipes (metres, jaw as a fraction of the maximum opening)
#   corner_out : corners move sideways (+ = widen)       corner_up : corners move up
#   pucker     : lateral squeeze of the lip region        protrude  : lips pushed forward
#   up_lift    : upper lip raised                         lo_drop  : lower lip lowered in addition to the jaw
#   cheek_up   : cheek raised (smile)                     press    : lips pressed together (close)
RECIPES = {
    "viseme_A": dict(jaw=0.80, corner_out=0.0030, corner_up=0.0000, pucker=0.00, protrude=0.0000, up_lift=0.0015, lo_drop=0.0000, cheek_up=0.0000),
    "viseme_I": dict(jaw=0.22, corner_out=0.0085, corner_up=0.0015, pucker=0.00, protrude=0.0000, up_lift=0.0010, lo_drop=0.0000, cheek_up=0.0012),
    "viseme_U": dict(jaw=0.30, corner_out=-0.0060, corner_up=0.0000, pucker=0.24, protrude=0.0065, up_lift=0.0000, lo_drop=0.0000, cheek_up=0.0000),
    "viseme_E": dict(jaw=0.45, corner_out=0.0055, corner_up=0.0005, pucker=0.00, protrude=0.0000, up_lift=0.0015, lo_drop=0.0000, cheek_up=0.0006),
    "viseme_O": dict(jaw=0.55, corner_out=-0.0045, corner_up=0.0000, pucker=0.14, protrude=0.0045, up_lift=0.0010, lo_drop=0.0000, cheek_up=0.0000),
    "mouthSmile": dict(jaw=0.00, corner_out=0.0060, corner_up=0.0070, pucker=0.00, protrude=0.0000, up_lift=0.0010, lo_drop=0.0000, cheek_up=0.0022),
    "mouthPucker": dict(jaw=0.00, corner_out=-0.0070, corner_up=0.0000, pucker=0.30, protrude=0.0080, up_lift=0.0000, lo_drop=0.0000, cheek_up=0.0000),
    "mouthFunnel": dict(jaw=0.30, corner_out=-0.0040, corner_up=0.0000, pucker=0.16, protrude=0.0070, up_lift=0.0020, lo_drop=0.0020, cheek_up=0.0000),
}
# one-sided recipes: side = +1 (character's left, +x) / -1 (right). corner_out / corner_up act on that side's corner only
SIDE_RECIPES = {
    "mouthSmile": dict(corner_out=0.0060, corner_up=0.0070, cheek_up=0.0022, up_lift=0.0010),
    "mouthFrown": dict(corner_out=-0.0010, corner_up=-0.0055, cheek_up=-0.0006, up_lift=0.0),
    "mouthStretch": dict(corner_out=0.0078, corner_up=-0.0012, cheek_up=0.0, up_lift=0.0),
}


class MouthFields:
    """Per-vertex falloff fields around the mouth (computed once for the assembled mesh)."""

    def __init__(self, asm):
        co = asm["co"].astype(np.float64)
        self.co = co
        self.asm = asm
        fr = asm["frame"]
        pk = asm["pocket"]
        self.xm, self.hw = pk["xm"], pk["hw"]
        self.yc = asm["y_center"]
        self.z0 = fr.z0
        part = asm["part"]
        self.part = part
        up, lo = asm["upper"], asm["lower"]
        P = co[up]
        self.cl = P[0]       # left corner (min x)
        self.cr = P[-1]
        x, y, z = co[:, 0], co[:, 1], co[:, 2]
        dx = x - self.xm
        dz = z - fr.zc(x)
        dz = np.where(np.abs(dz) < 3e-5, 3e-5, dz)
        self.dz = dz
        front = 1 - smoothstep(self.yc + 0.035, self.yc + 0.075, y)       # skin only on the face front
        skin_like = (part == PART_SKIN)
        face = np.where(skin_like, front, 1.0)
        # elliptical lip region (fades out ~1.6 half-widths sideways, ~3.5 cm vertically)
        r = np.sqrt((dx / (self.hw + 0.016)) ** 2 + (dz / 0.030) ** 2)
        self.m_lip = (1 - smoothstep(0.55, 1.25, r)) * face
        # tighter core for the protrusion / pucker
        r2 = np.sqrt((dx / (self.hw + 0.008)) ** 2 + (dz / 0.016) ** 2)
        self.m_core = (1 - smoothstep(0.45, 1.15, r2)) * face
        self.m_up = self.m_lip * (dz > 0) * (1 - smoothstep(0.004, 0.016, dz))
        self.lens = mb.lens_profile(dx / self.hw)
        self.side_l = smoothstep(-0.014, 0.014, dx)          # 1 on the character's left (+x) half, 0 on the right half (wide, soft blend: no ridge at the centre line)
        self.m_lo_band = (dz < 0) * (1 - smoothstep(0.002, 0.009, -dz)) * self.m_lip
        # corner blobs
        dl = np.sqrt((x - self.cl[0]) ** 2 + (z - self.cl[2]) ** 2 + ((y - self.cl[1]) * 0.6) ** 2)
        dr_ = np.sqrt((x - self.cr[0]) ** 2 + (z - self.cr[2]) ** 2 + ((y - self.cr[1]) * 0.6) ** 2)
        sig = 0.013
        self.m_cl = np.exp(-(dl / sig) ** 2) * face
        self.m_cr = np.exp(-(dr_ / sig) ** 2) * face
        # cheeks (smile)
        cheek_sig = 0.022
        cl_c = np.array([self.cl[0] - 0.010, self.cl[1] + 0.004, self.z0 + 0.012])
        cr_c = np.array([self.cr[0] + 0.010, self.cr[1] + 0.004, self.z0 + 0.012])
        dcl = np.linalg.norm((co - cl_c) * np.array([1, 0.7, 1]), axis=1)
        dcr = np.linalg.norm((co - cr_c) * np.array([1, 0.7, 1]), axis=1)
        self.m_cheek_l = np.exp(-(dcl / cheek_sig) ** 2) * face * skin_like
        self.m_cheek_r = np.exp(-(dcr / cheek_sig) ** 2) * face * skin_like
        # rigid-ish parts follow the lip fields with weight 1 (pocket) or not at all (teeth)
        self.w_jaw = mb.jaw_weights(asm)
        self.pivot = mb.jaw_pivot(fr, self.yc)
        # parts that must not be moved by lip fields: teeth & tongue (they follow only the jaw), hair-like far geometry (fields are local anyway)
        self.free = np.isin(part, [PART_UP_TEETH, PART_LO_TEETH, PART_TONGUE])


def jaw_rotation_delta(F, frac):
    return mb.rotate_jaw(F.co, F.w_jaw, F.pivot, JAW_MAX_DEG * frac) - F.co


def jaw_delta(F, frac):
    """Jaw rotation + the small rise of the upper lip that goes with an opening mouth (lens profile along the width)."""
    d = jaw_rotation_delta(F, frac)
    free = ~F.free
    d[:, 2] += UP_FOLLOW * frac * F.m_up * F.lens * free
    return d


def lip_delta(F, r):
    """Lip / corner / cheek displacement of a recipe (no jaw)."""
    co = F.co
    d = np.zeros_like(co)
    free = ~F.free
    # corners: left corner moves to -x when widening, right corner to +x
    d[:, 0] += -r["corner_out"] * F.m_cl + r["corner_out"] * F.m_cr
    d[:, 2] += r["corner_up"] * (F.m_cl + F.m_cr)
    # lateral squeeze (pucker) of the lip region towards the mouth centre line
    d[:, 0] += -r["pucker"] * (co[:, 0] - F.xm) * F.m_core
    # protrusion: lips pushed forward (-y), the whole core region (more at the lips than outside)
    d[:, 1] += -r["protrude"] * F.m_core
    # upper lip lift
    d[:, 2] += r["up_lift"] * F.m_up
    # lower lip extra drop (on top of the jaw)
    d[:, 2] += -r["lo_drop"] * F.m_lo_band
    # cheeks
    d[:, 2] += r["cheek_up"] * (F.m_cheek_l + F.m_cheek_r)
    d[:, 0] += -0.5 * r["cheek_up"] * F.m_cheek_l + 0.5 * r["cheek_up"] * F.m_cheek_r
    d[~free] = 0
    return d


def side_delta(F, side, r):
    """One-sided corner / cheek motion. side = +1: the character's left (+x) corner and cheek, -1: the right one."""
    co = F.co
    d = np.zeros_like(co)
    free = ~F.free
    mc = F.m_cr if side > 0 else F.m_cl
    mch = F.m_cheek_r if side > 0 else F.m_cheek_l
    d[:, 0] += side * r["corner_out"] * mc
    d[:, 2] += r["corner_up"] * mc
    d[:, 2] += r["up_lift"] * F.m_up * (F.side_l if side > 0 else 1 - F.side_l) * mc.clip(0, 1) ** 0.5
    d[:, 2] += r["cheek_up"] * mch
    d[:, 0] += side * 0.5 * r["cheek_up"] * mch
    d[~free] = 0
    return d


def build_keys(F):
    """Returns dict name -> delta (N,3) float32 relative to the basis."""
    keys = {}
    keys["jawOpen"] = jaw_delta(F, 1.0)
    pk = F.asm["pocket"]
    k_mid = min(3, pk["ids_up"].shape[1] - 1)
    ids_mid = pk["ids_up"][:, k_mid]
    for name, r in RECIPES.items():
        d = jaw_delta(F, r["jaw"]) + lip_delta(F, r)
        # narrowing visemes (U, O): the teeth / tongue follow the narrowed cavity sideways, otherwise the outermost teeth poke out of the corners
        x0 = F.co[ids_mid, 0]
        x1 = x0 + d[ids_mid, 0]
        s = (x1.max() - x1.min()) / (x0.max() - x0.min())
        if s < 1.0:
            d[F.free, 0] += (s - 1.0) * (F.co[F.free, 0] - F.xm)
        keys[name] = d
    # mouthClose: press the lips together; lifts the lower lip band by a small amount so that a slightly open jaw
    # (jawOpen <= ~0.12) is sealed, otherwise the lips are just pressed (lower lip forward by 0.4 mm so there is no z-fight)
    d = np.zeros_like(F.co)
    lift = jaw_rotation_delta(F, 0.12)
    band = F.m_lo_band.copy()
    band[F.part == PART_LO_WALL] = 1.0
    d[:, 2] += (-lift[:, 2] + 0.0002 + 0.0004 * F.lens) * band * (F.part != PART_TONGUE) * (F.part != PART_LO_TEETH)       # seal margin tapers towards the corners (no crossing lips there)
    d[:, 1] += (-lift[:, 1] - 0.0004) * band * (F.part != PART_TONGUE) * (F.part != PART_LO_TEETH)
    d[:, 2] += -(0.0001 + 0.0003 * F.lens) * F.m_up
    d[:, 0] += 0.04 * -(F.co[:, 0] - F.xm) * F.m_core * 0.2        # slight lateral tightening
    d[F.free] = 0
    keys["mouthClose"] = d
    # ---- one-sided corner keys
    for base, r in SIDE_RECIPES.items():
        keys[base + "Left"] = side_delta(F, +1, r)
        keys[base + "Right"] = side_delta(F, -1, r)
    # ---- whole mouth shifted sideways (skin, lips and the cavity walls; the teeth stay with the jaw)
    for nm, sg in (("mouthLeft", 1), ("mouthRight", -1)):
        d = np.zeros_like(F.co)
        d[:, 0] = sg * 0.0055 * F.m_core
        d[F.free, 0] = sg * 0.0050          # teeth and tongue travel with the mouth, otherwise the outer teeth poke out of the lips
        keys[nm] = d
    # ---- single upper lip raise / lower lip drop (snarl, half smile)
    for nm, sg in (("mouthUpperUpLeft", 1), ("mouthUpperUpRight", -1)):
        sd = F.side_l if sg > 0 else 1 - F.side_l
        d = np.zeros_like(F.co)
        d[:, 2] = 0.0030 * F.m_up * sd * F.lens ** 0.5
        d[F.free] = 0
        keys[nm] = d
    for nm, sg in (("mouthLowerDownLeft", 1), ("mouthLowerDownRight", -1)):
        sd = F.side_l if sg > 0 else 1 - F.side_l
        d = np.zeros_like(F.co)
        d[:, 2] = -0.0030 * F.m_lo_band * sd * F.lens ** 0.5
        d[F.free] = 0
        keys[nm] = d
    # ---- jaw translations (forward / sideways), same weights as the rotation
    for nm, vec in (("jawForward", (0.0, -0.0065, 0.0)), ("jawLeft", (0.0075, 0.0, 0.0)), ("jawRight", (-0.0075, 0.0, 0.0))):
        keys[nm] = F.w_jaw[:, None] * np.array(vec)[None, :]
    # ---- cheek puff
    d = np.zeros_like(F.co)
    d[:, 0] += 0.0068 * F.m_cheek_r - 0.0068 * F.m_cheek_l
    d[:, 1] += -0.0035 * (F.m_cheek_r + F.m_cheek_l)
    d[:, 2] += 0.0010 * (F.m_cheek_r + F.m_cheek_l)
    d[F.part != PART_SKIN] = 0
    keys["cheekPuff"] = d
    # ---- tongue (a rigid part that follows the jaw; these keys move it inside the open mouth)
    tg = F.part == PART_TONGUE
    d_out = np.zeros_like(F.co)
    d_up = np.zeros_like(F.co)
    if tg.any():
        y = F.co[tg, 1]
        t = (y - y.min()) / max(y.max() - y.min(), 1e-6)       # 0 at the tip .. 1 at the root
        d_out[tg, 1] = -0.024 * (1.0 - 0.55 * t)
        d_out[tg, 2] = 0.0100 * (1.0 - 0.6 * t)          # lifted so that the tip comes out over the lower lip when the jaw is open (jawOpen >= 0.7)
        d_up[tg, 2] = 0.0075 * (1.0 - t) ** 1.3 + 0.0010
        d_up[tg, 1] = -0.0030 * (1.0 - t)
    keys["tongueOut"] = d_out
    keys["tongueUp"] = d_up
    out = {}
    for k, v in keys.items():
        v = v.astype(np.float32)
        v[np.linalg.norm(v, axis=1) < 3e-6] = 0.0          # drop the invisible tails of the falloff fields (keeps the exported morph targets sparse)
        out[k] = v
    return out
