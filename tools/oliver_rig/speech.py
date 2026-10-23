"""Procedural speech + body motion for the showcase animation (numpy only; no Blender needed).

A short Japanese greeting is turned into per-frame channels:
  * mouth shape keys: vowel visemes with co-articulation (every vowel pulse overlaps its neighbours and the whole signal is Gaussian-smoothed,
    so the lips start moving before the syllable), lip closure for b / m / p, a small pucker for w, tongue-tip lifts for t / d / n / r,
    a slow smile, a little amplitude variation
  * relaxed fingers (a natural curl that grows from the index to the little finger, slow drift) and open-palm gestures
  * body: breathing, weight shift, head drift, nods on stressed syllables, an open-palm gesture of the right hand, a polite bow
Every function returns plain arrays; anim.py writes them into Blender actions.
"""
import numpy as np

FPS = 24

# (kana, vowel, onset, frames, amplitude, stress)   vowel None = pause / moraic nasal; onset: b = bilabial, w, y, t = tongue tip, '' = none
#  'devoiced' morae (す in です, し) get a small amplitude
PHRASE = [
    ("こ", "o", "", 4, 1.00, 0.0), ("ん", None, "n", 5, 0.0, 0.0), ("に", "i", "t", 4, 0.9, 0.0), ("ち", "i", "t", 4, 0.9, 0.9),
    ("は", "a", "w", 6, 1.10, 0.0), ("、", None, "", 8, 0.0, 0.0),
    ("オ", "o", "", 4, 1.00, 0.0), ("リ", "i", "t", 4, 0.9, 0.0), ("バ", "a", "b", 5, 1.10, 1.0), ("ー", "a", "", 5, 0.85, 0.0),
    ("デ", "e", "t", 4, 0.95, 0.0), ("ス", "u", "t", 5, 0.35, 0.0), ("。", None, "", 12, 0.0, 0.0),
    ("よ", "o", "y", 4, 1.00, 0.0), ("ろ", "o", "t", 4, 0.95, 0.0), ("し", "i", "t", 4, 0.70, 0.9), ("く", "u", "", 4, 0.80, 0.0), ("ね", "e", "t", 7, 1.00, 0.0),
]
LEAD = 10          # silent frames before the first syllable
TAIL = 22          # and after the last one

VOWEL_AMP = {"a": 0.92, "i": 0.85, "u": 0.90, "e": 0.85, "o": 0.88}     # conversational speech does not use the full range of the keys


def pulse(f, a, b, rin, rout):
    """0 -> 1 over `rin` frames ending at a, 1 on [a, b], 1 -> 0 over `rout` frames after b (smoothstep ramps)."""
    up = np.clip((f - (a - rin)) / max(rin, 1e-6), 0, 1)
    dn = np.clip(((b + rout) - f) / max(rout, 1e-6), 0, 1)
    x = np.minimum(up, dn)
    return x * x * (3 - 2 * x)


def gauss(x, sigma):
    from scipy.ndimage import gaussian_filter1d
    return gaussian_filter1d(x, sigma, mode="nearest")


def timeline():
    """Start frame (0-based) of every mora and the total number of frames."""
    t = LEAD
    starts = []
    for m in PHRASE:
        starts.append(t)
        t += m[3]
    return starts, t + TAIL


def length():
    return timeline()[1]


def mouth_channels():
    starts, n = timeline()
    f = np.arange(n, dtype=float)
    V = {v: np.zeros(n) for v in "aiueo"}
    close = np.zeros(n)
    pucker = np.zeros(n)
    tongue = np.zeros(n)
    jaw = np.zeros(n)
    stress = []
    for k, ((kana, vow, onset, dur, amp, st), s) in enumerate(zip(PHRASE, starts)):
        e = s + dur - 1
        jit = 1.0 + 0.06 * np.sin(1.7 * k + 0.4)                          # a little amplitude variation, deterministic
        if vow is not None:
            a0 = s + (1 if onset in ("b", "w") else 0)
            V[vow] = np.maximum(V[vow], VOWEL_AMP[vow] * amp * jit * pulse(f, a0, e - 0.5, 2.2, 2.6))
        if onset == "b":
            close = np.maximum(close, pulse(f, s - 1.0, s, 1.2, 1.2))
        if onset == "w":
            pucker = np.maximum(pucker, 0.45 * pulse(f, s - 1.0, s + 0.5, 1.5, 2.0))
        if onset == "y":
            V["i"] = np.maximum(V["i"], 0.35 * pulse(f, s - 1.0, s, 1.5, 1.5))
        if onset in ("t", "n"):
            tongue = np.maximum(tongue, 0.55 * pulse(f, s - 0.5, s + 0.5, 1.5, 1.5))
        if kana == "ん":
            jaw = np.maximum(jaw, 0.14 * pulse(f, s, e, 1.5, 2.0))
            close = np.maximum(close, 0.35 * pulse(f, s, e, 1.5, 2.0))
        if st > 0:
            stress.append(s)
    # the lips close for b / m / p: duck the vowel channels around the closure
    for v in V:
        V[v] = V[v] * (1.0 - np.clip(close * 1.4, 0, 1))
    # co-articulation: smoothing in time (anticipates the next syllable, lets the jaw lag the lips)
    for v in V:
        V[v] = gauss(V[v], 1.25)
    close = gauss(close, 0.7)
    pucker = gauss(pucker, 1.0)
    tongue = gauss(tongue, 1.1)
    jaw = gauss(jaw, 1.2)
    tot = np.sum([V[v] for v in V], axis=0)
    scale = np.where(tot > 1.0, 1.0 / np.maximum(tot, 1e-6), 1.0)
    for v in V:
        V[v] = np.clip(V[v] * scale, 0, 1)
    # a slow, friendly smile on the greeting and on the closing words, never fully gone
    t = f / FPS
    smile = 0.10 + 0.22 * pulse(f, starts[0] - 4, starts[5], 10, 18) + 0.28 * pulse(f, starts[13], starts[-1] + 8, 8, 20)
    smile = gauss(smile, 2.0)
    keys = {"viseme_A": V["a"], "viseme_I": V["i"], "viseme_U": V["u"], "viseme_E": V["e"], "viseme_O": V["o"],
            "mouthClose": np.clip(close, 0, 1), "mouthPucker": np.clip(pucker, 0, 1), "tongueUp": np.clip(tongue, 0, 1),
            "jawOpen": np.clip(jaw, 0, 1), "mouthSmile": np.clip(smile, 0, 1)}
    return keys, stress, starts


def hand_channels(n, starts):
    """Finger curl amounts (0 open .. 1 fist) per side / finger and the spread of the fingers (degrees)."""
    f = np.arange(n, dtype=float)
    t = f / FPS
    base = {"Thumb": 0.12, "Index": 0.13, "Middle": 0.18, "Ring": 0.24, "Pinky": 0.30}      # relaxed hand: curl grows towards the little finger
    out = {}
    g_right = pulse(f, starts[0] - 2, starts[5], 12, 14)        # open-palm gesture of the right hand while saying the greeting
    g_left = pulse(f, starts[13], starts[-1] + 6, 10, 16)       # and of the left hand while saying the closing words
    for side, g, ph in (("R", g_right, 0.0), ("L", g_left, 1.9)):
        for i, (fn, b) in enumerate(base.items()):
            drift = 0.035 * np.sin(2 * np.pi * t / (4.3 + 0.7 * i) + ph + i) + 0.02 * np.sin(2 * np.pi * t / (1.9 + 0.3 * i) + 2 * i + ph)
            open_amt = 0.04 + 0.03 * i
            amt = (b + drift) * (1 - g) + open_amt * g
            out[(side, fn)] = np.clip(amt, 0, 1)
        out[(side, "spread")] = 5.0 * g
    return out


def body_channels(n, starts, stress):
    """Rotation (degrees about the world x / y / z axes, applied to the bone in its rest frame) per body bone, per frame.
    +x = bend forward / nod down, +z = turn towards the character's left, y = lean sideways."""
    f = np.arange(n, dtype=float)
    t = f / FPS
    z = lambda: np.zeros((n, 3))
    R = {k: z() for k in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
                           "LeftForeArm", "RightForeArm", "LeftHand", "RightHand")}
    breath = np.sin(2 * np.pi * t / 3.9 - 0.6)
    R["Spine"][:, 0] += -0.25 * breath
    R["Spine1"][:, 0] += -0.55 * breath
    R["Spine2"][:, 0] += -0.80 * breath
    R["LeftShoulder"][:, 1] += -0.45 * breath
    R["RightShoulder"][:, 1] += 0.45 * breath
    sway = np.sin(2 * np.pi * t / 6.3)
    R["Hips"][:, 1] += 0.7 * sway
    R["Hips"][:, 2] += 0.5 * np.sin(2 * np.pi * t / 8.1 + 0.9)
    R["Spine"][:, 1] += -0.35 * sway
    R["Spine1"][:, 1] += -0.25 * sway
    R["Spine2"][:, 1] += -0.20 * sway
    R["LeftArm"][:, 0] += 0.5 * np.sin(2 * np.pi * t / 5.2 + 0.4)
    R["RightArm"][:, 0] += 0.5 * np.sin(2 * np.pi * t / 5.2 + 1.9)
    # head: slow drift + glances, nods on stressed syllables
    head_yaw = 2.2 * np.sin(2 * np.pi * t / 7.1 + 0.7) + 0.9 * np.sin(2 * np.pi * t / 2.9 + 1.3)
    head_roll = 1.1 * np.sin(2 * np.pi * t / 5.6 + 2.1)
    head_pitch = 0.8 * np.sin(2 * np.pi * t / 4.7 + 0.2)
    nod = np.zeros(n)
    for s in stress:
        nod += pulse(f, s - 2, s + 1, 4, 6)
    head_pitch = head_pitch + 3.2 * nod
    R["Head"][:, 2] += 0.65 * head_yaw
    R["Neck"][:, 2] += 0.35 * head_yaw
    R["Head"][:, 1] += 0.65 * head_roll
    R["Neck"][:, 1] += 0.35 * head_roll
    R["Head"][:, 0] += 0.6 * head_pitch
    R["Neck"][:, 0] += 0.4 * head_pitch
    # polite bow on "yoroshiku" (the three morae after the closing pause)
    bow = pulse(f, starts[14] - 1, starts[16], 9, 14)
    for b, a in (("Spine", 4.0), ("Spine1", 4.0), ("Spine2", 3.0), ("Neck", 3.0), ("Head", 4.0)):
        R[b][:, 0] += a * bow
    # right hand: open-palm gesture while greeting (forearm up and forward, palm turned up)
    gR = pulse(f, starts[0] - 2, starts[5], 12, 14)
    gL = pulse(f, starts[13], starts[-1] + 6, 10, 16)
    R["RightArm"][:, 0] += -9.0 * gR
    R["RightForeArm"][:, 0] += -48.0 * gR
    R["RightHand"][:, 0] += -8.0 * gR + 3.0 * gR * np.sin(2 * np.pi * t / 1.6)
    R["LeftArm"][:, 0] += -6.0 * gL
    R["LeftForeArm"][:, 0] += -32.0 * gL
    R["LeftHand"][:, 0] += -6.0 * gL
    return R, gR, gL


def build():
    """Everything the writer needs: n, mouth keys, hand channels, body rotations, roll (forearm twist) per side."""
    keys, stress, starts = mouth_channels()
    n = len(next(iter(keys.values())))
    hands = hand_channels(n, starts)
    body, gR, gL = body_channels(n, starts, stress)
    roll = {"R": 28.0 * gR, "L": 18.0 * gL}         # palm turned up: twist about the forearm axis (degrees)
    # everything that is not speech fades in from / out to the neutral A-pose, so that the segment starts and ends exactly in the rest pose
    f = np.arange(n, dtype=float)
    env = pulse(f, 14, n - 18, 12, 14)
    for b in body:
        body[b] = body[b] * env[:, None]
    for k in hands:
        hands[k] = hands[k] * env
    for k in roll:
        roll[k] = roll[k] * env
    keys["mouthSmile"] = keys["mouthSmile"] * env
    return dict(n=n, keys=keys, hands=hands, body=body, roll=roll, stress=stress, starts=starts)
