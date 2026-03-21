# Architecture

This skill should be implemented as:
- a reusable core workflow
- a thin Codex adapter

That separation keeps the project useful even if the execution environment changes later.

## Layer 1: Reusable Core

The reusable core includes:
- paper resolution logic
- metadata aggregation
- PDF acquisition strategy
- evidence extraction
- figure planning
- synthesis-bundle assembly
- note-quality checks
- Markdown note rendering constraints
- JSON contracts between stages

These pieces should live primarily in:
- `scripts/`
- `references/`
- `assets/`

The core should be agent-agnostic wherever possible.

## Layer 2: Codex Adapter

The Codex adapter includes:
- `SKILL.md`
- `agents/openai.yaml`
- trigger phrasing
- tool-selection instructions for the Codex environment
- commentary/final interaction style
- any Codex-specific Obsidian or MCP calling conventions
- local Zotero MCP preflight before network title resolution

This layer should stay thin.
Do not bury core business logic only inside `SKILL.md`.

## Design Rule

When adding a new behavior, ask:

1. Would another agent framework also need this behavior?
   - If yes, put it in the core.
2. Is this only about how Codex discovers or invokes the workflow?
   - If yes, put it in the adapter.

## What Belongs in Scripts

Put deterministic or repeated logic in scripts:
- normalization
- parsing
- metadata merge
- PDF discovery
- evidence-pack assembly
- synthesis-bundle assembly
- contract validation
- linting
- file writing

Do not put paper understanding into scripts:
- deciding the paper's real contribution
- choosing which result matters most
- reconstructing the true method chain
- writing the final deep-reading note prose

Those tasks belong to the language model after the deterministic bundle is prepared.

## What Belongs in References

Put durable reasoning guidance in references:
- what counts as a high-quality note
- how to adapt to paper types
- figure placement heuristics
- formatting rules
- source-priority rules

## What Belongs in SKILL.md

Keep only:
- when the skill should trigger
- the high-level workflow
- which scripts to use
- which references to read

## Portability Goals

A future non-Codex version should be able to reuse:
- the same scripts
- the same contracts
- the same note template
- the same evidence-first workflow

It should only need a different outer adapter.

## Anti-Patterns

Avoid:
- embedding essential contracts only in prompt text
- mixing platform-specific phrasing into script outputs
- writing natural-language-only intermediate artifacts when structured JSON is possible
- allowing note quality to depend on undocumented one-off prompt behavior
