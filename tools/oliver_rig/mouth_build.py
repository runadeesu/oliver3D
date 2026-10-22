"""Mouth construction: lip slit, oral pocket, teeth, tongue (numpy arrays)."""
from common import *
from mathutils.bvhtree import BVHTree
import mouth_cut


class MouthFrame:
    """Lip crease curve z_c(x) from the config + helpers (all in metres)."""
    def __init__(self, cfg):
        m = cfg["mouth"]
        self.cx = m["cx_mm"] / 1000.0
        self.xl = m["xl_mm"] / 1000.0
        self.xr = m["xr_mm"] / 1000.0
        self.p4 = np.array(m["poly4_mm"], float)

    def zc(self, x):
        return np.polyval(self.p4, np.asarray(x) * 1000.0) / 1000.0

    @property
    def z0(self):
        return float(self.zc(self.cx))


def face_bvh(co, faces, frame, margin=0.12):
    near = (np.abs(co[:, 0] - frame.cx) < margin) & (np.abs(co[:, 2] - frame.z0) < margin) & (co[:, 1] < 0.0)
    fm = near[faces].all(1)
    return BVHTree.FromPolygons([tuple(map(float, v)) for v in co], [tuple(map(int, f)) for f in faces[fm]], epsilon=0.0)


def surface_y(bvh, x, z):
    h = bvh.ray_cast(Vector((float(x), -0.5, float(z))), Vector((0, 1, 0)))
    return h[0].y if h[0] is not None else np.nan


def cut_lips(co, faces, uv, frame, y_back=0.02):
    """Split the face mesh along the lip crease. Returns dict (co, faces, uv, upper, lower)."""
    bvh = face_bvh(co, faces, frame)
    yc = surface_y(bvh, frame.cx, frame.z0)
    d = (co[:, 2] - frame.zc(co[:, 0])).astype(np.float64)
    # restrict to the neighbourhood of the mouth so that the cut surface doesn't touch other geometry
    region = (np.abs(co[:, 0] - frame.cx) < 0.06) & (np.abs(co[:, 2] - frame.z0) < 0.02) & (co[:, 1] < yc + y_back)
    # vertices lying (almost) exactly on the crease would stay shared between upper and lower faces -> treat them as
    # being slightly above the curve so that the cut always separates them from the faces below
    d = np.where(np.abs(d) < 3e-5, 3e-5, d)
    d = np.where(region, d, np.where(d > 0, 1.0, -1.0))   # outside the region: constant sign -> never cut

    def edge_ok(u, v, t):
        p = co[u] + (co[v] - co[u]) * t
        return frame.xl <= p[0] <= frame.xr and region[u] and region[v]

    res = mouth_cut.split_along_surface(co, faces, uv, d, edge_ok)
    # keep the longest chain only (in case other geometry was crossed)
    nb = res["nb"]
    seen, comps = set(), []
    for v in nb:
        if v in seen:
            continue
        stack, comp = [v], []
        while stack:
            a = stack.pop()
            if a in seen:
                continue
            seen.add(a)
            comp.append(a)
            stack += nb[a]
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    log("lip cut: chain components", [len(c) for c in comps][:5])
    main = set(comps[0])
    res["nb"] = {k: [n for n in v if n in main] for k, v in nb.items() if k in main}
    res["ends"] = [e for e in res["ends"] if e in main]
    out = mouth_cut.open_slit(res)
    out["y_center"] = yc
    out["bvh"] = bvh
    return out


# ----------------------------------------------------------------------------
# oral pocket
# ----------------------------------------------------------------------------
POCKET_D = np.array([0.0, 0.0006, 0.0015, 0.0030, 0.0055, 0.0085, 0.012, 0.0165, 0.023, 0.032, 0.042])     # depth behind the lip rim
POCKET_H = np.array([0.0, 0.0006, 0.0014, 0.0024, 0.0042, 0.0066, 0.0090, 0.0110, 0.0130, 0.0160, 0.0185])  # half height (wall distance from the slit plane)
BACK_D = 0.054
LIP_ROWS = 4        # rows 0..LIP_ROWS use the skin material (rounded inner lip band), deeper rows use the mouth-inside material


def local_uv_fit(co, faces, uv, verts, side_sign, frame, zr=0.007):
    """Fit uv = A*(x,z)+b on corners of faces touching `verts` on one side of the crease (for the lip band UVs)."""
    fm = np.isin(faces, verts).any(1)
    pts, uvs = [], []
    for fi in np.where(fm)[0]:
        for k in range(3):
            v = faces[fi, k]
            p = co[v]
            dz = p[2] - frame.zc(p[0])
            if side_sign * dz >= -1e-6 and abs(dz) < zr:
                pts.append([p[0], p[2], 1.0])
                uvs.append(uv[fi, k])
    pts, uvs = np.array(pts), np.array(uvs)
    sol, *_ = np.linalg.lstsq(pts, uvs, rcond=None)      # (3,2)
    return sol


def build_pocket(cut, frame):
    co, faces, uv = cut["co"], cut["faces"], cut["uv"]
    up, lo = cut["upper"], cut["lower"]
    n1 = len(up)
    P = co[up].astype(np.float64)                      # chain positions (closed state)
    xm = 0.5 * (P[:, 0].min() + P[:, 0].max())
    hw = 0.5 * (P[:, 0].max() - P[:, 0].min())
    u = np.clip((P[:, 0] - xm) / hw, -1, 1)
    hs = np.sqrt(np.clip(1 - u ** 2, 0, 1)) ** 0.8
    hs[0] = hs[-1] = 0.0
    K = len(POCKET_D) - 1
    newco, newuv_pts = [], []
    ids_up = np.full((n1, K + 1), -1, np.int64)
    ids_lo = np.full((n1, K + 1), -1, np.int64)
    ids_up[:, 0], ids_lo[:, 0] = up, lo
    base = len(co)
    cnt = 0
    verts = []
    meta = []   # (side, i, k)
    xscale = lambda k: 1.0 - 0.30 * (POCKET_D[k] / POCKET_D[-1])
    for k in range(1, K + 1):
        for i in range(n1):
            x = xm + (P[i, 0] - xm) * xscale(k)
            y = P[i, 1] + POCKET_D[k]
            z_u = P[i, 2] + POCKET_H[k] * hs[i]
            z_l = P[i, 2] - POCKET_H[k] * hs[i]
            verts.append((x, y, z_u)); meta.append((1, i, k)); ids_up[i, k] = base + cnt; cnt += 1
            if i in (0, n1 - 1):                     # corners: upper and lower pocket share vertices
                ids_lo[i, k] = ids_up[i, k]
            else:
                verts.append((x, y, z_l)); meta.append((-1, i, k)); ids_lo[i, k] = base + cnt; cnt += 1
    # back row (shared by upper and lower wall)
    ids_back = np.zeros(n1, np.int64)
    for i in range(n1):
        x = xm + (P[i, 0] - xm) * xscale(K) * 0.9
        verts.append((x, P[i, 1] + BACK_D, P[i, 2])); meta.append((0, i, K + 1)); ids_back[i] = base + cnt; cnt += 1
    pv = np.array(verts, np.float64)
    tris, kinds = [], []

    allco = np.concatenate([co, pv])
    quads = []
    for i in range(n1 - 1):
        for k in range(K):
            quads.append((ids_up[i, k], ids_up[i + 1, k], ids_up[i + 1, k + 1], ids_up[i, k + 1], 1 if k < LIP_ROWS else 3, (0, 0, -1)))
            quads.append((ids_lo[i, k], ids_lo[i + 1, k], ids_lo[i + 1, k + 1], ids_lo[i, k + 1], 2 if k < LIP_ROWS else 4, (0, 0, 1)))
        quads.append((ids_up[i, K], ids_up[i + 1, K], ids_back[i + 1], ids_back[i], 3, (0, -1, 0)))
        quads.append((ids_lo[i, K], ids_lo[i + 1, K], ids_back[i + 1], ids_back[i], 4, (0, -1, 0)))
    for a, b, c, d, kind, expect in quads:
        for tri in ((a, b, c), (a, c, d)):
            if len(set(tri)) < 3:
                continue
            p0, p1, p2 = allco[tri[0]], allco[tri[1]], allco[tri[2]]
            nrm = np.cross(p1 - p0, p2 - p0)
            if np.linalg.norm(nrm) < 1e-14:
                continue
            e = np.array(expect, float)
            # at the back wall / steep parts use the local direction towards the cavity centre line instead
            t = tri if (nrm @ e) >= 0 else (tri[0], tri[2], tri[1])
            tris.append(t)
            kinds.append(kind)
    tris = np.array(tris, np.int64)
    kinds = np.array(kinds, np.int8)
    # UVs: lip-band rows get the lip texture continued from the rim (local linear fit); deeper rows get a constant uv
    Au = local_uv_fit(co, faces, uv, up, +1, frame)
    Al = local_uv_fit(co, faces, uv, lo, -1, frame)
    vuv = np.zeros((len(allco), 2), np.float32)

    def rim_uv(vids):
        """uv of every rim (crease) vertex. A vertex on a UV seam carries several corner uvs: walk along the chain from its middle
        and pick, at every vertex, the corner uv closest to the previous one so the whole rim stays inside one chart."""
        cand = {int(v): [] for v in vids}
        fm = np.isin(faces, vids)
        for fi, k in zip(*np.where(fm)):
            v = int(faces[fi, k])
            u = tuple(np.round(uv[fi, k], 6))
            if u not in cand[v]:
                cand[v].append(u)
        order = list(range(len(vids) // 2, len(vids))) + list(range(len(vids) // 2 - 1, -1, -1))
        out, prev = {}, None
        for i in order:
            v = int(vids[i])
            if i == len(vids) // 2 - 1:
                prev = out[int(vids[len(vids) // 2])]          # restart the left half from the middle vertex
            c = cand[v] or [(0.0, 0.0)]
            if prev is None:
                out[v] = c[0]
            else:
                out[v] = min(c, key=lambda u: (u[0] - prev[0]) ** 2 + (u[1] - prev[1]) ** 2)
            prev = out[v]
        return {v: np.array(u, np.float32) for v, u in out.items()}
    ru, rl = rim_uv(up), rim_uv(lo)
    # Meshy atlases split the face into several UV charts, so one global linear fit can straddle charts. Anchor every
    # lip-band vertex on the uv of its own rim vertex (same chart as the skin it continues) and add only a small,
    # clipped offset from the fitted gradient.
    UV_CLIP = 0.004
    for (side, i, k), vid in zip(meta, range(base, base + len(meta))):
        if side != 0 and k <= LIP_ROWS:
            x, z = allco[vid, 0], allco[vid, 2]
            rv = int(up[i]) if side > 0 else int(lo[i])
            A = Au if side > 0 else Al
            anchor = np.array((ru if side > 0 else rl).get(rv, (0, 0)), np.float32)
            delta = np.array([x, z, 1.0]) @ A - np.array([allco[rv, 0], allco[rv, 2], 1.0]) @ A
            vuv[vid] = anchor + np.clip(delta, -UV_CLIP, UV_CLIP)
        elif side != 0:
            rv = int(up[i]) if side > 0 else int(lo[i])
            vuv[vid] = (ru if side > 0 else rl).get(rv, (0, 0))
    tuv = np.zeros((len(tris), 3, 2), np.float32)
    for fi, t in enumerate(tris):
        for k, v in enumerate(t):
            v = int(v)
            if v < len(co):
                tuv[fi, k] = ru.get(v, rl.get(v, (0, 0)))
            else:
                tuv[fi, k] = vuv[v]
    part_pocket = np.full(len(pv), 0, np.int8)
    for j, (side, i, k) in enumerate(meta):
        part_pocket[j] = 1 if side > 0 else (2 if side < 0 else 3)   # 1 upper wall, 2 lower wall, 3 back wall (treated as upper/static)
    return dict(verts=pv, faces=tris, kinds=kinds, uv=tuv, part=part_pocket, meta=meta, ids_up=ids_up, ids_lo=ids_lo, hs=hs, xm=xm, hw=hw, base=base)


# ----------------------------------------------------------------------------
# teeth and tongue (superellipsoids)
# ----------------------------------------------------------------------------
def _sgnpow(w, e):
    return np.sign(w) * np.abs(w) ** e


def superellipsoid(a, b, c, e1=0.5, e2=0.5, nu=16, nv=10):
    """Closed triangle mesh; returns (verts (N,3), faces)."""
    vs = np.linspace(-np.pi / 2, np.pi / 2, nv + 1)
    us = np.linspace(-np.pi, np.pi, nu, endpoint=False)
    V = []
    for j, v in enumerate(vs):
        for u in us:
            cv, sv = _sgnpow(np.cos(v), e1), _sgnpow(np.sin(v), e1)
            V.append((a * cv * _sgnpow(np.cos(u), e2), b * cv * _sgnpow(np.sin(u), e2), c * sv))
    V = np.array(V)
    F = []
    idx = lambda j, i: j * nu + (i % nu)
    for j in range(nv):
        for i in range(nu):
            a_, b_, c_, d_ = idx(j, i), idx(j, i + 1), idx(j + 1, i + 1), idx(j + 1, i)
            if j == 0:
                F.append((a_, c_, d_) if False else (a_, b_, c_)); F.append((a_, c_, d_))
            else:
                F.append((a_, b_, c_)); F.append((a_, c_, d_))
    F = np.array(F)
    # drop degenerate triangles at the poles
    keep = [len(set(map(tuple, V[f].round(9).tolist()))) == 3 for f in F]
    return V, F[np.array(keep)]


def make_tooth(center, width, thick, height, yaw, taper=0.22):
    V, F = superellipsoid(width / 2, thick / 2, height / 2, 0.45, 0.5)
    # taper towards the incisal edge (z-): narrower there
    t = (V[:, 2] / (height / 2) + 1) / 2                     # 0 bottom .. 1 top
    V[:, 0] *= (1 - taper * (1 - t))
    V[:, 1] *= (1 - 0.5 * taper * (1 - t))
    cy, sy = np.cos(yaw), np.sin(yaw)
    R = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return V @ R.T + np.asarray(center), F


UPPER_W = [0.0074, 0.0060, 0.0066]       # central, lateral, canine
UPPER_H = [0.0074, 0.0066, 0.0070]
LOWER_W = [0.0056, 0.0058, 0.0064]
LOWER_H = [0.0068, 0.0066, 0.0070]


def build_teeth_tongue(cut, pocket, frame):
    co = cut["co"]
    up = cut["upper"]
    P = co[up]
    xs, ys = P[:, 0], P[:, 1]
    hs_fun = lambda x: np.interp(x, pocket["ids_up"][:, 0] * 0 + xs, pocket["hs"])
    xm = pocket["xm"]
    parts = []   # (verts, faces, part_id)
    z0c = lambda x: frame.zc(x)
    def row(widths, heights, upper):
        out = []
        for sgn in (-1, 1):
            xcur = xm
            for w, h in zip(widths, heights):
                xc = xcur + sgn * w / 2
                xcur += sgn * w
                ysl = float(np.interp(xc, xs, ys))
                yaw = -float(np.arctan2(np.interp(xc + 0.003, xs, ys) - np.interp(xc - 0.003, xs, ys), 0.006))
                hh = h * (0.62 + 0.38 * float(np.interp(xc, xs, pocket["hs"])))
                # upper incisors overlap the lower ones (overbite 2.8 mm) and stand 2.6 mm in front of them (overjet)
                zc = (float(z0c(xc)) - 0.0028 + hh / 2) if upper else (float(z0c(xc)) - 0.0012 - hh / 2)
                yc = ysl + (0.0066 if upper else 0.0094)
                V, F = make_tooth((xc, yc, zc), w * 0.96, 0.0052 if w < 0.007 else 0.0058, hh, yaw)
                out.append((V, F))
        return out
    teeth_u = row(UPPER_W, UPPER_H, True)
    teeth_l = row(LOWER_W, LOWER_H, False)
    # tongue
    ytip = float(np.interp(xm, xs, ys)) + 0.0125
    V, F = superellipsoid(0.0155, 0.026, 0.0052, 0.6, 0.55, nu=20, nv=12)
    V = V + np.array([xm, ytip + 0.026, float(z0c(xm)) - 0.0105])
    tongue = (V, F)
    return teeth_u, teeth_l, tongue


# ----------------------------------------------------------------------------
# assembly
# ----------------------------------------------------------------------------
PART_SKIN, PART_UP_WALL, PART_LO_WALL, PART_UP_TEETH, PART_LO_TEETH, PART_TONGUE, PART_BACK = 0, 1, 2, 3, 4, 5, 6
MAT_SKIN, MAT_INSIDE, MAT_TEETH, MAT_TONGUE = 0, 1, 2, 3


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def assemble(co, faces, uv, mat, frame):
    cut = cut_lips(co, faces, uv, frame)
    pocket = build_pocket(cut, frame)
    teeth_u, teeth_l, tongue = build_teeth_tongue(cut, pocket, frame)
    C = [cut["co"]]
    Fs = [cut["faces"]]
    UVs = [cut["uv"]]
    M = [np.concatenate([mat, np.full(len(cut["faces"]) - len(mat), MAT_SKIN, mat.dtype)]) if len(cut["faces"]) >= len(mat) else mat[: len(cut["faces"])]]
    nskin = len(cut["co"])
    part = [np.zeros(nskin, np.int8)]
    # pocket (vertices are appended right after the skin vertices: pocket['base'] == nskin)
    assert pocket["base"] == nskin
    C.append(pocket["verts"].astype(np.float32))
    pp = pocket["part"].copy()
    pp = np.where(pp == 3, PART_BACK, pp)
    part.append(pp)
    Fs.append(pocket["faces"])
    UVs.append(pocket["uv"])
    M.append(np.where(pocket["kinds"] <= 2, MAT_SKIN, MAT_INSIDE).astype(mat.dtype))
    off = nskin + len(pocket["verts"])

    group = [np.zeros(nskin + len(pocket["verts"]), np.int32)]

    def add_mesh(V, F, pid, mid):
        nonlocal off
        group.append(np.full(len(V), 1 + sum(1 for g in group[1:]), np.int32))
        C.append(V.astype(np.float32))
        Fs.append(F + off)
        UVs.append(np.zeros((len(F), 3, 2), np.float32))
        M.append(np.full(len(F), mid, mat.dtype))
        part.append(np.full(len(V), pid, np.int8))
        off += len(V)
    for V, F in teeth_u:
        add_mesh(V, F, PART_UP_TEETH, MAT_TEETH)
    for V, F in teeth_l:
        add_mesh(V, F, PART_LO_TEETH, MAT_TEETH)
    add_mesh(tongue[0], tongue[1], PART_TONGUE, MAT_TONGUE)
    return dict(co=np.concatenate(C), faces=np.concatenate(Fs), uv=np.concatenate(UVs), mat=np.concatenate(M),
                part=np.concatenate(part), group=np.concatenate(group), upper=cut["upper"], lower=cut["lower"], n_skin=nskin, n_skin_faces=len(cut["faces"]),
                pocket=pocket, frame=frame, y_center=cut["y_center"])


def jaw_pivot(frame, y_center):
    return np.array([frame.cx, y_center + 0.095, frame.z0 + 0.060])


def jaw_weights(asm, mouth_cfg=None):
    """Per-vertex jaw weights for the assembled mouth mesh (skin + pocket + teeth + tongue).
    Across the lip slit the weight is binary (upper 0 / lower 1) so no triangle is sheared; it fades out sideways beyond the
    mouth corners and downwards onto the neck."""
    co, part, fr = asm["co"].astype(np.float64), asm["part"], asm["frame"]
    n = len(co)
    w = np.zeros(n)
    up, lo = asm["upper"], asm["lower"]
    xm = asm["pocket"]["xm"]
    hw = asm["pocket"]["hw"]
    yc = asm["y_center"]
    dx = co[:, 0] - xm
    dz = co[:, 2] - fr.zc(co[:, 0])
    dz = np.where(np.abs(dz) < 3e-5, 3e-5, dz)          # same convention as in cut_lips (on-curve vertices count as "above")
    wx = 1 - smoothstep(hw * 0.65, hw + 0.040, np.abs(dx))
    wz = 1 - smoothstep(0.050, 0.088, fr.z0 - co[:, 2])
    wy = 1 - smoothstep(yc + 0.05, yc + 0.11, co[:, 1])
    inside_w = np.abs(dx) <= hw + 1e-6
    # below the crease: 1 inside the mouth width; beyond the corners the crease line itself blends 0..1 over 5 mm
    wv = np.where(inside_w, (dz < -1e-6).astype(float), smoothstep(0.001, -0.004, dz))
    skin = part == PART_SKIN
    ws = wv * wx * wz * wy
    w[skin] = ws[skin]
    w[lo] = wx[lo]                  # lower rim follows the same lateral falloff as the skin below it
    w[up] = 0.0
    w[lo[0]] = w[lo[-1]] = 0.5 * wx[lo[0]]        # shared corner vertices: half way between upper (0) and lower
    low = part == PART_LO_WALL
    w[low] = wx[low]
    w[part == PART_UP_WALL] = 0.0
    w[part == PART_BACK] = 0.5 * wx[part == PART_BACK]          # throat follows half way
    pk = asm["pocket"]
    corner_ids = np.concatenate([pk["ids_up"][0, 1:], pk["ids_up"][-1, 1:]])
    w[corner_ids] = 0.5 * wx[corner_ids]                          # mouth-corner columns are shared by upper and lower wall
    w[part == PART_LO_TEETH] = 1.0
    w[part == PART_TONGUE] = 1.0
    return w


def rotate_jaw(co, w, pivot, theta_deg):
    """Linear-blend skinning of a single jaw bone rotation about the +x axis (positive = open)."""
    th = np.radians(theta_deg)
    c, s = np.cos(th), np.sin(th)
    p = co - pivot
    y2 = p[:, 1] * c + p[:, 2] * s * -1 * -1
    # opening: chin goes down (z-) and back (y+)  ->  rotation about x by +theta : y' = y*c - z*s ; z' = y*s + z*c
    y2 = p[:, 1] * c - p[:, 2] * s
    z2 = p[:, 1] * s + p[:, 2] * c
    R = np.stack([p[:, 0], y2, z2], 1) + pivot
    return co * (1 - w[:, None]) + R * w[:, None]


def clearance_report(asm, min_clear=0.0012, label=""):
    """For every pocket / teeth / tongue vertex cast a ray along -y (towards the face front): the first skin hit must be at
    least `min_clear` away, i.e. the part lies inside the head and does not poke through the outer skin.
    Rim rows of the pocket (they ARE the skin) are skipped. Returns dict part-> (min clearance, n_violations)."""
    co, part = asm["co"].astype(np.float64), asm["part"]
    nskin = asm["n_skin"]
    skin_faces = asm["faces"][: asm["n_skin_faces"]]
    near = (np.abs(co[:nskin, 0] - asm["frame"].cx) < 0.10) & (np.abs(co[:nskin, 2] - asm["frame"].z0) < 0.10) & (co[:nskin, 1] < 0.0)
    fm = near[skin_faces.clip(0, nskin - 1)].all(1) & (skin_faces < nskin).all(1)
    bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in co[:nskin]], [tuple(map(int, f)) for f in skin_faces[fm]], epsilon=0.0)
    rim = set(map(int, asm["upper"])) | set(map(int, asm["lower"]))
    pk = asm["pocket"]
    for (side, i, k), vid in zip(pk["meta"], range(pk["base"], pk["base"] + len(pk["meta"]))):
        if k <= 2:
            rim.add(vid)       # rows hugging the lip rim are part of the lip edge
    out = {}
    names = {1: "upper_wall", 2: "lower_wall", 3: "upper_teeth", 4: "lower_teeth", 5: "tongue", 6: "back_wall"}
    for pid, nm in names.items():
        idx = np.where(part == pid)[0]
        mins, viol = 1e9, 0
        worst = None
        for v in idx:
            if int(v) in rim:
                continue
            p = co[v]
            h = bvh.ray_cast(Vector(p), Vector((0, -1, 0)))
            if h[0] is None:
                clear = -1.0          # no skin in front at all -> outside the head
            else:
                clear = (p[1] - h[0].y)
            if clear < mins:
                mins, worst = clear, p.copy()
            if clear < min_clear:
                viol += 1
        out[nm] = (mins, viol, len(idx))
    log(label, "clearance to outer skin (mm): " + ", ".join(f"{k}: min {v[0]*1000:.2f} viol {v[1]}/{v[2]}" for k, v in out.items()))
    return out


def _skin_bvh(asm):
    co = asm["co"].astype(np.float64)
    nskin = asm["n_skin"]
    skin_faces = asm["faces"][: asm["n_skin_faces"]]
    fr = asm["frame"]
    near = (np.abs(co[:nskin, 0] - fr.cx) < 0.10) & (np.abs(co[:nskin, 2] - fr.z0) < 0.10) & (co[:nskin, 1] < 0.0)
    fm = near[skin_faces.clip(0, nskin - 1)].all(1) & (skin_faces < nskin).all(1)
    return BVHTree.FromPolygons([tuple(map(float, v)) for v in co[:nskin]], [tuple(map(int, f)) for f in skin_faces[fm]], epsilon=0.0)


def clearance_of(bvh, p):
    h = bvh.ray_cast(Vector(p), Vector((0, -1, 0)))
    return None if h[0] is None else p[1] - h[0].y


def fit_inside(asm, min_clear=0.0016, iters=4):
    """Push teeth, tongue and the deeper pocket walls back (+y) until they are at least `min_clear` inside the outer skin."""
    bvh = _skin_bvh(asm)
    co = asm["co"].astype(np.float64)
    part, group = asm["part"], asm["group"]
    pk = asm["pocket"]
    base = pk["base"]
    meta = pk["meta"]
    moved = 0.0
    for it in range(iters):
        changed = False
        # rigid parts (each tooth / the tongue): shift the whole part by the worst deficit
        for g in np.unique(group[np.isin(part, [3, 4, 5]) if False else np.isin(part, [3, 4, 5])]):
            idx = np.where((group == g) & np.isin(part, [3, 4, 5]))[0]
            worst = 0.0
            for v in idx:
                c = clearance_of(bvh, co[v])
                need = (min_clear - c) if c is not None else 0.004
                worst = max(worst, need)
            if worst > 0:
                co[idx, 1] += worst + 0.0002
                changed = True
                moved = max(moved, worst)
        # pocket rows beyond the lip band: per vertex
        pids = np.arange(base, base + len(meta))
        for (side, i, k), v in zip(meta, pids):
            if k <= 2 or side == 0:
                continue
            c = clearance_of(bvh, co[v])
            mc = min_clear if k > LIP_ROWS else 0.0010
            need = (mc - c) if c is not None else 0.004
            if need > 0:
                co[v, 1] += need + 0.0002
                changed = True
        if not changed:
            break
    asm["co"] = co.astype(np.float32)
    log("fit_inside: iterations", it + 1, "max shift", round(moved * 1000, 2), "mm")
    return asm
