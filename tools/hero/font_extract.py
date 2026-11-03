#!/usr/bin/env python3
"""Vendor the glyph outlines the banners draw text with, so rendering needs no font and looks the same everywhere.

    pip install fonttools
    python3 tools/hero/font_extract.py SpaceGrotesk[wght].ttf      # writes tools/hero/glyphs.json

The font is Space Grotesk (SIL Open Font License 1.1, no Reserved Font Name; licence in OFL-SpaceGrotesk.txt),
from https://github.com/google/fonts/tree/main/ofl/spacegrotesk. Two weights are instanced from the variable font:
``bold`` (700) for repo names and ``medium`` (500) for taglines and labels. Each printable ASCII glyph is stored as
its advance width and an SVG path in font units (y up, 1000 per em), rounded to whole units. Kerning is not applied.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEIGHTS = {"bold": 700, "medium": 500}
CHARS = "".join(chr(c) for c in range(32, 127)) + "·—–’³×°→"


def _path(glyphset, name) -> str:
    from fontTools.pens.svgPathPen import SVGPathPen

    pen = SVGPathPen(glyphset, ntos=lambda v: str(int(round(v))))
    glyphset[name].draw(pen)
    return pen.getCommands()


def extract(font_path: Path) -> dict:
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    raw = Path(font_path).read_bytes()
    out = {"font": "Space Grotesk", "licence": "OFL-1.1", "source": "github.com/google/fonts/ofl/spacegrotesk",
           "sha256": hashlib.sha256(raw).hexdigest(), "weights": {}}
    for label, wght in WEIGHTS.items():
        font = instancer.instantiateVariableFont(TTFont(font_path), {"wght": wght})
        cmap, gs, hmtx = font.getBestCmap(), font.getGlyphSet(), font["hmtx"]
        out["upm"] = font["head"].unitsPerEm
        out["cap"] = getattr(font["OS/2"], "sCapHeight", 700)
        out["xheight"] = getattr(font["OS/2"], "sxHeight", 500)
        glyphs = {}
        for ch in CHARS:
            name = cmap.get(ord(ch))
            if name is None:
                continue
            glyphs[ch] = [hmtx[name][0], _path(gs, name)]
        out["weights"][label] = glyphs
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    data = extract(Path(argv[0]))
    (HERE / "glyphs.json").write_text(json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote glyphs.json ({sum(len(g) for g in data['weights'].values())} glyphs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
