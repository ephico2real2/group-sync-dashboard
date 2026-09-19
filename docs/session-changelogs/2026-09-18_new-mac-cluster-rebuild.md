# Session change log — group-sync-dashboard, 2026-09-18 → 2026-09-18

The first session on the Apple M5 Pro MacBook: the resume prompt's four documents read, the machine's state
measured against what the prompt expected, the existing CRC VM started, and the lab rebuilt on it from
`docs/handoff/macbook-migration-plan.md` §4.6b onward. Times are git author times in America/Chicago; every
"measured" claim is one the session ran a command for; nothing below is recalled from memory alone.

Outcome in one line: **the lab rebuilt on the M5 Pro from the charts' values files, three PRs merged and one chart released, and the real cluster's Argo prune explained, reproduced and fixed.**

| | Before the session | After |
|---|---|---|
| main | `60735e2` (PR #191, the migration step map) | `2062fda` (#195, #197 merged after the operator's #192–#194) |
| chart / app | 0.34.0 / 0.24.0 on main; nothing deployed on this machine | 0.34.0 / 0.24.0 deployed from `main`, commit verified in-pod; mock `1/1`, both tiles `ok` |
| CRC | VM built 2026-09-16, stopped since 2026-09-16 22:23; OpenShift 4.22.7; only `packageserver` installed | six releases from their values files: cert-manager-venafi, kyverno 3.9.1, group-sync **0.13.2**, nco 0.22.0, group-sync-dashboard 0.34.0, openshift-gitops 0.1.0; LDAP lab with 8 logging-in users; proxy trusts the cert-manager root |
| Machine | no podman machine, no quay.io login, vault venv and key missing, `helm-local-development` absent | podman machine 4 CPU / 4 GiB with the registry hosts entry; venv on Python 3.14.7 (Homebrew, reinstalled once); quay.io login, vault and `helm-local-development` still absent |
| Open elsewhere | GSO helm chart #63, #64; dashboard tracking issue #171 open on purpose | GSO #63, #64 still open; GSO **#65 merged and released**, #66 filed; dashboard #171 open; new repo `openshift-gitops-helm-chart` |

---

## Part 1 — the machine, measured against the prompt (2026-09-18, 19:2x → 19:3x)

- Read the four documents the resume prompt names. Ran its four state checks: `~/.claude/agents` has
  `ob2.md ob3.md`; the sweeper named two stale Codex brokers (~2 GB, 82 processes, both from
  `cilium-implementation-poc`) and swept them; `vault.sh status` reported venv and key **MISSING**; the
  unpushed-repos loop was silent — because `helm-local-development` is not on this machine at all.
- The machine had been in use since 2026-09-15: 26 directories under `~/gitRepos`, a CRC VM built
  2026-09-16 (`crc.img` 120 GiB, last ran 22:23 that day), `crc-up.sh` and `pull-secret.txt` beside the
  repos. CRC config 10 cpus / 28672 MiB / 120 GiB / monitoring on — neither the plan's §4.6 (12/32768/100)
  nor `crc-up.sh` (10/32768/120). Started as configured, because Docker Desktop was running with 24 GiB for
  the kind lab (`eg1`/`eg2` up 2 h): 28 + 24 = 52 of 64.
- After start: OpenShift 4.22.7, `oc adm top node` 601m (6 %) / 11,487 Mi (41 %), 0 Pending pods, every
  ClusterOperator healthy, 12 pods in `openshift-monitoring`, and **only `packageserver` installed** — an
  empty cluster. No podman machine, no `quay.io` login, `mermaid-ascii` missing.

## Part 2 — the lab rebuilt from the charts (2026-09-18, 19:3x → 20:1x)

- `podman machine init --cpus 4 --memory 4096 --disk-size 40` (arm64/linux). `certified-operators`
  disabled; the other three catalog pods were already Running, so no contention fix was needed.
- **cert-manager** via the Venafi chart. The catalog on 4.22 serves `cert-manager-operator.v1.20.0` on
  `stable-v1`, so `operator.startingCSV` moved from the chart's v1.19.1 default per its own values doc.
  First install failed at the verify Job's step 6/6 on a missing `tpp-secret` — the old cluster's record
  says its Venafi issuer was `Ready=False` anyway; a placeholder Secret, then revision 2 `deployed`.
  Operator CSV Succeeded, three operands Available, webhook serving.
- **Kyverno** 3.9.1 / v1.19.1 from the captured values, the four `anyuid` grants first; four controllers
  `1/1 Running` on the first attempt (the old cluster needed three). Five policies applied from
  `openshift-rbac-automation/working-sessions/policies/` (4 ClusterPolicy + 1 ValidatingPolicy, all
  Audit) plus the eight labelled test namespaces.
- **LDAP lab, Path B**, with one ordering correction: script 15 requires the namespace that only
  `30 bootstrap` creates, so the working order is 10 → 30 bootstrap → 15 apply → 30 deploy → 20 → 90.
  Server `1/1 Running` in 52 s. **Found by the run:** the README's "new deployments get the correct
  form from `ldap-structure-combined.ldif` directly" is refuted by the file — lines 30–94 create `cn=`
  users — so `ldap-normalize-user-dns.ldif` is required on every fresh deploy (6 modrdn). Then the
  four extra LDIFs (12 + 6 + 1 + 7 entries), script 40 `bind-account` / `apply` / `verify`, and PR #63's
  `ldap-missing-from-seeds.ldif` (22 new entries, 3 already present) and `manual-test-users.yaml`
  (102 objects, 51 identity back-references repaired, 0 mismatched). Directory: 81 entries.
- **Found by the login test:** four PR #63 users had `memberOf=0` — the gate group's `uniqueMember`
  lines were written before those user entries existed, so the overlay never stamped them. Re-adding
  the four memberships fixed it. Login table: 8 gate members `oc login` OK (including
  `ocp-oauth-bind-serviceid`), `bob.wilson` and `charlie.brown` refused; `ocp-ldap-bind-serviceid`
  binds to LDAP but is refused by OpenShift, as designed. `oauth/cluster` carries `developer` and
  `ldap-local` (LDAPS 636, `ca-config-map`, `insecure=false`).
- **group-sync chart:** `helm install` on a bare cluster fails at kind resolution (`GroupSync`), and
  the README's `crd.install=true` escape hatch does **not** help on Helm 4.3.0 — a templated CRD is in
  the same manifest whose kinds Helm resolves. Applied the chart-rendered CRD, then installed. Both
  chart tests Succeeded; `15 verify` proved chain and SAN; forced syncs: 62 groups.
  **The operator's correction:** the old release used `test-discovery-values.yaml`, not
  `crc-values.yaml` — render diffed identical to the captured values; moved with `--reset-values`.
  The upgrade hit a server-side-apply conflict on `.spec.providers` from `60-force-groupsync.sh`'s
  `kubectl-patch` manager; `--force-conflicts` resolved it (rev 3). Then, at the operator's request,
  a clean uninstall/reinstall from the file — which found the orphaned-CSV defect (Part 4).
- **NCO chart** from `crc-values.yaml` (render identical to the captured values): CSV v1.2.6
  Succeeded, 2 GroupConfig + 4 NamespaceConfig, 18 labelled bindings. Its `:latest` on quay is an
  **arm64** manifest now, which is why it runs here and would not on an amd64 cluster.
- **Dashboard** via `release-crc.sh`: first run failed at the Containerfile's
  `/lib64/ld-linux-x86-64.so.2 --list` step (Part 3); the registry route resolved to the podman VM's
  own loopback (hosts entry to `192.168.127.254` inside the VM; HTTP 401 from the registry proves the
  path). From the fixed head: both images built natively, pushed, chart 0.34.0 / app 0.24.0
  `deployed`, in-pod commit verified.
- **Mock cluster:** image built, pushed; `certmanager-tls.yaml` applied, both certificates Ready;
  Deployment + Service authored (no manifest existed) — pod died with SIGILL (exit 132). **Found by a
  per-module probe on the node:** `cryptography`'s Rust binding; bisect in a pod: 50.0.1/49.0.0/48.0.0
  exit 132, 46.0.3 and below fine; podman VM (`paca pacg`, no `sve2`) runs it, CRC node (kernel 5.14,
  advertises `sve2 svei8mm`) does not. `OPENSSL_armcap=0` proven on the node (import + 2048-bit RSA).
  `mock-cluster-creds` from the live `mock-ca` (same SHA-256 fingerprint; the one-byte diff is the
  trailing newline `$(…)` strips), `mock-creds` volume patched. Both clusters poll: mock `200 OK`,
  7 namespaces, 4 group bindings; 0 unreachable/verify/absent lines.
- **Trust:** at the operator's prompt ("you cannot be forgetting this"), `15 trust-cluster`: bundle
  146 → 147 certificates, `proxy/cluster.trustedCA=ldap-enterprise-ca-bundle`, node roll **109 s**,
  root on the node's anchor file; auth and monitoring operators re-settled in 30 s.
- **Route DNS:** CRC's admin-helper log shows `hosts:[""] "input rejected"` at 19:56:50 for the
  dashboard Route — the chart sets `spec.subdomain` and leaves `spec.host` empty. Added the
  router-assigned name through the same helper; `/etc/hosts` has it once; route answers 403 (oauth wall).
- **OpenShift GitOps chart** (new repo `ephico2real2/openshift-gitops-helm-chart`, `47570d8`): approver
  approved exactly `openshift-gitops-operator.v1.21.4` and watched it install (47 s); instance
  `phase=Available`, 8 pods Running; SubjectAccessReview `allowed=true` for the controller; all five
  verify stages pass.

## Part 3 — the Containerfiles build on arm64 (2026-09-18, 20:0x) — commit `39f829f`, branch `fix/containerfile-arm64-loader`

- The bases are manifest lists for amd64 and arm64 and every packed library is named by soname; the
  loader path was the only amd64-specific line. Measured on both bases: `/lib64/ld-linux-x86-64.so.2`
  on amd64, `/lib/ld-linux-aarch64.so.1` on arm64 (not under `/lib64`); the glob
  `/lib*/ld-linux-*.so.*` matches exactly one on each and `--list` works on both.
- **Found by the suite:** `test_containerfile.py` pinned the x86-64 name and the annotated copy must
  stay instruction-identical; the parser did not know `set`. Both updated; 22 pass; full hermetic
  suite from `local-development/` as CI runs it: **3458 passed, 13 skipped**.
- Deployed from `6fa847d` (the pre-amend head) and verified in-pod; the amended head is to be
  redeployed after review.

## Part 4 — the group-sync chart's reinstall path, and what Argo CD was doing to the real cluster (2026-09-18 20:2x → 2026-09-19 05:4x) — `group-sync-operator-helm-chart` PR #65

- **Found by the operator's requested clean reinstall:** `helm uninstall` then `helm install` failed at the
  approver: `constraints not satisfiable: @existing/group-sync-operator//group-sync-operator.v0.0.36`.
  Helm stops at the first failed hook, so the extraction (5) and CA-copy (6) Jobs never ran and the
  GroupSync CRs sat on `ReconcileError` for objects the pre-delete cleanup had removed. The chart was the
  last of the three operator charts without a csv-reclaim Job. Ported from cert-manager-venafi at weight −2.
- **Found by the port's first run:** 5 s after the uninstall the orphan read `InstallReady/ComponentUnhealthy →
  Installing`, Succeeded again 12 s later; the sibling scan dismissed an unsettled CSV and the approver
  failed anyway. Rule refined: an unowned, unreferenced, non-copy CSV is a candidate in any phase and is
  waited on inside the budget. Second run: candidate +7 s, `ResolutionFailed` +10 s, deleted +18 s, deployed.
- **The operator's report from the real cluster** ("the configmap copy job … creates and then deletes
  `ca-config-map-copy` as I sync"): the hook Jobs stamped `app.kubernetes.io/instance=<release>` — Argo CD's
  tracking label — on the Secret and the CA copy. **Reproduced on CRC** (GitOps 1.21.4 / Argo CD 3.4.7 switched
  to label tracking via `extraConfig`; `spec.resourceTrackingMethod: label` is read but not written): at
  `0528f57` the objects were written 02:01:47, `Pruned` 02:01:48 (controller log, by name), absent 02:01:57,
  Application Synced/Healthy, every GroupSync `ReconcileError`. At the fixed commit: 0 pruned rows, objects
  present, all three `ReconcileSuccess` (02:05:13–15). The stamp now carries `group-sync-operator-helm/release`.
- **Found by the Argo run:** the approver and the reclaim share sync-wave 0 and Argo runs a wave's hooks
  concurrently; the approver read `ResolutionFailed` and failed while the reclaim was still confirming.
  While the reclaim is enabled the approver now waits through `ResolutionFailed`.
- Chart 0.13.2 (`5035101`), PR #65. Checks: lint, url-guard, check-ordering, qualified-resources, the
  20-combination matrix — all pass. The lab returned to Helm from `test-discovery-values.yaml` (the file the
  old cluster used — render diffed identical to the captured values; `crc-values.yaml` had been my error).
- Two operator rulings recorded as memory: the Helm values files are the source of truth (reinstall from the
  file, never patch), and `trust-cluster` is a fixed rebuild step.

### The review pass on #65 (2026-09-19 03:5x → 05:4x) — commit `6070b06`

- Codex (gpt-5.6-sol xhigh), Cursor (Grok 4.6), OB3 (Opus 5) on a ten-claim brief. **All three refuted C6**
  (the deadline path fell through to the generic message: `ATTEMPTS` and `DEADLINE` are two clocks — OB3
  measured the remedy appearing only at 0.5 s API latency). **Codex and OB3 refuted C10** (a release upgrade
  changes `helm.sh/chart` on 36 of 36 objects, so Argo's automated sync reruns the hooks — the "manual sync"
  statement named the wrong mechanism; Codex's extra-annotation snippet **rejected** as redundant).
  **Codex refuted C7**: `artifacthub.io/changes` had not parsed since the 0.11 entry quoting `(default "")` —
  on `main` too.
- **Found by OB3, the pass's most important finding:** a *settled* orphan made the approver exit 0 ("Succeeded
  and no plan pending"), so under Argo OLM's Manual plan was left unapproved — the 0.13.0 deadlock. My Argo
  runs had passed only inside the post-uninstall churn. **Accepted.** **Found by Codex:** the ported package
  match was a substring; `group-sync-operator-community.v9.9.9` deleted. **Accepted**, anchored on `<package>.v`.
- Applied with their tests: `ci/hook-scripts-harness.sh` (Codex's; failed on HEAD at the deadline assertion,
  passes after) and `ci/check-artifacthub-changes.py` (60 entries parse), both in CI. OB3's 16-case harness
  on the fixed scripts: every case as specified; `c6e` now approves its plan.
- **Live:** uninstall, the orphan `Failed/NoOperatorGroup` for ten minutes, install — reclaim waited through
  OLM's retry, deleted at +10 s, approver approved `install-rvf4d`, `deployed`, both chart tests Succeeded.
- Record: `group-sync-operator-helm-chart/docs/REVIEW_csv_reclaim_and_argo_prune.md`. Second pass launched on
  `6070b06`, OB3 at `effort: max` (the operator's instruction, 2026-09-19).

### The second pass on #65 (2026-09-19 05:3x → 06:3x) — commit `9bc170d`

- Same three reviewers on an eight-claim brief, OB3 at `effort: max`. **Nothing refuted** — OB3 drove 27
  cases through its stateful fake `oc` (instant and 0.5 s latency): the settled orphan now waits and approves,
  the deadline reports OLM's verdict on both timings, the reclaim-disabled path is byte-identical to `main`.
- **Found by OB3, accepted:** the approver's remedy grep and `csv_phase` were unanchored (`oc delete` lines
  printed for `other-<package>.v1` and `<package>.1.2.3`); and the new CI harness at `waitSeconds=1` let the
  *buggy* approver pass on 3–4 of 6 boundary-timed starts, printing nothing on failure — `waitSeconds=5`
  (0 of 6) and an ERR trap. **Found by Codex, accepted:** the changes checker accepted `kind: fixd`.
  **Rejected:** Codex's `csvNamePrefix` for package-aliasing catalogs — pre-existing, chart-wide; issue #66.
- Cursor: C2 and C8 by trace, the rest PLAUSIBLE (no shell); its stray `/tmp/pr65-pass2-measure` removed.
- Lesson kept: `pgrep -c` and `sed '0,/…/'` are GNU-isms that fail silently on this Mac — both bit this
  session once (a wrong process count; a test edit that never happened); measured and redone each time.

## Part 5 — the mock cluster, twice (2026-09-18 22:4x → 23:4x; 2026-09-19 05:0x) — PR #197

- #192/#193 (the operator's other session) captured the mock manifests and `deploy-mock.sh` from the old
  cluster while mine was in flight; #196 closed as superseded, its unique parts rebased as **#197**
  (`962ba23`): `OPENSSL_armcap=0` on the captured Deployment, the captured `clusterIP` stripped, the plan's
  Apple-Silicon, trust and Route passages. Suite: **3459 passed, 13 skipped**.
- **The operator's redeploy from `main`** (his exact instruction): the committed Deployment applied and
  crash-looped on exit 132, `--verify` all green, the dashboard reporting the mock `unreachable`. Stopped and
  reported per the rule; then, on "fix it", applied #197's Deployment from its branch: `1/1 Running`, both
  tiles `ok`.
- **"Fix this for next time"** → `b7d52d8`: `deploy-mock.sh --verify` requires the Deployment's rollout
  complete (a stalled rollout behind an old serving pod fails too — measured) and the dashboard's own
  `/api/clusters` `ok`, exiting 1 otherwise. Healthy exit 0; env removed → exit 1 naming
  `CrashLoopBackOff exit=132`; restored → 0.

## Part 6 — the CA for the MacBook (2026-09-19 05:1x)

- Exported to `~/gitRepos/crc-ca/`: `crc-enterprise-root-ca.crt` (`CN=LDAP Enterprise Root CA`, 2026-09-19 →
  2036-09-16, fingerprint `0E:1F:4B:E3…` = the root `proxy/cluster` trusts) and `crc-ingress-router-ca.crt`
  (`CN=ingress-operator@1785325954`, what every `*.apps-crc.testing` route presents). The
  `security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain` commands given; neither
  was in the keychain.

## Part 7 — the merges (2026-09-19 07:3x → 08:0x), on the operator's "Merge everything"

- Four steps each, never `--delete-branch`: GSO #65 → `a8a6517`, 9/9 files identical on main, branch deleted,
  release workflow `success`, `group-sync-operator-helm-0.13.2.tgz` published 12:36:30Z; dashboard #195 →
  `1803ba1` (4/4) and #197 → `2062fda` (5/5), each `BEHIND` under `strict: true` first, `gh pr update-branch`,
  the eight required checks re-run green, then merged and deleted. #194 the operator had merged himself.
- **Found by the merge loop:** zsh does not word-split an unquoted `$FILES`, so the first file-by-file
  validation reported one nine-line "path" as DIFF — redone with `while read`. Every file then identical.
- `release-crc.sh` from `main`: `0.24.0-2062fda401` built on arm64, pushed, deployed, verified in-pod;
  `deploy-mock.sh --no-build` from `main` rolled the mock out, `--verify` exit 0 (`rollout complete: 1/1`,
  `dashboard reports the mock cluster ok`) — the #197 fix on the merged tree.
- The operator's rulings this session: the GitOps chart's review can wait; OB3 runs at `effort: max`.

## Part 8 — the issue list, from the top (2026-09-19 08:3x → ) — PRs #200, #201, #202, #203, #205, #206, #207

Post-merge, the operator's "now let us look our issues and what is pending and start to complete the
issues". Small PRs first (#200 the vault fallback for `registry-creds.sh`; #201 the new CRC's namespaces
and direct grants; #203 the drill-link contrast; #205 the Kyverno step-0 measurements), then the two
that carry code: #202 (#163) and #206 (#156).

### #163 — retention ages a run from its completion (2026-09-19 10:2x → 13:5x) — commits `f3c9f61`, `916200a`, `43fc933`, PR #202

- `prune` keyed both tiers on the run id, minted at request time; a run that waited or rendered slowly
  arrived `done` already older than `manual.days`. One stamp, `retention_stamp` (`finished_at`, aged from
  the end of its second), both tiers. Chart 0.34.1 for the values/README wording.
- **Review pass 1** (Grok, OB3, Codex — `docs/REVIEW_retention_from_completion.md`): six accepted, three
  rejected. **Found by all three:** the boundary predicate `<` kept a run one second longer than `main`
  did — measured by two independent 200-run differentials, zero difference after `<=`. **Found by OB3:** a
  wrong-typed `finished_at` raised into `_maybe_prune`'s swallow and switched retention off for the whole
  store; the "legacy manifest" story was false (`finished_at` has always been written); a queue refusal
  never stamped. **Found by Grok:** a naive `now` hit the same swallow. **Found by Codex:** the scheduled tier
  had no behavioural test. **Rejected:** Codex's C8 — a permanent id-ordered protection for unstamped
  failed runs, which is the bug seen from the other side.
- **Review pass 2** (the same three at `916200a`): the predicate is decision-identical to `main` — OB3's
  9,036-run differential and Codex's 200-run one both 0. **Found by all three:** the loader never read the
  id, and the fallback's `strptime(id[:15])` was outside the `try` — one hand-edited id halted every prune,
  a regression against `main`'s string comparison; the loader now refuses a manifest whose id is not its
  directory's name or does not parse (OB3 reloaded 300 minted manifests identically). **Found by OB3:** the
  schedule last-success seed caught `ValueError` only — the wrong-typed stamp retention now tolerates
  crashlooped the pod. **Rejected:** Cursor's and Codex's re-opening of C8 (files under a restart-failed run
  are not servable: the download handler answers 404 for any run not `done`); Cursor's prose-agreement test.
- Measured: reporting suite 61 → 63 passed; full hermetic suite 3468 → 3471 passed, 13 skipped. Both
  passes' decisions are on the PR (comments of 2026-09-19).

### #156 — the KPI module (2026-09-19 12:1x → 13:0x) — commits `8c946d2`, `a7d2f58`, `8b89b0c`, `c245897`, `64bb82f`, PR #206

- `gsd/kpi/`: one definition per KPI with a privacy class the Prometheus renderer enforces (it REFUSES
  an internal definition); cgroup v2 self-report for both pods under `component`; churn and login
  counters accumulated from the event tables under an id watermark; `kpi_daily` (migration 15) written
  by the leader once a day; the group predicates spelled once and read by the store, the snapshot and,
  after review, the Groups report. Measured on CRC at `8c946d2`: dashboard 81 MB of 512Mi, 0.5 CPU, 5 of
  120 periods throttled; report 62 MB of 768Mi; `/api/kpi` 200 at the wide tier, 403 for `jdoe`.
- **Found by the live check** (before any report landed): a CPU rate minted over 0.0 s between the two
  cluster threads' usage pulls — a 5 s floor and a per-cycle baseline (`a7d2f58`). The operator's
  "everything as designed in our kpi mock up" → own bytes, report volume and the timeline start added
  (`8b89b0c`).
- **Review pass 1** (Grok, Codex, OB3 — `docs/REVIEW_kpi_module.md`): **found by all three** the `provider`
  label had no bound of the dashboard's own — bounded to the Identity-derived providers plus `unknown`
  (else `other`), and at the source by OB3's `configured_path_provider` after it drove `/login/evil%2Fx`
  into the column; **found by Grok and Codex** zeros from a partial `cpu.stat`, a zero period that 500'd
  `/api/kpi` and the usage feed, an unclamped throttled share, the rollup running after a FAILED poll,
  the Groups report's fourth spelling of the predicates; **found by Grok, Codex and OB3** the watermark
  queries scanning the cluster per scrape (OB3: measured at 300k rows) — migration 16. **Rejected:**
  pruning by watermark, a two-value anonymised provider class, a separate retention family.
- Measured: `tests/test_kpi.py` 28 → 37; full hermetic suite 3512 → 3522 passed, 13 skipped.

### #157 — the KPI page, to the mock (2026-09-19 13:0x → 14:1x) — commits `6e6405b`, `3c6e3c8`, `12065bf`, `c6bf775`, PR #207 (stacked on #206)

- The operator: "I want everything as designed in our kpi mock up for kpi page/panel." A new
  administrator-tier tab built to `docs/design/overview-kpi-mock.html`, rendered from `/api/kpi` (which
  gained `posture`, `thresholds`, `links`, `activity`): system status for both pods with the amber mark drawn
  on each track, the six-tile band, four trends with sparklines, the clusters table, the doors out. Chart
  0.35.0 (`kpi.thresholds.*`, `grafana.url`, `console.url`). Headless renders at 1280 and 375 px read before
  the first commit; the first CRC render found "512.0Mi" (`3c6e3c8`).
- **Review pass 1** (Grok, Codex, OB3 — `docs/REVIEW_kpi_page.md`): **found by OB3** the throttled mark at
  3 px on a 0–100 % track (the page's headline device read nothing — the track is drawn to 5× its
  threshold), the Bindings tile dropping the `unmanaged` tier, the fill's 2.70:1 amber, the window's
  partial first day off the line and the line's days from the browser's clock; **found by Grok and OB3**
  the paint refusing a host administrator over a selected narrowed remote; **found by Grok** a shared day
  kept from one cluster only, `report_run` without a cluster-leading index (migration 17); **found by Codex
  and OB3** a `javascript:` door URL reaching the href; **found by Codex** `data.kpi` missing from the repaint
  fingerprint. **Rejected:** a payload-driven refresh cadence; warn-and-unset for a bad door URL.
- Measured: `TestKpiPage` 9 → 16, `tests/test_kpi.py` 41; full hermetic suite 3539 passed, 13 skipped;
  deployed to CRC at `12065bf` and walked through the real proxy at 1440 light and 375 dark
  (`reports/2026-09-19_kpi-156-157/`); the dashboard pod on watch at 3.03 % throttled, 69 groups, 48 + 155
  bindings, 81.4 % login success over 43 attempts.
- Observed, not this session's: `tests/test_ui.py::TestLookup::test_the_also_line_…` fails on `main` on this
  machine ("typing must not fetch") and passes in CI; three reviewers could not say why offline.

---

### #162 / #161 — the openshift-grafana chart, the GrafanaDashboard CR, the discovered Observe door (2026-09-19 15:4x → 17:5x) — commits `2d1083c` … `07fb9c9`, PR #209

- `2d1083c` the second chart, `charts/openshift-grafana` (grafana-operator v5 from the catalog, the instance, a Thanos datasource on
  the tenancy port through a `view` RoleBinding in the namespace, service CA and token via `valuesFrom`, a NetworkPolicy, a wait gate;
  `crds/` for the one-shot install) and the console discovered from `openshift-config-managed/console-public`. Measured on the way: the
  tenancy port authorises the HTTP method as the verb (POST → `create pods`, so GET); the operator labels the pod `app: <name>` (the
  first policy selected nothing); the operator substitutes `datasourceName` verbatim into the panels' `uid` (a name → "Data source
  not found", so the uid).
- `0101f8e` the CR on request, six KPI panels; `576fc03` the OpenShift login (oauth-proxy sidecar; forged header on :3000 → 401),
  the UWM check, three KPI alerts; `d739ffd` `docs/DESIGN_grafana_and_observe.md`.
- **Review, pass 1** (Grok, Codex, OB3 — `docs/REVIEW_grafana_and_observe.md`): `1825626` the wait Role cut to the script's reads,
  a rediscovery that never blanks the door, every chart attested, the doors guarded at render; `368003f` OB3's: the required bump
  check was RED on the head (→ chart 0.36.0), lint loops every chart, the attestation takes exactly the uploaded packages, HostNetwork
  routers admitted (**Found by OB3** — CRC's single node cannot show it), one CSV phase per line, `--timeout 15m` above the gate, the
  CR refuses empties, the discovered URL held to the door rule, 25 silently-skipped citation checks restored (893/12 again).
- **G9 overturned by the operator** ("well only kubeadmin worked"; jane.smith on *Bad Request*): all three reviewers had CONFIRMED
  the Observe URL's parameters. Measured with the `developer` user given `view` and the last project primed to All: the admin form
  sent `query_range … namespace=` absent (prom-label-proxy 400 on :9092, reproduced with a lab token); the plugin's graphs put the
  console's *active namespace* on the tenancy request (`query-browser.tsx`), set only from a `/ns/<name>` path segment or
  `console.lastNamespace` — kubeadmin's happened to be the namespace, and he never uses the tenancy proxy. `972b143` the door is
  `/dev-monitoring/ns/<ns>?dashboard=<board>` → `namespace=<ns>` on the same user's request. Evidence `98a22a4`. Retracted on the way:
  the `--as=jane.smith` RBAC reading (impersonation drops OpenShift group membership; her real token passed `get pods`).
- `46ee06d` **the operator's defaults**: ServiceMonitor, rules, board and CR (behind `.Capabilities.APIVersions`) on; `grafana.url`
  discovered from the Route by label through a namespaced Role; the Grafana chart's Route on; the gate verifies UWM **by DNS** —
  `getent hosts prometheus-user-workload.openshift-user-workload-monitoring.svc`, measured from a namespace-only pod (resolves; a
  missing Service → NXDOMAIN, `getent` exit 2, present in `ose-cli`) — and reports, never fails; the Role in `openshift-monitoring`
  gone; a "Prerequisites — the Grafana and Observe integration" stanza in both READMEs. A latent defect surfaced by the flip: a quote
  in `fullnameOverride` broke `monitoring.yaml` once the rules rendered by default (**Found by the existing route test**) — two scalars
  quoted. Full suite 3684 passed, 13 skipped; TestKpiPage 16.
- `07fb9c9` the defaults-only install on CRC: the Grafana release on `--reset-values` (`USER-SUPPLIED VALUES: null`), gate
  `user-workload monitoring: ON`, 0 objects left in `openshift-monitoring`; the dashboard with `crc.yaml` setting none of it rendered
  the ServiceMonitor, the rule, the CR (`DashboardSynchronized=True`) and the discovery Role; `/api/kpi` links discovered; the Grafana
  door followed through the OpenShift login to the board (24 panels). Captures `reports/2026-09-19_grafana-observe-162-161/`.
- `a74577a`, `6fb95a9` **design for Argo CD, Flux and Kustomize** (the operator: "someone might use any of the 3 popular
  tools outside of helm"; "remember the argocd failed initially like 2 weeks ago"): what each renderer does, read from
  the sources (argo-cd `util/helm/cmd.go` `--api-versions … --include-crds`, `controller/state.go` live API list,
  `reposerver/cache/cache.go` cache key; helm-controller a real install). The chart's generated Secrets were the trap —
  `lookup` is empty under `helm template`, every render minted new values, every sync would have rotated them — so they
  are now **minted on the cluster by a hook, never rendered**. Four upgrades to get there, each measured: the hook's SA
  as an ordinary resource ("serviceaccount not found" — a pre-hook runs before the manifest → the identity is a hook
  at −10); Helm deleting the Secrets as they left the manifest (→ a post phase too); the datasource stuck 20 min in the
  operator's backoff (v5.24.0 returns an error and never watches the instance — the gate now annotates the watched
  `service-ca` ConfigMap); a final upgrade from a deployed revision: resourceVersions 596822/596848 **KEPT**, gate done
  in 2 min, the door through the proxy on the minted values (`/api/user` kubeadmin, `isGrafanaAdmin=True`). The
  dashboard chart's own `lookup` pattern (cookie, report token) is documented for Argo (`ignoreDifferences` +
  `RespectIgnoreDifferences=true`) and is the next PR's fix. Full suite 3686 passed, 13 skipped; CI green on `6fb95a9`.
- **#209 merged** at `1c99dcf` on the operator's instruction ("let us merge all changes … push it to my repo").
- Housekeeping: a background shell from the GSO night was still looping on `oc get application` (Argo removed) — stopped.

## Numbers

| | |
|---|---|
| Commits authored | 10 on the dashboard (2 branches, later rebased to 3 + 1), 5 on the GSO chart, 1 on the new GitOps chart repo |
| PRs merged | 3 (#65, #195, #197) — merged on instruction, four steps each; #196 closed as superseded |
| Review passes run | 2 on #65 (three reviewers each); none on #195/#197/the GitOps chart, by the operator's decision |
| Reviewer findings accepted / rejected | 8 accepted (C6, C7, C10, OB3 N1/N2 twice, Codex substring + kind), 2 rejected (Codex's Subscription annotation; `csvNamePrefix` → #66) |
| Defects found by tooling rather than reviewers | 9: the arm64 loader (podman build), the registry loopback (podman push), the SIGILL (pod probe + bisect), the orphaned CSV (helm install), the mid-flight orphan (the port's first run), `memberOf` on four users (`oc login`), the `cn=` seed users (script 40), the route with no `spec.host` (CRC's helper log), the Helm 4 `crd.install` hatch |
| Full suite, final | 3459 passed, 13 skipped (dashboard, #197 head); chart: lint, 4 ci scripts, 20-combination matrix, 2 new CI steps, 27-case harness |
| Longest single loss | ~35 min on the `printf > symlink` that overwrote Homebrew's Python (memory *never-write-through-a-symlink-in-bin*) |

## Where things are recorded

- `group-sync-operator-helm-chart/docs/REVIEW_csv_reclaim_and_argo_prune.md` — both passes; issue #66.
- `docs/handoff/macbook-migration-plan.md` §4.6, §4.9, §4.10, §5 — the Apple-Silicon measurements, the mock
  script, the trust step, the Route host; `local-development/mock-app/deploy/DEPLOY.md` — the new verify.
- Memory notes written: *crc-proxy-trusts-the-cert-manager-root*, *helm-values-files-are-the-source-of-truth*,
  *never-write-through-a-symlink-in-bin*; data points on *adversarial-review-before-shipping*.
- `~/gitRepos/claude-config/2026-09-18-design-programme/agents/ob3.md` — `effort: max`, uncommitted.

## State left behind

- CRC running, every release on its values file; `group-sync` on released 0.13.2 (the chart from the merged
  branch — identical content); Argo CD back on its default tracking, no Application; the mock from `main`.
- `~/gitRepos/crc-ca/` holds the two exported CAs; neither is in the macOS keychain yet.
- Not done: the screenshot walk of the deployed `main`; the review passes on #195/#197 (merged unreviewed by
  decision) and on the GitOps chart (deferred); quay.io login; the vault; `helm-local-development`
  (not on this machine); GSO #63/#64 still open for the operator.
