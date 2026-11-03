"""The Gyropup banner scene for extract_mesh.py: what is designed now, set exactly as the project's own README image
(tools/readme_hero.py, docs/hero.jpg) sets it: leg v2 standing at a 300 mm stance (cad/build_leg.py, the five-bar
of cad/fivebar.py on two RS-04 envelopes) beside the foam-ball turret (cad/turret.py) on its bench stand
(cad/turret_stand.py). Every shape comes from the project's CadQuery code; this file only groups and colours them.

Groups: ``leg``; ``stand``; ``turret`` (the parts fixed to the stand); ``turret_head`` (everything the pan joint
carries, plus the pan pinion that turns with it), which is drawn again at each pose. A pose is ``{"pan": deg,
"tilt": deg}`` about the turret's own pan and tilt axes (``Turret.posed``); tilt is 0 at level and negative down.
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path

REST = {"pan": -30.0, "tilt": -8.0}          # the pose docs/hero.jpg shows


@functools.cache
def _build(source: str):
    sys.path.insert(0, str(Path(source) / "cad"))
    import cadquery as cq
    import build_leg
    import turret as tu
    import turret_stand as ts

    leg = [(n, s) for n, (s, _) in build_leg.assembled(300.0).items() if s is not None]
    T = tu.Turret({"bodyTop": -(20.0 + tu.SADDLE_T)})
    shift = cq.Vector(-150.0, -400.0, -385.0 + ts.H + ts.BOT)     # the turret's stand on the leg's floor
    stand = [(n, s.val().translate(shift) if hasattr(s, "val") else s.translate(shift)) for n, s in ts.parts().items()]
    return leg, T, shift, stand


def role(name: str) -> str:
    """The colour role of a part, following tools/readme_hero.py's colours."""
    if any(k in name for k in ("upper_link", "front_link", "wheel_link")) or name == "barrel":
        return "accent"
    if name.startswith("hopper") and "flap" not in name:
        return "glass"
    if (name.startswith(("screws", "knee_nut", "stand_", "motor_", "wheel_tyre")) or "tyre" in name
            or name in ("wheel_cable", "flywheel", "lidar") or "motor_l" in name or "motor_r" in name
            or name.endswith("_servo")):
        return "dark"
    return "plate"


def parts(source: Path, pose=None):
    leg, T, shift, stand = _build(str(source))
    for name, shape in leg:
        yield name, "leg", role(name), shape
    for name, shape in stand:
        yield name, "stand", role(name), shape
    p = REST if pose is None else pose
    for name, shape in T.posed(p["pan"], p["tilt"]).items():
        group = "turret" if T.frame[name] == "base" else "turret_head"
        yield name, group, role(name), shape.val().translate(shift)
