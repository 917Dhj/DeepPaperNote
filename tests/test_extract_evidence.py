from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from build_synthesis_bundle import bundle


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_EVIDENCE_SCRIPT = PROJECT_ROOT / "scripts" / "extract_evidence.py"


def test_extract_evidence_outputs_ablation_evidence(tmp_path: Path) -> None:
    input_payload = {
        "paper_id": "paper:test",
        "title": "Ablation Heavy Paper",
        "abstract": (
            "We propose a multimodal framework. The visual encoder extracts region features and sends them to a fusion module. "
            "Without the memory replay module, accuracy drops by 4.1 points, "
            "and training becomes unstable during the final stage."
        ),
    }
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(EXTRACT_EVIDENCE_SCRIPT), "--input", str(input_path), "--output", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    ablation_evidence = payload["evidence_pack"]["ablation_evidence"]
    mechanism_evidence = payload["evidence_pack"]["mechanism_evidence"]
    assert len(ablation_evidence) == 1
    assert "drops by 4.1 points" in ablation_evidence[0]["evidence"]
    assert mechanism_evidence
    assert payload["summary"]["ablation_signals"]
    assert payload["summary"]["mechanism_signals"]
    assert payload["summary"]["paper_type"] == "AI_method"


def test_bundle_exposes_ablation_evidence_and_new_contract_rules() -> None:
    synthesis = bundle(
        metadata={"title": "Mechanism Paper"},
        evidence_wrapper={
            "evidence_pack": {
                "mechanism_evidence": [
                    {
                        "evidence": "The encoder extracts audio tokens and sends them into the fusion module.",
                        "source_section": "method",
                        "page_hint": "p.4",
                    }
                ],
                "ablation_evidence": [
                    {
                        "evidence": "Removing the decoder causes a 2-point drop and unstable optimization.",
                        "source_section": "experiment",
                        "page_hint": "p.8",
                    }
                ]
            },
            "summary": {"ablation_signals": ["Removing the decoder causes a 2-point drop."]},
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    assert synthesis["evidence"]["mechanism"][0]["source_section"] == "method"
    assert synthesis["evidence"]["ablation"][0]["source_section"] == "experiment"
    planning_rules = synthesis["writing_contract"]["planning_rules"]
    formula_rules = synthesis["writing_contract"]["formula_rules"]
    self_review_rules = synthesis["writing_contract"]["self_review_rules"]
    mechanism_flow_contract = synthesis["writing_contract"]["mechanism_flow_contract"]

    assert any("### 机制流程" in rule for rule in planning_rules)
    assert any("工程解释" in rule for rule in formula_rules)
    assert any("ablation_evidence" in rule for rule in self_review_rules)
    assert mechanism_flow_contract["title"] == "机制流程"
