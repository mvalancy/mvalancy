#!/usr/bin/env python3
"""Refresh the live parts of the profile README from the public GitHub API.

    GITHUB_TOKEN=... python3 tools/profile/update.py README.md
    GITHUB_TOKEN=... python3 tools/profile/update.py --config profile/live.json profile/README.md

These blocks are rewritten in place, each between its own marker comments:

* ``spotlight`` ("Recently updated"): the projects in ``SPOT``, always all of them in that fixed order, each as its animated
  card with live shields (latest release, or last commit when there is none, and stars) and a "what's new" line
  taken from its latest non-merge commit on the default branch.
* ``activity``: releases from the last two months.
* ``stats``: a strip of badges with real counts: open repositories, releases in the last 30 days, the last release
  and the last commit (static shields.io badges whose text is written here).
* ``ticker``: "now building", the repositories with the newest commits.

Each block is written only where its markers are. ``--config FILE`` names the accounts, the spotlight projects and an
optional hero spec (``hero``) whose ``ops`` motif gets the newest real events as its log lines; without it the
defaults below (this profile) apply. Another profile repo runs this script from a pinned checkout of this repo.

Only public, non-archived, non-fork repositories of the accounts in ``ACCOUNTS`` are read, and only through the
GitHub REST API (shields.io draws the badges in the reader's browser). Nothing else is called. Text that comes from
commits is cut to one line, stripped of markup and escaped before it is written. The output depends only on the API
answers, so a run with nothing new leaves the file byte-for-byte unchanged and the workflow makes no commit.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from pathlib import Path

API = "https://api.github.com"
ACCOUNTS = [("users", "mvalancy"), ("orgs", "Valpatel")]
SKIP = {"mvalancy/mvalancy", "Valpatel/.github"}  # the profile repos themselves: their pushes are this job's own
SPOT = {
    "Valpatel/cad-agent": dict(art="assets/spot/cad-agent", link="https://cad-agent.valpatel.com",
                               alt="cad-agent: your one stop shop for agentic CAD."),
    "Valpatel/gyropup": dict(art="assets/spot/gyropup", link="https://gyropup.com",
                             alt="Gyropup: a research robot designed to balance on two wheel-legs, with a foam-ball turret."),
    "mvalancy/val-ark": dict(art="assets/spot/val-ark",
                             alt="val-ark: fills a disk with open-source tools, AI models and Wikipedia, then serves it offline."),
    "mvalancy/j501-agx-orin": dict(art="assets/spot/j501-agx-orin",
                                   alt="j501-agx-orin: a 3D-printable enclosure for the Seeed J501 carrier and Jetson AGX Orin."),
}
RELEASES, RECENT = 4, 60
HERO = None          # a banner spec file whose ops motif gets the newest events as log lines
BADGE = ("05070a", "00f0ff")


def configure(cfg: dict) -> None:
    """Point the script at another profile: accounts, skipped repos, spotlight projects, hero spec, badge colours."""
    global ACCOUNTS, SKIP, SPOT, HERO, BADGE
    ACCOUNTS = [tuple(a) for a in cfg.get("accounts", ACCOUNTS)]
    SKIP = set(cfg.get("skip", SKIP))
    SPOT = cfg.get("spot", SPOT)
    HERO = cfg.get("hero", HERO)
    BADGE = tuple(cfg.get("badge", BADGE))


def fetch(path: str):
    """GET one API path and decode the JSON; a 404 (no releases, empty repo) is None."""
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json",
                                                      "X-GitHub-Api-Version": "2022-11-28",
                                                      "User-Agent": "mvalancy-profile-update"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # 409: a repository with no commits
            return None
        raise


def clean(text: str, limit: int = 80, more: str = "…") -> str:
    """One line of plain text: no tags, links or mentions. Escape it (``html.escape``) before writing it into HTML."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    line = re.sub(r"https?://\S+", "", line)
    line = re.sub(r"[`<>\\]", "", line)
    line = re.sub(r"@(?=\w)", "", line)
    line = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", line)   # controls, bidi, zero-width
    line = re.sub(r"\s+", " ", line).strip(" -:·")
    if len(line) > limit:
        line = line[: limit - len(more)].rsplit(" ", 1)[0].rstrip(" ,;:-") + more
    return line


TZ = ZoneInfo("America/Los_Angeles")   # dates as the owner lives them (Dublin, California)


def day(stamp: str) -> str:
    d = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(TZ)
    return f"{d:%b} {d.day}"


def public_repos(get=fetch) -> list[dict]:
    repos = []
    for kind, name in ACCOUNTS:
        for r in get(f"/{kind}/{name}/repos?per_page=100&type=public&sort=pushed") or []:
            if r["private"] or r["archived"] or r["fork"] or r["full_name"] in SKIP:
                continue
            repos.append(r)
    return sorted(repos, key=lambda r: (r["pushed_at"], r["full_name"]), reverse=True)


def last_commit(full: str, get=fetch):
    for c in get(f"/repos/{full}/commits?per_page=20") or []:
        msg = c["commit"]["message"]
        if len(c.get("parents", [])) == 1 and not msg.startswith("Merge "):
            return c["commit"]["author"]["date"], msg
    return None


def releases(full: str, get=fetch) -> list:
    """Published, non-prerelease releases, newest first (the last 100 of them)."""
    rel = [r for r in get(f"/repos/{full}/releases?per_page=100") or [] if not r.get("draft") and not r.get("prerelease")]
    return sorted(rel, key=lambda r: r["published_at"], reverse=True)


def gather(get=fetch, now: str = None) -> dict:
    repos = public_repos(get)
    out = {"repos": [], "releases": [], "all_releases": [],
           "today": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")}
    for r in repos:
        full = r["full_name"]
        every = releases(full, get)
        rel = every[0] if every else None
        info = {"full": full, "name": r["name"], "url": r["html_url"], "pushed": r["pushed_at"],
                "release": rel and {"tag": clean(rel["tag_name"], 30), "url": rel["html_url"], "at": rel["published_at"]},
                "commit": last_commit(full, get), "release_dates": [x["published_at"] for x in every]}
        out["repos"].append(info)
        if rel:
            out["releases"].append({"name": r["name"], **info["release"]})
    out["releases"].sort(key=lambda x: x["at"], reverse=True)
    out["all_releases"] = list(out["releases"])
    if out["releases"]:  # only recent releases: within RECENT days of the newest one (no clock, so reruns agree)
        newest = datetime.fromisoformat(out["releases"][0]["at"].replace("Z", "+00:00"))
        out["releases"] = [x for x in out["releases"]
                           if (newest - datetime.fromisoformat(x["at"].replace("Z", "+00:00"))).days <= RECENT]
    return out


def themed(art: str, alt: str, width: str) -> str:
    """Both schemes of an image inside a link. GitHub drops a <picture> wrapped in <a>, so use its own fragments:
    ``#gh-dark-mode-only`` / ``#gh-light-mode-only`` show one file per GitHub theme, with no script, on every browser."""
    return (f'<img src="{art}-dark.svg#gh-dark-mode-only" width="{width}" alt="{alt}">'
            f'<img src="{art}-light.svg#gh-light-mode-only" width="{width}" alt="{alt}">')


def badge(path: str, alt: str, query: str = "") -> str:
    return f'<img src="https://img.shields.io/github/{path}?style=flat-square{query}" alt="{alt}">'


def spotlight(data: dict) -> str:
    by_name = {r["full"]: r for r in data["repos"]}
    missing = [full for full in SPOT if full not in by_name]
    if missing:                                         # the owner picked these four: never drop one, fail instead
        raise SystemExit(f"spotlight repositories missing from the API: {', '.join(missing)}")
    spots = [by_name[full] for full in SPOT]            # the owner's order, never reordered
    cells = []
    for r in spots:
        s = SPOT[r["full"]]
        full = r["full"]
        live = badge(f"v/release/{full}", "latest release", "&amp;label=release&amp;sort=date") if r["release"] \
            else badge(f"last-commit/{full}", "last commit")
        stars = badge(f"stars/{full}", "stars", "&amp;label=%E2%98%85")
        new = f"<b>New</b> · {day(r['commit'][0])} · {html.escape(clean(r['commit'][1], 48), False)}" if r["commit"] else ""
        cells.append(f'<td width="50%" valign="top">\n'
                     f'<a href="{s.get("link", r["url"])}">{themed(s["art"], html.escape(s["alt"]), "100%")}</a>\n'
                     f'<br><a href="{r["url"]}">{live} {stars}</a>\n'
                     f'<br><sub>{new}</sub>\n</td>')
    rows = ["<tr>\n" + "\n".join(cells[i:i + 2]) + "\n</tr>" for i in range(0, len(cells), 2)]
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def activity(data: dict) -> str:
    rel = " · ".join(f'<a href="{x["url"]}">{html.escape(x["name"])} {html.escape(x["tag"], False)}</a> {day(x["at"])}'
                     for x in data["releases"][:RELEASES])
    return f'<p align="center"><sub><b>Latest releases</b> · {rel}</sub></p>' if rel else ""


def _when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def stat(label: str, value: str) -> str:
    esc = lambda t: quote(t.replace("-", "--").replace("_", "__"), safe="")
    return (f'<img src="https://img.shields.io/badge/{esc(label)}-{esc(value)}-{BADGE[1]}?style=for-the-badge'
            f'&amp;labelColor={BADGE[0]}" alt="{html.escape(label)}: {html.escape(value)}">')


def stats(data: dict) -> str:
    today = _when(data["today"])
    rel = data["all_releases"]
    month = sum(1 for r in data["repos"] for at in r["release_dates"] if (today - _when(at)).days < 30)
    commits = sorted((r["commit"][0] for r in data["repos"] if r["commit"]), reverse=True)
    parts = [stat("open repos", str(len(data["repos"]))), stat("releases · 30 days", str(month))]
    if rel:
        parts.append(stat("last release", f"{rel[0]['name']} {rel[0]['tag']} · {day(rel[0]['at'])}"))
    if commits:
        parts.append(stat("last commit", f"{day(commits[0])} {_when(commits[0]).astimezone(TZ):%H:%M} PT"))
    return '<p align="center">\n' + "\n".join(parts) + "\n</p>"


def _by_commit(data):
    return sorted((r for r in data["repos"] if r["commit"]), key=lambda r: (r["commit"][0], r["full"]), reverse=True)


def ticker(data: dict) -> str:
    recent = _by_commit(data)[:3]
    if not recent:
        return ""
    first, rest = recent[0], recent[1:]
    line = (f'<b>▸ Now building</b> · <a href="{first["url"]}">{html.escape(first["name"])}</a>: '
            f'{html.escape(clean(first["commit"][1], 56), False)}, {day(first["commit"][0])}')
    line += "".join(f' · <a href="{r["url"]}">{html.escape(r["name"])}</a>, {day(r["commit"][0])}' for r in rest)
    return f"<p><sub>{line}</sub></p>"


def events(data: dict, k: int = 3) -> list:
    """The newest real events, oldest first, as plain telemetry lines for a hero's log: one per repository, its
    latest release if that came within a week of its latest commit, otherwise its latest commit."""
    ev = []
    for r in data["repos"]:
        rel, com = r["release"], r["commit"]
        if rel and (not com or (_when(com[0]) - _when(rel["at"])).days < 7):
            ev.append((rel["at"], f"{_when(rel['at']).astimezone(TZ):%m-%d} [{r['name']}] released {rel['tag']}"))
        elif com:
            ev.append((com[0], f"{_when(com[0]).astimezone(TZ):%m-%d} [{r['name']}] {clean(com[1], 52 - len(r['name']), '...')}"))
    ev.sort(key=lambda e: e[0], reverse=True)
    return [line for _, line in reversed(ev[:k])]


def splice(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    if start not in text:
        return text
    a, b = text.index(start) + len(start), text.index(end)
    return text[:a] + "\n" + body + "\n" + text[b:]


BLOCKS = {"spotlight": spotlight, "activity": activity, "stats": stats, "ticker": ticker}


def update(text: str, data: dict) -> str:
    for name, block in BLOCKS.items():
        if f"<!-- {name}:start -->" in text:
            text = splice(text, name, block(data))
    return text


def update_hero(path: Path, data: dict) -> bool:
    """Write the newest events into the hero spec's ops motif; True if the file changed."""
    old = path.read_text(encoding="utf-8")
    spec = json.loads(old)
    for b in spec["banners"]:
        if (b.get("motif") or {}).get("kind") == "ops":
            b["motif"]["log"] = events(data)
    new = json.dumps(spec, indent=1, ensure_ascii=False) + "\n"
    if new != old:
        path.write_text(new, encoding="utf-8")
    return new != old


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--config" in argv:
        i = argv.index("--config")
        configure(json.loads(Path(argv[i + 1]).read_text(encoding="utf-8")))
        del argv[i:i + 2]
    path = Path(argv[0] if argv else "README.md")
    old = path.read_text(encoding="utf-8")
    data = gather()
    if HERO:
        print("updated" if update_hero(Path(HERO), data) else "unchanged", HERO)
    new = update(old, data)
    if new != old:
        path.write_text(new, encoding="utf-8")
    print("updated" if new != old else "unchanged", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
