#!/usr/bin/env python3
"""Animated README banners: a hero for the top of a repo's README and a mini card for profile listings.

    python3 tools/hero/heroes.py                      # write every banner in banners.json that lives in this repo
    python3 tools/hero/heroes.py --check              # exit 1 if a committed banner differs or breaks a rule
    python3 tools/hero/heroes.py val-ark --repo mvalancy/val-ark=../val-ark      # write a banner into another repo
    python3 tools/hero/heroes.py --check --repo mvalancy/val-ark=../val-ark        # and check it there
    python3 tools/hero/heroes.py --extract catalog --source ../val-ark --out tools/hero/motifs/val-ark.catalog.json
    python3 tools/hero/heroes.py --extract lines --source ../linux_tools/README.md --out tools/hero/motifs/x.lines.json
    python3 tools/hero/heroes.py --sample hero > /tmp/sample.svg          # render a throwaway banner (tests use this)

Every banner is an entry in ``tools/hero/banners.json``: its name (drawn large), a tagline, a palette, facts shown
as chips, and a motif drawn from the project's real content where one exists (a CAD assembly traced from its STEP
files by ``extract_cad.py``, its catalogue, its constants). Each banner is written twice, ``<out>-light.svg`` and
``<out>-dark.svg``, for a ``<picture>`` element whose ``prefers-color-scheme`` sources follow GitHub's theme.

Rendering needs only the Python standard library and is deterministic: the same inputs give the same bytes. Text is
drawn from vendored glyph outlines (``glyphs.json``, Space Grotesk, OFL-1.1), so it looks the same everywhere and
needs no font. Banners animate with CSS keyframes only: no script, no SMIL, no external reference. Under
``prefers-reduced-motion`` every animation stops and each element shows its base style, which is the final frame.
``problems()`` lists the rules a banner must pass: valid XML, a labelled ``role="img"`` root with a title, no script,
event handler, foreignObject, image or external reference, the reduced-motion rule, and the size budget (150 KB for a
hero, 30 KB for a card).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
THIS_REPO = "mvalancy/mvalancy"
BUDGET = {"hero": 150_000, "card": 30_000}
REDUCED_MOTION = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
SIZES = {"hero": (1200, 440), "card": (600, 200)}

# ------------------------------------------------------------------------------------------------ palettes

BASE = {
    "light": {"bg": "#ffffff", "bg2": "#f3f6f9", "ink": "#1f2328", "muted": "#59636e", "line": "#d6dde4",
              "edge": "#24323d", "glow": ".16", "f1": "#eef2f5", "f2": "#e3e9ee", "f3": "#f7f9fb", "dk": "#3a4744"},
    "dark": {"bg": "#0d1117", "bg2": "#131b26", "ink": "#e6edf3", "muted": "#9198a1", "line": "#2a3441",
             "edge": "#c9d6e2", "glow": ".22", "f1": "#18222e", "f2": "#1d2937", "f3": "#141c26", "dk": "#2b3540"},
}
ACCENTS = {  # name: (light a1, light a2, dark a1, dark a2)
    "teal": ("#0f766e", "#0369a1", "#2dd4bf", "#38bdf8"),
    "orange": ("#c2410c", "#b45309", "#fb923c", "#fbbf24"),
    "violet": ("#6d28d9", "#a21caf", "#a78bfa", "#f0abfc"),
    "blue": ("#1d4ed8", "#0e7490", "#60a5fa", "#22d3ee"),
    "green": ("#15803d", "#0f766e", "#4ade80", "#2dd4bf"),
    "rose": ("#be123c", "#c2410c", "#fb7185", "#fb923c"),
    "amber": ("#b45309", "#a16207", "#fbbf24", "#fde047"),
    "cyan": ("#0e7490", "#4338ca", "#22d3ee", "#818cf8"),
    "lime": ("#4d7c0f", "#0f766e", "#a3e635", "#34d399"),
    "gyropup": ("#bd3a12", "#287d8d", "#ff7a45", "#5cc8d6"),     # gyropup.com's --orange and --cyan
}


def palette(name: str, theme: str) -> dict:
    a = ACCENTS[name]
    p = dict(BASE[theme])
    p["a1"], p["a2"] = (a[0], a[1]) if theme == "light" else (a[2], a[3])
    return p


# ------------------------------------------------------------------------------------------------ numbers + paths

def n(v: float, d: int = 1) -> str:
    s = f"{v:.{d}f}".rstrip("0").rstrip(".") if d else f"{v:.0f}"
    if s in ("-0", ""):
        return "0"
    if s.startswith("0."):
        return s[1:]
    if s.startswith("-0."):
        return "-" + s[2:]
    return s


def _join(vals) -> str:
    out = ""
    for v in vals:
        out += v if (not out or v.startswith("-")) else " " + v
    return out


def poly(points, closed=False, d=1) -> str:
    """A compact path: absolute first point, then relative steps between rounded points, so rounding never drifts."""
    k = 10 ** d
    q = [(round(x * k), round(y * k)) for x, y in points]
    out = [q[0]]
    for p in q[1:]:
        if p != out[-1]:
            out.append(p)
    if len(out) < 2 and not closed:
        return ""
    s = "M" + _join([n(out[0][0] / k, d), n(out[0][1] / k, d)])
    if len(out) > 1:
        s += "l" + _join([v for a, b in zip(out, out[1:]) for v in (n((b[0] - a[0]) / k, d), n((b[1] - a[1]) / k, d))])
    return s + ("z" if closed else "")


def simplify(pts, tol):
    """Douglas-Peucker on an open polyline (drawing units)."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    best, idx = -1.0, 0
    for i, p in enumerate(pts[1:-1], 1):
        d = abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / L if L > 1e-9 else math.dist(p, a)
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def attr(s: str) -> str:
    return escape(s, {'"': "&quot;"})


class Rand:
    """A tiny deterministic generator (LCG), so pseudo-random motifs give the same bytes every run."""

    def __init__(self, seed):
        self.s = (sum(ord(c) * 131 ** i for i, c in enumerate(str(seed))) or 1) % 2 ** 31

    def __call__(self) -> float:
        self.s = (1103515245 * self.s + 12345) % 2 ** 31
        return self.s / 2 ** 31


# ------------------------------------------------------------------------------------------------ text from glyphs

_GLYPHS = None


def glyphs() -> dict:
    global _GLYPHS
    if _GLYPHS is None:
        _GLYPHS = json.loads((HERE / "glyphs.json").read_text(encoding="utf-8"))
    return _GLYPHS


class Doc:
    """Collects the glyphs, CSS and defs a banner uses while its body is built."""

    def __init__(self):
        self.used = {}
        self.css = []
        self.defs = []
        self.ids = 0

    def uid(self, stem: str) -> str:
        self.ids += 1
        return f"{stem}{self.ids}"

    def width(self, text: str, weight: str, size: float) -> float:
        g = glyphs()["weights"][weight]
        return sum(g.get(c, g[" "])[0] for c in text) * size / glyphs()["upm"]

    def uses(self, text: str, weight: str, extra=None) -> str:
        """``<use>`` elements for ``text`` in font units, from x = 0."""
        g = glyphs()["weights"][weight]
        x, out = 0, []
        for i, c in enumerate(text):
            adv, d = g.get(c, g[" "])
            if d:
                gid = weight[0] + str(ord(c))
                self.used[gid] = d
                more = extra(i) if extra else ""
                out.append(f'<use href="#{gid}" x="{x}"{more}/>')
            x += adv
        return "".join(out)

    def text(self, text, weight, size, x, y, cls="", fill=None) -> str:
        s = size / glyphs()["upm"]
        f = f' fill="{fill}"' if fill else ""
        c = f' class="{cls}"' if cls else ""
        return f'<g{c}{f} transform="translate({n(x)} {n(y)}) scale({n(s, 5)} {n(-s, 5)})">{self.uses(text, weight)}</g>'

    def glyph_defs(self) -> str:
        return "".join(f'<path id="{k}" d="{v}" pathLength="1"/>' for k, v in sorted(self.used.items()))


def wrap(doc: Doc, text: str, weight: str, size: float, width: float, max_lines: int):
    """Greedy word wrap; shrinks the size until the text fits in ``max_lines``."""
    while True:
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if doc.width(t, weight, size) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if len(lines) <= max_lines and all(doc.width(l, weight, size) <= width for l in lines) or size < 9:
            return lines, size
        size *= 0.94


# ------------------------------------------------------------------------------------------------ motifs
# Each motif draws into a box (x, y, w, h) and returns SVG markup; ``mini`` asks for the light card version.
# Elements that animate in carry ``class="in"`` plus a delay; their base style is their final state.

def _delay(t: float) -> str:
    return f' style="animation-delay:{n(t, 2)}s"'


def motif_cad(doc, data, box, mini, t0):
    """A real CAD assembly: each part's silhouette and visible edges, sliding in from its exploded position."""
    x, y, w, h = box
    if data.get("only_groups"):                     # e.g. one leg of a robot
        data = dict(data, parts=[p for p in data["parts"] if p.get("group") in data["only_groups"]], groups=None)
    pts = [p for part in data["parts"] for loop in part["outlines"] for p in loop]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx = min(w / (max(xs) - min(xs)), h / (max(ys) - min(ys))) * (0.9 if mini else 0.94)
    ox = x + (w - (max(xs) - min(xs)) * sx) / 2 - min(xs) * sx
    oy = y + (h - (max(ys) - min(ys)) * sx) / 2 - min(ys) * sx

    def tf(p):
        return (ox + p[0] * sx, oy + p[1] * sx)

    min_px = 14.0 if mini else 3.0
    digits = 0 if mini else 1                       # cards are small: whole pixels are enough
    fills = {"shell": "var(--f1)", "plate": "var(--f2)", "lid": "var(--f3)", "body": "var(--f1)", "accent": "var(--a1)",
             "dark": "var(--dk)"}
    sway = data.get("idle") == "balance" and not mini
    out = [f'<g class="cad{" sway" if sway else ""}"'
           + (f' style="transform-origin:{n(x + w / 2)}px {n(y + h)}px"' if sway else "") + ">"]
    groups = data.get("groups") or list(dict.fromkeys(part.get("group", i) for i, part in enumerate(data["parts"])))
    for i, part in enumerate(data["parts"]):
        lines = []
        for pl in part["lines"]:
            q = [tf(p) for p in pl]
            if sum(math.dist(a, b) for a, b in zip(q, q[1:])) >= min_px:
                lines.append(poly(simplify(q, 0.8 if mini else 0.5), d=digits))
        g = groups.index(part.get("group", i))
        fx, fy = part["from"][0] * sx, part["from"][1] * sx
        if g == 0:                                  # the first group is traced in by the scan line
            cls, style = "pt tr", _delay(t0)
        else:                                       # later groups slide in from where they start, one group at a time
            cls = "pt in"
            style = f' style="--fx:{n(fx)}px;--fy:{n(fy)}px;animation-delay:{n(t0 + 0.7 + 0.55 * (g - 1), 2)}s"'
        out.append(f'<g class="{cls}"{style}><path class="sil" fill="{fills[part["role"]]}" '
                   f'd="{"".join(poly(simplify([tf(p) for p in loop], 1.0) if mini else [tf(p) for p in loop], True, digits) for loop in part["outlines"])}"/>'
                   f'<path class="ed" d="{"".join(lines)}"/></g>')
    out.append("</g>")
    # a scan line sweeps the base as it is "traced", then idles
    out.append(f'<rect class="scan" x="{n(x)}" y="{n(y)}" width="3" height="{n(h)}" rx="1.5"{_delay(t0)}/>')
    doc.css.append(".cad .ed{fill:none;stroke:var(--edge);stroke-width:%s;stroke-linecap:round;stroke-linejoin:round;"
                   "opacity:.9}.cad .sil{stroke:var(--edge);stroke-width:%s;stroke-linejoin:round}"
                   ".cad .pt.in{animation:slide .9s cubic-bezier(.2,.8,.2,1) both}"
                   "@keyframes slide{from{transform:translate(var(--fx),var(--fy));opacity:0}to{opacity:1}}"
                   ".cad .pt.tr{animation:trace 1.2s ease-out both}"
                   "@keyframes trace{from{clip-path:inset(0 100%% 0 0)}to{clip-path:inset(0 0 0 0)}}"
                   ".scan{fill:var(--a1);opacity:0;animation:scan 1.2s ease-out both}"
                   "@keyframes scan{from{opacity:.9;transform:translateX(0)}to{opacity:0;transform:translateX(%spx)}}"
                   ".sway{animation:sway 5s 4.5s ease-in-out infinite}"
                   "@keyframes sway{0%%,100%%{transform:rotate(0)}30%%{transform:rotate(1.6deg)}70%%{transform:rotate(-1.4deg)}}"
                   % (n(0.9 if mini else 0.85, 2), n(1.2 if mini else 1.3, 2), n(w)))
    return "".join(out)


def motif_catalog(doc, data, box, mini, t0):
    """A disk filling itself from a real catalogue, diversity first, then serving it over wifi."""
    x, y, w, h = box
    items = data["items"]
    gw = w * (0.68 if not mini else 0.62)
    cols = 12 if mini else 16
    rows = math.ceil(len(items) / cols)
    gap = 2.0 if mini else 3.0
    cell = min((gw - gap * (cols - 1)) / cols, (h - 34 - gap * (rows - 1)) / rows)
    gx, gy = x + 4, y + (h - rows * (cell + gap) - 26) / 2 + 22
    colour = {"tool": "var(--a1)", "model": "var(--a2)", "installer": "var(--muted)"}
    out = [f'<rect class="disk" x="{n(gx - 8)}" y="{n(gy - 26)}" width="{n(cols * (cell + gap) + 14)}" '
           f'height="{n(rows * (cell + gap) + 34)}" rx="10"/>']
    span = 1.6 if mini else 2.4
    for r in range(rows):                           # a card pops a row at a time; a hero pops cell by cell
        row = items[r * cols:(r + 1) * cols]
        if mini:
            out.append(f'<g class="rw in"{_delay(t0 + span * r / rows)}>')
        for c, it in enumerate(row):
            i = r * cols + c
            cx, cy = gx + c * (cell + gap), gy + r * (cell + gap)
            out.append(f'<rect x="{n(cx)}" y="{n(cy)}" width="{n(cell)}" height="{n(cell)}" rx="{n(cell / 4)}" '
                       f'fill="{colour[it[0]]}"' + ("/>" if mini else f' class="cell in"{_delay(t0 + span * i / len(items))}/>'))
        if mini:
            out.append("</g>")
    bw = cols * (cell + gap) - gap
    out.append(f'<rect class="bar0" x="{n(gx)}" y="{n(gy - 16)}" width="{n(bw)}" height="6" rx="3"/>'
               f'<rect class="bar in" x="{n(gx)}" y="{n(gy - 16)}" width="{n(bw * 0.86)}" height="6" rx="3"'
               f'{_delay(t0)}/>')
    # wifi: an antenna and arcs pulsing outward
    ax, ay = x + w * (0.86 if not mini else 0.84), y + h * 0.5
    r0 = min(w * 0.05, 14)
    out.append(f'<circle class="ant" cx="{n(ax)}" cy="{n(ay + r0 * 2.5)}" r="{n(r0 * 0.45)}"/>')
    for k in range(3):
        r = r0 * (1.6 + 1.25 * k)
        a = math.radians(42)
        p0 = (ax - r * math.sin(a), ay + r0 * 2.5 - r * math.cos(a))
        p1 = (ax + r * math.sin(a), ay + r0 * 2.5 - r * math.cos(a))
        out.append(f'<path class="arc" d="M{n(p0[0])} {n(p0[1])}A{n(r)} {n(r)} 0 0 1 {n(p1[0])} {n(p1[1])}" '
                   f'style="animation-delay:{n(t0 + span + 0.25 * k, 2)}s"/>')
    doc.css.append(".disk{fill:var(--bg2);stroke:var(--line)}.bar0{fill:var(--line)}.bar{fill:url(#gr);"
                   "transform-box:fill-box;transform-origin:0 0}.bar.in{animation:grow %ss ease-out both}"
                   "@keyframes grow{from{transform:scaleX(0)}}"
                   ".cell{transform-box:fill-box;transform-origin:50%% 50%%}.cell.in{animation:pop .35s ease-out both}.rw.in{animation:fade .4s both}"
                   "@keyframes pop{from{transform:scale(0);opacity:0}}"
                   ".ant{fill:var(--a1)}.arc{fill:none;stroke:var(--a1);stroke-width:%s;stroke-linecap:round;"
                   "animation:wave 2.4s ease-out infinite}"
                   "@keyframes wave{0%%{opacity:.15}30%%{opacity:1}100%%{opacity:.15}}"
                   % (n(span, 2), n(2.2 if mini else 3, 1)))
    return "".join(out)


def motif_eye(doc, data, box, mini, t0):
    """A talking eyeball on a stick: pans, tilts and zooms over its real ranges, blinks, and talks."""
    x, y, w, h = box
    cx, r = x + w * 0.42, min(w * 0.3, h * 0.3)
    cy = y + r + h * 0.06
    base_y = y + h - 6
    gid = doc.uid("eg")
    doc.defs.append(f'<radialGradient id="{gid}" cx=".38" cy=".32" r=".75"><stop offset="0" stop-color="#ffffff"/>'
                    f'<stop offset=".7" stop-color="#e9eef3"/><stop offset="1" stop-color="#b9c4cf"/></radialGradient>')
    out = [f'<ellipse class="puck" cx="{n(cx)}" cy="{n(base_y - r * 0.12)}" rx="{n(r * 0.95)}" ry="{n(r * 0.22)}"/>',
           f'<rect class="stick" x="{n(cx - r * 0.09)}" y="{n(cy + r * 0.8)}" width="{n(r * 0.18)}" '
           f'height="{n(base_y - r * 0.2 - cy - r * 0.8)}" rx="{n(r * 0.06)}"/>',
           f'<g class="head"><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="url(#{gid})" class="ball"/>'
           f'<g class="look" style="transform-origin:{n(cx)}px {n(cy)}px">'
           f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r * 0.42)}" class="iris"/>'
           f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r * 0.2)}" class="pupil" style="transform-origin:{n(cx)}px {n(cy)}px"/>'
           f'<circle cx="{n(cx - r * 0.13)}" cy="{n(cy - r * 0.14)}" r="{n(r * 0.07)}" fill="#fff"/></g>'
           f'<rect class="lid" x="{n(cx - r)}" y="{n(cy - r)}" width="{n(2 * r)}" height="{n(2 * r)}" '
           f'style="transform-origin:{n(cx)}px {n(cy - r)}px" clip-path="url(#{gid}c)"/></g>']
    doc.defs.append(f'<clipPath id="{gid}c"><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}"/></clipPath>')
    # talking: a speech bubble of level bars
    bx, by = x + w * 0.72, y + h * 0.18
    bw, bh = w * 0.27, h * 0.26
    out.append(f'<path class="bub in" d="M{n(bx)} {n(by)}h{n(bw)}a8 8 0 0 1 8 8v{n(bh - 16)}a8 8 0 0 1-8 8h-{n(bw - 16)}'
               f'l-14 12 2-12h-{n(2)}a8 8 0 0 1-8-8v-{n(bh - 16)}a8 8 0 0 1 8-8z"{_delay(t0 + 0.8)}/>')
    nb = 5 if mini else 7
    for k in range(nb):
        hx = bx + 6 + (k + 0.5) * (bw - 12) / nb
        out.append(f'<rect class="lvl" x="{n(hx - 2)}" y="{n(by + bh * 0.25)}" width="4" height="{n(bh * 0.5)}" rx="2" '
                   f'style="transform-origin:{n(hx)}px {n(by + bh / 2 + 4)}px;animation-delay:{n(t0 + 1 + k * 0.13, 2)}s"/>')
    pan = data.get("pan", 1.0)
    zoom = data.get("zoom", [100, 500])
    dil = 1 + 0.45 * (zoom[1] - zoom[0]) / zoom[1]
    dx, dy = r * 0.42 * pan, r * 0.3
    doc.css.append(".puck{fill:var(--edge);opacity:.85}.stick{fill:var(--edge);opacity:.75}"
                   ".ball{stroke:var(--edge);stroke-width:1.5}.iris{fill:var(--a1)}.pupil{fill:#0b1016}"
                   ".lid{fill:var(--edge);transform:scaleY(0);animation:blink 6s %ss infinite}"
                   "@keyframes blink{0%%,92%%,100%%{transform:scaleY(0)}95%%{transform:scaleY(1)}}"
                   ".look{animation:look 9s %ss ease-in-out infinite}"
                   "@keyframes look{0%%,100%%{transform:translate(0,0)}14%%,24%%{transform:translate(-%spx,-%spx)}"
                   "38%%,48%%{transform:translate(%spx,-%spx)}62%%,72%%{transform:translate(%spx,%spx)}"
                   "84%%{transform:translate(-%spx,%spx)}}"
                   ".pupil{animation:zoom 9s %ss ease-in-out infinite}"
                   "@keyframes zoom{0%%,36%%,100%%{transform:scale(1)}44%%,56%%{transform:scale(%s)}}"
                   ".bub{fill:var(--bg2);stroke:var(--line);stroke-width:1.5}.bub.in{animation:fade .5s both}"
                   ".lvl{fill:var(--a2);animation:talk .9s ease-in-out infinite alternate}"
                   "@keyframes talk{from{transform:scaleY(.25)}to{transform:scaleY(1)}}"
                   % (n(t0 + 2.4, 2), n(t0 + 0.6, 2), n(dx), n(dy * 0.6), n(dx), n(dy * 0.4), n(dx * 0.6),
                      n(dy * 0.5), n(dx * 0.8), n(dy * 0.3), n(t0 + 0.6, 2), n(dil, 2)))
    return "".join(out)


def motif_face(doc, data, box, mini, t0):
    """A robot face on a screen: two big eyes that look around and blink, inside a ghostly glow."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    rw, rh = min(w * 0.4, h * 0.5), min(h * 0.38, w * 0.36)      # the halo (x1.2) stays inside the box
    out = [f'<ellipse class="halo" cx="{n(cx)}" cy="{n(cy)}" rx="{n(rw * 1.18)}" ry="{n(rh * 1.22)}"/>',
           f'<rect class="scr" x="{n(cx - rw)}" y="{n(cy - rh)}" width="{n(2 * rw)}" height="{n(2 * rh)}" rx="{n(rh * 0.7)}"/>',
           '<g class="eyes">']
    for s in (-1, 1):
        ex = cx + s * rw * 0.42
        out.append(f'<ellipse class="fe" cx="{n(ex)}" cy="{n(cy - rh * 0.08)}" rx="{n(rw * 0.2)}" ry="{n(rh * 0.38)}" '
                   f'style="transform-origin:{n(ex)}px {n(cy)}px"/>')
    out.append('</g>')
    out.append(f'<path class="mouth" d="M{n(cx - rw * 0.22)} {n(cy + rh * 0.48)}q{n(rw * 0.22)} {n(rh * 0.2)} '
               f'{n(rw * 0.44)} 0"/>')
    doc.css.append(".halo{fill:var(--a1);opacity:.12;animation:breathe 4s ease-in-out infinite alternate}"
                   "@keyframes breathe{to{opacity:.24}}"
                   ".scr{fill:#0b1220;stroke:var(--a1);stroke-width:2}.fe{fill:var(--a2);animation:fblink 5s %ss infinite}"
                   "@keyframes fblink{0%%,90%%,100%%{transform:scaleY(1)}94%%{transform:scaleY(.08)}}"
                   ".eyes{animation:flook 8s ease-in-out infinite}"
                   "@keyframes flook{0%%,100%%{transform:none}25%%{transform:translateX(-%spx)}60%%{transform:translateX(%spx)}}"
                   ".mouth{fill:none;stroke:var(--a2);stroke-width:3;stroke-linecap:round}"
                   % (n(t0 + 1, 2), n(rw * 0.12), n(rw * 0.12)))
    return "".join(out)


def motif_terminal(doc, data, box, mini, t0):
    """A terminal typing out the project's real commands: each bar is one line of its README's first code block."""
    x, y, w, h = box
    lines = data.get("lines") or [28, 40, 18, 34, 22, 44, 16]
    rows = lines[: (6 if mini else 9)]
    longest = max(rows) or 1
    out = [f'<rect class="term" x="{n(x)}" y="{n(y + 4)}" width="{n(w)}" height="{n(h - 8)}" rx="10"/>',
           f'<path class="tbar" d="M{n(x)} {n(y + 26)}h{n(w)}"/>']
    for k, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        out.append(f'<circle cx="{n(x + 16 + k * 14)}" cy="{n(y + 15)}" r="4.5" fill="{c}"/>')
    lh = (h - 52) / len(rows)
    for i, L in enumerate(rows):
        ly = y + 40 + i * lh
        bw = (w - 46) * L / longest
        out.append(f'<rect class="pr" x="{n(x + 14)}" y="{n(ly)}" width="8" height="{n(min(lh * 0.5, 9))}" rx="2"/>'
                   f'<rect class="ln in" x="{n(x + 28)}" y="{n(ly)}" width="{n(max(bw, 6))}" height="{n(min(lh * 0.5, 9))}" '
                   f'rx="2"{_delay(t0 + 0.28 * i)}/>')
    ly = y + 40 + len(rows) * lh - lh
    out.append(f'<rect class="cur" x="{n(x + 32 + (w - 46) * rows[-1] / longest)}" y="{n(ly)}" width="7" '
               f'height="{n(min(lh * 0.5, 9))}"/>')
    doc.css.append(".term{fill:#0b1220;stroke:var(--line)}.tbar{stroke:#1e293b}.pr{fill:var(--a1)}"
                   ".ln{fill:#cbd5e1;opacity:.8;transform-box:fill-box;transform-origin:0 0}"
                   ".ln.in{animation:type .45s steps(8) both}@keyframes type{from{transform:scaleX(0)}}"
                   ".cur{fill:var(--a2);animation:cur 1s steps(1) infinite}@keyframes cur{50%{opacity:0}}")
    return "".join(out)


def motif_circuit(doc, data, box, mini, t0):
    """A chip with traces routed to pads; pulses run along the traces."""
    x, y, w, h = box
    rnd = Rand(data.get("seed", "pcb"))
    cx, cy = x + w / 2, y + h / 2
    cw, ch = min(w, h) * 0.34, min(w, h) * 0.34
    out = []
    traces = []
    pins = 4 if mini else 5
    for side in range(4):
        for k in range(pins):
            t = (k + 1) / (pins + 1)
            if side == 0:
                p0, d = (cx - cw / 2 + cw * t, cy - ch / 2), (0, -1)
            elif side == 1:
                p0, d = (cx + cw / 2, cy - ch / 2 + ch * t), (1, 0)
            elif side == 2:
                p0, d = (cx - cw / 2 + cw * t, cy + ch / 2), (0, 1)
            else:
                p0, d = (cx - cw / 2, cy - ch / 2 + ch * t), (-1, 0)
            l1 = 10 + rnd() * min(w, h) * 0.12
            p1 = (p0[0] + d[0] * l1, p0[1] + d[1] * l1)
            j = (rnd() - 0.5) * 2
            bend = (d[1] * j * 18, d[0] * j * 18)
            l2 = 8 + rnd() * min(w, h) * 0.14
            p2 = (p1[0] + d[0] * l2 * 0.7 + bend[0], p1[1] + d[1] * l2 * 0.7 + bend[1])
            p3 = (p2[0] + d[0] * l2, p2[1] + d[1] * l2)
            p3 = (min(max(p3[0], x + 8), x + w - 8), min(max(p3[1], y + 8), y + h - 8))
            traces.append([p0, p1, p2, p3])
    path = "".join(poly(t) for t in traces)
    out.append(f'<path class="tr" d="{path}"/>')
    for i, t in enumerate(traces[:: (3 if mini else 2)]):
        out.append(f'<path class="pulse" d="{poly(t)}" pathLength="1" style="animation-delay:{n(t0 + 0.37 * i % 3.1, 2)}s"/>')
    out.append("".join(f'<circle class="pad" cx="{n(t[-1][0])}" cy="{n(t[-1][1])}" r="3.4"/>' for t in traces))
    out.append(f'<rect class="chip in" x="{n(cx - cw / 2)}" y="{n(cy - ch / 2)}" width="{n(cw)}" height="{n(ch)}" rx="5"'
               f'{_delay(t0)}/><circle class="dot1" cx="{n(cx - cw / 2 + 9)}" cy="{n(cy - ch / 2 + 9)}" r="3"/>')
    doc.css.append(".tr{fill:none;stroke:var(--a1);stroke-width:2;stroke-linejoin:round;opacity:.45}"
                   ".pulse{fill:none;stroke:var(--a2);stroke-width:3;stroke-linecap:round;stroke-dasharray:.12 .88;"
                   "stroke-dashoffset:1;animation:run 2.6s linear infinite}@keyframes run{to{stroke-dashoffset:0}}"
                   ".pad{fill:var(--bg);stroke:var(--a1);stroke-width:2}"
                   ".chip{fill:var(--edge)}.chip.in{animation:fade .6s both}.dot1{fill:var(--bg)}")
    return "".join(out)


def motif_chart(doc, data, box, mini, t0):
    """A live chart: a day of solar (``style: solar``) or per-outlet loads (``style: bars``)."""
    x, y, w, h = box
    style = data.get("style", "solar")
    out = [f'<path class="axis" d="M{n(x + 6)} {n(y + 8)}V{n(y + h - 10)}H{n(x + w - 4)}"/>']
    if style == "bars":
        vals = data.get("values") or [0.62, 0.35, 0.8, 0.18, 0.5, 0.72, 0.28, 0.44]
        bw = (w - 24) / len(vals)
        for i, v in enumerate(vals):
            bh = (h - 26) * v
            out.append(f'<rect class="b in" x="{n(x + 14 + i * bw)}" y="{n(y + h - 10 - bh)}" width="{n(bw * 0.66)}" '
                       f'height="{n(bh)}" rx="3" style="animation-delay:{n(t0 + 0.12 * i, 2)}s,{n(t0 + 1.4 + 0.3 * i, 2)}s"/>')
        doc.css.append(".b{fill:url(#gr);transform-box:fill-box;transform-origin:50% 100%}"
                       ".b.in{animation:rise .7s ease-out both,load 3.2s ease-in-out infinite alternate}"
                       "@keyframes rise{from{transform:scaleY(0)}}@keyframes load{to{transform:scaleY(.72)}}")
    else:
        pts = []
        for i in range(41):
            t = i / 40
            v = math.exp(-((t - 0.5) / 0.19) ** 2) * (0.92 - 0.08 * math.sin(t * 19))
            pts.append((x + 8 + t * (w - 14), y + h - 12 - v * (h - 30)))
        bat = [(x + 8 + t / 40 * (w - 14), y + h - 12 - (h - 30) * (0.25 + 0.6 / (1 + math.exp(-(t / 40 - 0.55) * 12))))
               for t in range(41)]
        area = poly(pts + [(pts[-1][0], y + h - 10), (pts[0][0], y + h - 10)], True)
        out.append(f'<path class="area in" d="{area}"{_delay(t0 + 0.6)}/>'
                   f'<path class="line in" d="{poly(pts)}" pathLength="1"{_delay(t0)}/>'
                   f'<path class="line2 in" d="{poly(bat)}" pathLength="1"{_delay(t0 + 0.5)}/>'
                   f'<circle class="sun" cx="{n(x + w * 0.82)}" cy="{n(y + 20)}" r="{n(min(w, h) * 0.07)}"/>')
        doc.css.append(".area{fill:var(--a2);opacity:.18}.area.in{animation:fade 1s both}"
                       ".line{fill:none;stroke:var(--a2);stroke-width:3;stroke-linejoin:round;stroke-dasharray:1}"
                       ".line2{fill:none;stroke:var(--a1);stroke-width:2.5;stroke-dasharray:1}"
                       ".line.in,.line2.in{animation:draw 1.6s ease-out both}@keyframes draw{from{stroke-dashoffset:1}}"
                       ".sun{fill:var(--a2);animation:breathe 3s ease-in-out infinite alternate}"
                       "@keyframes breathe{to{opacity:.5}}")
    doc.css.append(".axis{fill:none;stroke:var(--line);stroke-width:2}")
    return "".join(out)


def motif_dial(doc, data, box, mini, t0):
    """A servo motor: a spinning rotor inside a speed gauge whose needle sweeps."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h * 0.56
    r = min(w, h) * 0.42
    ticks = []
    for i in range(13):
        a = math.radians(-210 + i * 20)
        ticks.append(poly([(cx + r * math.cos(a), cy + r * math.sin(a)), (cx + r * 0.86 * math.cos(a), cy + r * 0.86 * math.sin(a))]))
    a0, a1 = math.radians(-210), math.radians(30)
    arc = f'M{n(cx + r * 1.04 * math.cos(a0))} {n(cy + r * 1.04 * math.sin(a0))}A{n(r * 1.04)} {n(r * 1.04)} 0 1 1 ' \
          f'{n(cx + r * 1.04 * math.cos(a1))} {n(cy + r * 1.04 * math.sin(a1))}'
    rr = r * 0.48
    spokes = "".join(poly([(cx, cy), (cx + rr * math.cos(math.radians(k * 60)), cy + rr * math.sin(math.radians(k * 60)))])
                     for k in range(6))
    out = [f'<path class="garc" d="{arc}" pathLength="1"/>', f'<path class="tick" d="{"".join(ticks)}"/>',
           f'<g class="rotor" style="transform-origin:{n(cx)}px {n(cy)}px"><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(rr)}" '
           f'class="rim"/><path class="spk" d="{spokes}"/></g>',
           f'<path class="needle" d="M{n(cx)} {n(cy)}L{n(cx + r * 0.8 * math.cos(a0))} {n(cy + r * 0.8 * math.sin(a0))}" '
           f'style="transform-origin:{n(cx)}px {n(cy)}px"/><circle cx="{n(cx)}" cy="{n(cy)}" r="5" class="hub"/>']
    doc.css.append(".garc{fill:none;stroke:url(#gr);stroke-width:6;stroke-linecap:round;stroke-dasharray:1;"
                   "animation:draw 1.4s %ss ease-out both}@keyframes draw{from{stroke-dashoffset:1}}"
                   ".tick{stroke:var(--muted);stroke-width:2}.rim{fill:var(--f2);stroke:var(--edge);stroke-width:2}"
                   ".spk{stroke:var(--edge);stroke-width:2.5;stroke-linecap:round}"
                   ".rotor{animation:spin 2.2s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}"
                   ".needle{stroke:var(--a1);stroke-width:3.5;stroke-linecap:round;transform:rotate(170deg);"
                   "animation:needle 5s %ss ease-in-out infinite alternate}"
                   "@keyframes needle{0%%{transform:rotate(0)}100%%{transform:rotate(225deg)}}.hub{fill:var(--a1)}"
                   % (n(t0, 2), n(t0, 2)))
    return "".join(out)


def motif_slides(doc, data, box, mini, t0):
    """Lesson slides fanning out, each with a heading and bullet lines."""
    x, y, w, h = box
    sw, sh = w * 0.62, h * 0.62
    out = []
    for k in range(3):
        sx, sy = x + w * 0.08 + k * w * 0.13, y + h * 0.06 + k * h * 0.12
        body = [f'<rect class="sl" x="{n(sx)}" y="{n(sy)}" width="{n(sw)}" height="{n(sh)}" rx="8"/>',
                f'<rect class="hd" x="{n(sx + 12)}" y="{n(sy + 12)}" width="{n(sw * 0.5)}" height="8" rx="4"/>']
        for j in range(3):
            body.append(f'<circle class="bu" cx="{n(sx + 16)}" cy="{n(sy + 34 + j * 15)}" r="3"/>'
                        f'<rect class="bl" x="{n(sx + 24)}" y="{n(sy + 31 + j * 15)}" width="{n(sw * (0.62 - 0.12 * j))}" '
                        f'height="6" rx="3"/>')
        out.append(f'<g class="sg in"{_delay(t0 + 0.35 * k)}>{"".join(body)}</g>')
    doc.css.append(".sl{fill:var(--bg);stroke:var(--line);stroke-width:1.5}.hd{fill:var(--a1)}.bu{fill:var(--a2)}"
                   ".bl{fill:var(--line)}.sg.in{animation:deal .6s cubic-bezier(.2,.8,.2,1) both}"
                   "@keyframes deal{from{transform:translate(-30px,20px) rotate(-6deg);opacity:0}}")
    return "".join(out)


def motif_linkage(doc, data, box, mini, t0):
    """A wheel-legged robot's five-bar leg stepping, solved from its real link lengths and foot path."""
    x, y, w, h = box
    L1, L2 = data["crank_mm"], data["link_mm"]
    (ecx, ecy), (erx, ery) = data["path_centre_mm"], data["path_radii_mm"]
    reach = L1 + L2
    s = min(w / (2.1 * (erx + L1 * 0.9)), h / (reach * 1.15))
    hx, hy = x + w / 2, y + h * 0.1
    frames = []
    N = 12
    for i in range(N):
        t = 2 * math.pi * i / N
        ex, ey = ecx + erx * math.cos(t), ecy + ery * math.sin(t)      # mm, y up, hip at origin
        d = math.hypot(ex, ey)
        base = math.atan2(ey, ex)
        off = math.acos(max(-1, min(1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))))
        frames.append((ex, ey, base + off, base - off))
    def P(mx, my):
        return hx + mx * s, hy - my * s

    def kf(name, fn):
        steps = "".join(f"{n(100 * i / N, 2)}%{{transform:{fn(f)}}}" for i, f in enumerate(frames + frames[:1]))
        return f"@keyframes {name}{{{steps.replace(n(100 * N / N, 2) + '%', '100%')}}}"

    def ang(a):
        return math.degrees(-a)
    css = [kf("ck1", lambda f: f"rotate({n(ang(f[2]), 1)}deg)"), kf("ck2", lambda f: f"rotate({n(ang(f[3]), 1)}deg)")]
    for j, k in ((2, "lk1"), (3, "lk2")):
        def fn(f, j=j):
            kx, ky = L1 * math.cos(f[j]), L1 * math.sin(f[j])
            a = math.atan2(f[1] - ky, f[0] - kx)
            return f"translate({n(kx * s)}px,{n(-ky * s)}px) rotate({n(ang(a), 1)}deg)"
        css.append(kf(k, fn))
    css.append(kf("ft", lambda f: f"translate({n(f[0] * s)}px,{n(-f[1] * s)}px)"))
    trace = poly([P(ecx + erx * math.cos(2 * math.pi * i / 48), ecy + ery * math.sin(2 * math.pi * i / 48)) for i in range(48)], True)
    lw = 9 if not mini else 7
    f0 = frames[0]
    out = [f'<path class="trace" d="{trace}"/>',
           f'<rect class="body" x="{n(hx - w * 0.2)}" y="{n(hy - h * 0.09)}" width="{n(w * 0.4)}" height="{n(h * 0.14)}" rx="8"/>',
           f'<g transform="translate({n(hx)} {n(hy)})">']
    for k, cls in (("lk1", "l2"), ("lk2", "l2")):
        out.append(f'<g class="{k}"><rect class="{cls}" x="0" y="{n(-lw / 2)}" width="{n(L2 * s)}" height="{lw}" rx="{n(lw / 2)}"/></g>')
    for k in ("ck1", "ck2"):
        out.append(f'<g class="{k}"><rect class="l1" x="0" y="{n(-lw / 2)}" width="{n(L1 * s)}" height="{lw}" rx="{n(lw / 2)}"/>'
                   f'<circle class="j" cx="{n(L1 * s)}" cy="0" r="{n(lw * 0.3)}"/></g>')
    wr = min(w, h) * 0.11
    out.append(f'<g class="ft"><circle class="wheel" cx="0" cy="0" r="{n(wr)}"/>'
               f'<path class="spoke" d="M{n(-wr * 0.7)} 0h{n(wr * 1.4)}M0 {n(-wr * 0.7)}v{n(wr * 1.4)}"/></g>'
               f'<circle class="hip" cx="0" cy="0" r="{n(lw * 0.75)}"/></g>')
    del f0
    doc.css.append("".join(css) + ".trace{fill:none;stroke:var(--a2);stroke-width:2;stroke-dasharray:5 5;opacity:.7}"
                   ".body{fill:var(--f2);stroke:var(--edge);stroke-width:2}.l1{fill:var(--a1)}.l2{fill:var(--edge);opacity:.8}"
                   ".j{fill:var(--bg)}.hip{fill:var(--edge)}.wheel{fill:var(--f1);stroke:var(--edge);stroke-width:3}"
                   ".spoke{stroke:var(--edge);stroke-width:2.5}"
                   ".ck1{animation:ck1 3s linear infinite}.ck2{animation:ck2 3s linear infinite}"
                   ".lk1{animation:lk1 3s linear infinite}.lk2{animation:lk2 3s linear infinite}"
                   ".ft{animation:ft 3s linear infinite}"
                   + _static_pose(frames[0], L1, s))
    return "".join(out)


def _static_pose(f, L1, s):
    """Base transforms (the reduced-motion still) for the linkage: its first frame."""
    def ang(a):
        return math.degrees(-a)
    out = f".ck1{{transform:rotate({n(ang(f[2]), 1)}deg)}}.ck2{{transform:rotate({n(ang(f[3]), 1)}deg)}}"
    for j, k in ((2, "lk1"), (3, "lk2")):
        kx, ky = L1 * math.cos(f[j]), L1 * math.sin(f[j])
        a = math.atan2(f[1] - ky, f[0] - kx)
        out += f".{k}{{transform:translate({n(kx * s)}px,{n(-ky * s)}px) rotate({n(ang(a), 1)}deg)}}"
    out += f".ft{{transform:translate({n(f[0] * s)}px,{n(-f[1] * s)}px)}}"
    return out


def motif_wave(doc, data, box, mini, t0):
    """Generated audio: a waveform of level bars that plays."""
    x, y, w, h = box
    nb = 22 if mini else 40
    bw = w / nb
    rnd = Rand(data.get("seed", "wave"))
    out = []
    for i in range(nb):
        env = 0.25 + 0.75 * abs(math.sin(i / nb * math.pi * 2.3 + 0.4)) * (0.6 + 0.4 * rnd())
        bh = (h - 20) * env
        bx = x + i * bw + bw * 0.2
        out.append(f'<rect class="wv" x="{n(bx)}" y="{n(y + h / 2 - bh / 2)}" width="{n(bw * 0.6)}" height="{n(bh)}" '
                   f'rx="{n(bw * 0.3)}" style="animation-delay:{n(t0 + (i * 0.07) % 1.3, 2)}s"/>')
    doc.css.append(".wv{fill:url(#gr);transform-box:fill-box;transform-origin:50% 50%;"
                   "animation:play 1.3s ease-in-out infinite alternate}@keyframes play{from{transform:scaleY(.3)}}")
    return "".join(out)


def motif_crystal(doc, data, box, mini, t0):
    """A crystal creature floating over a network of glowing nodes."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h * 0.46
    r = min(w, h) * 0.3
    rnd = Rand(data.get("seed", "graphlings"))
    nodes = [(x + 10 + rnd() * (w - 20), y + 10 + rnd() * (h - 20)) for _ in range(7 if mini else 11)]
    edges = "".join(poly([nodes[i], nodes[(i * 3 + 1) % len(nodes)]]) for i in range(len(nodes)))
    out = [f'<path class="net" d="{edges}"/>']
    for i, (px, py) in enumerate(nodes):
        out.append(f'<circle class="nd" cx="{n(px)}" cy="{n(py)}" r="3.5" style="animation-delay:{n(0.3 * i % 2.4, 2)}s"/>')
    top, bot = (cx, cy - r * 1.25), (cx, cy + r * 1.1)
    L, R = (cx - r * 0.8, cy - r * 0.15), (cx + r * 0.8, cy - r * 0.15)
    ML, MR = (cx - r * 0.3, cy + r * 0.1), (cx + r * 0.3, cy + r * 0.1)
    gid = doc.uid("cg")
    doc.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--a2)"/>'
                    f'<stop offset="1" stop-color="var(--a1)"/></linearGradient>')
    facets = [poly([top, L, ML], True), poly([top, ML, MR], True), poly([top, MR, R], True),
              poly([L, bot, ML], True), poly([ML, bot, MR], True), poly([MR, bot, R], True)]
    body = "".join(f'<path class="fc fc{i % 3}" d="{f}"/>' for i, f in enumerate(facets))
    eyes = "".join(f'<ellipse class="ce" cx="{n(cx + s * r * 0.2)}" cy="{n(cy + r * 0.05)}" rx="{n(r * 0.07)}" '
                   f'ry="{n(r * 0.12)}"/>' for s in (-1, 1))
    out.append(f'<ellipse class="shadow" cx="{n(cx)}" cy="{n(y + h - 10)}" rx="{n(r * 0.7)}" ry="{n(r * 0.12)}"/>'
               f'<g class="float"><g fill="url(#{gid})">{body}</g>{eyes}</g>')
    doc.css.append(".net{fill:none;stroke:var(--a1);stroke-width:1.3;opacity:.35}.nd{fill:var(--a2);"
                   "animation:glow 2.4s ease-in-out infinite alternate}@keyframes glow{from{opacity:.25}}"
                   ".fc{stroke:var(--bg);stroke-width:1.5;stroke-linejoin:round}.fc1{opacity:.85}.fc2{opacity:.7}"
                   ".ce{fill:#0b1016}.shadow{fill:var(--edge);opacity:.15}"
                   ".float{animation:float 3.6s ease-in-out infinite alternate}@keyframes float{to{transform:translateY(-8px)}}")
    return "".join(out)


def motif_radar(doc, data, box, mini, t0):
    """A radar sweep over a map: targets appear, are fused and tracked."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    r = min(w, h) * 0.46
    rings = "".join(f'<circle class="rg" cx="{n(cx)}" cy="{n(cy)}" r="{n(r * k / 3)}"/>' for k in (1, 2, 3))
    gid = doc.uid("rw")
    doc.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--a1)" '
                    f'stop-opacity="0"/><stop offset="1" stop-color="var(--a1)" stop-opacity=".55"/></linearGradient>')
    a = math.radians(50)
    wedge = f'M{n(cx)} {n(cy)}L{n(cx + r * math.cos(-a))} {n(cy + r * math.sin(-a))}A{n(r)} {n(r)} 0 0 1 {n(cx + r)} {n(cy)}z'
    out = [rings, f'<path class="cross" d="M{n(cx - r)} {n(cy)}h{n(2 * r)}M{n(cx)} {n(cy - r)}v{n(2 * r)}"/>',
           f'<g class="sweep" style="transform-origin:{n(cx)}px {n(cy)}px"><path d="{wedge}" fill="url(#{gid})"/>'
           f'<path class="beam" d="M{n(cx)} {n(cy)}h{n(r)}"/></g>']
    rnd = Rand(data.get("seed", "tritium"))
    pts = []
    for i in range(5 if mini else 7):
        ang, rad = rnd() * 2 * math.pi, r * (0.3 + 0.62 * rnd())
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang), ang))
    for i, (px, py, ang) in enumerate(pts):
        d = ((math.degrees(ang)) % 360) / 360 * 4
        out.append(f'<circle class="blip" cx="{n(px)}" cy="{n(py)}" r="4" style="animation-delay:{n(d, 2)}s"/>')
    out.append(f'<path class="fuse" d="{poly([p[:2] for p in pts[:3]], True)}" pathLength="1"/>')
    doc.css.append(".rg{fill:none;stroke:var(--a1);stroke-width:1.2;opacity:.4}.cross{stroke:var(--a1);opacity:.25}"
                   ".beam{stroke:var(--a1);stroke-width:2}.sweep{animation:spin 4s linear infinite}"
                   "@keyframes spin{to{transform:rotate(360deg)}}"
                   ".blip{fill:var(--a2);animation:blip 4s linear infinite}"
                   "@keyframes blip{0%{opacity:1;r:6px}40%{opacity:.35;r:4px}100%{opacity:.15}}"
                   ".fuse{fill:none;stroke:var(--a2);stroke-width:1.6;stroke-dasharray:1;"
                   "animation:draw 4s ease-in-out infinite alternate}@keyframes draw{from{stroke-dashoffset:1}}")
    return "".join(out)


def motif_fight(doc, data, box, mini, t0):
    """Two animal fighters squaring off: lunges, an impact burst and draining health bars."""
    x, y, w, h = box
    gy = y + h * 0.62
    r = min(w * 0.17, h * 0.26)

    def critter(cx, s, cls, ear):
        ears = (f'<path d="M{n(cx - r * 0.6)} {n(gy - r * 0.6)}l{n(r * 0.1)}-{n(r * 0.75)} {n(r * 0.4)} {n(r * 0.45)}z'
                f'M{n(cx + r * 0.6)} {n(gy - r * 0.6)}l-{n(r * 0.1)}-{n(r * 0.75)}-{n(r * 0.4)} {n(r * 0.45)}z"/>') if ear == "pointy" else \
            (f'<ellipse cx="{n(cx - r * 0.75)}" cy="{n(gy - r * 0.35)}" rx="{n(r * 0.28)}" ry="{n(r * 0.5)}"/>'
             f'<ellipse cx="{n(cx + r * 0.75)}" cy="{n(gy - r * 0.35)}" rx="{n(r * 0.28)}" ry="{n(r * 0.5)}"/>')
        face = (f'<circle cx="{n(cx)}" cy="{n(gy)}" r="{n(r)}"/>'
                f'<circle class="fey" cx="{n(cx + s * r * 0.35)}" cy="{n(gy - r * 0.15)}" r="{n(r * 0.14)}"/>'
                f'<circle class="fey" cx="{n(cx + s * r * 0.0)}" cy="{n(gy - r * 0.15)}" r="{n(r * 0.14)}"/>'
                f'<path class="brow" d="M{n(cx - r * 0.2)} {n(gy - r * 0.42)}l{n(r * 0.75)} {n(s * r * 0.18)}"/>')
        return f'<g class="{cls}">{ears}{face}</g>'
    lx, rx = x + w * 0.26, x + w * 0.74
    out = [f'<ellipse class="arena" cx="{n(x + w / 2)}" cy="{n(gy + r * 1.05)}" rx="{n(w * 0.46)}" ry="{n(h * 0.08)}"/>',
           critter(lx, 1, "fl", "pointy"), critter(rx, -1, "fr", "round")]
    bx, by = x + w / 2, gy - r * 0.2
    star = []
    for k in range(16):
        rr = r * (0.55 if k % 2 else 0.25)
        a = math.pi * k / 8
        star.append((bx + rr * math.cos(a), by + rr * math.sin(a)))
    out.append(f'<path class="pow" d="{poly(star, True)}" style="transform-origin:{n(bx)}px {n(by)}px"/>')
    for k, (hx, cls) in enumerate(((x + 8, "hp1"), (x + w * 0.56, "hp2"))):
        out.append(f'<rect class="hp0" x="{n(hx)}" y="{n(y + 8)}" width="{n(w * 0.42)}" height="8" rx="4"/>'
                   f'<rect class="hp {cls}" x="{n(hx)}" y="{n(y + 8)}" width="{n(w * 0.42)}" height="8" rx="4"/>')
    doc.css.append(".arena{fill:var(--edge);opacity:.12}.fl{fill:var(--a1)}.fr{fill:var(--a2)}.fey{fill:#0b1016}"
                   ".brow{stroke:#0b1016;stroke-width:3;stroke-linecap:round}"
                   ".fl{animation:lunge 2.4s ease-in-out infinite}.fr{animation:lunge2 2.4s ease-in-out infinite}"
                   "@keyframes lunge{0%,100%{transform:none}40%{transform:translateX(" + n(w * 0.08) + "px)}"
                   "55%{transform:translateX(-" + n(w * 0.03) + "px)}}"
                   "@keyframes lunge2{0%,40%,100%{transform:none}45%{transform:translateX(" + n(w * 0.05) + "px) rotate(8deg)}"
                   "70%{transform:translateX(-" + n(w * 0.08) + "px)}}"
                   ".pow{fill:#facc15;stroke:#ea580c;stroke-width:2;transform:scale(0);animation:pow 2.4s infinite}"
                   "@keyframes pow{0%,38%{transform:scale(0)}44%{transform:scale(1.15)}56%,100%{transform:scale(0)}}"
                   ".hp0{fill:var(--line)}.hp{transform-box:fill-box;transform-origin:0 0}.hp1{fill:var(--a1)}.hp2{fill:var(--a2)}"
                   ".hp1{animation:hp 9.6s steps(4) infinite}.hp2{animation:hp 9.6s 1.2s steps(4) infinite}"
                   "@keyframes hp{to{transform:scaleX(.2)}}")
    return "".join(out)


def motif_network(doc, data, box, mini, t0):
    """A constellation of projects: nodes light up and pulses travel along the links between them."""
    x, y, w, h = box
    rnd = Rand(data.get("seed", "net"))
    k = data.get("nodes", 14)
    pts = []
    for i in range(k):
        a = 2 * math.pi * i / k + rnd() * 0.5
        rad = 0.35 + 0.6 * rnd()
        pts.append((x + w / 2 + math.cos(a) * w * 0.45 * rad, y + h / 2 + math.sin(a) * h * 0.45 * rad))
    links = []
    for i, p in enumerate(pts):
        near = sorted(range(k), key=lambda j: math.dist(p, pts[j]))[1:3]
        for j in near:
            if (j, i) not in links:
                links.append((i, j))
    out = [f'<path class="lk" d="{"".join(poly([pts[i], pts[j]]) for i, j in links)}"/>']
    for m, (i, j) in enumerate(links[::2]):
        out.append(f'<path class="pl" d="{poly([pts[i], pts[j]])}" pathLength="1" style="animation-delay:{n(t0 + 0.41 * m % 3, 2)}s"/>')
    for i, (px, py) in enumerate(pts):
        rr = 5 + 7 * rnd()
        out.append(f'<circle class="nn in" cx="{n(px)}" cy="{n(py)}" r="{n(rr)}" fill="{"var(--a1)" if i % 2 else "var(--a2)"}"'
                   f'{_delay(t0 + 0.08 * i)}/>')
    doc.css.append(".lk{fill:none;stroke:var(--line);stroke-width:1.6}"
                   ".pl{fill:none;stroke:var(--a2);stroke-width:2.6;stroke-linecap:round;stroke-dasharray:.2 .8;"
                   "stroke-dashoffset:1;animation:run 3s linear infinite}@keyframes run{to{stroke-dashoffset:0}}"
                   ".nn{transform-box:fill-box;transform-origin:50% 50%}.nn.in{animation:pop .5s ease-out both}"
                   "@keyframes pop{from{transform:scale(0)}}")
    return "".join(out)


MOTIFS = {"cad": motif_cad, "catalog": motif_catalog, "eye": motif_eye, "face": motif_face, "terminal": motif_terminal,
          "circuit": motif_circuit, "chart": motif_chart, "dial": motif_dial, "slides": motif_slides,
          "linkage": motif_linkage, "wave": motif_wave, "crystal": motif_crystal, "radar": motif_radar,
          "fight": motif_fight, "network": motif_network}


def motif_data(spec: dict) -> dict:
    m = dict(spec.get("motif") or {"kind": "network"})
    if "data" in m:
        m.update(json.loads((HERE / m["data"]).read_text(encoding="utf-8")))
    return m


# ------------------------------------------------------------------------------------------------ the banner

def _sketch_title(doc, title, x0, base, s, adv, mini):
    """The name grows from a drafting sketch: a faint graph-paper grid appears, guide lines (baseline, x-height,
    cap height, descender) and a box per letter are drafted, each letter's outline is drawn as a thin construction
    stroke, the strokes gain weight, the letters fill and solidify, and the grid and construction fade away. The
    base style of every element is the finished wordmark, so reduced motion shows only the final name.
    Returns (svg, css, time the name is done)."""
    G = glyphs()
    upm, asc, desc, cap, xh = G["upm"], G["asc"], G["desc"], G["cap"], G["xheight"]
    tr = f"translate({n(x0)} {n(base)}) scale({n(s, 5)} {n(-s, 5)})"
    g = G["weights"]["bold"]
    t0, stagger, dur = (0.15, 0.035, 1.5) if mini else (0.25, 0.05, 2.1)
    t_end = t0 + 0.3 + stagger * (len(title) - 1) + dur            # the last letter is solid
    # graph paper behind the name, aligned to its left edge and baseline
    cell = 8 if mini else 12
    gx0, gx1 = x0 - cell, x0 + adv * s + cell
    gy0, gy1 = base - asc * s * 0.92, base - desc * s + cell * 0.5
    minor = "".join(f"M{k * cell} 0V{cell * 5}M0 {k * cell}H{cell * 5}" for k in range(5))
    doc.defs.append(f'<pattern id="gp" width="{cell * 5}" height="{cell * 5}" patternUnits="userSpaceOnUse" '
                    f'x="{n(x0)}" y="{n(base)}"><path d="{minor}" stroke="var(--a2)" stroke-width=".5" opacity=".45"/>'
                    f'<path d="M0 0V{cell * 5}M0 0H{cell * 5}" stroke="var(--a2)" stroke-width="1"/></pattern>')
    out = [f'<rect class="gp" x="{n(gx0)}" y="{n(gy0)}" width="{n(gx1 - gx0)}" height="{n(gy1 - gy0)}" fill="url(#gp)"/>']
    # construction: guide lines and a box per letter, in font units, with strokes kept at screen width
    con = []
    for k, yv in enumerate((0, xh, cap, desc)):
        con.append(f'<path class="gl" d="M{-int(upm * 0.12)} {yv}H{int(adv + upm * 0.12)}" '
                   f'style="animation-delay:{n(t0 + 0.06 * k, 2)}s"/>')
    x = 0
    for i, c in enumerate(title):
        a = g.get(c, g[" "])[0]
        if c != " ":
            con.append(f'<rect class="gb" x="{x}" y="{desc}" width="{a}" height="{cap - desc}" pathLength="1" '
                       f'style="animation-delay:{n(t0 + 0.15 + stagger * i, 2)}s"/>')
        x += a
    out.append(f'<g class="con" transform="{tr}">{"".join(con)}</g>')
    letters = doc.uses(title, "bold", lambda i: _delay(t0 + 0.3 + stagger * i))
    w_thin, w_bold, w_end = 0.9 / s, (2.6 if mini else 3.4) / s, 1.2 / s
    out.append(f'<g class="nm" transform="{tr}" fill="url(#ng)" stroke="url(#ng)" stroke-width="{n(w_end, 1)}">{letters}</g>')
    total = t_end + 0.4
    css = (f".nm use{{stroke-dasharray:1;stroke-dashoffset:0;animation:ink {n(dur, 2)}s cubic-bezier(.45,0,.2,1) both}}"
           f"@keyframes ink{{0%{{stroke-dashoffset:1;stroke-width:{n(w_thin, 1)}px;fill-opacity:0}}"
           f"42%{{stroke-dashoffset:0;stroke-width:{n(w_thin, 1)}px;fill-opacity:0}}"
           f"66%{{stroke-width:{n(w_bold, 1)}px;fill-opacity:.15}}100%{{stroke-width:{n(w_end, 1)}px;fill-opacity:1}}}}"
           f".gp{{opacity:0;animation:gp {n(total, 2)}s linear both}}"
           f"@keyframes gp{{0%{{opacity:0}}8%{{opacity:1}}70%{{opacity:1}}100%{{opacity:0}}}}"
           f".con path,.con rect{{fill:none;vector-effect:non-scaling-stroke}}"
           f".gl{{stroke:var(--a2);stroke-width:1;stroke-dasharray:6 4;opacity:0;transform-box:fill-box;transform-origin:0 0;"
           f"animation:gl {n(total - t0, 2)}s ease-out both}}"
           f"@keyframes gl{{0%{{opacity:.9;transform:scaleX(0)}}18%{{transform:scaleX(1)}}70%{{opacity:.8}}100%{{opacity:0}}}}"
           f".gb{{stroke:var(--muted);stroke-width:1;stroke-dasharray:1;opacity:0;animation:gb {n(dur + 0.4, 2)}s ease-out both}}"
           f"@keyframes gb{{0%{{opacity:.85;stroke-dashoffset:1}}30%{{opacity:.85;stroke-dashoffset:0}}"
           f"65%{{opacity:.55;stroke-dashoffset:0}}100%{{opacity:0;stroke-dashoffset:0}}}}")
    return "".join(out), css, t_end - 0.5



def render(spec: dict, theme: str) -> str:
    kind = spec.get("kind", "hero")
    W, H = SIZES[kind]
    pal = palette(spec.get("palette", "teal"), "light" if theme == "auto" else theme)
    doc = Doc()
    mini = kind == "card"
    title = spec.get("title", spec["name"])
    margin = 24 if mini else 48
    body = []

    # the name: as large as fits
    cap = glyphs()["cap"] / glyphs()["upm"]
    if mini:
        name_w, fs_max = W - margin * 2 - 212, 46
    else:
        name_w, fs_max = W - margin * 2, 150
    fs = min(fs_max, name_w / (doc.width(title, "bold", 1000) / 1000))
    base = margin + cap * fs + (2 if mini else 4)
    s = fs / glyphs()["upm"]
    adv = doc.width(title, "bold", glyphs()["upm"])
    tr = f"translate({n(margin)} {n(base)}) scale({n(s, 5)} {n(-s, 5)})"
    doc.defs.append(f'<linearGradient id="ng" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{n(adv, 0)}" y2="0">'
                    f'<stop offset="0" stop-color="var(--a1)"/><stop offset="1" stop-color="var(--a2)"/></linearGradient>')
    letters_svg, sketch_css, t_name = _sketch_title(doc, title, margin, base, s, adv, mini)
    body.append(letters_svg)
    if not mini:
        doc.defs.append(f'<clipPath id="nc" transform="{tr}">{doc.uses(title, "bold")}</clipPath>')
        body.append(f'<g clip-path="url(#nc)"><rect class="sh" x="{n(margin - 160)}" y="{n(margin - 10)}" width="120" '
                    f'height="{n(fs + 20)}" fill="#fff" transform="skewX(-20)"/></g>')

    # underline, tagline
    y = base + max(12 if mini else 22, 0.2 * fs + (4 if mini else 8))      # clear of descenders
    body.append(f'<rect class="ul" x="{n(margin)}" y="{n(y)}" width="{n(60 if mini else 132)}" height="{n(4 if mini else 6)}" '
                f'rx="3" fill="url(#gr)"/>')
    tsize, tmax = (17, 3) if mini else (27, 2)
    twidth = (W - margin * 2 - 212) if mini else 560
    lines, tsize = wrap(doc, spec.get("tagline", ""), "medium", tsize, twidth, tmax)
    y += (16 if mini else 24) + tsize * cap
    for i, line in enumerate(lines):
        body.append(f'<g class="tg in"{_delay(t_name * 0.6 + 0.1 * i)}>'
                    f'{doc.text(line, "medium", tsize, margin, y + i * tsize * 1.3, fill="var(--ink)")}</g>')
    y_text_end = y + (len(lines) - 1) * tsize * 1.3

    # chips (facts), from the bottom up
    chips = spec.get("facts", [])
    if mini and spec.get("private"):
        chips = ["private"] + chips[:1]
    cs = 13 if mini else 16
    ch = 24 if mini else 34
    cx, cy = margin, H - margin - ch
    rows = [[]]
    limit = (W - margin * 2 - 212) if mini else 600
    for c in chips:
        cw = doc.width(c, "medium", cs) + (24 if mini else 34)
        if rows[-1] and sum(r[1] + 8 for r in rows[-1]) + cw > limit:
            rows.append([])
        rows[-1].append((c, cw))
    rows = [r for r in rows if r]
    if mini:
        rows = rows[:1]
    for ri, row in enumerate(reversed(rows)):
        x = margin
        yy = cy - ri * (ch + 8)
        if yy < y_text_end + 10:
            break
        for ci, (c, cw) in enumerate(row):
            dot = c == "private"
            body.append(f'<g class="chip in"{_delay(t_name + 0.15 * (ci + ri * 3))}><rect x="{n(x)}" y="{n(yy)}" width="{n(cw)}" '
                        f'height="{ch}" rx="{n(ch / 2)}" class="{"cpv" if dot else "cbg"}"/>'
                        f'<circle cx="{n(x + (10 if mini else 14))}" cy="{n(yy + ch / 2)}" r="{n(3 if mini else 4)}" fill="var(--a1)"/>'
                        f'{doc.text(c, "medium", cs, x + (18 if mini else 25), yy + ch / 2 + cs * cap / 2, fill="var(--muted)")}</g>')
            x += cw + 8

    # the motif
    m = motif_data(spec)
    if mini:
        box = (W - margin - 196, 16, 196, H - 32)
    else:
        name_end = margin + adv * s + 24
        if W - margin - name_end >= W * 0.35:           # a short name leaves the full height beside it free
            left = max(name_end, W * 0.53)
            box = (left, 22, W - margin - left, H - 44)
        else:
            box = (W * 0.53, base + 30, W * 0.47 - margin, H - base - 52)
    motif_svg = MOTIFS[m["kind"]](doc, m, box, mini, 0.3 if mini else 0.5)

    label = spec.get("alt") or f"{title}: {spec.get('tagline', '')}".strip(": ")
    css = sketch_css + (".sh{opacity:.35;transform:translateX(-400px) skewX(-20deg);animation:shine 8s %ss ease-in-out infinite}"
           "@keyframes shine{0%%{transform:translateX(-200px) skewX(-20deg)}22%%,100%%{transform:translateX(%spx) skewX(-20deg)}}"
           ".ul{transform-box:fill-box;transform-origin:0 0;animation:grow .9s %ss ease-out both}"
           "@keyframes grow{from{transform:scaleX(0)}}"
           ".in{animation:fade .7s ease-out both}@keyframes fade{from{opacity:0;transform:translateY(6px)}}"
           ".cbg{fill:var(--bg2);stroke:var(--line)}.cpv{fill:none;stroke:var(--a1);stroke-dasharray:4 3}"
           % (n(t_name + 0.6, 2), n(W + 400), n(t_name * 0.5, 2))) + "".join(dict.fromkeys(doc.css)) + REDUCED_MOTION
    if theme == "light":
        css = css.replace(".sh{opacity:.35", ".sh{opacity:.55")
    bg = (f'<linearGradient id="bgg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{pal["bg"]}"/>'
          f'<stop offset="1" stop-color="{pal["bg2"]}"/></linearGradient>'
          f'<radialGradient id="glow" cx=".78" cy=".62" r=".5"><stop offset="0" stop-color="{pal["a1"]}" '
          f'stop-opacity="{pal["glow"]}"/><stop offset="1" stop-color="{pal["a1"]}" stop-opacity="0"/></radialGradient>'
          f'<linearGradient id="gr" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--a1)"/>'
          f'<stop offset="1" stop-color="var(--a2)"/></linearGradient>'
          f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" '
          f'fill="{pal["line"]}"/></pattern>')
    frame = (f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#bgg)"/>'
             f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#dots)" opacity=".7"/>'
             f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#glow)"/>'
             f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="{14 if mini else 18}" fill="none" stroke="{pal["line"]}"/>')
    desc = spec.get("desc", "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{attr(label)}"><title>{escape(label)}</title>'
            + (f"<desc>{escape(desc)}</desc>" if desc else "")
            + f"<style>{css}</style><defs>{bg}{''.join(doc.defs)}{doc.glyph_defs()}</defs>{frame}"
            + f'<g class="mo">{motif_svg}</g>' + "".join(body) + "</svg>\n")
    return _colour(svg, spec.get("palette", "teal"), theme)


KEYS = ("bg2", "bg", "ink", "muted", "line", "edge", "a1", "a2", "f1", "f2", "f3", "dk")


def _colour(svg: str, pal_name: str, theme: str) -> str:
    """Write the palette's colours in. Presentation attributes cannot read CSS variables, so attributes get literal
    colours. A fixed theme gets literals everywhere. ``auto`` keeps CSS variables in the stylesheet, set for light and
    for ``prefers-color-scheme: dark``, writes the light colours into attributes and overrides them for dark with
    attribute selectors (any CSS rule outranks a presentation attribute)."""
    var = re.compile(r"var\(--(" + "|".join(KEYS) + r")\)")
    if theme != "auto":
        pal = palette(pal_name, theme)
        return var.sub(lambda m: pal[m.group(1)], svg)
    light, dark = palette(pal_name, "light"), palette(pal_name, "dark")
    head, style, tail = re.match(r"(.*?<style>)(.*?)(</style>.*)", svg, re.S).groups()
    tail = var.sub(lambda m: light[m.group(1)], tail)
    back = {light[k]: dark[k] for k in KEYS}
    over = "".join(f'[{a}="{c}"]{{{a}:{back[c]}}}' for c in sorted(back) for a in ("fill", "stroke", "stop-color")
                   if f'{a}="{c}"' in tail)
    decl = lambda p: "svg{" + ";".join(f"--{k}:{p[k]}" for k in KEYS) + "}"
    style = decl(light) + "@media (prefers-color-scheme:dark){" + decl(dark) + over + "}" + style
    return head + style + tail


# ------------------------------------------------------------------------------------------------ the rules

def problems(text: str, kind: str = "hero") -> list:
    """Why ``text`` is not safe to embed as a GitHub ``<img>`` banner (empty when it is)."""
    out = []
    size = len(text.encode())
    if size > BUDGET[kind]:
        out.append(f"{size} bytes is over the {kind} budget of {BUDGET[kind]}")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return out + [f"not well-formed XML: {e}"]
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        out.append("the root is not an SVG element")
    if root.get("role") != "img" or not root.get("aria-label"):
        out.append('the root needs role="img" and an aria-label')
    if root.find("{http://www.w3.org/2000/svg}title") is None:
        out.append("no <title>")
    low = text.lower()
    for bad in ("<script", "<foreignobject", "<image", "<iframe", "<animate", "<set ", "javascript:", "@import"):
        if bad in low:
            out.append(f"contains {bad}")
    if re.search(r"\son[a-z]+\s*=", low):
        out.append("contains an event handler attribute")
    for m in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']*)["']""", text):
        if not m.group(1).startswith("#"):
            out.append(f"external reference {m.group(1)!r}")
    for m in re.finditer(r"url\(\s*['\"]?([^)'\"]*)", text):
        if not m.group(1).startswith("#"):
            out.append(f"external url({m.group(1)})")
    if REDUCED_MOTION not in text:
        out.append("no prefers-reduced-motion rule")
    return out


# ------------------------------------------------------------------------------------------------ extraction

def extract_catalog(source: Path) -> dict:
    """Val Ark's real catalogue: its per-tool download scripts, its model and installer tables, in the order the
    Librarian fills a disk: one of each kind first (diversity), then by priority."""
    items = []
    for p in sorted((source / "scripts" / "tools").glob("*.sh")):
        if not p.name.startswith("_"):
            items.append(("tool", p.stem, 900))
    # priority|id|kind|... for models; priority|id|title|kind|... for installers
    for name, kind, col in (("models-extra.tsv", "model", 2), ("installers.tsv", "installer", 3)):
        for line in (source / "data" / name).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                cols = line.split("|")
                items.append((kind, cols[1] + "/" + cols[col], int(cols[0])))
    by_sub = {}
    for k, name, pri in items:
        sub = k if k == "tool" else k + ":" + name.split("/")[1]
        by_sub.setdefault(sub, []).append((k, name, pri))
    for v in by_sub.values():
        v.sort(key=lambda t: (-t[2], t[1]))
    order, rest = [], []
    for sub in sorted(by_sub, key=lambda s: (-by_sub[s][0][2], s)):
        order.append(by_sub[sub][0])
        rest += by_sub[sub][1:]
    order += sorted(rest, key=lambda t: (-t[2], t[1]))
    counts = {k: sum(1 for t in items if t[0] == k) for k in ("tool", "model", "installer")}
    return {"kind": "catalog", "source": _source(source), "counts": counts, "items": [[t[0], t[1]] for t in order]}


def _source(path: Path) -> dict:
    import subprocess
    root = path if path.is_dir() else path.parent
    git = lambda *c: subprocess.run(["git", "-C", str(root), *c], capture_output=True, text=True).stdout.strip()
    url = git("remote", "get-url", "origin")
    return {"repo": url.rsplit("github.com", 1)[-1].lstrip(":/").removesuffix(".git"), "commit": git("rev-parse", "HEAD")}


def extract_lines(readme: Path) -> dict:
    """Line lengths of the first fenced code block in a README (what the terminal motif types out)."""
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"```[^\n]*\n(.*?)```", text, re.S)
    lines = [len(l.rstrip()) for l in (m.group(1).splitlines() if m else []) if l.strip()]
    return {"kind": "terminal", "source": dict(_source(readme), file=readme.name), "lines": lines[:12]}


# ------------------------------------------------------------------------------------------------ CLI

def banners() -> list:
    return json.loads((HERE / "banners.json").read_text(encoding="utf-8"))["banners"]


def outputs(spec: dict, roots: dict):
    """(theme, path) pairs for a banner: ``out`` is ``owner/repo:path`` (or a list of them; a bare path is this
    repo), and each theme is written to ``<path>-<theme>.svg`` (``<path>.svg`` for ``auto``). Repos that are not
    checked out here (``--repo``) are skipped."""
    out = []
    for target in spec["out"] if isinstance(spec["out"], list) else [spec["out"]]:
        repo, rel = target.split(":", 1) if ":" in target else (THIS_REPO, target)
        root = ROOT if repo == THIS_REPO else roots.get(repo)
        if root is None:
            continue
        for t in spec.get("themes", ["light", "dark"]):
            out.append((t, Path(root) / (f"{rel}.svg" if t == "auto" else f"{rel}-{t}.svg")))
    return out


SAMPLE = {"name": "sample-repo", "tagline": "A throwaway banner the tests render to check the rules.",
          "palette": "violet", "facts": ["MIT", "Python", "tested"], "motif": {"kind": "network"}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("names", nargs="*", help="banners to write (default: all whose repo is available)")
    ap.add_argument("--check", action="store_true", help="compare with the committed files instead of writing")
    ap.add_argument("--repo", action="append", default=[], metavar="OWNER/NAME=PATH",
                    help="a checkout of another repo whose banners to write or check")
    ap.add_argument("--extract", choices=["catalog", "lines"])
    ap.add_argument("--source", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sample", choices=["hero", "card"], help="print a sample banner to stdout")
    ap.add_argument("--theme", default="dark", choices=["light", "dark"])
    a = ap.parse_args(argv)
    if a.sample:
        sys.stdout.write(render(dict(SAMPLE, kind=a.sample), a.theme))
        return 0
    if a.extract:
        data = extract_catalog(a.source) if a.extract == "catalog" else extract_lines(a.source)
        a.out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")
        return 0
    roots = dict(r.split("=", 1) for r in a.repo)
    bad = 0
    for spec in banners():
        if a.names and spec["name"] not in a.names:
            continue
        for theme, path in outputs(spec, roots):
            text = render(spec, theme)
            for p in problems(text, spec.get("kind", "hero")):
                print(f"{path}: {p}")
                bad += 1
            if a.check:
                if not path.exists() or path.read_text(encoding="utf-8") != text:
                    print(f"{path} differs from its spec: run tools/hero/heroes.py")
                    bad += 1
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path} ({len(text.encode())} bytes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
