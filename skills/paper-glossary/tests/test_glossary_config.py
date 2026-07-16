from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from glossary_config import (
    configure_terms_dir,
    find_vault_root,
    load_config,
    resolve_terms_dir,
    validate_article,
)


INVALID_CONFIGURE_DESTINATIONS = (
    "vault-root",
    "normalized-root",
    "blank-child",
    "blank-component",
)


def _invalid_terms_dir(vault: Path, case: str) -> Path:
    if case == "vault-root":
        return vault
    if case == "normalized-root":
        return vault / "not-created" / ".."
    if case == "blank-child":
        return vault / "   "
    return vault / "   " / "Glossary"


def _tree_snapshot(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def test_configure_terms_dir_persists_nearest_vault_and_relative_subdir(
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    inner = outer / "research"
    (outer / ".obsidian").mkdir(parents=True)
    (inner / ".obsidian").mkdir(parents=True)
    terms_dir = inner / "book" / "术语"
    config_path = tmp_path / "device" / "config.json"

    payload = configure_terms_dir(terms_dir, config_path)

    assert payload == {
        "vault_root": str(inner.resolve()),
        "terms_subdir": str(Path("book") / "术语"),
    }
    assert terms_dir.is_dir()
    assert load_config(config_path) == payload
    assert resolve_terms_dir(payload) == terms_dir.resolve()


def test_configure_terms_dir_creates_a_missing_child_of_existing_vault(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "new" / "nested" / "术语"

    payload = configure_terms_dir(terms_dir, tmp_path / "config.json")

    assert terms_dir.is_dir()
    assert payload["vault_root"] == str(vault.resolve())
    assert payload["terms_subdir"] == str(Path("new") / "nested" / "术语")


def test_configure_terms_dir_reuses_an_existing_directory(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "existing-terms"
    terms_dir.mkdir()
    config_path = tmp_path / "config.json"

    payload = configure_terms_dir(terms_dir, config_path)

    assert load_config(config_path) == payload
    assert resolve_terms_dir(payload) == terms_dir.resolve()


def test_find_vault_root_returns_none_for_non_vault_path(tmp_path: Path) -> None:
    assert find_vault_root(tmp_path / "outside") is None


def test_configure_terms_dir_rejects_non_vault_path(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="inside an Obsidian vault"):
        configure_terms_dir(tmp_path / "outside" / "术语", tmp_path / "config.json")


@pytest.mark.parametrize("case", INVALID_CONFIGURE_DESTINATIONS)
@pytest.mark.parametrize("existing_config", [False, True], ids=["absent", "existing"])
def test_configure_terms_dir_rejects_invalid_child_without_config_mutation(
    tmp_path: Path, case: str, existing_config: bool
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "device" / "config.json"
    original = b'{"sentinel":"keep"}\r\n'
    if existing_config:
        config_path.parent.mkdir()
        config_path.write_bytes(original)
    before = _tree_snapshot(vault)

    with pytest.raises(SystemExit, match="real child"):
        configure_terms_dir(_invalid_terms_dir(vault, case), config_path)

    assert _tree_snapshot(vault) == before
    if existing_config:
        assert config_path.read_bytes() == original
    else:
        assert not config_path.exists()
        assert not config_path.parent.exists()


@pytest.mark.parametrize("case", INVALID_CONFIGURE_DESTINATIONS)
@pytest.mark.parametrize("existing_config", [False, True], ids=["absent", "existing"])
def test_configure_cli_rejects_invalid_child_without_config_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    existing_config: bool,
) -> None:
    from configure_glossary import main

    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "device" / "config.json"
    original = b'{"sentinel":"keep"}\r\n'
    if existing_config:
        config_path.parent.mkdir()
        config_path.write_bytes(original)
    before = _tree_snapshot(vault)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_glossary.py",
            "--terms-dir",
            str(_invalid_terms_dir(vault, case)),
            "--config-path",
            str(config_path),
        ],
    )

    with pytest.raises(SystemExit, match="real child"):
        main()

    assert _tree_snapshot(vault) == before
    if existing_config:
        assert config_path.read_bytes() == original
    else:
        assert not config_path.exists()
        assert not config_path.parent.exists()


def test_load_config_rejects_blank_subdirectory_component(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "vault_root": str(vault),
                "terms_subdir": str(Path("   ") / "Glossary"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Invalid paper-glossary config object"):
        load_config(config_path)


@pytest.mark.parametrize("vault_root", [".", "C:drive-relative"])
def test_load_config_rejects_relative_and_drive_relative_vault_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vault_root: str
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Glossary").mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"vault_root": vault_root, "terms_subdir": "Glossary"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(vault)

    with pytest.raises(SystemExit, match="Invalid paper-glossary config object"):
        load_config(config_path)


def test_load_config_returns_canonical_absolute_vault_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "vault_root": str(tmp_path / "nested" / ".." / "vault"),
                "terms_subdir": "Glossary",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded is not None
    assert loaded["vault_root"] == str(vault.resolve())


def test_validate_article_returns_path_and_hash_for_same_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "术语"
    article = vault / "papers" / "Paper.md"
    article.parent.mkdir()
    article.write_text("# Paper\n", encoding="utf-8")
    config = configure_terms_dir(terms_dir, tmp_path / "config.json")

    result = validate_article(article, config)

    assert result == {
        "article_path": str(article.resolve()),
        "article_sha256": hashlib.sha256(article.read_bytes()).hexdigest(),
    }


def test_validate_article_rejects_other_vault(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / ".obsidian").mkdir(parents=True)
    (second / ".obsidian").mkdir(parents=True)
    article = second / "Paper.md"
    article.write_text("# Paper\n", encoding="utf-8")
    config = configure_terms_dir(first / "术语", tmp_path / "config.json")

    with pytest.raises(SystemExit, match="same Obsidian vault"):
        validate_article(article, config)


def test_load_config_returns_none_before_first_use(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.json") is None


def test_resolve_terms_dir_rejects_missing_configured_paths(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)

    with pytest.raises(SystemExit, match="missing or invalid"):
        resolve_terms_dir(
            {"vault_root": str(vault), "terms_subdir": "missing"}
        )


def test_resolve_terms_dir_rejects_new_nearest_nested_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "research" / "terms"
    config = configure_terms_dir(terms_dir, tmp_path / "config.json")
    (terms_dir.parent / ".obsidian").mkdir()

    with pytest.raises(SystemExit, match="missing or invalid"):
        resolve_terms_dir(config)


def test_configure_cli_show_reset_and_validate(tmp_path: Path, monkeypatch, capsys) -> None:
    from configure_glossary import main

    config_path = tmp_path / "device" / "config.json"
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "术语"
    article = vault / "Paper.md"
    article.write_text("# Paper\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_glossary.py", "--show", "--config-path", str(config_path)],
    )
    main()
    show_result = json.loads(capsys.readouterr().out)
    assert isinstance(show_result.pop("elapsed_ms"), int)
    assert show_result == {
        "workflow_state": "needs_configuration"
    }

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_glossary.py",
            "--terms-dir",
            str(terms_dir),
            "--config-path",
            str(config_path),
        ],
    )
    main()
    configure_result = json.loads(capsys.readouterr().out)
    assert configure_result.pop("elapsed_ms") >= 0
    assert configure_result == {
        "vault_root": str(vault.resolve()),
        "terms_subdir": str(Path("术语")),
    }

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_glossary.py",
            "--validate-article",
            str(article),
            "--config-path",
            str(config_path),
        ],
    )
    main()
    validation = json.loads(capsys.readouterr().out)
    assert validation.pop("elapsed_ms") >= 0
    assert validation == {
        "terms_dir": str(terms_dir.resolve()),
        "article_path": str(article.resolve()),
        "article_sha256": hashlib.sha256(article.read_bytes()).hexdigest(),
    }

    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_glossary.py", "--reset", "--config-path", str(config_path)],
    )
    main()
    reset_result = json.loads(capsys.readouterr().out)
    assert reset_result.pop("elapsed_ms") >= 0
    assert reset_result == {"workflow_state": "reset"}
    assert not config_path.exists()
    assert terms_dir.is_dir()
    assert (vault / ".obsidian").is_dir()


def test_configure_cli_output_file_modes_emit_elapsed_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from configure_glossary import main

    config_path = tmp_path / "device" / "config.json"
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "terms"
    article = vault / "Paper.md"
    article.write_text("# Paper\n", encoding="utf-8")

    def run_mode(name: str, *arguments: str) -> dict:
        output = tmp_path / f"{name}.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "configure_glossary.py",
                *arguments,
                "--config-path",
                str(config_path),
                "--output",
                str(output),
            ],
        )
        main()
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(payload["elapsed_ms"], int)
        assert payload["elapsed_ms"] >= 0
        return payload

    show_result = run_mode("show", "--show")
    assert show_result["workflow_state"] == "needs_configuration"

    configure_result = run_mode("configure", "--terms-dir", str(terms_dir))
    assert configure_result["vault_root"] == str(vault.resolve())

    validation = run_mode("validate", "--validate-article", str(article))
    assert validation["article_sha256"] == hashlib.sha256(article.read_bytes()).hexdigest()

    reset_result = run_mode("reset", "--reset")
    assert reset_result["workflow_state"] == "reset"
    assert not config_path.exists()
