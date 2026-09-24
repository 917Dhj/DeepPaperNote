"""Shared paper-directory contract. Vendored unchanged by DeepPaperNote Connector.

Copyright (c) 2026 DeepPaperNote contributors. SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

SIDECAR = ".deeppapernote.json"


class ArchiveError(ValueError):
    def __init__(self, code: str, paths=()):
        self.code = code
        self.paths = [str(p) for p in paths]
        super().__init__(f"{code}: {', '.join(self.paths)}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


HASH = re.compile(r"[0-9a-f]{64}")
ARXIV = re.compile(r"(?:arxiv[:/\s]+|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
DOI = re.compile(r'10\.\d{4,9}/[^\s<>"]+', re.I)


def safe_path(root: Path, value: str) -> Path:
    raw = str(value)
    if (
        not raw
        or "\\" in raw
        or PureWindowsPath(raw).drive
        or Path(raw).is_absolute()
        or ".." in Path(raw).parts
    ):
        raise ArchiveError("unsafe_archive_path", [raw])
    target = root / raw
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ArchiveError("unsafe_archive_path", [target])
    return target


def normalized_title(value: str) -> str:
    return re.sub(r"[^\w]", "", value, flags=re.UNICODE).casefold()


def work_identity(record: dict) -> dict:
    contract = record.get("identity_contract", {}) or {}
    canonical = (
        contract.get("work_level_identity", {}) or record.get("work_level_identity", {}) or {}
    )
    data = {**record, **canonical}
    if isinstance(record.get("work"), dict):
        return copy.deepcopy(record["work"])
    identifiers = {}
    doi = DOI.search(
        " ".join(str(data.get(k) or "") for k in ("doi", "DOI", "paper_id", "source_url", "url"))
    )
    if doi:
        doi_value = doi.group().rstrip(".,;)").lower()
        if doi_value.startswith("10.48550/arxiv."):
            identifiers["arxiv"] = re.sub(r"v\d+$", "", doi_value.split("arxiv.", 1)[1])
        else:
            identifiers["doi"] = doi_value
    arxiv = str(data.get("arxiv_id") or data.get("arXiv") or "")
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", arxiv):
        identifiers["arxiv"] = re.sub(r"v\d+$", "", arxiv)
    else:
        match = ARXIV.search(
            " ".join(str(data.get(k, "")) for k in ("paper_id", "source_url", "url", "pdf_url"))
            + " "
            + arxiv
        )
        if match:
            identifiers["arxiv"] = re.sub(r"v\d+$", "", match[1])
    evidence = {"kind": "canonical_identity" if canonical else "supplied_metadata"}
    source_url = str(data.get("source_url") or data.get("url") or "")
    if source_url:
        evidence["source_url"] = source_url
    return {
        "title": str(data.get("title", "")),
        "identifiers": identifiers,
        "provenance": {key: [dict(evidence)] for key in identifiers},
    }


def record_work_evidence(work: dict, digest: str, observed: dict) -> None:
    """Keep identifier evidence separate from per-source PDF and note records."""
    ids = work.setdefault("identifiers", {})
    provenance = work.setdefault("provenance", {})
    for key, value in observed["identifiers"].items():
        if key in ids and ids[key] != value:
            raise ArchiveError("pdf_work_identity_mismatch")
        ids[key] = value
        evidence = {"kind": "pdf_first_page", "source_sha256": digest}
        entries = provenance.setdefault(key, [])
        if evidence not in entries:
            entries.append(evidence)


def same_work(left: dict, right: dict) -> bool:
    a, b = left.get("identifiers", {}), right.get("identifiers", {})
    shared = set(a) & set(b)
    return bool(shared) and all(a[k] == b[k] for k in shared)


def pdf_identity(path: Path) -> dict:
    try:
        import pymupdf as fitz

        with fitz.open(path) as doc:
            text = doc[0].get_text() if len(doc) else ""
    except (ImportError, RuntimeError, ValueError, IndexError) as exc:
        raise ArchiveError("pdf_identity_unavailable", [path]) from exc
    # Only the first page is identity evidence; references later in the PDF are not anchors.
    arxiv = ARXIV.search(text)
    doi = re.search(r"(?:doi\s*:\s*|doi\.org/)(10\.\d{4,9}/[^\s<>]+)", text, re.I)
    ids = {}
    if arxiv:
        ids["arxiv"] = re.sub(r"v\d+$", "", arxiv[1])
    if doi:
        ids.update(work_identity({"doi": doi[1]})["identifiers"])
    return {"identifiers": ids, "arxiv_id": arxiv[1] if arxiv else "", "text": text}


def verify_pdf(path: Path, record: dict, *, exact_version: bool = False) -> dict:
    observed = pdf_identity(path)
    expected = work_identity(record)
    a, b = observed["identifiers"], expected["identifiers"]
    if any(a[k] != b[k] for k in set(a) & set(b)):
        raise ArchiveError("pdf_work_identity_mismatch", [path])
    if not same_work(observed, expected):
        title = normalized_title(expected["title"])
        authors = (
            record.get("authors")
            or record.get("creators")
            or (record.get("identity_contract", {}).get("work_level_identity", {}) or {}).get(
                "authors"
            )
            or []
        )
        names = [
            str(x.get("lastName") or x.get("name") or "") if isinstance(x, dict) else str(x)
            for x in authors
        ]
        text = normalized_title(observed["text"])
        if (
            len(title) < 15
            or title not in text
            or not any(normalized_title(n) in text for n in names if n)
        ):
            raise ArchiveError("pdf_work_identity_unverified", [path])
    if exact_version:
        requested = source_details(record).get("arxiv_id", "")
        actual = observed.get("arxiv_id", "")
        if re.search(r"v\d+$", requested) and actual != requested:
            raise ArchiveError("pdf_version_mismatch", [path])
    return observed


def source_details(record: dict, pdf_path: Path | None = None) -> dict:
    manifestation = (
        record.get("source_manifestation", {})
        or (record.get("identity_contract", {}) or {}).get("source_manifestation", {})
        or {}
    )
    data = {**record, **manifestation}
    arxiv = str(data.get("arxiv_id") or data.get("arXiv") or "")
    match = ARXIV.search(
        " ".join(str(data.get(k, "")) for k in ("source_url", "pdf_url", "url", "paper_id"))
    )
    if match and not re.search(r"v\d+$", arxiv):
        arxiv = match[1]
    if pdf_path:
        try:
            observed = pdf_identity(pdf_path)
            arxiv = observed["arxiv_id"] or arxiv
        except ArchiveError:
            pass
    return {
        "arxiv_id": arxiv,
        "source_url": str(data.get("source_url") or data.get("url") or ""),
        "pdf_url": str(data.get("pdf_url") or ""),
    }


def read_record(directory: Path) -> dict | None:
    path = directory / SIDECAR
    if not path.exists() and not path.is_symlink():
        return None
    safe_path(directory, SIDECAR)
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        if (
            not isinstance(record, dict)
            or record.get("artifact_type") != "deeppapernote_paper_directory"
        ):
            raise ValueError()
        record = copy.deepcopy(record)
        if record.get("schema_version") == 1:
            digest = record["source_sha256"]
            record["sources"] = {
                digest: {
                    "notes": copy.deepcopy(record.get("notes", {})),
                    "note_stem": record["note_stem"],
                    "asset_subdir": "images",
                }
            }
            record["work"] = work_identity(record)
            record["work"]["provenance"] = {
                key: [{"kind": "legacy_record"}] for key in record["work"]["identifiers"]
            }
            record["schema_version"] = 2
            record.pop("source_sha256", None)
            record.pop("notes", None)
        if record.get("schema_version") != 2 or not isinstance(record.get("sources"), dict):
            raise ValueError()
        if not isinstance(record.get("work"), dict) or not isinstance(
            record["work"].get("identifiers"), dict
        ):
            raise ValueError()
        provenance = record["work"].setdefault("provenance", {})
        if not isinstance(provenance, dict):
            raise ValueError()
        for key, value in record["work"]["identifiers"].items():
            if not isinstance(value, str) or not value:
                raise ValueError()
            entries = provenance.setdefault(key, [{"kind": "legacy_record"}])
            if not isinstance(entries, list) or not entries:
                raise ValueError()
            for evidence in entries:
                if not isinstance(evidence, dict) or not isinstance(evidence.get("kind"), str):
                    raise ValueError()
                if evidence.get("source_sha256") and not HASH.fullmatch(
                    str(evidence["source_sha256"])
                ):
                    raise ValueError()
        if Path(record["note_stem"]).name != record["note_stem"]:
            raise ValueError()
        safe_path(directory, record["note_stem"])
        for digest, source in record["sources"].items():
            if (
                not HASH.fullmatch(digest)
                or not isinstance(source, dict)
                or not isinstance(source.get("notes"), dict)
            ):
                raise ValueError()
            if source.get("pdf_path"):
                safe_path(directory, source["pdf_path"])
            if source.get("note_stem"):
                if Path(source["note_stem"]).name != source["note_stem"]:
                    raise ValueError()
                safe_path(directory, source["note_stem"])
            if source.get("asset_subdir"):
                safe_path(directory, source["asset_subdir"])
            for language, note in source["notes"].items():
                if language not in ("en", "zh-CN") or not isinstance(note, dict):
                    raise ValueError()
                filename = note.get("filename", "")
                if Path(filename).name != filename or not filename.endswith(".md"):
                    raise ValueError()
                safe_path(directory, filename)
                if not HASH.fullmatch(str(note.get("note_sha256", ""))):
                    raise ValueError()
        return record
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchiveError("invalid_directory_record", [directory]) from exc


def new_record(title: str, note_stem: str, record: dict) -> dict:
    return {
        "artifact_type": "deeppapernote_paper_directory",
        "schema_version": 2,
        "title": title,
        "note_stem": note_stem,
        "work": work_identity(record),
        "sources": {},
    }


def source_stem(record: dict, digest: str, details: dict) -> str:
    previous = record["sources"].get(digest, {})
    if previous.get("note_stem"):
        return previous["note_stem"]
    if not record["sources"]:
        return record["note_stem"]
    version = re.search(r"v\d+$", str(details.get("arxiv_id", "")))
    label = "arxiv-" + version[0] if version else "source"
    return f"{record['note_stem']}.{label}-{digest[:12]}"


def register_source(record: dict, digest: str, details: dict) -> dict:
    if not HASH.fullmatch(digest):
        raise ArchiveError("invalid_source_hash")
    stem = source_stem(record, digest, details)
    source = record["sources"].setdefault(
        digest,
        {
            "notes": {},
            "note_stem": stem,
            "asset_subdir": "images" if not record["sources"] else f"images/{digest}",
        },
    )
    for key, value in details.items():
        if value and key not in ("notes", "note_stem", "asset_subdir"):
            source[key] = value
    return source


def write_record(directory: Path, record: dict) -> None:
    path = safe_path(directory, SIDECAR)
    fd, name = tempfile.mkstemp(prefix=SIDECAR + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def archive_lock(vault: Path):
    # ponytail: serialize short Vault writes; use directory locks if throughput requires it.
    path = safe_path(vault, ".deeppapernote.lock")
    with path.open("a+b") as stream:
        deadline = time.monotonic() + 15
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    if not stream.read(1):
                        stream.write(b"\0")
                        stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ArchiveError("archive_busy", [vault]) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def directory_candidates(vault: Path, record: dict, digest: str = "", name: str = "") -> list[dict]:
    work = work_identity(record)
    matches = []
    for directory in sorted(p for p in vault.rglob("*") if p.is_dir() and not p.is_symlink()):
        if not directory.resolve().is_relative_to(vault.resolve()):
            continue
        title_match = normalized_title(directory.name) in {
            normalized_title(name),
            normalized_title(work["title"]),
        } - {""}
        try:
            registry = read_record(directory)
        except ArchiveError:
            if title_match:
                matches.append(
                    {
                        "path": str(directory),
                        "confidence": "invalid",
                        "pdf_count": len(list(directory.glob("*.pdf"))),
                        "note_count": len(list(directory.glob("*.md"))),
                    }
                )
            continue
        verified = bool(
            registry and (digest in registry["sources"] or same_work(registry["work"], work))
        )
        if registry and normalized_title(registry.get("title", "")) == normalized_title(
            work["title"]
        ):
            title_match = True
        pdfs = [
            p
            for p in directory.iterdir()
            if p.suffix.lower() == ".pdf" and p.is_file() and not p.is_symlink()
        ]
        if not registry and not verified:
            for path in pdfs:
                if digest and sha256(path) == digest:
                    verified = True
                    break
                try:
                    if same_work(pdf_identity(path), work):
                        verified = True
                        break
                except ArchiveError:
                    continue
        if verified or title_match:
            matches.append(
                {
                    "path": str(directory),
                    "confidence": "verified" if verified else "candidate",
                    "pdf_count": len(pdfs),
                    "note_count": len(list(directory.glob("*.md"))),
                }
            )
    verified = [candidate for candidate in matches if candidate["confidence"] == "verified"]
    return verified or matches


def select_directory(candidates: list[dict], selected: str = "") -> Path | None:
    if selected:
        target = Path(selected).resolve()
        if target not in [Path(c["path"]).resolve() for c in candidates]:
            raise ArchiveError("selected_directory_not_candidate", [target])
        if (
            next(c for c in candidates if Path(c["path"]).resolve() == target)["confidence"]
            == "invalid"
        ):
            raise ArchiveError("invalid_directory_record", [target])
        return target
    if len(candidates) > 1:
        raise ArchiveError("multiple_source_directories", [c["path"] for c in candidates])
    if candidates and candidates[0]["confidence"] == "invalid":
        raise ArchiveError("invalid_directory_record", [candidates[0]["path"]])
    return Path(candidates[0]["path"]) if candidates else None


def admit_directory(directory: Path, record: dict, digest: str) -> dict:
    registry = read_record(directory)
    work = work_identity(record)
    if registry:
        if digest not in registry["sources"] and not same_work(registry["work"], work):
            raise ArchiveError("same_name_different_source", [directory])
        if any(
            registry["work"]["identifiers"][k] != work["identifiers"][k]
            for k in set(registry["work"]["identifiers"]) & set(work["identifiers"])
        ):
            raise ArchiveError("pdf_work_identity_mismatch", [directory])
    else:
        registry = new_record(record.get("title", directory.name), directory.name, record)
        for path in directory.iterdir():
            if path.name == ".DS_Store" or (
                path.name.startswith(".deeppapernote-") and path.suffix == ".part"
            ):
                continue
            if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".pdf":
                raise ArchiveError("unidentified_same_name_directory", [directory])
    for source_hash, source in registry["sources"].items():
        if source.get("pdf_path"):
            path = safe_path(directory, source["pdf_path"])
            if not path.is_file() or sha256(path) != source_hash:
                raise ArchiveError("archived_pdf_changed", [path])
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() != ".pdf":
            continue
        safe_path(directory, path.name)
        actual = sha256(path)
        if actual != digest and actual not in registry["sources"]:
            observed = verify_pdf(path, record)
            record_work_evidence(registry["work"], actual, observed)
        details = source_details(record if actual == digest else {}, path)
        details["pdf_path"] = path.name
        register_source(registry, actual, details)
    return registry


def find_source(
    vault: Path,
    record: dict,
    reference: str = "",
    selected_directory: str = "",
    selected_hash: str = "",
) -> dict | None:
    candidates = directory_candidates(vault, record)
    directory = select_directory(candidates, selected_directory)
    if directory is None:
        return None
    registry = admit_directory(directory, record, "")
    sources = []
    for digest, source in registry["sources"].items():
        if not source.get("pdf_path"):
            continue
        path = safe_path(directory, source["pdf_path"])
        if not path.is_file() or sha256(path) != digest:
            raise ArchiveError("archived_pdf_changed", [path])
        sources.append(
            {
                **source,
                "pdf_path": str(path),
                "source_sha256": digest,
                "target_directory": str(directory),
            }
        )
    if selected_hash:
        sources = [s for s in sources if s["source_sha256"] == selected_hash]
        if not sources:
            raise ArchiveError("selected_source_not_found", [directory])
    explicit = ARXIV.search(
        "arxiv:" + reference if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", reference) else reference
    )
    if explicit and re.search(r"v\d+$", explicit[1]):
        sources = [s for s in sources if s.get("arxiv_id") == explicit[1]]
    if not sources:
        if selected_hash:
            raise ArchiveError("selected_source_version_mismatch", [directory])
        return None
    if len(sources) > 1:
        versions = [
            re.fullmatch(r"(\d{4}\.\d{4,5})v(\d+)", str(s.get("arxiv_id", ""))) for s in sources
        ]
        if all(versions) and len({v[1] for v in versions}) == 1:
            latest = max(int(v[2]) for v in versions)
            sources = [s for s, v in zip(sources, versions) if int(v[2]) == latest]
        if len(sources) != 1:
            raise ArchiveError("ambiguous_archived_sources", [s["pdf_path"] for s in sources])
    return sources[0]


def archive_location() -> tuple[Path, str]:
    path = Path(
        os.environ.get("DEEPPAPERNOTE_CONFIG_PATH") or Path.home() / ".deeppapernote/config.json"
    ).expanduser()
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        vault = Path(config["obsidian_vault"]).expanduser()
        papers_dir = config["papers_dir"]
        if not vault.is_absolute() or not vault.is_dir():
            raise ValueError()
        safe_path(vault, papers_dir)
        return vault.resolve(), papers_dir
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArchiveError("shared_archive_configuration_required", [path]) from exc
