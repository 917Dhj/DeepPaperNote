from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import fitz

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts"


def pdf(path: Path, version: int = 1, title: str = "Archive Handoff Paper") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            f"{title}\nAlice Example\narXiv:2601.12345v{version}\n"
            "Abstract\nA study of paper archives.",
        )
        doc.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_note(tmp_path: Path, vault: Path, source: Path, *, preflight=True, extra=()):
    manifest = tmp_path / "source.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "ok",
                "title": "Archive Handoff Paper",
                "paper_id": "arxiv:2601.12345",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "pdf": {"path": str(source)},
            }
        )
    )
    cmd = [
        sys.executable,
        str(SCRIPTS / "write_obsidian_note.py"),
        "--vault",
        str(vault),
        "--title",
        "Archive Handoff Paper",
        "--language",
        "en",
        "--source-manifest",
        str(manifest),
    ]
    if preflight:
        cmd.append("--preflight")
    else:
        content = "# Archive Handoff Paper\n\nA verified reading.\n"
        lint = tmp_path / "lint.json"
        lint.write_text(
            json.dumps(
                {
                    "output_language": "en",
                    "note_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "passes_basic_structure": True,
                    "passes_style_gate": True,
                    "passes_math_gate": True,
                }
            )
        )
        decisions = tmp_path / "decisions.json"
        decisions.write_text(json.dumps({"output_language": "en", "decisions": []}))
        cmd += [
            "--content",
            content,
            "--lint-json",
            str(lint),
            "--figure-decisions",
            str(decisions),
        ]
    result = subprocess.run(cmd + list(extra), capture_output=True, text=True, env=os.environ)
    return result, json.loads(result.stdout) if result.stdout else {}


def test_pdf_only_folder_is_admitted_without_registration_and_preflight_is_readonly(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    source = folder / "original.pdf"
    pdf(source)
    result, report = write_note(tmp_path, vault, source)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(report["target_directory"]) == folder
    assert list(folder.iterdir()) == [source]
    result, report = write_note(tmp_path, vault, source, preflight=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(report["note_path"]).parent == folder
    assert source.is_file()


def test_new_version_reuses_directory_and_keeps_prior_note_and_assets(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    first = folder / "v1.pdf"
    first_hash = pdf(first)
    result, old = write_note(tmp_path, vault, first, preflight=False)
    assert result.returncode == 0, result.stdout + result.stderr
    old_note = Path(old["note_path"])
    original_text = old_note.read_bytes()
    second = tmp_path / "v2.pdf"
    second_hash = pdf(second, 2)
    result, report = write_note(tmp_path, vault, second, preflight=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(report["note_path"]).parent == folder
    assert Path(report["note_path"]) != old_note
    assert old_note.read_bytes() == original_text
    assert Path(report["images_dir"]).parent == folder / "images"
    record = json.loads((folder / ".deeppapernote.json").read_text())
    assert set(record["sources"]) == {first_hash, second_hash}
    result, conflict = write_note(tmp_path, vault, second)
    assert result.returncode == 2
    assert conflict["conflict_code"] == "same_language_note_exists"


def test_local_lookup_selects_latest_and_explicit_version_wins(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    pdf(folder / "v1.pdf", 1)
    pdf(folder / "v2.pdf", 2)
    command = [
        sys.executable,
        str(SCRIPTS / "find_archived_source.py"),
        "--vault",
        str(vault),
        "--input",
        "https://arxiv.org/abs/2601.12345",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(json.loads(result.stdout)["pdf_path"]).name == "v2.pdf"
    result = subprocess.run(
        command[:-1] + ["https://arxiv.org/abs/2601.12345v1"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(json.loads(result.stdout)["pdf_path"]).name == "v1.pdf"
    assert not (folder / ".deeppapernote.json").exists()


def test_multiple_directories_require_selection_and_selection_survives_save(tmp_path):
    import shutil

    vault = tmp_path / "vault"
    first = vault / "One/Archive_Handoff_Paper/original.pdf"
    pdf(first)
    second = vault / "Two/Archive_Handoff_Paper/original.pdf"
    second.parent.mkdir(parents=True)
    shutil.copy2(first, second)
    result, report = write_note(tmp_path, vault, first)
    assert result.returncode == 2
    assert report["conflict_code"] == "multiple_source_directories"
    result, report = write_note(
        tmp_path, vault, first, preflight=False, extra=("--target-directory", str(second.parent))
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(report["note_path"]).parent == second.parent
    assert not list(first.parent.glob("*.md"))


def test_legacy_note_binding_survives_source_record_migration(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    source = folder / "v1.pdf"
    digest = pdf(source)
    old_note = folder / "My reading.zh-CN.md"
    old_note.write_text("# My handwritten edits\n")
    note_record = {
        "filename": old_note.name,
        "note_sha256": hashlib.sha256(old_note.read_bytes()).hexdigest(),
    }
    (folder / ".deeppapernote.json").write_text(
        json.dumps(
            {
                "artifact_type": "deeppapernote_paper_directory",
                "schema_version": 1,
                "paper_id": "arxiv:2601.12345",
                "title": "Archive Handoff Paper",
                "source_sha256": digest,
                "note_stem": "Archive_Handoff_Paper",
                "notes": {"zh-CN": note_record},
                "custom_field": "keep me",
            }
        )
    )
    result, report = write_note(tmp_path, vault, source, preflight=False)
    assert result.returncode == 0, result.stdout + result.stderr
    updated = json.loads((folder / ".deeppapernote.json").read_text())
    assert updated["custom_field"] == "keep me"
    assert updated["sources"][digest]["notes"]["zh-CN"] == note_record
    assert old_note.read_text() == "# My handwritten edits\n"


def test_local_lookup_never_orders_same_version_variants_by_download_time(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    pdf(folder / "original.pdf", 2)
    pdf(folder / "annotated.pdf", 2)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "find_archived_source.py"),
            "--vault",
            str(vault),
            "--input",
            "https://arxiv.org/abs/2601.12345",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["conflict_code"] == "ambiguous_archived_sources"


def test_foreign_pdf_in_same_name_folder_blocks_without_writes(tmp_path):
    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    folder.mkdir(parents=True)
    foreign = folder / "foreign.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Different Paper\narXiv:2601.99999v1\nAbstract")
        doc.save(foreign)
    source = tmp_path / "wanted.pdf"
    pdf(source)
    result, report = write_note(tmp_path, vault, source)
    assert result.returncode == 2
    assert report["conflict_code"] == "pdf_work_identity_mismatch"
    assert list(folder.iterdir()) == [foreign]


def test_fetch_uses_archive_without_network_and_keeps_explicit_version(tmp_path, monkeypatch):
    import fetch_pdf

    vault = tmp_path / "vault"
    folder = vault / "Existing/Archive_Handoff_Paper"
    pdf(folder / "v1.pdf", 1)
    pdf(folder / "v2.pdf", 2)
    identity = {
        "status": "ok",
        "artifact_type": "canonical_identity",
        "schema_version": 2,
        "identity_verdict": "accepted",
        "paper_id": "arxiv:2601.12345",
        "work_level_identity": {"title": "Archive Handoff Paper", "arxiv_id": "2601.12345"},
        "source_manifestation": {"source_kind": "arxiv", "arxiv_id": "2601.12345v2"},
        "bound_sources": [{"kind": "pdf_url", "value": "https://arxiv.org/pdf/2601.12345v2"}],
    }

    def unexpected_network(url):
        raise AssertionError("Local archive must avoid downloading: " + url)

    monkeypatch.setattr(fetch_pdf, "http_get_bytes", unexpected_network)
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(identity))
    output = tmp_path / "fetch.json"
    fetch_pdf.main(
        [
            "--input",
            "{}",
            "--identity",
            str(identity_path),
            "--vault",
            str(vault),
            "--reference",
            "https://arxiv.org/abs/2601.12345v1",
            "--output",
            str(output),
        ]
    )
    result = json.loads(output.read_text())
    assert result["pdf_source"] == "obsidian_archive"
    assert Path(result["pdf_path"]).name == "v1.pdf"
    assert result["source_manifestation"]["arxiv_id"] == "2601.12345v1"
    assert result["archive_source"]["target_directory"] == str(folder)


def test_fetch_missing_explicit_version_acquires_that_revision(tmp_path, monkeypatch):
    import fetch_pdf

    vault = tmp_path / "vault"
    pdf(vault / "Existing/Archive_Handoff_Paper/v2.pdf", 2)
    requested_file = tmp_path / "requested.pdf"
    pdf(requested_file, 1)
    identity = {
        "status": "ok",
        "artifact_type": "canonical_identity",
        "schema_version": 2,
        "identity_verdict": "accepted",
        "paper_id": "arxiv:2601.12345",
        "work_level_identity": {"title": "Archive Handoff Paper", "arxiv_id": "2601.12345"},
        "source_manifestation": {"source_kind": "arxiv", "arxiv_id": "2601.12345"},
        "bound_sources": [{"kind": "pdf_url", "value": "https://arxiv.org/pdf/2601.12345.pdf"}],
    }
    urls = []

    def download(url):
        urls.append(url)
        return requested_file.read_bytes()

    monkeypatch.setattr(fetch_pdf, "http_get_bytes", download)
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(identity))
    output = tmp_path / "fetch.json"
    fetch_pdf.main(
        [
            "--input",
            "{}",
            "--identity",
            str(identity_path),
            "--vault",
            str(vault),
            "--target-directory",
            str(vault / "Existing/Archive_Handoff_Paper"),
            "--reference",
            "https://arxiv.org/abs/2601.12345v1",
            "--output",
            str(output),
            "--dest-dir",
            str(tmp_path / "download"),
        ]
    )
    assert urls == ["https://arxiv.org/pdf/2601.12345v1.pdf"]
    result = json.loads(output.read_text())
    assert result["source_manifestation"]["arxiv_id"] == "2601.12345v1"
    assert result["source_sha256"] == hashlib.sha256(requested_file.read_bytes()).hexdigest()

    assert result["archive_source"]["target_directory"] == str(
        vault / "Existing/Archive_Handoff_Paper"
    )


def test_unique_verified_directory_wins_over_title_only_candidate(tmp_path):
    vault = tmp_path / "vault"
    source = vault / "Verified/Archive_Handoff_Paper/original.pdf"
    pdf(source)
    (vault / "Other/Archive_Handoff_Paper").mkdir(parents=True)
    result, report = write_note(tmp_path, vault, source, preflight=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(report["note_path"]).parent == source.parent
    record = json.loads((source.parent / ".deeppapernote.json").read_text())
    evidence = record["work"]["provenance"]["arxiv"]
    assert {
        "kind": "pdf_first_page",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    } in evidence


def test_figure_planner_keeps_source_specific_asset_directory(tmp_path):
    manifest = tmp_path / "source.json"
    manifest.write_text(
        json.dumps(
            {"captions": {"figures": [{"id": "Figure 1", "caption": "Overview", "page": 1}]}}
        )
    )
    figures = tmp_path / "figures.json"
    figures.write_text(
        json.dumps(
            {
                "output_language": "en",
                "figure_plan": {
                    "figures": [
                        {
                            "id": "Figure 1",
                            "figure_asset_candidate": {
                                "filename": "figure.png",
                                "candidate_status": "reject",
                            },
                        }
                    ]
                },
            }
        )
    )
    asset_subdir = "images/" + "a" * 64
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "plan_figure_table_decisions.py"),
            "--source-manifest",
            str(manifest),
            "--figures",
            str(figures),
            "--language",
            "en",
            "--asset-subdir",
            asset_subdir,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["asset_subdir"] == asset_subdir
    assert (
        payload["decisions"][0]["relative_markdown_embed"]
        == f"![Figure 1]({asset_subdir}/figure.png)"
    )
