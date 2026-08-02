#!/usr/bin/env python3
"""Generate an access-governance report from one or more group-sync-dashboard deployments.

    ./cluster-report.py                                   # current oc context
    ./cluster-report.py --format markdown -o report.md
    ./cluster-report.py --clusters prod,staging,dev --domain example.com
    ./cluster-report.py --cluster prod=https://group-sync-dashboard.apps.prod.example.com

The parameterised form expands each name through --url-template, whose default is the usual
OpenShift shape:

    https://group-sync-dashboard.apps.<cluster>.<domain>

CRC is the exception — it publishes apps-crc.testing rather than apps.<name>.<domain> — so it
needs an explicit template. Real clusters do not.

WHY THIS IS A SCRIPT AND NOT A FEATURE

The dashboard already exposes everything a report needs at /api, per cluster, at a
predictable hostname. So an aggregator does not have to host or store anything — it reads
each cluster's own API and composes. That is what this does, and it is why the same tool
scales from the one cluster you have to fifty without a database behind it.

    group-sync-dashboard.apps.<cluster>.<domain>/api

HOW IT AUTHENTICATES, AND THE ONE THING THAT DOES NOT WORK YET

Two transports, tried in order:

  1. DIRECT — https://<host>/api with `Authorization: Bearer <token>`. This is the one an
     external aggregator wants: no cluster tooling, no port-forward, just a token and a URL.
     It needs `oauthProxy.apiTokenAccess.enabled=true` on the chart, which adds
     -openshift-delegate-urls for /api and binds system:auth-delegator to the PROXY's
     ServiceAccount. Without it the proxy only understands browser cookies and /api returns
     403 with the login page as the body — a valid token, rejected, confusingly.

     The CALLER needs only the permission the review names — `list groups` cluster-wide by
     default — and specifically NOT system:auth-delegator. Measured: a ServiceAccount that
     cannot list groups gets 403, an identity that can gets 200, and neither needed
     auth-delegator. `oc login` with an LDAP account is therefore all the authentication
     required, which is the whole point.

  2. PORT-FORWARD — `oc port-forward` to the pod and read 127.0.0.1. The fallback, for a
     cluster where apiTokenAccess is off. Requires oc and a reachable cluster.

The report is identical either way, so the transport can be swapped without touching the
content — which is the point of writing it this way rather than hardcoding port-forward.

WHAT THIS DELIBERATELY DOES NOT CLAIM

It reports DIRECT bindings. Role rules are never expanded, so it is not an
effective-permissions proof — the same caveat the API itself carries, repeated here because a
file that leaves the cluster loses the context a browser tab has. Accumulated history covers
only the period each dashboard has been running. Both are stated in the report's own header
rather than left for the reader to know.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime

NAMESPACE = "group-sync-dashboard"
TIMEOUT = 15


# ---------------------------------------------------------------------------
# transports
# ---------------------------------------------------------------------------
def _get(base: str, path: str, token: str | None = None) -> dict | list:
    req = urllib.request.Request(base.rstrip("/") + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    # The dashboard's Route is edge/reencrypt with the cluster's own CA, which a laptop does
    # not trust by default. Verification is skipped ONLY on the direct path and only for a
    # read; there is no credential in the response and the alternative is that nobody can
    # run the report. Say so rather than hide it.
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return json.loads(r.read())


def _oc(*args: str) -> str:
    return subprocess.run(("oc",) + args, capture_output=True, text=True,
                          timeout=TIMEOUT).stdout.strip()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _port_forward(namespace: str):
    """A port-forward to the dashboard pod, torn down on the way out."""
    pod = _oc("get", "pods", "-n", namespace, "-o",
              "jsonpath={.items[0].metadata.name}")
    if not pod:
        raise RuntimeError(f"no pod found in namespace {namespace!r}")
    port = _free_port()
    proc = subprocess.Popen(
        ["oc", "port-forward", "-n", namespace, pod, f"{port}:8080"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Poll rather than sleep a fixed amount: a cold pod takes longer than a warm one and
        # a fixed sleep is either slow or flaky.
        for _ in range(40):
            try:
                _get(f"http://127.0.0.1:{port}", "/api/version")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("port-forward never became ready")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@contextmanager
def connect(name: str, url: str | None, namespace: str):
    """Yield (base_url, how) for one cluster, preferring the direct path."""
    if url:
        token = _oc("whoami", "-t")
        try:
            _get(url, "/api/version", token)
            yield url, "direct (bearer token)"
            return
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None)
            print(f"  {name}: direct failed ({code or exc}); falling back to port-forward",
                  file=sys.stderr)
    with _port_forward(namespace) as base:
        yield base, "oc port-forward"


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------
def collect(base: str, token: str | None = None) -> dict:
    """Everything the report needs, in one pass per cluster."""
    version = _get(base, "/api/version", token)
    clusters = _get(base, "/api/clusters", token)
    out = {"version": version, "clusters": clusters, "per_cluster": {}}
    for c in clusters:
        cid = c["id"]
        q = f"/api/clusters/{cid}"
        out["per_cluster"][cid] = {
            "overview": c,
            # limit high enough to be complete on a normal cluster; `total` and `truncated`
            # in the response say when it was not, and the report prints that.
            "findings": _get(base, f"{q}/bindings/findings?limit=5000", token),
            "user_bindings": _get(base, f"{q}/user-bindings?limit=5000", token),
            "operator_configs": _get(base, f"{q}/operator-configs", token),
        }
    return out


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def render(results: dict[str, dict], fmt: str) -> str:
    b = []
    w = b.append
    h1, h2, h3 = ("# ", "## ", "### ") if fmt == "markdown" else ("", "", "")
    rule = "" if fmt == "markdown" else "=" * 78

    w(f"{h1}OpenShift access-governance report")
    w("")
    w(f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')} (UTC) by "
      f"cluster-report.py against {len(results)} dashboard"
      f"{'' if len(results) == 1 else 's'}.")
    w("")
    w("**Scope.** Direct bindings only — role rules are not expanded, so this is not an "
      "effective-permissions proof. Accumulated history (sync timelines, membership changes) "
      "covers only the period each dashboard has been running.")
    w("")

    for name, data in results.items():
        v = data["version"]
        w(rule)
        w(f"{h2}{name}")
        w("")
        w(f"- dashboard `{v.get('version')}` commit `{v.get('commit')}`"
          f"{' **(dirty build)**' if v.get('dirty') else ''}")
        w(f"- read via {data['_how']}")
        tz = v.get("timezone") or {}
        if tz.get("name"):
            w(f"- container timezone `{tz['name']}` ({tz.get('abbrev')} {tz.get('utc_offset')})"
              " — all timestamps below are UTC regardless")
        w("")

        for cid, d in data["per_cluster"].items():
            ov, f, ub = d["overview"], d["findings"], d["user_bindings"]
            oc_ = d["operator_configs"]
            w(f"{h3}{cid}")
            w("")
            w(f"- endpoint `{ov.get('api_url')}`")
            w(f"- last poll `{ov.get('last_poll') or 'never'}` — status "
              f"**{ov.get('status') or 'unknown'}**")
            if ov.get("error"):
                w(f"- **poll error:** {ov['error']}")
            # Field names read off the live response, not guessed. The first version of this
            # used groups/groupsyncs/empty/unattributed and printed 0 for all four on a
            # cluster with 62 groups — .get() with a default turns a wrong key into a
            # plausible zero, which is the worst way for a report to be wrong.
            w(f"- groups {ov['group_count']} · GroupSync CRs {ov['groupsync_count']}"
              f" · empty {ov['empty_groups']} · unattributed {ov['unattributed_groups']}")
            w(f"- oldest last sync `{ov.get('oldest_last_sync') or 'never'}`")
            w("")

            counts = f.get("counts", {})
            w(f"**Group bindings — {f.get('total', 0)} total**")
            w("")
            if fmt == "markdown":
                w("| Finding | Count | Meaning |")
                w("|---|---|---|")
                for tier, meaning in (
                    ("dangling", "grants nobody — the group no longer exists"),
                    ("unmanaged", "hand-made on an operator-synced group, outside policy"),
                    ("unresolved", "names a group that never existed"),
                    ("built_in", "virtual group, no object by design"),
                    ("ok", "resolves and is templated by the policy operator"),
                ):
                    w(f"| `{tier}` | {counts.get(tier, 0)} | {meaning} |")
            else:
                for tier in ("dangling", "unmanaged", "unresolved", "built_in", "ok"):
                    w(f"  {tier:12} {counts.get(tier, 0)}")
            if f.get("truncated"):
                w("")
                w(f"> Row detail truncated at {f.get('limit')} of {f.get('total')}; "
                  "the counts above are complete.")
            w("")

            rollup = ub.get("by_namespace", [])
            people = len({u for r in rollup for u in (r.get("users") or [])})
            w(f"**Direct user grants — {ub.get('total', 0)} across "
              f"{len(rollup)} namespace{'' if len(rollup) == 1 else 's'}, "
              f"{people} {'person' if people == 1 else 'people'}**")
            w("")
            w("Access bound to a person rather than an enterprise-managed group. These "
              "survive offboarding and are invisible to group-based review.")
            w("")
            if not rollup:
                w("None. Every role on this cluster is granted to a group.")
            elif fmt == "markdown":
                w("| Namespace | Worst privilege | People | Grants | Who |")
                w("|---|---|---|---|---|")
                for r in rollup:
                    priv = {4: "cluster-admin", 3: "admin", 2: "edit", 1: "view"}.get(
                        r.get("worst_privilege"), "?")
                    ns = "**CLUSTER-WIDE**" if r["namespace"] == "(cluster-scoped)" \
                        else f"`{r['namespace']}`"
                    who = ", ".join(r.get("users") or [])
                    w(f"| {ns} | `{priv}` | {r.get('distinct_users')} | "
                      f"{r.get('bindings')} | {who} |")
            else:
                for r in rollup:
                    w(f"  {r['namespace']:40} {r.get('distinct_users')} people "
                      f"{r.get('bindings')} grants")
            if ub.get("excluded_platform"):
                w("")
                w(f"> {ub['excluded_platform']} platform identities excluded "
                  "(system components, kubeadmin) — break-glass, nowhere to migrate to.")
            w("")

            if oc_.get("present"):
                cfgs = oc_.get("configs", [])
                failing = [c for c in cfgs
                           if c.get("error_at") and (not c.get("success_at")
                                                     or c["error_at"] > c["success_at"])]
                w(f"**Policy operator** — {len(cfgs)} CRs, "
                  f"{len(failing)} currently failing")
                for c in failing:
                    w(f"- **{c['kind']}/{c['name']}**: {c.get('error_message')}")
            else:
                w("**Policy operator** — CRDs not present on this cluster.")
            w("")
    return "\n".join(b)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cluster", action="append", default=[], metavar="NAME=URL",
                   help="a dashboard to read, by full URL. Repeat for several.")
    p.add_argument("--clusters", metavar="a,b,c",
                   help="cluster NAMES, expanded through --url-template. This is the "
                        "parameterised form: one flag per fleet rather than per cluster.")
    p.add_argument("--domain", metavar="company.com",
                   help="company domain, used by the default --url-template")
    p.add_argument("--url-template", default="https://group-sync-dashboard.apps.{cluster}.{domain}",
                   help="how a cluster name becomes a URL. Default matches the usual "
                        "OpenShift shape, apps.<cluster>.<domain>. CRC is the odd one out "
                        "and needs --url-template 'https://group-sync-dashboard.apps-{cluster}.testing'")
    p.add_argument("--namespace", default=NAMESPACE,
                   help=f"namespace of the dashboard for the port-forward path "
                        f"(default {NAMESPACE})")
    p.add_argument("--format", choices=("markdown", "text"), default="markdown")
    p.add_argument("-o", "--output", help="write here instead of stdout")
    args = p.parse_args()

    targets: list[tuple[str, str | None]] = []
    for spec in args.cluster:
        if "=" not in spec:
            p.error(f"--cluster wants NAME=URL, got {spec!r}")
        name, url = spec.split("=", 1)
        targets.append((name, url))

    # The parameterised path: names in, URLs derived. The template is a flag rather than a
    # hardcoded f-string because the shape is NOT universal — the usual OpenShift Route is
    # apps.<cluster>.<domain>, but CRC publishes apps-crc.testing, and a mirrored or
    # custom-domain cluster can be neither.
    if args.clusters:
        if not args.domain and "{domain}" in args.url_template:
            p.error("--clusters needs --domain (or a --url-template without {domain})")
        for name in [c.strip() for c in args.clusters.split(",") if c.strip()]:
            targets.append((name, args.url_template.format(cluster=name,
                                                           domain=args.domain or "")))
    if not targets:
        ctx = _oc("config", "current-context") or "current context"
        targets = [(ctx, None)]

    results: dict[str, dict] = {}
    for name, url in targets:
        try:
            with connect(name, url, args.namespace) as (base, how):
                token = _oc("whoami", "-t") if base.startswith("https") else None
                data = collect(base, token)
                data["_how"] = how
                results[name] = data
                print(f"  {name}: collected via {how}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            # One unreachable cluster must not lose the others — but it must be VISIBLE in
            # the report, not silently missing, or a reader counts findings from a subset.
            print(f"  {name}: FAILED — {exc}", file=sys.stderr)
            results[name] = {"version": {}, "clusters": [], "per_cluster": {},
                             "_how": f"UNREACHABLE — {exc}"}

    out = render(results, args.format)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(out + "\n")
        print(f"\nwrote {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if any(r["per_cluster"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
