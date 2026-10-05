"""Render real command output as a terminal-style PNG for charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md.
Every line shown is the command as run and its captured output; nothing is typed by hand."""
import html, sys, pathlib
from playwright.sync_api import sync_playwright

def page(title, caption, blocks):
    parts = []
    for cmd, out in blocks:
        parts.append(f'<div class="cmd">$ {html.escape(cmd)}</div><pre class="out">{html.escape(out.rstrip())}</pre>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#f6f5f2;font-family:-apple-system,Segoe UI,sans-serif}}
.wrap{{padding:24px;width:1180px}}
h1{{font-size:18px;margin:0 0 4px;color:#1d1d1f}} .cap{{font-size:13px;color:#555;margin:0 0 14px}}
.term{{background:#1e1f22;border-radius:8px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.2)}}
.cmd{{font:600 13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#8fd18f;white-space:pre-wrap;margin-top:10px}}
.cmd:first-child{{margin-top:0}}
.out{{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#e6e6e6;margin:2px 0 0;white-space:pre-wrap}}
</style></head><body><div class="wrap"><h1>{html.escape(title)}</h1><p class="cap">{html.escape(caption)}</p>
<div class="term">{''.join(parts)}</div></div></body></html>"""

def render(out_png, title, caption, blocks):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1228, "height": 400})
        pg.set_content(page(title, caption, blocks)); pg.locator(".wrap").screenshot(path=out_png); b.close()

if __name__ == "__main__":
    E = pathlib.Path(sys.argv[1]); out = sys.argv[2]
    rd = lambda n: (E / n).read_text()
    render(out, "A successful six-hourly backup",
           f"CRC lab, chart 0.58.3 / application 0.36.0, captured {rd('captured-at.txt').strip()}. "
           "The commands are the runbook's; the output is the pod's, unedited.",
           [("oc logs -n $NS deploy/$REL -c dashboard | grep 'backup written' | tail -1", rd("1-log.txt")),
            ("oc exec -n $NS deploy/$REL -c dashboard -- ls -l /data/backup", rd("2-ls.txt")),
            ("oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c '<the §1 check>' /data/backup/gsd-20260926T191426.213034Z.db", rd("4-verify.txt")),
            ("oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/metrics\").read().decode())' | grep '^gsd_backup'", rd("3-metrics.txt"))])
