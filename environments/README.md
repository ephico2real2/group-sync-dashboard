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
| `authLogLevel.manage` / `.enabled` | `false` / `false` | `true` / `true` | lab override |
| `loginCapture.enabled` | `false` | `true` | lab override |
| `oauthProxy.apiTokenAccess.enabled` | `false` | `true` | lab override |
| `monitoring.grafanaDashboard.enabled` | `""` | `true` | lab override: `""` follows the ServiceMonitor, which stays off here (no Prometheus Operator); grafana-operator v5 in namespace `grafana-test` validates the shipped board |

**Read the right-hand column as "why this is not the default".** Every override is fail-closed in
the chart on purpose, and a plain `helm install` must not do any of it uninvited:

- `authLogLevel` writes a **cluster-scoped** CR and rolls the OAuth server, which on a
  single-replica cluster is a login outage rather than a rolling update. `values.yaml` carries the
  measured blast radius and the check to run first.
- `loginCapture` grants the dashboard `pods/log` in `openshift-authentication` — reading logs that
  name every person who authenticates, with their LDAP DN.
- `apiTokenAccess` opens `/api` to bearer tokens. Off means cookie sessions only.
- `DEBUG` is for debugging. `INFO` is the level that stays readable at steady state.

The redundant row is deliberate, not an oversight: a release file should **state** what it wants
rather than inherit it, so a default that moves later cannot silently change this cluster. That
costs one line and buys a diff that shows intent.

`tests/test_environments_readme.py` holds this table against the real `values.yaml` and `crc.yaml`,
because a table of defaults is exactly the kind of documentation that rots quietly — it stays
plausible long after it stops being true.
