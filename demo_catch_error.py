#!/usr/bin/env python3
"""
Proof the tie-out checks have teeth: inject a single transcription error into the
extracted data and confirm validate.py catches it. (The real report passes with 0
exceptions — this shows what happens on a draft with a mistake.)

    python demo_catch_error.py
"""
import extract, validate

data = extract.extract("sample_report.pdf")

# Introduce ONE realistic error: a digit transposition in Public Works (Special Revenue),
# 150,717 -> 150,171 — the kind of slip a manual preparer makes.
for li in data["line_items"]:
    if li["label"].startswith("Public Works"):
        li["values"]["Special Revenue"] = 150171

checks, exceptions = validate.validate(data)
print(f"Injected one wrong figure (Public Works, Special Revenue: 150,717 -> 150,171).")
print(f"{checks} checks run, {len(exceptions)} exception(s) caught:\n")
for e in exceptions:
    print("  [x]", e)
