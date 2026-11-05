from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

root = Path(__file__).parent / "data" / "invoices"
root.mkdir(parents=True, exist_ok=True)


def draw_enterprise_invoice(pdf: canvas.Canvas, meta: dict) -> None:
    # 1. Top Emerald Brand Accent Bar
    pdf.setFillColorRGB(0.02, 0.59, 0.41)  # Emerald #059669
    pdf.rect(40, 755, 532, 6, fill=1, stroke=0)

    # 2. Seller / Vendor Entity Information
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, 732, meta["vendor"])

    pdf.setFont("Helvetica", 8)
    pdf.setFillColorRGB(0.35, 0.42, 0.50)
    pdf.drawString(40, 718, meta.get("address", "100 Industrial Parkway, Suite 400 | Chicago, IL 60601"))
    pdf.drawString(
        40, 706,
        f"Tax ID / EIN: {meta.get('tax_id', 'US-36-8819201')} | Phone: {meta.get('phone', '(312) 555-0199')} | Email: {meta.get('email', 'billing@vendor.com')}"
    )

    # 3. Invoice Header & Document Metadata
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawRightString(572, 732, "INVOICE")

    pdf.setFont("Helvetica-Bold", 8.5)
    y_meta = 718
    for label, val in meta.get("metadata", []):
        pdf.setFillColorRGB(0.25, 0.30, 0.38)
        pdf.drawRightString(480, y_meta, f"{label}:")
        pdf.setFillColorRGB(0.06, 0.09, 0.16)
        pdf.drawString(486, y_meta, str(val))
        y_meta -= 12

    # Horizontal Divider Line
    pdf.setStrokeColorRGB(0.88, 0.91, 0.94)
    pdf.setLineWidth(1)
    pdf.line(40, 650, 572, 650)

    # 4. Bill To / Ship To / Commercial Terms
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.drawString(40, 636, "BILL TO:")
    pdf.drawString(220, 636, "SHIP TO / DELIVER TO:")
    pdf.drawString(400, 636, "PAYMENT TERMS & REMIT:")

    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColorRGB(0.28, 0.34, 0.42)
    pdf.drawString(40, 624, "Mosaic Global Enterprises Inc.")
    pdf.drawString(40, 614, "Accounts Payable Operations - Floor 4")
    pdf.drawString(40, 604, "100 Financial Way, New York, NY 10005")

    pdf.drawString(220, 624, "Central Logistics Receiving Dock #4")
    pdf.drawString(220, 614, "500 Distribution Boulevard")
    pdf.drawString(220, 604, "Edison, NJ 08817")

    terms = meta.get("terms", "Net 30 Days")
    remit = meta.get("remit", "JPMorgan Chase Bank Acct ending 4912")
    pdf.drawString(400, 624, f"Terms: {terms}")
    pdf.drawString(400, 614, f"Remit to: {remit}")
    pdf.drawString(400, 604, "Settlement: Electronic ACH / Fedwire")

    # 5. Line Items Table Header
    pdf.setFillColorRGB(0.94, 0.96, 0.98)
    pdf.rect(40, 570, 532, 18, fill=1, stroke=0)
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(45, 576, "LN")
    pdf.drawString(65, 576, "SKU / PART #")
    pdf.drawString(160, 576, "ITEM DESCRIPTION")
    pdf.drawRightString(390, 576, "QTY")
    pdf.drawRightString(460, 576, "UNIT PRICE")
    pdf.drawRightString(565, 576, "LINE AMOUNT")

    # 6. Structured Line Items
    y_row = 552
    lines = meta.get("lines", [])
    for idx, item in enumerate(lines, 1):
        pdf.setFont("Helvetica", 7.5)
        pdf.setFillColorRGB(0.2, 0.25, 0.3)
        # Structured string ensuring robust text layer extraction
        line_text = f"Item {idx}: SKU {item.get('sku', '')} | {item.get('description', '')} | Qty: {item.get('qty', '')} | Unit Price: {item.get('price', '')} | Line Amount: {item.get('total', '')}"
        pdf.drawString(45, y_row, line_text)
        pdf.setStrokeColorRGB(0.92, 0.94, 0.96)
        pdf.line(40, y_row - 4, 572, y_row - 4)
        y_row -= 20

    # 7. Financial Summary Box (Subtotal, Tax, Total)
    y_totals = min(y_row - 10, 440)
    pdf.setFont("Helvetica", 8.5)
    pdf.setFillColorRGB(0.3, 0.35, 0.4)

    if "subtotal" in meta:
        pdf.drawRightString(460, y_totals, "Subtotal:")
        pdf.drawRightString(565, y_totals, meta["subtotal"])
        y_totals -= 14

    if "tax" in meta:
        pdf.drawRightString(460, y_totals, "Sales Tax / VAT:")
        pdf.drawRightString(565, y_totals, meta["tax"])
        y_totals -= 14

    if "total" in meta:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.setFillColorRGB(0.06, 0.09, 0.16)
        pdf.drawRightString(460, y_totals - 2, "Invoice Total:")
        pdf.drawRightString(565, y_totals - 2, meta["total"])
        y_totals -= 20
    elif "missing_total_note" in meta:
        pdf.setFont("Helvetica-Oblique", 8.5)
        pdf.setFillColorRGB(0.8, 0.2, 0.2)
        pdf.drawString(260, y_totals, meta["missing_total_note"])
        y_totals -= 18

    # 8. Footer Remittance Instructions & Audit Boilerplate
    pdf.setStrokeColorRGB(0.88, 0.91, 0.94)
    pdf.line(40, 210, 572, 210)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColorRGB(0.06, 0.09, 0.16)
    pdf.drawString(40, 196, "REMITTANCE INSTRUCTIONS & COMMERCIAL AUDIT POLICY")
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColorRGB(0.35, 0.42, 0.50)
    pdf.drawString(40, 184, f"Electronic Payment Coordinates: Remit to: {remit}")
    pdf.drawString(40, 172, "Please reference invoice number on remittance advice and submit to accounting@mosaicglobal.com.")
    pdf.drawString(40, 160, "Corporate terms: Invoices subject to automated 3-way matching and discrepancy resolution controls.")


enterprise_scenarios = {
    "happy_path.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-041"),
            ("Invoice Date", "2026-10-28"),
            ("Due Date", "2026-11-27"),
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912 | Routing: 021000021",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$100.00", "total": "$400.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,250.00",
    },
    "quantity_mismatch.pdf": {
        "vendor": "Apex Industrial Supplies",
        "address": "4500 Manufacturing Blvd, Building B | Detroit, MI 48201",
        "tax_id": "US-38-4491022",
        "phone": "(313) 555-0811",
        "email": "ar@apexindustrialsupplies.com",
        "metadata": [
            ("Invoice Number", "AIS-2026-904"),
            ("Invoice Date", "2026-11-02"),
            ("Due Date", "2026-12-17"),
            ("PO Number", "PO-1006"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 45"),
        ],
        "terms": "Net 45 Days",
        "remit": "PNC Bank Acct ending 5510 | Routing: 041000124",
        "lines": [
            {"sku": "IND-MOT-09", "description": "Variable Speed Electric Motor 5HP", "qty": "5", "price": "$300.00", "total": "$1,500.00"},
        ],
        "subtotal": "$1,500.00",
        "tax": "$0.00",
        "total": "$1,500.00",
    },
    "within_tolerance.pdf": {
        "vendor": "Acme Cloud Services",
        "address": "500 Cloud Way, Suite 1200 | Seattle, WA 98101",
        "tax_id": "US-91-3329104",
        "phone": "(206) 555-0144",
        "email": "invoicing@acmecloud.io",
        "metadata": [
            ("Invoice Number", "AC-8841"),
            ("Invoice Date", "2026-10-29"),
            ("Due Date", "2026-11-28"),
            ("PO Number", "PO-1002"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Silicon Valley Bank Acct ending 9012 | Routing: 121140399",
        "lines": [
            {"sku": "SRV-CLD-ENT", "description": "Dedicated Enterprise Cloud Cluster Hosting", "qty": "1", "price": "$5,050.00", "total": "$5,050.00"},
        ],
        "subtotal": "$5,050.00",
        "tax": "$0.00",
        "total": "$5,050.00",
    },
    "cumulative_balance.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-043"),
            ("Invoice Date", "2026-11-01"),
            ("Due Date", "2026-12-01"),
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$103.125", "total": "$412.50"},
        ],
        "subtotal": "$1,162.50",
        "tax": "$100.00",
        "total": "$1,262.50",
    },
    "possible_split_invoice.pdf": {
        "vendor": "Bluebird Logistics",
        "address": "800 Harbor Blvd | Long Beach, CA 90802",
        "tax_id": "US-95-7721098",
        "phone": "(562) 555-0311",
        "email": "freight-billing@bluebirdlogistics.com",
        "metadata": [
            ("Invoice Number", "BL-2207"),
            ("Invoice Date", "2026-10-30"),
            ("Due Date", "2026-11-29"),
            ("PO Number", "PO-1003"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Wells Fargo Bank Acct ending 8810",
        "lines": [
            {"sku": "LOG-FRT-STD", "description": "Interstate Freight - 40ft Container Transport (Partial 1 of 2)", "qty": "1", "price": "$1,200.00", "total": "$1,200.00"},
        ],
        "subtotal": "$1,200.00",
        "tax": "$0.00",
        "total": "$1,200.00",
    },
    "vendor_mismatch.pdf": {
        "vendor": "Other Freight LLC",
        "address": "12 Elm Street | Newark, NJ 07102",
        "tax_id": "US-22-9988112",
        "phone": "(973) 555-0182",
        "email": "billing@otherfreight.com",
        "metadata": [
            ("Invoice Number", "OF-7002"),
            ("Invoice Date", "2026-10-30"),
            ("Due Date", "2026-11-29"),
            ("PO Number", "PO-1003"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Bank of America Acct ending 7731",
        "lines": [
            {"sku": "LOG-FRT-STD", "description": "Interstate Freight - 40ft Container Transport", "qty": "2", "price": "$1,200.00", "total": "$2,400.00"},
        ],
        "subtotal": "$2,400.00",
        "tax": "$0.00",
        "total": "$2,400.00",
    },
    "missing_po_reference.pdf": {
        "vendor": "Maple Consulting",
        "address": "250 Bay Street, Suite 900 | Toronto, ON M5J 2T7",
        "tax_id": "CA-889102-RT0001",
        "phone": "(416) 555-0177",
        "email": "invoices@mapleconsulting.ca",
        "metadata": [
            ("Invoice Number", "MC-1109"),
            ("Invoice Date", "2026-10-31"),
            ("Due Date", "2026-11-30"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Royal Bank of Canada Acct ending 3012",
        "lines": [
            {"sku": "CON-ENG-SRV", "description": "Senior Systems Architecture Consulting (40 hrs)", "qty": "40", "price": "$80.00", "total": "$3,200.00"},
        ],
        "subtotal": "$3,200.00",
        "tax": "$0.00",
        "total": "$3,200.00",
    },
    "over_tolerance.pdf": {
        "vendor": "Maple Consulting",
        "address": "250 Bay Street, Suite 900 | Toronto, ON M5J 2T7",
        "tax_id": "CA-889102-RT0001",
        "phone": "(416) 555-0177",
        "email": "invoices@mapleconsulting.ca",
        "metadata": [
            ("Invoice Number", "MC-1110"),
            ("Invoice Date", "2026-10-31"),
            ("Due Date", "2026-11-30"),
            ("PO Number", "PO-1004"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Royal Bank of Canada Acct ending 3012",
        "lines": [
            {"sku": "CON-ENG-SRV", "description": "Senior Systems Architecture Consulting (45 hrs)", "qty": "45", "price": "$80.00", "total": "$3,600.00"},
        ],
        "subtotal": "$3,600.00",
        "tax": "$0.00",
        "total": "$3,600.00",
    },
    "missing_total.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-042"),
            ("Invoice Date", "2026-10-31"),
            ("Due Date", "2026-11-30"),
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
        ],
        "subtotal": "$750.00",
        "tax": "$60.00",
        "missing_total_note": "Please contact us with questions regarding final balance.",
    },
    "cents_mismatch.pdf": {
        "vendor": "Maple Consulting",
        "address": "250 Bay Street, Suite 900 | Toronto, ON M5J 2T7",
        "tax_id": "CA-889102-RT0001",
        "phone": "(416) 555-0177",
        "email": "invoices@mapleconsulting.ca",
        "metadata": [
            ("Invoice Number", "MC-1111"),
            ("Invoice Date", "2026-11-01"),
            ("Due Date", "2026-12-01"),
            ("PO Number", "PO-1004"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Royal Bank of Canada Acct ending 3012",
        "lines": [
            {"sku": "CON-ENG-SRV", "description": "Senior Systems Architecture Consulting", "qty": "14.375", "price": "$80.00", "total": "$1,150.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,215.00",  # Math error: 1150 + 100 != 1215
    },
    "ambiguous_date.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-044"),
            ("Invoice Date", "10/11/2026"),  # Ambiguous MM/DD vs DD/MM
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$100.00", "total": "$400.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,250.00",
    },
    "future_date.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-045"),
            ("Invoice Date", "2027-01-15"),  # Future date
            ("Due Date", "2027-02-14"),
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$100.00", "total": "$400.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,250.00",
    },
    "supplier_name_variant.pdf": {
        "vendor": "Northstar Office Supplies",  # DBA variant
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-046"),
            ("Invoice Date", "2026-11-02"),
            ("Due Date", "2026-12-02"),
            ("PO Number", "PO-1001"),
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$100.00", "total": "$400.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,250.00",
    },
    "pending_po.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-047"),
            ("Invoice Date", "2026-11-02"),
            ("Due Date", "2026-12-02"),
            ("PO Number", "PO-1005"),  # Pending PO
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "IT-MON-4K", "description": "Ultra-HD 32 inch IPS Developer Monitor", "qty": "2", "price": "$400.00", "total": "$800.00"},
        ],
        "subtotal": "$800.00",
        "tax": "$0.00",
        "total": "$800.00",
    },
    "currency_unknown.pdf": {
        "vendor": "Maple Consulting",
        "address": "250 Bay Street, Suite 900 | Toronto, ON M5J 2T7",
        "tax_id": "CA-889102-RT0001",
        "phone": "(416) 555-0177",
        "email": "invoices@mapleconsulting.ca",
        "metadata": [
            ("Invoice Number", "MC-1112"),
            ("Invoice Date", "2026-11-02"),
            ("Due Date", "2026-12-02"),
            ("PO Number", "PO-1004"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "Royal Bank of Canada Acct ending 3012",
        "lines": [
            {"sku": "CON-ENG-SRV", "description": "Senior Systems Architecture Consulting", "qty": "40", "price": "80.00", "total": "3200.00"},
        ],
        "subtotal": "3200.00",
        "total": "3200.00",  # No currency symbol
    },
    "po_typo.pdf": {
        "vendor": "Northstar Office Supply",
        "address": "100 Industrial Parkway, Suite 400 | Chicago, IL 60601",
        "tax_id": "US-36-8819201",
        "phone": "(312) 555-0199",
        "email": "billing@northstaroffice.com",
        "metadata": [
            ("Invoice Number", "NS-2026-048"),
            ("Invoice Date", "2026-11-02"),
            ("Due Date", "2026-12-02"),
            ("PO Number", "PO-1OO1"),  # Typo letters 'OO'
            ("Currency", "USD"),
            ("Payment Terms", "Net 30"),
        ],
        "terms": "Net 30 Days",
        "remit": "JPMorgan Chase Bank Acct ending 4912",
        "lines": [
            {"sku": "FUR-CH-01", "description": "Ergonomic Office Chair - Model X", "qty": "10", "price": "$75.00", "total": "$750.00"},
            {"sku": "FUR-DK-04", "description": "Standing Desk Converter - 36 inch", "qty": "4", "price": "$100.00", "total": "$400.00"},
        ],
        "subtotal": "$1,150.00",
        "tax": "$100.00",
        "total": "$1,250.00",
    },
}

# Generate all selectable-text scenario invoices
for filename, meta in enterprise_scenarios.items():
    file_path = root / filename
    c = canvas.Canvas(str(file_path), pagesize=letter)
    draw_enterprise_invoice(c, meta)
    c.save()

# duplicate_invoice.pdf is a bit-for-bit duplicate of happy_path.pdf
duplicate_path = root / "duplicate_invoice.pdf"
duplicate_path.write_bytes((root / "happy_path.pdf").read_bytes())

# Scanned image-only simulation
scanned = root / "image_only_scan.pdf"
pdf = canvas.Canvas(str(scanned), pagesize=letter)
pdf.setFillColorRGB(0.92, 0.90, 0.84)
pdf.rect(55, 80, 500, 650, fill=1, stroke=0)
pdf.setStrokeColorRGB(0.65, 0.62, 0.54)
for y in range(620, 200, -35):
    pdf.line(85, y, 450 if y % 2 else 500, y)
pdf.save()

print(f"Generated {len(enterprise_scenarios) + 2} enterprise scenario invoices in {root}")