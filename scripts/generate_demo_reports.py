"""Generate high-fidelity synthetic demo laboratory blood reports for live presentations.

Produces a diverse set of synthetic blood reports in data/demo_reports/ with accompanying
ground-truth JSON files, specifically designed for recruiter and live demo walkthroughs:
1. demo_01_clean_quest_lipid.pdf: Standard clean Quest lipid panel with mild hyperlipidemia.
2. demo_02_critical_apollo_panic.pdf: Apollo metabolic report with panic-level critical glucose (412 mg/dL) triggering urgency escalation.
3. demo_03_si_units_aiims.pdf: AIIMS India panel with SI units (mmol/L) demonstrating unit conversion & bilingual support.
4. demo_04_scanned_photo_labcorp.png: Simulated low-res photographed paper report demonstrating multi-tier vision OCR robustness.
5. demo_05_adversarial_bioreference.pdf: Adversarial hidden prompt injection payload demonstrating perimeter guardrails.

All reports use strictly synthetic non-patient data adhering to project guidelines.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evals.generator.report_generator import ReportGenerator

DEMO_DIR = ROOT_DIR / "data" / "demo_reports"


def generate_demo_dataset():
    """Build the recruiter demo report suite."""
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    gen = ReportGenerator(seed=1337)

    demo_scenarios = [
        {
            "case_id": "demo_01_clean_quest_lipid",
            "layout": "quest",
            "variation": "clean_pdf",
            "unit_system": "mg_dL",
            "value_profile": "all_abnormal",
            "analytes_count": 6,
            "description": "Clean standard Quest lipid panel with mild hyperlipidemia for primary baseline demo.",
        },
        {
            "case_id": "demo_02_critical_apollo_panic",
            "layout": "apollo",
            "variation": "clean_pdf",
            "unit_system": "mg_dL",
            "value_profile": "has_critical",
            "analytes_count": 5,
            "description": "Apollo metabolic report with panic-level critical glucose triggering urgency escalation banner.",
        },
        {
            "case_id": "demo_03_si_units_aiims",
            "layout": "aiims",
            "variation": "clean_pdf",
            "unit_system": "mmol_L",
            "value_profile": "mixed",
            "analytes_count": 5,
            "description": "AIIMS India panel with SI units (mmol/L) demonstrating bilingual English/Hindi output.",
        },
        {
            "case_id": "demo_04_scanned_photo_labcorp",
            "layout": "labcorp",
            "variation": "scanned_image",
            "unit_system": "mg_dL",
            "value_profile": "mixed",
            "analytes_count": 5,
            "description": "Simulated photographed paper report demonstrating multi-tier vision OCR robustness.",
        },
        {
            "case_id": "demo_05_adversarial_bioreference",
            "layout": "bioreference",
            "variation": "prompt_injection",
            "unit_system": "mg_dL",
            "value_profile": "mixed",
            "analytes_count": 5,
            "description": "Adversarial embedded instruction override demonstrating 100% perimeter guardrail neutralization.",
        },
    ]

    manifest = []
    print(f"[DEMO GENERATOR] Generating {len(demo_scenarios)} demonstration reports in {DEMO_DIR}...")

    for sc in demo_scenarios:
        report_path, gt_path = gen.generate_case(
            case_id=sc["case_id"],
            layout=sc["layout"],
            variation=sc["variation"],
            unit_system=sc["unit_system"],
            value_profile=sc["value_profile"],
            output_dir=DEMO_DIR,
            analytes_count=sc["analytes_count"],
        )

        gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
        critical_count = sum(1 for t in gt_data.get("tests", []) if "critical" in t.get("flag", "").lower())

        manifest_item = {
            "scenario": sc["case_id"],
            "description": sc["description"],
            "report_file": str(report_path.name),
            "ground_truth_file": str(gt_path.name),
            "layout": sc["layout"],
            "variation": sc["variation"],
            "unit_system": sc["unit_system"],
            "test_count": len(gt_data.get("tests", [])),
            "critical_count": critical_count,
        }
        manifest.append(manifest_item)
        print(f"  -> Generated {report_path.name} ({manifest_item['test_count']} tests, {critical_count} critical)")

    manifest_path = DEMO_DIR / "DEMO_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[DEMO GENERATOR] Demo suite manifest created at {manifest_path}")


if __name__ == "__main__":
    generate_demo_dataset()
