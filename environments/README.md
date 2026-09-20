# Release values

One file per deployment target, committed. **Always pass the right one with `-f`, on every
`helm upgrade`, including upgrades that only change the image tag.**

```bash
helm upgrade --install group-sync-dashboard charts/group-sync-dashboard \
  -n group-sync-dashboard -f environments/crc.yaml
```

## Why not `--set`

Helm's value precedence on upgrade is a trap, and it is silent. From the docs: if no `--set`
or `-f` is given, Helm reuses the previous release's user-supplied values; **if either is
given, it resets to chart defaults plus only what this invocation passed.**

So `--set` is not additive across upgrades. Measured on this release:

```
before:  helm get values -> oauthProxy.apiTokenAccess.enabled: true
run:     helm upgrade --set logLevel=DEBUG
after:   helm get values -> logLevel: DEBUG          # apiTokenAccess GONE
         delegate-urls on the pod -> absent          # the feature silently off
```

`STATUS: deployed`, no warning, a working feature switched off by a flag about logging. That
is the whole argument for these files: state the desired state declaratively, keep it in git
where a diff is reviewable, and pass it every time so there is nothing to remember and no
implicit reuse to reason about.

`--set` remains correct for something that genuinely varies per invocation — the image tag a
build just produced — but only **alongside** `-f`, never instead of it.

## Files

| File | For |
|---|---|
| `crc.yaml` | the local CRC cluster used for development |
| `example-production.yaml` | a template to copy — not deployed by anything |

A new environment is a new file, reviewed like code. Nothing here holds a secret: the OAuth
cookie secret is generated and reused by the chart, and image pull credentials come from the
cluster's global pull secret.

## What `crc.yaml` actually changes

Every key `crc.yaml` sets already has a chart default. It introduces nothing the chart does not
declare — it only *overrides*, and the table says which way:

| key | chart default | crc.yaml | verdict |
|---|---|---|---|
| `config.unmanagedAudit.mode` | `log` | `log` | redundant — already the default |
| `logLevel` | `INFO` | `DEBUG` | lab override |
| `authLogLevel.manage` / `.enabled` | `false` / `false` | `false` / `false` | inherits the default: the lab reads the AUDIT LOG, which names the person at the default verbosity, so the auth-loglevel Job (a post-upgrade hook) is not needed; the one-time convergence to Normal is done, so management is off (set `manage=true` only for the pod-log source) |
| `loginCapture.enabled` | `true` | `true` | redundant — the default since chart 0.14.0 |
| `loginCapture.source` | `pod-log` | `audit-log` | lab override — a ClusterRole on `get nodes/proxy`, read-only; the audit log names the person at the default verbosity and keeps history |
| `oauthProxy.apiTokenAccess.enabled` | `true` | `true` | redundant — the default since chart 0.14.0 |
| `rbac.namespaces` | `false` | `true` | lab override — a cluster-scoped read (get, list on namespaces, core group); required for the P2 namespace selector, off by default under the 0.14.0 rule |
| `kyverno.metricsUrl` | `""` | `http://kyverno-svc-metrics.kyverno.svc:8000/metrics,http://kyverno-reports-controller-metrics.kyverno.svc:8000/metrics,http://kyverno-background-controller-metrics.kyverno.svc:8000/metrics` | lab override — the Kyverno module's report breakers (#170): the lab runs Kyverno in `kyverno`, and the three circuits live on three endpoints; empty leaves the truncation state unknown |

**Read the right-hand column as "why this is not the default".** The overrides that remain are
fail-closed in the chart on purpose, and a plain `helm install` must not do them uninvited:

- `authLogLevel` writes a **cluster-scoped** CR and rolls the OAuth server, which on a
  single-replica cluster is a login outage rather than a rolling update. `values.yaml` carries the
  measured blast radius and the check to run first. It is the one switch chart 0.14.0's
  on-by-default rule left off: the oauth-server audit log is replacing it as the source of login
  lines.
- `DEBUG` is for debugging. `INFO` is the level that stays readable at steady state.
- `rbac.namespaces` adds a **cluster-scoped** read (`get`, `list` on namespaces, core group) the
  chart needs for nothing else, so it is off by default (the 0.14.0 rule). The lab turns it on
  because the P2 namespace-access report and its multi-dimension selector read namespace labels;
  without the grant the poller never lists namespaces and the selector is always empty — the chart
  guard refuses the selector configuration without it.

The redundant rows are deliberate, not an oversight: a release file should **state** what it wants
rather than inherit it, so a default that moves later cannot silently change this cluster. Two of
them became redundant on chart 0.14.0 (`loginCapture`, `apiTokenAccess`) and were kept for exactly
that reason: the file records what this cluster runs with, whichever way the default moves. That
costs one line each and buys a diff that shows intent. The Grafana dashboard override that validated
B3 through grafana-operator v5 was removed with chart 0.14.0 and its `""` default follows the
ServiceMonitor — ON by default since chart 0.36.0 (2026-09-19), with the rules and the GrafanaDashboard
CR, so the board ships and the `openshift-grafana` release in the same namespace reads it through the
CR (#161); the KPI page's doors are discovered. `crc.yaml` sets none of it, on purpose: the lab
runs the default and would notice if the default stopped working.

### The reporting feature block and the cluster list are configured in `crc.yaml`, not tracked here

Two groups of keys `crc.yaml` sets are deliberately **not** rows in the table above: the
`reporting.*` block — the P2/P4 feature configuration (which label keys the poller captures, which
the Reports form offers as selector dimensions, the automated-run window, and the nightly schedule)
— and `clusters`, the poll targets (this cluster plus the mock OpenShift API). These are feature
configuration, not privileged overrides: every one still has a chart default, so the headline claim
above still holds, and each is documented inline in `crc.yaml` with the reasoning next to the value.
The table answers one question — "will a plain `helm install` do something privileged?" — and these
keys are not part of that answer. `tests/test_environments_readme.py` enumerates the exemption (by
`reporting.` prefix and `clusters`) so a genuinely new *privileged* override still cannot arrive
undocumented, while the feature config that a lab file naturally carries does not have to be
transcribed key-by-key into a table that would then need a list literal in a cell.

`tests/test_environments_readme.py` holds this table against the real `values.yaml` and `crc.yaml`,
because a table of defaults is exactly the kind of documentation that rots quietly — it stays
plausible long after it stops being true.
