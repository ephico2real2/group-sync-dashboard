# Benchmarking the dashboard's browser rendering

Written because the Logins tab was reported as freezing. It is a runnable procedure, not a
description: every command below can be pasted, and the numbers in §6 are what the reference
cluster produced on 2026-08-10 so a future run has something to compare against.

**The finding, stated up front so nobody repeats the search:** at the reference cluster's data
volume (67 login rows, 65 groups, 236 bindings) **no freeze is reproducible.** A full
fetch-and-render is 34–61 ms per tab and `render()` alone is 0.5–1.3 ms. Two real inefficiencies
were found anyway and are recorded in §7.

**The pause, diagnosed (2026-08-10, §6a):** the reported symptom — "tabs just slightly don't
respond, some sort of pause, not a total freeze" — was never a freeze and never the server. A
tab click ran `navigate(); refresh();`, refresh() dimmed the OLD tab and then awaited four to
six endpoints one at a time before the destination could paint. With 40 ms of per-request
latency (the proxy path) the destination's first paint measured at median **271–337 ms** after
the click, with nothing on screen in between but the departing page at 0.55 opacity. Painting
the destination before the fetch and dispatching the fetches together brought first paint to
**2–4 ms** and settled content to roughly one round trip. §6a has the metric definitions and
the before/after table.

Measure in this order. Each step rules out a layer, and stopping early is how you end up
optimising the wrong one.

---

## 0. Set these once

```bash
NS=group-sync-dashboard
REPO=/Users/olasumbo/gitRepos/group-sync-dashboard          # or your checkout
PY=$REPO/local-development/.venv/bin/python                  # the venv, not system python
WORK=/tmp/gsd-bench                                          # scratch; anywhere writable
mkdir -p "$WORK"
POD=$(oc get pods -n $NS -l app.kubernetes.io/name=group-sync-dashboard -o name | head -1)
echo "pod: $POD"
```

## 1. The API, from inside the pod — is the server slow at all?

This is first because it is the cheapest and it eliminates the whole backend if it comes back
fast. Inside the pod there is no proxy and no TLS, so what you measure is the application.

```bash
for EP in "/api/clusters/crc-local/logins?limit=200" \
          "/api/clusters/crc-local/cluster-access" \
          "/api/clusters/crc-local/groups?state=all" \
          "/api/dashboard/activity"; do
  echo -n "  $EP  "
  oc exec -n $NS "$POD" -c dashboard -- sh -c "
    for i in 1 2 3; do
      curl -s -o /dev/null -w '%{time_total} ' -H 'X-Forwarded-User: john.doe' 'localhost:8080$EP'
    done"
  echo
done
```

**Reading it:** the *first* number is much larger than the rest. That is not the endpoint — it is
the visibility tier being resolved (a SubjectAccessReview plus a group read, ~97 ms on the
reference cluster) and then cached for `visibility.tierTtlSeconds`. Warm calls are the endpoint.

## 2. The route — does the proxy or TLS add the cost?

```bash
TOK=$(oc whoami -t)
HOST=$(oc get route -n $NS -o jsonpath='{.items[0].spec.host}')
for EP in "/api/clusters/crc-local/logins?limit=200" "/api/clusters/crc-local/groups?state=all" \
          "/api/clusters" "/api/alerts" "/api/whoami"; do
  curl -sk -o /dev/null -w "  %{size_download} bytes  %{time_total}s  $EP\n" \
    -H "Authorization: Bearer $TOK" "https://$HOST$EP"
done
```

A bearer token works here only when `oauthProxy.apiTokenAccess.enabled` is true **and** the
caller can `list clusterrolebindings` — that is the proxy's own `-openshift-delegate-urls` gate,
not ours. An ordinary user gets 403 with an HTML login page as the body; that is the proxy
refusing, not the dashboard. Check the body before concluding anything.

## 3. The database — is a query or a missing index the cost?

```bash
oc exec -n $NS "$POD" -c dashboard -- python3.14 - <<'EOF'
import sqlite3
c = sqlite3.connect("/data/gsd.db")
for t in ("login_event", "group_member", "rbac_group_binding", "dashboard_user_activity"):
    print(f"{t:26s} {c.execute(f'select count(*) from {t}').fetchone()[0]:>8d} rows")
print()
for r in c.execute("select name, sql from sqlite_master where type='index' and tbl_name='login_event'"):
    print(" ", r[0], "|", r[1] or "implicit")
EOF
```

## 4. Take a snapshot of the live database

To measure the browser you need the real data volume locally. Two traps here, both hit for real:

* **Do not `cp` the file.** It is a live WAL database; a raw copy can be torn. Use SQLite's own
  `backup`, which takes a consistent snapshot of a database being written to.
* **`oc cp` failed** on this pod (exit 255). Base64 through `exec` is slower but reliable.

```bash
oc exec -n $NS "$POD" -c dashboard -- python3.14 -c "
import sqlite3
src = sqlite3.connect('/data/gsd.db'); dst = sqlite3.connect('/tmp/snap.db')
src.backup(dst); dst.close(); print('snapshot taken')"

oc exec -n $NS "$POD" -c dashboard -- base64 /tmp/snap.db | base64 -d > "$WORK/live-snap.db"

$PY - <<EOF
import sqlite3
c = sqlite3.connect("$WORK/live-snap.db")
for t in ("login_event", "group_member", "rbac_group_binding"):
    print(f"  {t:22s}", c.execute(f"select count(*) from {t}").fetchone()[0], "rows")
EOF
```

The snapshot contains real usernames and login records. It is lab data; keep it local and delete
it when you are done (`rm "$WORK/live-snap.db"`).

## 5. The benchmark

Save as `$WORK/bench_render.py`. It serves the app locally against the snapshot with the
oauth-proxy **off** (so no OAuth flow is needed and every view renders wide), drives a real
Chromium, and times each tab from **inside the page** with `performance.now()`.

```python
"""Time the dashboard's per-tab fetch+render against a snapshot of real data.

Measured from inside the page, not with Playwright selector waits: a selector wait tells you when
one element appeared, which is not the same as when the tab finished, and it silently succeeds on
an element left over from the previous tab.
"""
import os, socket, sys, threading, time, warnings

warnings.filterwarnings("ignore")

REPO = os.environ.get("REPO", "/Users/olasumbo/gitRepos/group-sync-dashboard")
DB = os.environ["SNAPSHOT"]                      # $WORK/live-snap.db
sys.path.insert(0, f"{REPO}/local-development")

import httpx
import uvicorn

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings

settings = Settings(
    clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
    db_path=DB,
    oauth_proxy_enabled=False,     # no proxy => no OAuth, and every view renders wide
)

sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
threading.Thread(
    target=uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False),
        host="127.0.0.1", port=port, log_level="error")).run,
    daemon=True,
).start()

base = f"http://127.0.0.1:{port}"
for _ in range(100):
    try:
        if httpx.get(base + "/healthz", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    raise SystemExit("the app never became ready")

from playwright.sync_api import sync_playwright

TABS = ("overview", "groups", "bindings", "policy", "nsaudit", "logins", "usage")

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page()
    page.goto(base)
    page.wait_for_selector("button[data-nav='groups']")
    page.wait_for_timeout(600)          # let the first load settle

    print("  tab        fetch+render ms   tbody rows   #main nodes")
    for tab in TABS:
        r = page.evaluate("""async (tab) => {
            view.page = tab; view.cluster = 'crc-local';
            const t0 = performance.now();
            // {} and NOT {auto: true}: an automatic refresh may legally skip render() when
            // the payload fingerprint is unchanged (index.html, 2026-08-10), so {auto: true}
            // here would time fetch-without-render on every revisit. A manual refresh
            // always paints.
            await refresh({});
            const total = performance.now() - t0;
            const m = document.getElementById('main');
            return {total,
                    rows: m.querySelectorAll('tbody tr').length,
                    nodes: m.querySelectorAll('*').length};
        }""", tab)
        print(f"  {tab:10s} {r['total']:13.0f}   {r['rows']:>10d}   {r['nodes']:>10d}")

    print()
    print("  render() alone, no network:")
    for tab in TABS:
        ms = page.evaluate("""(tab) => {
            view.page = tab; view.cluster = 'crc-local';
            const t0 = performance.now(); render(); return performance.now() - t0;
        }""", tab)
        print(f"    {tab:10s} {ms:6.1f} ms")

    browser.close()
```

Run it:

```bash
cd "$REPO/local-development"          # so the gsd package and playwright browsers resolve
SNAPSHOT="$WORK/live-snap.db" REPO="$REPO" $PY "$WORK/bench_render.py"
```

If Chromium is missing: `$PY -m playwright install chromium`.

## 6. Baseline — the reference cluster, 2026-08-10

67 login rows, 65 groups, 236 bindings, 630 KB database.

| tab | fetch + render | tbody rows | `#main` nodes |
|---|---|---|---|
| overview | 34 ms | 14 | 200 |
| groups | 38 ms | 65 | 660 |
| bindings | 61 ms | 16 | 191 |
| policy | 49 ms | 18 | 192 |
| nsaudit | 52 ms | 14 | 237 |
| logins | 47 ms | 4 | 110 |
| usage | 37 ms | 0 | 6 |

`render()` alone: **0.5–2.7 ms** for every tab.

Expect roughly ±20% run to run — a second run of this same script gave 31/36/60/46/55/54/40 ms for
the table above, and `groups` moved from 1.3 to 2.7 ms on `render()`. Treat a number as meaningful
only if it is several times the baseline, not tens of percent above it.

Server side, for the same run: every endpoint 5–15 ms warm inside the pod, 120–250 ms on the
first call of a tier interval; through the route, `/logins` is the largest payload at 25 KB and
~45 ms warm.

**Nothing here freezes.** A run that reproduces a freeze should show it as a large
`fetch+render`, or as a large `render()` alone if the cost is in the DOM rather than the network.

## 6a. Timing a TAB CLICK — three numbers, not one (2026-08-10)

§5 times `refresh()` end to end, which is the right number for "is anything slow?" and the
wrong one for "did the click respond?". A click produces three separately perceptible moments,
and one metric that conflates them will report whatever the conflation happens to hit:

| metric | definition | what the reader experiences |
|---|---|---|
| **t_any** | first DOM change of any kind after `button.click()` | "the click registered" — but before the fix this was the OLD tab dimming, feedback of the wrong page |
| **t_dest** | first paint that IS the destination: `body[data-page]` equals the target (renderFilters sets it only inside `render()`) and `#main`'s children changed | the destination's own chrome/layout on screen — `Loading…` if its data is not cached, the full table if it is |
| **t_content** | first destination paint with rows and no `Loading…` | the data the reader came for |
| **t_settled** | the last childList change in a 2.5 s window | everything done, refetch repaint included |

**Why this is trustworthy where the first attempt was not.** One clock: t0 is
`performance.now()` taken in-page immediately before `button.click()` — click dispatches
synchronously, so the handler runs inside that call — and every timeline entry is
`performance.now()` in the same page. Nothing to satisfy early: a MutationObserver on `#main`
and `#filters` records *every* change (childList, attributes, characterData) with a snapshot of
`body[data-page]`, `#main` length, row count, `Loading…` presence; classification into the
metrics happens afterwards, offline, so no wait condition can be met by the previous tab's
leftovers — or by the pre-fetch paint (§8). Honest about pixels: observer callbacks run as
microtasks, so their timestamp is "the change existed and the task yielded"; each snapshot also
logs the next `requestAnimationFrame` timestamp (`t_*_frame`), and DOM time + frame time
bracket the paint. Cached and uncached destinations are separate scenarios. Ten iterations,
fresh page per iteration, medians reported.

Two environments per variant, because loopback (~1 ms/request) hides everything a route costs:
plain loopback, and loopback plus an ASGI middleware sleeping 40 ms on every `/api/*` request —
a stand-in for the proxy+TLS path, sized from §2's warm route numbers.

The in-page instrument, verbatim (install after load, then call `click(tab)` and read `take()`
after a settle):

```js
window.__bench = (() => {
  const log = [];
  let t0 = null, preLen = null;
  const snap = (kind) => {
    const m = document.getElementById('main');
    log.push({ t: performance.now(), kind,
               bodyPage: document.body.dataset.page || null,
               len: m.innerHTML.length,
               rows: m.querySelectorAll('tbody tr').length,
               loading: m.innerHTML.includes('Loading…') });
    requestAnimationFrame(() => log.push({ t: performance.now(), kind: 'frame' }));
  };
  const mo = new MutationObserver((recs) => {
    const child = recs.some((r) => r.type === 'childList' || r.type === 'characterData');
    snap(child ? 'dom' : 'attr');
  });
  const opts = { subtree: true, childList: true, attributes: true, characterData: true };
  mo.observe(document.getElementById('main'), opts);
  mo.observe(document.getElementById('filters'), opts);
  return {
    click(tab) {
      preLen = document.getElementById('main').innerHTML.length;
      log.length = 0;
      const b = document.querySelector(`button[data-nav='${tab}']`);
      t0 = performance.now();
      b.click();
      return t0;
    },
    take() { return { t0, preLen, log: log.slice() }; },
  };
})();
```

### The numbers — medians of 10, 2026-08-10, seeded at the reference volume

The live snapshot had been deleted per §4's cleanup note, so the volumes (65 groups, 236
bindings, 67 logins, 14 CRs) were re-seeded synthetically through the Store API — identical
volumes, not identical bytes, which is fine because every comparison is within one seeded DB.

`overview → logins` (cold = first visit, nothing cached) and `nsaudit ↔ logins` (warm = data
cached from an earlier visit) — the reporter's own pair. **before** = `navigate(); refresh();`
(serial fetches, render at the end); **paint-first** = render() before refresh() plus the
fingerprint skip and the 60 s poll, alone; **final** = paint-first plus parallel dispatch, the
150 ms `.stale` delay, no dim on auto cycles, and cluster-switch cache invalidation.

With 40 ms per-request latency (the proxy-path stand-in):

| scenario | metric | before | paint-first | final |
|---|---|---|---|---|
| logins cold | t_dest | **337 ms** | 2.7 ms | 3.6 ms |
| logins cold | t_content | 337 ms | 335 ms | **147 ms** |
| nsaudit cold | t_dest | **274 ms** | 2.2 ms | 2.8 ms |
| nsaudit cold | t_content | 274 ms | 271 ms | **118 ms** |
| logins warm | t_dest = t_content | **315 ms** | 4.0 ms | 4.9 ms |
| logins warm | t_settled (refetch repaint) | 315 ms | 318 ms | **126 ms** |
| nsaudit warm | t_dest = t_content | **272 ms** | 3.7 ms | 4.4 ms |

On plain loopback the same clicks: before t_dest 71–95 ms, paint-first/final t_dest 2–5 ms,
t_content cold 70–100 ms in all three variants (the fetch is the floor and loopback fetches are
already instant; parallel neither helps nor hurts there, per §7).

t_any tells the cautionary tale: it was **0.6–1.7 ms in the BEFORE runs too** — the `.stale`
dim of the departing tab is a DOM change within two frames of the click. The click always
"registered"; it registered as the old page fading, which readers experience as the pause. Any
metric that stops at "first visible change" calls the before behaviour fine. That, plus the
heading-wait blindness in §8, is how a working fix measured as no improvement.

Warm switches — the common case after the first minute — now paint complete content in under
5 ms against a previous ~300 ms, and cold first visits show the destination immediately and its
data in roughly one round trip instead of four to six.

## 7. What the exercise found anyway

Two things, neither of which needed a freeze to justify fixing:

1. **The 30 s poll was unguarded** — `setInterval(() => refresh({auto: true}), 30000)` refetched
   four to six endpoints and rewrote `#main` even when the browser tab was **hidden**, and even
   when the payload was **byte-identical** to the last one. **Fixed 2026-08-10**, four ways: the
   interval is 60 s (config.pollIntervalSeconds is 60 and bindingIntervalSeconds 300, verified in
   values.yaml, so 30 s provably outran the data); a hidden tab skips the cycle; a
   `visibilitychange` catch-up refetches on return **only when a full interval was actually
   missed** (verified under Playwright's clock: an alt-tab away-and-back costs nothing, and the
   hidden-at-59 s/visible-at-59.5 s worst case fires once, not twice); and refresh() skips
   `render()` on an automatic cycle whose payload fingerprint is unchanged — verified byte-identical
   `#main`, zero childList mutations, while a changed payload, a changed `/api/whoami` (the tier),
   a tab click and a manual refresh all still repaint.
2. **The group search rebuilds the whole page per keystroke.** `index.html`'s `gs.oninput` calls
   `render()`, correctly avoiding a round trip because the groups endpoint applies no limit — so
   the entire list is already in memory. At 65 groups that is 1.3 ms and imperceptible. On a
   cluster with thousands of groups it is a full-page rebuild on every character. Still open.

And one idea a loopback measurement **appeared to refute, wrongly**: every refresh awaited
`whoami`, `/api/clusters`, `/api/alerts` and `groupsyncs` one at a time regardless of tab, which
looks like an obvious `Promise.all`. On loopback parallel IS slower — re-derived 2026-08-10 as
67 ms parallel vs 59 ms serial (the earlier run's 43 vs 32 replicates) — but loopback has no
round trip to amortise. With 40 ms of injected per-request latency (an ASGI middleware sleeping
on `/api/*`, standing in for the proxy+TLS path) the same four endpoints measure **105 ms
parallel vs 220 ms serial**. The serial version billed the reader one full round trip per
endpoint; refresh() now dispatches every endpoint the view needs together. Server side this
made the cold-tier burst real — five to seven concurrent requests each resolving the viewer's
tier — so `TierResolver` single-flights concurrent resolutions per viewer (gsd/kube.py, tested
in test_visibility_tier.py::TestSingleFlight).

## 8. Traps, so the next run does not lose an hour to them

* **Hash navigation does not re-render.** `page.goto(base + '#page=logins')` changes the URL and
  leaves the DOM alone, so you time the *previous* tab. Set `view.page` and call the loader, as
  the script does, or click `button[data-nav='<tab>']`.
* **Since paint-first (2026-08-10), tab chrome no longer means "the fetch landed."** The click
  handler renders the destination before fetching, so `#f-state`, `#f-group-search` and the tab
  bar exist immediately, with the data still in flight. A wait that used them as a fetch proxy
  became a race — it cost seven UI tests, flakily. Wait on something only a fetched render
  produces: `tr[data-group]`, a row, the page's own `h2`.
* **A heading wait cannot SEE paint-first, so it "measures" no improvement.** The pre-fetch
  paint of an uncached tab is `Loading…` in a bare card — no heading, no table. A metric that
  waits for the destination's heading therefore still times the whole fetch and reports
  before ≈ after even when first paint moved from ~300 ms to ~3 ms. This is how the change was
  nearly dropped as a placebo; §6a's timeline method exists because of it.
* **`refresh({auto: true})` may legally skip `render()`.** Since the fingerprint change, an
  automatic refresh with a byte-identical payload does not repaint. Benchmark with
  `refresh({})`, which always paints, or you will time fetch-without-render on every revisit.
* **`render()` without a fetch renders the empty state.** A tab whose `data.*` has not been
  populated paints "Loading…" — about 70 characters of HTML. If a row count is 0 and the node
  count is single digits, you measured nothing. Use `refresh()` for end-to-end numbers.
* **A selector wait can be satisfied by the previous tab's leftovers.** `#main .card` exists on
  nearly every tab. Wait on something only the target tab renders, or measure in-page.
* **`oc exec ... -c <container>`** — the pod has two containers (`dashboard`, `oauth-proxy`) and
  omitting `-c` prints a "Defaulted container" line to stderr that will land in the middle of
  your parsed output.
* **Do not benchmark with the proxy on** unless you want to measure OAuth. Proxy off means no
  identity, which means the wide view — which is the heavier render anyway, so it is the right
  case to time.
* **This is macOS/BSD.** `cat -A` and `pgrep -fc` are GNU-only and will fail.
* **zsh does not word-split unquoted variables.** `FLAGS="--set a=b"; helm template $FLAGS` passes
  one argument, and `helm` fails with something that looks unrelated. Use arrays or write the
  flags out.
