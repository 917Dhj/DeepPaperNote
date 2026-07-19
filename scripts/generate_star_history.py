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

    left, top, right, bottom = 82, 92, 928, 472

    def x(day: dt.date) -> float:
        return left + ((day - start).days / span_days) * (right - left)

    def y(value: int) -> float:
        return bottom - (value / y_max) * (bottom - top)

    polyline = " ".join(f"{x(day):.1f},{y(value):.1f}" for day, value in points)
    if points:
        area = f"{left},{bottom} {polyline} {x(end):.1f},{bottom}"
    else:
        area = f"{left},{bottom} {right},{bottom}"

    y_ticks = range(0, y_max + 1, step)
    label_days = [start + dt.timedelta(days=round(span_days * ratio / 3)) for ratio in range(4)]
    repo_label = html.escape(repo)
    star_word = "star" if total == 1 else "stars"
    updated = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    grid = "".join(
        f'<line x1="{left}" y1="{y(value):.1f}" x2="{right}" y2="{y(value):.1f}" '
        f'stroke="#2e4264" stroke-width="1"/>'
        f'<text x="{left - 12}" y="{y(value) + 4:.1f}" text-anchor="end" '
        f'font-size="12" fill="#99abc7">{value:,}</text>'
        for value in y_ticks
    )
    x_labels = "".join(
        f'<line x1="{x(day):.1f}" y1="{top}" x2="{x(day):.1f}" y2="{bottom}" '
        f'stroke="#253652" stroke-width="1"/>'
        f'<text x="{x(day):.1f}" y="506" text-anchor="middle" font-size="12" '
        f'fill="#99abc7">{day.isoformat()}</text>'
        for day in label_days
    )
    end_x = x(end) if points else left
    end_y = y(total) if points else bottom

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="560"
  viewBox="0 0 960 560" role="img" aria-labelledby="title desc">
  <title id="title">Star history for {repo_label}</title>
  <desc id="desc">Static star history chart for {repo_label}, generated {updated}.</desc>
  <rect width="960" height="560" rx="18" fill="#0e1729"/>
  <text x="82" y="38" font-family="Inter, ui-sans-serif, system-ui, sans-serif"
    font-size="24" font-weight="700" fill="#f3f6fb">Star History</text>
  <text x="82" y="64" font-family="Inter, ui-sans-serif, system-ui, sans-serif"
    font-size="13" fill="#99abc7">{repo_label} · {total:,} {star_word} · updated {updated}</text>
  <g font-family="Inter, ui-sans-serif, system-ui, sans-serif">
    {grid}
    {x_labels}
    <line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#7085ab" stroke-width="1.2"/>
    <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#7085ab" stroke-width="1.2"/>
    <polygon points="{area}" fill="#77a2ff" opacity="0.18"/>
    <polyline points="{polyline}" fill="none" stroke="#77a2ff" stroke-width="3"
      stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="5" fill="#d69a4a"
      stroke="#f3f6fb" stroke-width="2"/>
    <text x="{right}" y="82" text-anchor="end" font-size="13" font-weight="700"
      fill="#d69a4a">{total:,} {star_word}</text>
    <text x="82" y="542" font-size="12" fill="#7085ab">
      GitHub repository metadata · sampled every three days
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
