from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import pytest

from scripts.generate_star_history import render_svg, update_history


def test_update_history_keeps_one_sample_per_day() -> None:
    history = [(dt.date(2026, 7, 18), 523)]

    assert update_history(history, dt.date(2026, 7, 18), 524) == [
        (dt.date(2026, 7, 18), 524)
    ]
    assert update_history(history, dt.date(2026, 7, 19), 524) == [
        (dt.date(2026, 7, 18), 523),
        (dt.date(2026, 7, 19), 524),
    ]


def test_render_svg_produces_branded_star_history_card() -> None:
    svg = render_svg(
        "917Dhj/DeepPaperNote",
        [(dt.date(2026, 4, 1), 1), (dt.date(2026, 4, 2), 3)],
        generated_at=dt.datetime(2026, 4, 3, 12, 30, tzinfo=dt.timezone.utc),
    )

    root = ET.fromstring(svg)

    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"] == "0 0 960 360"
    assert "917Dhj/DeepPaperNote" in svg
    assert "3 stars" in svg
    assert "2026-04-03 12:30 UTC" in svg
    ns = {"svg": "http://www.w3.org/2000/svg"}
    curve = root.find(".//svg:polyline", ns)
    assert curve is not None
    assert curve.attrib["points"] == "76.0,226.7 864.0,112.0"
    assert curve.attrib["stroke"] == "#e8b86a"
    assert curve.attrib["fill"] == "none"
    assert root.find(".//svg:polygon", ns) is None
    noise = root.find(".//svg:feTurbulence", ns)
    assert noise is not None and noise.attrib["seed"] == "17"
    assert svg.count(">3 stars</text>") == 1
    assert svg == render_svg(
        "917Dhj/DeepPaperNote",
        [(dt.date(2026, 4, 1), 1), (dt.date(2026, 4, 2), 3)],
        generated_at=dt.datetime(2026, 4, 3, 12, 30, tzinfo=dt.timezone.utc),
    )


@pytest.mark.parametrize("counts", [[], [1]])
def test_render_svg_short_history_has_no_duplicate_date_labels(counts: list[int]) -> None:
    svg = render_svg(
        "owner/paper & notes",
        [(dt.date(2026, 4, 1), value) for value in counts],
        generated_at=dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc),
    )

    root = ET.fromstring(svg)
    assert "Apr 01" in svg
    assert svg.count(">Apr 01</text>") == 1
    assert "1 star</text>" in svg if counts else "0 stars</text>" in svg
    assert root.find("{http://www.w3.org/2000/svg}title").text == (
        "Star history for owner/paper & notes"
    )
