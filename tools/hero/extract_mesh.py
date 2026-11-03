#!/usr/bin/env python3
"""Trace a CAD motif from a project's own CAD scene, posed several ways: filled regions per part role, the visible
feature edges, and (optionally) one moving group drawn at a set of poses, such as a turret that scans.

    <python with cadquery> tools/hero/extract_mesh.py tools/hero/motifs/gyropup.mesh.json --source ../gyropup

The spec names a scene module (``scene``, a Python file beside the spec). Its ``parts(source, pose)`` yields
``(name, group, role, shape)`` for every part, built by the project's own CAD code, in millimetres with z up;
``pose`` is None for the resting pose or one of the spec's ``poses``. Only the groups in ``posed`` are redrawn per
pose. This script tessellates the shapes, projects them, keeps each group's visible regions and edges (hidden lines
removed with a depth buffer), and writes ``parts`` and ``source`` back into the spec. Rendering (heroes.py) reads
only that committed result.

Each group hides only its own lines; the banner hides groups behind each other by stacking their filled regions in
painter order (``painter`` in the spec, far to near). Edges are creases sharper than ``crease_deg``, open edges and
silhouettes of the tessellated solids.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------------------------------------ geometry

def camera(view, up=(0.0, 0.0, 1.0)):
    """Unit vectors for a view from direction ``view`` (towards the camera): right, screen-down, towards-camera."""
    d = np.asarray(view, float)
    d /= np.linalg.norm(d)
    r = np.cross(up, d)
    r /= np.linalg.norm(r)
    return r, -np.cross(d, r), d


def tessellate(shape, tol=0.25, ang=0.3):
    """Triangles (N, 3, 3) of a CadQuery shape or workplane, in its own millimetres."""
    if hasattr(shape, "vals"):
        vals = shape.vals()
        import cadquery as cq
        shape = vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    v, t = shape.tessellate(tol, ang)
    if not t:
        return np.zeros((0, 3, 3))
    V = np.array([(q.x, q.y, q.z) for q in v], float)
    return V[np.array(t, int)]


def rasterize(tris, shape, ids):
    """Depth buffer (nearest = largest) and the id of the nearest triangle's mesh, for triangles in pixel units."""
    h, w = shape
    z = np.full(shape, -np.inf)
    idbuf = np.full(shape, -1, int)
    for tri, i in zip(tris, ids):
        P = tri[:, :2]
        x0, y0 = np.maximum(np.floor(P.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(P.max(0)).astype(int) + 1, (w, h))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        sx, sy = xx + .5, yy + .5
        (ax, ay), (bx, by), (cx, cy) = P
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        l1 = ((by - cy) * (sx - cx) + (cx - bx) * (sy - cy)) / den
        l2 = ((cy - ay) * (sx - cx) + (ax - cx) * (sy - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not inside.any():
            continue
        depth = l1 * tri[0, 2] + l2 * tri[1, 2] + l3 * tri[2, 2]
        zz = z[y0:y1, x0:x1]
        win = inside & (depth > zz)
        zz[win] = depth[win]
        idbuf[y0:y1, x0:x1][win] = i
    return z, idbuf


def loops(mask):
    """Every boundary of a mask as closed loops of pixel corners, filled pixels on the right (y down): outer loops
    run clockwise on screen and holes anticlockwise, so a nonzero fill keeps the holes open."""
    m = np.pad(mask, 1)
    edges = {}
    for (dy, dx), (a, b) in {(-1, 0): ((0, 0), (1, 0)), (1, 0): ((1, 1), (0, 1)),
                             (0, -1): ((0, 1), (0, 0)), (0, 1): ((1, 0), (1, 1))}.items():
        nb = np.roll(np.roll(m, -dy, 0), -dx, 1)
        ys, xs = np.nonzero(m & ~nb)
        for y, x in zip(ys.tolist(), xs.tolist()):
            edges.setdefault((x + a[0] - 1, y + a[1] - 1), []).append((x + b[0] - 1, y + b[1] - 1))
    out = []
    while edges:
        start = next(iter(edges))
        pts, cur = [start], start
        while True:
            nxt = edges[cur].pop()
            if not edges[cur]:
                del edges[cur]
            if nxt == start:
                break
            pts.append(nxt)
            cur = nxt
        # keep corners only
        k = len(pts)
        corners = [pts[i] for i in range(k)
                   if (pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
                   != (pts[(i + 1) % k][0] - pts[i][0], pts[(i + 1) % k][1] - pts[i][1])]
        out.append(corners)
    return out


def area(loop):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]))


def dp(P, tol):
    """Douglas-Peucker on an open polyline (array); returns the kept indices."""
    keep = [0, len(P) - 1]
    stack = [(0, len(P) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg, p0, v = P[a + 1:b], P[a], P[b] - P[a]
        nv = math.hypot(*v)
        dist = (np.abs(v[0] * (seg[:, 1] - p0[1]) - v[1] * (seg[:, 0] - p0[0])) / nv if nv > 1e-9
                else np.hypot(*(seg - p0).T))
        i = int(np.argmax(dist))
        if dist[i] > tol:
            keep.append(a + 1 + i)
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return sorted(keep)


def simplify_loop(pts, tol):
    if len(pts) < 5:
        return pts
    P = np.asarray(pts, float)
    far = int(np.argmax(np.hypot(*(P - P[0]).T)))
    a = dp(P[:far + 1], tol)
    b = dp(P[far:], tol)
    return [tuple(P[i]) for i in a[:-1]] + [tuple(P[far + i]) for i in b[:-1]]


def mesh_topology(local):
    """Welded edges of a triangle soup with their two faces (-1 when open) and the crease angle between them."""
    q = np.round(local / 1e-3).astype(np.int64)            # millimetres: weld at a micrometre
    _, inv = np.unique(q.reshape(-1, 3), axis=0, return_inverse=True)
    F = inv.reshape(-1, 3)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    f = np.tile(np.arange(len(F)), 3)
    e.sort(1)
    order = np.lexsort((e[:, 1], e[:, 0]))
    e, f = e[order], f[order]
    same = np.all(e[1:] == e[:-1], axis=1)
    pairs, i = [], 0
    while i < len(e):
        if i + 1 < len(e) and same[i]:
            pairs.append((e[i][0], e[i][1], f[i], f[i + 1]))
            i += 2
            while i < len(e) and i - 1 < len(same) and same[i - 1]:      # non-manifold extras: skip
                i += 1
        else:
            pairs.append((e[i][0], e[i][1], f[i], -1))
            i += 1
    return F, np.array(pairs, int)


def group_drawing(instances, view, spec):
    """One group's filled regions per role and its visible edges, in robot millimetres on the drawing plane."""
    R, D, Dz = camera(view)
    ppm = spec.get("px_per_mm", 2.0)
    crease = math.cos(math.radians(spec.get("crease_deg", 35)))
    world = []
    for inst in instances:
        w = inst["tris"].reshape(-1, 3)
        world.append(np.stack([w @ R, w @ D, w @ Dz], 1))
    allp = np.concatenate(world)
    lo = allp[:, :2].min(0) - 2
    shape = tuple((np.ceil((allp[:, :2].max(0) - lo) * ppm) + 4).astype(int)[::-1])
    tris, ids = [], []
    for k, s in enumerate(world):
        px = s.copy()
        px[:, :2] = (px[:, :2] - lo) * ppm
        tris.append(px.reshape(-1, 3, 3))
        ids.append(np.full(len(px) // 3, k))
    z, idbuf = rasterize(np.concatenate(tris), shape, np.concatenate(ids))
    roles = np.array([inst["role"] for inst in instances] + [""])
    regions = {}
    for role in spec["roles_order"]:
        mask = (idbuf >= 0) & (roles[idbuf] == role)
        if not mask.any():
            continue
        L = []
        for loop in loops(mask):
            if abs(area(loop)) < spec.get("min_area_px", 6):
                continue
            mm = [(x / ppm + lo[0], y / ppm + lo[1]) for x, y in loop]
            L.append([[round(x, 1), round(y, 1)] for x, y in simplify_loop(mm, spec.get("outline_tol_mm", 0.6))])
        if L:
            regions[role] = L
    # visible edges: creases, open edges and silhouettes, sampled against the group's depth buffer
    zf = np.where(np.isfinite(z), z, -1e9)
    zmin = zf.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            zmin = np.minimum(zmin, np.roll(np.roll(zf, dy, 0), dx, 1))
    eps = spec.get("depth_eps_mm", 1.0)
    segs = []
    for inst, s in zip(instances, world):
        F, E = inst["topo"]
        tri = s.reshape(-1, 3, 3)
        V = np.zeros((F.max() + 1, 3))
        V[F.reshape(-1)] = tri.reshape(-1, 3)
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        a, b, f1, f2 = E.T
        open_ = f2 < 0
        f2c = np.where(open_, f1, f2)
        keep = open_ | (np.sum(n[f1] * n[f2c], 1) < crease) | (np.sign(n[f1, 2]) != np.sign(n[f2c, 2]))
        for i, j in zip(a[keep], b[keep]):
            p, q = V[i], V[j]
            L = math.hypot(*(q[:2] - p[:2])) * ppm
            if L < 0.5:
                continue
            t = np.linspace(0, 1, int(L * 2) + 2)
            pts = p + (q - p) * t[:, None]
            px = np.clip(((pts[:, :2] - lo) * ppm).astype(int), 0, (shape[1] - 1, shape[0] - 1))
            vis = pts[:, 2] >= zmin[px[:, 1], px[:, 0]] - eps
            if not vis.any():
                continue
            idx = np.flatnonzero(np.diff(np.concatenate([[0], vis.astype(int), [0]])))
            for s0, s1 in zip(idx[::2], idx[1::2]):
                if s1 - 1 > s0:
                    segs.append((tuple(pts[s0, :2]), tuple(pts[s1 - 1, :2])))
    return regions, chain(segs, spec), float(np.mean(allp[:, 2]))


def chain(segs, spec):
    """Join segments that share end points into polylines, simplify, and drop short ones."""
    key = lambda p: (round(p[0] * 20), round(p[1] * 20))
    adj = {}
    for k, (p, q) in enumerate(segs):
        adj.setdefault(key(p), []).append(k)
        adj.setdefault(key(q), []).append(k)
    used, out = set(), []
    for k in range(len(segs)):
        if k in used:
            continue
        used.add(k)
        line = [segs[k][0], segs[k][1]]
        for end in (1, 0):
            while True:
                tip = line[-1] if end else line[0]
                nxt = [j for j in adj.get(key(tip), []) if j not in used]
                if len(adj.get(key(tip), [])) != 2 or not nxt:
                    break
                j = nxt[0]
                used.add(j)
                p, q = segs[j]
                far = q if key(p) == key(tip) else p
                if end:
                    line.append(far)
                else:
                    line.insert(0, far)
        P = np.asarray(line)
        if np.sum(np.hypot(*np.diff(P, axis=0).T)) < spec.get("min_edge_mm", 3.0):
            continue
        out.append([[round(float(x), 1), round(float(y), 1)] for x, y in P[dp(P, spec.get("edge_tol_mm", 0.3))]])
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    spec_path = Path(argv[0]).resolve()
    source = Path(argv[argv.index("--source") + 1]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    mod_spec = importlib.util.spec_from_file_location("scene", spec_path.parent / spec["scene"])
    scene = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(scene)
    poses = spec.get("poses", [])
    parts, names = [], {}
    for pose in [None] + poses:
        by_group = {}
        for name, group, role, shape in scene.parts(source, pose):
            if pose is not None and group not in spec.get("posed", []):
                continue
            if pose is None and group in spec.get("posed", []) and poses:
                continue                                     # drawn per pose instead
            tris = tessellate(shape)
            if not len(tris):
                continue
            names.setdefault(group, set()).add(name)
            by_group.setdefault(group, []).append({"role": role, "tris": tris, "topo": mesh_topology(tris)})
        for group, insts in by_group.items():
            regions, lines, depth = group_drawing(insts, spec["view"], spec)
            part = {"name": group, "group": spec.get("animate_as", {}).get(group, group), "depth": round(depth, 1),
                    "from": spec.get("from", {}).get(group, [0, 0]), "regions": regions, "lines": lines}
            if pose is not None:
                part["pose"] = poses.index(pose)
            parts.append(part)
            print(f"{group}{'' if pose is None else ' pose ' + str(pose)}: {sum(map(len, regions.values()))} "
                  f"loops, {len(lines)} edges", flush=True)
    order = spec["painter"]
    parts.sort(key=lambda p: (order.index(p["name"]), p.get("pose", -1)))
    git = lambda *a: subprocess.run(["git", "-C", str(source), *a], capture_output=True, text=True).stdout.strip()
    inputs = {}
    for f in spec.get("inputs", []):
        for path in sorted(source.glob(f)):
            inputs[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
    spec["source"] = {"repo": git("remote", "get-url", "origin").rsplit("github.com", 1)[-1].lstrip(":/").removesuffix(".git"),
                      "commit": git("rev-parse", "HEAD"), "inputs": inputs,
                      "parts": {g: sorted(v) for g, v in sorted(names.items())}}
    spec["parts"] = parts
    spec_path.write_text(json.dumps(spec, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {spec_path} ({spec_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
