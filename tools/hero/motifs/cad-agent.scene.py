"""The cad-agent banner scene for extract_mesh.py: the starter project that `cad-agent init` creates
(examples/starter-box: a 60 x 40 x 25 mm box and its lid on four M3 heat-set inserts), built by its own
cad/build.py with cad-agent's insert hole and boss design. The lid is drawn lifted, then drops on; MARKS are the four
insert joints, where the banner ticks off the starter's checks."""
from __future__ import annotations

import functools
import sys
from pathlib import Path


@functools.cache
def _build(source: str):
    sys.path[:0] = [str(Path(source) / "src"), str(Path(source) / "examples" / "starter-box" / "cad")]
    import build
    return build


def marks(source: Path):
    b = _build(str(source))
    return [(x, y, b.box_height) for x, y in b.corners]


def parts(source: Path, pose=None):
    b = _build(str(source))
    yield "box", "box", "plate", b.make_box()
    yield "lid", "lid", "accent", b.make_lid()
