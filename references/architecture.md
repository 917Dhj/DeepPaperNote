# Architecture

This skill should be implemented as:
- a reusable core workflow
- thin platform adapters

That separation keeps the project useful even if the host environment changes later.

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

## Layer 2: Platform Adapter Layer

A platform adapter can include:
- `SKILL.md`
- `agents/openai.yaml`
- other distribution-specific manifest files
- trigger phrasing
- tool-selection instructions for the host environment
- interaction-style notes
- host-specific Obsidian or local-library calling conventions

This layer should stay thin.
Do not bury core business logic only inside prompt text or distribution metadata.

## Design Rule

When adding a new behavior, ask:

1. Would another agent framework also need this behavior?
   - If yes, put it in the core.
2. Is this only about how one host environment discovers or invokes the workflow?
   - If yes, put it in the adapter layer.

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
- the non-negotiable workflow constraints that must remain visible at the entrypoint

## Portability Goals

A future adapter on another platform should be able to reuse:
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
