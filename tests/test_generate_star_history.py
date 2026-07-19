from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

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
    assert root.attrib["viewBox"] == "0 0 960 560"
    assert "917Dhj/DeepPaperNote" in svg
    assert "3 stars" in svg
    assert "2026-04-03 12:30 UTC" in svg
    assert "#0e1729" in svg
    assert "#2e4264" in svg
    assert "#f3f6fb" in svg
    assert "#99abc7" in svg
    assert "#77a2ff" in svg
    assert "#d69a4a" in svg
