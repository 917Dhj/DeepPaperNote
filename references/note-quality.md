# Note Quality

The note is high quality only if it satisfies most of the checks below.

## Minimum Bar

- It is not a paraphrase of the abstract.
- It distinguishes `research problem` from `task definition`.
- It explains how the method or analysis actually works.
- It reports the most meaningful results, not only the prettiest numbers.
- It includes at least one real limitation.
- It includes an explicit judgment about the paper's actual contribution.
- It includes at least one paper-specific technical subsection rather than only broad top-level sections.

## Structural Checks

The note should usually include:
- `核心信息`
- `一句话总结`
- `研究问题`
- `数据与任务定义`
- `方法主线`
- `关键结果`
- `深度分析`
- `局限`
- `我的笔记`

For non-trivial papers, it should usually also include multiple `###` subheadings inside:
- `数据与任务定义`
- `方法主线`
- `关键结果`
- `深度分析`

## Depth Checks

### Good signs

- The note explains the flow of information in the method.
- The note explains technical details with section-specific subheadings rather than one flat block.
- The note points out what the paper does not prove.
- The note identifies where labels, supervision, or evaluation may be weak.
- The note explains why the paper matters to later reading or research reuse.
- The note surfaces one paper-specific insight, not just generic praise.

### Bad signs

- It only repeats the introduction and abstract.
- It lists model names without explaining the pipeline.
- It copies metrics without noting the evaluation setting.
- It says the paper is innovative without locating the innovation.
- It uses generic limitations such as "future work can use more data" and nothing more specific.
- It flattens a technically rich paper into only `##` headings with no internal structure.

## Quality Gate

Fail closed if any of these are missing:
- method evidence
- result evidence
- a clear paper identity
- enough metadata to label the note responsibly

Also fail closed if:
- the final Chinese note still contains mixed-language prose lines
- English remains in full clauses rather than only stable proper nouns, model names, venues, URLs, or DOIs
- figure placeholders include untranslated caption sentences that read like raw extraction rather than note prose

Strong notes should also clearly contain:
- the most important numbers
- the most important comparison
- one paper-specific insight
- one honest limitation
