# SPEC G2 — platform users in the values file, and either platform list from an existing ConfigMap (#255)

| | |
|---|---|
| Programme | Epic G (#387), access declared, platform identities configured — build step 2 of 4. #239 (SPEC_G1) comes before it; #503 comes after it and changes the same direct-user view and alert |
| Batch | G — access declared |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 2.6.0, chart 0.63.0 |
| Issue | [#255](https://github.com/ephico2real2/group-sync-dashboard/issues/255) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from #255 (body refined 2026-09-30, "Decisions and corrections (2026-10-01)"), its epic #387 and main `afa01bb8` (application 2.0.0, chart 0.59.25). Measured on this machine (Python 3.14.7, helm v4.3.0) and read-only on the CRC lab (2026-10-01, 13:06–13:07Z). §7 was cut from an implemented copy of `afa01bb8` and proved against a clean tree (§4.3). Revised the same day after the review of `4c75c65b` by OB3 (in Grok's seat) and Codex, on the orchestrator's decisions (Orchestrator's notes, 4), on a branch that merged main `21132a25` (SPEC G1, #506); the corrected blocks were proved again on that main (§4.2, §4.3) |

## How to read this spec

**The point, in two sentences.** Today the list of "platform users" (identities whose direct grants are counted, never
raised as findings) is compiled into the image, and an estate cannot add its own break-glass or bind account without a
release. After this change it is a values-file stanza, `platformUsers`, built exactly like the `platformNamespaces`
stanza that already exists, and either stanza can instead be kept in a ConfigMap the estate owns.

§1 is the mandate and what is out of scope. §2 is the research, each finding with its primary source and the
sentence relied on, quoted, and what was measured on this repository and the lab. §2a is the alternatives the
research turned up, why each was chosen or rejected, and the reconciliation of every external claim with the line of
code that behaves accordingly. §3 is the design, one rule per subsection with its reason; §3.9 states the safety
property as a budget. §4 maps every test case of the issue (`T255-1` to `T255-16`) to a test and shows it failing on
`afa01bb8`. §5 is the lab walk the implementing pull request runs. §6 is what an operator sees and what it costs. §7
is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean
tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G2_platform_users.md . --apply

Citations into the code use `path#anchor` (a function, a class or a phrase in the file) at `afa01bb8` unless a
section says otherwise. This spec's row in the index moves through its lifecycle by the orchestrator's hand; no
block touches it. A block found wrong during implementation is corrected here, with the reason under the
orchestrator's notes, before it is applied again.

## Orchestrator's notes

1. **Corrections to the issue, each with its evidence.**
   - **OpenShift's break-glass user is `kube:admin` outside CRC, and the shipped defaults now name it.** The 2.0.0
     list names `kubeadmin`. In openshift/library-go the bootstrap user is `BootstrapUser = "kube:admin"`, and
     `kubeadmin` is only the name it logs in with (`bootstrapUserBasicAuth = "kubeadmin"`, §2.2); every project it
     requests binds `kube:admin` as the project's admin (openshift/openshift-apiserver, §2.2). On the CRC lab
     `kubeadmin` is an HTPasswd user and the bindings name `kubeadmin`, never `kube:admin` (§2.7). **The operator's
     ruling of 2026-10-01, recorded on #255:** *"kubeadmin or kube:admin is a trusted user in crc that we use as
     admin"* — one trusted admin identity, so the shipped defaults are 2.0.0's list plus `kube:admin`. This amends
     the issue's "the defaults reproduce 2.0.0's classification exactly": T255-1 pins 2.0.0's list written out plus
     `kube:admin` by name, and the CHANGELOG says so. On the lab it changes nothing: no binding names `kube:admin`
     (read-only `oc`, 2026-10-01T13:59:37Z: 35 User rows, none of them `kube:admin`). The login capture already
     counts `kube:admin` among the names that are never people (`local-development/gsd/auditlog.py#SYSTEM_NAMES`).
   - **The issue says `trustedCA` is a `subPath` mount.** Only its `subjectHash` link is
     (`charts/group-sync-dashboard/templates/deployment.yaml#subPath: {{ $.Values.trustedCA.existingConfigMap.key }}`);
     the bundle itself is a whole-ConfigMap directory mount. The platform lists are mounted the same way as the
     bundle: a directory, never a `subPath` (§3.5).
   - **An empty replacing list never reached the application.** `templates/configmap.yaml` keeps a key only `if $v`,
     so `platformNamespaces.names: []` rendered no `platformNamespaces` key at all (measured, §2.6), and the five
     shipped names stayed in force, contrary to the values comment ("`prefixes`, `suffixes` and `names` REPLACE the
     shipped defaults"). T255-3 needs `platformUsers.names: []` to work, and the render is now one loop for both
     stanzas, so a replacing key is rendered whenever it is set, empty included. This changes the render only for a
     values file that sets an empty replacing list; none of the four value sets of T255-12 does.
   - **`gsd/kube.py` stops being a classification site.** The reader has no settings (issue, correction 1), so the
     poller classifies User rows (§3.2). `UserBindingView` loses its `is_platform` field, `is_platform_user` and the
     two constants leave `gsd/kube.py` (the constants move to `gsd/config.py`, the function is removed: nothing would
     call it). `tests/test_platform_classification_marker.py` therefore no longer requires the marker in
     `gsd/kube.py`; it requires it on every new site instead (T255-11).
2. **Decisions made on "easy to manage, best practice"** (the operator's rule of 2026-09-05), each argued in §2a.
   - **The ConfigMap is read once, at start; `existingConfigMap.revision` rolls the pod.** The operator's rules of
     2026-10-01 ("supported by Helm values file directly", "nobody uses manual cli … only for troubleshooting and
     development") rule out a hand restart. The chart cannot see the ConfigMap's content (no `lookup` under a render,
     §2.5), so a values key that the release changes is the only values-file way to roll the pod after an edit. It
     is free text, rendered into the settings file, so `checksum/config` moves.
   - **`platformUsers` axes are lists; a string is refused, never split.** Kubernetes puts no format on a user name
     (§2.3), so `cn=jdoe,ou=People` is one name. `platformNamespaces` keeps its #259 semantics (a comma-separated
     string is still split there): its keys and semantics must not change.
   - **The ConfigMap's key holds the stanza itself, as YAML** (the same keys as inline). An empty key is refused: a
     list the estate pointed at must say something.
   - **Version.** App 2.1.0 and chart 0.60.0 are the next free MINORs after `afa01bb8` (MINOR for the chart: values
     are added). If another release lands first, the release-field blocks (§7, blocks 70–74) fail their check, because
     their Old text is the version they replace, and the implementing pull request re-derives them here first.
   - **The index row conflicts with SPEC_G1's (#239, in review on `docs/spec-g1-239`).** Both raise the count from
     thirty-five to thirty-six against `afa01bb8`, and both touch `tests/test_specs_index.py`. This spec excludes G2
     alone from the rising-issue-number assertion, by its id, and pins it to #255 (`assert ROWS["G2"]["issue"] ==
     "255"`), as G1 excludes G1 by its id and pins it to T1's issue: an exclusion by the `G` prefix let a G2 row
     mistyped as #256 or #525, and a later G row mistyped as #100, pass every index test (review of this spec, OB3).
     G1 merged first (`21132a25`); this branch merged it, so G2 is the thirty-seventh row and the exclusion is
     `fid not in ("G1", "G2")`, with both pins (a G2 row mistyped as #256 or #525 now fails, measured).
3. **Open for the operator** (asked when #255 is reached; it does not block the implementation).
   - (a) **A person an estate lists as a platform user leaves their own Namespace audit self view**, as `kubeadmin`
     does today: the page never sends `include_platform` there (`local-development/gsd/static/index.html#want.userBindings = guard403(get(`),
     while Home lists their grants. Kept exactly as today (the issue's decision 3 and the epic's open question 4).
   - (b) *Should the shipped defaults gain `kube:admin`?* Settled by the operator on 2026-10-01 (note 1): they do.
4. **The review of `4c75c65b`** (OB3 in Grok's seat, Codex gpt-5.6-sol at xhigh; decided by the orchestrator on
   2026-10-01). Every accepted change was traced before it was applied, and is in §3 and §7 and proved in §4.
   - **Accepted, OB3 F1 (and Codex C8, superseded by the ruling):** `kube:admin` in the shipped defaults, note 1.
   - **Accepted, OB3 F2 and Codex's required fix 1:** the mock cluster's suite (`.github/workflows/mock-cluster.yml`,
     outside the hermetic run) read the removed `UserBindingView.is_platform`; block 75 changes it, and §4 runs that
     suite. OB3's form is taken (it also asserts the default classifies the mock's user as a person); Codex's
     `hasattr` check is the same assertion. The other readers of the flag read the stored column, which the poller
     still writes (both reviewers swept them).
   - **Accepted, OB3 F3 and Codex's required fix 3:** the index exemption names G2 and pins #255 (note 2).
   - **Accepted, OB3 F4:** `PlatformUsers.unmatched([])` reports nothing, so a cluster whose bindings were never
     read shows no ⚠ for every entry (§3.4).
   - **Accepted, OB3 F5:** §2a sources A2 and A7 and weighs A9 (`podAnnotations`) and A10 (a versioned name).
   - **Accepted, OB3 F6:** the CHANGELOG names both `platformNamespaces` render changes (an empty replacing list now
     renders; a non-mapping is refused), and the empty-list render test loads what it renders.
   - **Accepted, OB3 F7 and F8 (low):** a quoted `existingConfigMap.enabled` is refused at render, and
     `revision: 0` renders as `"0"` so it rolls the pod.
   - **Accepted, Codex's required fix 2 (C6):** an unmatched entry is an observation, not a departed account: the
     page, the values comment, `API.md` and the docstring say "not currently matched by any User subject on a binding
     in this cluster; keep planned entries, and check unexpected ones" (§3.4).
   - **Not taken:** Codex's suggestion (C8) to leave the defaults at 2.0.0's and open a separate issue, superseded by
     the operator's ruling; OB3's two "no change proposed" items (a loose `existingConfigMap.name` pattern the API
     server refuses at apply; a ConfigMap-sourced `platformNamespaces` string still split, #259's semantics).

## 1. The mandate, and what is out of scope

The issue (#255, "What must be accomplished"): `values.yaml` gains `platformUsers` with `prefixes` and `names`
(replacing the defaults) and `additionalPrefixes` and `additionalNames` (appending); with nothing set the defaults
equal 2.0.0's lists (plus `kube:admin`, by the operator's ruling of 2026-10-01, Orchestrator's note 1); a listed user is the platform's everywhere the stored flag reaches (the direct-user rows, their
total and worklist, the alert, `excluded_platform`, the unmanaged finding's `built_in`); a typo is refused by name at
`helm template` and at start; the stanza reaches the application through the settings file; a stale `additional*`
entry is reported in the namespace index's idiom; `platformNamespaces` and `platformUsers` can each be read from an
existing ConfigMap, refused beside an inline list; the page's two platform notes say where their list comes from;
nothing else moves (the `platformNamespaces` keys and semantics, the lab's values, `/metrics` without names, the
classification marker, the dashboard ServiceAccount's permissions).

Out of scope, each owned elsewhere: honouring the operator's `rbac.ocp.io/config-source` label and the exception
annotation in the direct-user view (#503, the next build step, which starts from this spec's code), the Lease grant
(#420), the tier declaration (#239), a per-cluster list (the 2026-09-21 rule 5 on #255: the lists are cluster-wide),
and suffix, glob or regular-expression matching for users (the issue's decision).

## 2. Research, measured

Upstream documents were read from their source repositories at a pinned commit (fetched 2026-10-01 with
`curl -sfL https://raw.githubusercontent.com/<repo>/<sha>/<path>` and searched with `grep -n`), never from a rendered
page: kubernetes/website `607898ad`, helm/helm-www `a00848f7`, argoproj/argo-cd `317dd84c`, openshift/library-go
`5800ac43`. The OpenShift product documentation was read from docs.redhat.com (4.22, "Authentication and
authorization", fetched 2026-10-01). The lab reads were `oc get` of every RoleBinding and ClusterRoleBinding as JSON,
`oc get deploy`, `oc get cm` and the public `/metrics`, nothing else.

### 2.1 The `system:` prefix is Kubernetes'

**Source.** Kubernetes, "Using RBAC Authorization", "Referring to subjects": "The prefix `system:` is reserved for
Kubernetes system use, so you should ensure that you don't have users or groups with names that start with `system:`
by accident." And "Authenticating", the OIDC flags: `--oidc-username-prefix` is a "Prefix prepended to username
claims to prevent clashes with existing names (such as `system:` users)".

**What it settles.** The default prefix `system:` is the platform's by Kubernetes' own rule, and stays the default.
Service accounts authenticate as `system:serviceaccount:(NAMESPACE):(SERVICEACCOUNT)` (same page), which is why the
lab's `system:serviceaccount:openshift-kube-apiserver:check-endpoints` User subject (§2.7) is a platform row today.

### 2.2 OpenShift's `kubeadmin` is the user `kube:admin`

**Source.** OpenShift 4.22, "Authentication and authorization", §11.1 "The kubeadmin user": "OpenShift Container
Platform creates a cluster administrator, kubeadmin, after the installation process completes. This user has the
cluster-admin role automatically applied and is treated as the root user for the cluster." The same document's
example output for `oc describe rolebinding.rbac -n joe-project` lists the subject `User kube:admin`. The code,
openshift/library-go `pkg/authentication/bootstrapauthenticator/bootstrap.go` at `5800ac43` (`curl … | nl -ba`):

```text
    23		// BootstrapUser is the magic bootstrap OAuth user that can perform any action
    24		BootstrapUser = "kube:admin"
    26		bootstrapUserBasicAuth = "kubeadmin"
    57			names:  sets.New(BootstrapUser, bootstrapUserBasicAuth),
```

**Measured on the lab.** CRC's bindings name `kubeadmin` (an htpasswd user there) and never `kube:admin` (§2.7).

**Where `kube:admin` lands on a binding.** openshift/openshift-apiserver at `34196aab`,
`pkg/project/apiserver/registry/projectrequest/delegated/sample_template.go`, line 57: `binding :=
NewRoleBindingForClusterRole(bootstrappolicy.AdminRoleName, ns).Users("${" + ProjectAdminUserParam + "}")`, and
`delegated.go`, lines 148-150: `projectAdmin = userInfo.GetName()`. Every project the bootstrap user requests binds
the User `kube:admin` as its `admin`, the documentation's `joe-project` example above. On the lab `kubeadmin` is an
HTPasswd user (`oc get user kubeadmin`: identities `["developer:kubeadmin"]`) and `kube-system/kubeadmin`, the
bootstrap user's secret, does not exist, so no `kube:admin` binding can arise there.

**What it settles.** The 2.0.0 default `kubeadmin` matches the CRC lab's user and not the bootstrap user of an
installed OpenShift cluster, whose project bindings it would raise as a person's direct grants. The operator ruled on
2026-10-01 that the two names are one trusted admin identity (Orchestrator's note 1): the shipped defaults are 2.0.0's
list plus `kube:admin`, T255-1 pins exactly that, and nothing moves on the lab.

### 2.3 A user name has no format

**Source.** "Using RBAC Authorization", "Referring to subjects": "Kubernetes represents usernames as strings. These
can be: plain names, such as "alice"; email-style names, like "bob@example.com"; or numeric user IDs represented as a
string." and "Other than this special prefix, the RBAC authorization system does not require any format for
usernames."

**What it settles.** A user name may contain a comma (an LDAP DN mapped as the user name; the repository already
learned this for the direct-user rollup, `local-development/API.md#is a **list**, not a comma-joined string`). So a
`platformUsers` axis is a YAML list only; a string is refused rather than split (§3.6). Matching is byte-exact, as
the self tier already matches a viewer to a subject.

### 2.4 A ConfigMap mounted as a volume

**Source.** Kubernetes, "ConfigMaps", "Mounted ConfigMaps are updated automatically": "When a ConfigMap currently
consumed in a volume is updated, projected keys are eventually updated as well. The kubelet checks whether the
mounted ConfigMap is fresh on every periodic sync." … "the total delay from the moment when the ConfigMap is updated
to the moment when new keys are projected to the Pod can be as long as the kubelet sync period + cache propagation
delay". And: "A container using a ConfigMap as a subPath volume mount will not receive ConfigMap updates." The
kubelet's `syncFrequency`: "the max period between synchronizing running containers and config. Default: "1m""
(KubeletConfiguration v1beta1). On projection: "If you omit the `items` array entirely, every key in the ConfigMap
becomes a file with the same name as the key" ("ConfigMaps"), and a key "must consist of alphanumeric characters,
`-`, `_` or `.`". On absence ("Configure a Pod to Use a ConfigMap", "Restrictions"): "If you reference a ConfigMap
that doesn't exist and you don't mark the reference as `optional`, the Pod won't start. Similarly, references to keys
that don't exist in the ConfigMap will also prevent the Pod from starting, unless you mark the key references as
`optional`."

**What it settles.**

- Mount the whole ConfigMap as a directory, never a `subPath` and never with `items`. Without `items` a key that is
  missing is simply absent beneath the mount, so the loader reaches it and refuses the start naming the ConfigMap and
  the key, in the pod's log; with `items` the pod would never start and the reason would sit only in an event. (That
  an absent key leaves no file without `items` follows from the projection sentence; it was not measured on the lab,
  which is read-only here.)
- Not `optional`: a list the estate named that is missing stops the pod, exactly as `trustedCA.existingConfigMap`
  does (`charts/group-sync-dashboard/templates/deployment.yaml#NOT optional: you named this explicitly`).
- The kubelet refreshes the file within about a minute plus the cache delay, but this design reads it once, at
  start (§2a, A), so an edit takes effect when the pod restarts; `existingConfigMap.revision` is how the release
  restarts it (§3.5).

### 2.5 Refusing at render, and what a render cannot see

**Source.** Helm, "Template Function List": `fail` "Unconditionally returns an empty `string` and an `error` with the
specified text. This is useful in scenarios where other conditionals have determined that template rendering should
fail."; "There are two Kind functions: `kindOf` returns the kind of an object." and "`kindIs` function will let you
verify that a value is a particular kind". Helm, "Template Functions and Pipelines", `lookup`: "Keep in mind that
Helm is not supposed to contact the Kubernetes API Server during a `helm template|install|upgrade|delete|rollback
--dry-run` operation." Argo CD, "Helm": "Helm is only used to inflate charts with `helm template`." Helm, "Chart
Development Tips and Tricks", "Automatically Roll Deployments": "if the deployment spec itself didn't change the
application keeps running with the old configuration resulting in an inconsistent deployment. The `sha256sum` function
can be used to ensure a deployment's annotation section is updated if another file changes"; and the alternative,
"replacing with a random string so it always changes and causes the deployment to roll: `rollme: {{ randAlphaNum 5 |
quote }}`". Argo CD, "Helm", on `randAlphaNum`: "Because the random value is regenerated every time the comparison is
made, any application which makes use of the `randAlphaNum` function will always be in an `OutOfSync` state."

**What it settles.**

- An inline stanza is checked at render with `kindIs`/`fail`, as `gsd.validatePlatformNamespaces` already does
  (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.validatePlatformNamespaces`), and again at start.
- The content of an existing ConfigMap cannot be checked at render: a render has no cluster (Helm), and a GitOps
  conduit renders with `helm template` (Argo CD). The loader is the only place that can refuse a typo inside it, and
  its refusal names the ConfigMap and the key (§3.6).
- A ConfigMap edit changes no rendered byte, so the chart's own `checksum/config`
  (`charts/group-sync-dashboard/templates/deployment.yaml#checksum/config`) cannot roll the pod by itself. A random
  annotation would roll it on every render and leave a GitOps application permanently out of sync. A value the
  release sets (`revision`) and the chart renders into the settings file rolls it exactly when the release says so.

### 2.6 This repository at `afa01bb8`

- **The pattern to copy.** `platformNamespaces` (#259): `PlatformNamespaces` with `matches` and `unmatched`
  (`local-development/gsd/config.py#PlatformNamespaces`), its parser refusing an unknown key, a non-string and a glob
  (`local-development/gsd/config.py#_platform_namespaces_setting`), the render-time twin
  (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.validatePlatformNamespaces`), the settings-file key
  (`charts/group-sync-dashboard/templates/configmap.yaml#platformNamespaces: {{ toJson $set }}`), and the stale report
  on the namespace index (`local-development/gsd/static/index.html#no namespace on this cluster — a typo, or a convention that has gone`).
- **The users today.** `PLATFORM_USER_PREFIXES` and `PLATFORM_USER_NAMES` and `is_platform_user` are in
  `local-development/gsd/kube.py#is_platform_user`, whose comment says "no values key widens it". The reader sets the
  flag (`local-development/gsd/kube.py#_user_binding_views`) inside `ClusterClient.fetch_user_bindings`, which has no
  settings; the poller copies it into `user_binding` and calls `is_platform_user` again for the finding
  (`local-development/gsd/poller.py#_binding_is_platform`). The alert (`local-development/gsd/state.py#compute_alerts`),
  the excluded count (`local-development/gsd/store.py#Store.platform_user_binding_count`), the rollup, the reports
  (`local-development/gsd/reporting/snapshot.py`) and Home read the stored flag and decide nothing.
- **Reclassifying writes no history.** The binding-event diff compares the role only: "is_platform is metadata
  carried on the event, not part of what changed — a subject reclassified would otherwise read as removed + added"
  (`local-development/gsd/store.py#Store._append_binding_events`).
- **When a new list takes effect.** Settings load once (`local-development/gsd/config.py#load_settings`); the poll
  loop's first binding refresh runs at once after a start (`local-development/gsd/poller.py#next_binding_refresh = 0.0`),
  and a values change rolls the pod through `checksum/config`.
- **The precedents for the ConfigMap.** `trustedCA.existingConfigMap` is `{enabled, name, key}`
  (`charts/group-sync-dashboard/values.yaml#key: ca-bundle.crt`), mounted not optional; mutual exclusion at render is
  `charts/group-sync-dashboard/templates/rbac-auditors.yaml#mutually exclusive: either render the chart role`. A
  mount nested under `/etc/gsd` already exists (`/etc/gsd/report`), and runs on the lab (§2.7).
- **Measured on `afa01bb8` with helm v4.3.0** (the issue's T255-5, T255-8 and correction 1(c)):

```text
$ helm template t charts/group-sync-dashboard --set 'platformUsers.additionalNames={ocp-oauth-bind-serviceid}' \
    --set ingress.host=t.example.com | grep -c platformUsers
0
$ helm template t charts/group-sync-dashboard --set platformNamespaces.existingConfigMap=estate-platform …
Error: … platformNamespaces.existingConfigMap is not a key this chart defines; expected any of prefixes, suffixes,
names, additionalPrefixes, additionalSuffixes, additionalNames. A typo here is a pattern that never takes effect.
$ helm template t charts/group-sync-dashboard -f <(platformNamespaces: {names: []}) … | grep -n platformNamespaces
389:    # PLATFORM-CLASSIFICATION (#255, #353): values.yaml platformNamespaces → this file → config.py _platform_namespaces_setting
```

  The last render carries the comment and no `platformNamespaces:` key: the empty replacing list was dropped.

### 2.7 The lab, read-only (CRC, chart 0.59.25, image `quay.io/ephico2real/group-sync-dashboard:2.0.0`)

Every User subject on every RoleBinding and ClusterRoleBinding, classified by the 2.0.0 rule (2026-10-01T13:06:54Z):

```text
user rows 35 platform 24 not 11
   ('ClusterRoleBinding', '', 'cluster-reader', 'dana.lee', None)
   ('ClusterRoleBinding', '', 'group-sync-dashboard-cluster-poller', 'ocp-oauth-bind-serviceid', 'group-sync-operator-helm')
   ('ClusterRoleBinding', '', 'jdoe-edit', 'jdoe', None)
   ('RoleBinding', 'group-sync-operator', 'group-sync-dashboard-cluster-poller-token-reader', 'ocp-oauth-bind-serviceid', 'group-sync-operator-helm')
   ('RoleBinding', 'legacy-payments', 'asmith-admin', 'asmith', None)
   ('RoleBinding', 'legacy-payments', 'bwilliams-admin', 'bwilliams', None)
   ('RoleBinding', 'legacy-payments', 'jdoe-admin', 'jdoe', None)
   ('RoleBinding', 'legacy-reporting', 'jdoe-edit', 'jdoe', None)
   ('RoleBinding', 'legacy-reporting', 'tmp-contractor-9931-edit', 'tmp-contractor-9931', None)
   ('RoleBinding', 'openshift-console-user-settings', 'user-settings-27fcd795-…-rolebinding', 'jane.smith', None)
   ('RoleBinding', 'openshift-console-user-settings', 'user-settings-d46d9fe1-…-rolebinding', 'developer', None)
distinct users ['asmith', 'bwilliams', 'dana.lee', 'developer', 'jane.smith', 'jdoe', 'kubeadmin',
 'ocp-oauth-bind-serviceid', 'system:admin', 'system:kube-apiserver', 'system:kube-controller-manager',
 'system:kube-proxy', 'system:kube-scheduler', 'system:master',
 'system:serviceaccount:openshift-kube-apiserver:check-endpoints', 'tmp-contractor-9931']
kube:admin rows []
tmp-contractor rows [('RoleBinding', 'legacy-reporting', 'tmp-contractor-9931-edit', 'tmp-contractor-9931', None)]
```

The last column is the binding's `rbac.ocp.io/config-source` label. The issue's numbers hold: 35 rows, 24 platform,
11 not, and `tmp-contractor-9931` names exactly one unlabelled RoleBinding (§5's walk moves one row each way). The
public `/metrics` (13:07:12Z): `gsd_bindings_total{cluster="dashboard",finding="unmanaged"} 53.0`,
`finding="built_in"} 848.0`, `gsd_alerts_total{cluster="dashboard",kind="direct_user_binding",severity="warning"} 1.0`.
The live settings file carries
`platformNamespaces: {"additionalNames":["kyverno","group-sync-dashboard"],"additionalSuffixes":["-operator","-manager","-provisioner"]}`
and no `platformUsers` key. The dashboard container mounts `/etc/gsd`, `/etc/gsd/report` and `/etc/gsd/service-ca`, so
a volume nested under the settings volume runs there today.

## 2a. Alternatives considered

**A. Where an estate's external list is read, and how an edit takes effect.**

| option | source | cost here | decision |
|---|---|---|---|
| A1. The ConfigMap mounted as a directory, read once at start; `existingConfigMap.revision` in the values file rolls the pod | §2.4, §2.5 (Helm's checksum tip) | one volume and mount per enabled stanza, one optional value, one loader branch; no permission | **chosen** |
| A2. Read the ConfigMap through the API | the issue's decision 1 (one shape across the chart, no new permission) | a `get configmaps` grant in the release namespace (RBAC ADDED, against the issue's "no new RBAC: REMOVED 0, ADDED 0"), and an absent ConfigMap becomes a runtime state to handle instead of a pod that does not start | rejected |
| A3. Re-read the mounted file on every binding refresh | §2.4: "projected keys are eventually updated" | a runtime refusal path (keep the last list? stop classifying?), and the API (which reads `Settings`) and the poller (which would read the file) could hold two different lists between refreshes; the issue wants one classifier | rejected |
| A4. Helm `lookup` to inline the ConfigMap at render | §2.5 | returns nothing under `helm template` and therefore under a GitOps conduit; the render would silently use the defaults | rejected |
| A5. Restart by hand after an edit | the operator, 2026-10-01 | a CLI step outside the values file, which the operator's rule forbids outside troubleshooting; under a GitOps conduit the restart annotation is drift | rejected |
| A6. `rollme: {{ randAlphaNum 5 }}` | §2.5 | rolls the pod on every render; Argo CD documents the application as always `OutOfSync` | rejected |
| A7. A reloader controller watching the ConfigMap | stakater/Reloader at `099c9d8b`, `README.md` line 22: "a Kubernetes controller that automatically triggers rollouts of workloads … whenever referenced `Secrets`, `ConfigMaps` … are updated" | a second component to install and trust, for one file, and a roll no values file records | rejected |
| A8. Inline values only (no `existingConfigMap`) | the issue | the issue's outcome 6 requires the ConfigMap | rejected |
| A9. Bump an annotation in `podAnnotations` after an edit (no new key) | this chart: `charts/group-sync-dashboard/values.yaml#podAnnotations: {}`, rendered into the pod template (`charts/group-sync-dashboard/templates/deployment.yaml#with .Values.podAnnotations`); measured, a bumped annotation changes the pod template and rolls the pod | no code at all, but nothing ties the annotation to the list it re-reads: an estate must invent a key, and the settings file does not record which edit the pod started from | rejected in favour of `revision`, which sits beside the reference it rolls and is recorded in the settings file; it keeps working, as any pod annotation does |
| A10. A versioned ConfigMap name: a new name per edit (an immutable ConfigMap, or one a generator suffixes with a hash) | Kubernetes "ConfigMaps", "Immutable ConfigMaps": "You can only delete and recreate the ConfigMap. Because existing Pods maintain a mount point to the deleted ConfigMap, it is recommended to recreate these pods."; "Managing Kubernetes Objects Using Kustomize": "The generated ConfigMaps and Secrets have a content hash suffix appended. This ensures that a new ConfigMap or Secret is generated when the contents are changed." | no new key: a new `existingConfigMap.name` changes the pod template's volume and rolls the pod (measured), and an immutable copy cannot change under a running pod | supported as it stands (any name works); not the only way, because an estate that edits its ConfigMap in place needs `revision` |

**B. Matching.** Plain prefix and exact name (chosen, the issue's decision and #259's rule) against a suffix axis
(nothing measured needs one: the lab's non-platform User subjects, §2.7, are named people and named accounts, and an
estate lists an account by its name) and globs or regular expressions (an injection surface and an unreviewable diff in a values file, #259's
reasoning in `local-development/gsd/config.py#PlatformNamespaces`). A value carrying `*`, `?`, `[` or `]` is refused,
which also means a user name containing one of those cannot be listed; none exists on the lab.

**C. Where a User is classified.** In the poller from `Settings.platform_users` (chosen: ServiceAccounts are already
classified there from `platform_namespaces`, `local-development/gsd/poller.py#_binding_is_platform`, and the poller
already holds the settings) against handing the settings to `ClusterClient` (the reader would gain a dependency it
has never had, for one flag, and every other reader path would need it too).

**D. A list in both places.** Refuse (chosen, the issue's decision; the precedent is `rbacAuditors`) against merging
the two (two sources of truth for one answer, the defect the issue names).

**E. The mount.** A whole-ConfigMap directory (chosen) against `items` (a missing key would stop the pod with the
reason only in an event, §2.4) and against `subPath` (never updated, §2.4; harmless while the file is read at start,
but it closes the door to any later reload).

**F. The file's shape.** The stanza itself as YAML under one key (chosen: the same keys and the same parser as the
inline form, so "a ConfigMap-sourced list classifies exactly as the same list written inline", T255-9) against one
ConfigMap key per axis (a second format for one stanza).

**Reconciliation — each external claim, and the code that behaves accordingly.**

| research says | the code does it at |
|---|---|
| `system:` is reserved for Kubernetes (§2.1) | `PLATFORM_USER_PREFIXES = ("system:",)`, moved unchanged to `local-development/gsd/config.py#PLATFORM_USER_PREFIXES`; T255-1 pins it against the 2.0.0 list written out |
| the bootstrap user is `kube:admin` (§2.2) | in the shipped defaults beside `kubeadmin`, by the operator's ruling of 2026-10-01 (`local-development/gsd/config.py#PLATFORM_USER_NAMES`); T255-1 pins 2.0.0's list plus `kube:admin`, written out |
| a user name has no format (§2.3) | `local-development/gsd/config.py#_platform_users_setting` refuses a non-list ("a user name may contain a comma, so a string is never split") and `PlatformUsers.matches` compares bytes |
| a subPath mount is never updated; without `items` every key is a file (§2.4) | `charts/group-sync-dashboard/templates/deployment.yaml#A platform list kept in a ConfigMap you own` mounts the whole ConfigMap at `/etc/gsd/platform-users` (and `/etc/gsd/platform-namespaces`), no `subPath`, no `items`; `tests/test_chart_platform_users.py` asserts both |
| a missing, non-optional ConfigMap stops the pod (§2.4) | the volume carries no `optional` (`…#NOT optional, as trustedCA's`); a missing key reaches `local-development/gsd/config.py#_platform_stanza`, which refuses with the ConfigMap and the key |
| the kubelet updates the file eventually (§2.4) | nothing re-reads it: `_platform_stanza` runs once, inside `load_settings`; a change of `revision` changes `checksum/config` and rolls the pod (test `test_changing_the_revision_rolls_the_pod…`) |
| `fail`/`kindIs` refuse at render (§2.5) | `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.validatePlatformLists`, the one validator for both stanzas |
| a render cannot `lookup` (§2.5) | no `lookup` anywhere in the chart for this; the loader refuses a bad ConfigMap at start, by name (T255-9) |
| a random annotation keeps Argo CD `OutOfSync` (§2.5) | no random value is rendered; `revision` is the release's own text |

## 3. The design

### 3.1 The stanza, and its defaults

```yaml
platformUsers:
  # prefixes: ["system:"]
  # names: ["kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler", "kube-proxy", "kubeadmin", "kube:admin"]
  additionalPrefixes: []
  additionalNames: []       # e.g. ["breakglass-admin"]
  existingConfigMap:
    enabled: false
    name: ""
    key: platform-users.yaml
    revision: ""
```

Four list keys, as the issue decided: `prefixes` and `names` replace the shipped defaults, `additionalPrefixes` and
`additionalNames` append to them. With nothing set the defaults are 2.0.0's plus `kube:admin`: the constants move
from `gsd/kube.py` to `gsd/config.py` (`PLATFORM_USER_PREFIXES` unchanged, `PLATFORM_USER_NAMES` with `kube:admin`
added by the operator's ruling of 2026-10-01, Orchestrator's note 1), so `PlatformUsers()` holds them. `PlatformUsers.matches(name)` is the one User classifier: an exact name (shipped or
added), then a prefix (shipped or added). `platformNamespaces` gains the same `existingConfigMap` and nothing else.

Reason: the estate's common case is additive (a bind account, a break-glass login), and a restated list would rot on
the next OpenShift release; this is #259's reasoning for namespaces, applied to users.

### 3.2 One classifier, in the poller

`refresh_bindings` takes `platform_users` beside `platform_namespaces`, and `Poller._run_cluster` hands it
`settings.platform_users`, as it hands the namespaces. In that refresh:

- each `user_binding` row's `is_platform` is `platform_users.matches(user_name)` (the direct-user rows, their total,
  their rollup, `excluded_platform`, the alert, Home and the reports all read this stored flag and decide nothing);
- `_binding_is_platform` reads the same `PlatformUsers` for a User subject on the finding path (the unmanaged
  finding's `built_in`);
- the refresh line's "naming a person" count uses it too.

`UserBindingView` loses `is_platform` and `_user_binding_views` decides nothing: a flag computed by a reader with no
settings, then overwritten, would be a second classifier. `is_platform_user` is removed with it; nothing calls it.

Reason: the issue's correction 1 and decision; one list, read in one place, cannot disagree with itself.

### 3.3 When a change takes effect

A values change rolls the pod (`checksum/config`), and the new pod's first binding refresh, at start, restores every
row's flag from the new list. A change to an existing ConfigMap takes effect the same way once `revision` is changed
in the values file and the release is rolled out (§3.5). Until that refresh, the rows keep the flags the previous pod
stored, which is the previous list's classification and no other.

### 3.4 A stale entry

`PlatformUsers.unmatched(users)` returns every `additionalPrefixes` entry that is a prefix of none of `users` and
every `additionalNames` entry equal to none, by axis, as `PlatformNamespaces.unmatched` does. `users` is
`Store.user_binding_names(cluster)`: every User subject on that cluster's bindings, platform ones included (users have
no index of their own; the issue's decision 2). An empty list judges nothing: a cluster's bindings always name its
own `system:` components as Users (24 rows on the lab, §2.7), so none at all means the bindings have not been read
there, not that every entry has gone — the namespace index likewise shows its stale patterns only inside its
platform line (`local-development/gsd/static/index.html#const stalePatterns`). The shipped defaults are never
reported. `/user-bindings` returns it as `platform_users_unmatched` at the wide tier and `null` at self, with
`excluded_platform`.

This is an observation about the bindings now, not proof that an account is stale or deleted: an estate may
deliberately list a platform user before its first grant (review of this spec, Codex C6). The page therefore reports
it under the direct-user note in the namespace index's warning idiom, with neutral, actionable words: "⚠
`additionalNames`: `breakglass-2024` is not currently matched by any User subject on a binding in this cluster; keep
planned entries, and check unexpected ones."

### 3.5 `existingConfigMap`, for either stanza

| step | what happens |
|---|---|
| render | `gsd.validatePlatformLists` checks `existingConfigMap` is `{enabled, name, key, revision}`; enabled, it refuses any list of the same stanza that is set (an `additional*` with entries, or a replacing key at all), a name that is not a DNS subdomain and a key outside `[-._a-zA-Z0-9]+` |
| settings file | instead of the stanza, `platformUsersConfigMap: {"key":…,"name":…,"path":"/etc/gsd/platform-users/<key>","revision":…}` (and `platformNamespacesConfigMap`, path `/etc/gsd/platform-namespaces/<key>`) |
| pod | a volume per enabled stanza, the whole ConfigMap, not optional, mounted read-only at that directory in the dashboard container only; no `subPath`, no `items` |
| start | `_platform_stanza` reads the file once and hands its YAML to the same parser as the inline stanza; it refuses both forms at once, an unreadable or empty file and invalid YAML, every message naming `<stanza> (ConfigMap '<name>', key '<key>')` |
| after an edit | the estate changes `existingConfigMap.revision` in the values file and rolls the release out; the new `revision` changes `checksum/config`, the pod restarts and reads the new list |

`revision` is free text the loader does not read. A list read from a ConfigMap equals the same list written inline
(`origin` is outside the dataclasses' equality), which is T255-9.

### 3.6 The refusals, at render and at start

| input | render (`helm template`) | start (`load_settings`) |
|---|---|---|
| an unknown key (`additionalName`, `suffixes`) | `platformUsers.additionalName is not a key this chart defines; expected any of prefixes, names, additionalPrefixes, additionalNames, existingConfigMap.` | `platformUsers: unknown key(s) ['additionalName']; expected any of …` |
| a non-list (`additionalNames: x`) | `platformUsers.additionalNames must be a list, got string.` | `platformUsers.additionalNames: expected a list of strings, got 'x'; a user name may contain a comma, so a string is never split` |
| a non-string entry | `…: every entry must be a string; 3 is float64.` | `…: every entry must be a string, got 3` |
| a glob character | `…: "svc-*" contains * — matching is literal, not a glob. A prefix or a full name; …` | `…: 'svc-*' contains * — matching is literal, not a glob. …` |
| `existingConfigMap` beside a list | `platformUsers.existingConfigMap and platformUsers.additionalNames are both set: …` | `platformUsers and platformUsersConfigMap are both set; …` |
| a missing or bad ConfigMap key | cannot be seen (§2.5) | `platformUsers (ConfigMap 'estate-platform', key 'users.yaml'): cannot read …` / `invalid YAML …` / `… is empty …` / `unknown key(s) …` |

`platformNamespaces` keeps its #259 messages for an inline stanza; from a ConfigMap they gain the same
`(ConfigMap '<name>', key '<key>')`.

### 3.7 The page

The direct-user note (both of its places in `directUserGrants`) and the namespace index's note are built from the
payload. `platformListSource(src, stanza, defaults)` writes "`system:*` and seven named ones, the shipped defaults"
(or "the shipped defaults with `platformUsers.names` replaced"), then ", plus this estate's
`platformUsers.additionalNames`" for each `additional*` key set, then ", read from the ConfigMap `<name>` (key
`<key>`)". `/user-bindings` carries `platform_users_source` (`null` at self) and `/namespaces` carries
`platform_namespaces_source`: key names only, never the values. The direct-user note no longer says "system
components and `kubeadmin`" (`kubeadmin` may not be on the list) but "the cluster's own and break-glass identities".

### 3.8 What does not change

`platformNamespaces`' keys, its inline semantics and its messages; the lab's `environments/crc.yaml`; the settings file
rendered for every values set that sets no new key (T255-12); `/metrics` names nobody and moves by counts (T255-13);
every rendered Role, ClusterRole and binding (T255-14); the self tier's view (`include_platform` is still not sent,
open question (a)); the binding-event history (a reclassification writes no event); the database schema.

### 3.9 The budget

**Over the whole system (every cluster the dashboard polls, every replica, every restart), a name the estate lists
can only move the rows that name it from "raised" to "counted as platform", and back when it is removed:**

- the direct-user rows, their total and the worklist lose exactly the rows whose subject the list matches;
  `excluded_platform` rises by the same number on every cluster; the alert's subject counts the rest;
- the unmanaged finding moves exactly those User-subject rows from `unmanaged` (or `ok`) to `built_in`, and
  `gsd_bindings_total` moves by that count, with no name in any label;
- nothing is deleted from the store, no binding event is written, nothing is written to any cluster, and no
  permission is added or removed (T255-14: REMOVED 0, ADDED 0 across four values sets, election on and off).

A wrong list cannot widen anyone's access: the classification only decides what the dashboard reports. Its worst
case is a person listed by mistake, whose grants then show as counted instead of raised; the page states the count
and the list's source on the same line, and the values file is the reviewed record of who was listed.

### 3.10 Versions

Application 2.1.0 (`pyproject.toml`, `gsd/__init__.py`, `appVersion`) and chart 0.60.0, MINOR because values are added,
each with its history line, set by hand as the last releases were (`prepare-release.py` refuses a dirty tree and would
cut the `## Unreleased` heading). The CHANGELOG bullet goes first under `## Unreleased` and names the chart version, as
`tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release` requires.

## 4. Tests

### 4.1 One test per test case of the issue

| ID | test (file) | what it holds | why it fails on `afa01bb8` (measured, §4.2) |
|---|---|---|---|
| T255-1 | `test_t255_1_with_nothing_set_the_lists_are_those_of_2_0_0_plus_kube_admin` (`tests/test_config.py`) | with no stanza, `{}` or empty `additional*`, the prefixes are `("system:",)` and the names the six of 2.0.0 plus `kube:admin` (the operator's ruling of 2026-10-01), each written out in the test; `kubeadmin2`, `kube:admin2` and `System:admin` are people | `PlatformUsers` does not exist: the module fails to import |
| T255-2 | `test_t255_2_an_additional_name_appends_and_a_prefix_appends` (`tests/test_config.py`); `test_t255_2_a_named_user_leaves_the_rows_and_the_alert_and_is_counted` (`tests/test_rbac.py`) | listing `ocp-oauth-bind-serviceid` takes its two rows out of the rows, the total and the rollup, raises the excluded count from 1 to 3, turns the alert's subject from "3 direct user grants" to "1 direct user grant", and removing it restores them | `refresh_bindings` takes no `platform_users` (TypeError) |
| T255-3 | `test_t255_3_names_replaces_the_defaults_and_prefixes_still_applies` (`tests/test_config.py`); `test_t255_3_names_replaced_makes_kubeadmin_a_person` (`tests/test_rbac.py`) | `names: []` makes `kubeadmin` a person while `system:` still applies | no key reaches the names (import error; TypeError) |
| T255-4 | `test_t255_4_a_typo_is_refused_by_name`, six cases (`tests/test_config.py`) | an unknown key, `suffixes`, a glob, a string, a non-string and a non-mapping are refused, each by name | the loader never reads `platformUsers` |
| T255-5 | `test_t255_5_the_render_refuses_what_the_loader_refuses`, seven cases (`tests/test_chart_platform_users.py`) | the render refuses the same, an unknown `existingConfigMap` key, and an `enabled` that is not a boolean (a quoted `"false"` would turn it on) | `helm template` exits 0 on every case |
| T255-6 | `test_t255_6_the_stanza_reaches_the_settings_file`, `test_t255_6_an_absent_stanza_renders_no_key` (same file) | the settings file carries `platformUsers` when set and no new key when not | the first: the key is absent from the render; the second passes today (a guard) |
| T255-7 | `test_t255_7_a_stale_additional_entry_is_reportable_and_the_defaults_are_not` (`tests/test_config.py`); `test_t255_7_a_stale_additional_name_is_named_at_the_wide_tier`, `test_t255_7_the_stale_entries_and_the_source_are_withheld_at_self` (`tests/test_user_binding_paging.py`) | `ghost` is named, the listed bind account is not (its own rows match it), nothing is judged on a cluster whose bindings name no User, and both new fields are `null` at self | no such class, no such field (`KeyError`) |
| T255-8 | `test_t255_8_existing_configmap_beside_an_inline_list_fails_the_render` and `test_t255_8_a_replacing_key_set_empty_also_counts_as_inline`, both stanzas (`tests/test_chart_platform_users.py`); `test_t255_8_the_inline_stanza_beside_its_configmap_is_refused_at_start`, both stanzas (`tests/test_config.py`) | refused at render, naming both keys, and at start | `platformNamespaces.existingConfigMap is not a key this chart defines` (the wrong refusal), and the `platformUsers` cases render |
| T255-9 | `test_t255_9_a_configmap_list_equals_the_same_list_inline` and `test_t255_9_a_missing_or_malformed_file_refuses_the_start_naming_the_configmap_and_key`, both stanzas (`tests/test_config.py`); `test_t255_9_existing_configmap_is_mounted_as_a_file_and_named_in_the_settings` (`tests/test_chart_platform_users.py`) | the parsed lists equal the inline ones; a missing, invalid, empty or mistyped file refuses the start naming `(ConfigMap 'estate-platform', key 'lists.yaml')`; the volume is the whole ConfigMap, not optional, mounted without `subPath` in the dashboard container only | no such key, mount or reference |
| T255-10 | `test_t255_10_a_listed_user_is_built_in_not_unmanaged` (`tests/test_unmanaged_subjects.py`) | an unlabelled ClusterRoleBinding naming `jdoe` is `unmanaged`, and `built_in` once `jdoe` is listed | `refresh_bindings` takes no `platform_users` |
| T255-11 | `test_every_python_site_that_decides_or_consumes_platform_is_marked`, `test_the_chart_path_is_marked`, `test_the_site_pattern_sees_a_call_and_a_bound_method_pass_but_not_prose` (`tests/test_platform_classification_marker.py`, extended) | every new site carries `PLATFORM-CLASSIFICATION (#255, #353)`, `values.yaml`'s `platformUsers:` included | the extended pattern finds `PLATFORM_USER_NAMES` in `gsd/kube.py` unmarked, and `values.yaml` has no `platformUsers:` (`StopIteration`) |
| T255-12 | `test_t255_12_existing_values_render_the_namespace_list_as_before_and_no_user_key`, four value sets (`tests/test_chart_platform_users.py`) | no new key for a values file that sets none; `crc.yaml`'s `platformNamespaces` is the live ConfigMap's line (§2.7) | passes today (a guard) |
| T255-13 | `test_t255_13_the_exposition_moves_by_counts_and_names_nobody` (`tests/test_metrics.py`) | `unmanaged` 2 → 1 and `built_in` 0 → 1, and neither name in the exposition | `refresh_bindings` takes no `platform_users` |
| T255-14 | `test_t255_14_no_rendered_permission_moves_with_either_configmap` (`tests/test_chart_platform_users.py`), and the RBAC atoms of §4.3 | every Role, ClusterRole and binding renders identically inline or with both ConfigMaps | `existingConfigMap` is refused as an unknown key |
| T255-15 | `TestPlatformNotesNameTheirSource`, ten cases (`tests/test_ui.py`); `test_t255_15_the_envelope_says_where_the_list_comes_from` (`tests/test_namespaces_api.py`) | both notes name their source; a stale entry is reported; the state survives two timer repaints; no horizontal overflow at 375, 768 and 1280 px, light and dark; nothing at self | no `#du-platform-note`; no `platform_namespaces_source` |
| T255-16 | the lab walk, §5 | rows 11 → 10 → 11, `excluded_platform` 24 → 25 → 24, unmanaged 53 → 52 → 53 | the key does nothing today |

Added by the research and the design: `test_a_user_name_with_a_comma_is_one_name`, `test_the_summary_names_keys_and_never_values`,
`test_a_malformed_reference_is_refused` (`tests/test_config.py`); `test_a_reclassification_records_no_binding_event`
(`tests/test_rbac.py`); `test_the_poller_hands_the_settings_platform_users_to_every_refresh`
(`tests/test_unmanaged_subjects.py`, the hand-off a direct call cannot see); `test_an_empty_replacing_list_is_rendered_so_it_replaces`,
`test_an_unusable_reference_fails_the_render` and `test_changing_the_revision_rolls_the_pod_and_nothing_else_does_for_an_external_edit`
(`tests/test_chart_platform_users.py`); `test_a_replaced_axis_is_named_as_replaced` and `test_the_self_tier_shows_no_note`
(`tests/test_ui.py`). Three existing tests change with the design: `test_the_direct_user_view_is_unchanged` (its fake
reader builds six-field rows), `test_values_defaults.py`'s list of switches kept off (the two new
`existingConfigMap.enabled`), and the mock cluster's `test_fetch_user_bindings`
(`local-development/mock-app/tests/test_request_surface.py`, block 75), which read the reader's `is_platform` and is
run by `.github/workflows/mock-cluster.yml` on every pull request that changes `gsd/kube.py`, `gsd/config.py`,
`gsd/poller.py` or `gsd/store.py` — this one changes all four.

### 4.2 Each test fails without the change

On a clean worktree of `21132a25` (main after SPEC G1; none of the 30 files this spec changes differs from
`afa01bb8`) with only the test blocks applied (§7 blocks 46–61 and 75), `PYTHONPATH` at that tree's
`local-development` and the imported `gsd` printed from that tree, each file run alone (the mock cluster's suite in a
scratch virtualenv with `pip install -e .` and `-e 'mock-app[test]'`, as the workflow installs them):

| file | before (test blocks only) | after (every block) |
|---|---|---|
| `tests/test_config.py` | 1 error at collection: `ImportError: cannot import name 'PlatformUsers' from 'gsd.config'` | 118 passed |
| `tests/test_rbac.py` | 3 failed, 35 passed (the three new) | 38 passed |
| `tests/test_user_binding_paging.py` | 2 failed, 10 passed (the two new) | 12 passed |
| `tests/test_namespaces_api.py` | 1 failed, 25 passed (the new one) | 26 passed |
| `tests/test_unmanaged_subjects.py` | 3 failed, 52 passed (the two new, and the changed one: six-field rows) | 55 passed |
| `tests/test_metrics.py` | 1 failed, 37 passed (the new one) | 38 passed |
| `tests/test_chart_platform_users.py` | 18 failed, 5 passed (the five guards: T255-6's absent stanza and T255-12's four value sets) | 23 passed |
| `tests/test_platform_classification_marker.py` | 2 failed, 16 passed: `{'local-development/gsd/kube.py': [(207, 'PLATFORM_USER_NAMES = frozenset({')]}` and `StopIteration` on `platformUsers:` | 18 passed |
| `tests/test_values_defaults.py` | 2 failed, 5 passed: `listed but no longer false: ['platformNamespaces.existingConfigMap.enabled', 'platformUsers.existingConfigMap.enabled']` | 7 passed |
| `tests/test_ui.py -k TestPlatformNotesNameTheirSource --browser chromium` | 10 failed: `waiting for locator("#du-platform-note") to be visible` | 10 passed (inside the browser suite below) |
| `mock-app/tests/test_request_surface.py` (`pytest mock-app/tests`, the mock-openshift job; it needs the `mock-app[test]` extras) | 1 failed, 58 passed: `ImportError: cannot import name 'PlatformUsers' from 'gsd.config'` | 59 passed (without block 75: 1 failed, `AttributeError: 'UserBindingView' object has no attribute 'is_platform'`) |

### 4.3 The proof

§7 was not written by hand. The design was implemented in a copy of `afa01bb8`; a generator cut each block from that
copy at whole lines, Old from the file as the earlier blocks leave it and widened with context until it occurs exactly
once, and checked that the blocks, applied in order, give every implemented file byte for byte (`74 blocks across 29
files`). The review's corrections (Orchestrator's notes, 4) made them 75 across 30; they were proved again on a clean
worktree of `21132a25`, main after SPEC G1:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G2_platform_users.md <tree>
    75 blocks check out across 30 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G2_platform_users.md <tree> --apply

| check | command | result |
|---|---|---|
| the applied tree is the implemented copy | `diff -r` of the 29 files | all 29 identical (`cmp`) to the implemented copy (the first 74 blocks, before the review's corrections; the corrected blocks are proved by the rows below) |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py`, on `21132a25` with every block applied and this spec, the index and its test in the tree, as the implementing pull request will have them | `6249 passed, 23 skipped, 665 deselected, 5 xfailed` (the first version, on `afa01bb8` without this spec in the tree: `6180 passed, 22 skipped, 665 deselected, 5 xfailed`) |
| browser suite | `pytest tests/test_ui.py -q -p no:cacheprovider --browser chromium` | `661 passed` |
| mock cluster (the `mock-openshift` job) | `pytest mock-app/tests -q`, in a virtualenv with `pip install -e .` and `-e 'mock-app[test]'`, as the workflow installs them | `59 passed`; without block 75, `1 failed, 58 passed`: `AttributeError: 'UserBindingView' object has no attribute 'is_platform'` |
| markdown | `markdownlint-cli2` on the chart README, the exclusions document, `API.md` and the CHANGELOG | 15 findings before and after, the same per file and rule, all on main already; none new |
| chart | `helm lint`; `helm template` with the defaults and each of the three values files | `1 chart(s) linted, 0 chart(s) failed`; every render exits 0 |
| the settings file (T255-12) | the rendered `clusters.yaml` of `21132a25` and of the applied chart, parsed, for the defaults and the three values files | the parsed settings are equal for all four; the text differs in 9 lines, every one a comment of the template (§6: the pod rolls once) |
| RBAC (T255-14) | every Role/ClusterRole rule and binding subject as an atom, four values sets × leader election on and off, before, after, and after with both lists in ConfigMaps | 66 / 63 (defaults), 73 / 73 (`crc.yaml`), 66 / 63 and 71 / 71 (the two production examples) atoms with election on / off, the same before, after and with both ConfigMaps: REMOVED 0, ADDED 0 |

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here. The read-only half is measured (§2.7). The implementing pull
request runs this walk, deployed with `local-development/release-crc.sh` from its branch, with the lab's values file
(`environments/crc.yaml`) as the only input changed:

1. **Before.** Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (2026-10-01:
   `f065b7a4-535c-4ef1-868c-58f5afee4953`, `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`). Deploy the branch unchanged and
   wait for the refresh line (`<cluster>: N direct-user binding(s), M naming a person`). Read `dashboard`'s
   `/api/clusters/dashboard/user-bindings` at the wide tier (`total` 11, `excluded_platform` 24 predicted by §2.7) and
   the public `/metrics` (`finding="unmanaged"` 53). The dashboard's own numbers are the ones recorded; §2.7's are
   the prediction.
2. **Add.** In `environments/crc.yaml` add `platformUsers: {additionalNames: ["tmp-contractor-9931"]}` and deploy.
   Expected after the refresh line: `total` 10, `excluded_platform` 25, `platform_users_unmatched` `{}`, the alert's
   subject one fewer, `unmanaged` 52, and the Namespace audit tab's note "… plus this estate's
   `platformUsers.additionalNames`".
3. **Stale.** Add `ghost-9931` beside it and deploy: `platform_users_unmatched` is
   `{"additionalNames": ["ghost-9931"]}` and the page shows the ⚠ line; the three numbers do not move.
4. **Remove.** Put `environments/crc.yaml` back to its merged content and deploy: 11, 24 and 53 again.
5. **After.** The PVC UIDs again, unchanged; screenshots of the Namespace audit tab at 375, 768 and 1280 px, light and
   dark, under `reports/<date>_<slug>/`.

`existingConfigMap` is not walked on the lab by default: it needs a ConfigMap created in the release namespace,
which the walk may do (a throwaway `estate-platform-g2` holding `additionalNames: ["tmp-contractor-9931"]`), then
`platformUsers.existingConfigMap: {enabled: true, name: estate-platform-g2}` in the values file, the same numbers as
step 2, and the ConfigMap deleted after step 4.

## 6. What an operator sees, and what it costs

- **Nothing, until the values file says something.** With no `platformUsers` the classification is 2.0.0's plus
  `kube:admin` (the operator's ruling of 2026-10-01: a grant naming OpenShift's bootstrap user is counted as the
  platform's; no binding on the CRC lab names it) and the settings file is the one rendered today; the image and
  chart versions move and the pod rolls once because the template's comments changed.
- **With a list.** The listed users' grants leave the worklist and the alert and are counted; the direct-user note
  reads "N platform identities excluded — the cluster's own and break-glass identities, with nowhere to migrate to.
  · `system:*` and seven named ones, the shipped defaults, plus this estate's `platformUsers.additionalNames`."; a stale
  entry gets a ⚠ line under it; the namespace index's note names its source the same way.
- **With a ConfigMap.** One more mounted directory in the dashboard container; a missing ConfigMap keeps the pod from
  starting (as `trustedCA`'s does), a bad key stops the start with a message naming it; an edit takes effect when
  `revision` changes and the release is rolled out.
- **A refusal.** A typo in the values file fails the render with the key's name; a typo inside the ConfigMap stops
  the start with the ConfigMap's name and key in the last log line.
- **Costs.** No permission, no schema change, no new request to any cluster. One `SELECT DISTINCT user_name` per
  `/user-bindings` read at the wide tier, over a table of the cluster's direct-user rows (35 on the lab).

Lines added and removed by §7 (`git diff --numstat` on the applied tree):

| file | added | removed |
|---|---|---|
| `charts/group-sync-dashboard/Chart.yaml` | 7 | 2 |
| `charts/group-sync-dashboard/README.md` | 28 | 2 |
| `charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md` | 9 | 2 |
| `charts/group-sync-dashboard/templates/_helpers.tpl` | 63 | 19 |
| `charts/group-sync-dashboard/templates/configmap.yaml` | 18 | 6 |
| `charts/group-sync-dashboard/templates/deployment.yaml` | 20 | 0 |
| `charts/group-sync-dashboard/values.yaml` | 67 | 1 |
| `docs/CHANGELOG.md` | 22 | 0 |
| `local-development/API.md` | 19 | 3 |
| `local-development/gsd/__init__.py` | 1 | 1 |
| `local-development/gsd/api.py` | 17 | 7 |
| `local-development/gsd/config.py` | 221 | 5 |
| `local-development/gsd/kube.py` | 5 | 30 |
| `local-development/gsd/poller.py` | 17 | 11 |
| `local-development/gsd/state.py` | 1 | 1 |
| `local-development/gsd/static/index.html` | 38 | 11 |
| `local-development/gsd/storage.py` | 1 | 0 |
| `local-development/gsd/store.py` | 9 | 2 |
| `local-development/mock-app/tests/test_request_surface.py` | 5 | 1 |
| `local-development/pyproject.toml` | 1 | 1 |
| `local-development/tests/test_config.py` | 136 | 1 |
| `local-development/tests/test_metrics.py` | 38 | 0 |
| `local-development/tests/test_namespaces_api.py` | 13 | 0 |
| `local-development/tests/test_platform_classification_marker.py` | 21 | 11 |
| `local-development/tests/test_rbac.py` | 66 | 0 |
| `local-development/tests/test_ui.py` | 85 | 0 |
| `local-development/tests/test_unmanaged_subjects.py` | 70 | 4 |
| `local-development/tests/test_user_binding_paging.py` | 42 | 0 |
| `local-development/tests/test_values_defaults.py` | 2 | 0 |
| `local-development/tests/test_chart_platform_users.py` (new) | 179 | 0 |

## 7. Implementation blocks

Applied in this order. Blocks 1–37 are the application, 38–45 the chart, 46–61 the tests, 62–69 the documents,
70–74 the release fields, and 75 the mock cluster's test (placed last so that no block is renumbered).

### Block 1 — local-development/gsd/config.py

`PlatformNamespaces` remembers the ConfigMap its lists came from (`origin`), outside equality (§3.5).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    additional_names: frozenset[str] = frozenset()

```

New text:

```python
    additional_names: frozenset[str] = frozenset()
    # The ConfigMap (name, key) the lists were read from, or None for the settings file (#255). Not part of
    # equality: a list read from a ConfigMap classifies exactly as the same list written inline.
    origin: tuple[str, str] | None = field(default=None, compare=False)

```

### Block 2 — local-development/gsd/config.py

`PlatformNamespaces.summary`, the shipped User constants moved here from `gsd/kube.py` unchanged, `PlatformUsers` with `matches`, `unmatched` and `summary`, and `_list_summary` (§3.1, §3.4, §3.7).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        return stale
# ── Connection modes (SPEC_S3 §3/§4 — S3a ships the keys, S3b connects) ─────────────────────────
```

New text:

```python
        return stale

    def summary(self) -> dict:
        """Where the list comes from, for the page's note (#255); see `_list_summary`."""
        return _list_summary(
            self.origin,
            [key for key, value, default in (("prefixes", self.prefixes, PLATFORM_NAMESPACE_PREFIXES),
                                             ("suffixes", self.suffixes, ()),
                                             ("names", self.names, PLATFORM_NAMESPACES)) if value != default],
            [key for key, value in (("additionalPrefixes", self.additional_prefixes),
                                    ("additionalSuffixes", self.additional_suffixes),
                                    ("additionalNames", self.additional_names)) if value])


# The shipped User defaults, moved here from gsd/kube.py by #255 so the settings can default to them (gsd.kube
# imports gsd.config, not the reverse): 2.0.0's lists plus `kube:admin`, by the operator's ruling of 2026-10-01
# (#255); values.yaml `platformUsers.prefixes`/`names` replace them and
# `additionalPrefixes`/`additionalNames` widen them. Kubernetes reserves `system:` "for Kubernetes system use"
# (RBAC, "Referring to subjects"). Measured on the reference cluster: 36 direct-user bindings, of which 22 are
# these — kube-apiserver, kube-scheduler, kube-controller-manager, the node identities, and SA-shaped users like
# `system:serviceaccount:...`. Flagging them would bury the real findings under platform noise, which is the
# same mistake the `system:` GROUP tiering exists to avoid.
# PLATFORM-CLASSIFICATION (#255, #353): the User prefixes
PLATFORM_USER_PREFIXES = ("system:",)
# PLATFORM-CLASSIFICATION (#255, #353): the User names
PLATFORM_USER_NAMES = frozenset({
    "kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler", "kube-proxy",
    # kubeadmin is OpenShift's break-glass cluster identity, not a person with an LDAP
    # account. Flagging it as a migration violation is noise: there is nowhere to migrate
    # it TO, and on the reference cluster it accounted for 12 of the 14 non-system rows —
    # so leaving it in would have made the finding look like a kubeadmin report.
    "kubeadmin",
    # The same identity, by the name OpenShift's bootstrap authenticator gives it outside CRC: openshift/library-go
    # `BootstrapUser = "kube:admin"` (`kubeadmin` is only its login), and every project it requests binds
    # `kube:admin` as admin. The operator's ruling of 2026-10-01 (#255): "kubeadmin or kube:admin is a trusted user
    # in crc that we use as admin" — one trusted admin identity, both names shipped.
    "kube:admin",
})


@dataclass(frozen=True)
class PlatformUsers:
    """Which User subjects are the platform's rather than a person's (#255).

    The direct-user view's question and the unmanaged finding's, answered once: a platform user's grants
    are counted (`excluded_platform`, `built_in`) and never raised. Two axes, plain prefix and exact name,
    as `PlatformNamespaces` has them; no suffix axis (#255: a user is named, not a family with a common
    ending). `prefixes` and `names` replace the shipped defaults, `additional_*` append to them — the
    common case is an estate naming its own break-glass or bind account.
    """

    prefixes: tuple[str, ...] = PLATFORM_USER_PREFIXES
    names: frozenset[str] = PLATFORM_USER_NAMES
    additional_prefixes: tuple[str, ...] = ()
    additional_names: frozenset[str] = frozenset()
    # As on PlatformNamespaces: the ConfigMap (name, key) the lists were read from, outside equality.
    origin: tuple[str, str] | None = field(default=None, compare=False)

    # THE User classifier — the direct-user rows and their alert, the binding classification and the
    # unmanaged finding all read the flag the poller stores from it.
    # PLATFORM-CLASSIFICATION (#255, #353)
    def matches(self, name: str) -> bool:
        """Whether this User subject is the platform's. Byte-exact, as the self tier matches a viewer."""
        if name in self.names or name in self.additional_names:
            return True
        if self.prefixes and name.startswith(self.prefixes):
            return True
        return bool(self.additional_prefixes) and name.startswith(self.additional_prefixes)

    def unmatched(self, users: list[str]) -> dict[str, list[str]]:
        """Every `additional*` entry that matches none of `users`, by axis.

        `users` is every User subject on the cluster's bindings, platform ones included: users have no
        index of their own. An unmatched entry can be planned, misspelled, or no longer bound; this method
        reports the observation, not a deletion. An empty `users` judges nothing: a cluster's bindings always name its own
        `system:` components as Users, so none at all means they have not been read there (the namespace
        index shows its stale patterns only beside platform rows, likewise). The shipped defaults are not
        reported, as for namespaces."""
        if not users:
            return {}
        stale: dict[str, list[str]] = {}
        missing = [p for p in self.additional_prefixes if not any(u.startswith(p) for u in users)]
        if missing:
            stale["additionalPrefixes"] = missing
        present = set(users)
        missing_names = sorted(n for n in self.additional_names if n not in present)
        if missing_names:
            stale["additionalNames"] = missing_names
        return stale

    def summary(self) -> dict:
        """Where the list comes from, for the page's note (#255); see `_list_summary`."""
        return _list_summary(
            self.origin,
            [key for key, value, default in (("prefixes", self.prefixes, PLATFORM_USER_PREFIXES),
                                             ("names", self.names, PLATFORM_USER_NAMES)) if value != default],
            [key for key, value in (("additionalPrefixes", self.additional_prefixes),
                                    ("additionalNames", self.additional_names)) if value])


def _list_summary(origin: tuple[str, str] | None, replaced: list[str], additional: list[str]) -> dict:
    """The page's "where this list comes from" (#255): the shipped axes the estate replaced, the `additional*`
    axes it set, and the ConfigMap it was read from. Key names only — the note says where to look, and the
    values are the configuration's, not the payload's."""
    return {"configMap": None if origin is None else {"name": origin[0], "key": origin[1]},
            "replaced": replaced, "additional": additional}


# ── Connection modes (SPEC_S3 §3/§4 — S3a ships the keys, S3b connects) ─────────────────────────
```

### Block 3 — local-development/gsd/config.py

`Settings.platform_users`, defaulting to the 2.0.0 rule (§3.1).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    platform_namespaces: PlatformNamespaces = PlatformNamespaces()

```

New text:

```python
    platform_namespaces: PlatformNamespaces = PlatformNamespaces()
    # Which User subjects are the platform's (#255). Defaults to the rule gsd/kube.py shipped in 2.0.0.
    # PLATFORM-CLASSIFICATION (#255, #353): the settings every consumer reads it from (values.yaml platformUsers → clusters.yaml)
    platform_users: PlatformUsers = PlatformUsers()

```

### Block 4 — local-development/gsd/config.py

The namespace parser takes its mapping from `_platform_stanza` and names a ConfigMap source in its refusals (§3.5, §3.6).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    source = raw.get("platformNamespaces")
    if source is None:
        return PlatformNamespaces()
    if not isinstance(source, dict):
        raise ConfigError(f"platformNamespaces: expected a mapping, got {source!r}")
    known = {"prefixes", "suffixes", "names", "additionalPrefixes", "additionalSuffixes", "additionalNames"}
    unknown = set(source) - known
    if unknown:
        raise ConfigError(f"platformNamespaces: unknown key(s) {sorted(unknown)}; "
```

New text:

```python
    source, origin = _platform_stanza(raw, "platformNamespaces")
    if source is None:
        return PlatformNamespaces()
    at = _origin_text(origin)
    if not isinstance(source, dict):
        raise ConfigError(f"platformNamespaces{at}: expected a mapping, got {source!r}")
    known = {"prefixes", "suffixes", "names", "additionalPrefixes", "additionalSuffixes", "additionalNames"}
    unknown = set(source) - known
    if unknown:
        raise ConfigError(f"platformNamespaces{at}: unknown key(s) {sorted(unknown)}; "
```

### Block 5 — local-development/gsd/config.py

A list error from a ConfigMap names it; inline, the #259 message is unchanged (§3.6).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        values = _string_list_setting(source, key, default)
```

New text:

```python
        try:
            values = _string_list_setting(source, key, default)
        except ConfigError as exc:
            if origin is None:
                raise
            # From a ConfigMap the message names it: the reader fixes that object, not the values file.
            raise ConfigError(f"platformNamespaces.{key}{at}: {exc}") from exc
```

### Block 6 — local-development/gsd/config.py

The glob refusal names a ConfigMap source too (§3.6).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
                    f"platformNamespaces.{key}: {value!r} contains {''.join(sorted(bad))} — matching is "
```

New text:

```python
                    f"platformNamespaces.{key}{at}: {value!r} contains {''.join(sorted(bad))} — matching is "
```

### Block 7 — local-development/gsd/config.py

The parsed namespaces carry their origin; `_origin_text`, `_platform_stanza` (inline or the mounted file, never both) and `_platform_users_setting` (§3.5, §3.6).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        additional_names=frozenset(axis("additionalNames", ())),
    )
```

New text:

```python
        additional_names=frozenset(axis("additionalNames", ())),
        origin=origin,
    )


def _origin_text(origin: tuple[str, str] | None) -> str:
    """How a refusal names a list read from a ConfigMap; nothing for the settings file's own stanza."""
    return "" if origin is None else f" (ConfigMap {origin[0]!r}, key {origin[1]!r})"


def _platform_stanza(raw: dict, stanza: str) -> tuple[object, tuple[str, str] | None]:
    """The mapping a platform list is parsed from, and the ConfigMap (name, key) it came from (#255).

    Inline, `<stanza>` in the settings file; or `<stanza>ConfigMap: {name, key, path, revision}`, which the
    chart renders for `<stanza>.existingConfigMap` and mounts at `path`, holding the same mapping as YAML.
    Both at once is refused, as the chart refuses it at render: two sources for one answer is the defect,
    not a convenience. The file is read here, once, at start — the kubelet refreshes a mounted file, but
    nothing re-reads it, so the classification never changes under a running poll; `revision` is not read,
    it is in the settings file so that changing it in the values file rolls the pod (checksum/config)."""
    ref_key = f"{stanza}ConfigMap"
    inline, ref = raw.get(stanza), raw.get(ref_key)
    if ref is None:
        return inline, None
    if inline is not None:
        raise ConfigError(f"{stanza} and {ref_key} are both set; the lists come from one of them — "
                          f"inline in the values file or the ConfigMap, never both")
    if not isinstance(ref, dict) or not {"name", "key", "path"} <= set(ref) <= {"name", "key", "path", "revision"} \
            or not all(isinstance(ref[k], str) and ref[k] for k in ("name", "key", "path")):
        raise ConfigError(f"{ref_key}: expected {{name, key, path}}, each a non-empty string, and an optional "
                          f"revision, got {ref!r}")
    origin = (ref["name"], ref["key"])
    where = f"{stanza}{_origin_text(origin)}"
    try:
        text = Path(ref["path"]).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{where}: cannot read {ref['path']}: {exc.strerror or exc}; the ConfigMap must "
                          f"hold the key {origin[1]!r}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{where}: invalid YAML in {ref['path']}: {exc}") from exc
    if data is None:
        raise ConfigError(f"{where}: {ref['path']} is empty; it must hold the {stanza} mapping itself, "
                          f"for example `additionalNames: [...]`")
    return data, origin


# PLATFORM-CLASSIFICATION (#255, #353): values.yaml `platformUsers` → the chart's configmap → clusters.yaml → this parse
def _platform_users_setting(raw: dict) -> PlatformUsers:
    """`platformUsers` from the settings file (#255), or the 2.0.0 rule when absent.

    Built as `platformNamespaces` is, with two differences. No suffix axis: a user is named, not a family
    with a common ending. And every axis must be a LIST: Kubernetes puts no format on a user name ("the
    RBAC authorization system does not require any format for usernames"), so `cn=jdoe,ou=People` is one
    name and a comma-separated string can never be split safely. An unknown key, a non-list, a non-string
    entry and a glob character are refused by name, as the chart refuses them at render.
    """
    source, origin = _platform_stanza(raw, "platformUsers")
    if source is None:
        return PlatformUsers()
    at = _origin_text(origin)
    if not isinstance(source, dict):
        raise ConfigError(f"platformUsers{at}: expected a mapping, got {source!r}")
    known = {"prefixes", "names", "additionalPrefixes", "additionalNames"}
    unknown = set(source) - known
    if unknown:
        raise ConfigError(f"platformUsers{at}: unknown key(s) {sorted(unknown)}; expected any of "
                          f"{', '.join(sorted(known))} — a user is matched by a plain prefix or an exact name")

    def axis(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        value = source.get(key)
        if value is None:
            return default
        if not isinstance(value, list):
            raise ConfigError(f"platformUsers.{key}{at}: expected a list of strings, got {value!r}; a user "
                              f"name may contain a comma, so a string is never split")
        out: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ConfigError(f"platformUsers.{key}{at}: every entry must be a string, got {item!r}")
            bad = {c for c in "*?[]" if c in item}
            if bad:
                raise ConfigError(
                    f"platformUsers.{key}{at}: {item!r} contains {''.join(sorted(bad))} — matching is literal, "
                    f"not a glob. A prefix or a full name; `svc-*` is a prefix `svc-` on additionalPrefixes.")
            if item.strip():
                out.append(item.strip())
        # A repeated entry is harmless to matching and noise in a diff, as for namespaces.
        return tuple(dict.fromkeys(out))

    return PlatformUsers(
        prefixes=axis("prefixes", PLATFORM_USER_PREFIXES),
        names=frozenset(axis("names", tuple(sorted(PLATFORM_USER_NAMES)))),
        additional_prefixes=axis("additionalPrefixes", ()),
        additional_names=frozenset(axis("additionalNames", ())),
        origin=origin,
    )
```

### Block 8 — local-development/gsd/config.py

`load_settings` parses `platformUsers` (§3.1).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        platform_namespaces=_platform_namespaces_setting(raw),   # PLATFORM-CLASSIFICATION (#255, #353)
        user_activity_visibility=_visibility_setting(raw),
```

New text:

```python
        platform_namespaces=_platform_namespaces_setting(raw),   # PLATFORM-CLASSIFICATION (#255, #353)
        platform_users=_platform_users_setting(raw),   # PLATFORM-CLASSIFICATION (#255, #353)
        user_activity_visibility=_visibility_setting(raw),
```

### Block 9 — local-development/gsd/kube.py

The User constants and `is_platform_user` leave the reader; a comment says where the decision is now (§3.2).

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
# Platform identities that appear as `kind: User` on bindings the cluster ships with, and
# which must never be reported as a governance violation. Measured on the reference
# cluster: 36 direct-user bindings, of which 22 are these — kube-apiserver, kube-scheduler,
# kube-controller-manager, the node identities, and SA-shaped users like
# `system:serviceaccount:...`. Flagging them would bury the real findings under platform
# noise, which is the same mistake the `system:` GROUP tiering exists to avoid.
# The User classifier — a `system:` name or one of the identities below is the platform's; no values key
# widens it (the operator's rule keys Users on the name, ServiceAccounts on the namespace).
# PLATFORM-CLASSIFICATION (#255, #353): the User prefixes and names
PLATFORM_USER_PREFIXES = ("system:",)
PLATFORM_USER_NAMES = frozenset({
    "kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler", "kube-proxy",
    # kubeadmin is OpenShift's break-glass cluster identity, not a person with an LDAP
    # account. Flagging it as a migration violation is noise: there is nowhere to migrate
    # it TO, and on the reference cluster it accounted for 12 of the 14 non-system rows —
    # so leaving it in would have made the finding look like a kubeadmin report.
    "kubeadmin",
})


# PLATFORM-CLASSIFICATION (#255, #353): the User classifier
def is_platform_user(name: str) -> bool:
    """Whether a User subject is a cluster-internal identity rather than a person."""
    return name.startswith(PLATFORM_USER_PREFIXES) or name in PLATFORM_USER_NAMES
```

New text:

```python
# Which User subject is the platform's is not decided here (#255): the reader has no settings, so the poller
# classifies each User row from `Settings.platform_users` (gsd/config.py PlatformUsers), as it classifies
# ServiceAccounts from `platform_namespaces`.
```

### Block 10 — local-development/gsd/kube.py

`UserBindingView` carries no platform flag (§3.2).

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
    is_platform: bool
    """Cluster-internal identity (system:*, kube-apiserver, …) rather than a person.
    Carried rather than filtered out, so the UI can report the whole picture and the count
    of what it excluded — silently dropping rows is how a tool loses trust."""
```

New text:

```python
    # No platform flag (#255): the poller decides it from the settings and stores it beside the row, which
    # is carried rather than filtered out, so the page can report the count of what it excluded.
```

### Block 11 — local-development/gsd/kube.py

`_user_binding_views` decides nothing (§3.2).

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
                user_name=subject["name"],
                # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's rule, unchanged by #353
                is_platform=is_platform_user(subject["name"]),
            )
```

New text:

```python
                user_name=subject["name"],
            )
```

### Block 12 — local-development/gsd/poller.py

The poller imports `PlatformUsers` and no longer `is_platform_user` (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
from .config import (CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN, ClusterConfig, ConfigError, PlatformNamespaces, Settings,
                     remote_policy)
from .home import PLATFORM_CONTROLLER_BINDINGS
from .kube import (AUTH_FAILED, OK, SERVICE_ACCOUNT_KIND, SUBJECT_KINDS, UNREACHABLE, USER_KIND, ClusterClient,
                   ClusterError, GroupSyncView, GroupView, dn_equal, is_platform_user)
```

New text:

```python
from .config import (CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN, ClusterConfig, ConfigError, PlatformNamespaces,
                     PlatformUsers, Settings, remote_policy)
from .home import PLATFORM_CONTROLLER_BINDINGS
from .kube import (AUTH_FAILED, OK, SERVICE_ACCOUNT_KIND, SUBJECT_KINDS, UNREACHABLE, USER_KIND, ClusterClient,
                   ClusterError, GroupSyncView, GroupView, dn_equal)
```

### Block 13 — local-development/gsd/poller.py

`_binding_is_platform` takes the User classifier (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
def _binding_is_platform(b, platform: PlatformNamespaces) -> int:
```

New text:

```python
def _binding_is_platform(b, platform: PlatformNamespaces, users: PlatformUsers) -> int:
```

### Block 14 — local-development/gsd/poller.py

Its docstring names `platformUsers`.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
    platform's when `is_platform_user` names it (system:*, kubeadmin, the node identities), as the
    direct-user view has always decided. And OpenShift's own per-project controller bindings —
```

New text:

```python
    platform's when the estate's `platformUsers` names it (system:*, kubeadmin, the node identities by
    default), the classifier the direct-user rows are stored with. And OpenShift's own per-project
    controller bindings —
```

### Block 15 — local-development/gsd/poller.py

A User subject on the finding path is classified by the settings' list (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        return 1 if is_platform_user(b.group_name) else 0
```

New text:

```python
        return 1 if users.matches(b.group_name) else 0
```

### Block 16 — local-development/gsd/poller.py

`refresh_bindings` takes `platform_users`, as it takes `platform_namespaces` (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
    platform_namespaces: PlatformNamespaces | None = None,
) -> str:
```

New text:

```python
    platform_namespaces: PlatformNamespaces | None = None,
    platform_users: PlatformUsers | None = None,
) -> str:
```

### Block 17 — local-development/gsd/poller.py

The shipped rule when a caller passes none, as for namespaces (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
    platform = platform_namespaces if platform_namespaces is not None else PlatformNamespaces()
    group_changes = store.replace_bindings(
```

New text:

```python
    platform = platform_namespaces if platform_namespaces is not None else PlatformNamespaces()
    # PLATFORM-CLASSIFICATION (#255, #353): the same for Users — the Poller passes the settings' platformUsers
    user_rule = platform_users if platform_users is not None else PlatformUsers()
    group_changes = store.replace_bindings(
```

### Block 18 — local-development/gsd/poller.py

The finding path receives it.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
                "is_platform": _binding_is_platform(b, platform),   # PLATFORM-CLASSIFICATION (#255, #353)
```

New text:

```python
                "is_platform": _binding_is_platform(b, platform, user_rule),   # PLATFORM-CLASSIFICATION (#255, #353)
```

### Block 19 — local-development/gsd/poller.py

Each `user_binding` row's flag is the settings' classification (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
              # PLATFORM-CLASSIFICATION (#255, #353): the direct-user flag, from is_platform_user in the reader
              "is_platform": 1 if u.is_platform else 0} for u in user_rows],
```

New text:

```python
              # PLATFORM-CLASSIFICATION (#255, #353): the direct-user flag, from the settings' platformUsers
              "is_platform": 1 if user_rule.matches(u.user_name) else 0} for u in user_rows],
```

### Block 20 — local-development/gsd/poller.py

The refresh line's count of people uses the same classifier.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        people = sum(1 for u in user_rows if not u.is_platform)
```

New text:

```python
        people = sum(1 for u in user_rows if not user_rule.matches(u.user_name))
```

### Block 21 — local-development/gsd/poller.py

`Poller._run_cluster` hands the settings' `platform_users` to every refresh (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
                        platform_namespaces=self.settings.platform_namespaces,
                        namespaces_read=self.settings.namespaces_read_enabled,
```

New text:

```python
                        platform_namespaces=self.settings.platform_namespaces,
                        # PLATFORM-CLASSIFICATION (#255, #353): and its platformUsers, the values file's or the ConfigMap's
                        platform_users=self.settings.platform_users,
                        namespaces_read=self.settings.namespaces_read_enabled,
```

### Block 22 — local-development/gsd/store.py

A schema comment names `platformUsers` instead of the removed function (a comment only; no migration).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
    -- effective namespace the estate's platformNamespaces name, or a User is_platform_user names.
```

New text:

```python
    -- effective namespace the estate's platformNamespaces name, or a User its platformUsers name.
```

### Block 23 — local-development/gsd/store.py

The finding CASE's comment, likewise.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
                        -- values file's additional* lists), or a User is_platform_user names.
```

New text:

```python
                        -- values file's additional* lists), or a User the estate's platformUsers name.
```

### Block 24 — local-development/gsd/store.py

`Store.user_binding_names`: every User subject on a cluster's bindings, what a stale entry is judged against (§3.4).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python

    # -- namespace-configuration-operator health -----------------------------------------
```

New text:

```python

    def user_binding_names(self, cluster_id: str) -> list[str]:
        """Every User subject named on this cluster's bindings, platform ones included, sorted: what a
        stale `platformUsers.additional*` entry is judged against (#255), since users have no index of
        their own."""
        return [r["user_name"] for r in self._rows(
            "SELECT DISTINCT user_name FROM user_binding WHERE cluster_id=? ORDER BY user_name", (cluster_id,))]

    # -- namespace-configuration-operator health -----------------------------------------
```

### Block 25 — local-development/gsd/storage.py

The storage contract declares it (`tests/test_storage_seam.py` holds `Store` to the Protocol).

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python
    def platform_user_binding_count(self, cluster_id: str) -> int: ...
    def replace_user_bindings(
```

New text:

```python
    def platform_user_binding_count(self, cluster_id: str) -> int: ...
    def user_binding_names(self, cluster_id: str) -> list[str]: ...
    def replace_user_bindings(
```

### Block 26 — local-development/gsd/state.py

The alert's comment names where the stored flag comes from.

<!-- block: local-development/gsd/state.py | edit -->

Old text:

```python
    # PLATFORM-CLASSIFICATION (#255, #353): the direct-user alert leaves the platform's identities out, by the stored is_platform_user flag
```

New text:

```python
    # PLATFORM-CLASSIFICATION (#255, #353): the direct-user alert leaves the platform's identities out, by the flag the poller stored from platformUsers
```

### Block 27 — local-development/gsd/api.py

The namespace index carries `platform_namespaces_source` (§3.7).

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            "platform_patterns_unmatched": stale_patterns,
            "cluster_wide_groups": cluster_wide_groups,
```

New text:

```python
            "platform_patterns_unmatched": stale_patterns,
            # Where the namespace list comes from (#255): the page's note names it instead of a fixed sentence.
            "platform_namespaces_source": settings.platform_namespaces.summary(),
            "cluster_wide_groups": cluster_wide_groups,
```

### Block 28 — local-development/gsd/api.py

`include_platform`'s description names `platformUsers`.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            description="Include cluster-internal identities (`system:*`, `kubeadmin`). "
                        "Excluded by default: there is nowhere to migrate them to, and on "
                        "the reference cluster they were 34 of 36 rows."),
```

New text:

```python
            description="Include the platform's identities: the users `platformUsers` names "
                        "(by default `system:*`, the kube components, `kubeadmin` and `kube:admin`). "
                        "Excluded by default: there is nowhere to migrate them to, and on the "
                        "reference cluster they were 34 of 36 rows."),
```

### Block 29 — local-development/gsd/api.py

The handler's docstring, likewise.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        Cluster-internal identities (system:*, the kube components) and OpenShift's
        break-glass `kubeadmin` are excluded by default: there is nowhere to migrate them
        to, and on the reference cluster they were 34 of 36 rows, so including them would
```

New text:

```python
        The platform's identities — the users `platformUsers` names, by default system:*, the
        kube components and OpenShift's break-glass `kubeadmin` / `kube:admin` — are excluded by default:
        there is nowhere to migrate them to, and on the reference cluster they were 34 of 36 rows, so including them would
```

### Block 30 — local-development/gsd/api.py

`/user-bindings` carries `platform_users_unmatched` and `platform_users_source`, `null` at self (§3.4, §3.7).

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count (is_platform_user, stored at poll time)
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
```

New text:

```python
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count (platformUsers, stored at poll time)
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
            # Where that list comes from, and every `additional*` entry no User subject here matches (#255) —
            # judged against all of this cluster's User subjects, platform ones included. Withheld at self with
            # the count: both describe other people's grants.
            "platform_users_unmatched": (
                # PLATFORM-CLASSIFICATION (#255, #353): a stale platformUsers entry, reported where the count is
                settings.platform_users.unmatched(store.user_binding_names(cluster_id)) if scope == "all" else None),
            "platform_users_source": settings.platform_users.summary() if scope == "all" else None,
```

### Block 31 — local-development/gsd/static/index.html

The Built-in section's sentence names `platformUsers`.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
       <code>platformNamespaces</code> names, a <code>system:</code> user, <code>kubeadmin</code>.
       None of these is a finding.`,
```

New text:

```html
       <code>platformNamespaces</code> names, a user the chart's <code>platformUsers</code> names
       (by default a <code>system:</code> user, <code>kubeadmin</code> and <code>kube:admin</code>). None of these is a finding.`,
```

### Block 32 — local-development/gsd/static/index.html

The namespace index's note names its source instead of a fixed list (§3.7).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    <span class="muted"> · <code>openshift-*</code>, <code>kube-*</code>, and five named ones — the rule the Home page uses.</span>${stalePatterns}</div>`;
```

New text:

```html
    <span class="muted"> · ${platformListSource(d.platform_namespaces_source, "platformNamespaces",
      "<code>openshift-*</code>, <code>kube-*</code> and five named ones")} — the rule the Home page uses.</span>${stalePatterns}</div>`;
```

### Block 33 — local-development/gsd/static/index.html

A comment names `platformUsers` instead of the removed function.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  // PLATFORM-CLASSIFICATION (#255, #353): Home reads the stored flags — a Group's system: rule, a User's is_platform_user — and never decides
```

New text:

```html
  // PLATFORM-CLASSIFICATION (#255, #353): Home reads the stored flags — a Group's system: rule, a User's platformUsers — and never decides
```

### Block 34 — local-development/gsd/static/index.html

`platformListSource` and `platformUsersNote` (§3.4, §3.7).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html

/* Roles granted directly to a person, ranked by risk. */
```

New text:

```html

/* Where a platform list comes from (#255): the shipped defaults, the keys this estate set beside or in place
   of them, and the ConfigMap it was read from — all from the server's summary (`platform_*_source`), so the
   sentence is the configuration's and never a fixed list that is wrong on an estate that added to it. */
// PLATFORM-CLASSIFICATION (#255, #353): the platform notes name their source
function platformListSource(src, stanza, defaults) {
  const keys = (list) => list.map((k) => `<code>${esc(stanza)}.${esc(k)}</code>`).join(" and ");
  const s = src || {};
  const replaced = s.replaced || [], additional = s.additional || [];
  return (replaced.length ? `the shipped defaults with ${keys(replaced)} replaced` : `${defaults}, the shipped defaults`)
    + (additional.length ? `, plus this estate's ${keys(additional)}` : "")
    + (s.configMap ? `, read from the ConfigMap <code>${esc(s.configMap.name)}</code> (key <code>${esc(s.configMap.key)}</code>)` : "");
}

/* The direct-user section's platform note (#255): how many grants the platform's identities hold, where that
   list comes from, and any `additional*` entry no User subject on this cluster matches — the namespace index's
   idiom for a stale pattern. Wide tier only: at self both fields are null, with the count. */
function platformUsersNote(ub) {
  const stale = ub.platform_users_unmatched || {};
  const axes = Object.keys(stale).filter((k) => (stale[k] || []).length);
  if (!ub.excluded_platform && !axes.length) return "";
  const n = ub.excluded_platform || 0;
  const staleLine = !axes.length ? "" : `<div class="mt-2">⚠ ${axes
    .map((axis) => `<code>${esc(axis)}</code>: ${stale[axis].map((v) => `<code>${esc(v)}</code>`).join(", ")}`)
    .join("; ")} ${axes.length === 1 && stale[axes[0]].length === 1 ? "is" : "are"} not currently matched by any
    User subject on a binding in this cluster; keep planned entries, and check unexpected ones.</div>`;
  return `${n} platform identit${n === 1 ? "y" : "ies"} excluded — the cluster's own and break-glass identities,
    with nowhere to migrate to. <span class="muted">· ${platformListSource(ub.platform_users_source, "platformUsers",
      "<code>system:*</code> and seven named ones")}.</span>${staleLine}`;
}

/* Roles granted directly to a person, ranked by risk. */
```

### Block 35 — local-development/gsd/static/index.html

The direct-user note is computed once per paint.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const sortedGrants = grantsSorted(ub);

```

New text:

```html
  const sortedGrants = grantsSorted(ub);
  const platformNote = platformUsersNote(ub);

```

### Block 36 — local-development/gsd/static/index.html

The note on a cluster with no direct grant.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
        ${ub.excluded_platform ? `<br><span class="muted">${ub.excluded_platform} platform
          identit${ub.excluded_platform === 1 ? "y" : "ies"} excluded — system components
          and <code>kubeadmin</code> are break-glass, with nowhere to migrate to.</span>` : ""}
```

New text:

```html
        ${platformNote ? `<div class="mt-4" id="du-platform-note">${platformNote}</div>` : ""}
```

### Block 37 — local-development/gsd/static/index.html

The note under the worklist.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    ${ub.excluded_platform ? `<div class="filterbar-note mt-4">
      ${ub.excluded_platform} platform identit${ub.excluded_platform === 1 ? "y" : "ies"}
      excluded — system components and <code>kubeadmin</code> are break-glass and
      cluster-internal, with nowhere to migrate to.</div>` : ""}
```

New text:

```html
    ${platformNote ? `<div class="filterbar-note mt-4" id="du-platform-note">${platformNote}</div>` : ""}
```

### Block 38 — charts/group-sync-dashboard/templates/_helpers.tpl

One validator for both stanzas, `gsd.validatePlatformLists`, with `existingConfigMap` and its exclusion; `gsd.platformListDir` (§3.5, §3.6).

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```text
Which namespaces are the platform's (#255). REFUSED AT RENDER because the loader refuses the same
things at startup, and a green `helm upgrade` that CrashLoops the pod is the failure class this chart
has already shipped three of (#251). Measured in the review of #259, Codex C6: before this, a typo'd
`additionalSufixes` and a numeric entry both rendered happily into the ConfigMap and the pod refused
them on the next start.
*/ -}}
{{/* PLATFORM-CLASSIFICATION (#255, #353): refuses an unknown key or a non-list axis at render, so a typo never silently widens or narrows it */}}
{{- define "gsd.validatePlatformNamespaces" -}}
{{- with .Values.platformNamespaces -}}
{{- if not (kindIs "map" .) -}}
{{- fail (printf "platformNamespaces must be a mapping, got %s." (kindOf .)) -}}
{{- end -}}
{{- $known := list "prefixes" "suffixes" "names" "additionalPrefixes" "additionalSuffixes" "additionalNames" -}}
{{- range $key, $value := . -}}
{{- if not (has $key $known) -}}
{{- fail (printf "platformNamespaces.%s is not a key this chart defines; expected any of %s. A typo here is a pattern that never takes effect." $key (join ", " $known)) -}}
{{- end -}}
{{- if not (kindIs "invalid" $value) -}}
{{- if not (kindIs "slice" $value) -}}
{{- fail (printf "platformNamespaces.%s must be a list, got %s." $key (kindOf $value)) -}}
{{- end -}}
{{- range $entry := $value -}}
{{- if not (kindIs "string" $entry) -}}
{{- fail (printf "platformNamespaces.%s: every entry must be a string; %v is %s." $key $entry (kindOf $entry)) -}}
```

New text:

```text
Which namespaces and which users are the platform's (#255). REFUSED AT RENDER because the loader refuses
the same things at startup, and a green `helm upgrade` that CrashLoops the pod is the failure class this
chart has already shipped three of (#251). Measured in the review of #259, Codex C6: before this, a
typo'd `additionalSufixes` and a numeric entry both rendered happily into the ConfigMap and the pod
refused them on the next start. One definition for both stanzas, so the two refusals cannot drift.

`existingConfigMap` is the one key that is not a list: `{enabled, name, key}`, the shape of
`trustedCA.existingConfigMap`, plus `revision`, free text rendered into the settings file so that changing
it rolls the pod (the chart cannot see the ConfigMap's content, so it cannot roll on an edit by itself).
Enabled, it is refused beside any list of the same stanza (an `additional*` list with entries, or a
replacing key set at all), as rbac-auditors.yaml refuses `createClusterRole` beside `existingClusterRole`:
two sources for one answer is the defect. Its content cannot be checked here — a render has no cluster to
look it up in — so the loader refuses a typo inside it at start, naming the ConfigMap and the key.
*/ -}}
{{/* Where a platform list's existingConfigMap is mounted (#255): one directory per stanza, the whole ConfigMap, no subPath. */}}
{{- define "gsd.platformListDir" -}}
/etc/gsd/{{ . | kebabcase }}
{{- end -}}

{{/* PLATFORM-CLASSIFICATION (#255, #353): refuses an unknown key or a non-list axis at render, so a typo never silently widens or narrows it */}}
{{- define "gsd.validatePlatformLists" -}}
{{- $stanzas := list
      (dict "name" "platformNamespaces" "replace" (list "prefixes" "suffixes" "names") "add" (list "additionalPrefixes" "additionalSuffixes" "additionalNames") "hint" "A prefix, a suffix or a full name; `team-*` is a prefix `team-` on additionalPrefixes.")
      (dict "name" "platformUsers" "replace" (list "prefixes" "names") "add" (list "additionalPrefixes" "additionalNames") "hint" "A prefix or a full name; `svc-*` is a prefix `svc-` on additionalPrefixes.") -}}
{{- range $s := $stanzas -}}
{{- $stanza := index $.Values $s.name -}}
{{- if not (kindIs "invalid" $stanza) -}}
{{- if not (kindIs "map" $stanza) -}}
{{- fail (printf "%s must be a mapping, got %s." $s.name (kindOf $stanza)) -}}
{{- end -}}
{{- $known := concat $s.replace $s.add -}}
{{- $inline := list -}}
{{- range $key, $value := $stanza -}}
{{- if eq $key "existingConfigMap" -}}
{{- if not (kindIs "map" $value) -}}
{{- fail (printf "%s.existingConfigMap must be a mapping {enabled, name, key, revision}, got %s." $s.name (kindOf $value)) -}}
{{- end -}}
{{- range $k, $_ := $value -}}
{{- if not (has $k (list "enabled" "name" "key" "revision")) -}}
{{- fail (printf "%s.existingConfigMap.%s is not a key this chart defines; expected enabled, name, key, revision." $s.name $k) -}}
{{- end -}}
{{- end -}}
{{- if and (hasKey $value "enabled") (not (kindIs "bool" $value.enabled)) -}}
{{- fail (printf "%s.existingConfigMap.enabled must be true or false, got %s: a quoted \"false\" is a string, and a string turns it on." $s.name (kindOf $value.enabled)) -}}
{{- end -}}
{{- else if not (has $key $known) -}}
{{- fail (printf "%s.%s is not a key this chart defines; expected any of %s. A typo here is a pattern that never takes effect." $s.name $key (join ", " (append $known "existingConfigMap"))) -}}
{{- else if not (kindIs "invalid" $value) -}}
{{- if not (kindIs "slice" $value) -}}
{{- fail (printf "%s.%s must be a list, got %s." $s.name $key (kindOf $value)) -}}
{{- end -}}
{{- if or $value (has $key $s.replace) -}}{{- $inline = append $inline $key -}}{{- end -}}
{{- range $entry := $value -}}
{{- if not (kindIs "string" $entry) -}}
{{- fail (printf "%s.%s: every entry must be a string; %v is %s." $s.name $key $entry (kindOf $entry)) -}}
```

### Block 39 — charts/group-sync-dashboard/templates/_helpers.tpl

The rest of the validator: the glob refusal with each stanza's hint, the exclusion and the reference's name and key.

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```text
{{- fail (printf "platformNamespaces.%s: %q contains %s — matching is literal, not a glob. A prefix, a suffix or a full name; `team-*` is a prefix `team-` on additionalPrefixes." $key $entry $bad) -}}
{{- end -}}
```

New text:

```text
{{- fail (printf "%s.%s: %q contains %s — matching is literal, not a glob. %s" $s.name $key $entry $bad $s.hint) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $cm := $stanza.existingConfigMap | default dict -}}
{{- if $cm.enabled -}}
{{- if $inline -}}
{{- fail (printf "%s.existingConfigMap and %s.%s are both set: the list comes from one of them. Move the entries into the ConfigMap, or turn existingConfigMap off." $s.name $s.name (first $inline)) -}}
{{- end -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$" (toString $cm.name)) -}}
{{- fail (printf "%s.existingConfigMap.name must name a ConfigMap in the release namespace (a DNS subdomain), got %q." $s.name (toString $cm.name)) -}}
{{- end -}}
{{- if not (regexMatch "^[-._a-zA-Z0-9]+$" (toString $cm.key)) -}}
{{- fail (printf "%s.existingConfigMap.key must be a ConfigMap key ([-._a-zA-Z0-9]+), got %q." $s.name (toString $cm.key)) -}}
```

### Block 40 — charts/group-sync-dashboard/templates/configmap.yaml

The settings file renders both stanzas, or the ConfigMap reference; an empty replacing list is kept (§3.5, Orchestrator's note 1).

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->

Old text:

```yaml
    # Which namespaces are the platform's (#255). Rendered only when set: an absent key is the
    # shipped rule, and an empty mapping here would read as "replace the defaults with nothing".
    # PLATFORM-CLASSIFICATION (#255, #353): values.yaml platformNamespaces → this file → config.py _platform_namespaces_setting
    {{- $_ := include "gsd.validatePlatformNamespaces" . }}
    {{- with .Values.platformNamespaces }}
    {{- $set := dict }}
    {{- range $k, $v := . }}{{- if $v }}{{- $_ := set $set $k $v }}{{- end }}{{- end }}
    {{- if $set }}
    platformNamespaces: {{ toJson $set }}
```

New text:

```yaml
    # Which namespaces and which users are the platform's (#255). Rendered only when set: an absent key
    # is the shipped rule. An `additional*` list renders only with entries; a replacing key (`prefixes`,
    # `suffixes`, `names`) renders whenever it is set, even empty, because `names: []` means "none of the
    # shipped names" and dropping it would keep them silently. With existingConfigMap on, the key names the
    # ConfigMap and where deployment.yaml mounts it, and the loader reads the lists from that file; its
    # `revision` is here only so that changing it changes checksum/config and rolls the pod.
    # PLATFORM-CLASSIFICATION (#255, #353): values.yaml platformNamespaces → this file → config.py _platform_namespaces_setting
    # PLATFORM-CLASSIFICATION (#255, #353): values.yaml platformUsers → this file → config.py _platform_users_setting
    {{- $_ := include "gsd.validatePlatformLists" . }}
    {{- range $name := list "platformNamespaces" "platformUsers" }}
    {{- with index $.Values $name }}
    {{- $cm := .existingConfigMap | default dict }}
    {{- if $cm.enabled }}
    {{ $name }}ConfigMap: {{ toJson (dict "name" $cm.name "key" $cm.key "path" (printf "%s/%s" (include "gsd.platformListDir" $name) $cm.key) "revision" (ternary "" (toString $cm.revision) (kindIs "invalid" $cm.revision))) }}
    {{- else }}
    {{- $set := dict }}
    {{- range $k, $v := . }}{{- if and (ne $k "existingConfigMap") (kindIs "slice" $v) (or $v (has $k (list "prefixes" "suffixes" "names"))) }}{{- $_ := set $set $k $v }}{{- end }}{{- end }}
    {{- if $set }}
    {{ $name }}: {{ toJson $set }}
    {{- end }}
    {{- end }}
```

### Block 41 — charts/group-sync-dashboard/templates/deployment.yaml

The dashboard container mounts each enabled ConfigMap as a directory (§3.5).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
            {{- end }}
          {{- if .Values.probes.liveness.enabled }}
```

New text:

```yaml
            {{- end }}
            {{- range $name := list "platformNamespaces" "platformUsers" }}
            {{- $cm := (index $.Values $name | default dict).existingConfigMap | default dict }}
            {{- if $cm.enabled }}
            # A platform list kept in a ConfigMap you own (#255): the whole ConfigMap as a directory, never a
            # subPath, so the file is the kubelet's current copy. The dashboard reads it once, at start.
            - name: {{ $name | kebabcase }}
              mountPath: {{ include "gsd.platformListDir" $name }}
              readOnly: true
            {{- end }}
            {{- end }}
          {{- if .Values.probes.liveness.enabled }}
```

### Block 42 — charts/group-sync-dashboard/templates/deployment.yaml

The volumes, not optional (§3.5).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
        {{- end }}
        {{- if .Values.oauthProxy.enabled }}
```

New text:

```yaml
        {{- end }}
        {{- range $name := list "platformNamespaces" "platformUsers" }}
        {{- $cm := (index $.Values $name | default dict).existingConfigMap | default dict }}
        {{- if $cm.enabled }}
        - name: {{ $name | kebabcase }}
          configMap:
            # NOT optional, as trustedCA's: a list you named that is missing stops the pod rather than
            # starting it with the shipped defaults. A missing KEY reaches the loader, which names it.
            name: {{ $cm.name }}
        {{- end }}
        {{- end }}
        {{- if .Values.oauthProxy.enabled }}
```

### Block 43 — charts/group-sync-dashboard/values.yaml

The unmanaged finding's comment names `platformUsers`.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
  # ServiceAccount in a namespace `platformNamespaces` (below) names, a `system:` user, kubeadmin.
```

New text:

```yaml
  # ServiceAccount in a namespace `platformNamespaces` (below) names, a user `platformUsers` (below)
  # names — by default a `system:` user, the kube components, kubeadmin and kube:admin.
```

### Block 44 — charts/group-sync-dashboard/values.yaml

`platformNamespaces`' comment explains `existingConfigMap` and `revision`.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
# a direct grant the page says that too.
# PLATFORM-CLASSIFICATION (#255, #353): the estate's own additions to "which namespaces are the platform's" (#255). What
```

New text:

```yaml
# a direct grant the page says that too.
#
# `existingConfigMap` keeps the same six keys in a ConfigMap you own instead (#255), for an estate that
# maintains its platform list outside this chart: a ConfigMap in the release namespace, delivered by your
# own pipeline, whose key (`platform-namespaces.yaml` by default) holds the stanza as YAML, for example
#   additionalSuffixes: ["-operator", "-manager"]
#   additionalNames: ["kyverno"]
# It is mounted as a file (no new permission; the pod does not start while the ConfigMap is missing)
# and read ONCE, at start. The chart cannot see inside it, so editing it changes nothing until the pod
# restarts: after an edit, change `existingConfigMap.revision` to any new text in this release's values
# file and roll the release out through its deployment pipeline — the revision is rendered into the
# settings file, whose checksum rolls the pod. A typo inside the ConfigMap is refused when the pod
# starts, by the ConfigMap's name and key, because a render has no cluster to read it from. Setting it
# beside any list here is refused at render: one source per list.
# PLATFORM-CLASSIFICATION (#255, #353): the estate's own additions to "which namespaces are the platform's" (#255). What
```

### Block 45 — charts/group-sync-dashboard/values.yaml

`platformNamespaces.existingConfigMap`, and the `platformUsers` stanza with its comment (§3.1, §3.5).

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
  additionalNames: []       # e.g. ["kyverno", "group-sync-dashboard"]

# ---------------------------------------------------------------------------
# Cluster configuration as labelled Secrets  (#230, docs/specs/SPEC_S1_cluster_secrets.md)
```

New text:

```yaml
  additionalNames: []       # e.g. ["kyverno", "group-sync-dashboard"]

  # OR all of the above from a ConfigMap you own (see the comment above). Off: it needs a name.
  existingConfigMap:
    enabled: false
    name: ""
    key: platform-namespaces.yaml
    revision: ""      # change after editing the ConfigMap and roll the release out: the pod re-reads it

# ---------------------------------------------------------------------------
# Which USERS are the platform's rather than a person's  (#255)
# ---------------------------------------------------------------------------
# A platform user's direct grants are never a finding: the Namespace audit counts them as excluded
# ("24 platform identities excluded") instead of listing them in the worklist and the direct-user
# alert, and the unmanaged finding counts them as built-in. Which users those are differs by estate —
# a break-glass account, a bind account, a fleet login — so the list is yours, built like
# `platformNamespaces` above.
#
# The shipped defaults are the rule of 2.0.0 plus `kube:admin`: the prefix `system:` (Kubernetes reserves it
# "for Kubernetes system use") and the names below. `prefixes` and `names` REPLACE them; the `additional*`
# two APPEND, which is what an estate usually wants. Plain prefix and exact name only — no suffix, glob
# or regular expression, and every value is a list: a user name may contain a comma
# (`cn=jdoe,ou=People`), so a string is never split. A key that is not one of the four is refused by
# name at render and at start.
#
# `kubeadmin` and `kube:admin` are one trusted admin identity, both shipped: outside CRC the break-glass
# login `kubeadmin` signs in as the user `kube:admin` (openshift/library-go, bootstrapauthenticator), on CRC
# an HTPasswd `kubeadmin` signs in under its own name (the operator's ruling of 2026-10-01, #255).
#
# Never silent: the page states how many grants it excluded, names where this list comes from, and
# reports an `additional*` entry no User subject on a binding in that cluster currently matches — a
# pre-staged entry may be intentional, and the page asks the reader to check unexpected ones. A listed
# person's own grants also leave their self view of the Namespace audit, exactly as kubeadmin's do; Home
# still lists them.
# PLATFORM-CLASSIFICATION (#255, #353): the estate's own platform users. What this decides: the direct-user rows, their
# alert and their excluded count, and the unmanaged finding's built-in tier for a User subject.
platformUsers:
  # Uncomment to replace the shipped defaults outright (rarely what you want):
  # prefixes: ["system:"]
  # names: ["kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler", "kube-proxy", "kubeadmin", "kube:admin"]

  # What THIS estate adds for itself.
  additionalPrefixes: []
  additionalNames: []       # e.g. ["breakglass-admin"]

  # OR all of the above from a ConfigMap you own, as YAML under one key, with the same rules as
  # platformNamespaces.existingConfigMap: mounted, read at start, `revision` changed and the release rolled
  # out after an edit, refused beside an inline list. Off: it needs a name.
  existingConfigMap:
    enabled: false
    name: ""
    key: platform-users.yaml
    revision: ""

# ---------------------------------------------------------------------------
# Cluster configuration as labelled Secrets  (#230, docs/specs/SPEC_S1_cluster_secrets.md)
```

### Block 46 — local-development/tests/test_config.py

The loader tests import `PlatformUsers`.

<!-- block: local-development/tests/test_config.py | edit -->

Old text:

```python
from gsd.config import ClusterConfig, ConfigError, PlatformNamespaces, load_settings
```

New text:

```python
from gsd.config import ClusterConfig, ConfigError, PlatformNamespaces, PlatformUsers, load_settings
```

### Block 47 — local-development/tests/test_config.py

T255-1, T255-3, T255-4, T255-7's classifier half and T255-9's loader half, and T255-8 at start.

<!-- block: local-development/tests/test_config.py | edit -->

Old text:

```python
        assert cfg._trusted_ca_context() is second, "and it is cached again until it next changes"
```

New text:

```python
        assert cfg._trusted_ca_context() is second, "and it is cached again until it next changes"


# ── #255: platformUsers, and existingConfigMap for both platform lists ─────────────────────────────

def _settings(tmp_path, body: str):
    """A settings file with one cluster plus `body`, loaded."""
    path = tmp_path / f"pu-{abs(hash(body)) % 10**8}.yaml"
    path.write_text("clusters:\n  - name: a\n    apiUrl: https://x\n    tokenEnv: T\n" + body)
    return load_settings(path)


def _from_configmap(tmp_path, stanza: str, content: str, name: str = "estate-platform", key: str = "lists.yaml"):
    """What the chart renders for `<stanza>.existingConfigMap`, with the mounted file written where it points."""
    mounted = tmp_path / f"{stanza}-{key}"
    mounted.write_text(content)
    ref = f'{{"name": "{name}", "key": "{key}", "path": "{mounted}"}}'
    return _settings(tmp_path, f"{stanza}ConfigMap: {ref}\n")


class TestPlatformUsersAreConfigurable:
    """#255: which User subjects are the platform's was compiled into the image (gsd/kube.py, 2.0.0), so an
    estate could not name its own break-glass or bind account without a release."""

    #: The 2.0.0 lists, written out rather than imported: the defaults test must fail if the code's
    #: defaults move, not move with them (the issue's Definition of Done) — and `kube:admin`, which the
    #: operator's ruling of 2026-10-01 on #255 adds: OpenShift's bootstrap user, one identity with `kubeadmin`.
    PREFIXES_200 = ("system:",)
    NAMES_200 = frozenset({"kube-apiserver", "kubelet", "kube-controller-manager", "kube-scheduler",
                           "kube-proxy", "kubeadmin"})
    NAMES_RULED_2026_10_01 = frozenset({"kube:admin"})

    def test_t255_1_with_nothing_set_the_lists_are_those_of_2_0_0_plus_kube_admin(self, tmp_path):
        for body in ("", "platformUsers: {}\n", "platformUsers:\n  additionalPrefixes: []\n  additionalNames: []\n"):
            users = _settings(tmp_path, body).platform_users
            assert users.prefixes == self.PREFIXES_200, body
            assert users.names == self.NAMES_200 | self.NAMES_RULED_2026_10_01, body
            assert users.additional_prefixes == () and users.additional_names == frozenset(), body
            assert users == PlatformUsers(), body
        default = PlatformUsers()
        for name in ("system:admin", "system:serviceaccount:apps:deployer", "kube:admin", *sorted(self.NAMES_200)):
            assert default.matches(name), name
        for name in ("ocp-oauth-bind-serviceid", "jdoe", "kubeadmin2", "kube:admin2", "Kube:Admin", "System:admin"):
            assert not default.matches(name), name

    def test_t255_2_an_additional_name_appends_and_a_prefix_appends(self, tmp_path):
        users = _settings(tmp_path, 'platformUsers:\n  additionalNames: ["ocp-oauth-bind-serviceid"]\n'
                                    '  additionalPrefixes: ["svc-"]\n').platform_users
        for name in ("ocp-oauth-bind-serviceid", "svc-backup", "kubeadmin", "system:admin"):
            assert users.matches(name), name
        assert not users.matches("jdoe")

    def test_t255_3_names_replaces_the_defaults_and_prefixes_still_applies(self, tmp_path):
        users = _settings(tmp_path, "platformUsers:\n  names: []\n").platform_users
        assert not users.matches("kubeadmin"), "names: [] replaces the shipped names with none"
        assert users.matches("system:kube-scheduler"), "the prefix axis is untouched"
        users = _settings(tmp_path, 'platformUsers:\n  prefixes: ["corp-"]\n').platform_users
        assert users.matches("corp-ops") and users.matches("kubeadmin") and not users.matches("system:admin")

    @pytest.mark.parametrize("body, wanted", [
        ('platformUsers:\n  additionalName: ["x"]\n', "platformUsers: unknown key(s) ['additionalName']"),
        ('platformUsers:\n  suffixes: ["-bot"]\n', "unknown key(s) ['suffixes']"),
        ('platformUsers:\n  additionalNames: ["svc-*"]\n', "platformUsers.additionalNames: 'svc-*' contains * — matching is literal"),
        ('platformUsers:\n  additionalNames: "a,b"\n', "platformUsers.additionalNames: expected a list of strings"),
        ('platformUsers:\n  additionalNames: [3]\n', "platformUsers.additionalNames: every entry must be a string"),
        ('platformUsers: "nope"\n', "platformUsers: expected a mapping"),
    ])
    def test_t255_4_a_typo_is_refused_by_name(self, tmp_path, body, wanted):
        with pytest.raises(ConfigError, match=re.escape(wanted)):
            _settings(tmp_path, body)

    def test_a_user_name_with_a_comma_is_one_name(self, tmp_path):
        users = _settings(tmp_path, 'platformUsers:\n  additionalNames: ["cn=svc,ou=Apps,dc=example,dc=com"]\n').platform_users
        assert users.additional_names == frozenset({"cn=svc,ou=Apps,dc=example,dc=com"})

    def test_t255_7_a_stale_additional_entry_is_reportable_and_the_defaults_are_not(self):
        users = PlatformUsers(additional_prefixes=("svc-", "gone-"), additional_names=frozenset({"ghost", "jdoe"}))
        assert users.unmatched(["jdoe", "svc-backup", "system:admin"]) == {
            "additionalPrefixes": ["gone-"], "additionalNames": ["ghost"]}
        assert PlatformUsers().unmatched([]) == {}, "the shipped defaults are never reported"
        assert users.unmatched([]) == {}, "no User subject at all is bindings not yet read, not every entry gone"

    def test_the_summary_names_keys_and_never_values(self, tmp_path):
        users = _settings(tmp_path, 'platformUsers:\n  names: ["root"]\n  additionalNames: ["ghost"]\n').platform_users
        assert users.summary() == {"configMap": None, "replaced": ["names"], "additional": ["additionalNames"]}
        assert PlatformUsers().summary() == {"configMap": None, "replaced": [], "additional": []}
        assert PlatformNamespaces(additional_suffixes=("-operator",)).summary() == {
            "configMap": None, "replaced": [], "additional": ["additionalSuffixes"]}


class TestPlatformListsFromAConfigMap:
    """#255: either list may live in a ConfigMap the estate owns. The chart mounts it and names it in the settings
    file (`<stanza>ConfigMap: {name, key, path}`); the loader reads the file at start and parses it exactly as the
    inline stanza, so the same list classifies the same either way (T255-9)."""

    USERS = 'additionalNames: ["ocp-oauth-bind-serviceid"]\nadditionalPrefixes: ["svc-"]\n'
    NAMESPACES = 'additionalSuffixes: ["-operator", "-manager"]\nadditionalNames: ["kyverno"]\n'

    def test_t255_9_a_configmap_list_equals_the_same_list_inline(self, tmp_path):
        inline = _settings(tmp_path, "platformUsers:\n" + "".join("  " + line + "\n" for line in self.USERS.splitlines()))
        mounted = _from_configmap(tmp_path, "platformUsers", self.USERS)
        assert mounted.platform_users == inline.platform_users
        assert mounted.platform_users.origin == ("estate-platform", "lists.yaml")
        assert mounted.platform_users.summary()["configMap"] == {"name": "estate-platform", "key": "lists.yaml"}
        inline = _settings(tmp_path, "platformNamespaces:\n" + "".join("  " + line + "\n" for line in self.NAMESPACES.splitlines()))
        mounted = _from_configmap(tmp_path, "platformNamespaces", self.NAMESPACES)
        assert mounted.platform_namespaces == inline.platform_namespaces
        assert mounted.platform_namespaces.matches("cert-manager-operator")

    @pytest.mark.parametrize("stanza", ["platformUsers", "platformNamespaces"])
    def test_t255_9_a_missing_or_malformed_file_refuses_the_start_naming_the_configmap_and_key(self, tmp_path, stanza):
        named = f"{stanza} (ConfigMap 'estate-platform', key 'lists.yaml')"
        ref = f'{stanza}ConfigMap: {{"name": "estate-platform", "key": "lists.yaml", "path": "{tmp_path}/absent.yaml"}}\n'
        with pytest.raises(ConfigError, match=re.escape(f"{named}: cannot read")):
            _settings(tmp_path, ref)
        with pytest.raises(ConfigError, match=re.escape(f"{named}: invalid YAML")):
            _from_configmap(tmp_path, stanza, "additionalNames: [unclosed\n")
        with pytest.raises(ConfigError, match=re.escape(f"{named}: ") + ".*is empty"):
            _from_configmap(tmp_path, stanza, "")
        with pytest.raises(ConfigError, match=re.escape(f"{named}: unknown key(s) ['additionalName']")):
            _from_configmap(tmp_path, stanza, 'additionalName: ["x"]\n')
        with pytest.raises(ConfigError, match=re.escape(f"{stanza}.additionalNames (ConfigMap 'estate-platform', key 'lists.yaml')")):
            _from_configmap(tmp_path, stanza, 'additionalNames: ["x-*"]\n')

    @pytest.mark.parametrize("stanza", ["platformUsers", "platformNamespaces"])
    def test_t255_8_the_inline_stanza_beside_its_configmap_is_refused_at_start(self, tmp_path, stanza):
        mounted = tmp_path / "lists.yaml"
        mounted.write_text('additionalNames: ["x"]\n')
        body = (f'{stanza}:\n  additionalNames: ["y"]\n'
                f'{stanza}ConfigMap: {{"name": "e", "key": "lists.yaml", "path": "{mounted}"}}\n')
        with pytest.raises(ConfigError, match=re.escape(f"{stanza} and {stanza}ConfigMap are both set")):
            _settings(tmp_path, body)

    def test_a_malformed_reference_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match=re.escape("platformUsersConfigMap: expected {name, key, path}")):
            _settings(tmp_path, 'platformUsersConfigMap: {"name": "e", "key": ""}\n')
```

### Block 48 — local-development/tests/test_rbac.py

T255-2 and T255-3 through a refresh: the rows, the counts and the alert; a reclassification writes no binding event.

<!-- block: local-development/tests/test_rbac.py | edit -->

Old text:

```python
        ) == []
```

New text:

```python
        ) == []


class TestPlatformUsersReachEveryReader:
    """#255: a user the estate names in `platformUsers` is the platform's everywhere the stored flag reaches —
    the direct-user rows, their total, the excluded count and the alert — because the poller classifies the
    User rows from the settings at each binding refresh (the reader has none)."""

    BIND = "ocp-oauth-bind-serviceid"

    def _refresh(self, store, monkeypatch, users=None):
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import UserBindingView

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return []
            def fetch_user_bindings(self):
                return [UserBindingView("ClusterRoleBinding", "", "poller", "ClusterRole", "poller", TestPlatformUsersReachEveryReader.BIND),
                        UserBindingView("RoleBinding", "group-sync-operator", "token-reader", "Role", "reader",
                                        TestPlatformUsersReachEveryReader.BIND),
                        UserBindingView("RoleBinding", "legacy", "jdoe-edit", "ClusterRole", "edit", "jdoe"),
                        UserBindingView("ClusterRoleBinding", "", "ka", "ClusterRole", "cluster-admin", "kubeadmin")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5, platform_users=users)

    @staticmethod
    def _alert_subjects(store):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        return [a.subject for a in st.compute_alerts("crc", [], [], datetime.now(UTC), td(minutes=2),
                                                     user_bindings=store.direct_user_bindings("crc"))]

    def test_t255_2_a_named_user_leaves_the_rows_and_the_alert_and_is_counted(self, store, monkeypatch):
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch)
        assert sorted(r["user_name"] for r in store.direct_user_bindings("crc")) == ["jdoe", self.BIND, self.BIND]
        assert store.platform_user_binding_count("crc") == 1
        assert self._alert_subjects(store) == ["3 direct user grants"]

        self._refresh(store, monkeypatch, PlatformUsers(additional_names=frozenset({self.BIND})))
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["jdoe"]
        assert store.count_direct_user_bindings("crc") == 1
        assert [r["namespace"] for r in store.user_bindings_by_namespace("crc")] == ["legacy"]
        assert store.platform_user_binding_count("crc") == 3, "excluded_platform rises by exactly the two rows"
        assert self._alert_subjects(store) == ["1 direct user grant"]

        self._refresh(store, monkeypatch)
        assert store.platform_user_binding_count("crc") == 1, "removed from the list, the rows come back"

    def test_t255_3_names_replaced_makes_kubeadmin_a_person(self, store, monkeypatch):
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch, PlatformUsers(names=frozenset()))
        assert "kubeadmin" in {r["user_name"] for r in store.direct_user_bindings("crc")}
        assert store.platform_user_binding_count("crc") == 0

    def test_a_reclassification_records_no_binding_event(self, store, monkeypatch):
        """Moving a user between "a person" and "the platform" changes what is counted, not what is granted:
        the event stream compares the role only (store.py _append_binding_events), so it stays silent."""
        from gsd.config import PlatformUsers
        self._refresh(store, monkeypatch)
        before = store.binding_events("crc")
        self._refresh(store, monkeypatch, PlatformUsers(additional_names=frozenset({self.BIND})))
        assert store.binding_events("crc") == before
```

### Block 49 — local-development/tests/test_user_binding_paging.py

T255-7 at the API: named at the wide tier, withheld at self.

<!-- block: local-development/tests/test_user_binding_paging.py | edit -->

Old text:

```python
                      params={"limit": 0}).status_code == 422
```

New text:

```python
                      params={"limit": 0}).status_code == 422


# ── #255: the platform list the excluded count comes from, and its stale entries ───────────────────

def _platform_users_app(tmp_path, *, proxy: bool):
    """kubeadmin and ocp-oauth-bind-serviceid stored as the poller classifies them under
    `platformUsers.additionalNames: [ocp-oauth-bind-serviceid, ghost]`; nothing names `ghost`."""
    from gsd.config import PlatformUsers
    db = str(tmp_path / "pu.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    store.replace_user_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "poller",
         "role_kind": "ClusterRole", "role_name": "poller", "user_name": "ocp-oauth-bind-serviceid", "is_platform": 1},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ka",
         "role_kind": "ClusterRole", "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy", "binding_name": "jdoe-edit",
         "role_kind": "ClusterRole", "role_name": "edit", "user_name": "jdoe", "is_platform": 0},
    ], now_iso())
    store.close()
    settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")],
                        oauth_proxy_enabled=proxy,
                        platform_users=PlatformUsers(additional_names=frozenset({"ocp-oauth-bind-serviceid", "ghost"})))
    return TestClient(build_app(settings, run_poller=False))


def test_t255_7_a_stale_additional_name_is_named_at_the_wide_tier(tmp_path):
    """`ghost` matches no User subject on this cluster; the bind account matches its own (platform) rows, so it is
    not stale — the judgement is against every User subject, platform ones included."""
    body = _platform_users_app(tmp_path, proxy=False).get("/api/clusters/c1/user-bindings").json()
    assert body["scope"] == "all"
    assert body["platform_users_unmatched"] == {"additionalNames": ["ghost"]}
    assert body["platform_users_source"] == {"configMap": None, "replaced": [], "additional": ["additionalNames"]}
    assert body["excluded_platform"] == 2 and body["total"] == 1


def test_t255_7_the_stale_entries_and_the_source_are_withheld_at_self(tmp_path):
    body = _platform_users_app(tmp_path, proxy=True).get(
        "/api/clusters/c1/user-bindings", headers={"X-Forwarded-User": "jdoe"}).json()
    assert body["scope"] == "self"
    assert body["platform_users_unmatched"] is None and body["platform_users_source"] is None
    assert body["excluded_platform"] is None
```

### Block 50 — local-development/tests/test_namespaces_api.py

T255-15's namespace half: the index says where its list comes from.

<!-- block: local-development/tests/test_namespaces_api.py | edit -->

Old text:

```python
            "a workload must stay a workload"


class TestAStalePatternIsReportedWhereItCanBeActedOn:
```

New text:

```python
            "a workload must stay a workload"

    def test_t255_15_the_envelope_says_where_the_list_comes_from(self, tmp_path):
        """The page's note named a fixed list ("openshift-*, kube-*, and five named ones"), wrong on an estate
        that adds to it — the lab adds three suffixes and two names (#255). The envelope now carries the keys
        the estate set, so the note can name its source."""
        estate = PlatformNamespaces(additional_suffixes=("-operator",), additional_names=frozenset({"kyverno"}))
        with self._client(tmp_path, estate) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_namespaces_source"] == {
            "configMap": None, "replaced": [], "additional": ["additionalSuffixes", "additionalNames"]}
        with self._client(tmp_path, PlatformNamespaces()) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_namespaces_source"] == {"configMap": None, "replaced": [], "additional": []}


class TestAStalePatternIsReportedWhereItCanBeActedOn:
```

### Block 51 — local-development/tests/test_unmanaged_subjects.py

The existing direct-user test, without the reader's flag (§3.2).

<!-- block: local-development/tests/test_unmanaged_subjects.py | edit -->

Old text:

```python
        finding path's flag never reaches user_binding."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import UserBindingView, is_platform_user
```

New text:

```python
        finding path's flag never reaches user_binding. Since #255 the reader carries no flag: the poller
        classifies the User rows from the settings' platformUsers, the 2.0.0 rule by default."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import UserBindingView
```

### Block 52 — local-development/tests/test_unmanaged_subjects.py

Its fake reader builds rows of six fields.

<!-- block: local-development/tests/test_unmanaged_subjects.py | edit -->

Old text:

```python
                                        "system:serviceaccount:apps:deployer", is_platform_user("system:serviceaccount:apps:deployer")),
                        UserBindingView("RoleBinding", "apps", "person", "ClusterRole", "edit", "jdoe", is_platform_user("jdoe"))]
```

New text:

```python
                                        "system:serviceaccount:apps:deployer"),
                        UserBindingView("RoleBinding", "apps", "person", "ClusterRole", "edit", "jdoe")]
```

### Block 53 — local-development/tests/test_unmanaged_subjects.py

T255-10, and the Poller's hand-off of `platform_users`.

<!-- block: local-development/tests/test_unmanaged_subjects.py | edit -->

Old text:

```python
        assert {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")} == {"apps-sa": "unmanaged"}
```

New text:

```python
        assert {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")} == {"apps-sa": "unmanaged"}


class TestPlatformUsersSilenceTheFinding:
    """#255: the unmanaged finding's User arm reads the same classifier as the direct-user view — the estate's
    `platformUsers`, handed to every refresh by the Poller."""

    @staticmethod
    def _user(name, person):
        return BindingView("ClusterRoleBinding", "", name, "ClusterRole", "edit", person, subject_kind="User")

    def test_t255_10_a_listed_user_is_built_in_not_unmanaged(self, store, monkeypatch):
        from gsd import poller
        from gsd.config import ClusterConfig, PlatformUsers

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return [TestPlatformUsersSilenceTheFinding._user("jdoe-edit", "jdoe")]
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        cluster = ClusterConfig("crc", "https://x", token_env="T")
        poller.refresh_bindings(store, cluster, timeout=5)
        assert findings(store) == {"jdoe-edit": "unmanaged"}
        poller.refresh_bindings(store, cluster, timeout=5, platform_users=PlatformUsers(additional_names=frozenset({"jdoe"})))
        assert findings(store) == {"jdoe-edit": "built_in"}
        assert store.count_bindings_by_finding("crc") == {"built_in": 1}

    def test_the_poller_hands_the_settings_platform_users_to_every_refresh(self, monkeypatch):
        """As for platformNamespaces (OB1-lite, review of #361): every other test hands the classifier to
        refresh_bindings itself, so none would see the Poller drop it."""
        from gsd import poller
        from gsd.config import PlatformUsers
        from gsd.kube import UserBindingView
        cluster = ClusterConfig("crc", "https://x", token_env="T")
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        settings = Settings(clusters=[cluster], binding_interval_seconds=0, kyverno_enabled=False,
                            platform_users=PlatformUsers(additional_names=frozenset({"jdoe"})))
        runner = poller.Poller(store, settings)
        monkeypatch.setattr(poller, "poll_once", lambda *a, **kw: "ok")
        monkeypatch.setattr(poller, "capture_once", lambda *a, **kw: None)
        monkeypatch.setattr(runner, "_after_poll", lambda *a: None)
        tick = iter(range(10000))
        monkeypatch.setattr(poller.time, "monotonic", lambda: next(tick) * 1000.0)

        class Client:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self):
                runner._stop.set()
                return [TestPlatformUsersSilenceTheFinding._user("jdoe-edit", "jdoe"),
                        TestPlatformUsersSilenceTheFinding._user("ann-edit", "ann")]
            def fetch_user_bindings(self):
                return [UserBindingView("ClusterRoleBinding", "", "jdoe-edit", "ClusterRole", "edit", "jdoe"),
                        UserBindingView("ClusterRoleBinding", "", "ann-edit", "ClusterRole", "edit", "ann")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", Client)
        runner._run_cluster(cluster)
        got = {r["binding_name"]: (r["finding"], r["is_platform"]) for r in store.all_bindings("crc")}
        people = [r["user_name"] for r in store.direct_user_bindings("crc")]
        excluded = store.platform_user_binding_count("crc")
        store.close()
        assert got == {"jdoe-edit": ("built_in", 1), "ann-edit": ("unmanaged", 0)}, got
        assert people == ["ann"] and excluded == 1
```

### Block 54 — local-development/tests/test_metrics.py

T255-13: `/metrics` moves by counts and names nobody.

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python
        assert "GroupSyncGroupCountCliff" not in off
```

New text:

```python
        assert "GroupSyncGroupCountCliff" not in off


class TestPlatformUsersMoveCountsNeverNames:
    """#255: naming a user in `platformUsers` moves `gsd_bindings_total` between findings by count; /metrics is
    unauthenticated by decision, so no user name may appear in it either way."""

    def test_t255_13_the_exposition_moves_by_counts_and_names_nobody(self, monkeypatch):
        from gsd import poller
        from gsd.config import ClusterConfig, PlatformUsers
        from gsd.kube import BindingView, UserBindingView

        bind = "ocp-oauth-bind-serviceid"

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self):
                return [BindingView("ClusterRoleBinding", "", "poller", "ClusterRole", "poller", bind, subject_kind="User"),
                        BindingView("RoleBinding", "legacy", "jdoe-edit", "ClusterRole", "edit", "jdoe", subject_kind="User")]
            def fetch_user_bindings(self):
                return [UserBindingView("ClusterRoleBinding", "", "poller", "ClusterRole", "poller", bind),
                        UserBindingView("RoleBinding", "legacy", "jdoe-edit", "ClusterRole", "edit", "jdoe")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        store.record_poll("crc", "ok", None)
        cluster = ClusterConfig("crc", "https://x", token_env="T")
        poller.refresh_bindings(store, cluster, timeout=5)
        before = series(generate_latest(build_registry(store, GRACE)).decode(), "gsd_bindings_total")
        poller.refresh_bindings(store, cluster, timeout=5, platform_users=PlatformUsers(additional_names=frozenset({bind})))
        text = generate_latest(build_registry(store, GRACE)).decode()
        after = series(text, "gsd_bindings_total")
        store.close()
        key = 'gsd_bindings_total{cluster="crc",finding="%s"}'
        assert (before[key % "unmanaged"], after[key % "unmanaged"]) == (2, 1)
        assert (before[key % "built_in"], after[key % "built_in"]) == (0, 1)
        assert bind not in text and "jdoe" not in text
```

### Block 55 — local-development/tests/test_chart_platform_users.py

T255-5, T255-6, T255-8, T255-9's chart half, T255-12, T255-14, and the `revision` roll.

<!-- block: local-development/tests/test_chart_platform_users.py | create -->

```python
"""#255 at render: `platformUsers` reaches the settings file the way `platformNamespaces` does, the render refuses
what the loader refuses, and either list may come from an existing ConfigMap — mounted as a file, never beside an
inline list, with no new permission. Before #255 the chart had no such key: `helm template --set
'platformUsers.additionalNames={ocp-oauth-bind-serviceid}'` exited 0 with the value nowhere in the render, and
`platformNamespaces.existingConfigMap` was refused as an unknown key."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_strategy import CHART

REPO = CHART.parents[1]


def _render(tmp_path, values: dict | None = None, *files) -> tuple[bool, str]:
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for f in files:
        args += ["-f", str(f)]
    if values is not None:
        path = tmp_path / f"v-{abs(hash(repr(values))) % 10**8}.yaml"
        path.write_text(yaml.safe_dump(values, sort_keys=False))
        args += ["-f", str(path)]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(out: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(out) if d]


def _settings(out: str) -> dict:
    """The rendered settings file (the ConfigMap's clusters.yaml), parsed."""
    cm = next(d for d in _docs(out) if d["kind"] == "ConfigMap" and d["metadata"]["name"].endswith("-config"))
    return yaml.safe_load(cm["data"]["clusters.yaml"])


def _dashboard(out: str) -> dict:
    deploy = next(d for d in _docs(out) if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")
    return deploy["spec"]["template"]["spec"]


@pytest.mark.parametrize("stanza, fragment", [
    ({"additionalName": ["x"]}, "platformUsers.additionalName is not a key this chart defines"),
    ({"suffixes": ["-bot"]}, "platformUsers.suffixes is not a key this chart defines"),
    ({"additionalNames": ["svc-*"]}, 'platformUsers.additionalNames: "svc-*" contains * — matching is literal, not a glob'),
    ({"additionalNames": "x"}, "platformUsers.additionalNames must be a list, got string"),
    ({"names": [3]}, "platformUsers.names: every entry must be a string"),
    ({"existingConfigMap": {"enabld": True}}, "platformUsers.existingConfigMap.enabld is not a key this chart defines"),
    ({"existingConfigMap": {"enabled": "false", "name": "e"}}, "platformUsers.existingConfigMap.enabled must be true or false, got string"),
])
def test_t255_5_the_render_refuses_what_the_loader_refuses(tmp_path, stanza, fragment):
    ok, out = _render(tmp_path, {"platformUsers": stanza})
    assert not ok and fragment in out, out[-600:]


def test_t255_6_the_stanza_reaches_the_settings_file(tmp_path):
    ok, out = _render(tmp_path, {"platformUsers": {"additionalNames": ["ocp-oauth-bind-serviceid"]}})
    assert ok, out[-600:]
    assert _settings(out)["platformUsers"] == {"additionalNames": ["ocp-oauth-bind-serviceid"]}


def test_t255_6_an_absent_stanza_renders_no_key(tmp_path):
    ok, out = _render(tmp_path)
    assert ok, out[-600:]
    settings = _settings(out)
    assert not {"platformUsers", "platformUsersConfigMap", "platformNamespacesConfigMap"} & set(settings), settings


def test_an_empty_replacing_list_is_rendered_so_it_replaces(tmp_path):
    """`names: []` means "none of the shipped names". The namespace render dropped every empty list, so before
    #255 `platformNamespaces.names: []` rendered nothing and kept the five names silently."""
    ok, out = _render(tmp_path, {"platformUsers": {"names": []}, "platformNamespaces": {"names": []}})
    assert ok, out[-600:]
    settings = _settings(out)
    assert settings["platformUsers"] == {"names": []} and settings["platformNamespaces"] == {"names": []}
    # ... and the loader reads what was rendered as "none": the behaviour change the CHANGELOG names.
    from gsd.config import _platform_namespaces_setting, _platform_users_setting
    namespaces, users = _platform_namespaces_setting(settings), _platform_users_setting(settings)
    assert not namespaces.matches("default") and not namespaces.matches("openshift")
    assert namespaces.matches("openshift-monitoring"), "the prefix axis is untouched"
    assert not users.matches("kubeadmin") and users.matches("system:admin")


@pytest.mark.parametrize("stanza, inline", [("platformUsers", "additionalNames"),
                                            ("platformNamespaces", "additionalSuffixes")])
def test_t255_8_existing_configmap_beside_an_inline_list_fails_the_render(tmp_path, stanza, inline):
    ok, out = _render(tmp_path, {stanza: {inline: ["x"], "existingConfigMap": {"enabled": True, "name": "estate-platform"}}})
    assert not ok, out[-600:]
    assert f"{stanza}.existingConfigMap and {stanza}.{inline} are both set" in out, out[-600:]


@pytest.mark.parametrize("stanza", ["platformUsers", "platformNamespaces"])
def test_t255_8_a_replacing_key_set_empty_also_counts_as_inline(tmp_path, stanza):
    ok, out = _render(tmp_path, {stanza: {"names": [], "existingConfigMap": {"enabled": True, "name": "estate-platform"}}})
    assert not ok and f"{stanza}.existingConfigMap and {stanza}.names are both set" in out, out[-600:]


@pytest.mark.parametrize("cm, fragment", [
    ({"enabled": True}, "existingConfigMap.name must name a ConfigMap"),
    ({"enabled": True, "name": "e", "key": "a/b"}, "existingConfigMap.key must be a ConfigMap key"),
])
def test_an_unusable_reference_fails_the_render(tmp_path, cm, fragment):
    ok, out = _render(tmp_path, {"platformUsers": {"existingConfigMap": cm}})
    assert not ok and fragment in out, out[-600:]


def test_t255_9_existing_configmap_is_mounted_as_a_file_and_named_in_the_settings(tmp_path):
    values = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "key": "users.yaml"}},
              "platformNamespaces": {"existingConfigMap": {"enabled": True, "name": "estate-platform",
                                                           "key": "namespaces.yaml"}}}
    ok, out = _render(tmp_path, values)
    assert ok, out[-600:]
    settings = _settings(out)
    assert settings["platformUsersConfigMap"] == {"name": "estate-platform", "key": "users.yaml",
                                                  "path": "/etc/gsd/platform-users/users.yaml", "revision": ""}
    assert settings["platformNamespacesConfigMap"]["path"] == "/etc/gsd/platform-namespaces/namespaces.yaml"
    assert "platformUsers" not in settings and "platformNamespaces" not in settings
    pod = _dashboard(out)
    volumes = {v["name"]: v for v in pod["volumes"]}
    for name in ("platform-users", "platform-namespaces"):
        assert volumes[name]["configMap"] == {"name": "estate-platform"}, "the whole ConfigMap, and not optional"
    mounts = {m["name"]: m for c in pod["containers"] if c["name"] == "dashboard" for m in c["volumeMounts"]}
    assert mounts["platform-users"] == {"name": "platform-users", "mountPath": "/etc/gsd/platform-users", "readOnly": True}
    assert "subPath" not in mounts["platform-namespaces"], "a subPath mount never sees a ConfigMap update"
    proxy = [m["name"] for c in pod["containers"] if c["name"] != "dashboard" for m in c.get("volumeMounts", [])]
    assert "platform-users" not in proxy and "platform-namespaces" not in proxy


def test_changing_the_revision_rolls_the_pod_and_nothing_else_does_for_an_external_edit(tmp_path):
    """The chart cannot see the ConfigMap's content, so an edit to it alone changes no rendered byte; the
    `revision` value is the release's way to say "re-read it" (checksum/config moves, the pod rolls)."""
    base = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform"}}}
    bumped = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "revision": "2"}}}
    zero = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "revision": 0}}}
    checksums = []
    for values in (base, base, bumped, zero):
        ok, out = _render(tmp_path, values)
        assert ok, out[-600:]
        deploy = next(d for d in _docs(out) if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")
        checksums.append(deploy["spec"]["template"]["metadata"]["annotations"]["checksum/config"])
    assert checksums[0] == checksums[1] != checksums[2]
    assert checksums[3] not in (checksums[0], checksums[2]), "`revision: 0` is a revision like any other, not unset"


@pytest.mark.parametrize("values_file", ["environments/crc.yaml", "environments/example-production.yaml",
                                         "charts/group-sync-dashboard/example-production.yaml", None])
def test_t255_12_existing_values_render_the_namespace_list_as_before_and_no_user_key(tmp_path, values_file):
    """The rendered settings carry no new key for a values file that sets none, and `platformNamespaces` is the
    lab's measured line (the live ConfigMap on CRC, 2026-10-01) or absent."""
    files = [REPO / values_file] if values_file else []
    ok, out = _render(tmp_path, None, *files)
    assert ok, out[-600:]
    settings = _settings(out)
    assert not {"platformUsers", "platformUsersConfigMap", "platformNamespacesConfigMap"} & set(settings)
    if values_file == "environments/crc.yaml":
        assert settings["platformNamespaces"] == {"additionalNames": ["kyverno", "group-sync-dashboard"],
                                                  "additionalSuffixes": ["-operator", "-manager", "-provisioner"]}


def test_t255_14_no_rendered_permission_moves_with_either_configmap(tmp_path):
    """A ConfigMap mounted as a volume is read by the kubelet, not by the dashboard's ServiceAccount: every Role,
    ClusterRole and binding renders identically with both lists inline or in ConfigMaps."""
    rbac_kinds = {"Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}

    def rbac(values):
        ok, out = _render(tmp_path, values)
        assert ok, out[-600:]
        objs = [d for d in _docs(out) if d["kind"] in rbac_kinds]
        for d in objs:
            d["metadata"].get("labels", {}).pop("helm.sh/chart", None)
        return sorted(yaml.safe_dump(d, sort_keys=True) for d in objs)

    inline = rbac({"platformUsers": {"additionalNames": ["x"]}})
    mounted = rbac({"platformUsers": {"existingConfigMap": {"enabled": True, "name": "e"}},
                    "platformNamespaces": {"existingConfigMap": {"enabled": True, "name": "e"}}})
    assert inline and inline == mounted
```

### Block 56 — local-development/tests/test_platform_classification_marker.py

T255-11: the marker covers every new site.

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
    r"platform_namespaces\.(matches|unmatched)\s*[(,)]|\bplatform\.matches\s*\(|PlatformNamespaces\(\)\.matches\s*\("
    r"|\bis_platform_user\s*\(|\bis_platform_namespace\s*\("
    r"|PLATFORM_CONTROLLER_BINDINGS\b|^PLATFORM_(NAMESPACE_PREFIXES|NAMESPACES|USER_PREFIXES) ="
    r"|^def _platform_namespaces_setting\(|_platform_namespaces_setting\(raw\)|^\s+platform_namespaces: PlatformNamespaces = "
    # ... and the stored flag's SQL comparisons and Python assignments (OB1-lite, review of #361); a Python read
    # or a dict-literal write of the flag is marked by hand and not held here (OB2, second pass)
    r'|\bis_platform\s*=\s*[01]\b|\["is_platform"\]\s*=')
CHART_SITES = {
    ROOT / "charts/group-sync-dashboard/values.yaml": "platformNamespaces:",
    ROOT / "charts/group-sync-dashboard/templates/configmap.yaml": ".Values.platformNamespaces",
    ROOT / "charts/group-sync-dashboard/templates/_helpers.tpl": 'define "gsd.validatePlatformNamespaces"',
}
```

New text:

```python
    r"platform_(namespaces|users)\.(matches|unmatched)\s*[(,)]|\b(platform|users|user_rule)\.matches\s*\("
    r"|Platform(Namespaces|Users)\(\)\.matches\s*\("
    r"|\bis_platform_user\s*\(|\bis_platform_namespace\s*\("
    r"|PLATFORM_CONTROLLER_BINDINGS\b|^PLATFORM_(NAMESPACE_PREFIXES|NAMESPACES|USER_PREFIXES|USER_NAMES) ="
    r"|^def _platform_(namespaces|users)_setting\(|_platform_(namespaces|users)_setting\(raw\)"
    r"|^\s+platform_namespaces: PlatformNamespaces = |^\s+platform_users: PlatformUsers = "
    # ... and the stored flag's SQL comparisons and Python assignments (OB1-lite, review of #361); a Python read
    # or a dict-literal write of the flag is marked by hand and not held here (OB2, second pass)
    r'|\bis_platform\s*=\s*[01]\b|\["is_platform"\]\s*=')
# Each needle is a line the chart's path starts from; the marker sits on it or within the three lines above.
CHART_SITES = (
    (ROOT / "charts/group-sync-dashboard/values.yaml", "platformNamespaces:"),
    (ROOT / "charts/group-sync-dashboard/values.yaml", "platformUsers:"),
    (ROOT / "charts/group-sync-dashboard/templates/configmap.yaml", 'include "gsd.validatePlatformLists"'),
    (ROOT / "charts/group-sync-dashboard/templates/_helpers.tpl", 'define "gsd.validatePlatformLists"'),
)
```

### Block 57 — local-development/tests/test_platform_classification_marker.py

`gsd/kube.py` is no longer a marked hop (Orchestrator's note 1).

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
    and the finding path. A hop that loses its marker, or a file that drops out, fails here."""
    marked = {str(p.relative_to(ROOT)) for p in GSD.rglob("*.py") if MARKER in p.read_text(encoding="utf-8")}
    assert {"local-development/gsd/home.py", "local-development/gsd/config.py", "local-development/gsd/kube.py",
```

New text:

```python
    and the finding path. A hop that loses its marker, or a file that drops out, fails here. gsd/kube.py is
    not a hop since #255: the reader classifies nothing, the poller decides a User from the settings."""
    marked = {str(p.relative_to(ROOT)) for p in GSD.rglob("*.py") if MARKER in p.read_text(encoding="utf-8")}
    assert {"local-development/gsd/home.py", "local-development/gsd/config.py",
```

### Block 58 — local-development/tests/test_platform_classification_marker.py

`CHART_SITES` holds both stanzas' chart sites.

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
    for path, needle in CHART_SITES.items():
```

New text:

```python
    for path, needle in CHART_SITES:
```

### Block 59 — local-development/tests/test_platform_classification_marker.py

The site pattern's examples gain the new sites.

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
    ('    ok = is_platform_user ("kubeadmin")', True),
    ("                    WHERE cluster_id=? AND is_platform=0", True),
```

New text:

```python
    ('    ok = is_platform_user ("kubeadmin")', True),
    ("        return 1 if users.matches(b.group_name) else 0", True),
    ('              "is_platform": 1 if user_rule.matches(u.user_name) else 0} for u in user_rows],', True),
    ("                settings.platform_users.unmatched(store.user_binding_names(cluster_id)) if scope", True),
    ("PLATFORM_USER_NAMES = frozenset({", True),
    ("    platform_users: PlatformUsers = PlatformUsers()", True),
    ("                    WHERE cluster_id=? AND is_platform=0", True),
```

### Block 60 — local-development/tests/test_values_defaults.py

The two new `existingConfigMap.enabled` switches default off, with the reason (`tests/test_values_defaults.py`'s rule).

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    "trustedCA.existingConfigMap.enabled": "needs the name of a ConfigMap the operator supplies",
    "ingress.enabled": "exclusive with the Route, which the chart renders by default",
```

New text:

```python
    "trustedCA.existingConfigMap.enabled": "needs the name of a ConfigMap the operator supplies",
    "platformNamespaces.existingConfigMap.enabled": "#255: needs the name of a ConfigMap the operator supplies, as trustedCA's",
    "platformUsers.existingConfigMap.enabled": "#255: needs the name of a ConfigMap the operator supplies, as trustedCA's",
    "ingress.enabled": "exclusive with the Route, which the chart renders by default",
```

### Block 61 — local-development/tests/test_ui.py

T255-15 in the browser.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at 375px"
```

New text:

```python
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at 375px"


class TestPlatformNotesNameTheirSource:
    """#255 (T255-15): the two platform notes on the Namespace audit tab named a fixed list — "system components
    and kubeadmin" under the direct-user worklist, "openshift-*, kube-*, and five named ones" on the namespace
    index, already wrong on the lab, whose values add three suffixes and two names. Each now names where its list
    comes from, from the payload's summary, and the direct-user note reports a stale `additional*` entry in the
    namespace index's idiom. The served rig carries the shipped defaults; the estate's states are injected into
    the payload on the 60 s repaint's own path, so a repaint keeps them."""

    STALE = {"additionalNames": ["breakglass-2024"]}
    SOURCE = {"configMap": {"name": "estate-platform", "key": "platform-users.yaml"}, "replaced": [],
              "additional": ["additionalNames"]}

    def _open(self, dash):
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("#du-platform-note")

    def _note(self, dash, selector="#du-platform-note"):
        return " ".join(dash.locator(selector).inner_text().split())

    def test_the_defaults_are_named_as_the_shipped_defaults(self, dash):
        self._open(dash)
        assert self._note(dash) == ("1 platform identity excluded — the cluster's own and break-glass identities, with "
                                    "nowhere to migrate to. · system:* and seven named ones, the shipped defaults.")
        line = self._note(dash, "#ns-show-platform >> xpath=..")
        assert "openshift-*, kube-* and five named ones, the shipped defaults — the rule the Home page uses." in line, line
        assert "and five named ones —" not in line

    def test_the_estates_list_and_a_stale_entry_survive_the_repaint(self, dash):
        import json as _json
        self._open(dash)

        def estate(route):
            body = route.fetch().json()
            body["platform_users_source"] = self.SOURCE
            body["platform_users_unmatched"] = self.STALE
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(body))

        def estate_ns(route):
            body = route.fetch().json()
            body["platform_namespaces_source"] = {"configMap": None, "replaced": [],
                                                  "additional": ["additionalSuffixes", "additionalNames"]}
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(body))

        dash.route("**/api/clusters/*/user-bindings*", estate)
        dash.route("**/api/clusters/*/namespaces", estate_ns)
        for _ in range(2):   # the first poll brings the estate's payload; the second is a repaint of the same
            dash.evaluate("() => refresh({auto: true})")
            dash.wait_for_function("() => document.querySelector('#du-platform-note') && "
                                   "document.querySelector('#du-platform-note').innerText.includes('breakglass-2024')")
        note = self._note(dash)
        assert ("system:* and seven named ones, the shipped defaults, plus this estate's platformUsers.additionalNames, "
                "read from the ConfigMap estate-platform (key platform-users.yaml).") in note, note
        assert ("⚠ additionalNames: breakglass-2024 is not currently matched by any User subject on a binding in "
                "this cluster; keep planned entries, and check unexpected ones.") in note, note
        line = self._note(dash, "#ns-show-platform >> xpath=..")
        assert ("the shipped defaults, plus this estate's platformNamespaces.additionalSuffixes and "
                "platformNamespaces.additionalNames — the rule the Home page uses.") in line, line

    def test_a_replaced_axis_is_named_as_replaced(self, dash):
        self._open(dash)
        dash.evaluate("""() => { data.userBindings.platform_users_source = {configMap: null, replaced: ['names'], additional: []};
            render(); }""")
        assert self._note(dash).endswith("· the shipped defaults with platformUsers.names replaced."), self._note(dash)

    def test_the_self_tier_shows_no_note(self, dash):
        self._open(dash)
        dash.evaluate("""() => { Object.assign(data.userBindings, {excluded_platform: null, platform_users_unmatched: null,
            platform_users_source: null}); render(); }""")
        assert dash.locator("#du-platform-note").count() == 0

    @pytest.mark.parametrize("width", [375, 768, 1280])
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_no_horizontal_overflow(self, dash, width, theme):
        dash.set_viewport_size({"width": width, "height": 900})
        self._open(dash)
        dash.evaluate("""([theme, src, stale]) => { document.documentElement.setAttribute('data-theme', theme);
            Object.assign(data.userBindings, {platform_users_source: src, platform_users_unmatched: stale});
            data.namespaces.platform_namespaces_source = {configMap: {name: 'estate-platform-namespaces-list', key: 'platform-namespaces.yaml'},
              replaced: ['prefixes', 'names'], additional: ['additionalSuffixes', 'additionalNames']};
            render(); }""", [theme, self.SOURCE, {"additionalPrefixes": ["svc-retired-"], "additionalNames": ["breakglass-2024", "kube:admin"]}])
        assert "are not currently matched by any User subject" in self._note(dash)
        overflow = dash.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at {width}px ({theme})"
```

### Block 62 — charts/group-sync-dashboard/README.md

The chart README's section for both stanzas.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text

### Unmanaged-grant discovery
```

New text:

```text

### Platform identities — `platformNamespaces` and `platformUsers`

Which namespaces and which users are the cluster's own rather than a workload's or a person's (#255). A
platform namespace is hidden by default on the Namespace audit index and on Home (counted, one control away);
a ServiceAccount in one, and a platform user, are never an unmanaged finding; a platform user's direct grants
are counted as excluded instead of joining the direct-user worklist and its alert. Every key is set in this
release's values file and takes effect when the release is rolled out through its deployment pipeline.

| Key | Default | Notes |
|---|---|---|
| `platformNamespaces.prefixes`, `.suffixes`, `.names` | unset: `openshift-`, `kube-`; none; `default`, `openshift`, `kube-system`, `kube-public`, `kube-node-lease` | set, each REPLACES its shipped default (an empty list means none) |
| `platformNamespaces.additionalPrefixes`, `.additionalSuffixes`, `.additionalNames` | `[]` | APPEND to the defaults: what an estate usually wants |
| `platformUsers.prefixes`, `.names` | unset: `system:`; `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`, `kubeadmin`, `kube:admin` | set, each REPLACES its shipped default (an empty list means none). `kubeadmin` and `kube:admin` are one identity: OpenShift's break-glass login signs in as `kube:admin` outside CRC |
| `platformUsers.additionalPrefixes`, `.additionalNames` | `[]` | APPEND; for example a bind or break-glass account |
| `platformNamespaces.existingConfigMap.enabled`, `platformUsers.existingConfigMap.enabled` | `false` | read that stanza's keys from a ConfigMap you own instead, as YAML under one key; refused at render beside any list of the same stanza |
| `….existingConfigMap.name` | `""` | the ConfigMap, in the release namespace; required when enabled, and the pod does not start while it is missing |
| `….existingConfigMap.key` | `platform-namespaces.yaml`, `platform-users.yaml` | the key holding the YAML; a missing key or a typo inside it stops the start with a message naming the ConfigMap and the key |
| `….existingConfigMap.revision` | `""` | free text: change it after editing the ConfigMap and roll the release out, and the pod restarts and reads the new list. The ConfigMap is read once, at start, and the chart cannot see inside it |

Matching is plain prefix, suffix (namespaces only) and exact name: no globs, no regular expressions, and a
value with `*`, `?`, `[` or `]` is refused. Each list is a YAML list; a user name may contain a comma, so a
`platformUsers` string is refused rather than split. An `additional*` entry that matches nothing on a cluster
is reported on that cluster's Namespace audit tab — for namespaces against its namespaces, for users against
the User subjects on its bindings. A ConfigMap is mounted as a volume (whole, no `subPath`), so it needs no
permission beyond what the chart already renders.

### Unmanaged-grant discovery
```

### Block 63 — charts/group-sync-dashboard/README.md

The unmanaged finding's paragraph names `platformUsers`.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
ServiceAccount in a namespace `platformNamespaces` names (the defaults below, plus the estate's
`additionalPrefixes`/`additionalSuffixes`/`additionalNames`), a `system:` user or `kubeadmin` join the
```

New text:

```text
ServiceAccount in a namespace `platformNamespaces` names and a user `platformUsers` names (the
defaults and the estate's additions, in the section above; a `system:` user, `kubeadmin` and `kube:admin` by default) join the
```

### Block 64 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md

The exclusions document's User row (#255's Definition of Done).

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
| User | the name starts with `system:`, or is `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy` or `kubeadmin` | the same rule the direct-user view uses |
```

New text:

```text
| User | the user is a platform user: by default the name starts with `system:`, or is `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`, `kubeadmin` or `kube:admin` | the shipped defaults, plus your `platformUsers.additionalPrefixes` and `additionalNames` in `values.yaml` (or a ConfigMap, `platformUsers.existingConfigMap`); the same list the direct-user view uses |
```

### Block 65 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md

How to silence the estate's own user, and `kube:admin`.

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text

Nothing else silences a grant. A Helm, OLM or Argo CD label, the binding's name, or a ServiceAccount's name
```

New text:

```text

To silence a user who is the estate's own (a bind account, a break-glass login), add the name to
`platformUsers.additionalNames` in the release's values file and roll it out through the release's deployment
pipeline. OpenShift's break-glass login is shipped under both of its names: `kubeadmin`, and `kube:admin`, the
user it signs in as outside CRC.

Nothing else silences a grant. A Helm, OLM or Argo CD label, the binding's name, or a ServiceAccount's name
```

### Block 66 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md

When a list change takes effect.

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
**Built-in**.
```

New text:

```text
**Built-in**. A change to `platformNamespaces` or `platformUsers` in the values file restarts the pod, whose first
refresh applies it; a list kept in a ConfigMap is read at start, so after editing it change its
`existingConfigMap.revision` in the values file and roll the release out.
```

### Block 67 — local-development/API.md

`/namespaces`' platform fields, with `platform_namespaces_source`.

<!-- block: local-development/API.md | edit -->

Old text:

```text
two counts, a platform identity's binding included.

```

New text:

```text
two counts, a platform identity's binding included.

Each row's `platform` is the chart's `platformNamespaces` classification; `platform_count` counts those rows,
`platform_with_findings` the ones holding a direct grant, and `platform_patterns_unmatched` names each
`additional*` pattern matching no namespace here. `platform_namespaces_source` says where the list comes from, in
the shape of `/user-bindings`' `platform_users_source`.

```

### Block 68 — local-development/API.md

`/user-bindings`' example payload.

<!-- block: local-development/API.md | edit -->

Old text:

```text
  "excluded_platform": 36,
  "namespace": null, "total": 6, "limit": 200, "offset": 0, "truncated": false,
```

New text:

```text
  "excluded_platform": 36,
  "platform_users_unmatched": {"additionalNames": ["breakglass-2024"]},
  "platform_users_source": {"configMap": null, "replaced": [], "additional": ["additionalNames"]},
  "namespace": null, "total": 6, "limit": 200, "offset": 0, "truncated": false,
```

### Block 69 — local-development/API.md

`excluded_platform`, `include_platform` and the two new fields.

<!-- block: local-development/API.md | edit -->

Old text:

```text
`excluded_platform` counts what was left out: `system:*` identities and `kubeadmin` are
break-glass with nowhere to migrate to, and on the reference cluster they were 34 of 36 rows.
`include_platform=true` shows them.
```

New text:

```text
`excluded_platform` counts what was left out: the platform's identities, the users the chart's
`platformUsers` names (by default `system:*`, the kube components, `kubeadmin` and `kube:admin`), with nowhere to migrate
to; on the reference cluster they were 34 of 36 rows. `include_platform=true` shows them. The flag is stored
with each row at the binding refresh, from the list the pod started with.

`platform_users_source` says where that list comes from: the shipped axes the estate replaced (`replaced`),
the `additional*` axes it set (`additional`), and the ConfigMap it was read from (`configMap`, `{name, key}`,
or `null` for the values file) — key names only, never the values. `platform_users_unmatched` names every
`additional*` entry that matches none of the User subjects on this cluster's bindings, platform ones included,
by axis (`{}` when none, and while the cluster's bindings have not been read). An entry can be unmatched because
it is planned, misspelled, or no longer bound; the response reports that observation, not a deletion. Both are
`null` at the self tier, with `excluded_platform`.
```

### Block 70 — docs/CHANGELOG.md

The CHANGELOG bullet, first under Unreleased, naming the chart version (§3.10).

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **An estate names its own platform users, and either platform list can live in a ConfigMap (#255, Epic G #387,
  `docs/specs/SPEC_G2_platform_users.md`; application 2.1.0, chart 0.60.0).** `platformUsers` in the values file
  works like `platformNamespaces`: `prefixes` and `names` replace the shipped defaults (`system:`, and
  `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`, `kubeadmin` as in 2.0.0,
  plus `kube:admin`), `additionalPrefixes` and `additionalNames` append to them. **`kube:admin` is new in the
  defaults** (the operator's ruling of 2026-10-01 on #255): it is OpenShift's bootstrap break-glass user, the same
  identity as `kubeadmin`, so a grant naming it — every project it requests binds it as admin — is now counted as the
  platform's instead of raised as a person's direct grant; no binding on the CRC lab names it. A listed user's grants leave the direct-user
  worklist and its alert, are counted in `excluded_platform`, and are `built_in` in the unmanaged finding; the
  poller classifies Users from the settings at each binding refresh, so one list feeds all four. An unknown key, a
  non-list, a non-string entry or a glob character is refused by name at render and at start; an `additional*`
  entry matching no User subject on a cluster is reported on its Namespace audit tab. `existingConfigMap`
  (`enabled`, `name`, `key`, `revision`) reads either stanza from a ConfigMap you own, mounted as a file, read at
  start, refused at render beside an inline list; after editing the ConfigMap, change `revision` in the values
  file and roll the release out. No new permission. The two platform notes on the Namespace audit tab now say
  where their list comes from. **Two `platformNamespaces` inputs render differently on upgrade:** an empty
  replacing list (`prefixes: []`, `suffixes: []`, `names: []`) now reaches the application instead of being dropped
  at render, so it replaces the shipped defaults as the values comment always said (`names: []` makes `default` and
  `openshift` ordinary namespaces; `prefixes: []` does the same to every `openshift-*` and `kube-*` one); and a
  `platformNamespaces` that is not a mapping (`false`, `""`, `[]`), which rendered as if unset, is refused at render
  by name.

```

### Block 71 — charts/group-sync-dashboard/Chart.yaml

Chart 0.60.0 and its history line (§3.10).

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
version: 0.59.25
```

New text:

```yaml
# CHART 0.60.0 (2026-10-01), MINOR: `platformUsers` (prefixes, names, additionalPrefixes, additionalNames) and
#   `existingConfigMap` {enabled, name, key, revision} for platformNamespaces and platformUsers, mounted as a
#   file, refused at render beside an inline list; an empty replacing list now renders; appVersion moves to
#   application 2.1.0 (below); #255.
version: 0.60.0
```

### Block 72 — charts/group-sync-dashboard/Chart.yaml

`appVersion` 2.1.0 and its history line.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
appVersion: "2.0.0"
```

New text:

```yaml
# 2.1.0 (2026-10-01). An estate names its own platform users in the values file or a ConfigMap, and either platform list can live in a ConfigMap; the shipped platform users gain `kube:admin` (#255). MINOR.
appVersion: "2.1.0"
```

### Block 73 — local-development/pyproject.toml

The application version.

<!-- block: local-development/pyproject.toml | edit -->

Old text:

```toml
version = "2.0.0"
```

New text:

```toml
version = "2.1.0"
```

### Block 74 — local-development/gsd/__init__.py

`__version__`, held equal by `tests/test_chart_versions.py`.

<!-- block: local-development/gsd/__init__.py | edit -->

Old text:

```python
__version__ = "2.0.0"
```

New text:

```python
__version__ = "2.1.0"
```

### Block 75 — local-development/mock-app/tests/test_request_surface.py

The mock cluster's suite read the reader's `is_platform` (§3.2); `.github/workflows/mock-cluster.yml` runs it on
every pull request that changes `gsd/kube.py`, `gsd/config.py`, `gsd/poller.py` or `gsd/store.py`. The row carries
no flag now, and the shipped defaults make `lateef.o` a person.

<!-- block: local-development/mock-app/tests/test_request_surface.py | edit -->

Old text:

```python
    assert row.role_name == "viewer"
    assert row.is_platform is False
```

New text:

```python
    assert row.role_name == "viewer"
    # #255: the reader carries no platform flag; the poller decides it from the settings' platformUsers, whose
    # shipped defaults make lateef.o a person.
    from gsd.config import PlatformUsers
    assert not hasattr(row, "is_platform")
    assert not PlatformUsers().matches(row.user_name)
```
