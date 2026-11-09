# Domain Routing

Every paper directory sits in one domain folder directly under the papers root (Obsidian) or the workspace output root. You choose that folder; the save script only describes the existing domains and checks your choice. A paper whose existing directory admission reuses keeps that directory and its domain.

## Choosing

Preflight for a new paper directory without `--domain` stops with `domain_required` and a `domain_overview`:

- `source: domains_file`: the user's convention in `<Vault>/DeepPaperNote/domains.md` exists. Each domain carries its `definition`, `includes`, `excludes`, and `paper_count`. Folders the convention does not describe carry `sample_titles` instead.
- `source: folders`: there is no convention. Each domain carries `paper_count` and up to eight `sample_titles`.
- `on_disk` and `in_convention` show where the two disagree. A domain only in the convention is a valid choice; saving creates its folder.

Read the paper's title and abstract against every domain, and choose the one whose papers this paper belongs with. Judge a domain by what its papers are about, its definition or sample titles, never by its name alone; a folder named after a broad topic is a fit only when its papers are this paper's neighbours. When the convention exists, its `includes` and `excludes` decide; an `excludes` entry that names another domain sends the paper there. Rerun preflight with `--domain <name>`, and pass the same `--domain` to Formal Save.

## New Domains

Reuse is the default. Create a domain only when no existing domain's `includes` or sample titles cover the paper, and pass `--new-domain-reason` stating why each close candidate does not fit.

A new name is a specific research area at the same level as its siblings, such as `长视频理解` or `Mental-Health`. A name broader than an existing domain, such as `大模型`, `人工智能`, `Machine-Learning`, or `AI`, reuses the existing domain instead. In an empty library, name the first domain after this paper's specific research area.

New names must work as Obsidian tags: letters, digits, `_`, and `-` only, and not only digits. The Final user report names any domain created, with its reason.

## Domain Tag

The note's `tags` carry exactly one `papers/<domain>` tag, naming the saved domain with whitespace written as `_`. For a reused directory, the domain is its parent folder below the papers root. Formal Save refuses a note whose `papers/` tags differ; express topics with tags outside `papers/`.

## The Domains File

`<Vault>/DeepPaperNote/domains.md` is the user's classification convention, which the organize-wiki skill keeps with the user. DeepPaperNote only reads it:

```markdown
---
aliases: [领域分类]
---
# 领域分类

## 长视频理解

- 定义：理解长视频的模型、方法与基准。
- 收录：长视频问答、长视频基准、视频记忆机制。
- 不收录：短视频动作识别（去 计算机视觉）。
- 代表论文：[[LVBench]]、[[VideoAgent]]
```

Each `##` heading is a folder name. The labels `定义` / `Definition`, `收录` / `Includes`, `不收录` / `Excludes`, and `代表论文` / `Representative papers` are read in either language; other lines are ignored.
