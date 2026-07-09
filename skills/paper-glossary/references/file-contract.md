# Paper Glossary File Contract

## Inputs

`plan_glossary.py` accepts:

- `--source-manifest`: path to a JSON object, or an inline JSON object.
- `--raw-sections`: optional explicit JSONL path. If omitted, the manifest must contain `raw_sections_path`.
- `--terms`: selected terms as a JSON array, file path, comma-separated text, newline-separated text, or aliases separated by `|`.

Raw section records are JSONL objects. Records with `record_type` absent or equal to `section` are read. `kind: references` is excluded from evidence matching.

## Triage Output

`plan_glossary.py --terms ...` writes:

```json
{
  "status": "ok",
  "mode": "triage",
  "paper_id": "paper-id",
  "terms": [
    {
      "term": "MoE",
      "surface_forms": ["MoE"],
      "found_in_paper": true,
      "occurrences": 2,
      "routing": "anchor_only",
      "paper_anchors": [
        {
          "section_id": "sec:method",
          "title": "Method",
          "page_start": 3,
          "page_end": 5,
          "snippet": "..."
        }
      ]
    }
  ]
}
```

## Glossary Entry Input

`write_glossary_terms.py` expects:

```json
{
  "entries": [
    {
      "name": "KL 散度",
      "aliases": ["KL divergence", "相对熵"],
      "definition": "衡量两个概率分布差异的非对称度量。",
      "elaboration": "常用于把学生分布拉近教师分布。",
      "intuition": "把 Q 当作近似 P 时的信息损失。",
      "distinction": "不同于对称距离。",
      "confidence": "高",
      "occurrence": "方法 式(4)，第 3-6 页"
    }
  ]
}
```

Required fields for lint: `name`, `definition`, `confidence`, and one occurrence line linked to a paper note.
