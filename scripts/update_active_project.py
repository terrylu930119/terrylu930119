#!/usr/bin/env python3
"""Highlight the most active featured project over a rolling commit window.

Counts commits authored by GH_USER on each featured repository's default branch
within WINDOW_DAYS, then enables a subtle animated border and explanatory badge
on the winner's SVG.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OWNER = "terrylu930119"
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "30"))
USERNAME = os.environ.get("GH_USER", OWNER)
TOKEN = os.environ.get("GH_ACTIVITY_TOKEN", "").strip()
STATE_PATH = Path(".github/active-project-state.json")

PROJECTS = {
    "ai": {
        "repo": f"{OWNER}/ai_interactive_portfolio",
        "svg": Path("assets/v5_5/project-ai.svg"),
    },
    "quant": {
        "repo": f"{OWNER}/crypto_auto_trading",
        "svg": Path("assets/v5_5/project-quant.svg"),
    },
    "video": {
        "repo": f"{OWNER}/video_similarity_project",
        "svg": Path("assets/v5_5/project-video.svg"),
    },
}

ACTIVE_BLOCK = """<!-- ACTIVITY_BORDER_START -->
<rect x=\"42\" y=\"8\" width=\"1116\" height=\"178\" rx=\"18\" fill=\"none\" stroke=\"#8B5CF6\" stroke-width=\"3\" stroke-opacity=\".22\">
  <animate attributeName=\"stroke-opacity\" values=\".18;.95;.18\" dur=\"2.8s\" repeatCount=\"indefinite\"/>
  <animate attributeName=\"stroke-width\" values=\"2.5;4;2.5\" dur=\"2.8s\" repeatCount=\"indefinite\"/>
</rect>
<g>
  <rect x=\"876\" y=\"28\" width=\"168\" height=\"30\" rx=\"15\" fill=\"#f3edff\" stroke=\"#ddcffb\"/>
  <circle cx=\"896\" cy=\"43\" r=\"4.5\" fill=\"#8B5CF6\"><animate attributeName=\"opacity\" values=\".45;1;.45\" dur=\"2.8s\" repeatCount=\"indefinite\"/></circle>
  <text x=\"969\" y=\"43\" text-anchor=\"middle\" dominant-baseline=\"middle\" font-family=\"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif\" font-size=\"12.5\" font-weight=\"800\" fill=\"#6D4BD1\">MOST ACTIVE · 30D</text>
</g>
<!-- ACTIVITY_BORDER_END -->"""

INACTIVE_BLOCK = """<!-- ACTIVITY_BORDER_START -->
<!-- ACTIVITY_BORDER_END -->"""

BLOCK_RE = re.compile(
    r"<!-- ACTIVITY_BORDER_START -->.*?<!-- ACTIVITY_BORDER_END -->",
    re.DOTALL,
)


def api_get(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "terrylu930119-profile-readme-activity",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {url}: {body}") from exc


def count_commits(repo: str, since: datetime) -> int:
    total = 0
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {
                "author": USERNAME,
                "since": since.isoformat().replace("+00:00", "Z"),
                "per_page": 100,
                "page": page,
            }
        )
        items = api_get(f"https://api.github.com/repos/{repo}/commits?{params}")
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected response while reading commits for {repo}")
        total += len(items)
        if len(items) < 100:
            return total
        page += 1


def previous_winner() -> str | None:
    if not STATE_PATH.exists():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        value = state.get("active_project")
        return value if value in PROJECTS else None
    except (json.JSONDecodeError, OSError):
        return None


def pick_winner(counts: dict[str, int], previous: str | None) -> str:
    highest = max(counts.values())
    tied = [key for key, count in counts.items() if count == highest]
    if previous in tied:
        return previous
    # Deterministic fallback if two projects have exactly the same count.
    for key in ("quant", "ai", "video"):
        if key in tied:
            return key
    raise AssertionError("No winner found")


def update_svg(path: Path, active: bool) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = ACTIVE_BLOCK if active else INACTIVE_BLOCK
    new_text, replacements = BLOCK_RE.subn(replacement, text, count=1)
    if replacements != 1:
        raise RuntimeError(f"Missing activity border markers in {path}")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


def main() -> int:
    if not TOKEN:
        print(
            "GH_ACTIVITY_TOKEN is missing. Add repository secret PROFILE_ACTIVITY_PAT "
            "with read access to the featured private repositories.",
            file=sys.stderr,
        )
        return 2

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    counts = {
        key: count_commits(project["repo"], since)
        for key, project in PROJECTS.items()
    }
    winner = pick_winner(counts, previous_winner())

    for key, project in PROJECTS.items():
        update_svg(project["svg"], active=(key == winner))

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "active_project": winner,
                "counts": counts,
                "window_days": WINDOW_DAYS,
                "username": USERNAME,
                "updated_at": now.isoformat().replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Most active project: {winner} | counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
