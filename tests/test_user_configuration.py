from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import user_configuration
from localization import SUPPORTED_OUTPUT_LANGUAGES, note_schema
from user_configuration import (
    ConfigurationWriteError,
    inspect_configuration,
    persist_preferences,
    resolve_preferences,
    user_config_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCRIPT = PROJECT_ROOT / "skills/deeppapernote/scripts/user_configuration.py"
ENVIRONMENT_SCRIPT = PROJECT_ROOT / "skills/deeppapernote/scripts/check_environment.py"


def test_user_config_path_honors_process_isolation_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_path = tmp_path / "isolated" / "config.json"
    monkeypatch.setenv("DEEPPAPERNOTE_CONFIG_PATH", str(isolated_path))

    assert user_config_path() == isolated_path


def test_first_use_requests_one_workspace_prompt_batch(tmp_path: Path) -> None:
    result = inspect_configuration(config_path=tmp_path / "config.json", environ={})

    assert result == {
        "state": "needs_input",
        "config_path": str(tmp_path / "config.json"),
        "affected_fields": ["output_language", "save_mode"],
        "prompt_fields": ["output_language", "save_mode"],
        "migration_candidates": {},
        "warnings": [],
    }


def test_workspace_configuration_ignores_inactive_obsidian_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "save_mode": "workspace",
                "obsidian_vault": "relative/missing",
                "papers_dir": "../unsafe",
            }
        ),
        encoding="utf-8",
    )

    result = inspect_configuration(config_path=path, environ={})

    assert result["state"] == "ready"
    assert result["affected_fields"] == []
    assert result["configuration"]["save_mode"] == "workspace"


def test_obsidian_configuration_requires_safe_existing_paths(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "output_language": "de",
                "save_mode": "obsidian",
                "obsidian_vault": "relative/missing",
                "papers_dir": "../unsafe",
            }
        ),
        encoding="utf-8",
    )

    result = inspect_configuration(config_path=path, environ={})

    assert result["state"] == "invalid"
    assert result["affected_fields"] == [
        "output_language",
        "obsidian_vault",
        "papers_dir",
    ]
    assert [issue["code"] for issue in result["issues"]] == [
        "invalid_enum",
        "missing_vault",
        "unsafe_path",
    ]


def test_inspection_does_not_probe_or_create_the_obsidian_destination(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    papers_dir = vault / "Research/Papers"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "save_mode": "obsidian",
                "obsidian_vault": str(vault),
                "papers_dir": "Research/Papers",
            }
        ),
        encoding="utf-8",
    )

    result = inspect_configuration(config_path=path, environ={})

    assert result["state"] == "ready"
    assert not papers_dir.exists()


def test_precedence_is_explicit_cli_process_then_user_without_persistence(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = '{"output_language":"zh-CN","save_mode":"workspace"}\n'
    path.write_text(original, encoding="utf-8")

    resolved = resolve_preferences(
        config_path=path,
        explicit_overrides={"output_language": "en"},
        cli_overrides={"output_language": "zh-CN", "save_mode": "obsidian"},
        environ={
            "DEEPPAPERNOTE_OUTPUT_LANGUAGE": "zh-CN",
            "DEEPPAPERNOTE_SAVE_MODE": "workspace",
        },
    )

    assert resolved["values"]["output_language"] == "en"
    assert resolved["sources"]["output_language"] == "explicit_request"
    assert resolved["values"]["save_mode"] == "obsidian"
    assert resolved["sources"]["save_mode"] == "cli"
    assert path.read_text(encoding="utf-8") == original


def test_partial_repair_requests_only_affected_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "obsidian"}),
        encoding="utf-8",
    )

    result = inspect_configuration(config_path=path, environ={})

    assert result["state"] == "needs_input"
    assert result["prompt_fields"] == ["obsidian_vault", "papers_dir"]


def test_preference_change_preserves_unknown_fields_and_is_read_back(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"output_language": "zh-CN", "save_mode": "workspace", "future_field": 7}
        ),
        encoding="utf-8",
    )

    result = persist_preferences(
        {"output_language": "en"}, config_path=path, environ={}
    )

    assert result["state"] == "ready"
    assert result["configuration"]["future_field"] == 7
    assert result["configuration"]["output_language"] == "en"
    assert result["warnings"] == ["Preserved unknown configuration fields: future_field"]


@pytest.mark.parametrize("payload", ["{broken", "[]"])
def test_invalid_configuration_requires_confirmed_replacement_and_keeps_backup(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ConfigurationWriteError, match="confirmed replacement"):
        persist_preferences(
            {"output_language": "zh-CN", "save_mode": "workspace"},
            config_path=path,
            environ={},
        )

    result = persist_preferences(
        {"output_language": "zh-CN", "save_mode": "workspace"},
        config_path=path,
        environ={},
        replace_invalid=True,
    )

    backups = list(tmp_path.glob("config.invalid-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == payload
    assert result["state"] == "ready"


def test_absent_configuration_reports_process_and_shell_migration_candidates(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    shell = tmp_path / ".zshrc"
    shell.write_text(
        'export DEEPPAPERNOTE_SAVE_MODE="obsidian"\n'
        f'export DEEPPAPERNOTE_OBSIDIAN_VAULT="{vault}"\n',
        encoding="utf-8",
    )

    result = inspect_configuration(
        config_path=tmp_path / "config.json",
        environ={"DEEPPAPERNOTE_OUTPUT_LANGUAGE": "en"},
        shell_paths=[shell],
    )

    assert result["state"] == "needs_input"
    assert result["migration_candidates"] == {
        "output_language": {"value": "en", "source": "process_environment"},
        "save_mode": {"value": "obsidian", "source": str(shell)},
        "obsidian_vault": {"value": str(vault), "source": str(shell)},
    }


def test_invalid_legacy_values_are_not_migration_candidates(tmp_path: Path) -> None:
    result = inspect_configuration(
        config_path=tmp_path / "config.json",
        environ={
            "DEEPPAPERNOTE_OUTPUT_LANGUAGE": "de",
            "DEEPPAPERNOTE_SAVE_MODE": "banana",
            "DEEPPAPERNOTE_OBSIDIAN_VAULT": "relative/missing",
            "DEEPPAPERNOTE_PAPERS_DIR": "../escape",
        },
        shell_paths=[],
    )

    assert result["migration_candidates"] == {}


def test_unknown_home_legacy_vault_is_not_a_migration_candidate(tmp_path: Path) -> None:
    shell = tmp_path / ".zshrc"
    shell.write_text(
        "DEEPPAPERNOTE_OBSIDIAN_VAULT=~definitely_no_such_user_xyz/vault\n",
        encoding="utf-8",
    )

    result = inspect_configuration(
        config_path=tmp_path / "config.json",
        environ={
            "DEEPPAPERNOTE_OBSIDIAN_VAULT": "~definitely_no_such_user_xyz/vault"
        },
        shell_paths=[shell],
    )

    assert result["state"] == "needs_input"
    assert result["migration_candidates"] == {}


def test_existing_configuration_never_reads_shell_candidates(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "workspace"}),
        encoding="utf-8",
    )
    missing_shell = tmp_path / "must-not-be-read"

    result = inspect_configuration(
        config_path=path,
        environ={"DEEPPAPERNOTE_OUTPUT_LANGUAGE": "en"},
        shell_paths=[missing_shell],
    )

    assert result["state"] == "ready"
    assert result["migration_candidates"] == {}


@pytest.mark.parametrize(
    ("payload", "code"), [("{broken", "malformed"), ("[]", "non_object")]
)
def test_inspector_distinguishes_malformed_and_non_object(
    tmp_path: Path, payload: str, code: str
) -> None:
    path = tmp_path / "config.json"
    path.write_text(payload, encoding="utf-8")

    result = inspect_configuration(config_path=path, environ={})

    assert result["state"] == "invalid"
    assert result["issues"][0]["code"] == code


def test_inspector_reports_unreadable_and_unwritable_as_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "workspace"}),
        encoding="utf-8",
    )
    original_read = user_configuration._read_configuration
    monkeypatch.setattr(
        user_configuration,
        "_read_configuration",
        lambda candidate: (None, "unreadable:permission denied"),
    )
    unreadable = inspect_configuration(config_path=path, environ={})
    assert unreadable["state"] == "blocked"
    assert unreadable["issues"][0]["code"] == "unreadable"

    monkeypatch.setattr(user_configuration, "_read_configuration", original_read)
    monkeypatch.setattr(user_configuration, "_path_is_writable", lambda candidate: False)
    unwritable = inspect_configuration(config_path=path, environ={})
    assert unwritable["state"] == "blocked"
    assert unwritable["issues"][0]["code"] == "unwritable"


def test_writability_uses_atomic_replace_parent_directory(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "workspace"}),
        encoding="utf-8",
    )
    checked: list[Path] = []

    def fake_access(candidate: Path, mode: int) -> bool:
        checked.append(Path(candidate))
        return True

    monkeypatch.setattr(user_configuration.os, "access", fake_access)

    assert inspect_configuration(config_path=path, environ={})["state"] == "ready"
    assert checked == [tmp_path]


def test_readback_mismatch_is_never_reported_as_saved(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "workspace"}),
        encoding="utf-8",
    )

    def corrupt_write(candidate_path: Path, configuration: object) -> None:
        candidate_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(user_configuration, "_atomic_write", corrupt_write)

    with pytest.raises(ConfigurationWriteError, match="readback"):
        persist_preferences({"output_language": "en"}, config_path=path, environ={})


def test_confirmed_migration_becomes_the_only_durable_source(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    shell = tmp_path / ".zshrc"
    shell.write_text(
        "export DEEPPAPERNOTE_OUTPUT_LANGUAGE=en\n"
        "export DEEPPAPERNOTE_SAVE_MODE=workspace\n",
        encoding="utf-8",
    )
    candidates = inspect_configuration(
        config_path=path, environ={}, shell_paths=[shell]
    )["migration_candidates"]

    persist_preferences(
        {field: candidate["value"] for field, candidate in candidates.items()},
        config_path=path,
        environ={},
    )
    shell.write_text(
        "export DEEPPAPERNOTE_OUTPUT_LANGUAGE=zh-CN\n",
        encoding="utf-8",
    )
    result = inspect_configuration(config_path=path, environ={}, shell_paths=[shell])

    assert result["state"] == "ready"
    assert result["configuration"]["output_language"] == "en"
    assert result["migration_candidates"] == {}


def test_public_and_agent_contracts_share_user_configuration_source_of_truth() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    skill = (PROJECT_ROOT / "skills/deeppapernote/SKILL.md").read_text(encoding="utf-8")
    contract = (
        PROJECT_ROOT / "skills/deeppapernote/references/user-configuration.md"
    ).read_text(encoding="utf-8")

    for public_doc in (readme, readme_zh):
        assert "~/.deeppapernote/config.json" in public_doc
        for name in user_configuration.ENV_FIELDS.values():
            assert name in public_doc
    assert "references/user-configuration.md" in skill
    assert skill.index("Resolve Run Overrides") < skill.index("inspect User Configuration")
    assert skill.index("inspect User Configuration") < skill.index("resolve the paper identity")
    assert "explicit request > CLI > current process environment > User Configuration" in contract
    assert "without reading User Configuration" in contract
    assert "scripts/user_configuration.py" in contract


def test_public_onboarding_covers_bilingual_configuration_and_run_overrides() -> None:
    public_docs = {
        "en": (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        "zh-CN": (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
    }

    for text in public_docs.values():
        for field in user_configuration.KNOWN_FIELDS:
            assert f"`{field}`" in text
        values = (
            *sorted(user_configuration.OUTPUT_LANGUAGES),
            *sorted(user_configuration.SAVE_MODES),
        )
        for value in values:
            assert f"`{value}`" in text
        for option in ("--language", "--save-mode", "--vault", "--papers-dir"):
            assert f"`{option}`" in text
        assert '"output_language": "zh-CN"' in text
        assert '"output_language": "en"' in text
        assert (
            "explicit request > CLI > current process environment > User Configuration"
            in text
        )
        assert "Configuration Prompt Batch" in text
        assert "Run Override" in text
        assert "Preference Change" in text
        assert "Formal Save" in text
        assert "`images/`" in text
        assert "unknown" in text.lower()
        for name in user_configuration.ENV_FIELDS.values():
            assert name in text

        field_values = {
            "output_language": set(user_configuration.OUTPUT_LANGUAGES),
            "save_mode": set(user_configuration.SAVE_MODES),
        }
        for field, expected in field_values.items():
            row = re.search(rf"\| `{field}` \| ([^|]+) \|", text)
            assert row is not None
            assert set(re.findall(r"`([^`]+)`", row.group(1))) == expected

        profile = text.split("### Output Language Profiles and Formal Save", 1)[-1]
        if profile == text:
            profile = text.split("### 输出语言 Profile 与 Formal Save", 1)[-1]
        assert profile != text
        for language in SUPPORTED_OUTPUT_LANGUAGES:
            schema = note_schema(language)
            section_positions = [
                profile.index(f"`{section}`")
                for section in schema["sections"].values()
            ]
            assert section_positions == sorted(section_positions)
            for label in schema["figure_labels"].values():
                assert f"`{label}`" in profile
            assert f"`{schema['mechanism_flow']}`" in profile

    assert "Generate this paper's note in English just this once" in public_docs["en"]
    assert "Generate this paper's note in Simplified Chinese just this once" in public_docs["en"]
    assert "Change my default output language to English" in public_docs["en"]
    assert "这篇论文仅本次用英文生成" in public_docs["zh-CN"]
    assert "这篇论文仅本次用中文生成" in public_docs["zh-CN"]
    assert "以后默认生成英文笔记" in public_docs["zh-CN"]


def test_canonical_configuration_reference_matches_machine_contract() -> None:
    skill = (PROJECT_ROOT / "skills/deeppapernote/SKILL.md").read_text(
        encoding="utf-8"
    )
    contract = (
        PROJECT_ROOT / "skills/deeppapernote/references/user-configuration.md"
    ).read_text(encoding="utf-8")

    for field in user_configuration.KNOWN_FIELDS:
        assert f"`{field}`" in contract
    values = (
        *sorted(user_configuration.OUTPUT_LANGUAGES),
        *sorted(user_configuration.SAVE_MODES),
    )
    for value in values:
        assert f"`{value}`" in contract
    for state in ("ready", "needs_input", "invalid", "blocked"):
        assert f"`{state}`" in contract
    assert (
        "explicit request > CLI > current process environment > User Configuration"
        in contract
    )
    assert "preserve" in contract.lower() and "unknown" in contract.lower()
    assert "Workspace mode" in contract and "preserve" in contract
    assert "before paper identity resolution" in contract
    assert "one canonical Skill" in skill
    assert "one pipeline" in skill
    assert "paper-local `images/`" in skill


def test_output_language_reference_matches_both_machine_schemas() -> None:
    contract = (
        PROJECT_ROOT / "skills/deeppapernote/references/output-language.md"
    ).read_text(encoding="utf-8")

    for language in SUPPORTED_OUTPUT_LANGUAGES:
        schema = note_schema(language)
        section_positions = []
        for section in schema["sections"].values():
            assert f"`{section}`" in contract
            section_positions.append(contract.index(f"`{section}`"))
        assert section_positions == sorted(section_positions)
        for label in schema["figure_labels"].values():
            assert label in contract
        assert schema["mechanism_flow"] in contract


def test_configuration_cli_keeps_semantic_failures_repairable(
    configured_user_home: Path,
) -> None:
    configured_user_home.write_text(
        json.dumps({"output_language": "zh-CN", "save_mode": "workspace"}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CONFIG_SCRIPT), "--set-save-mode", "obsidian"],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["state"] == "needs_input"
    assert payload["affected_fields"] == ["obsidian_vault", "papers_dir"]


def test_environment_report_survives_missing_user_configuration(
    tmp_path: Path,
) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_CONFIG_PATH"] = str(home / ".deeppapernote" / "config.json")
    result = subprocess.run(
        [sys.executable, str(ENVIRONMENT_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["user_configuration"]["state"] == "needs_input"
