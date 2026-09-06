"""The reporting image proves itself, as the runtime user, on the finished filesystem.

Beyond image-proof.py's checks (module imports, the removals, the RPM directory): the report extra
imports under THIS interpreter; a PDF/A-2b document renders from the vendored font and carries the
XMP conformance marker and an embedded font; a VACUUM INTO copy of a WAL database opens with
immutable=1 and refuses a write. Every one is a thing the base or a dependency change could break
silently, and every one fails the build.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys

import croniter, fastapi, gsd, httpx, prometheus_client, uvicorn, yaml  # noqa: E401,F401
import fpdf, PIL, fontTools  # noqa: E401,F401
import jinja2, markupsafe  # noqa: E401,F401 — the HTML templates' engine and its escaping
from gsd.reporting import ticket  # noqa: F401 — importable without opening anything

REMOVED = ("/usr/lib64/libuuid.so.1", "/usr/share/python-wheels", "/usr/lib/python3.14/site-packages/pip",
           "/usr/share/bash-completion/completions/pip3.14", "/rpmdb-erased-files", "/rpmdb-erased-dirs")


def must_not_import(name: str, reason: str) -> None:
    try:
        __import__(name)
    except ImportError:
        return
    sys.exit(f"{name} is still importable: {reason}")


def main() -> None:
    must_not_import("_uuid", "libuuid was not removed")
    must_not_import("pip", "pip was not removed")
    for path in REMOVED:
        if os.path.lexists(path):
            sys.exit(f"still present: {path}")
    if sorted(os.listdir("/usr/lib/sysimage/rpm")) != [".rpm.lock", "rpmdb.sqlite"]:
        sys.exit("the RPM database directory does not hold the base's two files")

    # A PDF/A-2b document from the vendored font, under this interpreter.
    from fpdf import FPDF
    from fpdf.enums import DocumentCompliance
    regular, bold = os.environ["GSD_REPORT_FONT_REGULAR"], os.environ["GSD_REPORT_FONT_BOLD"]
    for f in (regular, bold):
        if not os.path.isfile(f):
            sys.exit(f"font missing: {f}")
    pdf = FPDF(enforce_compliance=DocumentCompliance.PDFA_2B)
    pdf.add_font("Body", "", regular)
    pdf.add_font("Body", "B", bold)
    pdf.set_title("proof"); pdf.set_lang("en-US")
    pdf.add_page(); pdf.set_font("Body", size=10)
    with pdf.table() as t:
        for r in (("a", "b"), ("1", "2")):
            row = t.row()
            for c in r:
                row.cell(c)
    data = bytes(pdf.output())
    if not data.startswith(b"%PDF") or b"/FontFile2" not in data or not re.search(rb"<pdfaid:part>2</pdfaid:part>", data):
        sys.exit("the PDF/A-2b proof document is not what fpdf2 produced on the development machine")

    # A VACUUM INTO copy opens read-only with immutable=1 and refuses a write.
    live = "/artifacts/.proof-live.db"
    conn = sqlite3.connect(live)
    if conn.execute("pragma journal_mode=wal").fetchone() != ("wal",):
        sys.exit("WAL mode did not take on /artifacts")
    conn.execute("create table t(x)"); conn.execute("insert into t values(1)"); conn.commit()
    copy = "/artifacts/gsd-19700101T000000.000000Z.db"
    conn.execute(f"VACUUM INTO '{copy}'"); conn.close()
    ro = sqlite3.connect(f"file:{copy}?immutable=1&mode=ro", uri=True)
    if ro.execute("select count(*) from t").fetchone()[0] != 1:
        sys.exit("the copy does not carry the row")
    try:
        ro.execute("insert into t values(2)")
        sys.exit("a write to the immutable copy SUCCEEDED")
    except sqlite3.OperationalError:
        pass
    ro.close()
    for name in os.listdir("/artifacts"):
        os.remove(os.path.join("/artifacts", name))
    if os.listdir("/artifacts"):
        sys.exit("/artifacts is not empty after the proof")
    print("report image proof OK; fpdf2", fpdf.__version__, "sqlite", sqlite3.sqlite_version, "pdf bytes", len(data))


if __name__ == "__main__":
    main()
