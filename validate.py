#!/usr/bin/env python3
"""
validate.py — tie-out checks on an extracted Combined Statement.

This is the part that makes the extraction trustworthy: instead of assuming the
numbers came out right, it re-derives every total from the underlying line items and
flags anything that doesn't reconcile. On an already-published (already-correct)
report it should report ZERO exceptions — which is exactly the point: it proves the
extraction is faithful, and on a draft it would catch a real foot/crossfoot error.

Checks:
  FOOT        — receipt/disbursement line items sum to their reported totals (per column)
  ARTICULATE  — net change = receipts − disbursements; ending = beginning + net change
  CROSSFOOT   — the Combined Total column = sum of the fund-type columns (every row)

Usage:
    python validate.py sample_report.pdf      # extract + validate
    python validate.py example_output.json    # validate an existing extraction
"""
import sys, json, re
import extract

TOLERANCE = 1.0   # whole-dollar reports; allow $1 for rounding


def _find(items, pattern):
    rx = re.compile(pattern, re.I)
    return next((li for li in items if rx.search(li["label"])), None)


def validate(data):
    items = data["line_items"]
    cols = data["columns"]
    total_col, comp_cols = cols[-1], cols[:-1]
    checks, exceptions = 0, []

    def amt(li, c):
        return li["values"].get(c, 0) if li else 0

    total_receipts = _find(items, r"^total cash receipts")
    total_disb = _find(items, r"^total cash disbursements")
    net_change = _find(items, r"net change in fund")
    begin = _find(items, r"fund cash balances,\s*january")
    end = _find(items, r"fund cash balances,\s*december")

    receipt_lines = [li for li in items
                     if "receipt" in (li["section"] or "").lower() and not re.match(r"(?i)\s*total", li["label"])]
    disb_lines = [li for li in items
                  if "disburse" in (li["section"] or "").lower()
                  and not re.match(r"(?i)\s*(total cash disb|net change|fund cash bal)", li["label"])]

    # 1 — FOOT receipts
    if total_receipts:
        for c in cols:
            checks += 1
            s = sum(amt(li, c) for li in receipt_lines)
            if abs(s - amt(total_receipts, c)) > TOLERANCE:
                exceptions.append(f"FOOT receipts [{c}]: line items sum {s:,} != reported total {amt(total_receipts,c):,}")

    # 2 — FOOT disbursements
    if total_disb:
        for c in cols:
            checks += 1
            s = sum(amt(li, c) for li in disb_lines)
            if abs(s - amt(total_disb, c)) > TOLERANCE:
                exceptions.append(f"FOOT disbursements [{c}]: line items sum {s:,} != reported total {amt(total_disb,c):,}")

    # 3 — ARTICULATE: net change = receipts − disbursements
    if total_receipts and total_disb and net_change:
        for c in cols:
            checks += 1
            calc = amt(total_receipts, c) - amt(total_disb, c)
            if abs(calc - amt(net_change, c)) > TOLERANCE:
                exceptions.append(f"ARTICULATE net change [{c}]: receipts − disbursements {calc:,} != reported {amt(net_change,c):,}")

    # 4 — ARTICULATE: ending balance = beginning + net change
    if begin and end and net_change:
        for c in cols:
            checks += 1
            calc = amt(begin, c) + amt(net_change, c)
            if abs(calc - amt(end, c)) > TOLERANCE:
                exceptions.append(f"ARTICULATE ending balance [{c}]: beginning + net change {calc:,} != reported {amt(end,c):,}")

    # 5 — CROSSFOOT: total column = sum of component columns, every row
    for li in items:
        if total_col in li["values"] and all(cc in li["values"] for cc in comp_cols):
            checks += 1
            s = sum(li["values"][cc] for cc in comp_cols)
            if abs(s - li["values"][total_col]) > TOLERANCE:
                exceptions.append(f"CROSSFOOT [{li['label']}]: {' + '.join(comp_cols)} = {s:,} != {total_col} {li['values'][total_col]:,}")

    return checks, exceptions


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "sample_report.pdf"
    data = extract.extract(arg) if arg.lower().endswith(".pdf") else json.load(open(arg, encoding="utf-8"))

    checks, exceptions = validate(data)
    print(f"Tie-out report — {data['entity']}  |  FYE {data['fiscal_year_end']}  |  {data['basis']}")
    print("=" * 70)
    print(f"Checks run: {checks}    Exceptions: {len(exceptions)}")
    if exceptions:
        print("\nEXCEPTIONS")
        for e in exceptions:
            print("  [x]", e)
        sys.exit(1)
    print("\n[OK] Statement foots, crossfoots, and articulates across all columns.")


if __name__ == "__main__":
    main()
