"""Open the lips: split the face mesh along the lip crease curve (numpy), producing an upper and a lower rim chain."""
from common import *


def split_along_surface(co, faces, uv, d, edge_ok):
    """Split triangles along the zero set of the per-vertex signed distance `d`.
    Only edges for which edge_ok(u, v, t) is True are cut (limits the cut to the mouth width).
    Returns new arrays plus chain info:
      co2, faces2, uv2, chain_upper (ordered vertex ids, original id kept), chain_lower (duplicates; end ids shared)."""
    d = np.where(d == 0, 1e-9, d)
    # candidate faces: any vertex with different sign
    sg = d[faces] > 0
    straddle = sg.any(1) & (~sg).any(1)
    cand = np.where(straddle)[0]
    edge_vid = {}
    new_pos = []
    nv0 = len(co)

    def cut_vertex(u, v):
        key = (u, v) if u < v else (v, u)
        return edge_vid.get(key)

    # decide which edges are cut
    cut_edges = {}
    for fi in cand:
        f = faces[fi]
        for k in range(3):
            u, v = int(f[k]), int(f[(k + 1) % 3])
            if (d[u] > 0) == (d[v] > 0):
                continue
            key = (u, v) if u < v else (v, u)
            if key in cut_edges:
                continue
            t = d[key[0]] / (d[key[0]] - d[key[1]])
            ok = edge_ok(key[0], key[1], t)
            cut_edges[key] = (t, ok)
    # create new vertices
    for key, (t, ok) in cut_edges.items():
        if ok:
            edge_vid[key] = nv0 + len(new_pos)
            new_pos.append(co[key[0]] + (co[key[1]] - co[key[0]]) * t)
    co2 = np.concatenate([co, np.array(new_pos, co.dtype).reshape(-1, 3)]) if new_pos else co.copy()
    out_faces, out_uv, out_side, out_src = [], [], [], []
    keep = np.ones(len(faces), bool)
    segs = []
    end_vertices = set()
    for fi in cand:
        f = faces[fi]
        fuv = uv[fi]
        cuts = []
        for k in range(3):
            u, v = int(f[k]), int(f[(k + 1) % 3])
            key = (u, v) if u < v else (v, u)
            if key in edge_vid:
                t = cut_edges[key][0]
                tt = t if u == key[0] else 1 - t
                cuts.append((k, edge_vid[key], tt))
        if not cuts:
            continue
        keep[fi] = False
        if len(cuts) == 1:
            k, m, tt = cuts[0]
            A, B, C = int(f[k]), int(f[(k + 1) % 3]), int(f[(k + 2) % 3])
            uA, uB, uC = fuv[k], fuv[(k + 1) % 3], fuv[(k + 2) % 3]
            um = uA + (uB - uA) * tt
            out_faces += [(A, m, C), (m, B, C)]
            out_uv += [(uA, um, uC), (um, uB, uC)]
            out_side += [1 if d[A] > 0 else -1, 1 if d[B] > 0 else -1]
            out_src += [fi, fi]
            end_vertices.add(m)
        else:
            # two cut edges: apex V is the vertex shared by both cut edges
            ks = [c[0] for c in cuts]
            # edge k connects corner k and k+1; apex = corner shared by edges ks[0] and ks[1]
            if (ks[0] + 1) % 3 == ks[1]:
                apex_k = ks[1]
            else:
                apex_k = ks[0]
            V, P, Q = int(f[apex_k]), int(f[(apex_k + 1) % 3]), int(f[(apex_k + 2) % 3])
            uV, uP, uQ = fuv[apex_k], fuv[(apex_k + 1) % 3], fuv[(apex_k + 2) % 3]
            # m1 on V-P, m2 on Q-V
            def find_m(a, b):
                key = (a, b) if a < b else (b, a)
                return edge_vid[key], cut_edges[key][0] if a == key[0] else 1 - cut_edges[key][0]
            m1, t1 = find_m(V, P)
            m2, t2 = find_m(V, Q)
            um1 = uV + (uP - uV) * t1
            um2 = uV + (uQ - uV) * t2
            sV = 1 if d[V] > 0 else -1
            out_faces += [(V, m1, m2), (m1, P, Q), (m1, Q, m2)]
            out_uv += [(uV, um1, um2), (um1, uP, uQ), (um1, uQ, um2)]
            out_side += [sV, -sV, -sV]
            out_src += [fi, fi, fi]
            segs.append((m1, m2))
    faces2 = np.concatenate([faces[keep], np.array(out_faces, faces.dtype)])
    uv2 = np.concatenate([uv[keep], np.array(out_uv, uv.dtype)])
    side = np.concatenate([np.zeros(keep.sum(), np.int8), np.array(out_side, np.int8)])
    # chain ordering via segment adjacency
    nb = {}
    for a_, b_ in segs:
        nb.setdefault(a_, []).append(b_)
        nb.setdefault(b_, []).append(a_)
    ends = [v for v, l in nb.items() if len(l) == 1]
    ends = list(set(ends) | {e for e in end_vertices if e in nb})
    return dict(co=co2, faces=faces2, uv=uv2, side=side, segs=segs, nb=nb, ends=ends, new_start=nv0, edge_vid=edge_vid)


def order_chain(nb, start):
    chain = [start]
    prev = None
    cur = start
    while True:
        nxt = [n for n in nb[cur] if n != prev]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        chain.append(cur)
        if len(chain) > len(nb) + 2:
            break
    return chain


def open_slit(res):
    """Duplicate interior chain vertices so the lower faces use their own copies. Returns dict with arrays + chains."""
    co, faces, uv, side, nb, ends = res["co"], res["faces"], res["uv"], res["side"], res["nb"], res["ends"]
    # the chain: find the two extreme ends along x among `ends` candidates that terminate the path
    xs = co[ends][:, 0]
    start = ends[int(np.argmin(xs))]
    chain = order_chain(nb, start)
    chain = np.array(chain)
    interior = chain[1:-1]
    dup = {int(v): len(co) + i for i, v in enumerate(interior)}
    co2 = np.concatenate([co, co[interior]])
    faces2 = faces.copy()
    lower = side == -1
    fl = faces2[lower]
    for v, nv in dup.items():
        fl[fl == v] = nv
    faces2[lower] = fl
    lower_chain = np.array([dup.get(int(v), int(v)) for v in chain])
    return dict(co=co2, faces=faces2, uv=uv, upper=chain, lower=lower_chain)
