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
        for kind in ("hero", "card"):
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

    def test_check_fails_when_a_committed_banner_differs(self):
        spec = next(b for b in heroes.banners() if heroes.outputs(b, {}))
        theme, path = heroes.outputs(spec, {})[0]
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("</svg>", "<!-- --></svg>"), encoding="utf-8")
            self.assertEqual(heroes.main(["--check", spec["name"]]), 1)
        finally:
            path.write_text(original, encoding="utf-8")
        self.assertEqual(heroes.main(["--check", spec["name"]]), 0)


if __name__ == "__main__":
    unittest.main()
