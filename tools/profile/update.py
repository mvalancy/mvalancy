#!/usr/bin/env python3
"""Refresh the live parts of the profile README from the public GitHub API.

    GITHUB_TOKEN=... python3 tools/profile/update.py README.md

Two blocks are rewritten in place, each between its own marker comments:

* ``spotlight``: the projects that have spotlight art (``SPOT``), newest default-branch commit first, each as its animated
  card with live shields (latest release, or last commit when there is none, and stars) and a "what's new" line
  taken from its latest non-merge commit on the default branch.
* ``activity``: releases from the last two months.

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
from datetime import datetime
from pathlib import Path

API = "https://api.github.com"
ACCOUNTS = [("users", "mvalancy"), ("orgs", "Valpatel")]
SKIP = {"mvalancy/mvalancy", "Valpatel/.github"}  # the profile repos themselves: their pushes are this job's own
SPOT = {
    "Valpatel/cad-agent": dict(art="assets/spot/cad-agent.svg", link="https://cad-agent.valpatel.com",
                               alt="cad-agent: your one stop shop for agentic CAD."),
    "Valpatel/gyropup": dict(art="assets/spot/gyropup.svg", link="https://gyropup.com",
                             alt="Gyropup: a research robot designed to balance on two wheel-legs, with a foam-ball turret."),
    "mvalancy/val-ark": dict(art="assets/spot/val-ark.svg",
                             alt="val-ark: fills a disk with open-source tools, AI models and Wikipedia, then serves it offline."),
    "mvalancy/j501-agx-orin": dict(art="assets/spot/j501-agx-orin.svg",
                                   alt="j501-agx-orin: a 3D-printable enclosure for the Seeed J501 carrier and Jetson AGX Orin."),
}
RELEASES, RECENT = 4, 60


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


def clean(text: str, limit: int = 80) -> str:
    """One line of plain text, safe inside an HTML block in a README: no tags, links or mentions, ``&`` escaped."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    line = re.sub(r"https?://\S+", "", line)
    line = re.sub(r"[`<>\\]", "", line)
    line = re.sub(r"@(?=\w)", "", line)
    line = re.sub(r"[\x00-\x1f\x7f]", "", line)
    line = re.sub(r"\s+", " ", line).strip(" -:·")
    if len(line) > limit:
        line = line[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return html.escape(line, quote=False)


def day(stamp: str) -> str:
    d = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
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
            return c["commit"]["author"]["date"], clean(msg, 48)
    return None


def latest_release(full: str, get=fetch):
    rel = [r for r in get(f"/repos/{full}/releases?per_page=5") or [] if not r.get("draft") and not r.get("prerelease")]
    return rel[0] if rel else None


def gather(get=fetch) -> dict:
    repos = public_repos(get)
    out = {"repos": [], "releases": []}
    for r in repos:
        full = r["full_name"]
        rel = latest_release(full, get)
        info = {"full": full, "name": r["name"], "url": r["html_url"], "pushed": r["pushed_at"],
                "release": rel and {"tag": clean(rel["tag_name"], 30), "url": rel["html_url"], "at": rel["published_at"]},
                "commit": last_commit(full, get)}
        out["repos"].append(info)
        if rel:
            out["releases"].append({"name": r["name"], **info["release"]})
    out["releases"].sort(key=lambda x: x["at"], reverse=True)
    if out["releases"]:  # only recent releases: within RECENT days of the newest one (no clock, so reruns agree)
        newest = datetime.fromisoformat(out["releases"][0]["at"].replace("Z", "+00:00"))
        out["releases"] = [x for x in out["releases"]
                           if (newest - datetime.fromisoformat(x["at"].replace("Z", "+00:00"))).days <= RECENT]
    return out


def badge(path: str, alt: str, query: str = "") -> str:
    return f'<img src="https://img.shields.io/github/{path}?style=flat-square{query}" alt="{alt}">'


def spotlight(data: dict) -> str:
    spots = sorted((r for r in data["repos"] if r["full"] in SPOT),
                   key=lambda r: (r["commit"][0] if r["commit"] else "", r["full"]), reverse=True)
    if not spots:                                       # never commit an empty spotlight: fail the run instead
        raise SystemExit("no spotlight repository came back from the API")
    cells = []
    for r in spots:
        s = SPOT[r["full"]]
        full = r["full"]
        live = badge(f"v/release/{full}", "latest release", "&amp;label=release&amp;sort=date") if r["release"] \
            else badge(f"last-commit/{full}", "last commit")
        stars = badge(f"stars/{full}", "stars", "&amp;label=%E2%98%85")
        new = f"<b>New</b> · {day(r['commit'][0])} · {r['commit'][1]}" if r["commit"] else ""
        cells.append(f'<td width="50%" valign="top">\n'
                     f'<a href="{s.get("link", r["url"])}"><img src="{s["art"]}" width="100%" alt="{html.escape(s["alt"])}"></a>\n'
                     f'<br><a href="{r["url"]}">{live} {stars}</a>\n'
                     f'<br><sub>{new}</sub>\n</td>')
    rows = ["<tr>\n" + "\n".join(cells[i:i + 2]) + "\n</tr>" for i in range(0, len(cells), 2)]
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def activity(data: dict) -> str:
    rel = " · ".join(f'<a href="{x["url"]}">{html.escape(x["name"])} {x["tag"]}</a> {day(x["at"])}'
                     for x in data["releases"][:RELEASES])
    return f'<p align="center"><sub><b>Latest releases</b> · {rel}</sub></p>' if rel else ""


def splice(text: str, name: str, body: str) -> str:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    a, b = text.index(start) + len(start), text.index(end)
    return text[:a] + "\n" + body + "\n" + text[b:]


def update(text: str, data: dict) -> str:
    return splice(splice(text, "spotlight", spotlight(data)), "activity", activity(data))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0] if argv else "README.md")
    old = path.read_text(encoding="utf-8")
    new = update(old, gather())
    if new != old:
        path.write_text(new, encoding="utf-8")
    print("updated" if new != old else "unchanged", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
