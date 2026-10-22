"""Mouth shape keys (jawOpen, mouthClose, viseme_A/I/U/E/O, mouthSmile) as per-vertex deltas on the assembled mouth mesh."""
from common import *
import mouth_build as mb
from mouth_build import smoothstep, PART_SKIN, PART_UP_WALL, PART_LO_WALL, PART_UP_TEETH, PART_LO_TEETH, PART_TONGUE, PART_BACK

JAW_MAX_DEG = 13.0
KEY_NAMES = ["jawOpen", "mouthClose", "viseme_A", "viseme_I", "viseme_U", "viseme_E", "viseme_O", "mouthSmile"]

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


def jaw_delta(F, frac):
    return mb.rotate_jaw(F.co, F.w_jaw, F.pivot, JAW_MAX_DEG * frac) - F.co


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
    lift = jaw_delta(F, 0.12)
    band = F.m_lo_band.copy()
    band[F.part == PART_LO_WALL] = 1.0
    d[:, 2] += (-lift[:, 2] + 0.0006) * band * (F.part != PART_TONGUE) * (F.part != PART_LO_TEETH)
    d[:, 1] += (-lift[:, 1] - 0.0004) * band * (F.part != PART_TONGUE) * (F.part != PART_LO_TEETH)
    d[:, 2] += -0.0004 * F.m_up
    d[:, 0] += 0.04 * -(F.co[:, 0] - F.xm) * F.m_core * 0.2        # slight lateral tightening
    d[F.free] = 0
    keys["mouthClose"] = d
    return {k: v.astype(np.float32) for k, v in keys.items()}
