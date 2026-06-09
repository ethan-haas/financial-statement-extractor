#!/usr/bin/env python3
"""
Golden-file regression test.

Pins the extractor's output to a known-good JSON so any future change that alters a
single extracted figure fails loudly — the same discipline used on audit tooling where
output has to be exactly right, not approximately right.

Run with either:
    pytest
    python test_golden.py        # no pytest needed
"""
import json, os
import extract, validate

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "sample_report.pdf")
GOLDEN = os.path.join(HERE, "expected_golden.json")


def test_extraction_matches_golden():
    got = extract.extract(PDF)
    exp = json.load(open(GOLDEN, encoding="utf-8"))
    assert got["entity"] == exp["entity"]
    assert got["columns"] == exp["columns"]
    assert got["line_items"] == exp["line_items"], "extracted figures drifted from the golden file"


def test_statement_ties_out():
    data = extract.extract(PDF)
    checks, exceptions = validate.validate(data)
    assert checks > 0, "no checks ran"
    assert exceptions == [], f"tie-out exceptions: {exceptions}"


if __name__ == "__main__":
    test_extraction_matches_golden()
    test_statement_ties_out()
    print("OK - both tests passed (extraction matches golden; statement ties out).")
