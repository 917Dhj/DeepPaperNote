# DeepPaperNote Agent Guide

## Repository Purpose

DeepPaperNote is:

- a dual-stack Claude Code and Codex plugin repository
- designed for deep reading of one paper at a time
- intended to support both Claude Code and Codex
- focused on producing a high-quality Obsidian-oriented paper note

DeepPaperNote is not:

- a multi-paper review framework
- a shallow summary generator

## Canonical Sources

Use the following source-of-truth hierarchy when working in this repository:

- `skills/deeppapernote/SKILL.md` is the canonical workflow definition
- `skills/deeppapernote/scripts/` and `skills/deeppapernote/references/` are part of the reusable core
- `README.md` and `README.zh-CN.md` are user-facing documentation, not the canonical workflow
- `skills/deeppapernote/agents/openai.yaml` is the Codex adapter layer
- `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` are host manifests and should stay thin

Adapter layers should stay thin and should not redefine the workflow independently.

## Non-Negotiable Product Invariants

Future changes should preserve these product invariants:

- DeepPaperNote handles one paper at a time
- the workflow remains evidence-first
- required stages must not be silently skipped
- weak evidence should fail closed rather than being presented as a full deep read
- figure and table placeholder-first handling remains required
- lint plus final readability review remain required before completion
- Obsidian-first save semantics remain intact
- the paper-local `images/` directory remains part of the save protocol
- scripts remain deterministic support tools, while paper understanding and final note writing remain model-led

## Repository Structure

The repository is layered as follows:

- `skills/deeppapernote/SKILL.md` is the canonical workflow definition and the skill entrypoint for both Claude Code and other agents
- `CLAUDE.md` provides Claude Code project-level guidance and includes `AGENTS.md` via `@AGENTS.md`
- `.claude-plugin/plugin.json` identifies the Claude Code plugin
- `.codex-plugin/plugin.json` identifies the Codex plugin
- `skills/deeppapernote/references/` stores durable workflow and writing guidance
- `skills/deeppapernote/scripts/` implements the deterministic pipeline and support utilities
- `skills/deeppapernote/agents/openai.yaml` is the Codex adapter
- `README.md` and `README.zh-CN.md` are user-facing documentation

## Environment and Onboarding Boundary

- user installation, configuration, and onboarding belong primarily in `README.md` and `README.zh-CN.md`
- `skills/deeppapernote/scripts/check_environment.py` is a maintenance and troubleshooting utility
- DeepPaperNote should not reintroduce a separate public `doctor`, `setup`, or `start` skill surface

## Working Commands

Common commands for local validation and maintenance:

- install the core runtime dependency with `python3 -m pip install PyMuPDF`
- install the local development environment with `python3 -m pip install -e '.[dev]'`
- run the test suite with `python3 -m pytest -q`
- when checking environment-related problems, use `python3 skills/deeppapernote/scripts/check_environment.py`

## Verification Expectations

When making meaningful changes:

- run `python3 -m pytest -q`
- confirm adapters remain aligned with `skills/deeppapernote/SKILL.md`
- confirm no wrapper introduces a second conflicting workflow
- confirm legacy public pseudo-commands are not reintroduced
- if packaging files are touched, keep them syntactically valid
