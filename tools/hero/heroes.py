#!/usr/bin/env python3
"""Animated README banners: a hero for the top of a repo's README and a mini card for profile listings.

    python3 tools/hero/heroes.py                      # write every banner in banners.json that lives in this repo
    python3 tools/hero/heroes.py --check              # exit 1 if a committed banner differs or breaks a rule
    python3 tools/hero/heroes.py val-ark --repo mvalancy/val-ark=../val-ark      # write a banner into another repo
    python3 tools/hero/heroes.py --check --repo mvalancy/val-ark=../val-ark        # and check it there
    python3 tools/hero/heroes.py --extract catalog --source ../val-ark --out tools/hero/motifs/val-ark.catalog.json
    python3 tools/hero/heroes.py --extract lines --source ../linux_tools/README.md --out tools/hero/motifs/x.lines.json
    python3 tools/hero/heroes.py --extract pcb --source ../board/hw/board.kicad_pcb --out tools/hero/motifs/x.pcb.json
    python3 tools/hero/heroes.py --sample hero > /tmp/sample.svg          # render a throwaway banner (tests use this)
    python3 ../mvalancy/tools/hero/heroes.py --spec profile/hero.json       # from another repo: its own spec file

Every banner is an entry in ``tools/hero/banners.json``: its name (drawn large), a tagline, a palette, facts shown
as chips, and a motif drawn from the project's real content where one exists (a CAD assembly traced from its STEP
files by ``extract_cad.py``, or built by the project's own CadQuery code and posed by ``extract_mesh.py``, a KiCad
board read by ``--extract pcb``, its catalogue, its constants). A CAD motif may draw one group at several poses and play them back as a ``scan`` (a
turret that sweeps, nods and holds); the rest pose is the still frame. Each banner is written twice, ``<out>-light.svg`` and
``<out>-dark.svg``, for a ``<picture>`` element whose ``prefers-color-scheme`` sources follow GitHub's theme.

Rendering needs only the Python standard library and is deterministic: the same inputs give the same bytes. Text is
drawn from vendored glyph outlines (``glyphs.json``, Space Grotesk, OFL-1.1), so it looks the same everywhere and
needs no font. Banners animate with CSS keyframes only: no script, no SMIL, no external reference. Every banner
loops (``_loop``): it builds, holds the finished frame for a few seconds, fades out and builds again, in one cycle that
every element shares, so a reader who scrolls to it late still sees it draw. Under ``prefers-reduced-motion`` every
animation stops and each element shows its base style, which is the final frame.
``problems()`` lists the rules a banner must pass: valid XML, a labelled ``role="img"`` root with a title, no script,
event handler, foreignObject, image or external reference, the reduced-motion rule, no animation that plays once and
stops, and the size budget (150 KB for a hero, 30 KB for a card).
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
BUDGET = {"hero": 150_000, "spot": 150_000, "card": 30_000}
REDUCED_MOTION = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
SIZES = {"hero": (1200, 440), "spot": (800, 400), "card": (600, 300)}
# Colours are baked into each file. WebKit (every iOS browser) draws an SVG in an <img> with the light scheme whatever
# the page is, so a scheme switched inside the SVG never fires there. A hero is not a link, so it gets a light and a
# dark file for a <picture>. Cards and spotlights are links, and GitHub cannot theme a linked image (its sanitiser
# takes the <img> out of a <picture> inside <a>, and an <a> inside <picture> hides the <source>), so they are drawn
# dark only: one file that reads on a light page and a dark one alike.
THEMES = {"hero": ["light", "dark"], "spot": ["dark"], "card": ["dark"]}

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
    "valpatel": ("#007f8c", "#00805a", "#00f0ff", "#05ffa1"),    # valpatel.com's cyan and signal green
    "graphdone": ("#4f46e5", "#047857", "#818cf8", "#34d399"),   # GraphDone's logo indigo and its OUTCOME indigo; done green
    "codegraph": ("#0e7490", "#a21caf", "#22d3ee", "#e879f9"),   # neon cyan and magenta
}
SURFACES = {  # palettes that bring their own surfaces and extra accents (a3 amber, a4 magenta), by theme
    "valpatel": {"dark": {"bg": "#05070a", "bg2": "#0a1016", "line": "#16232c", "edge": "#d8f6ff", "glow": ".18",
                          "a3": "#ffb000", "a4": "#ff2bd6"},
                 "light": {"bg": "#ffffff", "bg2": "#eef7f8", "edge": "#0b2530", "a3": "#a35a00", "a4": "#b0127f"}},
    # GraphDone's app is a dark navy workspace; its AI agents are amber and its features sky blue (workItemConstants.tsx)
    "graphdone": {"dark": {"bg": "#0b1020", "bg2": "#121a33", "line": "#26304d", "edge": "#c7d2fe", "f1": "#151d38",
                           "f2": "#1b2545", "glow": ".2", "a3": "#fbbf24", "a4": "#38bdf8"},
                  "light": {"bg": "#ffffff", "bg2": "#f1f3fd", "line": "#d9ddf0", "edge": "#1e1b4b", "f1": "#f6f7fe",
                            "f2": "#eceefb", "a3": "#b45309", "a4": "#0369a1"}},
    "codegraph": {"dark": {"bg": "#04050d", "bg2": "#0b0a20", "line": "#1d1f40", "edge": "#e0f7ff", "glow": ".28",
                           "a3": "#a3e635", "a4": "#818cf8"},
                  "light": {"bg": "#ffffff", "bg2": "#f3f1fd", "edge": "#0f0a2e", "a3": "#4d7c0f", "a4": "#4338ca"}},
}


def palette(name: str, theme: str) -> dict:
    a = ACCENTS[name]
    p = dict(BASE[theme])
    p["a1"], p["a2"] = (a[0], a[1]) if theme == "light" else (a[2], a[3])
    p["a3"], p["a4"] = p["a1"], p["a2"]                  # only some palettes have a third and fourth accent
    p.update(SURFACES.get(name, {}).get(theme, {}))
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
        self.ambient = set()      # keyframes that play while the finished frame is up (a scan), not before it
        self.periods = {}         # endless animations whose period render() sets to divide the loop's cycle: {name: near}

    def uid(self, stem: str) -> str:
        self.ids += 1
        return f"{stem}{self.ids}"

    def width(self, text: str, weight: str, size: float, track: float = 0) -> float:
        g = glyphs()["weights"][weight]
        return sum(g.get(c, g[" "])[0] + track for c in text) * size / glyphs()["upm"]

    def uses(self, text: str, weight: str, extra=None, track: float = 0) -> str:
        """``<use>`` elements for ``text`` in font units, from x = 0; ``track`` adds letter spacing (font units)."""
        g = glyphs()["weights"][weight]
        x, out = 0, []
        for i, c in enumerate(text):
            adv, d = g.get(c, g[" "])
            if d:
                gid = weight[0] + str(ord(c))
                self.used[gid] = d
                more = extra(i) if extra else ""
                out.append(f'<use href="#{gid}" x="{x}"{more}/>')
            x += adv + track
        return "".join(out)

    def text(self, text, weight, size, x, y, cls="", fill=None, track=0) -> str:
        s = size / glyphs()["upm"]
        f = f' fill="{fill}"' if fill else ""
        c = f' class="{cls}"' if cls else ""
        return (f'<g{c}{f} transform="translate({n(x)} {n(y)}) scale({n(s, 5)} {n(-s, 5)})">'
                f'{self.uses(text, weight, track=track)}</g>')

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


def _loops(part):
    """A part's filled loops by role: ``regions`` {role: loops} (mesh extracts) or ``outlines`` with one ``role``."""
    return part.get("regions") or {part.get("role", "body"): part["outlines"]}


def _scan_css(doc, data, poses, delay):
    """Keyframes that show one pose of the moving group at a time, following ``scan`` ([pose, seconds], ...); the
    rest pose is the base style, so reduced motion (no animation) shows it still. The scan plays once a cycle, from
    ``delay``, and ends back at the rest pose, which then holds until the banner restarts (``_loop``)."""
    fade = 0.05
    scan = list(data["scan"])
    rest = data.get("rest_pose")
    if rest is not None and scan[-1][0] != rest:      # come back to rest: the scan ends where the still frame is
        scan.append([rest, fade])
    period = sum(t for _, t in scan)
    css = []
    for k in poses:
        stops, t = [], 0.0
        for pose, dur in scan:
            if pose == k:
                stops.append((t, t + dur))
            t += dur
        if not stops:
            continue
        pts = []
        for t0, t1 in stops:
            pts += [(max(t0 - fade, 0), 0), (t0, 1), (t1, 1), (min(t1 + fade, period), 0)]
        if pts[0][0] > 0:
            pts.insert(0, (0, 0 if pts[0][1] == 0 or stops[0][0] > 0 else 1))
        if stops[0][0] == 0:
            pts[0] = (0, 1)
        if stops[-1][1] >= period:
            pts[-1] = (period, 1)
        elif pts[-1][0] < period:
            pts.append((period, 0))
        frames = "".join(f"{n(100 * t / period, 2)}%{{opacity:{o}}}" for t, o in pts)
        css.append(f"@keyframes ps{k}{{{frames}}}.ps{k}{{animation:ps{k} {n(period, 2)}s {n(delay, 2)}s linear both}}")
        doc.ambient.add(f"ps{k}")
    doc.css.append("".join(css))


def motif_cad(doc, data, box, mini, t0):
    """A real CAD assembly: each part's filled regions and visible edges, sliding in from its exploded position; a
    group drawn at several poses (``pose`` on its parts) plays them back as a scan once everything is in place."""
    x, y, w, h = box
    if data.get("only_groups"):                     # e.g. one leg of a robot
        data = dict(data, parts=[p for p in data["parts"] if p.get("group") in data["only_groups"]], groups=None)
    rest = data.get("rest_pose")
    parts = data["parts"]
    checks = data.get("checks") or []
    lab = (15 if mini else 17)
    row = lambda lab: sum(lab * 2.6 + doc.width(c, "medium", lab) for c in checks) - lab * 1.1
    if checks and row(lab) > w:                     # the row fits the motif box: shrink the labels, never clip
        lab = max(10, lab * w / row(lab))
    if checks:                                      # a row of ticked checks under the drawing
        h -= lab + 14
    if mini or not data.get("scan"):                # cards stay still in the rest pose
        parts = [p for p in parts if p.get("pose") in (None, rest)]
    pts = [q for part in parts for loops in _loops(part).values() for loop in loops for q in loop]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx = min(w / (max(xs) - min(xs)), h / (max(ys) - min(ys))) * (0.9 if mini else 0.94)
    ox = x + (w - (max(xs) - min(xs)) * sx) / 2 - min(xs) * sx
    oy = y + (h - (max(ys) - min(ys)) * sx) / 2 - min(ys) * sx

    def tf(p):
        return (ox + p[0] * sx, oy + p[1] * sx)

    min_px = 14.0 if mini else 3.0
    digits = 0 if mini else 1                       # cards are small: whole pixels are enough
    fills = {"shell": "var(--f1)", "plate": "var(--f2)", "lid": "var(--f3)", "body": "var(--f1)", "accent": "var(--a1)",
             "dark": "var(--dk)", "glass": "var(--a2)"}
    sway = data.get("idle") == "balance" and not mini
    out = [f'<g class="cad{" sway" if sway else ""}"'
           + (f' style="transform-origin:{n(x + w / 2)}px {n(y + h)}px"' if sway else "") + ">"]
    groups = data.get("groups") or list(dict.fromkeys(part.get("group", i) for i, part in enumerate(parts)))
    g_last = 0
    for i, part in enumerate(parts):
        lines = []
        for pl in part["lines"]:
            q = [tf(p) for p in pl]
            if sum(math.dist(a, b) for a, b in zip(q, q[1:])) >= min_px:
                lines.append(poly(simplify(q, 0.8 if mini else 0.5), d=digits))
        g = groups.index(part.get("group", i))
        g_last = max(g_last, g)
        fx, fy = part["from"][0] * sx, part["from"][1] * sx
        if g == 0:                                  # the first group is traced in by the scan line
            cls, style = "pt tr", _delay(t0)
        else:                                       # later groups slide in from where they start, one group at a time
            cls = "pt in"
            style = f' style="--fx:{n(fx)}px;--fy:{n(fy)}px;animation-delay:{n(t0 + 0.7 + 0.55 * (g - 1), 2)}s"'
        body = "".join(
            f'<path class="sil{" glass" if role == "glass" else ""}" fill="{fills[role]}" d="'
            + "".join(poly(simplify([tf(p) for p in loop], 1.0) if mini else [tf(p) for p in loop], True, digits)
                      for loop in loops) + '"/>'
            for role, loops in _loops(part).items()) + f'<path class="ed" d="{"".join(lines)}"/>'
        k = part.get("pose")
        if k is not None and not mini and data.get("scan"):
            body = f'<g class="ps{k}"{"" if k == rest else " opacity=" + chr(34) + "0" + chr(34)}>{body}</g>'
        out.append(f'<g class="{cls}"{style}>{body}</g>')
    out.append("</g>")
    t_land = t0 + 0.7 + 0.55 * max(g_last - 1, 0) + 0.9
    r = 10 if mini else 12
    tick = lambda X, Y, r: (f'<circle cx="{n(X)}" cy="{n(Y)}" r="{n(r)}" fill="var(--a2)"/><path d="M{n(X - r * .45)} '
                            f'{n(Y + r * .02)}l{n(r * .3)} {n(r * .32)}l{n(r * .58)} {n(-r * .64)}" fill="none" '
                            f'stroke="var(--bg)" stroke-width="{n(r * .28)}" stroke-linecap="round" stroke-linejoin="round"/>')
    for i, mk in enumerate(data.get("marks") or []):   # tick off the named points (joints) one by one
        X, Y = tf(mk)
        out.append(f'<g class="in"{_delay(t_land + 0.18 * i)}>{tick(X, Y, r)}</g>')
    if checks:
        cx, cy = x, y + h + 10 + lab / 2
        for i, c in enumerate(checks):
            out.append(f'<g class="in"{_delay(t_land + 0.8 + 0.25 * i)}>{tick(cx + lab * .6, cy, lab * .6)}'
                       f'{doc.text(c, "medium", lab, cx + lab * 1.5, cy + lab * 0.36, fill="var(--ink)")}</g>')
            cx += lab * 1.5 + doc.width(c, "medium", lab) + lab * 1.1
    if data.get("scan") and not mini:               # the scan starts once every group has landed
        _scan_css(doc, data, sorted({p["pose"] for p in parts if p.get("pose") is not None}),
                  t0 + 0.7 + 0.55 * max(g_last - 1, 0) + 0.9 + data.get("scan_wait", 0.8))
    # a scan line sweeps the base as it is "traced"
    out.append(f'<rect class="scan" x="{n(x)}" y="{n(y)}" width="3" height="{n(h)}" rx="1.5"{_delay(t0)}/>')
    doc.css.append(".cad .ed{fill:none;stroke:var(--edge);stroke-width:%s;stroke-linecap:round;stroke-linejoin:round;"
                   "opacity:.9}.cad .sil{stroke:var(--edge);stroke-width:%s;stroke-linejoin:round}"
                   ".cad .glass{fill-opacity:.35}"
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
            # the bar rises once a cycle (its group) and then breathes with the load (the bar): two elements, so
            # the looping rise is not overridden by the endless load on the same transform
            out.append(f'<g class="b in"{_delay(t0 + 0.12 * i)}><rect class="bv" x="{n(x + 14 + i * bw)}" '
                       f'y="{n(y + h - 10 - bh)}" width="{n(bw * 0.66)}" height="{n(bh)}" rx="3" '
                       f'style="animation-delay:{n(t0 + 1.4 + 0.3 * i, 2)}s"/></g>')
        doc.css.append(".b,.bv{transform-box:fill-box;transform-origin:50% 100%}.bv{fill:url(#gr)}"
                       ".b.in{animation:rise .7s ease-out both}.bv{animation:load 3.2s ease-in-out infinite alternate}"
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
                   ".fl,.fr{transform-box:fill-box;transform-origin:50% 50%}"   # rotate about the fighter, not the card corner
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


def _icon(kind, X, Y, r):
    """Small line icons drawn round (X, Y) at radius r, in the background colour on an accent node."""
    st = f'fill="none" stroke="var(--bg)" stroke-width="{n(r * 0.16)}" stroke-linecap="round" stroke-linejoin="round"'
    a = r * 0.5
    if kind == "chip":
        pins = "".join(f"M{n(X + d)} {n(Y - a)}v{n(-a * .45)}M{n(X + d)} {n(Y + a)}v{n(a * .45)}"
                       f"M{n(X - a)} {n(Y + d)}h{n(-a * .45)}M{n(X + a)} {n(Y + d)}h{n(a * .45)}" for d in (-a * .45, a * .45))
        return f'<rect x="{n(X - a)}" y="{n(Y - a)}" width="{n(2 * a)}" height="{n(2 * a)}" rx="{n(a * .2)}" {st}/><path d="{pins}" {st}/>'
    if kind == "gear":
        teeth = "".join(f"M{n(X + math.cos(t) * a * .75)} {n(Y + math.sin(t) * a * .75)}L{n(X + math.cos(t) * a * 1.25)} "
                        f"{n(Y + math.sin(t) * a * 1.25)}" for t in [k * math.pi / 4 for k in range(8)])
        return f'<circle cx="{n(X)}" cy="{n(Y)}" r="{n(a * .75)}" {st}/><circle cx="{n(X)}" cy="{n(Y)}" r="{n(a * .25)}" {st}/><path d="{teeth}" {st}/>'
    if kind == "robot":
        return (f'<rect x="{n(X - a)}" y="{n(Y - a * .55)}" width="{n(2 * a)}" height="{n(a * 1.5)}" rx="{n(a * .35)}" {st}/>'
                f'<path d="M{n(X)} {n(Y - a * .55)}v{n(-a * .5)}M{n(X - a * .4)} {n(Y + a * .15)}h.01M{n(X + a * .4)} {n(Y + a * .15)}h.01" {st}/>')
    if kind == "code":
        return f'<path d="M{n(X - a * .35)} {n(Y - a * .7)}L{n(X - a)} {n(Y)}L{n(X - a * .35)} {n(Y + a * .7)}M{n(X + a * .35)} {n(Y - a * .7)}L{n(X + a)} {n(Y)}L{n(X + a * .35)} {n(Y + a * .7)}M{n(X + a * .15)} {n(Y - a * .8)}L{n(X - a * .15)} {n(Y + a * .8)}" {st}/>'
    if kind == "brain":
        P = [(X - a, Y - a * .6), (X - a, Y + a * .6), (X, Y - a * .9), (X, Y), (X, Y + a * .9), (X + a, Y)]
        E = [(0, 2), (0, 3), (1, 3), (1, 4), (2, 5), (3, 5), (4, 5)]
        return (f'<path d="{"".join(f"M{n(P[i][0])} {n(P[i][1])}L{n(P[j][0])} {n(P[j][1])}" for i, j in E)}" {st}/>'
                + "".join(f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(a * .2)}" fill="var(--bg)"/>' for px, py in P))
    # window
    return (f'<rect x="{n(X - a)}" y="{n(Y - a * .8)}" width="{n(2 * a)}" height="{n(a * 1.6)}" rx="{n(a * .2)}" {st}/>'
            f'<path d="M{n(X - a)} {n(Y - a * .3)}h{n(2 * a)}" {st}/>')


def motif_stack(doc, data, box, mini, t0):
    """Full stack, hardware and software: labelled layers from PCBs at the bottom to apps at the top, built up one
    layer at a time, every layer's nodes wired to the next, and signals pulsing up and down the wires. The base style
    is the whole stack with every layer and label."""
    x, y, w, h = box
    layers = data.get("layers") or [["PCB · ELECTRONICS", "chip"], ["CAD · MECHANICAL", "gear"], ["MOTORS · ROBOTS", "robot"],
                                     ["FIRMWARE", "code"], ["EDGE AI", "brain"], ["APPS · UI", "window"]]
    k = len(layers)
    lh = h / k
    lab = 11 if mini else 14
    track = 90 if data.get("telemetry") else 0          # spaced capitals, like a HUD readout
    col = lambda i: "var(--%s)" % (layers[i][2] if len(layers[i]) > 2 else ("a1" if i < 3 else "a2"))
    lw = max(doc.width(l[0], "medium", lab, track) for l in layers) + 18
    nx0, nx1 = x + lw + 10, x + w - 14
    cols = 3
    r = min(lh * 0.34, 16)
    pos = []
    for i in range(k):                                  # bottom layer first
        yc = y + h - lh * (i + 0.5)
        shift = (nx1 - nx0) / (cols - 1) * (0.18 if i % 2 else -0.0)
        pos.append([(nx0 + r + shift + (nx1 - nx0 - 2 * r - abs(shift)) * j / (cols - 1), yc) for j in range(cols)])
    out = []
    for i, (name, icon, *_) in enumerate(layers):
        yc = pos[i][0][1]
        out.append(f'<g class="in"{_delay(t0 + 0.12 * i)}><rect x="{n(x)}" y="{n(yc - lh / 2 + 3)}" width="{n(w)}" height="{n(lh - 6)}" '
                   f'rx="{n(min(10, lh / 3))}" fill="{col(i)}" fill-opacity=".10" stroke="{col(i)}" '
                   f'stroke-opacity=".35"/>{doc.text(name, "medium", lab, x + 10, yc + lab * 0.36, fill="var(--ink)", track=track)}</g>')
    edges = []
    for i in range(k - 1):
        for j in range(cols):
            for jj in (j, j + 1):
                if jj < cols:
                    edges.append((pos[i][j], pos[i + 1][jj], i))
    wire = "".join(f"M{n(a[0])} {n(a[1])}L{n(b[0])} {n(b[1])}" for a, b, _ in edges)
    out.append(f'<path d="{wire}" stroke="var(--a2)" stroke-width="7" stroke-opacity=".16" fill="none"/>')
    out.append(f'<path d="{wire}" class="wire" stroke="var(--edge)" stroke-width="2.4" fill="none"/>')
    for e, (a, b, i) in enumerate(edges):
        up = e % 2 == 0
        p0, p1 = (a, b) if up else (b, a)
        out.append(f'<path class="pulse" pathLength="1" d="M{n(p0[0])} {n(p0[1])}L{n(p1[0])} {n(p1[1])}" '
                   f'stroke="{col(i if up else i + 1)}" style="animation-delay:{n(t0 + 1.2 + (e * 0.37) % 2.4, 2)}s"/>')
    for i, (name, icon, *_) in enumerate(layers):
        for j, (X, Y) in enumerate(pos[i]):
            out.append(f'<g class="in"{_delay(t0 + 0.12 * i + 0.05 * j)}><circle cx="{n(X)}" cy="{n(Y)}" r="{n(r)}" '
                       f'fill="{col(i)}" stroke="var(--bg)" stroke-width="2"/>{_icon(icon, X, Y, r)}</g>')
    doc.css.append(".pulse{fill:none;stroke-width:4.5;stroke-linecap:round;stroke-dasharray:.14 .86;stroke-dashoffset:1;"
                   "opacity:0;animation:pulse 2.4s linear infinite}"
                   "@keyframes pulse{0%{stroke-dashoffset:1.14;opacity:1}90%{opacity:1}100%{stroke-dashoffset:0;opacity:0}}")
    return "".join(out)


def motif_ops(doc, data, box, mini, t0):
    """An operations overview in valpatel.com's style: a dark panel with a faint grid, a hub with every product as a
    zone round it (name and real status), packets running along the links, small agents flying between zones, a
    pulsing LIVE tag, and telemetry log lines (real recent events) ticking in at the bottom. The base style is the
    whole board with every log line shown."""
    x, y, w, h = box
    cap = glyphs()["cap"] / glyphs()["upm"]
    nodes = data["nodes"][:8]
    log = data.get("log", [])[:3]
    head, lsz = 15, 14
    out = [f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="8" fill="var(--bg)" fill-opacity=".55" '
           f'stroke="var(--a1)" stroke-opacity=".35"/>',
           f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" rx="8" fill="url(#opg)"/>']
    doc.defs.append('<pattern id="opg" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" '
                    'fill="none" stroke="var(--a1)" stroke-opacity=".09"/></pattern>')
    out.append(doc.text(data.get("title", "OPERATIONS OVERVIEW"), "medium", head, x + 14, y + 14 + head * cap,
                        fill="var(--a1)", track=140))
    lw = doc.width("LIVE", "medium", head, 140)
    out.append(f'<circle class="led" cx="{n(x + w - 26 - lw)}" cy="{n(y + 14 + head * cap / 2)}" r="5" fill="var(--a2)"/>'
               + doc.text("LIVE", "medium", head, x + w - 14 - lw, y + 14 + head * cap, fill="var(--a2)", track=140))
    doc.css.append(".led{animation:led 1.6s ease-in-out infinite}@keyframes led{50%{opacity:.3}}")
    logh = (len(log) * lsz * 1.45 + 18) if log else 0
    gy0, gy1 = y + 14 + head + 14, y + h - logh - 8
    cw, chh = w / 3, (gy1 - gy0) / 3
    cells = [(c, r) for r in range(3) for c in range(3) if (c, r) != (1, 1)]
    hub = (x + cw * 1.5, gy0 + chh * 1.5)
    centres = [(x + cw * (c + .5), gy0 + chh * (r + .5)) for c, r in cells]
    wire = "".join(f"M{n(hub[0])} {n(hub[1])}L{n(cx)} {n(cy)}" for cx, cy in centres[:len(nodes)])
    out.append(f'<path d="{wire}" stroke="var(--a1)" stroke-opacity=".35" stroke-width="1.6" stroke-dasharray="5 5" fill="none"/>')
    for i, (cx, cy) in enumerate(centres[:len(nodes)]):        # packets out to each zone and back
        a, b = (hub, (cx, cy)) if i % 2 == 0 else ((cx, cy), hub)
        out.append(f'<path class="pk" pathLength="1" d="M{n(a[0])} {n(a[1])}L{n(b[0])} {n(b[1])}" '
                   f'stroke="var(--{"a2" if i % 2 else "a1"})" style="animation-delay:{n(t0 + 0.8 + (i * 0.53) % 2.6, 2)}s"/>')
    doc.css.append(".pk{fill:none;stroke-width:4;stroke-linecap:round;stroke-dasharray:.08 .92;stroke-dashoffset:1;"
                   "opacity:0;animation:pk 2.6s linear infinite}"
                   "@keyframes pk{0%{stroke-dashoffset:1.08;opacity:1}92%{opacity:1}100%{stroke-dashoffset:0;opacity:0}}")
    hr = min(cw, chh) * 0.3                                    # the hub: a hexagon with a core
    hexp = [(hub[0] + hr * math.cos(math.pi / 6 + k * math.pi / 3), hub[1] + hr * math.sin(math.pi / 6 + k * math.pi / 3))
            for k in range(6)]
    out.append(f'<path d="{poly(hexp, True)}" fill="var(--bg)" stroke="var(--a1)" stroke-width="2"/>'
               f'<circle class="core" cx="{n(hub[0])}" cy="{n(hub[1])}" r="{n(hr * .35)}" fill="var(--a1)"/>')
    doc.css.append(".core{transform-box:fill-box;transform-origin:50% 50%;animation:core 2.2s ease-in-out infinite}"
                   "@keyframes core{50%{transform:scale(.6);opacity:.6}}")
    zw, zh = cw - 14, min(chh - 12, 58)
    ns, ss = 15, 12
    for i, ((cx, cy), (name, status, *col)) in enumerate(zip(centres, nodes)):
        c = f"var(--{col[0] if col else ('a1' if i % 2 == 0 else 'a2')})"
        zx, zy = cx - zw / 2, cy - zh / 2
        t = 9
        ticks = (f"M{n(zx)} {n(zy + t)}V{n(zy)}H{n(zx + t)}M{n(zx + zw - t)} {n(zy)}H{n(zx + zw)}V{n(zy + t)}"
                 f"M{n(zx + zw)} {n(zy + zh - t)}V{n(zy + zh)}H{n(zx + zw - t)}M{n(zx + t)} {n(zy + zh)}H{n(zx)}V{n(zy + zh - t)}")
        tw = doc.width(name, "medium", ns, 80)
        nsz = ns if tw <= zw - 16 else ns * (zw - 16) / tw
        out.append(f'<g class="in"{_delay(t0 + 0.08 * i)}><rect x="{n(zx)}" y="{n(zy)}" width="{n(zw)}" height="{n(zh)}" '
                   f'fill="{c}" fill-opacity=".08" stroke="{c}" stroke-opacity=".3"/>'
                   f'<path d="{ticks}" fill="none" stroke="{c}" stroke-width="2"/>'
                   + doc.text(name, "medium", nsz, zx + 8, zy + 8 + nsz * cap, fill="var(--ink)", track=80)
                   + doc.text(status, "medium", ss, zx + 8, zy + zh - 8, fill=c, track=60) + '</g>')
    for k, route in enumerate(data.get("agents", [[0, 4, 7], [2, 5, 3]])):   # agents hop zone to zone
        pts = [centres[j] for j in route if j < len(nodes)] + [centres[route[0]]]
        dur = 2.2 * (len(pts) - 1)
        stops = "".join(f"{n(100 * q / (len(pts) - 1), 1)}%{{transform:translate({n(px - pts[0][0])}px,{n(py - pts[0][1])}px)}}"
                        for q, (px, py) in enumerate(pts))
        X, Y = pts[0][0] + zw / 2 - 12, pts[0][1] - zh / 2 + 12
        arms = "".join(f"M{n(X + dx * 3)} {n(Y + dy * 3)}l{n(dx * 5)} {n(dy * 5)}" for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)))
        out.append(f'<g class="ag{k}"><path d="{arms}" stroke="var(--a2)" stroke-width="1.8"/>'
                   f'<circle cx="{n(X)}" cy="{n(Y)}" r="3.2" fill="var(--a2)"/></g>')
        doc.css.append(f".ag{k}{{animation:ag{k} {n(dur, 1)}s {n(t0 + 1 + k * 1.1, 2)}s ease-in-out infinite}}@keyframes ag{k}{{{stops}}}")
    if log:                                                    # telemetry ticking in, newest last
        ly = y + h - logh
        out.append(f'<path d="M{n(x + 10)} {n(ly)}H{n(x + w - 10)}" stroke="var(--a1)" stroke-opacity=".25"/>')
        for i, line in enumerate(log):
            yy = ly + 10 + lsz * cap + i * lsz * 1.45
            out.append(f'<g class="lg" style="animation-delay:{n(t0 + 0.6 + 0.9 * i, 2)}s">'
                       + doc.text("> " + line, "medium", lsz, x + 14, yy, fill="var(--a2)" if i == len(log) - 1 else "var(--muted)", track=40)
                       + "</g>")
        doc.css.append(".lg{animation:lg .55s ease-out both}@keyframes lg{from{opacity:0;transform:translateX(-8px)}}")
    return "".join(out)


def _pcb_paths(segs, start):
    """Chain a net's track segments ([x1, y1, x2, y2, ...]) into polylines, walking out from the node nearest
    ``start`` so a path drawn on reads as the copper being laid from that end."""
    adj = {}
    for k, s in enumerate(segs):
        a, b = (s[0], s[1]), (s[2], s[3])
        adj.setdefault(a, []).append((b, k))
        adj.setdefault(b, []).append((a, k))
    used, out = set(), []
    nodes = sorted(adj, key=lambda p: math.dist(p, start))
    for seed in nodes:
        stack = [seed]
        while stack:
            p = stack.pop()
            for q, k in adj[p]:
                if k in used:
                    continue
                used.add(k)
                line = [p, q]
                while True:                     # extend while the walk is unbranched
                    nxt = [(r, j) for r, j in adj[line[-1]] if j not in used]
                    if len(nxt) != 1:
                        break
                    used.add(nxt[0][1])
                    line.append(nxt[0][0])
                out.append(line)
                stack.append(line[-1])
    return out


def _pcb_route(segs, a, b):
    """The shortest copper path between the nodes nearest points ``a`` and ``b`` (Dijkstra over track segments)."""
    import heapq
    adj = {}
    for s in segs:
        p, q = (s[0], s[1]), (s[2], s[3])
        adj.setdefault(p, []).append(q)
        adj.setdefault(q, []).append(p)
    if not adj:
        return []
    src = min(adj, key=lambda p: math.dist(p, a))
    dst = min(adj, key=lambda p: math.dist(p, b))
    dist, prev, heap = {src: 0.0}, {}, [(0.0, src)]
    while heap:
        d, p = heapq.heappop(heap)
        if p == dst:
            break
        if d > dist.get(p, 1e18):
            continue
        for q in adj[p]:
            nd = d + math.dist(p, q)
            if nd < dist.get(q, 1e18):
                dist[q], prev[q] = nd, p
                heapq.heappush(heap, (nd, q))
    if dst not in dist:
        return []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


def motif_pcb(doc, data, box, mini, t0):
    """A real KiCad board (``--extract pcb``): the outline is traced, pads and copper settle, the connectors named in
    ``parts`` drop onto their footprints, the ``pairs`` (differential nets, e.g. CAN H and L) are drawn as copper from
    their ``from`` part to their ``to`` part, and then signal pulses run along each pair, in step on both lines."""
    x, y, w, h = box
    labels = {} if mini else {r: (v, "top") if isinstance(v, str) else tuple(v) for r, v in (data.get("labels") or {}).items()}
    lab = 17
    sides = {s for _, s in labels.values()}
    lw = max([doc.width(t, "medium", lab, 40) for t, s in labels.values() if s in ("left", "right")] or [0]) + 30
    y, h = (y + lab + 12, h - lab - 12) if "top" in sides else (y, h)
    h -= lab + 12 if "bottom" in sides else 0
    x, w = (x + lw, w - lw) if "left" in sides else (x, w)
    w -= lw if "right" in sides else 0
    fps = {f["ref"]: f for f in data["footprints"]}
    nets = data["nets"]
    pts = [p for loop in data["outline"] for p in loop]
    pts += [q for r in data.get("parts", []) for ln in fps[r]["body"] for q in ln]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx = min(w / (max(xs) - min(xs)), h / (max(ys) - min(ys))) * (0.92 if mini else 0.96)
    ox = x + (w - (max(xs) - min(xs)) * sx) / 2 - min(xs) * sx
    oy = y + (h - (max(ys) - min(ys)) * sx) / 2 - min(ys) * sx
    tf = lambda p: (ox + p[0] * sx, oy + p[1] * sx)
    d = 0 if mini else 1
    hl = {net: (i, k) for i, pr in enumerate(data.get("pairs", [])) for k, net in enumerate(pr["nets"])}
    out = ['<g class="pcb">']
    board = "".join(poly([tf(p) for p in loop], True, d) for loop in data["outline"])
    holes = "".join(
        f'<circle cx="{n(tf(p[:2])[0], d)}" cy="{n(tf(p[:2])[1], d)}" r="{n(max(p[7] * sx / 2, 1), d)}"/>'
        for f in data["footprints"] for p in f["pads"] if p[8])                         # bare (unplated) holes
    out.append(f'<g class="bd tr"{_delay(t0)}><path class="sub" d="{board}"/><g class="hole">{holes}</g></g>')
    # the rest of the copper: every other track, faint, and the pads
    cu = {}
    for net, segs in data["tracks"].items():
        if net in hl:
            continue
        by_w = {}
        for s in segs:
            by_w.setdefault(max(1.0, round(s[5] * sx * 2) / 2), []).append(tuple(s))
        for k, ss in by_w.items():                  # chained into polylines: fewer moves, a smaller file
            cu.setdefault(k, []).extend(poly([tf(p) for p in ln], d=d) for ln in _pcb_paths(ss, ss[0][:2]))
    out.append(f'<g class="cu in"{_delay(t0 + 0.6)}>' + "".join(
        f'<path d="{"".join(v)}" stroke-width="{n(k)}"/>' for k, v in sorted(cu.items())) + "</g>")
    pads, drills = [], []
    for f in data["footprints"]:
        for p in f["pads"]:
            X, Y = tf(p[:2])
            pw, ph = max(p[2] * sx, 1.2), max(p[3] * sx, 1.2)
            if p[8]:
                continue
            if p[4] in ("circle", "oval") and abs(pw - ph) < 0.05:
                pads.append(f'<circle cx="{n(X, d)}" cy="{n(Y, d)}" r="{n(pw / 2, d)}"/>')
            else:
                rot = f' transform="rotate({n(-p[5])} {n(X, d)} {n(Y, d)})"' if p[5] % 180 else ""
                if p[5] % 180 and p[5] % 90 == 0:                     # a quarter turn: swap instead of rotating
                    pw, ph, rot = ph, pw, ""
                rx = min(pw, ph) / 2 if p[4] == "oval" else min(pw, ph) * 0.2 if p[4] == "roundrect" else 0
                pads.append(f'<rect x="{n(X - pw / 2, d)}" y="{n(Y - ph / 2, d)}" width="{n(pw, d)}" '
                            f'height="{n(ph, d)}"' + (f' rx="{n(rx, d)}"' if rx else "") + f"{rot}/>")
            if p[7] and not mini:
                drills.append(f'<circle cx="{n(X, d)}" cy="{n(Y, d)}" r="{n(max(p[7] * sx / 2, .6), d)}"/>')
    vias = "".join(f'<circle cx="{n(tf(v)[0], d)}" cy="{n(tf(v)[1], d)}" r="{n(max(v[2] * sx / 2, 1), d)}"/>'
                   for v in data.get("vias", []))
    out.append(f'<g class="pad in"{_delay(t0 + 0.8)}>{"".join(pads)}{vias}</g>')
    if drills:
        out.append(f'<g class="drl in"{_delay(t0 + 0.8)}>{"".join(drills)}</g>')
    # the named parts drop onto the board, one after another
    t_part = t0 + 1.2
    for i, ref in enumerate(data.get("parts", [])):
        f = fps[ref]
        shut = lambda ln: len(ln) > 3 and ln[0] == ln[-1]
        body = ('<path class="fl" d="' + "".join(poly([tf(p) for p in ln], True, d) for ln in f["body"] if shut(ln))
                + '"/><path d="' + "".join(poly([tf(p) for p in ln], False, d) for ln in f["body"] if not shut(ln)) + '"/>')
        cx = sum(p[0] for ln in f["body"] for p in ln) / max(1, sum(len(ln) for ln in f["body"]))
        cy = sum(p[1] for ln in f["body"] for p in ln) / max(1, sum(len(ln) for ln in f["body"]))
        bx, by = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        v = (cx - bx, cy - by)
        k = 26 / max(math.hypot(*v), 1e-9)
        out.append(f'<g class="part in" style="--fx:{n(v[0] * k)}px;--fy:{n(v[1] * k)}px;animation-delay:'
                   f'{n(t_part + 0.25 * i, 2)}s">{body}</g>')
    # the highlighted pairs: copper laid from the source part to the destination part, then pulses
    t_cu = t_part + 0.25 * len(data.get("parts", [])) + 0.5
    pulses = []
    for i, pr in enumerate(data.get("pairs", [])):
        a = fps[pr["from"]]["at"]
        b = fps[pr["to"]]["at"]
        a_pads = [p for p in fps[pr["from"]]["pads"] if p[6] is not None]
        b_pads = [p for p in fps[pr["to"]]["pads"] if p[6] is not None]
        for k, net in enumerate(pr["nets"]):
            segs = [tuple(s) for s in data["tracks"].get(net, [])]
            ni = nets.index(net)
            pa = next((p[:2] for p in a_pads if p[6] == ni), a[:2])
            pb = next((p[:2] for p in b_pads if p[6] == ni), b[:2])
            col = "var(--a1)" if k == 0 else "var(--a2)"
            wid = n(max(1.6, segs[0][5] * sx * 1.4) if segs else 2, 1)
            for line in _pcb_paths(segs, pa):
                out.append(f'<path class="can" d="{poly([tf(p) for p in line], d=d)}" pathLength="1" stroke="{col}" '
                           f'stroke-width="{wid}"{_delay(t_cu + 0.35 * i + 0.1 * k)}/>')
            route = _pcb_route(segs, pa, pb)
            if len(route) > 1 and not mini:
                pulses.append(f'<path class="pls" d="{poly([tf(p) for p in route], d=d)}" pathLength="1" '
                              f'style="animation-delay:{n(t_cu + 1.6 + 1.3 * i, 2)}s"/>')
    out += pulses
    out.append("</g>")
    t_lab = t_cu + 1.2
    bx0, bx1 = tf((min(xs), 0))[0], tf((max(xs), 0))[0]
    for i, (ref, (text, side)) in enumerate(labels.items()):   # name the parts beside the board
        q = [tf(p) for ln in fps[ref]["body"] for p in ln]
        qx, qy = [p[0] for p in q], [p[1] for p in q]
        tw = doc.width(text, "medium", lab, 40)
        if side in ("top", "bottom"):
            X = (min(qx) + max(qx)) / 2 - tw / 2
            Y = min(qy) - 10 if side == "top" else max(qy) + 10 + lab * 0.72
            lead = ""
        else:
            Y = (min(qy) + max(qy)) / 2 + lab * 0.36
            X = bx0 - 16 - tw if side == "left" else bx1 + 16
            x0, x1 = (bx0 - 10, min(qx) - 3) if side == "left" else (max(qx) + 3, bx1 + 10)
            lead = f'<path class="ld" d="M{n(x0)} {n(Y - lab * 0.36)}H{n(x1)}"/>'
        out.append(f'<g class="in"{_delay(t_lab + 0.2 * i)}>{lead}'
                   + doc.text(text, "medium", lab, X, Y, fill="var(--ink)", track=40) + "</g>")
    doc.css.append(".pcb .sub{fill:var(--f2);stroke:var(--edge);stroke-width:1.6;stroke-linejoin:round}"
                   ".pcb .hole{fill:var(--bg);stroke:var(--edge);stroke-width:1}"
                   ".pcb .bd.tr{animation:trace 1.2s ease-out both}"
                   "@keyframes trace{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}"
                   ".pcb .cu path{fill:none;stroke:var(--a1);stroke-linecap:round;stroke-linejoin:round;opacity:.35}"
                   ".pcb .pad{fill:var(--a1);opacity:.55}.pcb .drl{fill:var(--f2)}"
                   ".ld{fill:none;stroke:var(--muted);stroke-width:1.2;stroke-dasharray:3 3}"
                   ".pcb .part path{fill:none;stroke:var(--edge);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}"
                   ".pcb .part .fl{fill:var(--f1);fill-opacity:.9}"
                   ".pcb .part.in{animation:drop .8s cubic-bezier(.2,.8,.2,1) both}"
                   "@keyframes drop{from{transform:translate(var(--fx),var(--fy));opacity:0}to{opacity:1}}"
                   ".pcb .can{fill:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:0;"
                   "animation:lay 1.1s ease-in-out both}@keyframes lay{from{stroke-dashoffset:1}}"
                   ".pcb .pls{fill:none;stroke:var(--edge);stroke-width:5;stroke-linecap:round;stroke-dasharray:.06 .94;stroke-dashoffset:1;"
                   "opacity:0;animation:pls 2.6s linear infinite}"
                   "@keyframes pls{0%{stroke-dashoffset:1;opacity:0}8%{opacity:1}85%{opacity:1}100%{stroke-dashoffset:0;opacity:0}}")
    return "".join(out)


# GraphDone's own colours (packages/web/src/constants/workItemConstants.tsx): a work item's type, and COMPLETED
GD_TYPES = {"TASK": "#4ade80", "FEATURE": "#38bdf8", "BUG": "#ef4444", "MILESTONE": "#fb923c", "EPIC": "#e879f9",
            "IDEA": "#facc15", "OUTCOME": "#818cf8", "RESEARCH": "#2dd4bf", "REQUIREMENT": "#38bdf8"}
GD_DONE = "#22c55e"
# GraphDone's logo (docs/graphdone-logo.svg, 100 units square): an indigo disc, six work nodes round a white outcome
GD_LOGO = [(30, 35, 4, "#fbbf24"), (70, 35, 4, "#fbbf24"), (50, 25, 5, "#10b981"), (25, 65, 4, "#f59e0b"),
           (75, 65, 4, "#f59e0b"), (50, 75, 4, "#6b7280")]


def _cycle(end: float) -> float:
    """The loop's cycle (``_loop``) for a banner whose last intro ends at ``end`` seconds."""
    return round(end + HOLD + RESET, 1)


def _period(T: float, near: float) -> float:
    """A period near ``near`` seconds that divides the cycle ``T``, so an ambient animation looks the same a cycle on."""
    return T / max(1, round(T / near))


def _tick_path(X, Y, r):
    return f"M{n(X - r * .45)} {n(Y + r * .02)}l{n(r * .3)} {n(r * .32)}l{n(r * .58)} {n(-r * .64)}"


def motif_board(doc, data, box, mini, t0):
    """GraphDone: work coordinated through dependencies and outcomes. A list of GraphDone's work items (from the
    spec), each with its type, title and owner (a person, or an AI agent as a peer); their dependencies drawn as an
    arc diagram down the left; every item wired to the outcome, which is GraphDone's logo. The items complete in
    dependency order: the progress fills, a tick lands, the row lights, its dependency arcs and its wire to the
    outcome light up and one of the logo's work nodes comes on. With every item done the outcome is reached and work
    flows into it. The base style is the finished board."""
    x, y, w, h = box
    if not mini:
        y, h = y + 10, h - 20
    items = data["items"][: (data.get("mini_rows", 4) if mini else 6)]
    N = len(items)
    deps = [(a, b) for a, b in data.get("deps", []) if a < N and b < N]
    order = [i for i in data.get("order", range(N)) if i < N]
    order += [i for i in range(N) if i not in order]
    cap = glyphs()["cap"] / glyphs()["upm"]
    ow = min(w * 0.3, h * 0.62)                          # the outcome's column
    rail = 14 if mini else 30                            # the dependency arcs, left of the list
    lx0, lx1 = x + rail, x + w - ow - (12 if mini else 30)
    gap = 5 if mini else 9
    rh = (h - gap * (N - 1)) / N
    rw = lx1 - lx0
    cys = [y + i * (rh + gap) + rh / 2 for i in range(N)]
    R = min(ow * 0.42, h * (0.2 if mini else 0.17))
    ox, oy = x + w - ow / 2, y + h / 2 - (0 if mini else h * 0.09)
    step = 0.45 if mini else 0.5
    tc = t0 + (1.6 if mini else 1.9)
    done = {i: tc + step * j for j, i in enumerate(order)}
    t_final = tc + step * N + 0.6
    out, arcs, lit_arcs, ports, fans, lit_fans, flows = [], [], [], [], [], [], []
    ar = rh * (0.25 if mini else 0.27)
    cr = rh * (0.17 if mini else 0.2)
    # title size: one size for every row, the largest that fits them all
    tx = lx0 + (8 if mini else 14) + 2 * ar + (7 if mini else 12)
    room = lx1 - (6 if mini else 12) - 2 * cr - (8 if mini else 12) - tx
    ts = min([14.5] + [14.5 * room / max(doc.width(it[1], "medium", 14.5), 1) for it in items])
    for i, it in enumerate(items):
        kind, title, who = it[0], it[1], it[2]
        col = GD_TYPES.get(kind, "#9ca3af")
        cy = cys[i]
        ry = cy - rh / 2
        rx = min(10, rh * 0.22)
        body = [f'<rect x="{n(lx0)}" y="{n(ry)}" width="{n(rw)}" height="{n(rh)}" rx="{n(rx)}" class="gdr"/>',
                f'<rect x="{n(lx0 + 4)}" y="{n(ry + rh * .2)}" width="3" height="{n(rh * .6)}" rx="1.5" fill="{col}"/>']
        ax = lx0 + (8 if mini else 14) + ar
        if who == "agent":                               # an AI agent: a hexagon with a robot
            hexp = [(ax + ar * math.cos(math.pi / 6 + k * math.pi / 3), cy + ar * math.sin(math.pi / 6 + k * math.pi / 3))
                    for k in range(6)]
            body.append(f'<path d="{poly(hexp, True)}" fill="var(--a3)"/>{_icon("robot", ax, cy + ar * .06, ar * .95)}')
        else:                                            # a person: their initial
            fs = ar * 1.15
            body.append(f'<circle cx="{n(ax)}" cy="{n(cy)}" r="{n(ar)}" fill="var(--a1)"/>'
                        + doc.text(who[:1], "bold", fs, ax - doc.width(who[:1], "bold", fs) / 2, cy + fs * cap / 2,
                                   fill="var(--bg)"))
        kx = lx1 - (6 if mini else 12) - cr                    # the tick's centre
        if mini:                                         # a card: a type bar, and the title as a bar that fills
            bw = room * min(1, 0.45 + len(title) / 40)
            body.append(f'<rect x="{n(tx)}" y="{n(cy - rh * .26)}" width="{n(min(26, room * .4))}" height="6" rx="3" '
                        f'fill="{col}"/><rect x="{n(tx)}" y="{n(cy + rh * .08)}" width="{n(bw)}" height="6" rx="3" '
                        f'class="gdt"/>')
            bar = (tx, cy + rh * .08, bw, 6)
        else:
            cs = 9.5
            cw = doc.width(kind, "bold", cs, 80) + 12
            body.append(f'<rect x="{n(tx)}" y="{n(cy - rh * .36)}" width="{n(cw)}" height="15" rx="4" fill="{col}"/>'
                        + doc.text(kind, "bold", cs, tx + 6, cy - rh * .36 + 7.5 + cs * cap / 2, fill="#0b1020", track=80)
                        + doc.text(title, "medium", ts, tx, cy + rh * .3, fill="var(--ink)"))
            pw = min(64, room - cw - 14)
            bar = (kx - cr - 12 - pw, cy - rh * .36 + 5, pw, 5)
            body.append(f'<rect x="{n(bar[0])}" y="{n(bar[1])}" width="{n(pw)}" height="5" rx="2.5" class="gdt"/>')
        body.append(f'<circle cx="{n(kx)}" cy="{n(cy)}" r="{n(cr)}" class="gdo"/>')
        t = done[i]
        out.append(f'<g class="gdin"{_delay(t0 + 0.1 * i)}>{"".join(body)}'
                   f'<rect x="{n(bar[0])}" y="{n(bar[1])}" width="{n(bar[2])}" height="{n(bar[3])}" rx="{n(bar[3] / 2)}" '
                   f'fill="{GD_DONE}" class="gdp"{_delay(t - 0.45)}/>'
                   f'<rect x="{n(lx0)}" y="{n(ry)}" width="{n(rw)}" height="{n(rh)}" rx="{n(rx)}" class="gdl"{_delay(t)}/>'
                   f'<g class="gdk"{_delay(t)}><circle cx="{n(kx)}" cy="{n(cy)}" r="{n(cr)}" fill="{GD_DONE}"/>'
                   f'<path d="{_tick_path(kx, cy, cr)}" class="gdv" stroke-width="{n(cr * .3)}"/></g></g>')
        ports.append(f'<circle cx="{n(lx0)}" cy="{n(cy)}" r="{n(3 if mini else 4)}" class="gdq"/>'
                     f'<circle cx="{n(lx0)}" cy="{n(cy)}" r="{n(3 if mini else 4)}" fill="var(--a1)" class="gdk"{_delay(t)}/>')
        # the wire to the outcome, into the logo's rim facing the row
        th = math.pi + (i - (N - 1) / 2) * (0.34 if mini else 0.3)
        ex, ey = ox + (R + (9 if mini else 15)) * math.cos(th), oy + (R + (9 if mini else 15)) * math.sin(th)
        d = (ex - lx1) * 0.5
        wire = f"M{n(lx1)} {n(cy)}C{n(lx1 + d)} {n(cy)} {n(ex - d * .7)} {n(ey)} {n(ex)} {n(ey)}"
        fans.append(wire)
        lit_fans.append(f'<path d="{wire}" pathLength="1" class="gdw"{_delay(t)}/>')
        flows.append(f'<path d="{wire}" pathLength="1" class="gdf" style="animation-delay:-{n(0.37 * i, 2)}s"/>')
    for k, (a, b) in enumerate(deps):                   # the dependencies: an arc diagram, each into its dependant
        ya, yb = cys[a], cys[b]
        bulge = min(rail - 3, 6 + (5 if mini else 7) * abs(b - a)) * 1.33
        arc = (f"M{n(lx0 - 3)} {n(ya)}C{n(lx0 - bulge)} {n(ya)} {n(lx0 - bulge)} {n(yb)} {n(lx0 - 3)} {n(yb)}")
        arcs.append(arc)
        lit_arcs.append(f'<path d="{arc}" pathLength="1" class="gdw"{_delay(done[a])}/>')
    t_arcs = t0 + 0.8
    out.insert(0, f'<g class="gdd"{_delay(t_arcs)}><path d="{"".join(arcs)}" class="gda"/>'
                  f'<path d="{"".join(fans)}" class="gda"/></g>' + "".join(lit_arcs) + "".join(lit_fans))
    out.append(f'<g class="gdin"{_delay(t0 + 0.4)}>{"".join(ports)}</g>')
    # the outcome: GraphDone's logo, its work nodes coming on as the items complete
    k = R / 48
    L = lambda u, v: (ox + (u - 50) * k, oy + (v - 50) * k)
    gid = doc.uid("gdg")
    doc.defs.append(f'<radialGradient id="{gid}" cx=".4" cy=".3" r=".7"><stop offset="0" stop-color="#fff" '
                    f'stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
    spokes = "".join(f"M{n(L(u, v)[0])} {n(L(u, v)[1])}L{n(ox)} {n(oy)}" for u, v, _, _ in GD_LOGO)
    logo = [f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(R * 1.5)}" class="gdh"/>',
            f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(R)}" fill="#4f46e5"/>',
            f'<path d="{spokes}" class="gds" stroke-width="{n(max(1.2, 2 * k), 1)}"/>']
    sat = list(range(len(GD_LOGO)))
    for j, (u, v, r, c) in enumerate(GD_LOGO):          # a node per completed item; the rest when the outcome is met
        X, Y = L(u, v)
        t = done[order[j]] + 0.55 if j < N else t_final
        logo.append(f'<circle cx="{n(X)}" cy="{n(Y)}" r="{n(r * k * 1.25)}" fill="{c}" class="gdk"{_delay(t)}/>')
    del sat
    logo.append(f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(R)}" fill="url(#{gid})"/>'
                f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(7 * k * 1.2)}" fill="#fff" stroke="#4f46e5" '
                f'stroke-width="{n(2 * k)}"/>')
    out.append(f'<g class="gdpop" style="transform-origin:{n(ox)}px {n(oy)}px;animation-delay:{n(t0 + 0.5, 2)}s">'
               + "".join(logo) + "</g>")
    # the outcome is reached: a ring goes round the logo, its label lights, and work flows into it
    ring = f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(R + (5 if mini else 8))}" pathLength="1" class="gdc"{_delay(t_final)}/>'
    P, Pr = 1.7, 2.6
    doc.periods.update(gdf=P, gdh=Pr, gdpi=Pr)
    out.append(ring + f'<g class="gdfl"{_delay(t_final)}>{"".join(flows)}'
               f'<circle cx="{n(ox)}" cy="{n(oy)}" r="{n(R)}" class="gdpi" style="transform-origin:{n(ox)}px {n(oy)}px"/></g>')
    if not mini:                                         # its type and title under the logo
        cs = 10
        lab = "OUTCOME"
        cw = doc.width(lab, "bold", cs, 80) + 14
        ly = oy + R + 20
        lines, tsz = wrap(doc, data.get("outcome", ""), "medium", 15, ow + 10, 2)
        txt = "".join(doc.text(line, "medium", tsz, ox - doc.width(line, "medium", tsz) / 2, ly + 30 + tsz * cap + k2 * tsz * 1.3,
                               fill="var(--ink)") for k2, line in enumerate(lines))
        out.append(f'<g class="gdin"{_delay(t0 + 0.7)}><rect x="{n(ox - cw / 2)}" y="{n(ly)}" width="{n(cw)}" height="17" '
                   f'rx="4" fill="{GD_TYPES["OUTCOME"]}"/>'
                   + doc.text(lab, "bold", cs, ox - cw / 2 + 7, ly + 8.5 + cs * cap / 2, fill="#0b1020", track=80)
                   + txt + "</g>")
    doc.css.append(
        ".gdr{fill:var(--f1);stroke:var(--line);stroke-width:1.2}.gdt{fill:var(--line)}.gdo{fill:none;stroke:var(--line);"
        "stroke-width:2}.gdq{fill:var(--bg);stroke:var(--muted);stroke-width:1.5}"
        ".gda{fill:none;stroke:var(--muted);stroke-width:1.4;stroke-opacity:.45;stroke-dasharray:3 4}"
        ".gdw{fill:none;stroke:var(--a1);stroke-width:%s;stroke-linecap:round;stroke-dasharray:1;"
        "animation:gddraw .6s ease-in-out both}@keyframes gddraw{from{stroke-dashoffset:1}}"
        ".gdv{fill:none;stroke:var(--bg);stroke-linecap:round;stroke-linejoin:round}"
        ".gdin{animation:gdin .6s cubic-bezier(.2,.8,.2,1) both}@keyframes gdin{from{opacity:0;transform:translateX(-14px)}}"
        ".gdd{animation:gdfade .8s ease-out both}@keyframes gdfade{from{opacity:0}}"
        ".gdp{transform-box:fill-box;transform-origin:0 0;animation:gdgrow .45s ease-in-out both}"
        "@keyframes gdgrow{from{transform:scaleX(0)}}"
        ".gdl{fill:%s;fill-opacity:.07;stroke:%s;stroke-width:1.6;animation:gdfade .5s ease-out both}"
        ".gdk{transform-box:fill-box;transform-origin:50%% 50%%;animation:gdpop .4s cubic-bezier(.3,1.6,.5,1) both}"
        "@keyframes gdpop{from{opacity:0;transform:scale(0)}}"
        ".gdpop{animation:gdpop .7s cubic-bezier(.3,1.4,.5,1) both}"
        ".gdh{fill:var(--a1);opacity:.13;transform-box:fill-box;transform-origin:50%% 50%%;"
        "animation:gdh %ss ease-in-out infinite}@keyframes gdh{50%%{opacity:.26;transform:scale(1.06)}}"
        ".gds{fill:none;stroke:#e5e7eb;stroke-opacity:.55;stroke-linecap:round}"
        ".gdc{fill:none;stroke:%s;stroke-width:%s;stroke-linecap:round;stroke-dasharray:1;"
        "animation:gddraw .8s ease-in-out both}"
        ".gdfl{animation:gdfade .6s ease-out both}"
        ".gdf{fill:none;stroke:var(--a2);stroke-width:%s;stroke-linecap:round;stroke-dasharray:.07 .93;"
        "animation:gdf %ss linear infinite}@keyframes gdf{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".gdpi{fill:none;stroke:%s;stroke-width:2;opacity:0;animation:gdpi %ss ease-out infinite}"
        "@keyframes gdpi{0%%{opacity:.7;transform:scale(1)}100%%{opacity:0;transform:scale(1.6)}}"
        % (n(1.6 if mini else 2.2, 1), GD_DONE, GD_DONE, n(Pr, 3), GD_DONE, n(2.5 if mini else 3.5, 1),
           n(3 if mini else 4, 1), n(P, 3), GD_DONE, n(Pr, 3)))
    return "".join(out)


# the same type colours, deepened for a light page (Tailwind's 600/700 shades), where the 400s wash out
GD_TYPES_LIGHT = {"TASK": "#16a34a", "FEATURE": "#0284c7", "BUG": "#dc2626", "MILESTONE": "#ea580c", "EPIC": "#c026d3",
                  "IDEA": "#ca8a04", "OUTCOME": "#4f46e5", "RESEARCH": "#0d9488", "REQUIREMENT": "#0284c7"}


def motif_topology(doc, data, box, mini, t0):
    """GraphDone as a live graph in orbit: GraphDone's work items (from the spec) ride an orbit round their
    outcome (GraphDone's logo), each a node in its type's colour, owned by a person (their initial) or an AI agent
    (a hexagon with a robot), with a HUD callout naming it. Their dependencies run along the orbit and every item is
    wired to the outcome by a neon spoke. Behind it a perspective grid floor and two drifting layers of distant graph
    give it depth. The items complete in dependency order: a ring closes round the node, its dependency arcs and its
    spoke light and data pulses start to flow into the outcome, and one of the logo's work nodes comes on. With every
    item done the outcome locks: a ring closes round the logo, the readout counts the last item and pings ring out.
    The base style is the finished, locked graph. A card, or a box too small for the orbit and its callouts (a spotlight
    under a long name), draws the board instead."""
    if mini or box[3] < 300 or box[2] < 440:
        return motif_board(doc, data, box, mini, t0)
    x, y, w, h = box
    light = getattr(doc, "theme", "dark") != "dark"      # light or auto: the deeper colours read on both
    types = GD_TYPES_LIGHT if light else GD_TYPES
    done_c = "#16a34a" if light else GD_DONE
    W, H = getattr(doc, "size", SIZES["hero"])
    cap = glyphs()["cap"] / glyphs()["upm"]
    items = data["items"][:6]
    N = len(items)
    labels = (data.get("labels") or [it[1] for it in items])[:N]
    deps = [(a, b) for a, b in data.get("deps", []) if a < N and b < N]
    order = [i for i in data.get("order", range(N)) if i < N]
    order += [i for i in range(N) if i not in order]
    angles = list(data.get("angles") or [])[:N]
    angles += [200 + 360 * k / N for k in range(len(angles), N)]      # evenly round the orbit where none is given
    cx, cy = x + w * 0.51, y + h * 0.47                  # the orbit's centre; the outcome floats there
    rx, ry = w * 0.37, h * 0.28
    R = min(w, h) * 0.105                                # the logo's radius
    pos = []
    for th in angles:
        a = math.radians(th)
        z = math.sin(a)                                  # -1 at the back of the orbit, +1 at the front
        pos.append((cx + rx * math.cos(a), cy + ry * z, z))
    step, tc = 0.5, t0 + 2.0
    done = {i: tc + step * j for j, i in enumerate(order)}
    t_final = tc + step * N + 0.5
    out = []
    glows = {}

    def glow(c):                                         # a soft radial glow in one colour, made once
        if c not in glows:
            glows[c] = doc.uid("gtz")
            doc.defs.append(f'<radialGradient id="{glows[c]}"><stop offset=".3" stop-color="{c}" stop-opacity=".55"/>'
                            f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>')
        return glows[c]
    # ---- depth: a perspective floor and two layers of distant graph, drifting at different speeds (parallax)
    hz = cy + ry * 0.55                                  # the floor's horizon, under the orbit
    vp = (cx, cy - h * 0.25)
    fl = []
    for k in range(-9, 10):                              # lines running to the vanishing point
        bx = cx + k * 70
        tt = (hz - vp[1]) / (H - vp[1])
        fl.append(f"M{n(vp[0] + (bx - vp[0]) * tt)} {n(hz)}L{n(bx)} {n(H)}")
    for k in range(8):                                   # rungs closer together toward the horizon
        yy = hz + (H - hz) * (k / 7) ** 1.8
        fl.append(f"M{n(x - 40)} {n(yy)}H{n(W)}")
    mid, fid = doc.uid("gtm"), doc.uid("gtf")
    doc.defs.append(f'<radialGradient id="{fid}" gradientUnits="userSpaceOnUse" cx="{n(cx)}" cy="{n(H)}" r="{n(w * .62)}">'
                    f'<stop offset="0" stop-color="#fff"/><stop offset=".55" stop-color="#fff" stop-opacity=".5"/>'
                    f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                    f'<mask id="{mid}"><rect x="0" y="{n(hz)}" width="{W}" height="{n(H - hz)}" fill="url(#{fid})"/></mask>')
    Pscan = 3.2
    out.append(f'<g class="gtd"{_delay(t0)} mask="url(#{mid})"><path d="{"".join(fl)}" class="gtfl"/>'
               f'<path d="M0 {n(hz)}H{W}" class="gtsc"/></g>')
    rnd = Rand(data.get("seed", "graphdone"))
    layers = []
    for q, (count, rr, op) in enumerate(((46, 1.1, .5), (12, 2.4, .55))):
        pts = [(x - 60 + (w + 120) * rnd(), 14 + (H - 28) * rnd()) for _ in range(count)]
        if q == 0:                                       # far: specks, a few joined
            pts += [(40 + (x - 80) * rnd(), 14 + (H - 28) * rnd()) for _ in range(14)]
        dots = "".join(f"M{n(px)} {n(py)}h0" for px, py in pts)
        near = []
        for i, p in enumerate(pts[:count]):
            j = min((j for j in range(count) if j != i), key=lambda j: math.dist(p, pts[j]))
            if math.dist(p, pts[j]) < (70 if q == 0 else 130) and i < j:
                near.append(f"M{n(p[0])} {n(p[1])}L{n(pts[j][0])} {n(pts[j][1])}")
        layers.append(f'<g class="gtp{q}"><path d="{"".join(near)}" class="gtl{q}"/>'
                      f'<path d="{dots}" class="gtn{q}" stroke-width="{n(rr * 2, 1)}"/></g>')
    out.append(f'<g class="gtd"{_delay(t0 + 0.1)}>{"".join(layers)}</g>')
    # ---- the orbit, and the dependencies along it
    oid = doc.uid("gto")
    orbit = f'<ellipse id="{oid}" cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(ry)}" pathLength="1"/>'
    doc.defs.append(orbit.replace('pathLength="1"', 'pathLength="100"'))
    out.append(f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx * 1.13)}" ry="{n(ry * 1.13)}" class="gto2 gtd"{_delay(t0 + .2)}/>'
               f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(ry)}" pathLength="1" class="gto"{_delay(t0 + .2)}/>'
               f'<g class="gtd"{_delay(t0 + 1)}><use href="#{oid}" class="gtof"/></g>')

    def arc(a, b):                                       # along the orbit, the short way, from a to b
        ta, tb = angles[a], angles[b]
        d = (tb - ta + 540) % 360 - 180
        steps = max(4, int(abs(d) / 4))
        pts = [(cx + rx * math.cos(math.radians(ta + d * s / steps)),
                cy + ry * math.sin(math.radians(ta + d * s / steps))) for s in range(steps + 1)]
        return poly(pts)
    dep_lit, dep_flow = [], []
    Pf = 1.6
    for k, (a, b) in enumerate(deps):
        d = arc(a, b)
        dep_lit.append(f'<path d="{d}" pathLength="1" class="gtdl"{_delay(done[a])}/>')
        dep_flow.append(f'<g class="gtd"{_delay(done[a] + .4)}><path d="{d}" pathLength="1" class="gtdf" '
                        f'style="animation-delay:-{n(Pf * k / max(1, len(deps)), 2)}s"/></g>')
    # ---- the spokes: every item wired to the outcome, in neon from its type colour into the outcome's indigo
    spokes, lit, flows = [], [], []
    for i, (px, py, z) in enumerate(pos):
        col = types.get(items[i][0], "#9ca3af")
        L = math.hypot(cx - px, cy - py)
        ux, uy = (cx - px) / L, (cy - py) / L
        r = 13 + 3 * z
        a0, b0 = (px + ux * (r + 4), py + uy * (r + 4)), (cx - ux * (R + 12), cy - uy * (R + 12))
        gid = doc.uid("gts")
        doc.defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{n(a0[0])}" y1="{n(a0[1])}" '
                        f'x2="{n(b0[0])}" y2="{n(b0[1])}"><stop offset="0" stop-color="{col}"/>'
                        f'<stop offset="1" stop-color="var(--a1)"/></linearGradient>')
        d = poly([a0, b0])
        spokes.append(d)
        lit.append(f'<g class="gtd"{_delay(done[i])}><path d="{d}" stroke="url(#{gid})" class="gtg"/></g>'
                   f'<path d="{d}" pathLength="1" stroke="url(#{gid})" class="gtw"{_delay(done[i])}/>')
        flows.append(f'<g class="gtd"{_delay(done[i] + .5)}><path d="{d}" pathLength="1" class="gtpf" '
                     f'style="animation-delay:-{n(.27 * i, 2)}s"/></g>')
    out.append(f'<path d="{"".join(spokes)}" class="gta gtd"{_delay(t0 + .6)}/>')
    out += dep_lit + lit + dep_flow + flows
    # ---- the outcome: GraphDone's logo, with HUD rings turning round it
    k = R / 48
    Lg = lambda u, v: (cx + (u - 50) * k, cy + (v - 50) * k)
    gg = doc.uid("gtg")
    doc.defs.append(f'<radialGradient id="{gg}" cx=".4" cy=".3" r=".7"><stop offset="0" stop-color="#fff" '
                    f'stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')
    spk = "".join(f"M{n(Lg(u, v)[0])} {n(Lg(u, v)[1])}L{n(cx)} {n(cy)}" for u, v, _, _ in GD_LOGO)
    logo = [f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R * 2.3)}" fill="url(#{glow("#6366f1")})" class="gth"/>',
            f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R)}" fill="#4f46e5"/>',
            f'<path d="{spk}" class="gds" stroke-width="{n(max(1.2, 2 * k), 1)}"/>']
    for j, (u, v, r, c) in enumerate(GD_LOGO):
        X, Y = Lg(u, v)
        t = done[order[j]] + 0.55 if j < N else t_final
        logo.append(f'<circle cx="{n(X)}" cy="{n(Y)}" r="{n(r * k * 1.25)}" fill="{c}" class="gdk"{_delay(t)}/>')
    logo.append(f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R)}" fill="url(#{gg})"/>'
                f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(7 * k * 1.2)}" fill="#fff" stroke="#4f46e5" '
                f'stroke-width="{n(2 * k)}"/>')
    rings = (f'<g class="gtd"{_delay(t0 + .7)}><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R + 14)}" pathLength="360" class="gtr1"/>'
             f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R + 22)}" pathLength="120" class="gtr2"/></g>')
    out.append(rings + f'<g class="gdpop" style="transform-origin:{n(cx)}px {n(cy)}px;animation-delay:{n(t0 + 0.5, 2)}s">'
               + "".join(logo) + "</g>")
    out.append(f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R + 6)}" pathLength="1" class="gtc"{_delay(t_final)}/>'
               f'<g class="gtd"{_delay(t_final)}><circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R + 6)}" class="gtpi" '
               f'style="transform-origin:{n(cx)}px {n(cy)}px"/></g>')
    # ---- the work items, back to front: a node in its type's colour, its owner inside, a callout naming it
    for i in sorted(range(N), key=lambda i: pos[i][2]):
        kind, title, who = items[i][0], labels[i], items[i][2]
        col = types.get(kind, "#9ca3af")
        px, py, z = pos[i]
        r = 13 + 3 * z
        t = done[i]
        body = [f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(r * 2.2)}" fill="url(#{glow(col)})"/>']
        if who == "agent":
            hexp = [(px + r * math.cos(math.pi / 6 + q * math.pi / 3), py + r * math.sin(math.pi / 6 + q * math.pi / 3))
                    for q in range(6)]
            body.append(f'<path d="{poly(hexp, True)}" fill="var(--bg)" stroke="{col}" stroke-width="2.4"/>'
                        f'{_icon("robot", px, py + r * .06, r * .95).replace("var(--bg)", "var(--a3)")}')
        else:
            fs = r * 1.05
            body.append(f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(r)}" fill="var(--bg)" stroke="{col}" stroke-width="2.4"/>'
                        + doc.text(who[:1], "bold", fs, px - doc.width(who[:1], "bold", fs) / 2, py + fs * cap / 2,
                                   fill="var(--ink)"))
        # the callout: a tick out of the node to a bar, the label above it (back of the orbit) or below it (front)
        up = z < 0
        ts, cs = 15, 11.5
        tag = f"{kind} · {'AI AGENT' if who == 'agent' else who.upper()}"
        lw = max(doc.width(title, "medium", ts), doc.width(tag, "medium", cs, 120))
        lx = min(max(px - lw / 2, x), x + w - lw)
        sg = -1 if up else 1
        y0, y1 = py + sg * (r + 6), py + sg * (r + 16)
        if up:
            ty, gy = y1 - 7, y1 - 7 - ts * cap - 8
        else:
            gy, ty = y1 + 7 + cs * cap, y1 + 7 + cs * cap + 8 + ts * cap
        top = gy - cs * cap - 6 if up else y1 + 2
        bot = y1 - 2 if up else ty + 6
        call = (f'<rect x="{n(lx - 6)}" y="{n(top)}" width="{n(lw + 12)}" height="{n(bot - top)}" rx="3" class="gtpl"/>'
                f'<path d="M{n(px)} {n(y0)}V{n(y1)}M{n(lx)} {n(y1)}H{n(lx + lw)}" class="gtcl" stroke="{col}"/>'
                + doc.text(title, "medium", ts, lx, ty, fill="var(--ink)")
                + doc.text(tag, "medium", cs, lx, gy, fill=col, track=120))
        if who == "agent":
            lit = (f'<path d="{poly(hexp, True)}" fill="{col}" stroke="{col}" stroke-width="2.4"/>'
                   f'{_icon("robot", px, py + r * .06, r * .95)}')
        else:
            lit = (f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(r + 1.2)}" fill="{col}"/>'
                   + doc.text(who[:1], "bold", fs, px - doc.width(who[:1], "bold", fs) / 2, py + fs * cap / 2,
                              fill="var(--bg)"))
        body.append(f'<g class="gdk"{_delay(t)}>{lit}</g>')
        ring = (f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(r + 5)}" pathLength="1" class="gtk" stroke="{done_c}"{_delay(t)}/>'
                f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(r + 5)}" class="gtx" stroke="{done_c}"'
                f' style="transform-origin:{n(px)}px {n(py)}px;animation-delay:{n(t, 2)}s"/>')
        out.append(f'<g class="gtn" style="transform-origin:{n(px)}px {n(py)}px;animation-delay:{n(t0 + .7 + .08 * i, 2)}s">'
                   f'{"".join(body)}</g>{ring}<g class="gtd"{_delay(t0 + 1 + .08 * i)}>{call}</g>')
    # ---- the readout, bottom right: the outcome, and the count of items done
    rs, rt = 12, 15
    ox1 = x + w
    lines, rt = wrap(doc, data.get("outcome", ""), "medium", rt, 160, 2)
    tw = max(doc.width(t, "medium", rt) for t in lines)
    by = y + h - 2 - (len(lines) - 1) * rt * 1.3
    lab = "OUTCOME"
    cw = doc.width(lab + " ", "medium", rs, 160)
    cnt = f"{N}/{N} DONE"
    rw = max(tw, cw + doc.width(cnt, "medium", rs, 160))
    rx0 = ox1 - rw
    ry0 = by - rt * cap - 10
    out.append(f'<g class="gtd"{_delay(t0 + 1.2)}>'
               + "".join(doc.text(t, "medium", rt, rx0, by + q * rt * 1.3, fill="var(--ink)") for q, t in enumerate(lines))
               + doc.text(lab, "medium", rs, rx0, ry0, fill=types["OUTCOME"], track=160)
               + f'<path d="M{n(rx0 - 12)} {n(ry0 - rs * cap)}V{n(by + (len(lines) - 1) * rt * 1.3)}" class="gtcl" '
               f'stroke="{types["OUTCOME"]}"/></g>')
    for j in range(N + 1):                               # the count ticks up as items complete; N/N is the still frame
        txt = doc.text(f"{j}/{N} DONE", "medium", rs, rx0 + cw, ry0, fill=done_c if j == N else "var(--muted)", track=160)
        a = done[order[j - 1]] if j else t0 + 1.2
        if j == N:
            out.append(f'<g class="gtqf" style="animation:gtqn .02s {n(a - .02, 2)}s step-end both">{txt}</g>')
        else:
            out.append(f'<g class="gtq" style="animation:gtq {n(done[order[j]] - a, 2)}s {n(a, 2)}s linear both">{txt}</g>')
    P1, P2, Pp, Pd = 30.0, 30.0, 2.6, 14.0      # rings: a quarter and a third of a turn a cycle
    doc.periods.update(gtf=Pf, gtpf=Pf, gtr1=P1, gtr2=P2, gtpi=Pp, gth=Pp * 2, gtp0=Pd * 2, gtp1=Pd, gtof=12.0,
                       gtsc=Pscan)
    halo = ".55" if light else ".8"
    doc.css.append(
        ".gtd{animation:gdfade .7s ease-out both}@keyframes gdfade{from{opacity:0}}"
        ".gtfl{fill:none;stroke:var(--a1);stroke-width:1;stroke-opacity:%s}"
        ".gtsc{fill:none;stroke:var(--a2);stroke-width:2;opacity:0;animation:gtsc %ss cubic-bezier(.5,0,.9,.6) infinite}"
        "@keyframes gtsc{0%%{opacity:0;transform:translateY(0)}15%%{opacity:.55}100%%{opacity:0;transform:translateY(%spx)}}"
        ".gtp0{animation:gtp0 28s ease-in-out infinite}@keyframes gtp0{50%%{transform:translate(-7px,2px)}}"
        ".gtp1{animation:gtp1 14s ease-in-out infinite}@keyframes gtp1{50%%{transform:translate(-14px,4px)}}"
        ".gtl0{fill:none;stroke:var(--a1);stroke-width:.8;stroke-opacity:.25}"
        ".gtl1{fill:none;stroke:var(--a1);stroke-width:1;stroke-opacity:.3}"
        ".gtn0{fill:none;stroke:var(--edge);stroke-linecap:round;stroke-opacity:.35}"
        ".gtn1{fill:none;stroke:var(--a1);stroke-linecap:round;stroke-opacity:.55}"
        ".gto{fill:none;stroke:var(--a1);stroke-width:1.4;stroke-opacity:.45;stroke-dasharray:1;"
        "animation:gddraw 1.2s ease-in-out both}@keyframes gddraw{from{stroke-dashoffset:1}}"
        ".gto2{fill:none;stroke:var(--a1);stroke-width:1;stroke-opacity:.2;stroke-dasharray:2 6}"
        ".gtof{fill:none;stroke:var(--a2);stroke-width:2.2;stroke-linecap:round;stroke-dasharray:2 23;stroke-opacity:.6;"
        "animation:gtof 12s linear infinite}@keyframes gtof{to{stroke-dashoffset:-100}}"
        ".gta{fill:none;stroke:var(--a1);stroke-width:1.2;stroke-opacity:.35;stroke-dasharray:2 5}"
        ".gtdl{fill:none;stroke:var(--a4);stroke-width:2.6;stroke-linecap:round;stroke-dasharray:1;"
        "animation:gddraw .6s ease-in-out both}"
        ".gtdf{fill:none;stroke:var(--edge);stroke-width:4;stroke-linecap:round;stroke-dasharray:.05 .95;"
        "animation:gtf %ss linear infinite}@keyframes gtf{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".gtg{fill:none;stroke-width:9;stroke-linecap:round;stroke-opacity:.18}"
        ".gtw{fill:none;stroke-width:2.4;stroke-linecap:round;stroke-dasharray:1;animation:gddraw .6s ease-in-out both}"
        ".gtpf{fill:none;stroke:var(--edge);stroke-width:4.5;stroke-linecap:round;stroke-dasharray:.07 .93;"
        "animation:gtpf %ss linear infinite}@keyframes gtpf{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".gth{opacity:%s;transform-box:fill-box;transform-origin:50%% 50%%;"
        "animation:gth 5.2s ease-in-out infinite}@keyframes gth{50%%{opacity:%s;transform:scale(1.1)}}"
        ".gds{fill:none;stroke:#e5e7eb;stroke-opacity:.55;stroke-linecap:round}"
        ".gdk{transform-box:fill-box;transform-origin:50%% 50%%;animation:gdpop .4s cubic-bezier(.3,1.6,.5,1) both}"
        "@keyframes gdpop{from{opacity:0;transform:scale(0)}}"
        ".gdpop{animation:gdpop .7s cubic-bezier(.3,1.4,.5,1) both}"
        ".gtn{animation:gdpop .5s cubic-bezier(.3,1.5,.5,1) both}"
        ".gtr1{fill:none;stroke:var(--a1);stroke-width:1.5;stroke-dasharray:1.5 4.5;stroke-opacity:.8;transform-box:fill-box;"
        "transform-origin:50%% 50%%;animation:gtr1 12s linear infinite}@keyframes gtr1{to{transform:rotate(90deg)}}"
        ".gtr2{fill:none;stroke:var(--a2);stroke-width:2;stroke-dasharray:24 6 4 6;stroke-opacity:.6;transform-box:fill-box;"
        "transform-origin:50%% 50%%;animation:gtr2 12s linear infinite}@keyframes gtr2{to{transform:rotate(-120deg)}}"
        ".gtc{fill:none;stroke:%s;stroke-width:3;stroke-linecap:round;stroke-dasharray:1;animation:gddraw .8s ease-in-out both}"
        ".gtpi{fill:none;stroke:%s;stroke-width:2;opacity:0;animation:gtpi 2.6s ease-out infinite}"
        "@keyframes gtpi{0%%{opacity:.8;transform:scale(1)}100%%{opacity:0;transform:scale(1.9)}}"
        ".gtk{fill:none;stroke-width:2.2;stroke-linecap:round;stroke-dasharray:1;animation:gddraw .45s ease-out both}"
        ".gtx{fill:none;stroke-width:3;opacity:0;animation:gtx .7s ease-out both}"
        "@keyframes gtx{0%%{opacity:0;transform:scale(1)}12%%{opacity:.9;transform:scale(1.1)}100%%{opacity:0;transform:scale(2.2)}}"
        ".gtcl{fill:none;stroke-width:1.3;stroke-opacity:.8}.gtpl{fill:var(--bg);fill-opacity:.62}"
        ".gtq{opacity:0}@keyframes gtq{0%%{opacity:0}1%%{opacity:1}99%%{opacity:1}100%%{opacity:0}}@keyframes gtqn{from{opacity:0}}"
        % (".22" if light else ".3", n(Pscan, 3), n(H - hz, 1), n(Pf, 3), n(Pf, 3), halo, ".85" if light else "1",
           done_c, done_c))
    return "".join(out)


def _fractal(rnd, cx, cy, R, branch, radii):
    """A radial code graph: a root, its modules, their files, their symbols, each level fanned out in its parent's
    sector, with a little jitter. Returns the levels of nodes [(x, y, angle, sector, branch)] and the edges of each
    level as curves from parent to child (so a dash moving along them runs outward)."""
    levels = [[(cx, cy, -math.pi / 2, 2 * math.pi, 0)]]
    edges = []
    for L, b in enumerate(branch):
        nxt, eds = [], []
        for (px, py, a, sec, br) in levels[-1]:
            sub = sec / b
            for j in range(b):
                aa = (a + sub * j) if L == 0 else (a + (j - (b - 1) / 2) * sub * 0.9)
                aa += (rnd() - 0.5) * sub * 0.22
                rr = R * radii[L + 1] * (1 + (rnd() - 0.5) * 0.1)
                qx, qy = cx + rr * math.cos(aa), cy + rr * math.sin(aa)
                nxt.append((qx, qy, aa, sub, j if L == 0 else br))
                pr = math.hypot(px - cx, py - cy)        # bend outward: the control point is on the child's ray
                kx, ky = cx + pr * math.cos(aa), cy + pr * math.sin(aa)
                eds.append((j if L == 0 else br, f"M{n(px)} {n(py)}Q{n(kx)} {n(ky)} {n(qx)} {n(qy)}"))
        levels.append(nxt)
        edges.append(eds)
    return levels, edges


def motif_fractal(doc, data, box, mini, t0):
    """CodeGraph: a code graph as a living fractal. A root blooms into modules, files and symbols, level by level, in
    neon; dependency links cut across it; data streams outward along every edge; rings bloom from the modules; and
    behind it the same graph repeats at every depth, zooming past forever, like a flight through the codebase. The
    complexity is in a few groups moved by transform and opacity, not in thousands of animated nodes. The base style
    is the grown graph with its depth layers at rest."""
    x, y, w, h = box
    if mini:                                             # a card: the graph takes the right of the card, under the name
        x, y, w, h = x - 6, 64, w + 4, y + h + 10 - 64
    rnd = Rand(data.get("seed", "codegraph"))
    cx, cy = x + w / 2, y + h / 2
    R = min(w, h) / 2 * 0.94
    branch = data.get("branch") or ([5, 3, 3] if mini else [6, 3, 3])
    radii = [0, .34, .66, .95]
    levels, edges = _fractal(rnd, cx, cy, R, branch, radii)
    nb = branch[0]
    t_grow = t0 + 0.2
    grow = 1.7
    lvl_t = [t_grow + grow * r * 0.85 for r in radii]     # a level blooms as the reveal reaches it
    t_end = lvl_t[-1] + 0.6
    T = _cycle(t_end + 0.3)                               # a first guess; render() fits the periods to the real cycle
    out = []
    # the depth: the same graph, simplified, in three layers that zoom past forever (in defs, drawn by <use>)
    fid, eid, lid = doc.uid("cgz"), doc.uid("cge"), doc.uid("cgl")
    allp = "".join(e for eds in edges for _, e in eds)
    leaves = "".join(f"M{n(q[0])} {n(q[1])}h0" for q in levels[-1])
    # the edges and the symbols are written once and drawn by <use>: the graph, its glow, its data and its depth layers
    doc.defs.append(f'<path id="{eid}" d="{allp}" class="cgv"/><path id="{lid}" d="{leaves}" class="cgv"/>'
                    f'<g id="{fid}"><use href="#{eid}" class="cgzl"/><use href="#{lid}" class="cgzd"/></g>')
    Pz = 4.5 if mini else 6
    zs = [0.3 * 8 ** (q / 4) for q in range(5)]
    frames = "".join(f"{q * 25}%{{transform:scale({n(s, 3)}) rotate({n(-30 + 15 * q)}deg)"
                     + (";opacity:0" if q in (0, 4) else ";opacity:1" if q == 2 else "") + "}"
                     for q, s in enumerate(zs))
    nz = 4
    for q in range(nz):
        s0 = 0.3 * 8 ** ((q + 0.5) / nz)
        out.append(f'<g class="cgz{" cgz2" if q % 2 else ""}" style="transform-origin:{n(cx)}px {n(cy)}px;'
                   f'transform:scale({n(s0, 3)});opacity:{n(0.8 - 0.15 * q, 2)};animation-delay:-{n(Pz * (q + 0.5) / nz, 3)}s">'
                   f'<use href="#{fid}"/></g>')
    # warp streaks flying out of the root, past the depth layers
    rays = []
    for k in range(36 if mini else 48):
        a = 2 * math.pi * (k + rnd() * 0.8) / (36 if mini else 48)
        r0, r1 = R * (0.12 + 0.2 * rnd()), R * 2.8
        rays.append(f"M{n(cx + r0 * math.cos(a))} {n(cy + r0 * math.sin(a))}L{n(cx + r1 * math.cos(a))} {n(cy + r1 * math.sin(a))}")
    Pw = 1.2
    out.append(f'<path d="{"".join(rays)}" class="cgw"/>')
    # HUD rings round the graph, turning
    out.append(f'<g class="cgu" style="transform-origin:{n(cx)}px {n(cy)}px">'
               f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R * 1.07)}" class="cgr1"/>'
               f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R * 1.15)}" class="cgr2"/></g>')
    # the graph: a neon underglow and the edges, revealed outward from the root
    links = []
    l2 = levels[2]
    for i in range(0, len(l2), 2):                        # dependencies across modules
        a, b = l2[i], l2[(i * 7 + len(l2) // 3) % len(l2)]
        if a[4] == b[4]:
            continue
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        links.append(f"M{n(a[0])} {n(a[1])}Q{n(cx + (mx - cx) * .25)} {n(cy + (my - cy) * .25)} {n(b[0])} {n(b[1])}")
    out.append(f'<g class="cgg"{_delay(t_grow)}><use href="#{eid}" class="cge0"/><use href="#{eid}" class="cge"/>'
               f'<path d="{"".join(links)}" class="cgx"/></g>')
    # data streaming outward along every edge, once the graph has grown
    Pf = 1.4
    doc.periods.update(cgz=Pz, cgw=Pw, cgu=T, cgf=Pf * 2, cgb=Pf * 2)
    out.append(f'<g class="cgfl"{_delay(t_end - 0.3)}><use href="#{eid}" class="cgf"/>'
               + "".join(f'<circle cx="{n(q[0])}" cy="{n(q[1])}" r="{n(R * .1)}" class="cgb" '
                         f'style="animation-delay:-{n(Pf * 2 * k / nb, 2)}s"/>' for k, q in enumerate(levels[1]))
               + "</g>")
    # the nodes bloom level by level, each level burst out from the root
    pop = lambda t, inner: (f'<g class="cgn" style="transform-origin:{n(cx)}px {n(cy)}px;animation-delay:{n(t, 2)}s">'
                            f'{inner}</g>')
    out.append(pop(lvl_t[3] - 0.05, f'<use href="#{lid}" class="cgd3"/>'))
    out.append(pop(lvl_t[2], "".join(f'<circle cx="{n(q[0])}" cy="{n(q[1])}" r="{n(2.6 if mini else 3.2)}"/>'
                                     for q in levels[2]).join(['<g class="cgd2">', "</g>"])))
    out.append(pop(lvl_t[1], "".join(f'<circle cx="{n(q[0])}" cy="{n(q[1])}" r="{n(R * .085)}" class="cgh"/>'
                                     f'<circle cx="{n(q[0])}" cy="{n(q[1])}" r="{n(R * .045)}" class="cgd1"/>'
                                     for q in levels[1])))
    hexp = [(cx + R * .11 * math.cos(math.pi / 6 + k * math.pi / 3), cy + R * .11 * math.sin(math.pi / 6 + k * math.pi / 3))
            for k in range(6)]
    out.append(pop(t_grow, f'<path d="{poly(hexp, True)}" class="cgo"/>'
                           f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(R * .045)}" class="cgc"/>'))
    sw = 1.6 if mini else 1.3
    doc.css.append(
        ".cgv{vector-effect:non-scaling-stroke}"
        ".cgzl{fill:none;stroke:var(--z,var(--a4));stroke-width:1.2;stroke-opacity:.8}"
        ".cgzd{fill:none;stroke:var(--a1);stroke-width:2.6;stroke-linecap:round;stroke-opacity:.8}"
        ".cgz{animation:cgz %ss linear infinite}@keyframes cgz{%s}.cgz2{--z:var(--a2)}"
        ".cgw{fill:none;stroke:var(--edge);stroke-width:1.2;stroke-linecap:round;stroke-dasharray:5 31 2 34;"
        "stroke-opacity:.32;animation:cgw %ss linear infinite}@keyframes cgw{to{stroke-dashoffset:-72}}"
        ".cgu{animation:cgu %ss linear infinite}@keyframes cgu{to{transform:rotate(360deg)}}"
        ".cgr1{fill:none;stroke:var(--a1);stroke-width:1.5;stroke-dasharray:1.5 6;stroke-opacity:.7}"
        ".cgr2{fill:none;stroke:var(--a2);stroke-width:2;stroke-dasharray:46 14 6 14;stroke-opacity:.45}"
        ".cge0{fill:none;stroke:var(--a1);stroke-width:%s;stroke-opacity:.13;stroke-linecap:round}"
        ".cge{fill:none;stroke:var(--a1);stroke-width:%s;stroke-opacity:.85;stroke-linecap:round}"
        ".cgx{fill:none;stroke:var(--a2);stroke-width:1;stroke-opacity:.55;stroke-dasharray:3 3}"
        ".cgg{animation:cgg %ss cubic-bezier(.3,.6,.4,1) both}"
        "@keyframes cgg{from{clip-path:circle(0%% at 50%% 50%%)}to{clip-path:circle(80%% at 50%% 50%%)}}"
        ".cgfl{animation:cgfade .6s ease-out both}@keyframes cgfade{from{opacity:0}}"
        ".cgf{fill:none;stroke:var(--edge);stroke-width:%s;stroke-linecap:round;stroke-dasharray:.1 13.9;"
        "animation:cgf %ss linear infinite}@keyframes cgf{to{stroke-dashoffset:-28}}"
        ".cgb{fill:none;stroke:var(--a2);stroke-width:1.5;opacity:0;transform-box:fill-box;transform-origin:50%% 50%%;"
        "animation:cgb %ss ease-out infinite}@keyframes cgb{0%%{opacity:.9;transform:scale(.5)}100%%{opacity:0;transform:scale(2.6)}}"
        ".cgn{animation:cgn .55s cubic-bezier(.3,1.5,.5,1) both}@keyframes cgn{from{opacity:0;transform:scale(.55)}}"
        ".cgd3{fill:none;stroke:var(--a3);stroke-width:%s;stroke-linecap:round}"
        ".cgd2{fill:var(--a2)}.cgd1{fill:var(--edge)}.cgh{fill:var(--a1);fill-opacity:.35}"
        ".cgo{fill:var(--bg);stroke:var(--a1);stroke-width:2.5}.cgc{fill:var(--a2)}"
        % (n(Pz, 3), frames, n(Pw, 3), n(T, 3), n(sw * 5, 1), n(sw, 1), n(grow, 2), n(2.6 if mini else 2.8, 1), n(Pf * 2, 3),
           n(Pf * 2, 3), n(4 if mini else 4.5, 1)))
    return "".join(out)


MOTIFS = {"cad": motif_cad, "stack": motif_stack, "ops": motif_ops, "catalog": motif_catalog, "eye": motif_eye, "face": motif_face, "terminal": motif_terminal,
          "circuit": motif_circuit, "chart": motif_chart, "dial": motif_dial, "slides": motif_slides,
          "linkage": motif_linkage, "wave": motif_wave, "crystal": motif_crystal, "radar": motif_radar,
          "fight": motif_fight, "network": motif_network, "pcb": motif_pcb,
          "board": motif_board, "topology": motif_topology, "fractal": motif_fractal}


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
    t0, stagger, dur = (0.05, 0.02, 0.7)                            # a quick flourish: the name reads within ~1 s
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



LAYOUT = {  # hero: a README's opening banner; spot: a large profile card; margin, name cap, tagline size/lines/width
    "hero": dict(margin=48, fs_max=150, tsize=27, tlines=2, twidth=560, cs=16, ch=34, chip_w=600),
    "spot": dict(margin=34, fs_max=112, tsize=29, tlines=3, twidth=400, cs=17, ch=34, chip_w=420),
}


def _chip(doc, c, x, y, cs, ch, cap, mini, delay=None):
    cw = doc.width(c, "medium", cs) + (24 if mini else 34)
    dot = c == "private"
    svg = (f'<g class="chip{" in" if delay is not None else ""}"{_delay(delay) if delay is not None else ""}>'
           f'<rect x="{n(x)}" y="{n(y)}" width="{n(cw)}" height="{ch}" rx="{n(ch / 2)}" class="{"cpv" if dot else "cbg"}"/>'
           f'<circle cx="{n(x + (11 if mini else 14))}" cy="{n(y + ch / 2)}" r="{n(3.5 if mini else 4)}" fill="var(--a1)"/>'
           f'{doc.text(c, "medium", cs, x + (20 if mini else 25), y + ch / 2 + cs * cap / 2, fill="var(--muted)")}</g>')
    return svg, cw


def _cta(doc, spec, x, y, fs, ph, cap):
    """A call-to-action pill (the card links there): a play triangle or an arrow, then the label. Returns its width."""
    cta = spec["cta"]
    pw = doc.width(cta, "medium", fs) + 50
    k = ph / 32
    icon = (f'<path d="M{n(x + 15 * k)} {n(y + 9 * k)}l{n(13 * k)} {n(7 * k)}-{n(13 * k)} {n(7 * k)}z" fill="var(--bg)"/>'
            if spec.get("cta_icon") == "play" else
            f'<path d="M{n(x + 13 * k)} {n(y + ph / 2)}h{n(14 * k)}m-{n(5 * k)}-{n(5 * k)} {n(5 * k)} {n(5 * k)}-{n(5 * k)} {n(5 * k)}" '
            f'fill="none" stroke="var(--bg)" stroke-width="{n(2.4 * k)}" stroke-linecap="round" stroke-linejoin="round"/>')
    doc.css.append(".cta{animation:cta 2.4s 1s ease-in-out infinite}@keyframes cta{50%{opacity:.78}}")
    return (f'<g class="cta"><rect x="{n(x)}" y="{n(y)}" width="{n(pw)}" height="{n(ph)}" rx="{n(ph / 2)}" fill="var(--a1)"/>'
            f'{icon}{doc.text(cta, "medium", fs, x + 37 * k, y + ph / 2 + fs * cap / 2, fill="var(--bg)")}</g>'), pw


def _card_text(doc, spec, title, W, H, adv, cap):
    """A profile card, made to be read at a third of a README's width: the name set large and solid from the first
    frame (cards often start animating only once scrolled into view, so nothing a reader needs may wait on a
    timeline), a three-line tagline, one chip, and the motif to the right. Only a quick underline and the motif move."""
    margin = 26
    upm = glyphs()["upm"]
    fs = min(72, (W - margin * 2) / (adv / upm))
    s = fs / upm
    base = margin + cap * fs
    tr = f"translate({n(margin)} {n(base)}) scale({n(s, 5)} {n(-s, 5)})"
    doc.defs.append(f'<linearGradient id="ng" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{n(adv, 0)}" y2="0">'
                    f'<stop offset="0" stop-color="var(--a1)"/><stop offset="1" stop-color="var(--a2)"/></linearGradient>')
    out = [f'<g transform="{tr}" fill="url(#ng)">{doc.uses(title, "bold")}</g>']
    y = base + max(10, 0.2 * fs + 4)
    out.append(f'<rect class="ul" x="{margin}" y="{n(y)}" width="64" height="5" rx="2.5" fill="url(#gr)"/>')
    name_end = margin + adv * s + 18
    beside = W - margin - name_end >= W * 0.36          # a short name leaves the full height beside it free
    left = max(name_end, W * 0.6) if beside else W * 0.6
    box = (left, 18, W - 14 - left, H - 36) if beside else (left, y + 4, W - 14 - left, H - y - 18)
    lines, tsize = wrap(doc, spec.get("tagline", ""), "medium", 28, left - margin - 14, 3)
    y += 14 + tsize * cap
    for i, line in enumerate(lines):
        out.append(doc.text(line, "medium", tsize, margin, y + i * tsize * 1.28, fill="var(--ink)"))
    y_end = y + (len(lines) - 1) * tsize * 1.28
    chips = (["private"] if spec.get("private") else []) + spec.get("facts", [])[:1]
    cs, ch = 15, 28
    yy = H - margin - ch + 6
    x = margin
    cta = spec.get("cta")
    if cta and yy > y_end + 8:                      # a call to action: the card links there
        ph = 32
        yy = H - margin - ph + 6
        svg, pw = _cta(doc, spec, x, yy, 17, ph, cap)
        out.append(svg)
        x += pw + 8
        yy += (ph - ch) / 2
        chips = chips[:1] if x + 90 < left else []
    if chips and yy > y_end + 8:
        svg, _ = _chip(doc, chips[0], x, yy, cs, ch, cap, True)
        out.append(svg)
    return "".join(out), "", 0.0, box


def _hero_text(doc, spec, title, kind, W, H, adv, cap):
    """A README hero or a profile spotlight card. On a hero the name grows from a quick drafting sketch and the tagline
    fades in; a spotlight's name and tagline are still from the first frame. The motif takes the space the name leaves."""
    L = LAYOUT[kind]
    margin = L["margin"]
    upm = glyphs()["upm"]
    fs = min(spec.get("name_size", L["fs_max"]), L["fs_max"], (W - margin * 2) / (adv / upm))
    kick = spec.get("kicker")                           # a telemetry line over the name, valpatel.com style
    base = margin + (34 if kick else 0) + cap * fs + 4
    s = fs / upm
    tr = f"translate({n(margin)} {n(base)}) scale({n(s, 5)} {n(-s, 5)})"
    doc.defs.append(f'<linearGradient id="ng" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{n(adv, 0)}" y2="0">'
                    f'<stop offset="0" stop-color="var(--a1)"/><stop offset="1" stop-color="var(--a2)"/></linearGradient>')
    out = []
    if kick:
        ks = 15
        out.append(f'<circle class="led" cx="{n(margin + 5)}" cy="{n(margin + 6)}" r="4.5" fill="var(--a2)"/>'
                   + doc.text(kick.upper(), "medium", ks, margin + 20, margin + 6 + ks * cap / 2, fill="var(--a1)", track=140))
        doc.css.append(".led{animation:led 1.6s ease-in-out infinite}@keyframes led{50%{opacity:.3}}")
    still = kind == "spot"      # spotlights sit below the fold and start late: their name is there from the first frame
    if still:
        sketch_css, t_name = "", 0.3
        out.append(f'<g transform="{tr}" fill="url(#ng)">{doc.uses(title, "bold")}</g>')
    else:
        letters_svg, sketch_css, t_name = _sketch_title(doc, title, margin, base, s, adv, False)
        if spec.get("glow") and getattr(doc, "theme", "") == "dark":    # a neon glow behind the name, once drawn
            doc.defs.append('<filter id="nglow" x="-10%" y="-40%" width="120%" height="180%">'
                            '<feGaussianBlur stdDeviation="9"/></filter>')
            out.append(f'<g class="in" filter="url(#nglow)" opacity="{spec["glow"]}"{_delay(t_name)}>'
                       f'<g transform="{tr}" fill="url(#ng)">{doc.uses(title, "bold")}</g></g>')
        out.append(letters_svg)
    doc.defs.append(f'<clipPath id="nc" transform="{tr}">{doc.uses(title, "bold")}</clipPath>')
    out.append(f'<g clip-path="url(#nc)"><rect class="sh" x="{n(margin - 160)}" y="{n(margin - 10)}" width="120" '
               f'height="{n(fs + 20)}" fill="#fff" transform="skewX(-20)"/></g>')
    y = base + max(22, 0.2 * fs + 8)                    # clear of descenders
    out.append(f'<rect class="ul" x="{n(margin)}" y="{n(y)}" width="132" height="6" rx="3" fill="url(#gr)"/>')
    name_end = margin + adv * s + 24
    if W - margin - name_end >= W * 0.35:               # a short name leaves the full height beside it free
        left = max(name_end, W * 0.53)
        box = (left, 22, W - margin - left, H - 44)
    else:
        left = W * 0.53
        box = (left, base + 30, W * 0.47 - margin, H - base - 52)
    twidth = min(L["twidth"], left - margin - 16)
    lines, tsize = wrap(doc, spec.get("tagline", ""), "medium", L["tsize"], twidth, L["tlines"])
    y += 24 + tsize * cap
    for i, line in enumerate(lines):
        text = doc.text(line, "medium", tsize, margin, y + i * tsize * 1.3, fill="var(--ink)")
        out.append(text if still else f'<g class="tg in"{_delay(t_name * 0.6 + 0.1 * i)}>{text}</g>')
    y_text_end = y + (len(lines) - 1) * tsize * 1.3
    cs, ch = L["cs"], L["ch"]
    rows = [[]]
    for c in spec.get("facts", []):
        cw = doc.width(c, "medium", cs) + 34
        if rows[-1] and sum(r[1] + 8 for r in rows[-1]) + cw > min(L["chip_w"], left - margin - 8):
            rows.append([])
        rows[-1].append((c, cw))
    rows = [r for r in rows if r]
    x0 = margin
    if spec.get("cta"):                                 # the call to action leads the bottom row
        svg, pw = _cta(doc, spec, margin, H - margin - ch, L["cs"] + 3, ch, cap)
        out.append(svg)
        x0 = margin + pw + 10
        rows = [rows[-1][:max(1, len(rows[-1]) - 1)]] if rows else []
    for ri, row in enumerate(reversed(rows)):
        x = x0 if ri == 0 else margin
        yy = H - margin - ch - ri * (ch + 8)
        if yy < y_text_end + 10:
            break
        for ci, (c, cw) in enumerate(row):
            svg, _ = _chip(doc, c, x, yy, cs, ch, cap, False, t_name + 0.15 * (ci + ri * 3))
            out.append(svg)
            x += cw + 8
    return "".join(out), sketch_css, t_name, box


# ------------------------------------------------------------------------------------------------ the loop

# endless animations that start once their part is drawn (network packets, stack packets, CAN pulses, wifi arcs,
# talk bars): the loop gates them so they show only while their part does. Every other delay on an endless
# animation is a phase offset on a part that shows from the start (eyes, nodes, bars), left running as it is.
WAITS = {"pulse", "pk", "pls", "wave", "talk"}
HOLD = 4.0          # seconds the finished frame stays up after the last element lands, before the banner restarts
REST = 3.0          # seconds an ambient animation (a scan) rests at its still frame before the restart
RESET = 0.6         # seconds the animated elements take to fade out at the end of a cycle
SPREAD = 0.25       # elements of one animation whose delays lie within this many seconds share one set of keyframes
GATE = 0.3          # seconds a delayed endless animation (a pulse, a wave) takes to fade in when it starts
_INITIAL = {"opacity": "1", "fill-opacity": "1", "stroke-dashoffset": "0", "transform": "none", "clip-path": "none"}
_TIMING = re.compile(r"(ease(-in|-out|-in-out)?|linear|step-start|step-end|(cubic-bezier|steps)\([^)]*\))$")


def _split(text: str, sep: str = ",") -> list:
    """``text`` split on ``sep`` outside parentheses."""
    out, depth, cur = [], 0, ""
    for c in text:
        depth += (c == "(") - (c == ")")
        if c == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
    return [x.strip() for x in out + [cur] if x.strip()]


def _blocks(css: str) -> list:
    """The top-level ``prelude{body}`` blocks of a stylesheet, braces matched."""
    out, i = [], 0
    while i < len(css) and css[i:].strip():
        j = css.index("{", i)
        depth, k = 1, j + 1
        while depth:
            depth += (css[k] == "{") - (css[k] == "}")
            k += 1
        out.append((css[i:j].strip(), css[j + 1:k - 1]))
        i = k
    return out


def _decls(body: str) -> list:
    return [tuple(x.strip() for x in d.split(":", 1)) for d in _split(body, ";")]


def _secs(tok: str) -> float:
    return float(tok[:-2]) / 1000 if tok.endswith("ms") else float(tok[:-1])


def _anim(item: str) -> dict:
    """One entry of an ``animation`` list, by part. Times are seconds; ``count`` is None for ``infinite``."""
    a = {"name": None, "dur": 0.0, "delay": 0.0, "timing": "ease", "count": 1.0, "rest": []}
    times = []
    for tok in re.findall(r"[a-z-]+\([^)]*\)|\S+", item):
        if re.fullmatch(r"-?(\d+\.?\d*|\.\d+)m?s", tok):
            times.append(_secs(tok))
        elif _TIMING.match(tok):
            a["timing"] = tok
        elif tok == "infinite":
            a["count"] = None
        elif re.fullmatch(r"\d+\.?\d*|\.\d+", tok):
            a["count"] = float(tok)
        elif tok in ("normal", "reverse", "alternate", "alternate-reverse", "none", "forwards", "backwards", "both",
                     "running", "paused"):
            a["rest"].append(tok)
        else:
            a["name"] = tok
    a["dur"], a["delay"] = (times + [0.0, 0.0])[:2]
    return a


def _selector(sel: str) -> list:
    """A selector as compounds [(tag or None, {classes})], for type, class and descendant selectors only."""
    if re.search(r"[^\w\s.*-]", sel):
        raise ValueError(f"the loop cannot match the selector {sel!r}")
    out = []
    for comp in sel.split():
        tag, *classes = comp.split(".")
        out.append((None if tag in ("", "*") else tag, set(classes)))
    return out


def _matches(compounds, path) -> bool:
    """``path`` is [(tag, classes)] from the root to the element; descendant combinators only."""
    hit = lambda c, e: (c[0] is None or c[0] == e[0]) and c[1] <= e[1]
    if not path or not hit(compounds[-1], path[-1]):
        return False
    i = len(compounds) - 2
    for e in reversed(path[:-1]):
        if i < 0:
            break
        if hit(compounds[i], e):
            i -= 1
    return i < 0


def _scan(rules, markup: str) -> tuple:
    """Walk ``markup`` with the stylesheet's ``rules``. Returns (found, gates): ``found`` lists the elements with an
    animation that plays once, as (match, attributes, style declarations, animations, computed style); ``gates``
    lists the elements whose endless animation in ``WAITS`` waits for a delay (a pulse that starts once its board is
    drawn) with nothing that loops around or inside them, as [start, end, delay] in ``markup``. An element counts as looping when
    it plays an animation once, or repeats one whose keyframes the loop wrote (``L<n>``)."""
    tag_re = re.compile(r'<(/?)([A-Za-z][\w:-]*)((?:\s+[\w:-]+="[^"]*")*)\s*(/?)>')
    path, stack, found, gates = [], [], [], []

    def close(entry, end):
        if entry["gate"] is not None and not entry["inner"]:
            entry["gate"][1] = end
            gates.append(entry["gate"])
        if (entry["looped"] or entry["inner"]) and stack:
            stack[-1]["inner"] = True

    for m in tag_re.finditer(markup):
        if m.group(1):
            path.pop()
            close(stack.pop(), m.end())
            continue
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(3)))
        path.append((m.group(2), set(attrs.get("class", "").split())))
        style = _decls(attrs.get("style", ""))
        hits = sorted((r for r in rules if _matches(r[2], path)), key=lambda r: (r[0], r[1]))
        computed = {}
        for prop, val in [d for r in hits for d in r[3]] + style:
            computed[prop] = val
            if prop == "animation":
                computed.pop("animation-delay", None)
        anims = []
        if "animation" in computed:
            anims = [_anim(x) for x in _split(computed["animation"])]
            if "animation-delay" in computed:
                delays = [_secs(t) for t in _split(computed["animation-delay"])]
                for i, a in enumerate(anims):
                    a["delay"] = delays[i % len(delays)]
        once = any(a["count"] is not None for a in anims)
        looped = once or any(re.fullmatch(r"L\d+", a["name"] or "") for a in anims)
        if once:
            found.append((m, attrs, style, anims, dict(computed)))
        waits = [a["delay"] for a in anims if a["count"] is None and a["delay"] > 0 and a["name"] in WAITS]
        inside = any(e["looped"] or e["gate"] is not None for e in stack)
        entry = {"looped": looped, "inner": False,
                 "gate": [m.start(), None, min(waits)] if waits and not looped and not inside else None}
        stack.append(entry)
        if m.group(4):
            path.pop()
            close(stack.pop(), m.end())
    return found, gates


def drifting(text: str) -> list:
    """The elements of a rendered banner whose endless animation in ``WAITS`` waits for a delay but is not inside
    anything that loops: from the second cycle on it would run out of step, on a banner that is fading or being rebuilt."""
    css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)
    markup = re.sub(r"\s*</svg>\s*$", "", text[text.index("</style>") + 8:])   # the root's end tag
    rules = []
    for order, (pre, body) in enumerate(_blocks(css)):
        if not pre.startswith("@"):
            for sel in _split(pre):
                if not re.search(r"[^\w\s.*-]", sel):           # the theme's attribute selectors set colours only
                    comp = _selector(sel)
                    rules.append(((sum(len(c[1]) for c in comp), sum(c[0] is not None for c in comp)), order, comp,
                                  _decls(body)))
    return [markup[g[0]:g[0] + 80] for g in _scan(rules, markup)[1]]


def _loop(css: str, markup: str, ambient=()) -> tuple:
    """Make a banner loop. Every element whose animation plays once (an intro: it fades, slides, draws or traces in)
    is given keyframes that span one cycle of ``T`` seconds, repeated forever: the intro at its own time, the finished
    frame held for ``HOLD`` seconds after the last element lands (``REST`` after an ``ambient`` animation such as a
    scan ends), a ``RESET`` fade out, and the restart, so every part restarts in step. Elements of one animation whose
    delays lie within ``SPREAD`` share keyframes and keep their stagger as an ``animation-delay``; the earlier ones
    fade out that much sooner, so a banner clears in the order it was built. Animations that already repeat are left
    as they are. The keyframes' easing is kept stop by stop; values a keyframe leaves out (CSS takes them from the
    element's own style) are read from the stylesheet or the element's attributes. The base style is untouched, so
    under reduced motion (no animation) every element still shows the finished frame.
    Returns (css, markup, T); T is 0 when nothing plays once."""
    blocks = _blocks(css)
    rules, frames = [], {}
    for order, (pre, body) in enumerate(blocks):
        if pre.startswith("@keyframes"):
            stops = []
            for at, decl in _blocks(body):
                for q in _split(at):
                    stops.append(({"from": 0.0, "to": 1.0}.get(q) if q in ("from", "to") else float(q[:-1]) / 100,
                                  dict(_decls(decl))))
            frames[pre.split()[1]] = sorted(stops, key=lambda x: x[0])
        elif not pre.startswith("@"):
            for sel in _split(pre):
                comp = _selector(sel)
                spec = (sum(len(c[1]) for c in comp), sum(c[0] is not None for c in comp))
                rules.append((spec, order, comp, _decls(body)))
    found, gates = _scan(rules, markup)
    if not found and not gates:
        return css, markup, 0.0

    def base(prop, computed, attrs):
        if prop in computed:
            return computed[prop]
        if prop == "transform" and "transform" in attrs:
            raise ValueError("the loop cannot restore a transform attribute; animate a child element instead")
        return attrs.get(prop, _INITIAL.get(prop))

    once = [(i, a) for i, f in enumerate(found) for a in f[3] if a["count"] is not None]
    for i, a in once:
        if a["count"] != 1 or "both" not in a["rest"] and "backwards" not in a["rest"] or set(a["rest"]) & {
                "reverse", "alternate", "alternate-reverse"}:
            raise ValueError(f"the loop needs a single forward play that fills backwards: {a}")
        if a["name"] not in frames:
            raise ValueError(f"no @keyframes {a['name']}")
        for b in found[i][3]:
            if b["count"] is None and b["name"] in frames:
                mine = {p for _, d in frames[a["name"]] for p in d} | {"opacity"}    # the loop fades it too
                if mine & {p for _, d in frames[b["name"]] for p in d}:
                    raise ValueError(f"{a['name']} and the endless {b['name']} animate one property on one element")
    built = [a["delay"] + a["dur"] for _, a in once if a["name"] not in ambient] + [g[2] + GATE for g in gates]
    rested = [a["delay"] + a["dur"] for _, a in once if a["name"] in ambient]
    T = round(max([max(built, default=0) + HOLD] + [t + REST for t in rested]) + RESET, 1)
    # group: one set of keyframes per animation, element style and cluster of delays
    groups = {}
    for i, a in once:
        f = found[i]
        props = list(dict.fromkeys([p for _, d in frames[a["name"]] for p in d] + ["opacity"]))
        start = {p: base(p, f[4], f[1]) for p in props}      # CSS fills a missing 0 % or 100 % from the base style
        end = dict(start)
        for at, d in frames[a["name"]]:
            (start if at == 0 else end if at == 1 else {}).update(d)
        key = (a["name"], a["dur"], a["timing"], tuple(start.items()), tuple(end.items()))
        groups.setdefault(key, []).append((a["delay"], i, a))
    names, out_frames, inline = {}, [], {}
    pct = lambda t: n(100 * t / T, 2) + "%"
    for (name, dur, timing, start, end), members in groups.items():
        start, end = dict(start), dict(end)
        members.sort(key=lambda x: x[0])
        clusters = []
        for d, i, a in members:
            if clusters and d - clusters[-1][0][0] <= SPREAD:
                clusters[-1].append((d, i, a))
            else:
                clusters.append([(d, i, a)])
        for cl in clusters:
            d0, spread = cl[0][0], cl[-1][0] - cl[0][0]
            ef = f"animation-timing-function:{timing}"
            body = lambda v: ";".join(f"{p}:{x}" for p, x in v.items())
            stops = [(0, body(start))] if d0 > 0 else []
            stops.append((d0, body(start) + ";" + ef))
            for at, d in frames[name]:
                if 0 < at < 1:
                    stops.append((d0 + at * dur, body(d) + ";" + ef))
            hidden = body(dict(end, opacity="0"))
            stops += [(d0 + dur, body(end)), (T - RESET - spread, body(end)), (T - spread, hidden), (T, hidden)]
            by = {}
            for t, b in stops:
                by.setdefault(b, []).append(pct(t))
            kf = "".join(f"{','.join(dict.fromkeys(ps))}{{{b}}}" for b, ps in by.items())
            if kf not in names:
                names[kf] = f"L{len(names)}"
                out_frames.append(f"@keyframes {names[kf]}{{{kf}}}")
            for d, i, a in cl:
                lag = f" {n(d - d0, 2)}s backwards" if d - d0 > 0 else ""
                inline[(i, id(a))] = f"{names[kf]} {n(T, 2)}s{lag} infinite"
    # a gate: hidden until its endless animation starts, shown, faded out with the rest, so it restarts in step
    gate_open = {}
    gates.sort(key=lambda g: g[2])
    clusters = []
    for g in gates:
        if clusters and g[2] - clusters[-1][0][2] <= SPREAD:
            clusters[-1].append(g)
        else:
            clusters.append([g])
    for cl in clusters:
        d0, spread = cl[0][2], cl[-1][2] - cl[0][2]
        stops = [(0, "opacity:0"), (d0, "opacity:0;animation-timing-function:ease-out"), (d0 + GATE, "opacity:1"),
                 (T - RESET - spread, "opacity:1"), (T - spread, "opacity:0"), (T, "opacity:0")]
        by = {}
        for t, b in stops:
            by.setdefault(b, []).append(pct(t))
        kf = "".join(f"{','.join(dict.fromkeys(ps))}{{{b}}}" for b, ps in by.items())
        if kf not in names:
            names[kf] = f"L{len(names)}"
            out_frames.append(f"@keyframes {names[kf]}{{{kf}}}")
        for g in cl:
            lag = f" {n(g[2] - d0, 2)}s backwards" if g[2] - d0 > 0 else ""
            gate_open[id(g)] = f'<g style="animation:{names[kf]} {n(T, 2)}s{lag} infinite">'
    clash = set(names.values()) & set(frames)
    if clash:
        raise ValueError(f"generated keyframe names clash with {clash}")
    # rewrite each element's style (repeating animations keep their own timing and delay) and wrap each gated one
    # at one offset: an element that ends there closes first, then a gate opens, then the next tag is rewritten
    edits = [(g[0], 1, g[0], gate_open[id(g)]) for g in gates] + [(g[1], 0, g[1], "</g>") for g in gates]
    for i, (m, attrs, style, anims, _) in enumerate(found):
        lst = []
        for a in anims:
            if a["count"] is None:
                lst.append(" ".join([a["name"], n(a["dur"], 2) + "s", n(a["delay"], 2) + "s", a["timing"], "infinite"]
                                    + [r for r in a["rest"]]))
            else:
                lst.append(inline[(i, id(a))])
        decl = [(p, v) for p, v in style if p not in ("animation", "animation-delay")] + [("animation", ",".join(lst))]
        new_style = ";".join(f"{p}:{v}" for p, v in decl)
        tag = m.group(0)
        if "style" in attrs:
            tag = tag.replace(f'style="{attrs["style"]}"', f'style="{new_style}"', 1)
        else:
            tag = tag[:-2] + f' style="{new_style}"/>' if tag.endswith("/>") else tag[:-1] + f' style="{new_style}">'
        edits.append((m.start(), 2, m.end(), tag))
    pieces, at = [], 0
    for start, _, end, text in sorted(edits, key=lambda e: (e[0], e[1])):
        pieces += [markup[at:start], text]
        at = end
    markup = "".join(pieces) + markup[at:]
    # drop the play-once declarations (every element they reached now has its own) and keyframes nothing uses
    kept = []
    for pre, body in blocks:
        if not pre.startswith("@"):
            ds = _decls(body)
            ds2 = [(p, v) for p, v in ds if not (p == "animation" and any(_anim(x)["count"] is not None for x in _split(v)))]
            if not ds2:
                continue
            if ds2 != ds:
                body = ";".join(f"{p}:{v}" for p, v in ds2)
        kept.append((pre, body))
    text = "".join(f"{pre}{{{body}}}" for pre, body in kept if not pre.startswith("@keyframes")) + markup
    used = set(re.findall(r"animation:([^;}\"]+)", text))
    used = {_anim(x)["name"] for u in used for x in _split(u)}
    css = "".join(f"{pre}{{{body}}}" for pre, body in kept
                  if not pre.startswith("@keyframes") or pre.split()[1] in used) + "".join(out_frames)
    return css, markup, T


def timed(text: str) -> list:
    """The animations in a rendered banner that do not repeat forever (none, once it loops): every ``animation``
    item without ``infinite``, and every ``animation-iteration-count`` that is not ``infinite``. ``animation:none``
    (reduced motion) is not an animation; the generator writes no other longhand."""
    out = []
    for m in re.finditer(r"animation(-iteration-count)?\s*:([^;}\"]+)", text, re.I):
        value = m.group(2).replace("!important", "").strip()
        if m.group(1):
            out += [f"iteration count {c}" for c in _split(value) if c.lower() != "infinite"]
        else:
            out += [x for x in _split(value) if x.lower() != "none" and _anim(x)["count"] is not None]
    return out


def render(spec: dict, theme: str) -> str:
    kind = spec.get("kind", "hero")
    W, H = SIZES[kind]
    pal = palette(spec.get("palette", "teal"), "light" if theme == "auto" else theme)
    doc = Doc()
    doc.theme, doc.size = theme, (W, H)
    mini = kind == "card"
    title = spec.get("title", spec["name"])
    body = []
    cap = glyphs()["cap"] / glyphs()["upm"]
    adv = doc.width(title, "bold", glyphs()["upm"])
    if mini:
        body_svg, sketch_css, t_name, box = _card_text(doc, spec, title, W, H, adv, cap)
        body.append(body_svg)
    else:
        body_svg, sketch_css, t_name, box = _hero_text(doc, spec, title, kind, W, H, adv, cap)
        body.append(body_svg)
    m = motif_data(spec)
    motif_svg = MOTIFS[m["kind"]](doc, m, box, mini, 0.3 if mini else 0.5)

    label = spec.get("alt") or f"{title}: {spec.get('tagline', '')}".strip(": ")
    # the shine sweeps the drawn title once, so the loop gives it a pass in every cycle (off the banner either side)
    css = sketch_css + (".sh{opacity:.35;transform:translateX(-400px) skewX(-20deg);animation:shine 1.76s %ss ease-in-out both}"
           "@keyframes shine{0%%{transform:translateX(-200px) skewX(-20deg)}100%%{transform:translateX(%spx) skewX(-20deg)}}"
           ".ul{transform-box:fill-box;transform-origin:0 0;animation:grow .9s %ss ease-out both}"
           "@keyframes grow{from{transform:scaleX(0)}}"
           ".in{animation:fade .7s ease-out both}@keyframes fade{from{opacity:0;transform:translateY(6px)}}"
           ".cbg{fill:var(--bg2);stroke:var(--line)}.cpv{fill:none;stroke:var(--a1);stroke-dasharray:4 3}"
           % (n(t_name + 0.6, 2), n(W + 400), n(t_name * 0.5, 2))) + "".join(dict.fromkeys(doc.css))
    if theme == "light":
        css = css.replace(".sh{opacity:.35", ".sh{opacity:.55")
    bg = (f'<linearGradient id="bgg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{pal["bg"]}"/>'
          f'<stop offset="1" stop-color="{pal["bg2"]}"/></linearGradient>'
          f'<radialGradient id="glow" cx=".78" cy=".62" r=".5"><stop offset="0" stop-color="{pal["a1"]}" '
          f'stop-opacity="{pal["glow"]}"/><stop offset="1" stop-color="{pal["a1"]}" stop-opacity="0"/></radialGradient>'
          f'<linearGradient id="gr" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="var(--a1)"/>'
          f'<stop offset="1" stop-color="var(--a2)"/></linearGradient>'
          + (f'<pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" '
             f'stroke="{pal["line"]}" stroke-width=".8"/></pattern>' if spec.get("backdrop") == "grid" else
             f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" '
             f'fill="{pal["line"]}"/></pattern>'))
    frame = (f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#bgg)"/>'
             f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#dots)" opacity=".7"/>'
             f'<rect width="{W}" height="{H}" rx="{14 if mini else 18}" fill="url(#glow)"/>'
             f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="{14 if mini else 18}" fill="none" stroke="{pal["line"]}"/>')
    if spec.get("hud"):                                 # HUD corner brackets
        i, L = 12, 28
        frame += (f'<path d="M{i} {i + L}V{i}H{i + L}M{W - i - L} {i}H{W - i}V{i + L}M{W - i} {H - i - L}V{H - i}'
                  f'H{W - i - L}M{i + L} {H - i}H{i}V{H - i - L}" fill="none" stroke="var(--a1)" stroke-width="2.5" '
                  f'stroke-linecap="square"/>')
    desc = spec.get("desc", "")
    src = m.get("source") if isinstance(m.get("source"), dict) else {}
    if desc and src.get("repo") and src.get("commit") and not spec.get("private"):
        desc += f" Drawn from {src['repo']} at commit {src['commit'][:12]}."
    markup = (f"<defs>{bg}{''.join(doc.defs)}{doc.glyph_defs()}</defs>{frame}"
              + f'<g class="mo">{motif_svg}</g>' + "".join(body))
    css, markup, T = _loop(css, markup, doc.ambient)
    for name, near in doc.periods.items():               # a frame and the frame a cycle later are the same
        css = re.sub(r"(animation:%s )[\d.]+s" % name, lambda m: m.group(1) + n(_period(T or near, near), 3) + "s", css)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="{attr(label)}"><title>{escape(label)}</title>'
            + (f"<desc>{escape(desc)}</desc>" if desc else "")
            + f"<style>{css}{REDUCED_MOTION}</style>{markup}</svg>\n")
    return _colour(svg, spec.get("palette", "teal"), theme)


KEYS = ("bg2", "bg", "ink", "muted", "line", "edge", "a1", "a2", "a3", "a4", "f1", "f2", "f3", "dk")


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
    keys = [k for k in KEYS if k not in ("a3", "a4") or f"var(--{k})" in style]   # extra accents only when used
    decl = lambda p: "svg{" + ";".join(f"--{k}:{p[k]}" for k in keys) + "}"
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
    for a in timed(text):
        out.append(f"an animation that plays once and stops ({a}): every timed animation must repeat")
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


def _sexp(text: str):
    """A KiCad s-expression as nested lists of strings (quoted strings unquoted)."""
    stack = [[]]
    for m in re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text):
        t = m.group()
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(re.sub(r"\\(.)", r"\1", t[1:-1]) if t[0] == '"' else t)
    return stack[0][0]


def _kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _xy(node, name):
    c = _kids(node, name)
    return (float(c[0][1]), float(c[0][2])) if c else None


def _arc_pts(a, m, b, steps=12):
    """Points along the circular arc through a, m, b."""
    ax, ay = a
    bx, by = b
    mx, my = m
    dd = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(dd) < 1e-12:
        return [a, b]
    ux = ((ax ** 2 + ay ** 2) * (my - by) + (mx ** 2 + my ** 2) * (by - ay) + (bx ** 2 + by ** 2) * (ay - my)) / dd
    uy = ((ax ** 2 + ay ** 2) * (bx - mx) + (mx ** 2 + my ** 2) * (ax - bx) + (bx ** 2 + by ** 2) * (mx - ax)) / dd
    r = math.dist((ux, uy), a)
    t0, tm, t1 = (math.atan2(p[1] - uy, p[0] - ux) for p in (a, m, b))
    span = (t1 - t0) % (2 * math.pi)
    if (tm - t0) % (2 * math.pi) > span:          # the arc runs the other way round
        span -= 2 * math.pi
    return [(ux + r * math.cos(t0 + span * k / steps), uy + r * math.sin(t0 + span * k / steps)) for k in range(steps + 1)]


def _shape_lines(g):
    """Polylines (local mm) for one gr_*/fp_* graphic."""
    kind = g[0].split("_", 1)[1]
    if kind == "line":
        return [[_xy(g, "start"), _xy(g, "end")]]
    if kind == "rect":
        (x0, y0), (x1, y1) = _xy(g, "start"), _xy(g, "end")
        return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]
    if kind == "arc":
        return [_arc_pts(_xy(g, "start"), _xy(g, "mid"), _xy(g, "end"))]
    if kind == "circle":
        c, e = _xy(g, "center"), _xy(g, "end")
        r = math.dist(c, e)
        return [[(c[0] + r * math.cos(2 * math.pi * k / 24), c[1] + r * math.sin(2 * math.pi * k / 24)) for k in range(25)]]
    if kind == "poly":
        pts = [(float(p[1]), float(p[2])) for p in _kids(_kids(g, "pts")[0], "xy")]
        return [pts + pts[:1]]
    return []


def _chain(lines, tol=1e-3):
    """Join polylines that share end points into as few polylines as possible (closed loops end where they start)."""
    lines = [list(l) for l in lines if len(l) > 1]
    out = []
    while lines:
        cur = lines.pop(0)
        grown = True
        while grown:
            grown = False
            for i, l in enumerate(lines):
                if math.dist(cur[-1], l[0]) < tol:
                    cur += l[1:]
                elif math.dist(cur[-1], l[-1]) < tol:
                    cur += l[::-1][1:]
                elif math.dist(cur[0], l[-1]) < tol:
                    cur = l[:-1] + cur
                elif math.dist(cur[0], l[0]) < tol:
                    cur = l[::-1][:-1] + cur
                else:
                    continue
                lines.pop(i)
                grown = True
                break
        out.append(cur)
    return out


def extract_pcb(source: Path) -> dict:
    """A KiCad board's drawing data (standard library only): the Edge.Cuts outline, every footprint's position, F.Fab
    body lines and pads ([x, y, w, h, shape, angle, net, drill, unplated]), every track segment by net, and the vias,
    in board millimetres (x right, y down).
    Front-side only: a banner shows the top of the board."""
    root = _sexp(source.read_text(encoding="utf-8"))
    r2 = lambda v: round(v, 2)
    nets = []

    numbered = {c[1]: c[2] for c in _kids(root, "net") if len(c) > 2}   # KiCad 6-9 declare (net 3 "name") once

    def net_of(node):
        c = _kids(node, "net")
        if not c:
            return None
        # KiCad 10: (net "name"); KiCad 6-9: (net 3 "name") on pads and (net 3) on tracks and vias
        name = c[0][2] if len(c[0]) > 2 else numbered.get(c[0][1], c[0][1])
        if name not in nets:
            nets.append(name)
        return nets.index(name)

    edge = []
    for g in root:
        if isinstance(g, list) and g[0].startswith("gr_") and _kids(g, "layer") and _kids(g, "layer")[0][1] == "Edge.Cuts":
            edge += _shape_lines(g)
    outline = [[[r2(x), r2(y)] for x, y in loop] for loop in _chain(edge)]
    footprints = []
    for fp in _kids(root, "footprint"):
        at = _kids(fp, "at")[0]
        fx, fy, rot = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        place = lambda p: (fx + p[0] * c + p[1] * s, fy - p[0] * s + p[1] * c)
        ref = next((p[2] for p in _kids(fp, "property") if p[1] == "Reference"),       # KiCad 8 and later
                   next((p[2] for p in _kids(fp, "fp_text") if p[1] == "reference"), ""))
        body = []
        for g in fp:
            if isinstance(g, list) and g[0] in ("fp_line", "fp_rect", "fp_arc", "fp_circle", "fp_poly") \
                    and _kids(g, "layer") and _kids(g, "layer")[0][1] == "F.Fab":
                body += [[place(p) for p in ln] for ln in _shape_lines(g)]
        pads = []
        for p in _kids(fp, "pad"):
            pat = _kids(p, "at")[0]
            px, py = place((float(pat[1]), float(pat[2])))
            ang = float(pat[3]) if len(pat) > 3 else 0.0   # the pad's absolute angle; KiCad omits it when 0
            sz = _kids(p, "size")[0]
            dr = _kids(p, "drill")
            drill = float(dr[0][2] if dr[0][1] == "oval" else dr[0][1]) if dr and len(dr[0]) > 1 else 0
            pads.append([r2(px), r2(py), r2(float(sz[1])), r2(float(sz[2])), p[3], r2(ang % 360), net_of(p), r2(drill),
                         int(p[2] == "np_thru_hole")])
        footprints.append({"ref": ref, "at": [r2(fx), r2(fy), r2(rot)],
                           "body": [[[r2(x), r2(y)] for x, y in ln] for ln in _chain(body)], "pads": pads})
    tracks = {}
    for seg in _kids(root, "segment") + _kids(root, "arc"):
        i = net_of(seg)
        lay = 0 if _kids(seg, "layer")[0][1] == "F.Cu" else 1
        wd = float(_kids(seg, "width")[0][1])
        pts = [_xy(seg, "start"), _xy(seg, "end")] if seg[0] == "segment" else \
            _arc_pts(_xy(seg, "start"), _xy(seg, "mid"), _xy(seg, "end"), 6)
        for a, b in zip(pts, pts[1:]):
            tracks.setdefault(nets[i] if i is not None else "", []).append(
                [r2(a[0]), r2(a[1]), r2(b[0]), r2(b[1]), lay, r2(wd)])
    vias = [[r2(_xy(v, "at")[0]), r2(_xy(v, "at")[1]), r2(float(_kids(v, "size")[0][1]))] for v in _kids(root, "via")]
    import subprocess
    rel = subprocess.run(["git", "-C", str(source.parent), "ls-files", "--full-name", source.name],
                         capture_output=True, text=True).stdout.strip() or source.name
    return {"kind": "pcb", "source": dict(_source(source), file=rel, sha256=_sha256(source)), "nets": nets,
            "outline": outline, "footprints": footprints, "tracks": tracks, "vias": vias}


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------ CLI

def banners(path: Path = None) -> list:
    return json.loads((path or HERE / "banners.json").read_text(encoding="utf-8"))["banners"]


def outputs(spec: dict, roots: dict, home: Path = ROOT):
    """(theme, path) pairs for a banner: ``out`` is ``owner/repo:path`` (or a list of them; a bare path is this
    repo), and each theme is written to ``<path>-<theme>.svg`` (``<path>.svg`` for ``auto``). Repos that are not
    checked out here (``--repo``) are skipped."""
    out = []
    for target in spec["out"] if isinstance(spec["out"], list) else [spec["out"]]:
        repo, rel = target.split(":", 1) if ":" in target else (THIS_REPO, target)
        root = home if repo == THIS_REPO else roots.get(repo)
        if root is None:
            continue
        for t in spec.get("themes", THEMES[spec.get("kind", "hero")]):
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
    ap.add_argument("--spec", type=Path, help="render the banners in this file instead of banners.json; "
                    "bare out paths are then relative to the current directory (a profile repo's own workflow)")
    ap.add_argument("--extract", choices=["catalog", "lines", "pcb"])
    ap.add_argument("--source", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sample", choices=["hero", "card"], help="print a sample banner to stdout")
    ap.add_argument("--theme", default="dark", choices=["light", "dark"])
    a = ap.parse_args(argv)
    if a.sample:
        sys.stdout.write(render(dict(SAMPLE, kind=a.sample), a.theme))
        return 0
    if a.extract:
        data = {"catalog": extract_catalog, "lines": extract_lines, "pcb": extract_pcb}[a.extract](a.source)
        a.out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"wrote {a.out}")
        return 0
    roots = dict(r.split("=", 1) for r in a.repo)
    bad = 0
    for spec in banners(a.spec):
        if a.names and spec["name"] not in a.names:
            continue
        for theme, path in outputs(spec, roots, Path.cwd() if a.spec else ROOT):
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
