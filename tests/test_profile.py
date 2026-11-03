"""tools/profile/update.py against canned API answers: no network."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "profile"))
import update  # noqa: E402


def repo(full, pushed, **kw):
    owner, name = full.split("/")
    return dict(full_name=full, name=name, html_url=f"https://github.com/{full}", pushed_at=pushed,
                private=False, archived=False, fork=False, **kw)


def commit(date, msg, parents=1):
    return dict(commit=dict(message=msg, author=dict(date=date)), parents=[{}] * parents)


API = {
    "/users/mvalancy/repos?per_page=100&type=public&sort=pushed": [
        repo("mvalancy/val-ark", "2026-11-02T08:00:00Z"),
        repo("mvalancy/j501-agx-orin", "2026-10-31T08:00:00Z"),
        repo("mvalancy/mvalancy", "2026-11-03T08:00:00Z"),
        {**repo("mvalancy/old-thing", "2026-11-01T00:00:00Z"), "archived": True},
        {**repo("mvalancy/a-fork", "2026-11-01T00:00:00Z"), "fork": True},
        repo("mvalancy/lesson-plans", "2026-10-28T00:00:00Z"),
    ],
    "/orgs/Valpatel/repos?per_page=100&type=public&sort=pushed": [
        repo("Valpatel/cad-agent", "2026-11-03T04:00:00Z"),
        repo("Valpatel/gyropup", "2026-11-03T04:00:00Z"),
        {**repo("Valpatel/secret", "2026-11-03T00:00:00Z"), "private": True},
    ],
    "/repos/Valpatel/cad-agent/commits?per_page=20": [
        commit("2026-11-03T01:00:00Z", "Merge pull request #9 from x/y", 2),
        commit("2026-11-03T00:30:00Z", "Add `fit` check <script>alert(1)</script> see https://evil.example @someone\nbody"),
    ],
    "/repos/Valpatel/cad-agent/releases?per_page=30": [
        dict(tag_name="v0.18.0-rc", html_url="u", published_at="2026-11-03T00:00:00Z", prerelease=True),
        dict(tag_name="v0.17.0", html_url="https://github.com/Valpatel/cad-agent/releases/tag/v0.17.0",
             published_at="2026-11-02T15:00:00Z"),
    ],
    "/repos/Valpatel/gyropup/commits?per_page=20": [commit("2026-11-02T20:00:00Z", "Leg v2: " + "long words " * 20)],
    "/repos/mvalancy/val-ark/commits?per_page=20": [commit("2026-11-02T07:00:00Z", "Release 0.1.18")],
    "/repos/mvalancy/val-ark/releases?per_page=30": [
        dict(tag_name="0.1.18", html_url="https://github.com/mvalancy/val-ark/releases/tag/0.1.18",
             published_at="2026-11-02T07:20:00Z")],
    "/repos/mvalancy/j501-agx-orin/commits?per_page=20": [commit("2026-10-31T06:00:00Z", "validate_review: fix")],
    "/repos/mvalancy/lesson-plans/commits?per_page=20": [commit("2026-10-28T16:00:00Z", "Publish lessons")],
    "/repos/mvalancy/lesson-plans/releases?per_page=30": [
        dict(tag_name="v1", html_url="old", published_at="2026-06-01T00:00:00Z")],
}
README = "top\n<!-- spotlight:start -->\nold\n<!-- spotlight:end -->\nmid\n<!-- activity:start -->\n<!-- activity:end -->\nend\n"


class ProfileUpdate(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def get(path):
            self.calls.append(path)
            return API.get(path)

        self.data = update.gather(get, now="2026-11-03T00:00:00Z")
        self.out = update.update(README, self.data)

    def test_reads_only_public_live_repos(self):
        names = [r["full"] for r in self.data["repos"]]
        for gone in ("mvalancy/mvalancy", "mvalancy/old-thing", "mvalancy/a-fork", "Valpatel/secret"):
            self.assertNotIn(gone, names)
        self.assertFalse(any("secret" in c or "a-fork" in c for c in self.calls))

    def test_spotlight_orders_by_newest_commit_and_links_live_sites(self):
        spot = self.out.split("<!-- spotlight:start -->")[1].split("<!-- spotlight:end -->")[0]
        order = [spot.index(f"assets/spot/{n}.svg") for n in ("cad-agent", "gyropup", "val-ark", "j501-agx-orin")]
        self.assertEqual(order, sorted(order))
        self.assertIn('href="https://cad-agent.valpatel.com"', spot)
        self.assertIn('href="https://gyropup.com"', spot)
        self.assertIn("v/release/Valpatel/cad-agent", spot)  # has a release
        self.assertIn("last-commit/Valpatel/gyropup", spot)  # has none
        self.assertIn("validate_review: fix", spot)
        self.assertNotIn("old", spot)

    def test_commit_text_is_one_safe_line(self):
        spot = self.out.split("<!-- spotlight:end -->")[0]
        self.assertNotIn("<script", spot)
        self.assertNotIn("evil.example", spot)
        self.assertNotIn("@someone", spot)
        self.assertNotIn("Merge pull request", spot)
        self.assertNotIn("body", spot)
        self.assertIn("Add fit check", spot)
        self.assertTrue(all(len(line) < 400 for line in spot.splitlines()))
        self.assertIn("…", spot)  # the long gyropup line is cut

    def test_activity_lists_recent_stable_releases(self):
        act = self.out.split("<!-- activity:start -->")[1]
        self.assertIn("cad-agent v0.17.0", act)
        self.assertNotIn("rc<", act)
        self.assertNotIn("lesson-plans v1", act)  # months older than the newest release
        self.assertTrue(self.out.startswith("top\n") and self.out.endswith("end\n"))

    def test_rerun_is_byte_identical(self):
        self.assertEqual(update.update(self.out, self.data), self.out)


    def test_stats_are_real_counts(self):
        out = update.update("<!-- stats:start -->\n<!-- stats:end -->\n", self.data)
        self.assertIn("open%20repos-5-", out)                     # cad-agent, gyropup, val-ark, j501, lesson-plans
        self.assertIn("releases%20%C2%B7%2030%20days-2-", out)    # v0.17.0, 0.1.18; rc is a prerelease, lesson-plans v1 is from June
        self.assertIn("last%20release-cad--agent%20v0.17.0%20%C2%B7%20Nov%202-", out)
        self.assertIn("last%20commit-Nov%202%2016%3A30%20PT-", out)

    def test_ticker_and_hero_events(self):
        out = update.update("<!-- ticker:start -->\n<!-- ticker:end -->\n", self.data)
        self.assertIn('Now building</b> · <a href="https://github.com/Valpatel/cad-agent">cad-agent</a>: Add fit check', out)
        log = update.events(self.data)
        self.assertEqual(len(log), 3)
        self.assertTrue(log[-1].startswith("11-02 [gyropup] Leg v2"))         # newest last, in Pacific time
        self.assertEqual(len({line.split("]")[0] for line in log}), 3)          # one line per repository
        self.assertIn("11-02 [cad-agent] released v0.17.0", log)
        self.assertTrue(all("<" not in line and "http" not in line and len(line) < 70 for line in log))

    def test_a_missing_block_is_left_alone(self):
        self.assertEqual(update.update("no markers\n", self.data), "no markers\n")

    def test_configure_points_at_another_profile(self):
        saved = (update.ACCOUNTS, update.SKIP, update.SPOT, update.HERO, update.BADGE)
        try:
            update.configure({"accounts": [["orgs", "Valpatel"]], "skip": ["Valpatel/.github"], "spot": {}})
            names = [r["full"] for r in update.gather(lambda p: API.get(p))["repos"]]
            self.assertEqual(sorted(names), ["Valpatel/cad-agent", "Valpatel/gyropup"])
        finally:
            update.ACCOUNTS, update.SKIP, update.SPOT, update.HERO, update.BADGE = saved


if __name__ == "__main__":
    unittest.main()
