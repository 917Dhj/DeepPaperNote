"""A local PDF's title comes from its title-sized type, and providers keep their subtitles."""

from __future__ import annotations

from pathlib import Path

import pytest
from common import extract_local_pdf_hints, fitz, normalize_crossref_work

pytestmark = pytest.mark.skipif(fitz is None, reason="PyMuPDF is required")


def write_first_page(path: Path, lines: list[tuple[float, float, str]], font: str = "helv") -> Path:
    """Write one page with (y, font size, text) lines, as a journal first page lays them out."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for y, size, text in lines:
        page.insert_text((50, y), text, fontsize=size, fontname=font)
    doc.save(path)
    doc.close()
    return path


def test_title_is_the_largest_type_not_the_journal_header(tmp_path: Path) -> None:
    pdf = write_first_page(
        tmp_path / "paper.pdf",
        [
            (40, 10, "Journal of Inorganic Analytical Chemistry Vol. 14, No. 2"),
            (110, 20, "Portable Laser Spectroscopy for Heavy"),
            (135, 20, "Metals in Agricultural Soil*"),
            (170, 12, "Mingjun Ma, Li Fang, Nanjing Zhao"),
        ],
    )

    hints = extract_local_pdf_hints(pdf)

    assert hints["title"] == "Portable Laser Spectroscopy for Heavy Metals in Agricultural Soil"
    assert hints["local_pdf_title_source"] == "first_page_title_used"


def test_chinese_title_is_the_largest_type_not_the_journal_name(tmp_path: Path) -> None:
    pdf = write_first_page(
        tmp_path / "paper.pdf",
        [
            (36, 13, "中国无机分析化学"),
            (60, 10, "第14卷第2期 2024年2月"),
            (107, 20, "便携式激光诱导击穿光谱仪测定土壤中重金属"),
            (140, 13, "马明俊，方丽，赵南京"),
        ],
        font="china-s",
    )

    hints = extract_local_pdf_hints(pdf)

    assert hints["title"] == "便携式激光诱导击穿光谱仪测定土壤中重金属"


def test_garbled_first_page_is_not_taken_as_a_title(tmp_path: Path) -> None:
    pdf = write_first_page(
        tmp_path / "lithium-review.pdf",
        [
            (60, 10, "!\"#$%&"),
            (110, 20, "!\"#$%&'()*"),
            (150, 13, "# $ # \" $ !! %"),
        ],
    )

    hints = extract_local_pdf_hints(pdf)

    assert hints["local_pdf_title_source"] == "local_pdf_stem_used"


@pytest.mark.parametrize(
    ("title", "subtitle", "expected"),
    [
        (
            ["LightGCN"],
            ["Simplifying and Powering Graph Convolution Network for Recommendation"],
            "LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation",
        ),
        (
            ["LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation"],
            ["Simplifying and Powering Graph Convolution Network for Recommendation"],
            "LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation",
        ),
        (["Segment Anything"], [], "Segment Anything"),
    ],
)
def test_crossref_title_keeps_its_subtitle(
    title: list[str], subtitle: list[str], expected: str
) -> None:
    record = normalize_crossref_work({"title": title, "subtitle": subtitle})

    assert record["title"] == expected
