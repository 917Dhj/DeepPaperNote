# Evidence-First Note Writing

Use this guide when the goal is to approach the quality of a hand-written research note rather than a template-filled summary.

## Core Rule

Do not write the finished note directly from:
- the title
- the abstract
- one or two extracted snippets
- fixed headings alone

## Source Manifest Bundle

The source manifest and bundle should answer:
- what type of paper this is
- which parts of the PDF were actually found
- where the raw source text lives
- which numbers matter
- which datasets, metrics, baselines, or cohorts matter
- which figures are method figures, data figures, and result figures
- which conclusions are about scale, transfer, cost, limitations, or practical value
- which central claims have source evidence and which boundaries the evidence cannot cross

In `DeepPaperNote`, use:
- `scripts/run_pipeline.py`
- `scripts/extract_source_text.py`
- `scripts/build_synthesis_bundle.py`

## Explicit Note Plan

Before drafting the final note, the agent should create an explicit short planning artifact rather than silently "thinking it through" and jumping straight to the final Markdown.

Require a compact and inspectable JSON plan that satisfies the generated bundle contract. The bundle is authoritative for required fields, allowed paper types, and grounding expectations; do not expose a long free-form chain-of-thought block.

The plan should state:
- the `paper_type` (and `positioning`, `survey_mode`, `secondary_type`, `secondary_host_section` where they apply), chosen as `paper-types.md` describes; the type fixes the middle sections, so `section_plan` has one entry per middle section plus `局限`
- `core_answers` for every core question of the type: an answer with `evidence_refs`, or `not_reported` with a reason
- the `workflow` steps when the type has one
- which sections need more technical depth
- which subsections deserve `###` headings
- which evidence feeds each section
- which 3 to 6 numbers matter most
- which comparisons are the real ones
- which central claims are supported by which source sections or pages
- what each central claim actually proves and does not prove
- which weak, negative, limiting, or explicitly unreported results constrain the conclusion
- one or two reusable takeaways and one or two follow-up questions or experiments, each specific to this paper and at least 20 characters long
- the user's research direction in `reader_research_direction`: the one stated in the request, verbatim; else the bundle's `research_memory.suggested_reader_research_direction` when its status is `ok`; else an empty string
- three to five `key_prior_work` items `{work, role}`: the prior works this paper builds on, with how it uses each (baseline, backbone model, data source, theoretical basis, method source)
- zero to eight `connections` `{target, relation, reason}` chosen from the bundle's `connection_candidates`; `target` copies a candidate's `target`, `relation` is a key of `writing_contract.connections_contract.relations`, and Grounding Lint rejects any target the bundle did not recall
- whether key formulas or complexity expressions need to appear in the final note

Good note plans often add paper-specific sections such as:
- `### 数据构建`
- `### 量表代理特征抽取`
- `### 训练细节`
- `### 关键洞察`
- `### 为什么结果不等于临床可用`

Recommended shape:

```json
{
  "output_language": "zh-CN",
  "paper_type": "method",
  "paper_type_rationale": "The paper proposes a model mechanism and evaluates it against baselines; the script suggestion was treated only as a hint.",
  "dominant_domain": "machine learning",
  "must_cover": [
    "失败状态如何被记录",
    "关键消融"
  ],
  "key_numbers": [
    "主结果提升 3.2 points",
    "训练成本降低 40%"
  ],
  "real_comparisons": [
    "against the strongest reported baseline"
  ],
  "central_claims": [
    {
      "claim": "The proposed mechanism improves multi-step tool use reliability.",
      "supporting_evidence": [
        {
          "section_id": "sec:experiments"
        },
        {
          "pages": [
            7,
            8
          ]
        }
      ],
      "what_it_actually_proves": "The reported benchmark settings show fewer unrecoverable tool errors than the named baseline.",
      "what_it_does_not_prove": "It does not prove robustness to arbitrary tools or production latency failures."
    }
  ],
  "claim_boundaries": [
    "The result is tied to the paper's tool set and benchmark distribution."
  ],
  "negative_or_limiting_results": [
    "The paper does not clearly report a failed external-tool setting."
  ],
  "mechanism_result_map": [
    "The state transition design explains the lower unrecoverable-error rate by preserving failed tool-call state for later repair."
  ],
  "comparative_positioning": [
    "Compared with answer-only baselines, the paper evaluates a mechanism that keeps intermediate failure states inspectable."
  ],
  "reuse_takeaways": [
    "Track tool failures as first-class state rather than hiding them in the final answer."
  ],
  "followup_questions": [
    "Does the same state logging still help when external tools are slow, missing, or adversarially noisy?"
  ],
  "key_prior_work": [
    {
      "work": "Yao et al. 2023. ReAct: Synergizing Reasoning and Acting in Language Models",
      "role": "基线"
    },
    {
      "work": "Schick et al. 2023. Toolformer: Language Models Can Teach Themselves to Use Tools",
      "role": "方法来源"
    },
    {
      "work": "Yang et al. 2018. HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering",
      "role": "数据来源"
    }
  ],
  "section_plan": [
    {
      "section": "背景与问题",
      "focus": "说明多步工具调用为什么会在中途失败后无法恢复，以及作者把它定义成什么问题",
      "subsections": [],
      "evidence_sources": [
        {
          "section_id": "sec:introduction"
        }
      ]
    },
    {
      "section": "现有方法的局限",
      "focus": "说明只看答案的方法为什么分不清证据不足和推理错误",
      "subsections": [],
      "evidence_sources": [
        {
          "section_id": "sec:introduction"
        }
      ]
    },
    {
      "section": "核心思路与挑战",
      "focus": "一句话讲清状态机思路，以及失败状态必须被后续步骤读取这一难点",
      "subsections": [],
      "evidence_sources": [
        {
          "section_id": "sec:method"
        }
      ]
    },
    {
      "section": "方法",
      "weight": "high",
      "focus": "按调用顺序讲清失败状态如何被记录、保留并在后续步骤里被读取和修复",
      "subsections": [
        "方法流程",
        "训练目标"
      ],
      "evidence_sources": [
        {
          "section_id": "sec:method"
        },
        {
          "pages": [
            4,
            6
          ]
        }
      ]
    },
    {
      "section": "实验证据",
      "focus": "对比最强基线的不可恢复错误率与成功率，用消融判断收益来自状态保留还是额外重试",
      "subsections": [
        "挑战—模块—证据表"
      ],
      "evidence_sources": [
        {
          "section_id": "sec:experiments"
        },
        {
          "section_id": "sec:ablation"
        }
      ]
    },
    {
      "section": "深度分析",
      "focus": "讨论机制在什么工具集合与延迟条件下成立，以及日志带来的代价",
      "subsections": [],
      "evidence_sources": [
        {
          "pages": [
            9
          ]
        }
      ]
    },
    {
      "section": "局限",
      "focus": "指出结论只覆盖论文的工具集合与基准分布，缺少慢速或缺失工具下的检验",
      "subsections": [],
      "evidence_sources": [
        {
          "section_id": "sec:limitations"
        }
      ]
    }
  ],
  "reader_research_direction": "",
  "connections": [
    {
      "target": "ReAct.zh-CN",
      "relation": "baseline",
      "reason": "本文把 ReAct 作为主要对照，并在同一批多跳问答任务上比较可追溯错误率。"
    }
  ],
  "positioning": "technique",
  "survey_mode": "",
  "secondary_type": "",
  "secondary_host_section": "",
  "core_answers": {
    "method.problem": {
      "answer": "多步工具调用中途失败后无法恢复，错误一路传到最终答案。",
      "evidence_refs": [
        {
          "section_id": "sec:introduction"
        }
      ]
    },
    "method.prior_gaps": {
      "answer": "只看答案的方法不记录失败调用，无法区分证据不足和推理错误。",
      "evidence_refs": [
        {
          "section_id": "sec:introduction"
        }
      ]
    },
    "method.key_idea": {
      "answer": "把每次调用写进可回溯的状态机；难点是失败状态要被后续步骤读取。",
      "evidence_refs": [
        {
          "section_id": "sec:method"
        }
      ]
    },
    "method.claim_evidence": {
      "answer": "状态保留的收益由去掉状态日志的消融支撑；重试次数没有单独控制。",
      "evidence_refs": [
        {
          "section_id": "sec:ablation"
        }
      ]
    },
    "method.comparison": {
      "not_reported": true,
      "reason": "论文只报告单次运行，没有误差条或显著性检验。"
    },
    "method.boundary_cost": {
      "answer": "只在论文的工具集合上验证，额外日志带来约 15% 的延迟。",
      "evidence_refs": [
        {
          "pages": [
            9
          ]
        }
      ]
    }
  },
  "workflow": [
    {
      "name": "推理",
      "steps": [
        {
          "step": "证据筛选",
          "input": "问题与候选证据",
          "operation": "过滤低置信证据",
          "output": "证据集合",
          "novel": false
        },
        {
          "step": "工具规划",
          "input": "证据集合与状态日志",
          "operation": "选择下一步调用并记录状态",
          "output": "调用记录",
          "novel": true
        },
        {
          "step": "失败修复",
          "input": "失败调用的状态",
          "operation": "回滚并重新规划",
          "output": "修复后的调用",
          "novel": true
        },
        {
          "step": "答案生成",
          "input": "完整状态日志",
          "operation": "结合日志输出结论",
          "output": "可追溯答案",
          "novel": false
        }
      ]
    }
  ]
}
```

`section_plan` must cover every required section. Each one needs evidence sources and a paper-specific `focus`. The bundle's `writing_contract.note_plan_contract.template` gives this shape with every value empty. Start from it and fill each value; Lint and Grounding reject the template while any value is still empty.

Before drafting from this plan, run `scripts/lint_grounding.py --note-plan ... --source-manifest ... --bundle-json ... --figure-decisions ... --output ...` and retain the resulting Grounding Lint JSON for Formal Save.

The plan should be short, structured, and directly useful for the final draft.

## Writing Layer

Only after the evidence bundle and explicit JSON `note_plan` exist should the model draft the final note.

Good final notes should:
- prioritize numbers and comparisons over generic summary sentences
- add paper-specific subsections when the evidence supports them
- avoid abstract-only rewriting
- explain why a figure or table matters, not just attach it
- separate “作者声称了什么” from “论文真正证明了什么”
- carry the plan's claim boundaries into the analysis-carrying middle section and `局限`
- explain the mechanism deeply enough that an engineer could re-explain or re-implement the main flow

## Minimum Quality Bar

If the note does not clearly contain:
- the most important numbers
- the most important comparison
- one paper-specific insight
- one honest limitation
- one technically detailed subsection
- and, when necessary, one key formula or formal expression

then the note is still too close to a template summary.
