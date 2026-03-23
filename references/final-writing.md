# Final Writing

The final note should not read like raw extracted evidence.

Use the structured artifacts as inputs:
- `metadata.json`
- `evidence_pack.json`
- `figure_plan.json`
- `synthesis_bundle.json`

Then draft the final note in natural language.

## Writing Priorities

1. explain the paper rather than quote it
2. distinguish research problem from task definition
3. explain the method or analysis flow in your own words
4. choose the most meaningful results rather than repeating every number
5. say what the paper does not prove
6. keep the note readable weeks later

## What Scripts Should Not Try To Fully Replace

Scripts are good at:
- resolution
- extraction
- formatting
- linting
- placeholder planning

Scripts are not enough on their own for:
- nuanced judgment
- identifying what is easy to misread
- deciding what the paper's real contribution is
- writing strong, natural Chinese analytical prose

The language model should do all of the following:
- infer the paper type from the evidence bundle
- make an internal note plan before drafting
- decide which sections need more weight
- decide where `###` subheadings are needed
- select the truly central results
- reconstruct the method or analysis flow
- write the final note in clean Chinese

## Final-Draft Standard

The note should feel like:
- a careful reading note
- not an abstract rewrite
- not a raw evidence dump
- not a benchmark table converted into bullets

The final Chinese note must also pass a language-cleanliness check:
- no half-English half-Chinese prose lines
- English is allowed only for stable proper nouns or citation metadata
- if the style gate fails, do not write the note into Obsidian yet

For non-trivial papers, the note should usually not stop at only broad `##` sections.
It should use meaningful `###` subheadings where they improve technical clarity.

Examples:
- `### 数据来源`
- `### 任务定义`
- `### 中间特征抽取`
- `### 训练细节`
- `### 哪些结果最重要`
- `### 哪些地方容易被误读`

## Figure Placeholders

Start from placeholders, not from extracted images.
The note should preserve the full figure/table structure even when image extraction is partial.

If the bundle contains candidate figure pages or candidate image files:
- use them as evidence for semantic matching
- prefer the candidate with the strongest caption/page-context agreement
- still make the final decision yourself rather than trusting the candidate ranking blindly

Final-note figure rules:
- keep the original paper numbering, such as `Fig. 1`, `Fig. 3`, `Table 2`
- do not rename them to `图 1`, `图 2` just because of note order
- if you replace a placeholder with a real image, keep the same paper figure id in the caption
- if an important figure cannot be confidently extracted, keep a placeholder with a short explanation
- text may be complete even when figures are partial; do not let missing images erase textual coverage
- complete the figure decision inside the same task as the note generation
- do not stop after the text draft and ask the user whether to continue with figures unless they explicitly asked for a staged workflow
- prefer a stable figure callout format in the final note:
  - `> [!figure] Fig. 3 ...`
  - `> 建议位置：...`
  - `> 放置原因：...`
  - `> 当前状态：...`
