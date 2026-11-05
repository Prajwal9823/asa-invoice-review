from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asa_engine as engine

EXPECTED = {
    "happy_path.pdf":"APPROVE",
    "cumulative_balance.pdf":"REVIEW",  # Evaluated after happy_path has been recorded.
    "within_tolerance.pdf":"APPROVE",
    "possible_split_invoice.pdf":"REVIEW",
    "vendor_mismatch.pdf":"REJECT",
    "missing_po_reference.pdf":"REVIEW",
    "over_tolerance.pdf":"REVIEW",
    "missing_total.pdf":"REVIEW",
    "cents_mismatch.pdf":"REVIEW",
    "ambiguous_date.pdf":"REVIEW",
    "future_date.pdf":"REVIEW",
    "supplier_name_variant.pdf":"REVIEW",
    "pending_po.pdf":"REVIEW",
    "currency_unknown.pdf":"REVIEW",
    "image_only_scan.pdf":"REVIEW",
    "po_typo.pdf":"REVIEW",
}
LABELS = ("APPROVE", "REVIEW", "REJECT")


def main() -> int:
    original_db = engine.DB_PATH
    outcomes: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory(prefix="mosaic-experiment-") as folder:
        engine.DB_PATH = Path(folder) / "experiment.sqlite3"
        pos = engine.load_pos()
        order = list(EXPECTED)
        order.remove("happy_path.pdf")
        order.remove("cumulative_balance.pdf")
        order = ["happy_path.pdf", "cumulative_balance.pdf", *order]
        for filename in order:
            pdf = engine.ROOT / "data" / "invoices" / filename
            invoice, result = engine.process_pdf(pdf.read_bytes(), filename, pos)
            outcomes.append((filename, EXPECTED[filename], result["decision"]))
            engine.save_run(invoice, result)
    engine.DB_PATH = original_db
    correct = sum(expected == predicted for _, expected, predicted in outcomes)
    matrix = {expected:{predicted:0 for predicted in LABELS} for expected in LABELS}
    for _, expected, predicted in outcomes:
        matrix[expected][predicted] += 1
    per_class = {}
    for label in LABELS:
        tp = matrix[label][label]
        predicted_count = sum(matrix[truth][label] for truth in LABELS)
        support = sum(matrix[label].values())
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision":round(precision, 3), "recall":round(recall, 3), "f1":round(f1, 3), "support":support}
    report = {
        "experiment":"Mosaic synthetic invoice routing benchmark",
        "scope":"Labeled prepared PDFs; one ordered two-invoice PO-balance sequence; no real-world accuracy claim.",
        "cases":len(outcomes), "route_accuracy":round(correct / len(outcomes), 3),
        "per_class":per_class, "confusion_matrix":matrix,
        "cases_detail":[{"file":name, "expected":expected, "actual":predicted, "pass":expected == predicted} for name, expected, predicted in outcomes],
    }
    print(json.dumps(report, indent=2))
    return 0 if correct == len(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
