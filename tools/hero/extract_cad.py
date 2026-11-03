#!/usr/bin/env python3
"""Trace a CAD motif for a banner from a project's real STEP files: each part's visible edges (OpenCASCADE's exact
hidden-line removal), its filled silhouette, and where it starts before sliding into place.

    <python with cadquery> tools/hero/extract_cad.py tools/hero/motifs/j501-agx-orin.cad.json --source ../j501-agx-orin

The spec file names the parts and the view; this script fills in ``parts`` (and ``source`` with the commit and every
input's sha256) and writes the same file back. Rendering (heroes.py) reads only the committed result, so it needs
nothing but the Python standard library.

Each solid gets its own hidden-line removal, so its edges hide only behind itself; the banner hides parts behind
each other by stacking their filled silhouettes in depth order. The HLR code is adapted from
github.com/Valpatel/cad-agent ``src/cadagent/publish/anim/cad.py`` (MIT).
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np


def basis(direction, up=(0.0, 0.0, 1.0)):
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    r = np.cross(up, d)
    r /= np.linalg.norm(r)
    return d, r, np.cross(d, r)


def project(pts, direction):
    d, r, u = basis(direction)
    p = np.asarray(pts, float).reshape(-1, 3)
    return np.stack([p @ r, -(p @ u)], axis=1), p @ d


def hlr_polylines(solid, direction, deflection=0.05):
    """Visible sharp edges and outlines of ``solid`` alone, as drawing polylines in mm (x right, y down)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    d, r, _ = basis(direction)
    algo = HLRBRep_Algo()
    algo.Add(solid.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d), gp_Dir(*r))))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    out = []
    for comp in (h.VCompound(), h.OutLineVCompound()):
        if comp is None or comp.IsNull():
            continue
        ex = TopExp_Explorer(comp, TopAbs_EDGE)
        while ex.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()))
            u0, u1 = sorted((c.FirstParameter(), c.LastParameter()))
            if c.GetType() == GeomAbs_Line:
                pts = [c.Value(u0), c.Value(u1)]
            else:
                s = GCPnts_QuasiUniformDeflection(c, deflection, u0, u1)
                pts = [s.Value(i) for i in range(1, s.NbPoints() + 1)]
            out.append([(p.X(), -p.Y()) for p in pts])
            ex.Next()
    return out


def silhouette(solid, direction, px_per_mm=4.0):
    """The outer outline of the solid's projection, traced from a raster of its triangles (mm, simplified)."""
    v, t = solid.tessellate(0.2, 0.3)
    v = np.array([(p.x, p.y, p.z) for p in v], float)
    xy, _ = project(v, direction)
    lo = xy.min(0) - 2
    g = ((xy - lo) * px_per_mm)
    w, hgt = (np.ceil(g.max(0)) + 3).astype(int)
    mask = np.zeros((hgt, w), bool)
    yy, xx = np.mgrid[0:hgt, 0:w]
    for a, b, c in np.array(t, int).reshape(-1, 3):
        P = g[[a, b, c]]
        x0, y0 = np.floor(P.min(0)).astype(int)
        x1, y1 = np.ceil(P.max(0)).astype(int) + 1
        sx, sy = xx[y0:y1, x0:x1] + .5, yy[y0:y1, x0:x1] + .5
        (ax, ay), (bx, by), (cx, cy) = P
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (sx - cx) + (cx - bx) * (sy - cy)) / den
        l2 = ((cy - ay) * (sx - cx) + (ax - cx) * (sy - cy)) / den
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (1 - l1 - l2 >= -1e-6)
        mask[y0:y1, x0:x1] |= inside
    loop = _trace(mask)
    pts = [(x / px_per_mm + lo[0], y / px_per_mm + lo[1]) for x, y in loop]
    return _simplify(pts, 0.35)


def _trace(mask):
    """Outer boundary of the top-most blob as pixel-corner points: walk the pixel edges with the filled pixels on
    the right (y down), turning left when the pixel ahead-left is filled and right when neither ahead pixel is."""
    h, w = mask.shape
    m = np.zeros((h + 2, w + 2), bool)
    m[1:-1, 1:-1] = mask
    ys, xs = np.nonzero(m)
    i = int(np.argmin(ys * (w + 2) + xs))
    start = (int(xs[i]), int(ys[i]))
    ahead = {(1, 0): ((0, -1), (0, 0)), (0, 1): ((0, 0), (-1, 0)),
             (-1, 0): ((-1, 0), (-1, -1)), (0, -1): ((-1, -1), (0, -1))}
    pos, dirn, pts = start, (1, 0), [start]
    for _ in range(4 * m.size):
        (lx, ly), (rx, ry) = ahead[dirn]
        left, right = m[pos[1] + ly, pos[0] + lx], m[pos[1] + ry, pos[0] + rx]
        new = (dirn[1], -dirn[0]) if left else dirn if right else (-dirn[1], dirn[0])
        if new != dirn:
            pts.append(pos)
        dirn = new
        pos = (pos[0] + dirn[0], pos[1] + dirn[1])
        if pos == start:
            break
    return [(x - 1, y - 1) for x, y in pts]


def _simplify(pts, tol):
    """Douglas-Peucker on a closed loop."""
    if len(pts) < 4:
        return pts
    P = np.asarray(pts, float)

    def dp(a, b):
        seg = P[a:b + 1]
        if b - a < 2:
            return [a, b]
        p0, p1 = P[a], P[b]
        v = p1 - p0
        n = np.hypot(*v)
        if n < 1e-9:
            dist = np.hypot(*(seg - p0).T)
        else:
            q = seg - p0
            dist = np.abs(v[0] * q[:, 1] - v[1] * q[:, 0]) / n
        i = int(np.argmax(dist))
        if dist[i] > tol:
            left = dp(a, a + i)
            return left[:-1] + dp(a + i, b)
        return [a, b]

    far = int(np.argmax(np.hypot(*(P - P[0]).T)))
    idx = dp(0, far)[:-1] + dp(far, len(P) - 1)
    return [tuple(map(float, P[i])) for i in dict.fromkeys(idx)]


def main(argv=None) -> int:
    import cadquery as cq

    argv = sys.argv[1:] if argv is None else argv
    spec_path = Path(argv[0])
    source = Path(argv[argv.index("--source") + 1]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    view = spec["view"]
    parts, inputs = [], {}
    for part in spec["parts_spec"]:
        step = source / part["step"]
        inputs[part["step"]] = hashlib.sha256(step.read_bytes()).hexdigest()
        solids = cq.importers.importStep(str(step)).solids().vals()
        solid = solids[0] if len(solids) == 1 else cq.Compound.makeCompound(solids)
        bb = solid.BoundingBox()
        centre = ((bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2, (bb.zmin + bb.zmax) / 2)
        _, depth = project([centre], view)
        lines = [pl for pl in hlr_polylines(solid, view)
                 if sum(math.dist(a, b) for a, b in zip(pl, pl[1:])) >= spec.get("min_edge_mm", 1.0)]
        explode, _ = project([part.get("from", (0, 0, 0))], view)
        parts.append({"name": part["name"], "role": part.get("role", "body"), "group": part.get("group", part["name"]),
                      "depth": round(float(depth[0]), 2),
                      "from": [round(float(v), 2) for v in explode[0]],
                      "outlines": [[[round(x, 2), round(y, 2)] for x, y in silhouette(one, view)] for one in solids],
                      "lines": [[[round(x, 2), round(y, 2)] for x, y in pl] for pl in lines]})
        print(f"{part['name']}: {len(lines)} edges", flush=True)
    order = spec.get("painter") or [p["name"] for p in sorted(parts, key=lambda p: p["depth"])]
    parts.sort(key=lambda p: order.index(p["name"]))
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    remote = subprocess.run(["git", "-C", str(source), "remote", "get-url", "origin"], capture_output=True,
                            text=True).stdout.strip()
    spec["source"] = {"repo": remote.rsplit("github.com", 1)[-1].lstrip(":/").removesuffix(".git"), "commit": commit,
                      "inputs": inputs}
    spec["parts"] = parts
    spec_path.write_text(json.dumps(spec, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {spec_path} ({spec_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
