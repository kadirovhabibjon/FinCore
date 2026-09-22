from fincore_common import Gauge

# spec Section 24: "reconciliation mismatches" — set by the
# reconciliation loop (app/main.py) after each pass to the total count
# of violations found (spec Section 8.4's four invariants combined),
# regardless of kind. A non-zero value is an incident to investigate
# (ADR-0002), never something this service corrects on its own.
RECONCILIATION_MISMATCHES = Gauge(
    "fincore_reconciliation_mismatches",
    "Violations found on the most recent reconciliation pass.",
)
