"""The README banner generator (tools/hero/heroes.py): a sample hero and card render to valid, small, script-free
SVGs with no external reference and a reduced-motion rule; each embed rule is shown to fail on an SVG that breaks it;
rendering is deterministic; and every banner committed in this repository is exactly what its spec renders to.

    python3 -m unittest discover -s tests -v          # standard library only
"""
from __future__ import annotations

import importlib.util
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("heroes", ROOT / "tools" / "hero" / "heroes.py")
heroes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(heroes)
SVG = "{http://www.w3.org/2000/svg}"


def sample(kind, theme="dark", **more):
    return heroes.render(dict(heroes.SAMPLE, kind=kind, **more), theme)


class Sample(unittest.TestCase):
    def test_hero_and_card_pass_the_embed_rules(self):
        for kind in ("hero", "spot", "card"):
            for theme in ("light", "dark", "auto"):
                with self.subTest(kind=kind, theme=theme):
                    text = sample(kind, theme)
                    self.assertEqual(heroes.problems(text, kind), [])
                    self.assertLessEqual(len(text.encode()), heroes.BUDGET[kind])
                    root = ET.fromstring(text)
                    self.assertEqual(root.tag, SVG + "svg")
                    self.assertEqual(root.get("role"), "img")
                    self.assertTrue(root.get("aria-label"))
                    self.assertIsNotNone(root.find(SVG + "title"))
                    self.assertNotIn("<script", text.lower())
                    self.assertIsNone(re.search(r"""(?:href|src)\s*=\s*["'](?!#)""", text))
                    self.assertIsNone(re.search(r"url\(\s*['\"]?(?!#)", text))
                    self.assertIn(heroes.REDUCED_MOTION, text)

    def test_every_motif_renders_within_budget(self):
        for kind, data in [("network", {}), ("face", {}), ("terminal", {"lines": [10, 30, 20]}), ("circuit", {}),
                           ("chart", {"style": "solar"}), ("chart", {"style": "bars"}), ("dial", {}), ("slides", {}),
                           ("wave", {}), ("crystal", {}), ("radar", {}), ("fight", {}),
                           ("eye", {"pan": 1, "zoom": [100, 500]}),
                           ("linkage", {"crank_mm": 150, "link_mm": 250, "path_centre_mm": [0, -255],
                                        "path_radii_mm": [80, 45]})]:
            for size in ("hero", "card"):
                with self.subTest(motif=kind, size=size):
                    text = sample(size, motif=dict(data, kind=kind))
                    self.assertEqual(heroes.problems(text, size), [])

    def test_the_board_topology_and_fractal_motifs_loop_in_step(self):
        """GraphDone's board and topology and CodeGraph's fractal: within budget at every size and theme, and every
        ambient animation's period divides the loop's cycle, so a frame and the frame a cycle later are the same."""
        board = {"kind": "board", "items": [["TASK", "Set up a database", "Alice"], ["TASK", "Write a schema", "agent"],
                                            ["MILESTONE", "Ship it", "Bob"]], "deps": [[0, 1], [1, 2]], "outcome": "Done"}
        topology = dict(board, kind="topology", labels=["Database", "Schema", "Ship"], angles=[215, 325, 90])
        for motif in (board, topology, {"kind": "fractal"}):
            for kind, theme in (("hero", "dark"), ("hero", "light"), ("spot", "dark"), ("card", "dark")):
                with self.subTest(motif=motif["kind"], kind=kind, theme=theme):
                    text = sample(kind, theme, motif=motif)
                    self.assertEqual(heroes.problems(text, kind), [])
                    T = float(re.search(r'animation:L\d+ ([\d.]+)s', text).group(1))
                    for name, dur in re.findall(r'animation:(gd\w+|gt\w+|cg\w+) ([\d.]+)s[^;}"]*infinite', text):
                        k = T / float(dur)
                        self.assertAlmostEqual(k, round(k), places=2, msg=(name, dur, T))
        card = sample("card", motif={"kind": "fractal"})
        self.assertEqual(card.count("<use href=\"#cge"), 4)          # the edges written once: graph, glow, data, depth

    def test_the_stack_motif_fits_a_hero(self):
        text = sample("hero", motif={"kind": "stack"})
        self.assertEqual(heroes.problems(text, "hero"), [])
        self.assertIn('class="pulse', text)

    def test_the_ops_board_with_a_kicker_and_hud(self):
        motif = {"kind": "ops", "nodes": [["ZONE %d" % i, "STATUS", "a3" if i % 2 else "a4"] for i in range(8)],
                 "log": ["11-02 [cad-agent] released v0.18.0", "11-03 [gyropup] leg v2", "x" * 60]}
        for theme in ("light", "dark", "auto"):
            text = heroes.render(dict(heroes.SAMPLE, kind="hero", palette="valpatel", hud=True, kicker="Autonomous systems",
                                      motif=motif), theme)
            self.assertEqual(heroes.problems(text, "hero"), [])
            self.assertEqual(text.count('class="lg"'), 3)              # every log line, shown in the still frame
            self.assertIn('class="led"', text)                          # the LIVE and kicker lights
        self.assertIn('[fill="#a35a00"]{fill:#ffb000}', text)           # the amber accent follows the dark scheme
        self.assertNotIn("--a3:", sample("card", "auto"))               # no unused accent variables

    def test_a_spec_file_writes_beside_the_caller(self):
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "hero.json"
            spec.write_text(json.dumps({"banners": [dict(heroes.SAMPLE, kind="hero", out="out/b")]}))
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertEqual(heroes.main(["--spec", str(spec)]), 0)
            finally:
                os.chdir(cwd)
            self.assertTrue((Path(tmp) / "out/b-dark.svg").exists() and (Path(tmp) / "out/b-light.svg").exists())

    def test_a_posed_group_scans_and_rests_still_under_reduced_motion(self):
        square = lambda x0: {"plate": [[[x0, 0], [x0 + 10, 0], [x0 + 10, 10], [x0, 10]]]}
        parts = [{"name": "base", "group": "base", "from": [0, 0], "regions": dict(square(0), glass=square(5)["plate"]),
                  "lines": [[[0, 0], [10, 10]]]}]
        parts += [{"name": "head", "group": "head", "from": [0, -20], "regions": square(10 + k), "lines": [], "pose": k}
                  for k in range(3)]
        motif = {"kind": "cad", "parts": parts, "rest_pose": 1, "scan": [[1, 1.0], [0, 0.5], [2, 0.5]]}
        text = sample("hero", motif=motif)
        self.assertEqual(heroes.problems(text, "hero"), [])
        self.assertRegex(text, r'<g class="ps1" style="animation:L\d+ ')     # the rest pose is the still frame
        self.assertRegex(text, r'<g class="ps0" opacity="0" style="animation:L\d+ ')
        self.assertRegex(text, r'<g class="ps2" opacity="0" style="animation:L\d+ ')
        self.assertEqual(heroes.timed(text), [])                      # the scan plays once a cycle, in step
        self.assertIn('class="sil glass"', text)                     # not the title's guide-line class ("gl")
        card = sample("card", motif=motif)                            # cards keep only the rest pose
        self.assertNotIn("ps0", card)
        self.assertEqual(heroes.problems(card, "card"), [])

    def test_a_card_reads_in_its_first_frame(self):
        """Cards often start scrolled off screen, so the name and tagline are drawn still, not sketched in."""
        card = sample("card", tagline="Short line.", cta="Play", cta_icon="play")
        self.assertEqual(heroes.problems(card, "card"), [])
        self.assertIn('<g class="cta">', card)
        self.assertIn('l13 7-13 7z', card)                          # the play triangle
        self.assertIn('<g class="cta">', sample("card", cta="Visit"))
        self.assertNotIn('l13 7-13 7z', sample("card", cta="Visit"))

    def test_checks_and_marks_draw_under_a_cad_motif(self):
        square = [[[0, 0], [10, 0], [10, 10], [0, 10]]]
        motif = {"kind": "cad", "parts": [{"name": "box", "group": "box", "from": [0, 0], "regions": {"accent": square},
                                           "lines": [[[0, 0], [10, 10]]]}],
                 "marks": [[2, 2], [8, 8]], "checks": ["inserts", "fit"]}
        for size in ("spot", "card"):
            text = sample(size, motif=motif)
            self.assertEqual(heroes.problems(text, size), [])
            self.assertEqual(text.count('stroke-linecap="round" stroke-linejoin="round"/></g>'), 2)  # one per mark

    BOARD = """(kicad_pcb (version 20250000)
  (net "/CAN_H") (net "/CAN_L")
  (gr_line (start 0 0) (end 40 0) (layer "Edge.Cuts"))
  (gr_line (start 40 0) (end 40 30) (layer "Edge.Cuts"))
  (gr_arc (start 40 30) (mid 39.12 32.12) (end 37 33) (layer "Edge.Cuts"))
  (gr_line (start 37 33) (end 0 33) (layer "Edge.Cuts"))
  (gr_line (start 0 33) (end 0 0) (layer "Edge.Cuts"))
  (footprint "Lib:Header" (layer "F.Cu") (at 10 25)
    (property "Reference" "J1" (at 0 -2 0) (layer "F.SilkS"))
    (fp_rect (start -3 -2) (end 3 2) (layer "F.Fab"))
    (pad "1" smd rect (at -1 0) (size 1 2) (layers "F.Cu") (net "/CAN_H"))
    (pad "2" smd rect (at 1 0) (size 1 2) (layers "F.Cu") (net "/CAN_L")))
  (footprint "Lib:DE9" (layer "F.Cu") (at 30 5 90)
    (property "Reference" "J2" (at 0 -2 90) (layer "F.SilkS"))
    (fp_line (start -4 -3) (end 4 -3) (layer "F.Fab"))
    (fp_line (start 4 -3) (end 4 3) (layer "F.Fab"))
    (pad "7" thru_hole circle (at 1 0 90) (size 1.6 1.6) (drill 1) (layers "*.Cu") (net "/CAN_H"))
    (pad "2" thru_hole circle (at -1 0 90) (size 1.6 1.6) (drill 1) (layers "*.Cu") (net "/CAN_L"))
    (pad "" np_thru_hole circle (at 0 3 90) (size 3.2 3.2) (drill 3.2) (layers "*.Cu")))
  (segment (start 9 25) (end 9 15) (width .25) (layer "F.Cu") (net "/CAN_H"))
  (segment (start 9 15) (end 30 15) (width .25) (layer "F.Cu") (net "/CAN_H"))
  (segment (start 30 15) (end 30 4) (width .25) (layer "B.Cu") (net "/CAN_H"))
  (segment (start 9 15) (end 5 15) (width .25) (layer "F.Cu") (net "/CAN_H"))
  (segment (start 11 25) (end 30 6) (width .25) (layer "F.Cu") (net "/CAN_L"))
  (via (at 30 15) (size .6) (drill .3) (layers "F.Cu" "B.Cu") (net "/CAN_H")))
"""

    def test_a_kicad_board_extracts_and_draws_as_a_pcb_motif(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "b.kicad_pcb"
            src.write_text(self.BOARD, encoding="utf-8")
            data = heroes.extract_pcb(src)
        self.assertEqual(len(data["outline"]), 1)                    # four lines and an arc chain into one loop
        loop = data["outline"][0]
        self.assertEqual(loop[0], loop[-1])
        self.assertTrue(any(abs(x - 39.12) < .2 and abs(y - 32.12) < .2 for x, y in loop))   # the arc is sampled
        fps = {f["ref"]: f for f in data["footprints"]}
        # J2 is turned 90 degrees: its local (1, 0) pad lands at board (30, 4), its (-1, 0) pad at (30, 6)
        self.assertEqual([fps["J2"]["pads"][0][:2], fps["J2"]["pads"][1][:2]], [[30, 4], [30, 6]])
        self.assertEqual(data["nets"][fps["J2"]["pads"][0][6]], "/CAN_H")
        self.assertIsNone(fps["J2"]["pads"][2][6])                   # the unplated hole has no net
        self.assertEqual([p[8] for p in fps["J2"]["pads"]], [0, 0, 1])
        self.assertEqual(len(data["tracks"]["/CAN_H"]), 4)
        self.assertEqual(len(data["vias"]), 1)
        # the shortest copper path skips the stub at (5, 15)
        route = heroes._pcb_route([tuple(s) for s in data["tracks"]["/CAN_H"]], (9, 25), (30, 4))
        self.assertEqual(route, [(9, 25), (9, 15), (30, 15), (30, 4)])
        motif = dict(data, parts=["J1", "J2"], pairs=[{"nets": ["/CAN_H", "/CAN_L"], "from": "J1", "to": "J2"}],
                     labels={"J2": ["CAN0", "top"], "J1": ["J1", "left"]})
        hero = sample("hero", motif=motif)
        self.assertEqual(heroes.problems(hero, "hero"), [])
        self.assertEqual(hero.count('class="pls"'), 2)               # a pulse on each line of the pair
        self.assertIn(".pcb .pls{fill:none;stroke:var(--edge)".replace("var(--edge)", heroes.palette("violet", "dark")["edge"]), hero)
        self.assertIn("opacity:0;animation:pls", hero)               # pulses are hidden in the still frame
        self.assertIn(".pcb .can{fill:none;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;"
                      "stroke-dashoffset:0}", hero)                   # the pairs are fully drawn in the still frame
        self.assertIn('class="ld"', hero)                            # the left label has a leader line
        card = sample("card", motif=motif)
        self.assertEqual(heroes.problems(card, "card"), [])
        self.assertNotIn('class="pls"', card)                        # no pulses on a card: only the drawing loops
        self.assertNotIn('class="ld"', card)

    def test_older_kicad_net_numbers_references_and_unangled_pads(self):
        """KiCad 6-9 declare (net 1 "name") once and tracks carry only (net 1); before KiCad 8 the reference is an
        fp_text. A pad with no angle is at 0 degrees whatever the footprint's rotation (KiCad stores pad angles whole)."""
        import tempfile
        board = """(kicad_pcb (version 20221018) (net 0 "") (net 1 "/CAN_H")
  (footprint "Lib:H" (layer "F.Cu") (at 10 10 90)
    (fp_text reference "J1" (at 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at 0 0) (size 1 2) (layers "F.Cu") (net 1 "/CAN_H")))
  (segment (start 10 10) (end 20 10) (width .25) (layer "F.Cu") (net 1))
  (via (at 20 10) (size .6) (drill .3) (layers "F.Cu" "B.Cu") (net 1)))
"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "old.kicad_pcb"
            src.write_text(board, encoding="utf-8")
            data = heroes.extract_pcb(src)
        self.assertEqual(list(data["tracks"]), ["/CAN_H"])
        fp = data["footprints"][0]
        self.assertEqual(fp["ref"], "J1")
        self.assertEqual(data["nets"][fp["pads"][0][6]], "/CAN_H")
        self.assertEqual(fp["pads"][0][5], 0)
        self.assertEqual(fp["pads"][0][8], 0)                        # plated

    def test_rendering_is_deterministic(self):
        self.assertEqual(sample("hero"), sample("hero"))
        self.assertEqual(sample("card", "light"), sample("card", "light"))

    def test_auto_theme_carries_both_schemes(self):
        text = sample("hero", "auto")
        self.assertIn("@media (prefers-color-scheme:dark)", text)
        self.assertNotIn("prefers-color-scheme", sample("hero", "light"))

    def test_the_name_is_drawn_from_glyph_outlines_not_a_font(self):
        text = sample("hero")
        self.assertNotIn("<text", text)
        self.assertNotIn("font-family", text)
        self.assertIn('<use href="#b115"', text)          # the bold "s" of "sample-repo"


class Rules(unittest.TestCase):
    """Each rule catches an SVG that breaks it, so a rule that stops checking is caught too."""

    @staticmethod
    def specs():
        """Every motif at every size, and every committed banner spec."""
        specs = [dict(heroes.SAMPLE, kind=k, motif=m) for k in ("hero", "spot", "card") for m in (
            {"kind": "network"}, {"kind": "chart", "style": "bars"}, {"kind": "chart", "style": "solar"},
            {"kind": "slides"}, {"kind": "terminal", "lines": [10, 30, 20]}, {"kind": "dial"}, {"kind": "circuit"},
            {"kind": "stack"}, {"kind": "eye", "pan": 1, "zoom": [100, 500]})]
        return specs + [b for b in heroes.banners()
                        if not (isinstance(b["out"], str) and b["out"].startswith("Valpatel/.github"))]

    def test_every_timed_animation_repeats_and_reduced_motion_shows_the_finished_frame(self):
        """Every banner loops: no animation plays once and stops, the intros share one cycle (so they restart in
        step), and the reduced-motion rule that stops them all is there. Checked on every motif, every size and every
        committed banner spec."""
        for spec in self.specs():
            for theme in spec.get("themes", ["dark"]):
                with self.subTest(banner=spec["name"], kind=spec.get("kind"), motif=(spec.get("motif") or {}).get("kind")):
                    text = heroes.render(spec, theme)
                    self.assertEqual(heroes.timed(text), [])
                    self.assertIn(heroes.REDUCED_MOTION, text)
                    cycles = {float(t) for t in re.findall(r'animation:L\d+ ([\d.]+)s', text)}
                    self.assertEqual(len(cycles), 1, cycles)                  # one cycle for every intro
                    T = cycles.pop()
                    self.assertGreaterEqual(T, heroes.HOLD + heroes.RESET)
                    for lag in re.findall(r'animation:L\d+ [\d.]+s ([\d.]+)s backwards', text):
                        self.assertLessEqual(float(lag), heroes.SPREAD)     # a stagger, never a second start
                    self.assertEqual(heroes.drifting(text), [])               # no endless pulse outlives its part

    def test_a_delayed_endless_animation_restarts_with_the_cycle(self):
        """A pulse that starts once its part is drawn is gated: hidden until its delay, faded out with the rest, so it
        never runs on a banner that is fading or being rebuilt. One already inside a looping part is left alone."""
        css = (".in{animation:fade 1s both}@keyframes fade{from{opacity:0}}"
               ".p{animation:pulse 2s 3s linear infinite}@keyframes pulse{to{opacity:.2}}"
               ".e{animation:blink 5s 1s infinite}@keyframes blink{50%{opacity:.4}}")
        out_css, markup, T = heroes._loop(css, '<g class="in"><path class="p"/></g><path class="p"/><g/><g class="e"/>')
        self.assertEqual(T, round(3 + heroes.GATE + heroes.HOLD + heroes.RESET, 1))   # the pulse gets the full hold
        self.assertEqual(markup.count("<g style="), 1)                       # only the free pulse is wrapped
        self.assertRegex(markup, r'^<g class="in" style="animation:L\d+ [\d.]+s infinite"><path class="p"/></g>'
                                 r'<g style="animation:L\d+ [\d.]+s infinite"><path class="p"/></g><g/><g class="e"/>$')
        pct = lambda t: heroes.n(100 * t / T, 2) + "%"
        self.assertIn(f"{pct(3)}{{opacity:0;animation-timing-function:ease-out}}", out_css)
        self.assertEqual(heroes.drifting(f"<style>{css}</style><path class=\"p\"/>"), ['<path class="p"/>'])

    def test_a_phase_offset_is_not_gated(self):
        """Only the animations in WAITS start once their part is drawn. Any other delay on an endless animation is a
        phase offset on a part that shows from the first frame (the eye looks around, the face blinks, the nodes
        glow), so the loop never hides it: in every banner each gate wraps an animation from WAITS, and the eyes,
        nodes, bars and blips stay unwrapped."""
        phased = {"look", "fblink", "blink", "zoom", "glow", "play", "hp", "blip", "cta"}
        for spec in self.specs():
            text = heroes.render(spec, "dark")
            with self.subTest(banner=spec["name"], kind=spec.get("kind"), motif=(spec.get("motif") or {}).get("kind")):
                for inner in re.findall(r'<g style="animation:L\d+ [^"]*">(<[^>]*>)', text):
                    cls = re.search(r'class="([^"]*)"', inner)
                    names = set(re.findall(r'animation:(\w+)', inner))
                    if cls:
                        for c in cls.group(1).split():
                            names |= set(re.findall(r'\.' + re.escape(c) + r'\{[^}]*?animation:(\w+)', text))
                    self.assertTrue(names & heroes.WAITS, inner)
                    self.assertFalse(names & phased, inner)

    def test_a_looped_intro_holds_its_finished_frame_then_fades(self):
        """The loop keeps an intro's easing and timing, holds its end state and fades out before the restart."""
        css = ".a{opacity:.5}.in{animation:fade 1s 2s ease-out both}@keyframes fade{from{opacity:0;transform:translateY(6px)}}"
        out_css, markup, T = heroes._loop(css, '<g class="a in"/><g class="a in" style="animation-delay:2.1s"/>')
        self.assertEqual(T, round(3.1 + heroes.HOLD + heroes.RESET, 1))
        self.assertNotIn("@keyframes fade", out_css)                          # nothing plays it once any more
        self.assertNotIn("animation:fade", out_css)
        self.assertIn(f'<g class="a in" style="animation:L0 {heroes.n(T, 2)}s infinite"/>', markup)
        self.assertIn(f'style="animation:L0 {heroes.n(T, 2)}s .1s backwards infinite"', markup)   # shared, staggered
        pct = lambda t: heroes.n(100 * t / T, 2) + "%"
        self.assertIn(f"{pct(2)}{{opacity:0;transform:translateY(6px);animation-timing-function:ease-out}}", out_css)
        self.assertIn(f"{pct(3)},{pct(T - heroes.RESET - 0.1)}{{opacity:.5;transform:none}}", out_css)   # its own .5
        self.assertIn(f"{pct(T - 0.1)},100%{{opacity:0;transform:none}}", out_css)

    def test_the_loop_refuses_what_it_cannot_restart(self):
        with self.assertRaises(ValueError):          # a transform attribute that the keyframes would replace
            heroes._loop(".in{animation:g 1s both}@keyframes g{from{transform:scale(0)}}", '<g class="in" transform="scale(2)"/>')
        with self.assertRaises(ValueError):          # a one-shot and an endless animation on one property
            heroes._loop(".x{animation:g 1s both,h 2s infinite}@keyframes g{from{opacity:0}}@keyframes h{to{opacity:.5}}",
                         '<g class="x"/>')
        with self.assertRaises(ValueError):          # ... the opacity the loop fades counts too
            heroes._loop(".x{animation:g 1s both,h 2s infinite}@keyframes g{from{transform:scale(0)}}"
                         "@keyframes h{to{opacity:.5}}", '<g class="x"/>')

    def setUp(self):
        self.good = sample("card")

    def broken(self, old, new):
        self.assertIn(old, self.good)
        return self.good.replace(old, new, 1)

    def test_script(self):
        self.assertTrue(heroes.problems(self.broken("</svg>", "<script>alert(1)</script></svg>"), "card"))

    def test_event_handler(self):
        self.assertTrue(heroes.problems(self.broken('role="img"', 'role="img" onload="x()"'), "card"))

    def test_external_reference(self):
        self.assertTrue(heroes.problems(self.broken('href="#', 'href="https://example.com/x.svg#'), "card"))
        self.assertTrue(heroes.problems(self.broken("url(#", "url(https://example.com/#"), "card"))

    def test_embedded_image_and_smil(self):
        self.assertTrue(heroes.problems(self.broken("</svg>", '<image width="1" height="1"/></svg>'), "card"))
        self.assertTrue(heroes.problems(self.broken("</svg>", '<animate attributeName="x"/></svg>'), "card"))

    def test_reduced_motion(self):
        self.assertTrue(heroes.problems(self.broken(heroes.REDUCED_MOTION, ""), "card"))

    def test_an_animation_that_plays_once(self):
        self.assertEqual(heroes.timed(self.good), [])
        self.assertEqual(heroes.timed('<g style="animation:none"/>'), [])
        self.assertEqual(heroes.timed(".a{animation:a 2s infinite;animation-iteration-count:3}"), ["iteration count 3"])
        once = re.sub(r"(animation:L\d+ [\d.]+s) infinite", r"\1 1 both", self.good, count=1)
        self.assertEqual(len(heroes.timed(once)), 1)
        self.assertTrue(heroes.problems(once, "card"))

    def test_label_and_title(self):
        self.assertTrue(heroes.problems(self.broken('role="img"', 'role="presentation"'), "card"))
        self.assertTrue(heroes.problems(re.sub(r"<title>.*?</title>", "", self.good), "card"))

    def test_size_budget(self):
        self.assertTrue(heroes.problems(self.broken("</svg>", "<!--" + "x" * heroes.BUDGET["card"] + "--></svg>"), "card"))

    def test_not_well_formed(self):
        self.assertTrue(heroes.problems(self.good[:-10], "card"))


class Committed(unittest.TestCase):
    def test_every_banner_in_this_repo_is_what_its_spec_renders_to(self):
        self.assertEqual(heroes.main(["--check"]), 0)

    def test_check_fails_when_a_banner_differs(self):
        # on a copy written into a temporary checkout, so the committed files are never touched
        import contextlib, io, tempfile
        spec = next(b for b in heroes.banners() if isinstance(b.get("out"), str) and ":" in b["out"])
        repo = spec["out"].split(":", 1)[0]
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            args = [spec["name"], "--repo", f"{repo}={tmp}"]
            self.assertEqual(heroes.main(args), 0)
            self.assertEqual(heroes.main(["--check"] + args), 0)
            for _, path in heroes.outputs(spec, {repo: Path(tmp)}):
                path.write_text(path.read_text(encoding="utf-8").replace("</svg>", "<!-- --></svg>"), encoding="utf-8")
            self.assertEqual(heroes.main(["--check"] + args), 1)


if __name__ == "__main__":
    unittest.main()
