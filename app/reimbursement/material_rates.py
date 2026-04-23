"""Guild repair reimbursement: material quantities × fixed gold rates (TIF/BWC operation)."""

# Display key, label, gold per unit
REIMBURSEMENT_MATERIALS: list[tuple[str, str, int]] = [
    ("canvas", "Canvas", 300),
    ("beams", "Beams", 1000),
    ("bulkheads", "Bulkheads", 1200),
    ("bronze", "Bronze", 1300),
    ("plates", "Plates", 1500),
    ("bp_fragment", "BP fragment", 22000),
]

RATE_BY_KEY: dict[str, int] = {k: r for k, _, r in REIMBURSEMENT_MATERIALS}
