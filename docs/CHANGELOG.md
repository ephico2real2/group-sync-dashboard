# Changelog

What each release changed, newest first. Two artefacts, two version lines (`docs/RELEASING.md`):
the application (`pyproject.toml`, deployed as `quay.io/ephico2real/group-sync-dashboard:<version>`)
and the chart (`Chart.yaml`, published to the Helm repository). A chart release that only moves
`appVersion` is listed under the application release it carries. The reasoning behind each change
lives next to the code and in the design and review records linked here. Changes merged since the
last release sit under `## Unreleased` until the release that carries them replaces that heading —
which `local-development/prepare-release.py` does when the release is cut.

## Chart 0.13.0 — application 0.13.0 — 2026-09-05

- **A Grafana dashboard ships with the chart.** `monitoring.grafanaDashboard` renders
  `dashboards/group-sync-dashboard.json` as a ConfigMap labelled `grafana_dashboard: "1"` — the
  sidecar convention; grafana-operator v5 reads it through `configMapRef` (recipe in the chart
  README). Default `""` follows `monitoring.serviceMonitor.enabled`. Every panel expression is held
  to the collector's declared families, the thresholds to `values.yaml`'s defaults, and the rendered
  JSON to the file byte-for-byte, all by `tests/test_chart_grafana_dashboard.py`.
  (spec `docs/specs/SPEC_B3_grafana_dashboard.md`)

## Application 0.13.0 — chart 0.12.0 — 2026-09-05

- **Retention for the accumulated history, `config.retention`.** `membershipEventsDays: 0`
  (forever) and `syncEventsDays: 730` by default; the leader prunes after the cycle's backup, never
  before one has succeeded in this process's life and never at all while `config.backup` is off,
  5,000 rows per table per cycle, counted into `gsd_retention_rows_deleted_total{table}`. Four
  history responses gain `retention: {window_days, retained_since}` and the page says "history
  retained since …" where a timeline begins at the cut. First start after upgrade builds the
  `sync_event_by_time` index. **Restoring an old backup to read its history: set both windows to
  `0` first** — the first successful backup in the new process's life releases the prune.
  (spec `docs/specs/SPEC_B2_history_retention.md`)

## Application 0.12.0 — chart 0.11.0 — 2026-09-05

- **Group-count cliff alert, with read-only silencing.** A group whose membership fell by
  `config.alerts.groupCountCliff.dropRatio` (0.5) from at least `minMembers` (10) within
  `windowHours` (24) is alert kind `group_count_cliff`, severity warning — reconstructed from the
  membership events the poll already records, so no new table. Silence it read-only with the Group
  annotation `groupsync-dashboard.io/silence-group-count-cliff` (`true` or `until=YYYY-MM-DD`) or the
  chart's `silence` globs; a silenced cliff is still reported as `group_count_cliff_silenced`, dimmed
  on the Overview, counted under its own kind on `/metrics`, and never pages. New
  `GroupSyncGroupCountCliff` rule (the twelfth). `/api/alerts` rows gain `silenced` and
  `silenced_by`; group rows gain `cliff_silence`; schema migration 8. Both cliff kinds are withheld
  at the self tier. Default on, and the README's "needs a floor as well as a ratio" is answered by
  the floor. (spec `docs/specs/SPEC_B4_group_count_cliff.md`)

- **The browser tests run in CI.** `tests/test_ui.py` — the real app on a free port, a seeded store,
  Playwright against it — now runs in a `ui` job of its own on every pull request and push, on the
  interpreter the image ships, with the Playwright package pinned so the Chromium build is too.
  Screenshots and traces are kept as a workflow artifact only when a test fails. Repository
  variable `CI_UI_TESTS=false` turns the job off and leaves the interpreter matrix exactly as it
  was; `test_live_smoke.py` still runs nowhere but against a cluster you name.
- **A release is one command.** `local-development/prepare-release.py --app X.Y.Z "reason"` (or
  `--chart A.B.C`) moves the four version fields together, writes the `Chart.yaml` history line and
  the application paragraph, turns this `## Unreleased` heading into the release heading, runs
  `tests/test_chart_versions.py`, and commits to `release/…` with the operator as sole author;
  `--pr` opens the pull request. It refuses a dirty tree, a version that does not advance, and a
  branch that exists. Nothing writes to `main`, as before.

## Application 0.11.0 — chart 0.10.0 — 2026-09-04

- **The image runs on Red Hat Hardened Images.** `hi/python:3.14` to run and `hi/python:3.14-builder`
  to build, on the floating `3.14` tags so every build takes Red Hat's latest 3.14. The runtime base
  has no shell, so a third stage assembles one — bash (and `sh`), `curl` on `libcurl-minimal`, `jq`,
  and the coreutils shims `cat`, `ls`, `base64`, `mkdir`, `chgrp`, `chmod`, `rm` — with exactly the
  twelve libraries the runtime lacks, measured by `ldd`, and copies it in. Every in-pod command in
  the docs and the release scripts' stamp check still work. SQLite is 3.53.4 (UBI: 3.34.1); zoneinfo
  ships, so the tzdata reinstall is gone; 186 MB against 227. The declared user is the base's
  65532 rather than UBI's 1001 — the distroless convention, numeric, and on OpenShift never the
  UID the process runs as anyway. The recipe is written to be read, with its two Python steps
  as repository scripts; `Containerfile.annotated` is the same instructions with the full
  reasoning beside each step, held identical by a test, and `Containerfile.ubi` is the previous
  recipe — both built by nothing. (#52; design `DESIGN_hardened_image.md`)
- **Three packages uninstalled from the base, files and RPM records together.** `libuuid`, the one
  HIGH-rated package in the base (four util-linux advisories of 2026-09-02, all in mount code the
  image does not ship, no fixed build from Red Hat yet) — nothing needs it, and `uuid` falls back to
  pure Python, proven on every build. And pip, twice (`python3-pip` and the `python-pip-wheel`
  seed), an installer nothing needs, whose vendored msgpack and setuptools were the only Python
  findings. The file list comes from the RPM database itself, so files and records cannot diverge.
  The shipped image scans at zero CRITICAL, zero HIGH, zero fixable at any severity. (#52;
  `image-vulnerability-scan.md`)
- **CI scans with Grype, not Trivy.** Measured: Trivy does not recognise Hummingbird OS and scans
  no OS package; Grype reads the RPM database and Red Hat's advisories for it. The gate runs on the
  shipped image and on the pack stage, fails only on fixable HIGH, and a separate step shows the
  full inventory. (#52)
- **Chart 0.10.0: curl in the pod trusts what the dashboard trusts.** curl reads the image's own
  system bundle and none of the application's settings, so an `oc exec … curl` against a
  corporate-signed URL failed where the application verified it. Now a `.curlrc` ConfigMap,
  mounted at `/etc/curl` and found through `CURL_HOME`, names the injected bundle as `cacert`
  (when `trustedCA.injected` is on) and OpenSSL's hashed directory as `capath`; and a new
  `trustedCA.existingConfigMap.subjectHash` mounts the manual CA into that directory as
  `<hash>.0`, Hummingbird's "Approach 2", so curl, urllib and the dashboard's fallback context all
  trust it. A file rather than `CURL_CA_BUNDLE` and `SSL_CERT_DIR`, because curl ignores the
  second whenever the first is set (measured on curl 7.76 and 8.22), and only the curl tool reads
  the file, so the dashboard's own TLS cannot be touched by it. Every claim measured in a pod;
  `TUTORIAL_ca_trust_hashed_directory.md` teaches the mechanism. Also `appVersion`, and the
  `timezone` and SQLite comments now say what the hardened base ships. (#52)

## Application 0.10.2 — chart 0.9.4 — 2026-09-04

- **Access granted, from the second-pass review:** when the reader's tier is indeterminate (a
  whoami that fails on a later cycle) the tab fails closed to Loading, as the Overview does, instead
  of painting a cached payload of either tier; the Reaches column's logged-in count is null until
  the User objects have been read at least once, rather than a confident zero on a fresh install or
  the cycle after migration 7; a row that carries no tier renders its group name as plain text,
  closing the last way into the 404 that #49 removed. (review record `REVIEW_second_pass_2026-09-04.md`)
- **Chart 0.9.3:** the chart README's values table only — the row for a `redirectMode` key that no
  longer exists. Docs for the whole day's state, and this changelog, landed with it. (#50)

## Application 0.10.1 — chart 0.9.2 — 2026-09-04

- **Access granted:** a group name is a drill only where a group page can answer. Built-in
  virtual groups never have a Group object and unresolved bindings name groups that never existed,
  so those names drilled to a 404 that blamed a deletion which never happened. They render as plain
  text now; dangling and granted groups keep the drill. (#49)

## Application 0.10.0 — chart 0.9.1 — 2026-09-03

- **Access granted opens on what was granted.** The faults (dangling, unresolved, unmanaged) stay on
  top because nothing on the cluster reports them; the Granted section follows; the built-in
  majority stays one filter away. It used to open on the faults alone. (#48)
- **Every row says who it reaches.** `member_count` — the named Group's own count — and
  `logged_in_count` — members with a `User` that has an identity, the 0.9.0 definition of a login.
  Both null when no Group object exists, so 0 means the group exists and grants nobody today, and is
  highlighted. Opt-in on the store query and pre-grouped, so the metrics scrape, the poller and
  `/api/clusters` pay nothing for it; `/api/clusters` also stops materialising every binding row to
  count them. (#48)
- **Filter and sort.** A type-to-match box like the Groups and Users tabs, over group, role,
  namespace and binding name, narrowing every section with the cluster-wide counts untouched; sortable
  column headers on the shared table; truncation disclosed when the page is cut. (#48)
- **A narrowed reader sees their own grants.** The findings endpoint still refuses them; the tab reads
  their own `/users/{name}` and shows the bindings that reach them through their groups, with the
  group named. The tab re-decides its tier from the whoami that just arrived, so a tier change
  mid-session paints the right view on the next cycle. (#48; review record
  `REVIEW_access_granted_reach.md`)

## Application 0.9.0 — chart 0.9.0 — 2026-09-03

- **The Users tab counts the people who have logged in.** Rows are OpenShift `User` objects, which
  the cluster creates at first login and never before; group membership is an attribute of a row
  and may be zero. Synced members who have never logged in are one line, by count, with the names a
  click away. Per row: first login, identity provider(s), last captured login, display name.
  Headline KPIs, chips by membership and provider, a banner naming `rbac.users` when the read is
  refused, and the age of the last successful read. `/users` pages properly (`total`, `offset`) and
  carries `logged_in_total` beside `total` so a manual account with no identity is listed but not
  counted as a login. Schema migration 7 rebuilds `ocp_user`. (#47; design
  `DESIGN_users_tab_logins.md`, review record `REVIEW_users_tab_logins.md`)
- **Fix:** `Store.login_without_access` was defined twice and only the undocumented copy ran; an
  AST guard test now fails the build on any repeated method name in the package. (#46)
- **Chart 0.9.0:** `appVersion` moves; the `rbac.users` grant is now the Users tab's source rather
  than a decoration of it, so turning it off costs that tab's rows (the tab says so by name) instead
  of display names. No template output changes.

## Chart 0.8.0 — application 0.8.1 — 2026-09-03

- **A Route the router names, by default.** `route.enabled` (default true) emits an OpenShift Route
  with `spec.subdomain: <fullname>`, so the hostname is `<fullname>.<apps domain>` — the release name,
  never the namespace — with no cluster lookup at render time. The ServiceAccount's OAuth callback
  becomes a reference to that Route by name. That is what lets ArgoCD, Flux and any `helm template`
  renderer deploy the chart with no per-cluster value: the Ingress path's apps-domain lookup could
  never succeed there and the render was refused. `ingress.enabled` (default false) keeps the
  Ingress for plain Kubernetes, unchanged. A host set deliberately (`route.host`, or a carried-over
  `ingress.host`) is used as given. (#45; design `DESIGN_route_exposure.md`, review record
  `REVIEW_route_exposure.md`)
- **`argocd.enabled` defaults to true.** It adds `argocd.argoproj.io/sync-options` annotations and
  nothing else, which Kubernetes ignores outside Argo, so an Application needs no chart value at
  all. (#45)
- On upgrade from 0.7.1 the Ingress and its generated Route are replaced by the chart's Route on the
  same hostname; sessions, data and RBAC are untouched. Measured on the reference cluster.
