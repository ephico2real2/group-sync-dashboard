"""The ``/_mock/*`` control + inspection surface (DESIGN §9).

A tiny operator window under a reserved prefix that is NOT part of the kube API, so it can
never shadow a real path. It renders the loaded fixture at a glance, a live request log (so an
implementer can *see* the poller's traffic), and a SAR probe form for eyeballing the authorizer.
It is a debugging tool, not a product surface — deliberately minimal, self-contained (inline
CSS, no external assets, CSP-safe), and served without the Bearer gate.
"""

from __future__ import annotations

import html
import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RequestRecord:
    method: str
    path: str
    status: int
    endpoint: str          # the a–p id, or "-"
    nbytes: int


@dataclass
class RequestLog:
    """A bounded in-memory ring buffer of the most recent requests."""

    capacity: int = 200
    _buf: deque = field(default_factory=lambda: deque(maxlen=200))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._buf = deque(maxlen=self.capacity)

    def record(self, method: str, path: str, status: int, endpoint: str, nbytes: int) -> None:
        with self._lock:
            self._buf.append(RequestRecord(method, path, status, endpoint or "-", nbytes))

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._buf)[-limit:]
        return [
            {"method": r.method, "path": r.path, "status": r.status,
             "endpoint": r.endpoint, "bytes": r.nbytes}
            for r in reversed(items)
        ]


# The a–p endpoint id for a matched request, for the inspection view.
ENDPOINT_LABELS = {
    "a": "GroupSync CRs", "b": "Groups", "c": "Users", "d": "Identities",
    "e": "Namespaces", "f": "RoleBindings", "g": "ClusterRoleBindings",
    "h": "NamespaceConfigs", "i": "GroupConfigs", "j": "Nodes", "k": "OAuth CR",
    "l": "OAuth pods", "m": "Pod log", "n": "Node-log listing", "o": "Node-log file",
    "p": "SubjectAccessReview",
}


def state_json(fixture, reqlog: RequestLog) -> dict:
    return {
        "fixture_summary": fixture.summary(),
        "recent_requests": reqlog.recent(100),
        "sar_cache_note": (
            "The dashboard's TierResolver caches a verdict for its TTL (60s default); the mock "
            "itself is stateless and recomputes every SAR from the fixture RBAC."
        ),
    }


def render_page(fixture, reqlog: RequestLog) -> str:
    fx = fixture.summary()
    rows = "".join(
        f"<tr><td>{html.escape(r['method'])}</td>"
        f"<td class='path'>{html.escape(r['path'])}</td>"
        f"<td>{r['status']}</td>"
        f"<td>{html.escape(str(r['endpoint']))}</td>"
        f"<td class='num'>{r['bytes']}</td></tr>"
        for r in reqlog.recent(50)
    )
    verb_options = "".join(
        f"<option value='{v}'>{v}</option>" for v in ("list", "get", "watch", "update", "create", "delete")
    )
    facts = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(val))}</td></tr>"
        for k, val in fx.items()
    )
    return _PAGE.format(
        cluster=html.escape(fx["clusterName"]),
        facts=facts,
        rows=rows or "<tr><td colspan='5' class='muted'>no requests yet</td></tr>",
        verb_options=verb_options,
    )


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mock-openshift · {cluster}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#0f1115; --fg:#e7e9ee; --muted:#8b93a7;
           --card:#171a21; --accent:#4f9cf9; --line:#242833; --ok:#3fb950; --no:#f85149; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
          background:var(--bg); color:var(--fg); }}
  header {{ padding:18px 24px; border-bottom:1px solid var(--line);
            display:flex; align-items:baseline; gap:12px; }}
  header h1 {{ font-size:18px; margin:0; font-weight:600; }}
  header .tag {{ color:var(--muted); font-size:12px; }}
  main {{ display:grid; grid-template-columns:320px 1fr; gap:0; }}
  @media (max-width:820px) {{ main {{ grid-template-columns:1fr; }} }}
  aside {{ padding:20px 24px; border-right:1px solid var(--line); }}
  section {{ padding:20px 24px; min-width:0; }}
  h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted);
        margin:0 0 12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ text-align:left; padding:5px 8px; border-bottom:1px solid var(--line);
           vertical-align:top; }}
  aside th {{ color:var(--muted); font-weight:500; width:52%; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .path {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px;
           word-break:break-all; }}
  .muted {{ color:var(--muted); }}
  form.probe {{ display:flex; flex-wrap:wrap; gap:8px; align-items:end; margin-bottom:14px; }}
  form.probe label {{ display:flex; flex-direction:column; gap:3px; font-size:12px;
                      color:var(--muted); }}
  input, select {{ background:var(--card); color:var(--fg); border:1px solid var(--line);
                   border-radius:6px; padding:6px 8px; font:inherit; }}
  button {{ background:var(--accent); color:#04101f; border:0; border-radius:6px;
            padding:7px 14px; font-weight:600; cursor:pointer; }}
  #verdict {{ margin:0 0 16px; padding:10px 12px; border-radius:8px; background:var(--card);
              border:1px solid var(--line); font-size:13px; }}
  .allow {{ color:var(--ok); font-weight:600; }}
  .deny {{ color:var(--no); font-weight:600; }}
  .wrap {{ overflow-x:auto; }}
</style>
</head>
<body>
<header>
  <h1>mock-openshift</h1>
  <span class="tag">{cluster} · fixture-driven OpenShift API surface for group-sync-dashboard</span>
</header>
<main>
  <aside>
    <h2>Fixture at a glance</h2>
    <table>{facts}</table>
  </aside>
  <section>
    <h2>SAR probe</h2>
    <form class="probe" id="sarForm">
      <label>user<input name="user" value="lateef.o"></label>
      <label>verb<select name="verb">{verb_options}</select></label>
      <label>resource<input name="resource" value="clusterrolebindings"></label>
      <label>group<input name="group" value="rbac.authorization.k8s.io"></label>
      <label>namespace<input name="namespace" placeholder="(cluster-scoped)"></label>
      <button type="submit">Evaluate</button>
    </form>
    <div id="verdict" class="muted">Enter a subject and press Evaluate. The user's group
      memberships from the fixture are added automatically, just as the dashboard would.</div>

    <h2>Recent requests</h2>
    <div class="wrap">
      <table>
        <thead><tr><th>method</th><th>path</th><th>status</th><th>ep</th><th class="num">bytes</th></tr></thead>
        <tbody id="reqbody">{rows}</tbody>
      </table>
    </div>
  </section>
</main>
<script>
const form = document.getElementById('sarForm');
form.addEventListener('submit', async (e) => {{
  e.preventDefault();
  const fd = new FormData(form);
  const body = Object.fromEntries(fd.entries());
  const res = await fetch('/_mock/sar-probe', {{
    method:'POST', headers:{{'content-type':'application/json'}}, body:JSON.stringify(body)
  }});
  const data = await res.json();
  const v = document.getElementById('verdict');
  const cls = data.allowed ? 'allow' : 'deny';
  const word = data.allowed ? 'ALLOWED' : 'DENIED';
  const via = data.binding ? (' via binding <code>' + data.binding + '</code>') : ' (no binding grants it)';
  v.className = '';
  v.innerHTML = '<span class="' + cls + '">' + word + '</span>' + via +
                '<br><span class="muted">groups sent: ' + (data.groups || []).join(', ') + '</span>';
}});
async function refresh() {{
  try {{
    const res = await fetch('/_mock/state');
    const data = await res.json();
    const tb = document.getElementById('reqbody');
    tb.innerHTML = (data.recent_requests || []).slice(0, 50).map(r =>
      '<tr><td>' + r.method + '</td><td class="path">' + r.path + '</td><td>' +
      r.status + '</td><td>' + r.endpoint + '</td><td class="num">' + r.bytes + '</td></tr>'
    ).join('') || '<tr><td colspan="5" class="muted">no requests yet</td></tr>';
  }} catch (err) {{ /* server gone; leave the last render */ }}
}}
setInterval(refresh, 2000);
</script>
</body>
</html>
"""
