from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import asa_engine as engine


class InvoiceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mosaic-engine-")
        self.previous_db = engine.DB_PATH
        engine.DB_PATH = Path(self.temp.name) / "history.sqlite3"
        self.pos = engine.load_pos()

    def tearDown(self) -> None:
        engine.DB_PATH = self.previous_db
        self.temp.cleanup()

    def run_fixture(self, name: str, tolerance: float = 2.0):
        path = engine.ROOT / "data" / "invoices" / name
        return engine.process_pdf(path.read_bytes(), name, self.pos, tolerance)

    def test_prepared_route_fixtures(self) -> None:
        expected = {
            "happy_path.pdf":"APPROVE", "within_tolerance.pdf":"APPROVE",
            "possible_split_invoice.pdf":"REVIEW", "vendor_mismatch.pdf":"REJECT",
            "missing_po_reference.pdf":"REVIEW", "over_tolerance.pdf":"REVIEW",
            "missing_total.pdf":"REVIEW", "cents_mismatch.pdf":"REVIEW",
            "ambiguous_date.pdf":"REVIEW", "future_date.pdf":"REVIEW",
            "supplier_name_variant.pdf":"REVIEW", "pending_po.pdf":"REVIEW",
            "currency_unknown.pdf":"REVIEW", "image_only_scan.pdf":"REVIEW",
            "po_typo.pdf":"REVIEW",
        }
        for filename, route in expected.items():
            with self.subTest(filename=filename):
                _, result = self.run_fixture(filename)
                self.assertEqual(result["decision"], route)

    def test_ambiguous_locale_date_is_not_guessed(self) -> None:
        _, result = self.run_fixture("ambiguous_date.pdf")
        self.assertIn("AMBIGUOUS_INVOICE_DATE", result["flags"])

    def test_missing_currency_is_not_assumed_to_be_usd(self) -> None:
        invoice, result = self.run_fixture("currency_unknown.pdf")
        self.assertIsNone(invoice.currency)
        self.assertIn("CURRENCY_UNKNOWN", result["flags"])

    def test_po_typo_returns_explainable_lead_without_matching_it(self) -> None:
        _, result = self.run_fixture("po_typo.pdf")
        self.assertEqual(result["decision"], "REVIEW")
        self.assertEqual(result["flags"], ["PO_NOT_FOUND"])
        self.assertEqual(result["candidates"][0]["po_number"], "PO-1001")
        self.assertIn("reference_similarity", result["candidates"][0]["signals"])

    def test_policy_tolerance_changes_route_at_threshold(self) -> None:
        _, allowed = self.run_fixture("within_tolerance.pdf", tolerance=2.0)
        _, held = self.run_fixture("within_tolerance.pdf", tolerance=0.5)
        self.assertEqual(allowed["decision"], "APPROVE")
        self.assertEqual(held["decision"], "REVIEW")
        self.assertIn("OVER_PO_TOLERANCE", held["flags"])

    def test_cumulative_approved_billing_blocks_second_invoice(self) -> None:
        invoice, first = self.run_fixture("happy_path.pdf")
        self.assertEqual(first["decision"], "APPROVE")
        engine.save_run(invoice, first)
        _, second = self.run_fixture("cumulative_balance.pdf")
        self.assertEqual(second["decision"], "REVIEW")
        self.assertIn("CUMULATIVE_PO_OVERAGE", second["flags"])

    def test_same_file_is_duplicate_and_same_reference_other_supplier_is_review(self) -> None:
        invoice, result = self.run_fixture("happy_path.pdf")
        engine.save_run(invoice, result)
        _, duplicate = self.run_fixture("happy_path.pdf")
        self.assertIn("DUPLICATE", duplicate["flags"])
        collision = replace(invoice, vendor="Impostor Office Supply", sha256="different-file-digest")
        collision_result = engine.decide(collision, self.pos)
        self.assertEqual(collision_result["decision"], "REVIEW")
        self.assertIn("REFERENCE_COLLISION", collision_result["flags"])

    def test_summary_is_exact_and_history_projection_omits_source_text(self) -> None:
        invoice, result = self.run_fixture("happy_path.pdf")
        engine.save_run(invoice, result)
        _, review = self.run_fixture("missing_total.pdf")
        review_invoice, _ = self.run_fixture("missing_total.pdf")
        engine.save_run(review_invoice, review)
        summary = engine.get_summary()
        self.assertEqual((summary["total"], summary["approved"], summary["review"], summary["rejected"]), (2, 1, 1, 0))
        self.assertNotIn("raw_text", engine.get_runs()[0]["invoice"])
        self.assertEqual(len(summary["daily"]), 7)

    def test_case_workbench_keeps_notes_corrections_and_override_auditable(self) -> None:
        invoice, result = self.run_fixture("happy_path.pdf")
        run_id = engine.save_run(invoice, result)
        self.assertIsNotNone(result["po_balance"])
        self.assertEqual(result["po_balance"]["previously_approved"], 0)
        updated = engine.update_case(run_id, {
            "status":"IN_REVIEW", "assigned_to":"R. Carter", "note":"Confirm delivery receipt.",
            "decision_override":"REVIEW", "override_rationale":"Receiving evidence is not attached.",
            "correction":{"field":"invoice_number","value":"RB-77431-A","rationale":"Verified against the source header."},
        })
        self.assertEqual(updated["status"], "IN_REVIEW")
        self.assertEqual(updated["assigned_to"], "R. Carter")
        self.assertEqual(updated["decision_override"], "REVIEW")
        self.assertEqual(updated["override_rationale"], "Receiving evidence is not attached.")
        self.assertEqual(updated["result"]["decision"], "APPROVE")
        self.assertEqual(updated["corrections"]["invoice_number"]["corrected"], "RB-77431-A")
        self.assertEqual({event["kind"] for event in updated["events"]}, {"created","status","assignment","note","disposition","correction"})

    def test_override_requires_a_reason_and_rejects_unknown_fields(self) -> None:
        invoice, result = self.run_fixture("happy_path.pdf")
        run_id = engine.save_run(invoice, result)
        with self.assertRaisesRegex(ValueError, "Explain why"):
            engine.update_case(run_id,{"decision_override":"REJECT"})
        with self.assertRaisesRegex(ValueError, "supported field"):
            engine.update_case(run_id,{"correction":{"field":"sha256","value":"x","rationale":"because"}})

    def test_case_comparison_shows_changed_fields_for_same_invoice_reference(self) -> None:
        invoice, result = self.run_fixture("happy_path.pdf")
        engine.save_run(invoice,result)
        revised = replace(invoice,total=invoice.total+25,sha256="second-version-digest",source="revised_invoice.pdf")
        revised_result = engine.decide(revised,self.pos)
        revised_id = engine.save_run(revised,revised_result)
        case = engine.get_case(revised_id)
        self.assertIsNotNone(case["comparison"])
        self.assertEqual(case["comparison"]["changes"],[{"field":"total","before":invoice.total,"after":revised.total}])

    def test_legacy_history_schema_is_migrated_without_losing_rows(self) -> None:
        legacy = Path(self.temp.name) / "legacy.sqlite3"
        invoice_json = json.dumps({"invoice_number":"OLD-1", "vendor":"Northstar Office Supply", "po_number":"PO-1001", "total":1250})
        result_json = json.dumps({"decision":"APPROVE", "matched_po":{"po_number":"PO-1001"}})
        with sqlite3.connect(legacy) as connection:
            connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL, invoice_json TEXT NOT NULL, result_json TEXT NOT NULL)")
            connection.execute("INSERT INTO runs(created_at,filename,sha256,invoice_json,result_json) VALUES(?,?,?,?,?)", ("2026-11-02T12:00:00+00:00", "old.pdf", "old-hash", invoice_json, result_json))
        engine.DB_PATH = legacy
        engine.init_db()
        with sqlite3.connect(legacy) as connection:
            count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            indexed = connection.execute("SELECT po_number,decision FROM runs").fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(indexed, ("PO-1001", "APPROVE"))
        self.assertEqual(engine.get_runs()[0]["filename"], "old.pdf")


if __name__ == "__main__":
    unittest.main()
