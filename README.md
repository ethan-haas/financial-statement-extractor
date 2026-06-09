# Cash-Basis Financial Statement Extractor

Turns a government audit PDF (Ohio Auditor of State, *regulatory cash basis*) into clean,
structured JSON — and then **proves the numbers are right** with tie-out checks and a
golden-file test. Deterministic: same PDF in, same JSON out. Runs offline; no OCR needed
for born-digital text, and the model is never trusted to do arithmetic.

This is a sanitized demo of the kind of document-extraction work I do. It runs on a
**public record** (the Allen Township, Darke County audit report, published by the Ohio
Auditor of State — not affiliated with any client) and generalizes to any AOS cash-basis
"Combined Statement of Receipts, Disbursements and Changes in Fund Balances."

## What it does
1. **`extract.py`** — finds the combined-statement page, clusters words by character
   position into rows and columns, and emits structured JSON: each line item with its
   section, label, per-fund-type values, and source page.
2. **`validate.py`** — re-derives every total from the underlying line items and flags
   anything that doesn't reconcile:
   - **FOOT** — receipt/disbursement line items sum to their reported totals (each column)
   - **ARTICULATE** — net change = receipts − disbursements; ending = beginning + net change
   - **CROSSFOOT** — the Combined Total column = sum of the fund-type columns, every row
3. **`test_golden.py`** — pins the extracted output to a known-good golden file, so any
   future change that alters a single figure fails loudly.

## Why it's built this way
The hard part of AI document work isn't pulling text out — it's being *sure it's right*.
So the LLM (where one is used at all) only reads and classifies; **tested code does every
calculation**, every figure carries its source page, and anything that doesn't tie routes
to an exceptions report for human review. That separation is what makes output you can put
in front of an auditor.

## Run it
```bash
pip install pdfplumber pytest
python extract.py sample_report.pdf example_output.json   # PDF -> structured JSON
python validate.py sample_report.pdf                      # tie-out report
python demo_catch_error.py                                # proof the checks catch errors
pytest                                                    # golden-file regression test
```

## Sample output

**Tie-out on the real (published, correct) report — 0 exceptions:**
```
Tie-out report — Allen Township, Darke County  |  FYE December 31, 2024  |  Regulatory Cash Basis
======================================================================
Checks run: 25    Exceptions: 0

[OK] Statement foots, crossfoots, and articulates across all columns.
```

**The checks have teeth** — inject one transposed digit and it's caught:
```
Injected one wrong figure (Public Works, Special Revenue: 150,717 -> 150,171).
25 checks run, 2 exception(s) caught:

  [x] FOOT disbursements [Special Revenue]: line items sum 248,676 != reported total 249,222
  [x] CROSSFOOT [Public Works]: General + Special Revenue = 150,171 != Combined Total 150,717
```

**Structured JSON (excerpt):**
```json
{
  "entity": "Allen Township, Darke County",
  "fiscal_year_end": "December 31, 2024",
  "basis": "Regulatory Cash Basis",
  "columns": ["General", "Special Revenue", "Combined Total"],
  "line_items": [
    {"section": "Cash Receipts", "label": "Property and Other Local Taxes",
     "values": {"General": 26216, "Special Revenue": 115423, "Combined Total": 141639},
     "source_page": 10}
  ]
}
```

## Files
| File | Purpose |
|---|---|
| `extract.py` | PDF → structured JSON (character-position clustering) |
| `validate.py` | foot / crossfoot / articulate tie-out checks |
| `test_golden.py` | golden-file regression test (`pytest`) |
| `demo_catch_error.py` | shows the checks catching an injected error |
| `expected_golden.json` | known-good extraction (the golden file) |
| `example_output.json` | latest extraction output |
| `example_tie_out_report.txt` | saved tie-out report |
| `sample_report.pdf` | the public AOS report used as input |

## Stack
Python · pdfplumber · pytest. ~250 lines, no external services, runs on any machine.
