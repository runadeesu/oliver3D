"""Shared helpers for the Oliver Tree rigging pipeline (run inside Blender's Python)."""
import os
import sys
import json
import time
import math

# scipy / scikit-image live in an extra site-packages dir (see tools/setup_env.sh)
_pylibs = os.environ.get("OLIVER_PYLIBS")
if _pylibs and _pylibs not in sys.path:
    sys.path.insert(0, _pylibs)

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Vector, Matrix
except ImportError:  # allows numpy-only analysis with Blender's bundled python
    bpy = None

WORK = os.environ.get("OLIVER_WORK", "/tmp/oliver_work")
ROOT = os.environ.get("OLIVER_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
CONFIG_DIR = os.path.join(ROOT, "tools", "configs")

MODELS = {
    "turbo":  {"title": "Oliver_Turbo_A_Pose"},
    "cowboy": {"title": "Oliver_Cowboy_Tears_A_Pose"},
    "alone":  {"title": "Oliver_Alone_In_A_Crowd_A_Pose"},
    "gray":   {"title": "Oliver_Gray_Suit_A_Pose"},
}


def log(*a):
    print("[rig]", *a, flush=True)


def load_config(tag):
    with open(os.path.join(CONFIG_DIR, f"{tag}.json")) as f:
        return json.load(f)


def timer():
    t0 = time.time()
    return lambda: time.time() - t0


# ----------------------------------------------------------------------------
# mesh <-> numpy (meshes in this project are all-triangle)
# ----------------------------------------------------------------------------
def mesh_to_arrays(obj, uv_name="UVMap"):
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    nloop_per_poly = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", nloop_per_poly)
    assert (nloop_per_poly == 3).all(), "mesh must be all triangles"
    faces = lv.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers[uv_name].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 3, 2)
    mat = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mat)
    return co, faces, uv, mat


def arrays_to_mesh(name, co, faces, uv, mat=None, uv_name="UVMap"):
    """Create a fresh mesh datablock from numpy arrays (triangles, per-corner UV)."""
    me = bpy.data.meshes.new(name)
    nv, nf = len(co), len(faces)
    me.vertices.add(nv)
    me.vertices.foreach_set("co", np.ascontiguousarray(co, np.float32).ravel())
    me.loops.add(nf * 3)
    me.polygons.add(nf)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(faces, np.int32).ravel())
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 3, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nf, 3, np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nf, bool))
    if mat is not None:
        me.polygons.foreach_set("material_index", np.ascontiguousarray(mat, np.int32))
    me.update(calc_edges=True)
    lay = me.uv_layers.new(name=uv_name)
    lay.data.foreach_set("uv", np.ascontiguousarray(uv, np.float32).ravel())
    me.validate(clean_customdata=False)
    return me


# ----------------------------------------------------------------------------
# textures
# ----------------------------------------------------------------------------
_tex_cache = {}


def load_texture(path):
    if path in _tex_cache:
        return _tex_cache[path]
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    _tex_cache[path] = a
    return a


def sample_texture(tex, uv):
    """Bilinear sample. uv (...,2) in Blender convention (origin bottom-left). Returns float 0..1 (...,3)."""
    h, w = tex.shape[:2]
    x = np.clip(uv[..., 0] % 1.0, 0, 1) * (w - 1)
    y = (1.0 - np.clip(uv[..., 1] % 1.0, 0, 1)) * (h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    c = (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy)
         + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)
    return c / 255.0


def vertex_colors(co, faces, uv, tex):
    """Average texture colour at each vertex over its incident corners."""
    cc = sample_texture(tex, uv.reshape(-1, 2)).reshape(-1, 3, 3)
    n = len(co)
    acc = np.zeros((n, 3), np.float64)
    cnt = np.zeros(n, np.float64)
    for k in range(3):
        np.add.at(acc, faces[:, k], cc[:, k])
        np.add.at(cnt, faces[:, k], 1)
    return (acc / np.maximum(cnt, 1)[:, None]).astype(np.float32)


def rgb_to_hsv(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx = c.max(-1)
    mn = c.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm = m & (mx == r)
    gm = m & (mx == g) & ~rm
    bm = m & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    h = h * 60.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return np.stack([h, s, mx], -1)
