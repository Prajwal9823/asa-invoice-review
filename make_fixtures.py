from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

root = Path(__file__).parent / "data" / "invoices"
root.mkdir(parents=True, exist_ok=True)
fixtures = {
    "happy_path.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-041", "Invoice Date: 2026-10-28", "PO Number: PO-1001", "Currency: USD", "Subtotal: $1,150.00", "Tax: $100.00", "Invoice Total: $1,250.00"],
    "within_tolerance.pdf": ["Acme Cloud Services", "INVOICE", "Invoice Number: AC-8841", "Invoice Date: 2026-10-29", "PO Number: PO-1002", "Currency: USD", "Invoice Total: $5,050.00"],
    "cumulative_balance.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-043", "Invoice Date: 2026-11-01", "PO Number: PO-1001", "Currency: USD", "Subtotal: $1,162.50", "Tax: $100.00", "Invoice Total: $1,262.50"],
    "possible_split_invoice.pdf": ["Bluebird Logistics", "INVOICE", "Invoice Number: BL-2207", "Invoice Date: 2026-10-30", "PO Number: PO-1003", "Currency: USD", "Invoice Total: $1,200.00"],
    "vendor_mismatch.pdf": ["Other Freight LLC", "INVOICE", "Invoice Number: OF-7002", "Invoice Date: 2026-10-30", "PO Number: PO-1003", "Currency: USD", "Invoice Total: $2,400.00"],
    "missing_po_reference.pdf": ["Maple Consulting", "INVOICE", "Invoice Number: MC-1109", "Invoice Date: 2026-10-31", "Currency: USD", "Invoice Total: $3,200.00"],
    "over_tolerance.pdf": ["Maple Consulting", "INVOICE", "Invoice Number: MC-1110", "Invoice Date: 2026-10-31", "PO Number: PO-1004", "Currency: USD", "Invoice Total: $3,600.00"],
    "missing_total.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-042", "Invoice Date: 2026-10-31", "PO Number: PO-1001", "Currency: USD", "Please contact us with questions."],
    "cents_mismatch.pdf": ["Maple Consulting", "INVOICE", "Invoice Number: MC-1111", "Invoice Date: 2026-11-01", "PO Number: PO-1004", "Currency: USD", "Subtotal: $1,150.00", "Tax: $100.00", "Invoice Total: $1,215.00"],
    "ambiguous_date.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-044", "Invoice Date: 10/11/2026", "PO Number: PO-1001", "Currency: USD", "Invoice Total: $1,250.00"],
    "future_date.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-045", "Invoice Date: 2027-01-15", "PO Number: PO-1001", "Currency: USD", "Invoice Total: $1,250.00"],
    "supplier_name_variant.pdf": ["Northstar Office Supplies", "INVOICE", "Invoice Number: NS-2026-046", "Invoice Date: 2026-11-02", "PO Number: PO-1001", "Currency: USD", "Invoice Total: $1,250.00"],
    "pending_po.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-047", "Invoice Date: 2026-11-02", "PO Number: PO-1005", "Currency: USD", "Invoice Total: $800.00"],
    "currency_unknown.pdf": ["Maple Consulting", "INVOICE", "Invoice Number: MC-1112", "Invoice Date: 2026-11-02", "PO Number: PO-1004", "Invoice Total: 3200.00"],
    "po_typo.pdf": ["Northstar Office Supply", "INVOICE", "Invoice Number: NS-2026-048", "Invoice Date: 2026-11-02", "PO Number: PO-1OO1", "Currency: USD", "Invoice Total: $1,250.00"],
}
for name, lines in fixtures.items():
    path = root / name
    if path.exists():
        continue
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, 730, lines[0])
    y = 690
    for line in lines[1:]:
        pdf.setFont("Helvetica", 12)
        pdf.drawString(72, y, line)
        y -= 28
    pdf.save()
scanned = root / "image_only_scan.pdf"
if not scanned.exists():
    pdf = canvas.Canvas(str(scanned), pagesize=letter)
    pdf.setFillColorRGB(0.92, 0.90, 0.84)
    pdf.rect(55, 80, 500, 650, fill=1, stroke=0)
    pdf.setStrokeColorRGB(0.65, 0.62, 0.54)
    for y in range(620, 200, -35):
        pdf.line(85, y, 450 if y % 2 else 500, y)
    pdf.save()
print(f"Created {len(fixtures)} selectable-text scenarios and an image-only scan in {root}")

