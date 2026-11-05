# Five-minute walkthrough

1. Show the evidence-first desk and describe the invoice, supplier, PO, and control tiles.
2. Run **Clean match**. Point out the amount reconciliation and recommendation to continue with AP approval.
3. Run **Different supplier**. Explain why it stops safely even when the amount is exact.
4. Run **Possible split bill** or **Outside tolerance**. Show the suggested human next step.
5. For the standout control, run **Clean match** first, then **The PO is nearly spoken for**. Each invoice looks acceptable on its own, but together they exceed the approved commitment. Mosaic catches the cumulative overrun.
6. Open **Case archive**. Find a run, reopen its reasoning, and export a JSON packet or CSV.
7. Open **Decision map**. Explain why fuzzy matches are hints, not approvals, and name the scan/OCR boundary.

Keep the human approval boundary clear: Mosaic prepares the case; it does not pay invoices.
