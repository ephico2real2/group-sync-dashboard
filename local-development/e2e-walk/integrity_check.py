#!/usr/bin/env python3
"""Four-way integrity check on the artefacts a walk downloaded.

For every <run>/reports/*.json: recompute the sha256 of the canonical data the same way the
service seals it (gsd/reporting/model.py, Report.seal: name, cluster, params, coverage, totals,
truncated, include_members, sections; sorted keys, compact separators, default=str) and compare
it with (1) the JSON's own `sha256` field, (2) the run record the page polled (results.json),
(3) the PDF's metadata (`sha256 <hex>` in the document subject), (4) the HTML (the 16-char
prefix in the header and footer). Also checks the PDF/A marker. Writes <run>/integrity.jsonl,
one line per report, and exits 1 if any check fails.

    integrity_check.py <run dir>
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

CANONICAL = ("name", "cluster", "params", "coverage", "totals", "truncated", "include_members", "sections")


def main() -> int:
    run = pathlib.Path(sys.argv[1])
    res = json.loads((run / "results.json").read_text())
    runs = {s["run"]["id"]: s["run"] for s in res["steps"] if s.get("run")}
    out = run / "integrity.jsonl"
    lines, bad = [], 0
    for jf in sorted((run / "reports").glob("*.json")):
        d = json.loads(jf.read_text())
        canon = {k: d[k] for k in CANONICAL}
        recomputed = hashlib.sha256(
            json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
        pdf, html = jf.with_suffix(".pdf"), jf.with_suffix(".html")
        pdf_bytes = pdf.read_bytes() if pdf.exists() else b""
        html_text = html.read_text(errors="replace") if html.exists() else ""
        row = {
            "name": d["name"], "sha256": d["sha256"],
            "recomputed_matches": recomputed == d["sha256"],
            "run_matches": runs.get(d["run_id"], {}).get("sha256") == d["sha256"],
            "sha_in_pdf_metadata": f"sha256 {d['sha256']}".encode() in pdf_bytes,
            "sha_in_html": d["sha256"][:16] in html_text,
            "pdfa_marker": b"pdfaid:part" in pdf_bytes,
        }
        ok = all(row[k] for k in ("recomputed_matches", "run_matches", "sha_in_pdf_metadata", "sha_in_html"))
        bad += 0 if ok else 1
        lines.append(json.dumps(row))
        print(f"  [{'ok ' if ok else 'FAIL'}] {d['name']:24} {d['sha256'][:12]}  recomputed={row['recomputed_matches']} run={row['run_matches']} pdf={row['sha_in_pdf_metadata']} html={row['sha_in_html']} pdf/a={row['pdfa_marker']}")
    out.write_text("\n".join(lines) + "\n")
    print(f"{len(lines) - bad} / {len(lines)} reports pass → {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
