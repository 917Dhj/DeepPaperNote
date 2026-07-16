from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]


def _section(text: str, start: str, end: str | None = None) -> str:
    body = text.split(start, 1)[1]
    return body.split(end, 1)[0] if end else body


def _assert_in_order(text: str, phrases: tuple[str, ...]) -> None:
    positions = [text.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)


def test_skill_documents_required_manifest_override_file_boundary() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "*_source_manifest.json" in text
    assert "raw_sections_path" in text
    assert "*_raw_sections.jsonl" in text
    assert "`--source-manifest` is always required" in text
    assert "`--raw-sections` only overrides" in text
    assert "scripts/run_pipeline.py" not in text


def test_scripts_are_self_contained_within_paper_glossary() -> None:
    scripts = sorted((SKILL_DIR / "scripts").glob("*.py"))
    assert scripts
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert "skills.deeppapernote" not in text
        assert "deeppapernote" not in text.lower()


def test_skill_orders_preview_gate_before_post_selection_writes() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    preview = _section(text, "## Preview And Wait (Default)", "## After Selection")
    after = _section(text, "## After Selection", "## Grounding")

    _assert_in_order(
        preview,
        (
            "Show saved configuration",
            "Require an explicit article Markdown path",
            "Run deterministic proposal",
            "Perform exactly one grounded host semantic review",
            "Record the reviewed shortlist",
            "Present every retained term",
            "No glossary notes or article Markdown have been written",
            "End the response and wait",
        ),
    )
    _assert_in_order(
        after,
        (
            "Accept only numbers",
            "Triage",
            "inventory",
            "generate one action-aware batch",
            "Run one writer invocation",
            "whole-batch preflight",
            "create/enrich/reuse commit",
            "Link each successful writer result",
            "Lint writer-returned changed glossary note files",
            "Report observable wall-clock timing",
        ),
    )


def test_task7_acceptance_preview_records_review_before_display_and_wait() -> None:
    text = (SKILL_DIR / "references" / "optimization-implementation-plan.md").read_text(
        encoding="utf-8"
    )
    task7 = _section(text, "### Task 7:", "## Execution Completion Criteria")

    _assert_in_order(
        task7,
        (
            "--review-proposal",
            "Display every retained item from this reviewed artifact",
            "End the response and wait",
        ),
    )


def test_preview_discloses_setup_write_and_limits_no_write_claim() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    preview = _section(text, "## Preview And Wait (Default)", "## After Selection")

    assert "Setup may create `~/.paper-glossary/config.json`" in preview
    assert "No glossary notes or article Markdown have been written" in preview
    assert "no files have been written" not in preview.lower()
    assert "before selection" in preview


def test_semantic_review_is_an_exact_term_subset_permutation() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(
        encoding="utf-8"
    )

    for text in (skill, contract):
        assert "only drop or reorder candidates" in text
        assert "exact `term` string" in text
        assert not re.search(
            r"\b(?:merge|rename|canonical|canonicalize|invent)\b", text, re.IGNORECASE
        )


def test_linker_is_conditional_and_glossary_only_skips_it() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(
        encoding="utf-8"
    )
    after = _section(skill, "## After Selection", "## Grounding")

    for text in (after, contract):
        assert "only if an article Markdown was supplied/requested" in text
        assert "For a glossary-only request, skip `link_glossary_terms.py`" in text


def test_lint_scope_is_writer_returned_changed_glossary_notes_only() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(
        encoding="utf-8"
    )
    after = _section(skill, "## After Selection", "## Grounding")

    for text in (after, contract):
        assert "writer-returned changed glossary note files" in text
        assert "`action` is `created`, `enriched`, or `updated`" in text
        assert "one `lint_glossary.py` invocation with repeated `--input PATH`" in text
        assert "Do not pass article Markdown to `lint_glossary.py`" in text


def test_term_note_linter_rejects_an_ordinary_article() -> None:
    scripts_dir = SKILL_DIR / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from lint_glossary import lint_term_file_text

    result = lint_term_file_text("# Paper\n\nOrdinary article prose.\n")
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes"] is False
    assert {
        "term_disclaimer_missing",
        "term_concept_zone_missing",
        "term_occurrence_zone_missing",
    }.issubset(codes)


def test_timing_matches_host_and_cli_observation_boundaries() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(
        encoding="utf-8"
    )
    after = _section(skill, "## After Selection", "## Grounding")

    for text in (after, contract):
        assert "Time host-only phases separately" in text
        assert "Each CLI emits top-level `elapsed_ms`" in text
        assert "single writer invocation includes whole-batch preflight and commit" in text
        assert "Do not report separate preflight and commit timings" in text
        assert "around each phase" not in text
    assert "current CLIs do not emit `elapsed_ms`" not in after
    assert '"elapsed_ms"' in contract


def test_default_prompt_enters_preview_and_wait_before_content_writes() -> None:
    text = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
    default_prompt = next(
        line.strip() for line in text.splitlines() if line.strip().startswith("default_prompt:")
    ).lower()

    assert "preview-and-wait" in default_prompt
    assert "numbered shortlist" in default_prompt
    assert "stop and wait" in default_prompt
    assert "before writing glossary notes or article links" in default_prompt


def test_readme_has_copy_paste_commands_for_each_launcher() -> None:
    text = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
    windows = _section(text, "## Windows PowerShell", "## macOS / Linux Bash")
    unix = _section(text, "## macOS / Linux Bash")

    windows_commands = [
        line.strip() for line in windows.splitlines() if line.startswith("py -3.12 ")
    ]
    unix_commands = [
        line.strip() for line in unix.splitlines() if line.startswith("python3 ")
    ]

    assert len(windows_commands) == 5
    assert len(unix_commands) == 5
    assert "python3 " not in windows
    assert "py -3.12 " not in unix
    assert any("--terms-dir '<vault>\\Glossary'" in line for line in windows_commands)
    assert any(
        "--validate-article '<vault>\\Papers\\example.md'" in line
        for line in windows_commands
    )
    assert any("--terms-dir '<vault>/Glossary'" in line for line in unix_commands)
    assert any(
        "--validate-article '<vault>/Papers/example.md'" in line
        for line in unix_commands
    )
    for flag in ("--show", "--reset", "-m pytest"):
        assert any(flag in line for line in windows_commands)
        assert any(flag in line for line in unix_commands)


def test_writer_docs_use_configured_destination_only() -> None:
    documents = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "README.md",
        SKILL_DIR / "references" / "file-contract.md",
    ]

    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert "configured glossary directory" in text


def test_test_suite_is_self_contained_within_skill() -> None:
    forbidden_fragments = (
        "." + "superpowers",
        "SKILL_DIR.parents" + "[1]",
    )

    for path in (SKILL_DIR / "tests").glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in text, f"{path.name} depends on repo-local scratch: {fragment}"


def test_workflow_integrations_use_config_backed_writer_cli() -> None:
    text = (SKILL_DIR / "tests" / "test_workflow_integration.py").read_text(
        encoding="utf-8"
    )

    assert "write_glossary_entries" not in text
    assert 'SCRIPTS_DIR / "write_glossary_terms.py"' in text
    assert text.count("_run_writer_cli(") == 4
    assert '"--config-path"' in text
    assert text.count('"--triage"') == 2


def test_contract_documents_current_json_and_required_manifest_override() -> None:
    text = (SKILL_DIR / "references" / "file-contract.md").read_text(encoding="utf-8")

    assert "`--source-manifest` is always required" in text
    assert "`--raw-sections` only overrides" in text
    assert "cannot replace the manifest" in text
    for field in (
        '"shortlist_limit"',
        '"awaiting_semantic_review"',
        '"existing_thin"',
        '"operation": "enrich"',
        '"article_sha256"',
        '"already_linked"',
        '"surface_forms"',
        '"proposal_sha256"',
        '"review_sha256"',
    ):
        assert field in text

    for flag in ("--review-proposal", "--reviewed-terms", "--reviewed-shortlist"):
        assert flag in text


def test_docs_stop_when_semantic_review_drops_every_candidate() -> None:
    documents = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "README.md",
        SKILL_DIR / "references" / "file-contract.md",
    ]

    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert "empty reviewed shortlist" in text
        assert "`no_candidates`" in text


def test_post_triage_docs_define_current_chain_digest_and_writer_contexts() -> None:
    documents = [
        SKILL_DIR / "SKILL.md",
        SKILL_DIR / "README.md",
        SKILL_DIR / "references" / "file-contract.md",
    ]

    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert "current `--source-manifest`" in text
        assert "saved `--reviewed-shortlist`" in text
        assert "saved `--triage`" in text
        assert "`mappings_sha256`" in text
        assert "`triage_sha256`" in text
        assert "exact ordered `term` and `surface_forms`" in text
        assert "derived from the resolved article Markdown stem" in text
        assert "validated manifest `paper_id`" in text
        assert "no bound article path" in text
        assert "--paper-link" not in text


def test_plan_parser_rejects_raw_sections_without_required_manifest() -> None:
    script = SKILL_DIR / "scripts" / "plan_glossary.py"
    result = subprocess.run(
        [sys.executable, str(script), "--propose", "--raw-sections", "paper.jsonl"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "the following arguments are required: --source-manifest" in result.stderr


def test_optimization_design_preserves_reviewed_candidates_and_forms() -> None:
    text = (SKILL_DIR / "references" / "optimization-design.md").read_text(
        encoding="utf-8"
    )
    review = _section(text, "### Semantic review", "## Selection and Generation")

    assert "only drop or reorder exact proposal candidates" in review
    assert "exact `term`" in review
    assert "ordered `surface_forms`" in review
    assert "may not merge aliases" in review
    assert "remove residual noise, merge aliases" not in review


def test_optimization_design_uses_config_only_writer_authority() -> None:
    text = (SKILL_DIR / "references" / "optimization-design.md").read_text(
        encoding="utf-8"
    )
    configuration = _section(text, "## First-use Configuration", "## Candidate Workflow")

    assert "Writer destination authority comes only from validated device config" in configuration
    assert "`--config-path` selects a config file" in configuration
    assert "reset and configure" in configuration
    assert "explicit path supplied for the current run overrides" not in configuration
    assert "transient destination override" not in configuration


def test_implementation_plan_step5_inventory_cli_lists_every_required_flag() -> None:
    text = (SKILL_DIR / "references" / "optimization-implementation-plan.md").read_text(
        encoding="utf-8"
    )
    task3 = _section(text, "### Task 3:", "### Task 4:")
    inventory_step = _section(
        task3,
        "- [ ] **Step 5: Add inventory CLI**",
        "- [ ] **Step 6:",
    )

    for flag in (
        "--terms",
        "--terms-dir",
        "--source-manifest",
        "--raw-sections",
        "--reviewed-shortlist",
        "--output",
    ):
        assert flag in inventory_step
    assert "triage JSON" in inventory_step
    assert "optional `--raw-sections`" in inventory_step


def test_implementation_plan_documents_authenticated_integration_flow() -> None:
    text = (SKILL_DIR / "references" / "optimization-implementation-plan.md").read_text(
        encoding="utf-8"
    )
    integration = _section(text, "### Task 6:", "### Task 7:")

    assert "proposal -> recorded review -> explicit selection -> triage -> authenticated inventory" in integration
    assert "config-backed writer -> authenticated linker" in integration
    for helper in (
        "inspect_selected_terms(",
        "write_glossary_entries(",
        "link_article_terms(",
    ):
        assert helper not in integration


def test_file_contract_writer_example_is_parseable_and_consistently_bound() -> None:
    text = (SKILL_DIR / "references" / "file-contract.md").read_text(encoding="utf-8")
    writer_section = text.split(
        "`write_glossary_terms.py` returns successful results", 1
    )[1]
    match = re.search(
        r"```json\r?\n(?P<payload>.*?)\r?\n```",
        writer_section,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group("payload"))

    proposal = payload["provenance"]["proposal"]
    review = payload["provenance"]["review"]
    result = payload["results"][0]
    candidate = proposal["candidates"][0]

    assert payload["paper_id"] == proposal["paper_id"] == review["paper_id"]
    assert payload["context"]["paper_id"] == payload["paper_id"]
    assert proposal["candidates"] == review["candidates"]
    assert review["reviewed_shortlist"] == [candidate]
    assert candidate["term"] == result["name"] == result["link_stem"] == "MoE"
    assert candidate["surface_forms"] == result["forms"] == ["MoE", "ＭｏＥ"]
    assert payload["provenance"]["selection_sha256"] == "sha256"
    assert payload["triage_sha256"] == "sha256"
    assert payload["mappings_sha256"] == "sha256"
