from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import asa_engine as engine


class EnterpriseFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mosaic-enterprise-")
        self.previous_db = engine.DB_PATH
        engine.DB_PATH = Path(self.temp.name) / "history.sqlite3"
        self.pos = engine.load_pos()

    def tearDown(self) -> None:
        engine.DB_PATH = self.previous_db
        self.temp.cleanup()

    def test_three_way_match_quantity_mismatch_detected(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "quantity_mismatch.pdf"
        invoice, result = engine.process_pdf(path.read_bytes(), "quantity_mismatch.pdf", self.pos)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("GRN_QUANTITY_MISMATCH", result["flags"])
        tw = result["three_way_match"]
        self.assertEqual(tw["status"], "QUANTITY_MISMATCH")
        self.assertTrue(tw["has_quantity_mismatch"])
        self.assertEqual(tw["quantity_variance"], 2.0)
        self.assertEqual(len(tw["lines"]), 1)
        self.assertEqual(tw["lines"][0]["line_status"], "QTY_EXCEEDS_GRN")

    def test_three_way_match_happy_path(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        invoice, result = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        self.assertEqual(result["decision"], "APPROVE")
        tw = result["three_way_match"]
        self.assertEqual(tw["status"], "MATCHED")
        self.assertFalse(tw["has_quantity_mismatch"])
        self.assertFalse(tw["has_price_mismatch"])
        self.assertGreaterEqual(len(tw["lines"]), 2)

    def test_risk_scoring_engine_produces_transparent_factors(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "quantity_mismatch.pdf"
        _, result = engine.process_pdf(path.read_bytes(), "quantity_mismatch.pdf", self.pos)
        risk = result["risk_engine"]
        self.assertIsInstance(risk["score"], int)
        self.assertIn(risk["level"], {"LOW", "MODERATE", "HIGH", "CRITICAL"})
        self.assertTrue(len(risk["factors"]) > 0)
        # Verify factor structure
        first_factor = risk["factors"][0]
        self.assertIn("title", first_factor)
        self.assertIn("why_it_matters", first_factor)
        self.assertIn("evidence", first_factor)
        self.assertIn("points", first_factor)
        self.assertIn("recommendation", first_factor)

    def test_vendor_intelligence_lookup(self) -> None:
        vendors = engine.load_vendors()
        self.assertGreaterEqual(len(vendors), 5)
        northstar = engine.get_vendor_by_name("Northstar Office Supply")
        self.assertIsNotNone(northstar)
        self.assertEqual(northstar["verification_status"], "VERIFIED")
        self.assertIn("bank_details", northstar)
        self.assertTrue(northstar["bank_details"]["verified"])

    def test_ai_assistant_grounded_response(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "quantity_mismatch.pdf"
        invoice, result = engine.process_pdf(path.read_bytes(), "quantity_mismatch.pdf", self.pos)
        case_id = engine.save_run(invoice, result)

        response = engine.ask_assistant(case_id, "Why was this invoice flagged?")
        self.assertIn("answer", response)
        self.assertIn("citations", response)
        self.assertIn("suggested_followups", response)
        self.assertIn("GRN", response["answer"].upper())

    def test_case_priority_and_resolution_reason(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        invoice, result = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        case_id = engine.save_run(invoice, result)

        updated = engine.update_case(case_id, {
            "status": "ESCALATED",
            "priority": "HIGH",
            "resolution_reason": "Escalated for senior review"
        })
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "ESCALATED")
        self.assertEqual(updated["priority"], "HIGH")
        self.assertEqual(updated["resolution_reason"], "Escalated for senior review")

    def test_summary_includes_financial_metrics(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        invoice, result = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        engine.save_run(invoice, result)

        summary = engine.get_summary()
        self.assertIn("total_invoiced_value", summary)
        self.assertIn("discrepancies_amount", summary)
        self.assertIn("vendor_spending", summary)
        self.assertIn("exception_distribution", summary)
        self.assertGreater(summary["total_invoiced_value"], 0)

    def test_seed_database_populates_curated_demo_cases(self) -> None:
        engine.seed_database(engine.DB_PATH)
        summary = engine.get_summary()
        runs = engine.get_runs(limit=20)
        self.assertEqual(len(runs), 6)
        open_cases = [r for r in runs if r["status"] != "RESOLVED"]
        resolved_cases = [r for r in runs if r["status"] == "RESOLVED"]
        self.assertEqual(len(open_cases), 3)
        self.assertEqual(len(resolved_cases), 3)
        self.assertGreater(summary["total_invoiced_value"], 0)

    def test_session_workspace_isolation(self) -> None:
        db_a = engine.get_session_db_path("test_session_alpha_1")
        db_b = engine.get_session_db_path("test_session_beta_2")
        try:
            self.assertTrue(db_a.exists())
            self.assertTrue(db_b.exists())
            engine.seed_database(db_a)
            engine.seed_database(db_b)
            # Mutate session A
            engine.update_case(2, {"status": "RESOLVED", "resolution_reason": "Cleared by reviewer in session A"}, db_a)
            case_a = engine.get_case(2, db_a)
            case_b = engine.get_case(2, db_b)
            self.assertEqual(case_a["status"], "RESOLVED")
            self.assertEqual(case_b["status"], "IN_REVIEW")
        finally:
            db_a.unlink(missing_ok=True)
            db_b.unlink(missing_ok=True)

    def test_extraction_textual_dates_and_confidence(self) -> None:
        parsed_iso, ambig1 = engine._parse_date("28-Oct-2026")
        self.assertEqual(parsed_iso, "2026-10-28")
        self.assertFalse(ambig1)

        parsed_text, ambig2 = engine._parse_date("October 28, 2026")
        self.assertEqual(parsed_text, "2026-10-28")
        self.assertFalse(ambig2)

        # Ambiguous numeric date
        _, ambig3 = engine._parse_date("05/06/2026")
        self.assertTrue(ambig3)

        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, _ = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        self.assertGreaterEqual(inv.field_confidence.get("invoice_number", 0), 0.95)
        self.assertGreaterEqual(inv.field_confidence.get("total", 0), 0.95)
        self.assertGreaterEqual(inv.field_confidence.get("line_items", 0), 0.95)

    def test_fuzzy_vendor_duplicate_detection(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, res = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        engine.save_run(inv, res)

        # Minor company name variant with exact same invoice number
        fuzzy_dup_inv = engine.Invoice(
            invoice_number=inv.invoice_number,
            invoice_date=inv.invoice_date,
            vendor="Northstar Office Supplies",  # Variant of 'Northstar Office Supply'
            po_number=inv.po_number,
            total=inv.total,
            currency=inv.currency,
            subtotal=inv.subtotal,
            tax=inv.tax,
            source="duplicate_variant.pdf",
            sha256="different-sha256-hash-value-01",
            raw_text=inv.raw_text
        )
        dup_result = engine.decide(fuzzy_dup_inv, self.pos)
        self.assertEqual(dup_result["decision"], "REJECT")
        self.assertIn("DUPLICATE", dup_result["flags"])

    def test_suspected_duplicate_billing_detection(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, res = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        engine.save_run(inv, res)

        # Different invoice number, same vendor, same amount, within 5 days
        rebilled_inv = engine.Invoice(
            invoice_number="NS-2026-999-NEW",
            invoice_date="2026-10-31",
            vendor=inv.vendor,
            po_number=inv.po_number,
            total=inv.total,
            currency=inv.currency,
            subtotal=inv.subtotal,
            tax=inv.tax,
            source="rebilled.pdf",
            sha256="third-distinct-sha256-hash",
            raw_text="Rebilled invoice text"
        )
        suspected = engine.find_suspected_duplicate_billing(rebilled_inv)
        self.assertIsNotNone(suspected)
        self.assertEqual(suspected["total"], inv.total)

        anomalies = engine.detect_anomalies(rebilled_inv)
        self.assertTrue(any(a["id"] == "SUSPECTED_DUPLICATE_BILLING" for a in anomalies))

    def test_line_item_math_mismatch_validation(self) -> None:
        inv = engine.Invoice(
            invoice_number="INV-LINE-ERR",
            invoice_date="2026-10-28",
            vendor="Northstar Office Supply",
            po_number="PO-1001",
            total=1250.0,
            currency="USD",
            subtotal=1150.0,
            tax=100.0,
            source="err.pdf",
            sha256="hash-err-1",
            raw_text="Sample text",
            line_items=[
                {"line_number": 1, "sku": "FUR-CH-01", "description": "Chair", "quantity": 1, "unit_price": 500.0, "total": 500.0}
                # Total of lines is 500, but subtotal is declared as 1150!
            ]
        )
        result = engine.decide(inv, self.pos)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("LINE_ITEM_MATH_MISMATCH", result["flags"])

    def test_due_date_precedes_invoice_validation(self) -> None:
        inv = engine.Invoice(
            invoice_number="INV-DATE-ERR",
            invoice_date="2026-10-28",
            due_date="2026-10-15",  # Due date is earlier than invoice date
            vendor="Northstar Office Supply",
            po_number="PO-1001",
            total=1250.0,
            currency="USD",
            subtotal=1150.0,
            tax=100.0,
            source="err2.pdf",
            sha256="hash-err-2",
            raw_text="Sample text",
            line_items=[
                {"line_number": 1, "sku": "FUR-CH-01", "description": "Chair", "quantity": 10, "unit_price": 75.0, "total": 750.0},
                {"line_number": 2, "sku": "FUR-DK-04", "description": "Desk", "quantity": 4, "unit_price": 100.0, "total": 400.0}
            ]
        )
        result = engine.decide(inv, self.pos)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("DUE_DATE_PRECEDES_INVOICE", result["flags"])

    def test_stale_invoice_date_validation(self) -> None:
        inv = engine.Invoice(
            invoice_number="INV-STALE-01",
            invoice_date="2024-01-15",  # Over 2 years old
            vendor="Northstar Office Supply",
            po_number="PO-1001",
            total=1250.0,
            currency="USD",
            subtotal=1150.0,
            tax=100.0,
            source="stale.pdf",
            sha256="hash-err-3",
            raw_text="Sample text"
        )
        result = engine.decide(inv, self.pos)
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("STALE_INVOICE_DATE", result["flags"])

    def test_statistical_anomaly_detection_signals(self) -> None:
        # 1. Round amount anomaly on industrial supplier
        round_inv = engine.Invoice(
            invoice_number="INV-RND-1",
            invoice_date="2026-10-28",
            vendor="Apex Industrial Supplies",
            po_number="PO-1006",
            total=2000.0,
            currency="USD",
            subtotal=2000.0,
            tax=0.0,
            source="rnd.pdf",
            sha256="hash-rnd",
            raw_text="Sample text"
        )
        anomalies1 = engine.detect_anomalies(round_inv)
        self.assertTrue(any(a["id"] == "ROUND_AMOUNT_ANOMALY" for a in anomalies1))

        # 2. Weekend invoice date (2026-11-01 was a Sunday)
        weekend_inv = engine.Invoice(
            invoice_number="INV-WKD-1",
            invoice_date="2026-11-01",
            vendor="Apex Industrial Supplies",
            po_number="PO-1006",
            total=1500.0,
            currency="USD",
            subtotal=1500.0,
            tax=0.0,
            source="wkd.pdf",
            sha256="hash-wkd",
            raw_text="Sample text"
        )
        anomalies2 = engine.detect_anomalies(weekend_inv)
        self.assertTrue(any(a["id"] == "WEEKEND_INVOICE_DATE" for a in anomalies2))

        # 3. Split invoicing structuring risk ($4,950 just below $5,000 threshold)
        split_inv = engine.Invoice(
            invoice_number="INV-SPLIT-1",
            invoice_date="2026-10-28",
            vendor="Acme Cloud Services",
            po_number="PO-1002",
            total=4950.0,
            currency="USD",
            subtotal=4950.0,
            tax=0.0,
            source="split.pdf",
            sha256="hash-split",
            raw_text="Sample text"
        )
        anomalies3 = engine.detect_anomalies(split_inv)
        self.assertTrue(any(a["id"] == "SPLIT_INVOICE_RISK" for a in anomalies3))

        # 4. Abnormal tax rate (> 25%)
        tax_inv = engine.Invoice(
            invoice_number="INV-TAX-1",
            invoice_date="2026-10-28",
            vendor="Acme Cloud Services",
            po_number="PO-1002",
            total=1350.0,
            currency="USD",
            subtotal=1000.0,
            tax=350.0,  # 35% tax
            source="tax.pdf",
            sha256="hash-tax",
            raw_text="Sample text"
        )
        anomalies4 = engine.detect_anomalies(tax_inv)
        self.assertTrue(any(a["id"] == "ABNORMAL_TAX_RATE" for a in anomalies4))

    def test_three_way_match_extended_metrics(self) -> None:
        path = engine.ROOT / "data" / "invoices" / "happy_path.pdf"
        inv, res = engine.process_pdf(path.read_bytes(), "happy_path.pdf", self.pos)
        tw = res["three_way_match"]
        self.assertIn("match_percentage", tw)
        self.assertIn("matched_lines_count", tw)
        self.assertIn("discrepant_lines_count", tw)
        self.assertEqual(tw["match_percentage"], 100.0)
        self.assertEqual(tw["discrepant_lines_count"], 0)


if __name__ == "__main__":
    unittest.main()

