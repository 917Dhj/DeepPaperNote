---
name: organize-wiki
description: Use when the user wants to organize their paper library (整理知识库): review or change its domain folders, write the domain convention DeepPaperNote follows, refile misplaced papers, fix papers/ tags, or undo the last reorganization.
---

# Organize Wiki

Keep the user's paper library in domain folders they agree with. You **propose**, with evidence from the library and their research memory; the user decides. Only a confirmed plan reaches the vault, only through `scripts/organize.py`, and only after the user has seen its preview.

`references/file-contract.md` defines the library layout, the domains file, the scan, the plan, and the log. Read it before step 3.

To undo the last reorganization, run `python3 scripts/organize.py undo --latest`, report what it restored or the conflicts it lists, and stop.

## 1. Read the library

Run `python3 scripts/scan_library.py --output <tmp>/scan.json`. It finds the vault through DeepPaperNote's configuration. On `needs_vault` or `not_a_vault`, ask the user once for their Obsidian vault folder and pass `--vault <path>` to every script.

**Done when** the scan reports `status: ok`.

## 2. Agree on the convention

The **convention** is the set of domains, each with a definition, what it includes, what it excludes and where that goes instead, and three to five representative papers. `domains_file.exists` picks the mode.

**Building** (no domains file): draft each existing domain's fields from its papers' titles and excerpts, then propose changes to the set:
- merge a domain holding one or two papers, or two domains whose papers mostly overlap;
- split a domain past about 25 papers that holds at least two clear sub-areas of five or more papers each;
- rename a domain whose name is broader or vaguer than what its papers are about;
- add a domain for papers no domain covers.

**Updating** (the file exists): every domain in it counts as confirmed. Ask only about change: papers no domain includes, papers a domain's own excludes rule out, domains grown past about 25 or shrunk to one or two, definitions that overlap.

In both modes:
- With `research_memory.exists`, split finer along the user's directions and keep not-focus topics coarse. Without it, say once that a research memory would fit the split to their research, and go on.
- The thresholds are guides; give the reason when you depart from them.
- Domains stay one level: a split makes sibling folders. A new name is a specific research area at the level of its siblings, written with letters, digits, `_`, and `-` only.

Interview in **rounds** of at most four numbered questions in the user's language. Each asks one decision, with your proposal and its evidence (paper counts and titles), worded so "yes" accepts it. Show the full convention draft once the rounds settle it.

**Done when** the user has confirmed the complete convention.

## 3. Plan the changes

Assign every paper to a domain of the convention by its title and excerpt; its current folder is weak evidence. Present the plan in groups, each item numbered with a one-line reason:

1. **Folder changes**: domains created, renamed, merged, or removed.
2. **Moves**: each misfiled paper, from and to.
3. **Tag fixes**: papers that stay put with `tag_status` `mismatch` or `multiple`. Moved papers get the same fix automatically. Notes without frontmatter stay untouched.
4. **Structure**: flatten each `nested_folder`, wrap each `loose_file` in its own paper folder, and move each `paper_at_root` into a domain. Report each `images_index` without changing it.
5. **Needs your judgment**: each paper you cannot place with confidence, asked as a question with your best guess.

The user accepts everything or rejects items by number. Write what they accepted as the plan JSON.

**Done when** every item is accepted or rejected and no question is open.

## 4. Preview, confirm, apply

Run `python3 scripts/organize.py preview --plan <plan.json>`. On `refused`, fix the plan for each error and rerun.

Show the user the summary counts, the moves, the domains file diff (the full text when it is new), and the warnings. Name any note outside the paper folder whose links will be rewritten.

After the user confirms, run `python3 scripts/organize.py apply --plan <plan.json> --expected-digest <plan_digest>`. A refusal because the library changed means rerunning preview and showing what differs before asking again. A lock refusal means DeepPaperNote is saving a note; retry once it finishes.

**Done when** apply reports `status: ok` with `verify.status: ok`, or the user declined. Report any issue `verify` lists.

## 5. Report

Give the log path, the counts of moved papers, fixed tags, and rewritten links, and the domains file path. Say that DeepPaperNote now follows the convention when it files a new paper, that the user can edit the domains file in Obsidian, and that "撤销上一次整理" / "undo the last reorganization" restores the library while the touched files stay unedited.
