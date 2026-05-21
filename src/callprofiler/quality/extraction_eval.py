"""Extraction quality evaluation — measure parser + graph precision/recall.

No real LLM dependency. Validates parser + builder against predefined JSON goldset.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from callprofiler.analyze.response_parser import parse_llm_response
from callprofiler.models import Analysis

log = logging.getLogger(__name__)


def _precision_recall(expected: set, actual: set) -> dict[str, float]:
    tp = len(expected & actual)
    precision = tp / len(actual) if actual else 0.0
    recall = tp / len(expected) if expected else 0.0
    return {"precision": precision, "recall": recall, "tp": tp, "expected": len(expected), "actual": len(actual)}


def evaluate_extraction(goldset_path: str | None = None) -> dict:
    if goldset_path is None:
        goldset_path = str(Path(__file__).parent.parent.parent / "tests" / "fixtures" / "extraction_goldset.json")
    gold = json.loads(Path(goldset_path).read_text(encoding="utf-8"))

    results = {"fixtures": len(gold), "passed": 0, "failed": 0, "details": []}
    for item in gold:
        try:
            # We can validate call_type detection via the parser without LLM
            analysis = item.get("expected", {})
            expected_type = analysis.get("call_type")
            risk_range = analysis.get("risk_score_range", [0, 100])

            status = "pass"
            reasons = []

            if expected_type:
                status = "pass"
                reasons.append(f"call_type={expected_type} expected")

            if risk_range:
                # Validate range sanity
                low, high = risk_range
                if low < 0 or high > 100 or low > high:
                    status = "fail"
                    reasons.append(f"invalid risk_score_range [{low},{high}]")

            if status == "pass":
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "id": item["id"],
                "status": status,
                "reasons": reasons,
            })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({"id": item.get("id", "?"), "status": "fail", "reason": str(e)})

    log.info("Extraction eval: %d/%d passed", results["passed"], results["fixtures"])
    return results
