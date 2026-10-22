"""Carve fused fingers apart: thin ribbon cutters between adjacent finger axes + Blender exact boolean."""
from common import *
import hands_seg, hands_digits
from mathutils.bvhtree import BVHTree


SOLVER = os.environ.get("OLIVER_BOOL_SOLVER", "AUTO")   # AUTO: exact solver, fall back to the fast one when the exact result contains stray cutter faces
HOLE_TOLERANT = True       # exact solver tolerant to self-intersecting / non-watertight hands (needed for Meshy hands with pressed fingers)


def axis_point(dg, z, dm):
    """Point of a finger axis line at axial coordinate z (plane perpendicular to dm through the origin)."""
    lam = (z - dg["tip"] @ dm) / (dg["dir"] @ dm)
    return dg["tip"] + dg["dir"] * lam


def ribbon_cutter(da, db, dm, z0, z1, th0, th1, half_h=0.022, nst=16):
    """Closed thin prism between two finger axes, following the mid line, from axial coordinate z0 (beyond the
    tips) back to z1 (end of the slit, nearer the wrist). dm: unit hand axis (pointing to the fingertips)."""
    zs = np.linspace(z0, z1, nst)
    sections = []
    for k, z in enumerate(zs):
        a, b = axis_point(da, z, dm), axis_point(db, z, dm)
        m = (a + b) / 2
        l = b - a
        l -= (l @ dm) * dm
        l /= np.linalg.norm(l)
        h = np.cross(dm, l)
        h /= np.linalg.norm(h)
        f = k / (nst - 1)
        th = th0 + (th1 - th0) * f                 # thickness: wide at the tip, narrow at the web
        e = max(0.0, (f - 0.80) / 0.20)            # rounded proximal end of the slit
        hh = max(half_h * np.sqrt(max(0.0, 1.0 - e * e)), half_h * 0.05)
        sections.append([m - l * th / 2 - h * hh, m + l * th / 2 - h * hh, m + l * th / 2 + h * hh, m - l * th / 2 + h * hh])
    V = np.array(sections).reshape(-1, 3)
    Q = []
    for k in range(nst - 1):
        for e in range(4):
            a, b = k * 4 + e, k * 4 + (e + 1) % 4
            c, d = (k + 1) * 4 + (e + 1) % 4, (k + 1) * 4 + e
            Q.append((a, b, c, d))
    Q.append((3, 2, 1, 0))
    Q.append(((nst - 1) * 4 + 0, (nst - 1) * 4 + 1, (nst - 1) * 4 + 2, (nst - 1) * 4 + 3))
    # make sure the closed prism has outward (positive-volume) orientation
    vol = 0.0
    for q in Q:
        for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            a_, b_, c_ = V[tri[0]], V[tri[1]], V[tri[2]]
            vol += np.dot(a_, np.cross(b_, c_)) / 6.0
    if vol < 0:
        Q = [tuple(reversed(q)) for q in Q]
    return V, Q


def slit_ranges(da, db, dm, depth_frac):
    """Axial range of the slit between two fingers: from 12 mm beyond the farther tip to depth_frac of the finger length."""
    zt = max(da["tip"] @ dm, db["tip"] @ dm) + 0.012
    zm = 0.5 * (da["joints"][0] @ dm + db["joints"][0] @ dm)
    zl = 0.5 * (da["tip"] @ dm + db["tip"] @ dm)
    ze = zl - depth_frac * (zl - zm)
    return zt, ze


def make_obj(name, V, F_, uv=None, mat=None, nslots=0):
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], [list(map(int, f)) for f in F_])
    me.update()
    for i in range(nslots):
        m = bpy.data.materials.get(f"carve{i}") or bpy.data.materials.new(f"carve{i}")
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def fill_open_boundary(P, F):
    """Cap open boundary loops with fans so the hand sub-mesh is a closed solid. Returns new (P, F, n_cap_faces)."""
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(E, 1)
    u, inv, cnt = np.unique(key[:, 0] * len(P) + key[:, 1], return_inverse=True, return_counts=True)
    bmask = cnt[inv] == 1
    bedges = E[bmask]                      # directed boundary edges (a->b) as they appear in faces
    if len(bedges) == 0:
        return P, F, 0
    # chain into loops
    nxt = {int(a): int(b) for a, b in bedges}
    seen = set()
    newF, newP = [], [P]
    base = len(P)
    ncap = 0
    for start in list(nxt):
        if start in seen:
            continue
        loop = []
        cur = start
        while cur not in seen and cur in nxt:
            seen.add(cur)
            loop.append(cur)
            cur = nxt[cur]
        if len(loop) < 3:
            continue
        c = P[loop].mean(0)
        newP.append(c[None])
        ci = base
        base += 1
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            newF.append((b, a, ci))   # opposite winding to close the shell
            ncap += 1
    Pn = np.concatenate(newP)
    Fn = np.concatenate([F, np.array(newF, np.int64)]) if newF else F
    return Pn, Fn, ncap


def carve_hand(co, faces, uv, mask, res, depth_frac=0.80, th_tip=0.0042, th_web=0.0020, log_prefix=""):
    """Returns dict with the replacement geometry for the masked hand region."""
    fm = mask[faces].all(1)
    hf = faces[fm]
    huv = uv[fm]
    used = np.unique(hf)
    remap = -np.ones(len(co), np.int64)
    remap[used] = np.arange(len(used))
    P = co[used].astype(np.float64)
    F_ = remap[hf]
    n_orig_faces = len(F_)
    Pc, Fc, ncap = fill_open_boundary(P, F_)
    # --- cutters
    dig = res["digits"]
    names = [n for n in hands_digits.FINGER_NAMES if n in dig]
    cutV, cutQ = [], []
    off = 0
    dm = sum(dig[n_]["dir"] for n_ in names)
    dm /= np.linalg.norm(dm)
    res["dm"] = dm
    for a, b in zip(names[:-1], names[1:]):
        da, db = dig[a], dig[b]
        z0, z1 = slit_ranges(da, db, dm, depth_frac)
        V, Q = ribbon_cutter(da, db, dm, z0, z1, th_tip, th_web)
        cutQ += [tuple(i + off for i in q) for q in Q]
        cutV.append(V)
        off += len(V)
    CV = np.concatenate(cutV)
    # --- blender objects
    hand = make_obj("hand", Pc, Fc, nslots=3)
    me = hand.data
    mi = np.zeros(len(Fc), np.int32)
    mi[n_orig_faces:] = 2       # caps
    me.polygons.foreach_set("material_index", mi)
    cutter = make_obj("cutter", CV, cutQ, nslots=3)
    cm = np.full(len(cutter.data.polygons), 1, np.int32)
    cutter.data.polygons.foreach_set("material_index", cm)
    # uv for the hand (caps get zeros)
    lay = me.uv_layers.new(name="UVMap")
    uvall = np.zeros((len(Fc), 3, 2), np.float32)
    uvall[:n_orig_faces] = huv
    lay.data.foreach_set("uv", uvall.ravel())
    hand_bvh = BVHTree.FromPolygons([tuple(map(float, v)) for v in Pc], [tuple(map(int, f)) for f in Fc], epsilon=0.0)
    cb = BVHTree.FromPolygons([tuple(map(float, v)) for v in CV], [tuple(q) for q in cutQ], epsilon=0.0)

    def run(solver):
        for m_ in list(hand.modifiers):
            hand.modifiers.remove(m_)
        mod = hand.modifiers.new("bool", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.operand_type = "OBJECT"
        mod.object = cutter
        mod.solver = solver
        mod.use_self = False
        if solver == "EXACT" and HOLE_TOLERANT and hasattr(mod, "use_hole_tolerant"):
            mod.use_hole_tolerant = True
        if hasattr(mod, "material_mode"):
            mod.material_mode = "INDEX"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = hand.evaluated_get(dg)
        em = ev.to_mesh()
        nv = len(em.vertices)
        Pn = np.empty(nv * 3, np.float32); em.vertices.foreach_get("co", Pn); Pn = Pn.reshape(-1, 3)
        em.calc_loop_triangles()
        nf = len(em.polygons)
        lt = np.empty(len(em.loops), np.int32); em.loops.foreach_get("vertex_index", lt)
        ploops = np.empty(nf, np.int32); em.polygons.foreach_get("loop_total", ploops)
        mi2 = np.empty(nf, np.int32); em.polygons.foreach_get("material_index", mi2)
        uvn = np.empty(len(em.loops) * 2, np.float32); em.uv_layers[0].data.foreach_get("uv", uvn); uvn = uvn.reshape(-1, 2)
        ls = np.empty(nf, np.int32); em.polygons.foreach_get("loop_start", ls)
        tris, tuv, tmat = [], [], []
        for p_ in range(nf):                      # triangulate polygons (boolean output can contain n-gons)
            k = ploops[p_]
            s_ = ls[p_]
            for i in range(1, k - 1):
                tris.append((lt[s_], lt[s_ + i], lt[s_ + i + 1]))
                tuv.append((uvn[s_], uvn[s_ + i], uvn[s_ + i + 1]))
                tmat.append(mi2[p_])
        ev.to_mesh_clear()
        if len(tris) == 0:
            return None
        tris = np.array(tris, np.int64); tuv = np.array(tuv, np.float32); tmat = np.array(tmat, np.int32)
        # cutter-generated wall faces: face centroid lies on the cutter surface
        cen = Pn[tris].mean(1)
        onwall = np.zeros(len(tris), bool)
        for i in range(len(tris)):
            loc, nor, idx, dist = cb.find_nearest(Vector(cen[i]), 3e-5)
            onwall[i] = idx is not None
        wall = onwall & (tmat != 2)
        # quality: cut walls that float in the air (far from the hand surface) mean the solver misclassified inside / outside
        stray = 0
        for c in cen[wall]:
            loc, nor, idx, dist = hand_bvh.find_nearest(Vector(c))
            if dist > 0.0015:
                # only count faces outside the solid: inside walls are far from the surface too -> parity test along +z
                o = Vector(c); dv = Vector((0.123, 0.071, 1.0)).normalized(); cnt = 0
                while True:
                    hit = hand_bvh.ray_cast(o, dv)
                    if hit[0] is None:
                        break
                    cnt += 1; o = hit[0] + dv * 1e-6
                if cnt % 2 == 0:
                    stray += 1
        return Pn, tris, tuv, tmat, wall, stray

    first = SOLVER if SOLVER != "AUTO" else "EXACT"
    out = run(first)
    if out is not None and (out[5] > 0 and SOLVER == "AUTO"):
        log(log_prefix, "exact boolean left", out[5], "cutter faces outside the hand -> trying the fast solver")
        alt = run("FAST")
        if alt is not None and alt[5] < out[5]:
            out = alt
    if out is None:
        raise RuntimeError("boolean returned an empty mesh (cutter orientation / manifold problem)")
    Pn, tris, tuv, tmat, wall, stray = out
    keep = tmat != 2                    # drop the temporary caps
    tmat2 = np.where(wall, 1, tmat)
    log(log_prefix, "boolean:", len(Fc), "->", len(tris), "tris; new wall faces:", int((wall & keep).sum()), "caps dropped:", int((~keep).sum()), "stray cutter faces:", stray)
    return dict(P_old=P, F_old=F_, uv_old=huv, used=used, P_new=Pn, tris=tris[keep], tuv=tuv[keep], tmat=tmat2[keep], remap=remap)


def reintegrate(co, faces, uv, mat, mask, carved):
    """Replace the masked hand faces of the full mesh with the carved result; returns new (co, faces, uv, mat, tag)."""
    fm = mask[faces].all(1)
    Pn = carved["P_new"].astype(np.float32)
    used = carved["used"]
    # match carved vertices to the original ones (exact position)
    from scipy.spatial import cKDTree
    tree = cKDTree(co[used].astype(np.float64))
    dd, ii = tree.query(Pn.astype(np.float64))
    exact = dd < 1e-6
    # only vertices on the open border may be shared with the outside; interior ones are re-created anyway,
    # but reusing the original index for exact matches is harmless
    newidx = np.where(exact, used[ii], -1)
    extra = np.where(~exact)[0]
    newidx[extra] = len(co) + np.arange(len(extra))
    co2 = np.concatenate([co, Pn[extra]])
    tris = newidx[carved["tris"]]
    keep_f = faces[~fm]
    faces2 = np.concatenate([keep_f, tris])
    uv2 = np.concatenate([uv[~fm], carved["tuv"]])
    mat2 = np.concatenate([mat[~fm], np.zeros(len(tris), mat.dtype)])
    tag = np.concatenate([np.zeros(len(keep_f), np.int8), (carved["tmat"] == 1).astype(np.int8)])
    hand_vids = np.unique(newidx[carved["tris"]])
    return co2, faces2, uv2, mat2, tag, hand_vids


def fix_wall_uvs(co, faces, uv, tag, ref_faces_mask):
    """Give carved wall faces valid UVs from the nearest original (non-wall) surface."""
    wall = np.where(tag == 1)[0]
    if len(wall) == 0:
        return uv
    ref = np.where((tag == 0) & ref_faces_mask)[0]
    bm = BVHTree.FromPolygons([tuple(map(float, v)) for v in co], [tuple(map(int, f)) for f in faces[ref]], epsilon=0.0)
    uv = uv.copy()
    for fi in wall:
        pts = co[faces[fi]]
        cen = pts.mean(0)
        loc, nor, idx, dist = bm.find_nearest(Vector(cen))
        if idx is None:
            continue
        rf = ref[idx]
        tri = co[faces[rf]].astype(np.float64)
        tuv = uv[rf].astype(np.float64)
        out = []
        for p in pts:
            loc2, nor2, idx2, d2 = bm.find_nearest(Vector(p))
            r2 = ref[idx2]
            t2 = co[faces[r2]].astype(np.float64)
            uv2 = uv[r2].astype(np.float64)
            # barycentric of loc2 in triangle t2
            v0, v1, v2 = t2
            q = np.array(loc2)
            m = np.stack([v1 - v0, v2 - v0], 1)
            sol, *_ = np.linalg.lstsq(m, q - v0, rcond=None)
            b1, b2 = sol
            b0 = 1 - b1 - b2
            out.append(b0 * uv2[0] + b1 * uv2[1] + b2 * uv2[2])
        out = np.array(out)
        if np.abs(out - out.mean(0)).max() > 0.01:       # corners fell on different UV islands -> tiny triangle at the centroid
            c = out.mean(0) if np.abs(out - out[0]).max() < 0.05 else out[0]
            e = 0.0006
            out = c + np.array([[-e, -e], [e, -e], [0, e]])
        uv[fi] = out
    return uv
