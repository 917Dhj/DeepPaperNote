"""Keep the user-owned My Notes section across note regeneration.

The My Notes section is the last top-level section of a note. Everything from
its heading line to the end of the file belongs to the user. A generated draft
holds only the standard guidance there; Formal Save swaps in the user's block
from the note it replaces.
"""

from __future__ import annotations

import hashlib
import re

from localization import note_schema


def _heading_re(language: str) -> re.Pattern[str]:
    heading = note_schema(language)["sections"]["my_notes"]
    return re.compile(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", flags=re.MULTILINE)


def split_user_notes(text: str, language: str) -> tuple[str, str] | None:
    """Return (generated part, user block), or None when the heading is absent."""
    match = _heading_re(language).search(text)
    if match is None:
        return None
    return text[: match.start()], text[match.start():]


def _block_body(block: str) -> str:
    _, _, body = block.partition("\n")
    return body


def is_default_block(block: str, language: str) -> bool:
    return _block_body(block).strip() == note_schema(language)["my_notes_guidance"]


def _content_chars(block: str) -> int:
    return sum(1 for ch in _block_body(block) if not ch.isspace())


def _normalize(text: str) -> str:
    return text.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")


def inspect_existing_user_notes(text: str, language: str) -> dict:
    """Describe the user content of a note about to be replaced, for the overwrite prompt."""
    parts = split_user_notes(_normalize(text), language)
    if parts is None:
        return {"status": "heading_missing", "chars": 0}
    block = parts[1]
    if is_default_block(block, language):
        return {"status": "none", "chars": 0}
    return {"status": "present", "chars": _content_chars(block)}


def merge_user_notes(
    draft_text: str,
    existing_text: str | None,
    language: str,
    *,
    recorded_saved_sha256: str = "",
) -> tuple[str, dict]:
    """Carry the user's My Notes block from the existing note into the reviewed draft.

    The block is treated as untouched, and the draft's guidance kept, when the
    existing note is byte-identical to what Formal Save last recorded or when the
    block is exactly the standard guidance. Any other block is kept as it is.
    """
    if existing_text is None:
        return draft_text, {"status": "no_existing_note", "chars": 0, "user_notes_sha256": ""}
    if recorded_saved_sha256 and (
        hashlib.sha256(existing_text.encode("utf-8")).hexdigest() == recorded_saved_sha256
    ):
        return draft_text, {"status": "untouched", "chars": 0, "user_notes_sha256": ""}
    existing_parts = split_user_notes(_normalize(existing_text), language)
    if existing_parts is None:
        return draft_text, {"status": "heading_missing", "chars": 0, "user_notes_sha256": ""}
    block = existing_parts[1]
    if is_default_block(block, language):
        return draft_text, {"status": "untouched", "chars": 0, "user_notes_sha256": ""}
    draft_parts = split_user_notes(draft_text, language)
    if draft_parts is None:
        raise ValueError(
            "The draft has no My Notes section, so the user's notes in the existing note "
            "cannot be kept; restore the section and rerun Final Note Lint."
        )
    if not block.endswith("\n"):
        block += "\n"
    return draft_parts[0] + block, {
        "status": "preserved",
        "chars": _content_chars(block),
        "user_notes_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
    }


def restore_generated_text(saved_text: str, draft_text: str, language: str) -> str:
    """Rebuild the reviewed draft from a saved note by swapping the user block back out."""
    saved_parts = split_user_notes(saved_text, language)
    draft_parts = split_user_notes(draft_text, language)
    if saved_parts is None or draft_parts is None:
        return saved_text
    return saved_parts[0] + draft_parts[1]
