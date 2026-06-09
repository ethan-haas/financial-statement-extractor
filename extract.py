#!/usr/bin/env python3
"""
extract.py — turn an Ohio Auditor of State "Combined Statement of Receipts,
Disbursements and Changes in Fund Balances (Regulatory Cash Basis)" into clean,
structured JSON.

These reports are generated PDFs with no table layer, so extraction works by
clustering words on character x-positions (columns) and y-positions (rows) — no OCR
needed for born-digital text. Output is deterministic: same PDF in, same JSON out.

Usage:
    python extract.py sample_report.pdf            # prints JSON to stdout
    python extract.py sample_report.pdf out.json   # also writes to file
"""
import sys, re, json
import pdfplumber

_NUM = re.compile(r"^\(?\$?-?[\d,]+(?:\.\d+)?\)?$")   # money / number, optional () for negatives
_DASH = {"-", "–", "—"}                                # dash = zero in these statements
_LABEL_MAX_X = 295                                     # words ending left of here are row labels


def parse_amount(tok: str):
    """'26,216' -> 26216 ; '(1,200)' -> -1200 ; '-' -> 0 ; '$' -> None (skip marker)."""
    t = tok.strip()
    if t in _DASH:
        return 0
    if t == "$":
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace("$", "").replace(",", "").strip()
    if t == "" or t in _DASH:
        return 0
    try:
        v = float(t)
    except ValueError:
        return None
    v = int(v) if v == int(v) else v
    return -v if neg else v


def is_value_token(tok: str) -> bool:
    t = tok.strip()
    return t in _DASH or bool(_NUM.match(t))


def cluster(values, gap):
    """1-D clustering: sort, split where consecutive points differ by > gap. Returns centers."""
    if not values:
        return []
    vals = sorted(values)
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] > gap:
            groups.append(cur); cur = [v]
        else:
            cur.append(v)
    groups.append(cur)
    return [sum(g) / len(g) for g in groups]


def group_rows(words, tol=3.0):
    """Group words into visual rows by 'top' coordinate; keep each row's top + sorted words."""
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(w["top"] - rows[-1]["top"]) <= tol:
            rows[-1]["words"].append(w)
        else:
            rows.append({"top": w["top"], "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda w: w["x0"])
    return rows


def _has_value(row) -> bool:
    return any(w["x0"] > _LABEL_MAX_X and is_value_token(w["text"]) for w in row["words"])


def _is_data_row(row) -> bool:
    """Real table row: has a value column AND a left-margin label (excludes centered title/period lines)."""
    return _has_value(row) and any(w["x0"] < 150 and re.search(r"[A-Za-z]", w["text"]) for w in row["words"])


def _name_columns(header_words, centers):
    """Map header words to the nearest column center; order tokens top-then-left; join."""
    fallback = [f"Column {i+1}" for i in range(len(centers))]
    if not centers:
        return fallback
    buckets = {i: [] for i in range(len(centers))}
    for w in header_words:
        mid = (w["x0"] + w["x1"]) / 2
        ci = min(range(len(centers)), key=lambda k: abs(mid - centers[k]))
        buckets[ci].append((w["top"], w["x0"], w["text"]))
    names = []
    for i in range(len(centers)):
        toks = [t for _, _, t in sorted(buckets[i])]
        names.append(" ".join(toks).strip() or fallback[i])
    return names


def extract(pdf_path: str) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        pi = _find_statement_page(pdf)
        page = pdf.pages[pi]
        full = page.extract_text() or ""
        rows = group_rows(page.extract_words())

    # header metadata from the page's title block
    head = "\n".join(full.splitlines()[:8])
    ent = re.search(r"^([A-Z][A-Z .'-]+?)\s+([A-Z]+ COUNTY)", head, re.M)
    entity = f"{ent.group(1).title()}, {ent.group(2).title()}" if ent else "Unknown entity"
    fye = re.search(r"YEAR ENDED ([A-Z]+ \d{1,2}, \d{4})", full, re.I)
    fiscal_year_end = fye.group(1).title() if fye else None
    basis = "Regulatory Cash Basis" if re.search(r"REGULATORY CASH BASIS", full, re.I) else "Unknown"

    # first real data row (values + left-margin label) — skips the centered title/period block
    first_data_idx = next((i for i, r in enumerate(rows) if _is_data_row(r)), None)
    if first_data_idx is None:
        raise SystemExit("No data rows found on the statement page.")
    first_top = rows[first_data_idx]["top"]

    # column-title rows = rows above the data carrying right-side text (e.g., General / Combined Total);
    # keep only those within 50px of the data (excludes the far-above report title block)
    header_idxs = [i for i in range(first_data_idx)
                   if any(w["x0"] > _LABEL_MAX_X and re.search(r"[A-Za-z]", w["text"]) and not is_value_token(w["text"])
                          for w in rows[i]["words"])]
    header_words = [w for i in header_idxs if rows[i]["top"] >= first_top - 50
                    for w in rows[i]["words"] if w["x0"] > _LABEL_MAX_X and re.search(r"[A-Za-z]", w["text"])]

    # start just under the column-title rows so section headers (e.g., "Cash Receipts") are included
    start_idx = min(max(header_idxs) + 1, first_data_idx) if header_idxs else first_data_idx
    data_rows = []
    for r in rows[start_idx:]:
        if "notes to the financial statements" in " ".join(w["text"] for w in r["words"]).lower():
            break
        data_rows.append(r)

    # columns: cluster the right-edges of value tokens in the data rows (title/period excluded now)
    value_x1 = [w["x1"] for r in data_rows for w in r["words"] if w["x0"] > _LABEL_MAX_X and is_value_token(w["text"])]
    col_centers = cluster(value_x1, gap=25)
    col_names = _name_columns(header_words, col_centers)

    line_items, section = [], None
    for r in rows_iter(data_rows):
        label = " ".join(w["text"] for w in r["words"] if w["x1"] <= _LABEL_MAX_X).strip().rstrip(":")
        vals = {}
        for w in r["words"]:
            if w["x0"] <= _LABEL_MAX_X or not is_value_token(w["text"]):
                continue
            amt = parse_amount(w["text"])
            if amt is None:
                continue
            ci = min(range(len(col_centers)), key=lambda k: abs(w["x1"] - col_centers[k]))
            vals[col_names[ci]] = amt
        if not label:
            continue
        if not vals:                                   # label-only row = section header
            if re.search(r"\b(receipts|disbursements)\b", label, re.I) and not re.search(r"total|net", label, re.I):
                section = label
            continue
        line_items.append({"section": section, "label": label, "values": vals, "source_page": pi + 1})

    return {
        "entity": entity,
        "fiscal_year_end": fiscal_year_end,
        "basis": basis,
        "statement": "Combined Statement of Receipts, Disbursements and Changes in Fund Balances",
        "columns": col_names,
        "line_items": line_items,
        "_source": {"file": pdf_path.replace("/", "\\").split("\\")[-1], "page": pi + 1},
    }


def rows_iter(data_rows):
    return data_rows


def _find_statement_page(pdf):
    for i, pg in enumerate(pdf.pages):
        t = pg.extract_text() or ""
        if re.search(r"COMBINED STATEMENT OF .*RECEIPTS", t, re.I) and "Fund Cash Balances" in t and re.search(r"\d", t):
            return i
    raise SystemExit("No cash-basis Combined Statement page found.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python extract.py <report.pdf> [out.json]")
    data = extract(sys.argv[1])
    out = json.dumps(data, indent=2)
    print(out)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\nwrote {sys.argv[2]}", file=sys.stderr)
