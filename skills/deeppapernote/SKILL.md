---
name: deeppapernote
description: Generate a high-quality deep-reading note for a single paper and write it into an Obsidian-style vault. Use when the user gives a paper title, DOI, URL, arXiv ID, Zotero item, or local PDF and wants a polished Markdown note with strong structure, evidence-based analysis, and figure placeholders.
---

# DeepPaperNote

Turn one paper into a replication-grade deep-reading note and save it to the workspace or Obsidian target of the resolved configuration. Each run handles one paper. A rewrite of the abstract is never a finished note.

## Standard

The note reconstructs the paper's argument: the problem it solves, how the task is defined, the data or materials it uses, how the method or analysis works, which results matter most, what the paper does not prove, and why it is worth keeping.

Write as a top-tier researcher or algorithm engineer keeping a replication-oriented lab note, for a reader who follows Python, PyTorch, training loops, and evaluation logic. Keep the shared section structure and shift its emphasis by paper type: AI method, benchmark, clinical study, or humanities and social science.

These hold at every step:

- **Evidence-first:** `*_raw_sections.jsonl` and `*_source_manifest.json` are the canonical reading material. Finish only from inspected full-text evidence, never from the title, abstract, or headings alone.
- **Model-first:** scripts gather and structure evidence. You choose the paper type, emphasis, contributions, mechanism, limitations, and prose; script suggestions are hints.
- **Fail closed:** when the evidence cannot support a deep note, stop as Stop Conditions describes.
- **Placeholder-first figures:** every major figure and table starts as a placeholder. It becomes an image only after Visual Review accepts it and Formal Save materializes it. Image extraction is optional and never reduces textual coverage.

## Language Integrity Contract

After Configuration Readiness, resolve one `output_language` (`zh-CN` or `en`) and pass it as `--language` to every script. `source_manifest.language_hint` describes the source text only and never selects the note profile.

The value travels through Save Target Admission → Figure Plan → Figure/Table Decisions → Synthesis Bundle → Note Plan → Grounding Lint → Final Note Lint → Final Quality Review → Final Readability Review → Formal Save. Every artifact records it as `output_language`, and each script stops on a missing or mismatched value. Final Note Lint records `note_sha256`, so any edit after lint means rerunning it. Formal Save checks every binding before any save side effect. `references/output-language.md` describes the two profiles.

## Workflow

Run the steps in order. A step is complete at its **done when**, never because a partial artifact exists. At any point, `scripts/run_state.py status --workdir <run_directory> --prefix <run_prefix>` reports verified stages, stale artifacts, and the `next_action`; `references/run-state.md` explains how to bind the artifacts you write.

1. **Configuration Readiness.** Resolve Run Overrides from the explicit request, CLI, and process environment. Read User Configuration only for fields they leave unset; `references/user-configuration.md` covers admission, migration, repair, and Preference Changes. **Done when** the save mode, its target, and the output language are resolved and valid.
2. **Acquire.** `scripts/run_pipeline.py acquire --input <paper> --prefix <run_prefix>` resolves the identity, collects metadata, fetches the PDF, and extracts the raw source text, following Sources below. Without `--workdir` it picks a directory under `~/.deeppapernote/runs/` and prints `workdir=`; reuse that value in every later step, or pass a writable `--workdir` when a sandbox blocks the default. **Done when** the source manifest exists and is not `blocked`.
3. **Save Target Admission.** In Obsidian mode, run `scripts/write_obsidian_note.py --preflight` with the resolved title, `--language`, Vault, `--source-manifest`, and `--output <run_directory>/<run_prefix>_admission.json`. Its result is authoritative:

   | Result | Action |
   |---|---|
   | reuse of an existing directory | Use that directory and its domain. A verified PDF-only directory needs no confirmation. |
   | `same_language_note_exists` | Ask whether to overwrite the reported note, and say what its `user_notes` result means: `present` keeps the user's My Notes block (about `chars` characters) and regenerates everything else; `none` found no notes of the user's; `heading_missing` found no My Notes heading, so nothing can be kept. When `legacy_format` is true, add that the kept block predates the current note format and may be old model-written text. Edits elsewhere in the note are replaced. Carry its `existing_read_date`, when non-empty, into the new note's `read_date`. On yes, rerun with `--overwrite-existing-note --expected-existing-note-sha256 <reported_sha256>` and carry it to Formal Save. On no, stop without writing. |
   | several matching directories or sources | Ask for the selection as `references/paper-archive.md` describes, and carry it through Formal Save. |
   | any other conflict | Report it and stop. |

   Workspace mode skips this step and routes the domain normally. **Done when** an admitted result is saved.
4. **Prepare.** `scripts/run_pipeline.py prepare --workdir <run_directory> --prefix <run_prefix> --admission <admission.json>` (workspace mode omits `--admission`) extracts structure and PDF assets, plans figures, builds the complete figure/table decision table, and writes the synthesis bundle, all offline. It refuses to replace decisions that hold Visual Review work unless the user accepts repeating those reviews and you pass `--discard-reviews`. Rerun a failed phase whole. **Done when** the bundle exists.
5. **Visual Review and Figure/Table Decision Freeze.** Record a verdict for every `review_pending` item with `scripts/plan_figure_table_decisions.py review`, send any Figure/Table the note needs into review with `promote`, and drop a usable candidate the note has no use for with a recorded reason, as `references/figure-placement.md` describes. Every decision must satisfy `writing_contract.figure_table_contract`. **Done when** `scripts/plan_figure_table_decisions.py summary --decisions <decisions.json>` lists no `review_pending_labels`; its table gives each insert's embed.
6. **Note plan.** Read the bundle and the raw sections, choose the paper type, and fill every value of `writing_contract.note_plan_contract.template` to create a short JSON `note_plan` with the exact `output_language`. Set `reader_research_direction` to the research direction the request states, verbatim; when the request states none and `research_memory.status` is `ok`, copy `research_memory.suggested_reader_research_direction`; otherwise leave it empty. Fill `key_prior_work` with the three to five works this paper builds on, and put in `connections` only those `connection_candidates` from the bundle that truly relate to this paper, each with a relation key and a one-sentence reason. `references/evidence-first.md` shows a complete plan. **Done when** Grounding passes.
7. **Grounding.** `scripts/lint_grounding.py --note-plan <note_plan> --source-manifest <manifest> --bundle-json <bundle> --figure-decisions <decisions.json> --language <language> --output <grounding.json>`. **Done when** it reports no issue; keep its JSON for Formal Save.
8. **Draft.** Write the note from the plan, following Note Shape, as one Markdown file in UTF-8 without BOM and with LF line endings. **Done when** the complete draft is on disk.
9. **Final Note Lint.** `scripts/lint_note.py --input <note> --plan-file <note_plan> --language <language> --output <lint.json>`. **Done when** every reported `passes_*` gate is `true`. A failed style gate is normal for several rounds: fix the reported text and rerun. Each `zh-CN` mixed-language issue names the English it counted in `english_run` or `english_words`; translate that wording, or wrap a retained proper noun in backticks, keeping formulas inline and proper nouns intact. Escalate to the user only when the same failures repeat unchanged across several rounds.
10. **Final Quality Review and Final Readability Review.** Follow `references/final-quality-review.md` for the reviewer prompt, the recorded `final_quality_review`, the two-revision limit, and the `final_readability_review` receipt. A readability edit repeats Final Note Lint and a fresh quality review. **Done when** both reviews pass for the current note bytes.
11. **Formal Save.** Run `scripts/write_obsidian_note.py` with `--content-file`, `--plan-file`, `--lint-json`, `--grounding-lint-json`, `--source-manifest`, `--figure-decisions`, `--final-quality-review`, `--final-readability-review`, and any approved overwrite hash, each naming the exact file the linters and reviewers checked. It repeats admission, refuses missing, failed, or stale gates, refuses unresolvable `[[links]]`, and materializes each `insert` into the paper-local `images/` directory. **Done when** the save succeeds.

Both lint artifacts bind the plan through `note_plan_sha256`, and Grounding Lint also binds the source manifest and decisions. These are exact-byte hashes, so reformatting JSON invalidates them: rerun both linters after a plan change, Grounding Lint after a source or decision change, and Final Note Lint after a note edit.

| Save Target | Formal Save |
|---|---|
| `save_mode=obsidian` with a usable Vault | Save to that Vault. |
| `save_mode=obsidian` and the save fails | Keep the Vault target and recover within scope; otherwise report `blocked`, and do not switch to workspace. |
| `save_mode=workspace` | Save inside the workspace output root. |

Running `scripts/run_pipeline.py` without a phase performs both phases in workspace mode only; Obsidian mode needs Save Target Admission between them.

A normal request finishes in one run: text, figure decisions, image materialization, and save. Produce a text-only note only when the user asks for one.

## Sources

Prefer the strongest source in this order:

1. local PDF path given by the user
2. local Zotero item and local Zotero attachment if available
3. verified local Obsidian PDF for the accepted work and requested version
4. DOI and publisher metadata
5. arXiv or open-access PDF sources
6. Semantic Scholar or OpenAlex for metadata backfill

`acquire` checks the desktop library through the Zotero Local API first. Its `--zotero-mode` is `auto` by default and falls back to the web providers when Zotero has no match; `off` makes no Local API request, and `required` demands a Zotero match. An explicit Zotero key must resolve locally. A trusted JSON artifact or explicit local PDF stays authoritative and skips this lookup. A confident local-library hit outranks any title-only web match. When a library match exposes only an attachment key and filename, `scripts/locate_zotero_attachment.py` finds the PDF under Zotero storage. In Obsidian mode, a matching local archive is verified and reused before any download; `references/paper-archive.md` covers version and source selection and Connector handoff.

## Stop Conditions

Stop, report the blocked stage and the remaining stages, and ask for what would unblock it when:

- the paper identity is ambiguous, including several equally plausible local items: ask for a DOI, arXiv ID, or exact Zotero key
- no PDF is available after every supported acquisition path: local PDF, Zotero attachment, metadata `pdf_url`, direct PDF URL, arXiv or open-access sources, an accessible publisher PDF, DOI enrichment, and any other implemented fetch path
- the source manifest is `blocked` with `blocked_code: unreadable_text`: ask for an OCR version or another copy, since rerunning cannot fix it
- the PDF or evidence is too weak for a real deep note: ask for a better PDF, OCR, or other source material

When any other step fails, retry it or take a fallback this skill names. Otherwise stop as above. An abstract-only, provisional, or partial note is never the finished output.

## Note Shape

- Start with an Obsidian YAML properties block above the `#` title heading. Include `tags` with a `papers/<domain>` value and useful `aliases`; add `date`, `doi`, or `arxiv_id` when known, and omit unknown fields. Always include the fields of `writing_contract.frontmatter_contract`: `paper_type` matching the plan, `methods`, `datasets`, and `tasks` as lists of at most 5 central items, and `read_date` as `YYYY-MM-DD`. A list value that names a term in the bundle's `glossary_terms` is written as that term's `link`, copied verbatim; every other value is plain text. Formal Save refuses a frontmatter link that is not a glossary term note.
- Use real `#`, `##`, and `###` headings. The top-level sections are exactly `writing_contract.must_include_sections`, in that order. A non-trivial paper gets several meaningful `###` subsections in its technical sections.
- Core Information is a fixed metadata block holding only `writing_contract.core_info_fields`, in order. Analysis belongs in later sections.
- Abstract renders the original abstract faithfully in the configured language, translated in `zh-CN` mode, with no later evidence or judgment added.
- Contributions lists the paper's actual innovations and why each matters.
- A method, framework, or system paper gets the localized mechanism-flow subsection under its method section, usually 3 to 4 numbered steps that each name the input, the operation, and where the output goes.
- Give replication-grade detail: key settings and numbers, plus the central formulas, objectives, or complexity expressions as `$...$` or `$$...$$`. Write a central comparison of three or more systems, settings, tasks, datasets, metrics, or ablation rows as a compact Markdown table followed by its interpretation.
- Takeaways holds exactly the two subsections of `writing_contract.takeaways_contract`, one or two items each, and each item is one or two sentences: reusable ideas that name the paper's mechanism, where it transfers, and its precondition, then follow-up questions or experiments specific to this paper, at least one of which tests the paper's own claims or evidence. With a non-empty `reader_research_direction`, connect at least one transferable idea to that direction whenever a credible transfer exists, start every item that connects to it with `takeaways_contract.judgment_marker`, and say plainly when no credible transfer exists.
- Connections follows `writing_contract.connections_contract`: the in-vault subsection lists exactly the planned `connections` as `[[target|Title]]` entries with their relation labels, or its fixed empty statement; the key-prior-work subsection lists the planned `key_prior_work` as plain text. Never write the bibliography, and never write a `[[link]]` whose target is not a bundle candidate. Prose outside Connections carries no `[[link]]`; paper-glossary links terms in the body after saving. Formal Save refuses links it cannot find in the vault, and any link in workspace mode. A recommended next paper must already appear here. `references/obsidian-format.md` shows the format.
- My Notes is the last section and belongs to the user. The draft holds exactly `writing_contract.my_notes_contract.guidance` there. Formal Save keeps the user's own block from the note it replaces.
- A short paper still gets a complete deep note: spend the space on protocol details, ablations, limitations, and replication implications.
- The readability pass rewrites leftover language into natural prose in the configured language and keeps stable proper nouns. It adds no new facts or filler.

`references/final-writing.md` and `references/obsidian-format.md` hold the full writing and Markdown rules.

## Reporting

Say each phrase only when its condition holds:

| Phrase | Condition |
|---|---|
| `笔记已完成` | The workflow is complete through Formal Save. |
| `已生成草稿` | The draft exists, but lint, a review, or the save is pending. |
| `已通过校验` | Final Note Lint ran and passed. |
| `已保存到 Obsidian` | Formal Save succeeded. |

Lint is a floor, not polish: while the readability review is pending, say the draft passed script lint but has not finished its final language review. When a run stops early, name the current stage and the remaining stages.

Final user report:

- After a successful Formal Save, report in the user's conversation language, and derive every claim from current-run artifacts; the `summary` of `scripts/run_state.py status` carries these fields.
- Lead with the final note link or path, the save mode, and the actual saved domain, read from the note path under the configured papers root in Obsidian mode or the output root in workspace mode. When admission reused an existing directory, report that directory's existing domain.
- Then report, in order:
  1. the paper title and strongest verified identifier
  2. the Grounding Lint, Final Note Lint, Final Quality Review, and Final Readability Review results, plus the warning count
  3. the materialized and retained-placeholder figure/table counts, plus each dropped item with its reason from `figure_drops`
  4. whether the generated part of the saved note matches the Final Note Lint `note_sha256`
- When `reader_research_direction` came from `research_memory`, say in one line that the transferable ideas followed the user's research memory.
- When the save receipt's `glossary_followup.status` is `suggested`, suggest running paper-glossary on this paper and give its `source_manifest` and `note_path`; when `regenerated` is true, add that term links the glossary had added to the replaced note return only after that rerun. For any other status, say nothing about the glossary.
- When the save replaced an existing note, report the save receipt's `user_notes.status`: `preserved` kept the user's My Notes; `untouched` found none to keep; `heading_missing` found no My Notes heading. Only when `user_notes.legacy_format` is true, add that the kept block predates the current note format and may be old model-written text the user can delete.
- Add overwrite actions, preference changes, or user-relevant warnings only when they occurred.

## References

`SKILL.md` and the synthesis bundle carry a normal run. Read a reference only when its row applies:

| Reference | When |
|---|---|
| `references/user-configuration.md` | Configuration Readiness |
| `references/paper-archive.md` | existing Obsidian directories, local PDF versions, Connector handoff |
| `references/figure-placement.md` | Visual Review, promotion, drops, and placement |
| `references/run-state.md` | reading `run_state.py status` and binding artifacts |
| `references/final-quality-review.md` | Final Quality Review and Final Readability Review |
| `references/output-language.md` | language profiles, while drafting or debugging either language |
| `references/evidence-first.md` | a complete note plan example |
| `references/deep-analysis.md`, `references/final-writing.md` | a complex paper or a draft that is too shallow |
| `references/obsidian-format.md` | Markdown, vault, frontmatter, and Connections formatting |
| `references/note-quality.md`, `references/paper-types.md` | final review and paper-type adaptation |
| `references/metadata-sources.md` | incomplete metadata |
| `references/architecture.md` | repository maintenance |

## Environment

- The scripts need Python 3.10 or newer. When `python3` is older, use another interpreter of 3.10 or newer, such as `python3.12`, for the whole run; when none exists, stop and report the version found.
- Run `scripts/check_environment.py` only when a concrete dependency or integration problem blocks a step, and explain the required dependencies, optional enhancements, and downgrade behavior directly.
