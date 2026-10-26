#!/usr/bin/env python3
"""Update a repository-local star-history SVG from public star-count samples."""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_API = "https://api.github.com"


def update_history(
    history: list[tuple[dt.date, int]], sample_day: dt.date, total: int
) -> list[tuple[dt.date, int]]:
    if history and history[-1][0] == sample_day:
        return [*history[:-1], (sample_day, total)]
    return [*history, (sample_day, total)]


def github_json(url: str, retries: int = 3) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "deeppapernote-static-star-history",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            if attempt == retries:
                raise RuntimeError(f"GitHub request failed: {exc}") from exc
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def fetch_star_count(repo: str) -> int:
    data = github_json(f"{GITHUB_API}/repos/{repo}")
    if not isinstance(data, dict) or not isinstance(data.get("stargazers_count"), int):
        raise RuntimeError(f"GitHub response omitted stargazers_count for {repo}")
    return data["stargazers_count"]


def load_history(path: Path) -> list[tuple[dt.date, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(dt.date.fromisoformat(item["date"]), int(item["stars"])) for item in data]


def atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def _nice_step(maximum: int) -> int:
    rough = max(1, maximum) / 4
    power = 10 ** math.floor(math.log10(rough))
    for multiplier in (1, 2, 5, 10):
        step = int(multiplier * power)
        if step >= rough:
            return max(1, step)
    return 1


def render_svg(
    repo: str,
    points: list[tuple[dt.date, int]],
    *,
    generated_at: dt.datetime,
) -> str:
    total = points[-1][1] if points else 0
    generated_at = generated_at.astimezone(dt.timezone.utc)
    fallback_day = generated_at.date()
    start = points[0][0] if points else fallback_day
    end = points[-1][0] if points else fallback_day
    span_days = max(1, (end - start).days)
    max_y = max(1, total)
    step = _nice_step(max_y)
    y_max = max(step, math.ceil(max_y / step) * step)

    left, top, right, bottom = 76, 112, 864, 284

    def x(day: dt.date) -> float:
        return left + ((day - start).days / span_days) * (right - left)

    def y(value: int) -> float:
        return bottom - (value / y_max) * (bottom - top)

    polyline = " ".join(f"{x(day):.1f},{y(value):.1f}" for day, value in points)
    y_ticks = range(0, y_max + 1, step)
    label_days = list(dict.fromkeys(
        start + dt.timedelta(days=round((end - start).days * ratio / 3))
        for ratio in range(4)
    ))
    repo_label = html.escape(repo)
    star_word = "star" if total == 1 else "stars"
    updated = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    grid = "".join(
        f'<line x1="{left}" y1="{y(value):.1f}" x2="{right}" y2="{y(value):.1f}" '
        f'stroke="#b2a28a" stroke-opacity="0.18" stroke-width="0.7" '
        f'stroke-dasharray="3 4"/>'
        f'<text x="{left - 12}" y="{y(value) + 4:.1f}" text-anchor="end" '
        f'font-size="12" fill="#ad9f89">{value:,}</text>'
        for value in y_ticks
    )
    x_labels = "".join(
        f'<line x1="{x(day):.1f}" y1="{bottom}" x2="{x(day):.1f}" y2="{bottom + 6}" '
        f'stroke="#ad9f89" stroke-opacity="0.4" stroke-width="0.7"/>'
        f'<text x="{x(day):.1f}" y="309" text-anchor="middle" font-size="12" '
        f'fill="#ad9f89">{day.strftime("%b %d")}</text>'
        for day in label_days
    )
    end_x = x(end) if points else left
    end_y = y(total) if points else bottom

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="360"
  style="max-width:100%;height:auto"
  viewBox="0 0 960 360" role="img" aria-labelledby="title desc">
  <title id="title">Star history for {repo_label}</title>
  <desc id="desc">Static star history chart for {repo_label}, generated {updated}.</desc>
  <defs>
    <clipPath id="card"><rect width="960" height="360" rx="14"/></clipPath>
    <radialGradient id="lamplight" cx="98%" cy="0%" r="85%">
      <stop stop-color="#c18b47" stop-opacity="0.16"/>
      <stop offset="1" stop-color="#c18b47" stop-opacity="0"/>
    </radialGradient>
    <filter id="paper" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.7 0.35" numOctaves="3"
        seed="17" stitchTiles="stitch"/>
      <feColorMatrix type="saturate" values="0"/>
    </filter>
    <filter id="glow" x="-10%" y="-30%" width="120%" height="160%"
      color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="2.5"/>
      <feComponentTransfer><feFuncA type="linear" slope="0.55"/></feComponentTransfer>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <g clip-path="url(#card)">
    <rect width="960" height="360" fill="#101820"/>
    <rect width="960" height="360" fill="url(#lamplight)"/>
    <rect width="960" height="360" filter="url(#paper)" opacity="0.055"/>
  </g>
  <text x="76" y="53" font-family="Georgia, 'Times New Roman', serif"
    font-size="32" font-weight="700" fill="#e8ddc8">Star History</text>
  <g font-family="Inter, ui-sans-serif, system-ui, sans-serif">
    <text x="76" y="78" font-size="13" fill="#ad9f89">{repo_label}</text>
    {grid}
    {x_labels}
    <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}"
      stroke="#ad9f89" stroke-opacity="0.5" stroke-width="0.7"/>
    <g filter="url(#glow)">
      <polyline points="{polyline}" fill="none" stroke="#e8b86a" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="4" fill="#e8b86a"
        stroke="#fff0ce" stroke-width="1"/>
    </g>
    <text x="{end_x + 48:.1f}" y="{end_y - 16:.1f}" text-anchor="end" font-size="14"
      fill="#e8b86a">{total:,} {star_word}</text>
    <text x="912" y="340" text-anchor="end" font-size="10" fill="#ad9f89">
      Updated {generated_at.strftime("%b %d, %Y")}
    </text>
  </g>
</svg>
'''


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "917Dhj/DeepPaperNote")
    output = Path("assets/star-history.svg")
    history_path = Path("assets/star-history.json")
    sample_day = dt.datetime.now(dt.timezone.utc).date()
    history = update_history(load_history(history_path), sample_day, fetch_star_count(repo))
    svg = render_svg(
        repo,
        history,
        generated_at=dt.datetime.combine(sample_day, dt.time.min, tzinfo=dt.timezone.utc),
    )
    atomic_write(history_path, json.dumps(
        [{"date": day.isoformat(), "stars": stars} for day, stars in history],
        indent=2,
    ) + "\n")
    atomic_write(output, svg)
    print(f"Wrote {history_path} and {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
