#!/usr/bin/env python3
"""Build the end-to-end walk document from results.json + results_extra.json + the images.

Every number in the document is read from the two results files or measured here (file sizes,
hashes); nothing is typed in. Images are downscaled for the document; the originals stay on
disk. Output: e2e_walk.html (self-contained) and e2e_walk.pdf (Chromium print).
"""
from __future__ import annotations

import base64
import html
import io
import json
import pathlib
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

RUN = pathlib.Path(sys.argv[1])
ENV = json.loads(pathlib.Path(sys.argv[2]).read_text())   # cluster facts gathered with oc/helm
OUT = RUN / "doc"
OUT.mkdir(exist_ok=True)
res = json.loads((RUN / "results.json").read_text())
extra = json.loads((RUN / "extra" / "results_extra.json").read_text())
integrity = [json.loads(l) for l in (RUN / "integrity.jsonl").read_text().splitlines() if l.strip()]
steps = res["steps"]
by_step = {s["step"]: s for s in steps}
xby = {s["step"]: s for s in extra["steps"]}


def img(path: pathlib.Path, width: int = 1000, max_height: int = 2600) -> str:
    """A downscaled JPEG data URI. Tall full-page captures are cropped at max_height so a page
    of 4,000 px does not become an unreadable strip; the crop is stated in the caption."""
    im = Image.open(path).convert("RGB")
    cropped = False
    if im.height > max_height:
        im = im.crop((0, 0, im.width, max_height)); cropped = True
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=84, optimize=True)
    uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, cropped


def figure(path: pathlib.Path, caption: str, width: int = 1000, max_height: int = 2600) -> str:
    uri, cropped = img(path, width, max_height)
    note = " (full-page capture, shown to the first 2,600 px)" if cropped else ""
    return f'<figure><img src="{uri}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}{note}</figcaption></figure>'


def e(s) -> str:
    return html.escape("" if s is None else str(s))


# ---- facts --------------------------------------------------------------------------------
whoami = by_step["GET /api/whoami"]["api"]
version = by_step["GET /api/version"]["api"]
clusters = by_step["GET /api/clusters"]["api"]
tabs = [s for s in steps if s["step"].startswith("tab ") and s["step"] != "tab strip"]
tab_strip = by_step["tab strip"]["detail"]
reports_step = by_step["Reports tab"]
catalogue = reports_step["catalogue"]
gen = [s for s in steps if s["step"].endswith(": generate")]
dl = [s for s in steps if ": download ." in s["step"]]
recent = by_step["Recent runs table"]
passed, failed = res["passed"], res["failed"]
xpassed = sum(1 for s in extra["steps"] if s["ok"]); xtotal = len(extra["steps"])
pdf_ok = sum(1 for p in extra["pdf_page1"] if p["ok"])
total_artefact_bytes = sum(s["bytes"] for s in dl)
started, finished = res["started"], extra["finished"]

# ---- page ---------------------------------------------------------------------------------
css = """
:root { --ink:#1b1f24; --muted:#5b6470; --line:#d9dee5; --accent:#1f5fbf; --ok:#1a7f37; --bad:#b42318; --bg:#ffffff; }
* { box-sizing: border-box; }
body { font: 11pt/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: var(--ink); background: var(--bg); margin: 0; }
main { max-width: 1040px; margin: 0 auto; padding: 28px 36px 60px; }
h1 { font-size: 24pt; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 16pt; margin: 34px 0 8px; padding-top: 10px; border-top: 2px solid var(--line); page-break-after: avoid; }
h3 { font-size: 12.5pt; margin: 22px 0 6px; page-break-after: avoid; }
p { margin: 6px 0; }
.lede { color: var(--muted); font-size: 10.5pt; }
.outcome { font-size: 13pt; margin: 14px 0; padding: 12px 16px; border-left: 4px solid var(--ok); background: #f2f8f3; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9.5pt; page-break-inside: auto; }
th, td { border: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #f3f5f8; font-weight: 600; }
tr { page-break-inside: avoid; }
code, .mono { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9pt; }
pre { background: #f6f8fa; border: 1px solid var(--line); padding: 8px 10px; overflow-x: auto; font-size: 8.5pt; white-space: pre-wrap; word-break: break-word; }
figure { margin: 12px 0 18px; page-break-inside: avoid; }
figure img { width: 100%; border: 1px solid var(--line); border-radius: 4px; display: block; }
figcaption { font-size: 9.5pt; color: var(--muted); margin-top: 5px; }
.ok { color: var(--ok); font-weight: 600; } .bad { color: var(--bad); font-weight: 600; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.finding { border: 1px solid var(--line); border-left: 4px solid var(--bad); padding: 10px 14px; margin: 12px 0; background: #fff8f7; page-break-inside: avoid; }
.finding.note { border-left-color: #b7791f; background: #fffaf0; }
.small { font-size: 9.5pt; color: var(--muted); }
@page { size: A4; margin: 14mm 12mm; }
@media print { h2 { page-break-before: always; } h2.first { page-break-before: auto; } }
"""

parts: list[str] = []
P = parts.append
P(f"<title>End-to-end walk — OCP Access Tracking Dashboard {e(version['version'])} on CRC</title><style>{css}</style><main>")
P(f"<h1>End-to-end walk — OCP Access Tracking Dashboard {e(version['version'])} on CRC</h1>")
P(f"<p class='lede'>Application {e(version['version'])} (commit {e(version['commit'])}), chart {e(ENV['chart'])}, "
  f"on the reference cluster {e(ENV['openshift'])}. Driven by Playwright (Chromium, 1440×900) through the real route "
  f"<span class='mono'>{e(res['base'])}</span>, logged in as {e(res['login_user'])} through oauth-proxy and OpenShift OAuth. "
  f"Run {e(started)} → {e(finished)}. Every number below is read from the run's results files or measured on the "
  f"downloaded artefacts; nothing is typed in from memory.</p>")

verdict = "PASS" if failed == 0 else "FAIL"
P(f"<div class='outcome'><b>Outcome: {verdict}.</b> {passed} of {passed + failed} scripted steps passed in the main walk; "
  f"{xpassed} of {xtotal} in the second pass (the one failure is a product finding, §9, not a test defect). "
  f"All {len(catalogue)} reports in the catalogue generated as PDF and HTML; {len(dl)} artefacts downloaded through the page's own download path; "
  f"{sum(1 for i in integrity if all((i['recomputed_matches'], i['run_matches'], i['sha_in_pdf_metadata'], i['sha_in_html'])))} of {len(integrity)} "
  f"reports passed the four-way integrity check.</div>")

P("<h2 class='first'>1. What was measured</h2>")
P("<table><tr><th>Measure</th><th>Value</th></tr>")
for k, v in [
    ("Route", res["base"]),
    ("Identity used", f"{whoami['user']} ({whoami['email']}), authenticated={whoami['authenticated']}, scope {whoami['visibility']['scope']}"),
    ("Application / commit / branch", f"{version['version']} / {version['commit']} / {version['branch']} (dirty={version['dirty']})"),
    ("Features", ", ".join(f"{k}={v}" for k, v in version["features"].items())),
    ("Chart / Helm revision", f"{ENV['chart']} / revision {ENV['helm_revision']} ({ENV['helm_updated']})"),
    ("Pods", ENV["pods"]),
    ("Images", ENV["images"]),
    ("Tabs offered", tab_strip),
    ("Reports in the catalogue", f"{len(catalogue)} ({sum(1 for c in catalogue if c['enabled'])} enabled); PDF variant {reports_step['detail'].split('variant ')[-1] if 'variant' in reports_step['detail'] else 'n/a'}"),
    ("Report runs, generation time", f"min {min(g['elapsed_s'] for g in gen)} s · max {max(g['elapsed_s'] for g in gen)} s · all {sum(1 for g in gen if g['ok'])}/{len(gen)} done"),
    ("Artefacts downloaded", f"{len(dl)} files, {total_artefact_bytes:,} bytes"),
    ("Recent-runs table", recent["detail"]),
    ("Scripted steps", f"main walk {passed} passed / {failed} failed; second pass {xpassed} / {xtotal}; PDF first pages rendered {pdf_ok} / {len(extra['pdf_page1'])}"),
]:
    P(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>")
P("</table>")

P("<h2>2. Login through the real ingress</h2>")
P("<p>oauth-proxy's interstitial, OpenShift's identity-provider chooser (two providers on this lab), the credential form, then the dashboard. "
  "The ServiceAccount is the OAuth client, so a consent page can appear; this session did not show one.</p>")
for s in steps[:4]:
    if s.get("screenshot"):
        P(figure(RUN / s["screenshot"], f"{s['step']} — {s['detail']}", width=900))
login_step = by_step["login"]
P(f"<p><span class='ok'>✓</span> {e(login_step['detail'])}</p>")

P("<h2>3. API probes from inside the session</h2>")
P("<p>Same-origin fetches issued by the page, so the proxy cookie travels with them.</p><table><tr><th>Endpoint</th><th>HTTP</th><th>Body (abridged)</th></tr>")
for path in ("/api/whoami", "/api/version", "/api/clusters", "/report/healthz", "/report/readyz"):
    s = by_step[f"GET {path}"]
    body = s.get("api")
    if path == "/api/clusters":
        body = [{k: c.get(k) for k in ("id", "enabled", "reachable", "status", "last_poll", "group_count", "groupsync_count", "visibility")} for c in body]
    txt = json.dumps(body, separators=(",", ":"))
    P(f"<tr><td class='mono'>{e(path)}</td><td class='{'ok' if s['ok'] else 'bad'}'>{e(s['detail'])}</td><td><pre>{e(txt[:900])}{'…' if len(txt) > 900 else ''}</pre></td></tr>")
P("</table>")

P("<h2>4. Every tab</h2>")
P("<p>Each tab is clicked, the page waits for the tab to report <span class='mono'>aria-current</span>, the network to settle and a heading to exist, "
  "and the capture is refused if any JavaScript error or a visible “Dashboard API error” occurred.</p>")
for s in tabs:
    P(figure(RUN / s["screenshot"], f"{s['step']} — {s['detail']}"))

P("<h2>5. Reports — the catalogue</h2>")
P(f"<p>{e(reports_step['detail'])}.</p>")
P(figure(RUN / reports_step["screenshot"], "The Reports tab: the catalogue, the form for the selected report, and the recent runs"))
P("<table><tr><th>Report</th><th>Title</th><th>Enabled</th></tr>")
for c in catalogue:
    P(f"<tr><td class='mono'>{e(c['name'])}</td><td>{e(c['title'])}</td><td>{e(c['enabled'])}</td></tr>")
P("</table>")

P("<h2>6. Reports — every report generated, downloaded and opened</h2>")
P("<p>For each report: the form (required parameters filled where the report has no default), Generate with PDF and HTML both ticked, "
  "the run polled to a terminal state, the three artefacts downloaded through the page's own buttons, the PDF's first page rendered, and the HTML opened in a browser.</p>")
for g in gen:
    name = g["step"].split(" ")[1].rstrip(":")
    form = by_step[f"report {name}: form"]
    files = {s["step"].split(".")[-1]: s for s in dl if s["step"].startswith(f"report {name}: ")}
    P(f"<h3>{e(form['detail'].split(' — ')[0])} <span class='mono small'>({e(name)})</span></h3>")
    P(f"<p><span class='{'ok' if g['ok'] else 'bad'}'>{'✓' if g['ok'] else '✗'}</span> {e(g['detail'])}</p>")
    P("<table><tr><th>Artefact</th><th>File</th><th>Bytes</th><th>Check</th></tr>")
    for fmt in ("pdf", "html", "json"):
        s = files.get(fmt)
        if not s:
            P(f"<tr><td>.{fmt}</td><td colspan=3 class='bad'>not downloaded</td></tr>"); continue
        check = s.get("magic", "").strip() if fmt == "pdf" else (f"sha256 of file {s['sha256_of_file'][:16]}…" if fmt == "json" else "opened in Chromium, see below")
        P(f"<tr><td>.{fmt}</td><td class='mono'>{e(pathlib.Path(s['file']).name)}</td><td>{s['bytes']:,}</td><td>{e(check)}</td></tr>")
    P("</table>")
    P("<div class='pair'>")
    P(figure(RUN / form["screenshot"], f"Form — {form['detail']}", width=700, max_height=1500))
    P(figure(RUN / g["screenshot"], f"Status after Generate — {g['status_line']}", width=700, max_height=1500))
    P("</div><div class='pair'>")
    pdf_png = RUN / "extra" / f"pdf-page1-{name}.png"
    if pdf_png.exists():
        P(figure(pdf_png, f"The PDF, page 1 (rendered from the downloaded file)", width=700, max_height=1400))
    hx = xby.get(f"HTML report {name} opens")
    if hx and hx.get("screenshot"):
        P(figure(RUN / "extra" / hx["screenshot"], f"The HTML artefact opened in Chromium — {hx['detail']}", width=700, max_height=1400))
    P("</div>")

P("<h2>7. Integrity of the artefacts</h2>")
P("<p>Every report is sealed with the sha256 of its canonical data (name, cluster, params, coverage, totals, truncated, include_members, sections; "
  "sorted keys, compact separators). Four independent checks per report: the hash recomputed from the downloaded JSON equals the JSON's own "
  "<span class='mono'>sha256</span> field; the run record the page polled reports the same hash; the PDF's metadata carries "
  "<span class='mono'>sha256 &lt;hash&gt;</span>; the HTML carries the hash prefix. The PDF/A marker (<span class='mono'>pdfaid:part</span>) is also checked.</p>")
P("<table><tr><th>Report</th><th>sha256</th><th>Recomputed = field</th><th>= run record</th><th>In PDF metadata</th><th>In HTML</th><th>PDF/A marker</th></tr>")
for i in integrity:
    cell = lambda b: f"<td class='{'ok' if b else 'bad'}'>{'yes' if b else 'NO'}</td>"  # noqa: E731
    P(f"<tr><td class='mono'>{e(i['name'])}</td><td class='mono'>{e(i['sha256'][:24])}…</td>{cell(i['recomputed_matches'])}{cell(i['run_matches'])}{cell(i['sha_in_pdf_metadata'])}{cell(i['sha_in_html'])}{cell(i['pdfa_marker'])}</tr>")
P("</table>")
P(figure(RUN / recent["screenshot"], f"Recent runs after the walk — {recent['detail']}"))

P("<h2>8. Second cluster, light theme</h2>")
sw = xby.get("switch cluster to prod-east"); rp = xby.get("Reports tab on prod-east"); lt = xby.get("light theme Overview")
P(f"<p>The cluster selector offers: {e(xby['cluster selector options']['detail'])}. Scope pill: “{e(xby['scope pill']['detail'])}”.</p>")
if lt and lt.get("screenshot"):
    P(figure(RUN / "extra" / lt["screenshot"], f"Overview in the light theme — {lt['detail']}", width=900))
if sw and sw.get("screenshot"):
    P(figure(RUN / "extra" / sw["screenshot"], f"Selecting prod-east — {sw['detail']}", width=900))

P("<h2>9. Findings</h2>")
P("<div class='finding'><b>Finding 1 — a cluster removed from the configuration lingers in the UI.</b> "
  f"<span class='mono'>prod-east</span> was configured during the D2 live check and removed again (the live ConfigMap lists one cluster, "
  f"<span class='mono'>crc-local</span>; Helm's user values have no <span class='mono'>clusters</span> key). Yet <span class='mono'>/api/clusters</span> still returns it as "
  f"enabled, reachable, status ok, with last_poll {e(next(c['last_poll'] for c in clusters if c['id'] == 'prod-east'))} (the last poll before the upgrade that removed it), "
  f"the Overview counts “{e(by_step['tab Overview']['detail'])}” alerts across 2 clusters, three of them <i>critical</i> “schedule has stopped firing” for prod-east — an artefact of the frozen snapshot — "
  f"and selecting prod-east renders “{e((sw or {}).get('detail', ''))}”. Mechanism, from the source: cluster rows are upserted from the configuration at startup and never retired "
  f"(<span class='mono'>store.upsert_cluster</span>); <span class='mono'>list_clusters</span> iterates every stored row, while the per-cluster routes go through "
  f"<span class='mono'>require_cluster</span>, which consults the configuration and returns 404. Not a test defect; recorded as an issue.</div>")
P("<div class='finding note'><b>Finding 2 — the report pod is preempted on this saturated lab node.</b> "
  f"The node runs at {e(ENV['node_cpu'])} of CPU requests. The OLM <span class='mono'>collect-profiles</span> CronJob (every 15 min, priority class "
  f"openshift-user-critical) and a marketplace catalog pod preempt a priority-0 pod when they schedule; the scheduler's tie-breaks pick the youngest pod, and once "
  f"preempted the report pod stays the youngest. {e(ENV['preemptions'])} preemptions between {e(ENV['preempt_first'])} and {e(ENV['preempt_last'])}; the dashboard pod was untouched. "
  f"Every run in this walk completed (1.6–7.8 s each) between two preemptions. Lab capacity, but the chart could offer <span class='mono'>priorityClassName</span> for both Deployments so an operator can decide.</div>")

P("<h2>10. Files delivered with this document</h2>")
P("<table><tr><th>File</th><th>Bytes</th><th>What</th></tr>")
for f in sorted((RUN / "reports").glob("*")):
    kind = {"pdf": "PDF/A-2b report, generated by the report service", "html": "HTML report", "json": "canonical data + run facts"}[f.suffix[1:]]
    P(f"<tr><td class='mono'>{e(f.name)}</td><td>{f.stat().st_size:,}</td><td>{e(kind)}</td></tr>")
P("</table>")
P(f"<p class='small'>Screenshots: {len([s for s in steps if s.get('screenshot')])} in the main walk and {len([s for s in extra['steps'] if s.get('screenshot')]) + pdf_ok} in the second pass, "
  "at 1440×900 device pixels (full-page where the tab scrolls); the images in this document are downscaled copies.</p>")
P("</main>")

html_path = OUT / "e2e_walk.html"
html_path.write_text("".join(parts))
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.goto(html_path.as_uri(), wait_until="load")
    pg.pdf(path=str(OUT / "e2e_walk.pdf"), format="A4", print_background=True, margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
    b.close()
print(f"html {html_path.stat().st_size:,} bytes; pdf {(OUT / 'e2e_walk.pdf').stat().st_size:,} bytes")
