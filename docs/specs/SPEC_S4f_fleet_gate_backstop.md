# SPEC S4f — the fleet gate's backstop: a deleted fleet Lease is put back from a copy beside the database, so `crc start` sends no refused password again and pings no second time in a day (#481)

| | |
|---|---|
| Programme | Epic C (#383), keep the shared fleet login account safe — a follow-up to SPEC_S4c (#285), whose gate and daily ping live on the fleet account's Lease |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step C, a follow-up) |
| Version on release | app 1.18.0, chart 0.59.20 |
| Issue | [#481](https://github.com/ephico2real2/group-sync-dashboard/issues/481) |
| Status | merged |
| Source | Written by the implementer (phase 2: the spec; no production code) from #481 and its comments — the research of 2026-09-29 (phase 1) and the operator's decision of the same day — SPEC_S4c, and the research's prototype of option (c2). Measured on this machine against main `696ddc9` (application 1.17.0, chart 0.59.19) on the fleet suite's own hermetic harness (`local-development/tests/test_fleet_lifecycle.py`: a fake OAuth server that counts authorize requests, a fake API server for the Lease). The lab was read, never written, and no login was made. §6's blocks were cut from a copy of `696ddc9` with the design implemented, and applied back to a clean copy for the proof in §5. |

## How to read this spec

Each section opens with its point in one bold line. §1 is the requirement, the decision and what is out of scope. §2 is
what was measured and read, upstream and on the lab. §3 is the design. §4 is the budgets over the system, each number
measured by a test §6 adds or marked derived. §5 is the documents this changes and the proof of the blocks. §6 is the
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4f_fleet_gate_backstop.md . --apply

Line citations are plain file:line text at `696ddc9`. `path#name` citations are the maintained kind. Upstream sources
are named with the commit or version they were read at. Phase 2 writes this file, its index row, one CHANGELOG line and
the test that holds the document; it applies no block.

**Words used below.** The fleet account's **Lease** is one `coordination.k8s.io/v1` object per fleet account in the
release namespace, `gsd-fleet-<sha256(username)[:16]>` (SPEC_S4c §3.3). Its `spec` is the **claim**: which process may
send the password now. Its `refused` annotation is the **entry** (the gate): a password the directory already answered
with a failure, or an attempt whose answer was never recorded (the **reservation**, marked `uncertain`). Its five
`ping-*` annotations are the daily ping's instants. A **bind** is one password presented to the directory, counted as
one authorize request on the fake OAuth server. The **copy** is the file this spec adds, `fleet-gate.json`, beside the
database. `crc start` is starting a stopped CodeReady Containers cluster.

## Orchestrator's notes

- **Phase 2 is the spec.** No production code is applied. Versions stay where they are: the implementing PR takes the
  next free application minor at the head of the merge queue, and a chart bump, because it changes two documents under
  `charts/group-sync-dashboard/`. The CHANGELOG line phase 2 adds says "Spec only". This spec's Status, and its row in
  `docs/specs/README.md`, move to `merged` by hand in the implementing commit: a block cannot, because its Old text would
  also match inside its own fence (SPEC_S4c §3.13's rule).
- **The decision is the operator's, 2026-09-29: option (c2), plus option (a)'s warning line.** From the issue: *"The
  fleet gate gets a backstop on the dashboard's own data volume: a small JSON file beside `gsd.db`, re-read when the
  fleet Lease is absent, plus (a)'s warning line. There is no RBAC change and no migration. The Lease stays the authority
  whenever it exists, and §5 Q7's clear still re-arms the gate. Not covered, and to be stated in B2: persistence off, an
  etcd restore, a reinstall into another namespace, and a clear by hand followed by a `crc start` (an over-block, the
  safe direction)."* The research's options (b) a ConfigMap or Secret mirror and (d) an annotation on the password
  Secret were not chosen; their measurements stay on the issue.
- **A retraction from the research (its §1.3, last bullet, and its row 12).** The research said *"a PUT re-creates a
  deleted Lease"*: the Lease strategy allows create-on-update (Kubernetes v1.35.6 pkg/registry/coordination/lease/strategy.go:83-86),
  so a holder whose write lands after a deletion puts its copy back. That is wrong for every PUT this dashboard sends.
  The body of each is the object as the API server returned it, `metadata.uid` included (`_applied(record.raw, …)` at
  gsd/fleetstate.py:284 and :340). The PUT handler turns a body's uid into a precondition
  (staging/src/k8s.io/apiserver/pkg/registry/rest/update.go:188-203, read at `fc0e7a6c`, the commit of tag v1.35.6),
  which an absent object fails (§2.4), and the answer is **409**, not a create. Create-on-update serves only a body
  without a uid. The research's row 12 was measured on a fake that stamped no uid, so its "1 incl. a restart, the entry
  re-created by the PUT" was the fake's. Measured again on a fake with the API server's behaviour (`ApiServer`, §6's
  test file): today's count for that row is **2**, the same as the suite's `LeaseAPI`, which raises `KeyError` there
  instead. §4 carries the corrected row.
- **Three changes to the prototype, each found while writing this spec.**
  1. *The leader's sweep puts an absent Lease back* (`gsd/fleetstate.py#FleetLease.restore`). In the prototype only a
     claim re-created the Lease, and the daily ping stands down on a gated account **before** it claims
     (gsd/poller.py:1779-1808). So an account whose only paths are retrieved clusters — the lab's shape — kept an absent
     Lease for as long as it stayed gated, and §5 Q7's `oc annotate` had nothing to act on. With the entry clear, the
     ping is not due until its kept interval ends, so the Lease stayed absent for up to a day there too.
  2. *A reservation that cannot be kept is completed* (`gsd/fleetstate.py#FleetLease.reserve`). The research's probe on
     the prototype: when the copy's write at the reservation failed, nothing was sent (0 authorizes), but the
     reservation was already on the Lease, `{"code": "login-failed", "uncertain": true}`, and gated the account until
     §5 Q7's clear. Now `complete()` removes it first: the password was provably not sent.
  3. *The warning*, the operator's addition: one `fleet-lease-absent` line when a Lease is put back, said once (§3.7).
- **The code, measured against the prototype.** The original blocks add 113 code lines and remove 10 in
  `gsd/fleetstate.py`; the option (c2) prototype adds 60 and removes 8 (other storage variants excluded).
  The reviewed replacement adds 114 and removes 12 against the original tree: **one fewer production code line**
  than the original blocks. It removes distributed `_keep` calls and the one-use `FileBackstop.load` wrapper,
  and serializes each API response with its save in `_call`. The strict reservation still calls `complete()` on a
  failed keep. The warning, restore, shape check, atomic rename, directory flush, and failure-transition logging stay.
  Two thread-interleaving tests catch a stale read erasing a refusal or undoing an observed clear; two direct tests
  hold restore's clear handling and POST arbitration. Two per-pod-copy cases measure the replica residual, and two
  document assertions hold the proof wording and runbook. No RBAC, schema, poller, or self-login behavior is added.
- **SPEC_D6 gets a note too.** `tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds SPEC_D6's prose to
  the live count of `event` and `failure` call sites, and this change adds three, all in `gsd/fleetstate.py`: 42 → 45
  in 6 consuming modules (measured on both trees). D6's §2.3 keeps its 42, the count at `ece9298`; an orchestrator's
  note in D6 records 45.
- **Found while measuring, outside this change.** (1) The suite's `LeaseAPI`
  (`local-development/tests/test_fleet_lifecycle.py#LeaseAPI`) answers a PUT to an absent name with `KeyError`, where
  the API server answers 409. No shipped test deletes a Lease, so it is left as is; §6's test file subclasses it
  (`ApiServer`). (2) `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` carries two markdownlint findings on main
  (MD012 at its line 18, MD040 at its line 98). This change touches neither line; markdownlint runs in no CI job.

## 1. The requirement, the decision, and what is out of scope

**A password the directory refused stays refused, and the daily ping stays once a day, across a deletion of the fleet
Lease and a `crc start` — within the scope §4 states — and a Lease deleted is said, once.**

### 1.1 The requirement, in plain English

The dashboard sends the fleet account's password to a directory at most once while it is the same password (SPEC_S4c
§3.2, B2), and pings once a day (B3). Both rules are kept on the fleet account's Lease. `crc start` deletes every Lease
on the cluster and restarts every pod, so after each start the dashboard read an empty Lease, sent a refused or locked
password once more, and pinged a second time that day. Each extra bind is one more step of the lockout walk the gate
exists to stop, against the account every cluster shares. #481's Definition of Done asks for two behaviours, each held by
a test that fails before and passes after: *"a refused password stays refused after its Lease is deleted and the process
restarts; the ping stays at most once a day across the same events"*.

### 1.2 The decision (2026-09-29)

Option (c2): a backstop of the gate on the dashboard's own data volume — a small JSON file beside `gsd.db`, re-read when
the fleet Lease is absent — plus option (a)'s warning line. No RBAC change and no schema migration. The Lease stays the
authority whenever it exists, and SPEC_S4c §5 Q7's clear still re-arms the gate (the operator's words are in the
orchestrator's notes).

### 1.3 Not fixed, as the operator accepted

| what | why the copy cannot cover it | cost, per event (§4) |
|---|---|---|
| persistence off (`persistence.enabled: false`) | the copy lives on the pod's `emptyDir`, and a new pod starts without it | +1 bind per refused password, +1 ping |
| two replicas with independent copies | a winning replica can restore a stale copy before it has observed the other replica's refusal or ping | +1 bind or +1 ping in the measured interleaving (§3.9) |
| an etcd restore to a time before the refusal | the restored Lease exists, so it is read and the copy is not; the copy is then overwritten from it | +1 (derived) |
| a reinstall into another namespace | a new release has a new data volume and no copy | +1 (derived) |
| a clear by hand made while no pod read the Lease, then a `crc start` | the copy still holds the entry and puts it back: the clear is undone — an over-block, the safe direction | 0, until the runbook's second clear (+1) |
| a database in memory (`:memory:`, tests and local runs) | no file to keep the copy beside | +1 |
| the Lease deleted AND the data volume replaced | both copies gone | +1 (derived) |
| Rejoin's gate (a person's typed password, SPEC_D4) | its gate is the process's alone by design (SPEC_D4, D4-7); no fleet Lease is involved | unchanged |
| crc's own behaviour | crc deletes every Lease on each cold start, with no switch (§2.1) | — |

## 2. What was measured and read

**`crc start` deletes every Lease on the cluster, on purpose and with no switch; nothing in Kubernetes does it
otherwise; on the lab it cost a second fleet bind and a second ping on 2026-09-28; and B2's premise does not hold.**

### 2.1 Who deletes the fleet Lease

- crc-org/crc `v2.63.0` (`3a67a3687c`, the lab's `CRC version: 2.63.0+3a67a3`), pkg/crc/cluster/cluster.go:495-509,
  `DeleteMCOLeaderLease`: after one named ConfigMap, `ocConfig.RunOcCommand("delete", "-A", "lease", "--all")` (line
  509) under the comment `// https://issues.redhat.com/browse/OCPBUGS-7583 as workaround` (line 505). It is called on
  every cold start from pkg/crc/machine/start.go:584, inside `(client *client) Start` with no condition around it. Only
  a VM already running (start.go:363-371) and the MicroShift preset (start.go:550) skip it.
- Since crc **2.29.0**. GitHub blame of cluster.go at `3a67a36` gives line 509 to `9354dd4c18a1`, "Cluster: Remove all
  the lease from cluster" (committed 2023-11-07); `compare` puts that commit after v2.28.0 and before v2.29.0. v2.28.0's
  cluster.go:507 deleted the Leases of one namespace only; v2.14.0 deleted none. crc `main` (`0aaea852`, 2026-09-28)
  still has it at cluster.go:509, called from start.go:585. The commit message says why: from OpenShift 4.14 the one
  namespace's delete no longer shortened the start, *"so I am removing all the lease from older cluster"*.
- No switch. Every one of the 269 Go files under `pkg/` and `cmd/` at `3a67a36` was grepped for "lease": the only
  Kubernetes-Lease lines are cluster.go:495, 506, 509 and start.go:584, and no configuration key names a Lease. crc runs
  each `oc` call under a 30-second timeout (pkg/crc/oc/oc.go:12).
- **OCPBUGS-7583** (Jira REST, 2026-09-29): *"MCO takes the lease ownership (~5 mins) after API server is up"*, **Closed,
  Not a Bug**, resolved 2023-03-07. The Jira's own workaround is **one named Lease**:
  `oc delete lease machine-config-controller -n openshift-machine-config-operator`. The delete-every-Lease form is crc's
  own widening (`9354dd4c`), not the Jira's. #481's first wording, which called `oc delete lease --all -A` "the
  workaround for OCPBUGS-7583", is corrected here as the research corrected it on the issue.
- Nothing else deletes it. Kubernetes v1.35.6 (`fc0e7a6c`), read as source: the API server's lease garbage collector
  deletes expired identity Leases in `kube-system` only (pkg/controlplane/controller/apiserverleasegc/gc_controller.go:129);
  a lease controller deletes only its own Lease
  (staging/src/k8s.io/component-helpers/apimachinery/lease/controller.go:114, 137); a Lease has no time to live
  (staging/src/k8s.io/api/coordination/v1/types.go:59-61); the fleet Lease carries no `ownerReferences` for the garbage
  collector to follow (the lab answers `ownerReferences=0 finalizers=0`). It goes when someone deletes it by name,
  deletes the Leases of its namespace, deletes the namespace, or copies crc's `-A --all`. An etcd restore rolls it back
  instead (openshift/openshift-docs `72cab1f9`, modules/dr-restoring-cluster-state-about.adoc:27).

### 2.2 The lab, read-only

`KUBECONFIG` = the lab's read-only kubeconfig (OpenShift 4.22.7, Kubernetes v1.35.6), 2026-09-29T04:07:34Z, `get`,
`list`, `logs` and `auth can-i` only. The fleet account's name is not printed.

- **58 of 58 Leases postdate the start.** `oc get leases.coordination.k8s.io -A`: 58 Leases, **0** created before
  2026-09-28T17:55:17Z. The earliest is `kube-node-lease/crc` at 17:55:17Z; the latest the fleet Lease
  `gsd-fleet-666f1ba7f2fdead0` at 17:57:01Z.
- **What survived.** In `group-sync-dashboard`: ConfigMaps 11 of 11, Secrets 33 of 34 (the 34th is a later redeploy's
  pull Secret), PersistentVolumeClaims 2 of 2 predate the start; Leases 0 of 3. In `openshift-config`: ConfigMaps 14 of
  14, Secrets 10 of 10. The pods were restarted in place: the same pod objects, new processes.
- **The data volume.** `group-sync-dashboard-data`, ReadWriteMany, mounted at `/data`; the Deployment runs one replica,
  `Recreate`, with `GSD_DB_PATH=/data/gsd.db`. The chart renders the same shape by default
  (charts/group-sync-dashboard/values.yaml:925-926, `persistence.enabled: true`;
  charts/group-sync-dashboard/templates/deployment.yaml:164-177 and 471-478).
- **What it cost on 2026-09-28** (the issue's log lines; that pod was replaced by a redeploy at 2026-09-29T01:40:34Z,
  so they are cited, not re-read): the fleet Lease's old copy held the 10:30:01Z ping; after the start the dashboard
  logged `fleet-login cluster=shared-rnd` at 17:57:02Z and `fleet-ping … last_ok=2026-09-28T17:57:01Z`. The Lease now
  reads `ping-last-attempt` 17:57:01Z, 7 h 27 min after the 10:30:01Z ping: **two pings inside one 86 400 s interval**.
  The password was good, so the extra bind was harmless; a refused one would have been sent again the same way.
- **RBAC today.** `oc auth can-i --list` as the dashboard's ServiceAccount, in its namespace: `leases get create update`;
  `secrets get list watch create update delete` (writes are on in the lab's values); `configmaps get list watch`. The
  live grants equal the chart's render of `696ddc9` with `environments/crc.yaml`, 49 atoms each. The copy needs none of
  them: it is a file on the pod's own volume.

### 2.3 B2's premise, refined

SPEC_S4c §3.2's B2 prices a deleted Lease as *"+1 per act, an operator's act by a principal that can already read the
password Secret"*. Neither half holds in general. `crc start` deletes it with no operator deciding (§2.1). And the stock
`admin` and `edit` ClusterRoles hold `delete` on Leases, while a RoleBinding grants only inside its own namespace: with
the password Secret in `openshift-config`, as on the lab, a team given `admin` on the release namespace can delete the
fleet Lease without being able to read the password. On the lab every RoleBinding subject in the namespace is a
ServiceAccount, so OB2's measurement held there, and only there.

### 2.4 What the API server does with a write after a deletion

Read at Kubernetes `fc0e7a6c` (tag v1.35.6), because the design depends on it:

| step | source | what it does |
|---|---|---|
| the PUT handler | staging/src/k8s.io/apiserver/pkg/endpoints/handlers/update.go:208-211 | calls `Update` with `rest.DefaultUpdatedObjectInfo(obj)` |
| the precondition | staging/src/k8s.io/apiserver/pkg/registry/rest/update.go:188-203 | a body carrying `metadata.uid` is a UID precondition |
| the store | staging/src/k8s.io/apiserver/pkg/registry/generic/registry/store.go:630-641 | passes it to `GuaranteedUpdate`, ignoring not-found because the Lease strategy allows create-on-update |
| an absent key | staging/src/k8s.io/apiserver/pkg/storage/etcd3/store.go:1014-1020, 501-505, 608-616 | the current object is the zero value; the precondition is checked against it — also after a failed transaction re-reads a stale cached object |
| the check | staging/src/k8s.io/apiserver/pkg/storage/interfaces.go:150-155 | the uid differs from the zero value's empty one: `InvalidObjError` |
| the answer | registry/store.go:800-805, then staging/src/k8s.io/apiserver/pkg/storage/errors/storage.go:78-81 | not creating, so `InterpretUpdateError`: an invalid object is a **409 Conflict** |
| create-on-update | pkg/registry/coordination/lease/strategy.go:83-86; registry/store.go:646-712 | reached only by a body with no uid |

So a Lease deleted from under a claim is never re-created by its holder's PUT (`FleetLease._put` meets the 409,
re-reads a 404 and raises `was deleted under a claim`, gsd/fleetstate.py:352-353). A create is a POST, which
`claim()` sends for a record it read as absent (gsd/fleetstate.py:266), and which the API server admits once: a second
POST of the same name answers 409 `AlreadyExists`, which `claim()` turns into `ClaimHeld`.

### 2.5 The bind counts today

Measured on this spec's own tests (§6) run against `696ddc9` with only the test file added; the fake API server models
§2.4. One wrong (401) or locked (500) password on one account; each `crc start` deletes every Lease and builds new
processes over the same fake API server.

- **Every `crc start` costs +1 bind** for a refused, locked or `uncertain` password, on every path — the lookup, the
  daily ping and self-login: `[1, 0, 1, 1]` for first answer, a restart, two starts, in all six path-and-answer cases.
- **Every `crc start` costs +1 ping** with a valid password, and so does a live deletion at the next cadence:
  `[1, 0, 1, 1, 1, 1]` (first ping, a restart, two starts, a live deletion, a day later).
- A live deletion costs **+0 while the pod runs and +1 at its next ordinary restart**: the process's own gate refused,
  but the Lease it re-created carried no entry (`[1, 0, 1]`).
- A deletion while an attempt is on the wire lets a **second path of the same process** bind: 2 in all.

## 3. The design

**Every fleet Lease this process reads or writes is also kept, entry and ping instants only, in one file beside the
database; an absent Lease reads as that copy and is created again from it; the Lease stays the authority whenever it
exists; and whatever cannot be known binds nothing.**

```text
FleetLease.read()
  GET the Lease ──200──▶ the Lease is the authority ──▶ keep its entry and ping instants in the copy
        │
       404
        ▼
  the copy has it? ──no──▶ an empty record (a first install, as before)
        │           ──unreadable──▶ FleetStateUnavailable: nothing binds
       yes
        ▼
  a record AS KEPT: the same gate, the same ping instants, no holder
        ▼
  the next claim POSTs the Lease WITH them (the API server admits one create)
  ── said once: fleet-lease-absent kept=true
```

### 3.1 Where the copy lives

`<the database's directory>/fleet-gate.json`: `/data/fleet-gate.json` at one replica, `/data/<pod>/fleet-gate.json`
above one (the database path the chart renders, charts/group-sync-dashboard/templates/deployment.yaml:164-177). The
poller derives it once, from the store's own path (`gsd/poller.py#Poller`), and hands the one `FileBackstop` to every
Lease it builds, through one factory (`gsd/poller.py#Poller._fleet_lease`) that the lookup, the ping and self-login all
use. A store in memory, or one with no file path, keeps no copy.

The data volume's object outlived the `crc start` on the lab (§2.2); its content was read only indirectly: the
redeployed pod's first backup line said `(4 kept)`, which is `min(files present, backupKeep)` (gsd/store.py:1758-1765),
so at least three older backups were on the volume. The copy is not the database: no backup copies it (the offsite job
ships only the backup files, charts/group-sync-dashboard/templates/backup-offsite.yaml:33), nor does a report
snapshot, and it needs no schema migration. `.gitignore` ignores it beside `*.db`.

### 3.2 Its format

One JSON object. Its keys are Lease names; each value maps the Lease's kept annotations, by their full names, to their
values **exactly as the Lease holds them** — so `refused` is itself a JSON string. Only annotations the Lease carries are
kept, and only these six (`gsd/fleetstate.py#KEPT`): `refused`, `ping-last-attempt`, `ping-last-ok`,
`ping-last-outcome`, `ping-last-target`, `ping-digest`. Never the claim (`spec`), which must not outlive the Lease, and
never the account annotation, which the next claim writes again. Written with sorted keys.

```json
{"gsd-fleet-666f1ba7f2fdead0": {"groupsync-dashboard.io/ping-digest": "<16 hex>",
  "groupsync-dashboard.io/ping-last-attempt": "2026-09-28T17:57:01Z", "groupsync-dashboard.io/ping-last-ok": "2026-09-28T17:57:01Z",
  "groupsync-dashboard.io/ping-last-outcome": "ok", "groupsync-dashboard.io/ping-last-target": "shared-rnd",
  "groupsync-dashboard.io/refused": "{\"at\": \"…\", \"code\": \"login-refused\", \"digest\": \"<16 hex>\", \"target\": \"…\"}"}}
```

Why byte for byte: after a 409, `FleetLease._put` touches the entry only while the Lease still holds, byte for byte,
the value its write was decided on (SPEC_S4c round 2, C5 and F1). A Lease created again from the copy carries the same
bytes, so an attempt still in flight across the deletion still recognises its own reservation. The digests are the
Lease's own scrypt fingerprints, salted with the password Secret's uid (SPEC_S4c round 1, D2): the copy is no oracle
that the Lease, readable by `cluster-reader`, is not already.

### 3.3 When it is written, and how

**When.** After every successful read of a present Lease and every successful write — `claim()`, `reserve()`, and the
writes of `complete()`, `refuse()` and `release()` (`FleetLease._put`) — the Lease's six kept annotations are compared
with the copy, and the file is written only when they differ (`gsd/fleetstate.py#FleetLease._keep`). So it is written
at a reservation, an answer, a completion, the ping's claim (its attempt, target and digest), the ping's release (its ok
instant and outcome), and whenever a read sees another writer's change — a hand-clear, another replica. The account
sweep reads every account's Lease each discovery cadence (gsd/poller.py:1750-1757; 300 s by default), so the copy
follows a hand-clear within one cadence, and a sweep that changes nothing writes nothing.

**How.** To `fleet-gate.json.tmp` beside it; flushed and `fsync`ed; renamed over the file with `os.replace`; then the
directory `fsync`ed — the order `gsd/store.py#_pre_upgrade_copy` already uses (gsd/store.py:1262-1267), so a reader sees
the old file or the new one, never half of one, and a host crash followed by `crc start` finds the rename. One reentrant
lock per process (`gsd/fleetstate.py#FileBackstop`) covers the API request, response, and save together in
`FleetLease._call`, across discovery and self-login threads. An older response therefore cannot overwrite a newer saved
reservation, refusal, ping, or observed clear. A 404 reads the atomically renamed file directly. One process writes it:
one replica with `Recreate`, or one directory per pod above one (whose stale-copy residual is in §3.9).

### 3.4 When it is read

Only when the Lease is absent: `FleetLease.read()` on a 404 (`gsd/fleetstate.py#FleetLease.read`). A present Lease is
never compared with the copy — it wins, and the copy is overwritten from it on that read. An absent Lease with a copy
reads as a record with the kept annotations, no holder and no resourceVersion: the gate (`gated()`), the view the tab
and `/metrics` serve, the ping's due-ness and `reservation_pending` all see what was kept. An absent Lease with no copy
is an empty record, as today: a first install.

### 3.5 How an absent Lease is created again

By the next claim, with the claim's compare-and-swap unchanged. `claim()` on a record read as absent sends a POST, as
for a first install, carrying the kept annotations with the account and the claim's own changes. The API server admits
one create: a second process's POST answers 409 `AlreadyExists`, which is `ClaimHeld` (§2.4). No write path is added,
and no PUT is ever sent to an absent name.

On the leader, the account sweep also puts an absent Lease back at once (`gsd/fleetstate.py#FleetLease.restore`: a
claim and its release) when the copy holds it, or when nothing was kept but the account is one the configuration
declares and clusters were retrieved as it. Without that, a gated account whose only paths are retrieved clusters — the
ping stands down before it claims (gsd/poller.py:1779-1808) — would keep an absent Lease, and §5 Q7's clear would have
nothing to clear. A standby writes nothing, as today (SPEC_S4c §3.4): it serves the kept view. The sweep reads only the
accounts in use (SPEC_S4c §3.4), so a retired account's Lease, deleted, stays deleted; its entry stays in the copy, which
nothing prunes, and is read only if that account comes back while its Lease is absent — an over-block, the safe
direction, cleared as §3.8 says.

### 3.6 Fail closed

| what fails | what happens |
|---|---|
| the Lease is absent and the copy cannot be read (a permission, not JSON, not a map of Lease names to string annotations) | `FleetStateUnavailable`: no path binds, and no Lease is created over a gate nobody can read. The finding is `fleet-state-unavailable`, with the copy's path and what to do |
| the copy cannot be written at the reservation | `reserve()` removes the reservation from the Lease again (`complete()`: the password was provably not sent) and raises `FleetStateUnavailable`: no bind, and no `uncertain` entry is stranded — the research prototype's defect |
| the copy cannot be written anywhere else (a claim, a read, an answer, a completion, a release) | not a stop — the Lease still holds the state, and the next reservation fails closed anyway: one `fleet-state-unavailable` line when the copy starts failing, said again only once a write of the copy has succeeded in between |

The copy's `action=` says what to do: *"the data volume must hold a readable, writable <path>; nothing binds until it
does. Moving an unreadable copy aside is safe only while every fleet Lease exists (oc get leases.coordination.k8s.io -l
groupsync-dashboard.io/lease-type=fleet-account)"*.

### 3.7 The warning

One event, `fleet-lease-absent`, at WARNING, in two forms. Each is said once per absence, with no memory kept: only one
create is admitted, and after it the Lease is present again.

| form | said by, and when |
|---|---|
| `kept=true` | the process whose create put the Lease back from its copy — whichever path made it: a lookup, the ping, self-login or the sweep (`gsd/fleetstate.py#FleetLease.claim`). `refused`, `since` and `last_attempt` appear only when the copy holds them |
| `kept=false` | the leader's sweep (`gsd/fleetstate.py#FleetLease.restore`), when an account the configuration declares, with clusters retrieved as it, has no Lease and nothing kept; it then creates the Lease empty |

The lines, word for word (`gsd/fleetstate.py#RESTORED`, `gsd/fleetstate.py#NOTHING_KEPT`):

```text
fleet-lease-absent account=<account> lease=<name> kept=true refused=<code> since=<entry's at> last_attempt=<the ping's> action="the Lease was deleted — by hand, or by `crc start`, which deletes every Lease on the cluster — and is put back from the copy kept beside the database, as this dashboard last read it; if an entry was removed by hand while no pod read the Lease, it is back: remove it again and restart the pod"
fleet-lease-absent account=<account> lease=<name> kept=false action="the Lease was absent and nothing was kept beside the database (persistence off, or a new volume), or it was never created (clusters retrieved before #285): a password its gate held back may be sent once more; it is created empty"
```

What it cannot see, stated: an account with only self-login or pending clusters and no copy leaves no trace, so nothing
is said there. And when a pending lookup or a self-login acquisition creates an empty Lease before the sweep runs, their
own lines are what is said.

**No new finding code.** A finding is a standing condition held in a registry slot until its owner's next success; a
deletion is an event. The state it can leave — a gated entry — is already served as findings by the paths that meet it,
each naming §5 Q7's clear: the ping's stand-down, the lookup's gated refusal, `self-login-suspended`. A new code would
join the closed `FINDING_CODES` set and need an owner to clear it, and it would sit on the tab after every `crc start`
asking for nothing. The copy's own failures use the existing `fleet-state-unavailable`.

### 3.8 §5 Q7 still re-arms the gate, and the runbook's new step

SPEC_S4c §5 Q7's clear is unchanged: remove the `refused` annotation from the Lease, then restart the dashboard pod,
which keeps its own copy of the refusal until it restarts. The copy does not change that: while the Lease exists it is
the authority, and the running pod's sweep carries the clear into the copy within one cadence. Deleting the Lease no
longer clears the gate; clearing the entry does. The one ordering the copy changes: the entry cleared while no pod read
the Lease, then a `crc start`. The copy still holds the entry and puts it back (`kept=true refused=<code>`) — an
over-block, the safe direction — and the runbook's step is to wait for the Lease, clear the entry again, and restart
the pod. `charts/group-sync-dashboard/RUNBOOK.md` gains that procedure as its section 7, the runbook Q7 asked for:
until now the procedure was only in SPEC_S4c.

### 3.9 Above one replica, and with persistence off

- **Above one replica** (election off, `/data/$(POD_NAME)/gsd.db`), each pod keeps its own copy. The lookup and
  self-login do not run there (gsd/poller.py:1622-1638 refuses the lookup without an elector above one replica;
  self-login is refused at render, charts/group-sync-dashboard/templates/_helpers.tpl:1047-1048, and at run time,
  gsd/selflogin.py:118-123); only the ping does. **A stale per-pod copy can allow +1 bind or +1 ping after a Lease deletion**:
  pod B can keep an empty Lease, pod A can then record a refusal or ping, and `crc start` can delete the Lease before B's
  next read. B's create wins legitimately, with its older copy. The API server still admits just one create; that does
  not make the winning copy current. Reproduced with two independent pod directories by
  `test_independent_pod_copy_can_miss_a_refusal_before_crc` (two answer variants: refusal and success).
  Therefore the +0 guarantee below is for **one replica**, with its data volume kept. Above one replica, a copy protects
  only the state that pod has observed; deployment-wide +0 is not guaranteed, even for pods restarted in place.
  A replaced pod also gets a new name and directory, so it has no copy (derived from the chart).
- **With persistence off**, `/data` is an `emptyDir` (charts/group-sync-dashboard/templates/deployment.yaml:476-477):
  the copy lives as long as the pod object. A new pod starts without it and says `kept=false` for an account with
  retrieved clusters. Measured by modelling the copy as lost (§4). Not measured: whether a node reboot keeps a
  disk-backed `emptyDir` for a pod restarted in place.

## 4. The budgets over the system

**Every row is one wrong (401) or locked (500) password, or one valid password for the ping, on one account; "before"
is `696ddc9` with only §6's test file added, "after" is every block applied; each count is authorize requests on the
fake OAuth server, and each row names the test that measures it, or says derived.**

The scopes. SPEC_S4c's B1 (the claim), B4 and B5 are unchanged. B2 and B3 were scoped "across every target, replica and
restart" and hold on the Lease; this spec extends the scope to a **deletion of the Lease**, with the data volume kept,
on one replica with its data volume kept. Per-pod copies above one replica may be stale (§3.9);
deployment-wide +0 is not guaranteed there.

### 4.1 B2 — at most one answered failed authorize per (account, password)

| shape | before | after | measured by (`local-development/tests/test_fleet_gate_backstop.py`) |
|---|---|---|---|
| one target; T targets on one account; a restart; two replicas; a crash after the authorize GET | 1, 1, +0, +0, +0 | unchanged | SPEC_S4c §8.2; its tests pass on the applied tree (§5.2) |
| **a `crc start`, then a second one** — lookup, ping, self-login; 401 and 500 | +1, +1 | **+0, +0** | `test_a_refused_password_stays_refused_across_crc_starts[401-lookup]` and the five other cases |
| an `uncertain` reservation (a crash after the authorize GET), then a `crc start` | +1 | **+0** | `test_an_uncertain_reservation_survives_a_crc_start` |
| the Lease deleted on a running cluster, then an ordinary restart | +0, then +1 | **+0, then +0** | `test_a_live_deletion_then_an_ordinary_restart_binds_nothing` |
| the Lease deleted while an attempt is on the wire, a second path of the same process running | 2 in all | **1 in all** | `test_a_deletion_while_an_attempt_is_on_the_wire_admits_no_second_bind` |
| the refusal written after a live deletion, then a restart (the research's row 12, corrected) | 2 in all | **1 in all** | `test_a_refusal_written_after_a_live_deletion_is_not_lost` |
| §5 Q7: the entry removed by hand, the pod restarted | +1, the re-arm | +1 | `test_q7s_clear_still_rearms_the_gate` |
| §5 Q7's clear read by the running pod, then a `crc start` | +1 | +1 | `test_a_clear_the_running_pod_has_read_survives_a_crc_start` |
| §5 Q7's clear made while no pod read the Lease, then a `crc start` | +1: the clear stands (3 and 2 authorizes in all; the lookup variant's third is the day's first ping) | **0**, an over-block said once; +1 after the runbook's second clear | `test_a_clear_by_hand_then_a_crc_start_before_any_read_is_undone_and_said[lookup]`, `[ping]` |
| the Lease present, its copy stale (an entry the Lease no longer holds) | +1 | +1: the Lease decides, and the copy follows it | `test_the_lease_stays_the_authority_whenever_it_exists` |
| two sequential process instances sharing one kept copy after a `crc start` | 2 | **1**, and one line | `test_the_restore_is_said_once_by_the_process_that_creates_it` |
| the Lease absent and its copy unreadable | 1 (no copy exists) | **0**, fail closed, no Lease written | `test_an_unreadable_copy_behind_an_absent_lease_binds_nothing` |
| the copy unwritable at the reservation | 1 | **0**, fail closed, no entry stranded, one line in three cycles | `test_a_copy_that_cannot_be_written_at_the_reservation_binds_nothing_and_strands_no_entry` |
| a first install (no Lease, nothing kept) | 1 | 1, nothing said | `test_a_first_install_binds_once_and_says_nothing` |
| persistence off, then a `crc start` | +1 | +1 — not fixed | `test_persistence_off_is_the_row_not_fixed[lookup]`, `[self-login]` |
| a database in memory, then a `crc start` | +1 | +1 — not fixed | `test_a_database_in_memory_keeps_no_copy` |
| an etcd restore to before the refusal | +1 | +1 — not fixed | derived: the restored Lease exists and is read first (§3.4) |
| a reinstall into another namespace | +1 | +1 — not fixed | derived: a new volume holds no copy |
| the password rotated; the password Secret deleted and recreated (a new uid) | +1; +1 | unchanged | SPEC_S4c §8.2 |

### 4.2 B3 — at most one ping bind per (account, password) per `fleetPingIntervalSeconds`

A valid password and three retrieved clusters, measured in one run by
`test_the_ping_stays_once_a_day_across_crc_starts_and_a_live_deletion`: before `[1, 0, 1, 1, 1, 1]`, after
`[1, 0, 0, 0, 0, 1]`.

| shape | before | after | measured by |
|---|---|---|---|
| the first ping, over two cadences | 1 | 1 | `test_the_ping_stays_once_a_day_across_crc_starts_and_a_live_deletion` |
| a restart inside the interval | +0 | +0 | the same |
| **a `crc start`; a second one the same day** | +1; +1 | **+0; +0** | the same |
| the Lease deleted on a running cluster, the next cadence | +1 | **+0** | the same |
| a day later | +1 | +1, to the next target by name (the kept rotation) | the same |
| persistence off, then a `crc start` | +1 | +1 — not fixed, said once (`kept=false`) | `test_nothing_kept_is_said_once_and_the_ping_binds_again` |
| a standby's view after a `crc start` | `last_ok` null until the leader's next ping | the kept instant; the standby writes nothing | `test_a_standbys_view_after_a_crc_start_is_the_kept_copy_and_it_writes_nothing` |

### 4.3 What the copy does not change

The claim and its compare-and-swap (B1): the create is a POST the API server admits once, as for a first install.
`FleetStateUnavailable` still fails closed, and now also for an absent Lease whose copy cannot be read. The Lease is the
authority whenever it exists. §5 Q7's clear still re-arms. The dashboard ServiceAccount's permissions: no template
changes, and the chart's whole render is byte-identical before and after (§5.2, point 5), so the rendered RBAC is
ADDED 0, REMOVED 0. #293's success mark stays off the Lease and off the copy. No fleet login in any test.

## 5. The documents, and the proof

**Four documents move and SPEC_D6 gains a note. The original 28-test proof has 22 assertion failures and 6 passing
controls on `696ddc9`, and 28 passes with the blocks. The six controls cover behavior that must remain unchanged;
there is no claim that all 28 fail before implementation. The chart renders the same.**

### 5.1 The documents

| document | change |
|---|---|
| `docs/specs/SPEC_S4c_credential_lifecycle.md` | an orchestrator's note pointing here: B2's "+1 per act" for a deleted Lease is superseded, and why. The body stays verbatim |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | the paragraph on the Lease (its lines 41-45) gains the copy, `crc start`, and where the clear is |
| `charts/group-sync-dashboard/RUNBOOK.md` | section 7: clear the fleet account's entry by hand (§5 Q7), and the step after a `crc start` |
| `docs/specs/SPEC_D6_scrub_span.md` | an orchestrator's note: 45 emit call sites once this is applied (orchestrator's notes above) |
| `docs/CHANGELOG.md` | the implementation's bullet under `## Unreleased` |
| `.gitignore` | `fleet-gate.json*` beside `*.db` |
| `local-development/tests/test_cluster_rejoin.py` | the runbook's section pin moves from six to seven |

Read and left unchanged, each still true: `docs/CLUSTER_STANZA.md`'s and `docs/polling-and-discovery.md`'s sentences on
the Lease (a restart, a crash or another replica still sends nothing again); `local-development/API.md`'s `fleet`
block (still the Lease's state — while the Lease is absent, as last kept); the chart README's ping row and its
conditional-rules paragraph (the only objects the dashboard writes on a cluster are still two Leases);
`docs/DESIGN_cluster_connection_flows.md`'s ping lines.

### 5.2 The proof

All of it run on this machine from `local-development/`, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests`, pytest
`-p no:cacheprovider`, `gsd` imported from the copy under test (printed). The copies are exports of the tree, without
`.git`, because `apply-spec-blocks.py` refuses a git tree with uncommitted changes.

1. **The blocks apply.** On a copy of the phase-2 tree (`696ddc9` with this spec, its index row, its CHANGELOG line and
   its tests): `python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4f_fleet_gate_backstop.md <copy>
   --apply` printed `28 blocks check out across 11 files` for the original blocks. The ten files the blocks change besides the CHANGELOG are
   byte-identical (`cmp`) to the copy every measurement here was taken on; the CHANGELOG differs from it only by phase
   2's own line, which the implementation's line sits above.
2. **The original regression tests fail before and pass after.** The original `tests/test_fleet_gate_backstop.py`
   had 28 cases; the following is the original proof, before the eight review cases were added. With the three code
   files put back to `696ddc9`'s bytes and every other block applied: **22 failed, 6 passed** — every failure an
   `AssertionError` carrying the count it met (the "before" column of §4), none at import. The six that pass on both
   trees are the rows this change must leave as they are: §5 Q7's re-arm, a clear the running pod has read, persistence
   off (two), a first install, and a database in memory. With every original block applied: **28 passed**. The eight added review cases give **6 failed, 2 passed** against
   the original applied copy and **8 passed** after the code and document fixes; the full revised file has **36 passes**.
   The two concurrency failures assert real bind counts. Two replica cases assert the measured +1 residual and its
   explicit scope in §3.9; two document cases require the corrected proof wording and runbook.
3. **Each design decision, reverted, is caught.** Eighteen mutants of the applied copy, one text replacement each, run
   against the new file and seven shipped fleet test files: **17 of 18 caught**. The one not caught is the directory
   flush after the rename, which only a host crash between the rename and the journal's commit would show.
4. **Original implementer proof (before review fixes).** On the original applied copy, after the by-hand status move the implementing commit makes: the new
   file, this spec's document test, the fleet files (`test_fleet_lifecycle.py`, `…_round3.py`, `test_fleet_lookup.py`,
   `test_fleet_login.py`, `test_ping_account_scope.py`, `test_credential_gate_account.py`,
   `test_credential_gate_diagnostics.py`, `test_configmap_onboarding.py`, `test_s4c_step6_walk.py`), the Rejoin file
   (the runbook's pin) and the document tests (`test_scrub_span_spec.py`, `test_docs_citations.py`,
   `test_specs_index.py`, `test_credential_gate_docs.py`, `test_docs_diagrams.py`): **2317 passed, 20 skipped,
   5 xfailed**. The whole hermetic suite with the browser tests, `pytest -p no:cacheprovider tests/ --deselect
   tests/test_live_smoke.py --browser chromium`: **6625 passed, 3 failed, 24 skipped, 4 deselected, 5 xfailed** in
   506 s. The three failures run `git` — `test_tree_hygiene.py::test_no_tracked_file_carries_a_conflict_marker`,
   `test_migration_needs_app_release.py::test_this_repository_released_its_highest_migration`, and
   `test_build_and_push_report.py::test_the_wrapper_builds_the_report_recipe_under_the_report_name`, whose wrapper
   calls `git rev-parse` — and the copy is an export without `.git`. They fail the same way on an export of `696ddc9`
   without this change, and pass in the git worktree.
5. **The chart renders the same.** `helm template` (v4.3.0) of `696ddc9`'s chart and the applied copy's, with the
   default values and with `environments/crc.yaml`: both renders byte-identical, so the rendered RBAC is ADDED 0,
   REMOVED 0.

## 6. Implementation blocks

**27 blocks, in apply order.** These replace the original §6 in full. They contain the original behavior plus the
review fixes and eight regression checks, cut against the unchanged phase-2 head. No production code is applied by
this spec-only change; Status and the index row still move to `merged` in the implementing commit.

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
`release()` lets the claim go — so the ping's due-ness is decided on the read its claim writes against, and
nothing here is shared between threads.
"""

```

```python
`release()` lets the claim go — so the ping's due-ness is decided on the read its claim writes against, and
nothing here is shared between threads.

THE COPY BESIDE THE DATABASE (#481, SPEC_S4f). `crc start` deletes every Lease on the cluster (crc-org/crc
pkg/crc/cluster/cluster.go:509, `oc delete -A lease --all`, since crc 2.29.0), and a person can delete one by hand.
An absent Lease read as empty would send a refused password again, and ping twice in a day. So every Lease this
process reads or writes is also kept, gate and ping instants only, in one file on the data volume (`FileBackstop`),
and an absent Lease reads as that copy and is re-created from it by the next claim. The Lease stays the authority
whenever it exists: the copy is read only on a 404, and overwritten from the Lease on every read.
"""

```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python

import copy
import hashlib
import hmac
```

```python

import copy
import dataclasses
import hashlib
import hmac
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
import os
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import failure
from .fleetlogin import RETRY_POLICY
from .kube import ClusterClient, ClusterError
```

```python
import os
import socket
import threading
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import event, failure
from .fleetlogin import RETRY_POLICY
from .kube import ClusterClient, ClusterError
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
GRANT = ("grant get/create/update on coordination.k8s.io/leases in this namespace to the dashboard's "
         "ServiceAccount — the chart renders it under leaderElection.enabled or a fleet account in use")

_DIGESTS: dict[tuple[str, str, str], str] = {}
```

```python
GRANT = ("grant get/create/update on coordination.k8s.io/leases in this namespace to the dashboard's "
         "ServiceAccount — the chart renders it under leaderElection.enabled or a fleet account in use")
#: The file beside the database that keeps every fleet Lease's gate and ping instants (#481).
GATE_FILE = "fleet-gate.json"
#: What that file keeps of a Lease, annotation by annotation, each value exactly as the Lease holds it: the gate and
#: the ping's bookkeeping. Never the claim, which must not outlive the Lease, nor the account, which a claim rewrites.
KEPT = tuple(PREFIX + key for key in ("refused", "ping-last-attempt", "ping-last-ok", "ping-last-outcome",
                                      "ping-last-target", "ping-digest"))
#: What an absent Lease's line says when it is put back from that copy.
RESTORED = ("the Lease was deleted — by hand, or by `crc start`, which deletes every Lease on the cluster — and is put "
            "back from the copy kept beside the database, as this dashboard last read it; if an entry was removed by "
            "hand while no pod read the Lease, it is back: remove it again and restart the pod")
#: …and when nothing was kept to put back.
NOTHING_KEPT = ("the Lease was absent and nothing was kept beside the database (persistence off, or a new volume), or "
                "it was never created (clusters retrieved before #285): a password its gate held back may be sent once "
                "more; it is created empty")

_DIGESTS: dict[tuple[str, str, str], str] = {}
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
    ping_digest: str | None                # the password the last ATTEMPT was for (B3)
    raw: dict | None = field(default=None, repr=False, compare=False)

    def gated(self, digest: str) -> dict | None:
```

```python
    ping_digest: str | None                # the password the last ATTEMPT was for (B3)
    raw: dict | None = field(default=None, repr=False, compare=False)
    #: An ABSENT Lease's annotations as the copy beside the database kept them (#481): what the next claim re-creates.
    seed: dict | None = field(default=None, repr=False, compare=False)

    def gated(self, digest: str) -> dict | None:
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python


class FleetLease:
    """One attempt's handle on an account's Lease, through the host cluster's client: the pod's own
```

```python


def _absent(account: str, kept: dict) -> FleetRecord:
    """An absent Lease this dashboard kept (#481) reads as it was kept, not as empty; unheld, since no claim is kept."""
    return dataclasses.replace(_record(account, {"metadata": {"annotations": dict(kept)}}), raw=None, seed=dict(kept))


class FleetLease:
    """One attempt's handle on an account's Lease, through the host cluster's client: the pod's own
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python

    def __init__(self, host: ClusterClient, namespace: str, account: str, *, claim_seconds: int,
                 identity: str | None = None, clock: Callable[[], datetime] | None = None):
        self.host, self.namespace, self.account = host, namespace, account
        self.name = lease_name(account)
```

```python

    def __init__(self, host: ClusterClient, namespace: str, account: str, *, claim_seconds: int,
                 identity: str | None = None, clock: Callable[[], datetime] | None = None,
                 backstop: FileBackstop | None = None):
        self.host, self.namespace, self.account = host, namespace, account
        self.name = lease_name(account)
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
        self.claim_seconds = claim_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        #: The claim this instance holds, as its last write left it; None when it holds none.
        self.record: FleetRecord | None = None
```

```python
        self.claim_seconds = claim_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        #: The copy beside the database (#481); None where there is no database file to keep it beside.
        self.backstop = backstop
        #: The claim this instance holds, as its last write left it; None when it holds none.
        self.record: FleetRecord | None = None
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
        self._lost = False

    def _call(self, method: str, obj: dict | None = None) -> dict | None:
        path = LEASE_API.format(ns=self.namespace)
        with self.host._client() as client:
            if method == "GET":
                return self.host._get(client, f"{path}/{self.name}", {})
            return self.host._send(client, method, path if method == "POST" else f"{path}/{self.name}", json=obj)

    def _unavailable(self, what: str, exc: ClusterError) -> FleetStateUnavailable:
```

```python
        self._lost = False

    def _call(self, method: str, obj: dict | None = None, *, strict: bool = False) -> dict | None:
        # Serialize the API response AND its copy: a delayed read must not overwrite a later reservation or clear.
        path = LEASE_API.format(ns=self.namespace)
        with self.backstop._lock if self.backstop else nullcontext():
            with self.host._client() as client:
                result = (self.host._get(client, f"{path}/{self.name}", {}) if method == "GET" else
                          self.host._send(client, method, path if method == "POST" else f"{path}/{self.name}", json=obj))
                if result is None and method != "GET":
                    result = self.host._get(client, f"{path}/{self.name}", {})
            if self.backstop is not None and isinstance(result, dict):
                if strict:
                    self.record = _record(self.account, result)  # complete() needs the reservation if keeping it fails
                self._keep(result, strict=strict)
            return result

    def _unavailable(self, what: str, exc: ClusterError) -> FleetStateUnavailable:
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
                                     f"{exc.message.split(': ', 1)[0]}")

    def read(self) -> FleetRecord:
        """The Lease without a claim; an absent one is an empty record, not an error."""
        try:
            obj = self._call("GET")
        except ClusterError as exc:
            if exc.message.startswith("HTTP 404"):
                return _record(self.account, None)
            raise self._unavailable("read", exc) from exc
        return _record(self.account, obj)

```

```python
                                     f"{exc.message.split(': ', 1)[0]}")

    def _keep(self, obj: dict, *, strict: bool = False) -> None:
        """The Lease as this process just read or wrote it, kept beside the database (#481) — so a hand-clear is
        followed within one discovery cadence and a deletion loses nothing. A copy that cannot be written never
        replaces the Lease's outcome: one line when the copy starts failing; `strict` raises instead, for the
        reservation, which must not bind unkept."""
        try:
            self.backstop.save(self.name, (obj.get("metadata") or {}).get("annotations") or {})
        except Exception as exc:  # noqa: BLE001 - the copy never replaces the Lease's own outcome
            detail = (f"cannot keep Lease {self.namespace}/{self.name} in {self.backstop.path}: "
                      f"{type(exc).__name__}: {exc}")
            if strict:
                raise FleetStateUnavailable(detail, self.backstop.action) from exc
            if not self.backstop.failing:                # a transition, not a state (events.py, rule 1)
                failure(log, "fleet-state-unavailable", phase="credential", outcome=FleetStateUnavailable.code,
                        account=self.account, lease=self.name, action=self.backstop.action, detail=detail)
            self.backstop.failing = True
        else:
            self.backstop.failing = False

    def read(self) -> FleetRecord:
        """The Lease without a claim. An absent one reads as its copy beside the database when there is one (#481),
        else as an empty record — neither is an error; absent with a copy that cannot be read is FleetStateUnavailable,
        because then the gate is unknown and nothing may bind."""
        try:
            obj = self._call("GET")
        except ClusterError as exc:
            if not exc.message.startswith("HTTP 404"):
                raise self._unavailable("read", exc) from exc
            if self.backstop is None:
                return _record(self.account, None)
            try:
                kept = self.backstop._all().get(self.name)
            except Exception as err:  # noqa: BLE001 - absent AND unknown: fail closed, as for an unreadable Lease
                raise FleetStateUnavailable(f"Lease {self.namespace}/{self.name} is absent and its copy in "
                                            f"{self.backstop.path} cannot be read: {type(err).__name__}: {err}",
                                            self.backstop.action) from err
            return _record(self.account, None) if kept is None else _absent(self.account, kept)
        return _record(self.account, obj)

```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
        if record.in_flight(now):
            raise ClaimHeld(f"{record.holder} holds {self.name} until {stamp(record.holder_until)}")
        obj = _applied(record.raw or {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                                      "metadata": {"name": self.name, "namespace": self.namespace,
                                                   "labels": {LEASE_TYPE_LABEL: LEASE_TYPE}}},
                       {"account": self.account, **changes})
        obj["spec"] = {**(obj.get("spec") or {}), "holderIdentity": self.identity,
```

```python
        if record.in_flight(now):
            raise ClaimHeld(f"{record.holder} holds {self.name} until {stamp(record.holder_until)}")
        # An absent Lease this dashboard kept is created WITH its copy (#481): the create is the API server's to
        # arbitrate (a second POST answers 409), exactly as a first install's is.
        obj = _applied(record.raw or {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                                      "metadata": {"name": self.name, "namespace": self.namespace,
                                                   "labels": {LEASE_TYPE_LABEL: LEASE_TYPE},
                                                   "annotations": dict(record.seed or {})}},
                       {"account": self.account, **changes})
        obj["spec"] = {**(obj.get("spec") or {}), "holderIdentity": self.identity,
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
            raise self._unavailable("claim", exc) from exc
        self.record, self._lost = (_record(self.account, written) if isinstance(written, dict) else self.read()), False
        return self.record

    def reserve(self, target: str, digest: str) -> None:
```

```python
            raise self._unavailable("claim", exc) from exc
        self.record, self._lost = (_record(self.account, written) if isinstance(written, dict) else self.read()), False
        if record.seed is not None:
            # Said once per deletion: only one create is admitted, and it is this one.
            entry = self.record.refused or {}
            event(log, logging.WARNING, "fleet-lease-absent", account=self.account, lease=self.name, kept="true",
                  refused=entry.get("code"), since=entry.get("at") or None,
                  last_attempt=stamp(self.record.ping_last_attempt) if self.record.ping_last_attempt else None,
                  action=RESTORED)
        return self.record

    def restore(self, record: FleetRecord) -> FleetRecord:
        """Put an absent Lease back now, by one claim and its release (#481): from its copy when there is one, empty
        when the caller knows the account had one (clusters were retrieved as it) and nothing was kept. So the gate is
        on the object again, where §5 Q7's clear can reach it. Said once — one create is admitted; never raises."""
        try:
            self.claim(record)
        except (ClaimHeld, FleetStateUnavailable):
            return record                            # another process put it back, or the next cadence tries
        if record.seed is None:
            event(log, logging.WARNING, "fleet-lease-absent", account=self.account, lease=self.name, kept="false",
                  action=NOTHING_KEPT)
        return self.release() or record

    def reserve(self, target: str, digest: str) -> None:
```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python
                            "uncertain": True, "attempt": uuid.uuid4().hex}, sort_keys=True)
        try:
            written = self._call("PUT", _applied(self.record.raw, {"refused": entry}))
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise ClaimHeld(f"{self.name} changed since it was claimed") from exc
            raise self._unavailable("reserve", exc) from exc
        self.record = _record(self.account, written) if isinstance(written, dict) else self.read()

```

```python
                            "uncertain": True, "attempt": uuid.uuid4().hex}, sort_keys=True)
        try:
            written = self._call("PUT", _applied(self.record.raw, {"refused": entry}), strict=True)
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise ClaimHeld(f"{self.name} changed since it was claimed") from exc
            raise self._unavailable("reserve", exc) from exc
        except FleetStateUnavailable:
            # Kept on the Lease but not beside the database: nothing is sent, so the entry goes again rather than
            # gate a password the directory never saw (#481).
            self.complete()
            raise
        self.record = _record(self.account, written) if isinstance(written, dict) else self.read()

```

<!-- block: local-development/gsd/fleetstate.py | edit -->
```python


__all__ = ["CAS_TRIES", "ClaimHeld", "FleetLease", "FleetRecord", "FleetStateUnavailable", "LEASE_TYPE",
           "LEASE_TYPE_LABEL", "claim_seconds", "lease_digest", "lease_name", "stamp"]
```

```python


class FileBackstop:
    """Every fleet Lease's gate and ping instants, kept in ONE small file beside the database (#481, SPEC_S4f):
    `{"<Lease name>": {"<annotation>": "<value as the Lease holds it>", …}, …}`, the KEPT annotations only. The data
    volume outlives what deletes Leases — `crc start`, a hand — and nothing that copies the database (a backup, a
    report snapshot) copies this file. Written only when what it keeps changed, to a `.tmp` beside it, flushed and
    renamed over it, then the directory flushed (`gsd/store.py#_pre_upgrade_copy`'s order), so a reader never sees half
    of it. One per process; the lock covers each Lease API response and its save, including discovery and self-login threads.
    A 404 reads the atomically renamed file directly; it never observes a partly written file."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        #: The last write of the copy failed: its line was said, and is said again only after a write succeeds.
        self.failing = False
        #: What a `fleet-state-unavailable` about this file tells the operator to do.
        self.action = (f"the data volume must hold a readable, writable {path}; nothing binds until it does. Moving an "
                       f"unreadable copy aside is safe only while every fleet Lease exists (oc get "
                       f"leases.coordination.k8s.io -l {LEASE_TYPE_LABEL}={LEASE_TYPE})")

    def _all(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                state = json.load(fh)
        except FileNotFoundError:
            return {}
        if not isinstance(state, dict) or not all(
                isinstance(kept, dict) and all(isinstance(v, str) for v in kept.values()) for kept in state.values()):
            raise ValueError(f"{self.path} is not a map of Lease names to their annotations")
        return state

    def save(self, name: str, annotations: dict) -> None:
        kept = {key: value for key, value in annotations.items() if key in KEPT}
        with self._lock:
            state = self._all()
            if state.get(name) == kept:
                return                             # the sweep reads every Lease each cadence: most reads write nothing
            state[name] = kept
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            fd = os.open(os.path.dirname(self.path) or ".", os.O_RDONLY)
            try:
                os.fsync(fd)                       # the rename itself: a host crash then `crc start` must find it
            finally:
                os.close(fd)


__all__ = ["CAS_TRIES", "GATE_FILE", "KEPT", "ClaimHeld", "FileBackstop", "FleetLease", "FleetRecord",
           "FleetStateUnavailable", "LEASE_TYPE", "LEASE_TYPE_LABEL", "claim_seconds", "lease_digest", "lease_name",
           "stamp"]
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        self.self_login = SelfLoginSessions(self)
        self._ping_said: set[tuple[str, str]] = set()

    def _maybe_backup(self) -> None:
```

```python
        self.self_login = SelfLoginSessions(self)
        self._ping_said: set[tuple[str, str]] = set()
        # #481 (SPEC_S4f): every fleet Lease's gate, kept beside the database, where `crc start` — which deletes every
        # Lease on the cluster — cannot reach it. A database in memory keeps no copy, as it keeps nothing else.
        from .fleetstate import GATE_FILE, FileBackstop
        path = getattr(store, "path", None)
        self._fleet_backstop = (FileBackstop(os.path.join(os.path.dirname(path), GATE_FILE))
                                if isinstance(path, str) and path != ":memory:" else None)

    def _maybe_backup(self) -> None:
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
    # ── SPEC_S4c (#285): the account Lease and the daily ping ────────────────────────────────────────

    def _fleet_lease(self, client: ClusterClient, namespace: str, account: str):
        from .fleetstate import FleetLease, claim_seconds
        return FleetLease(client, namespace, account, claim_seconds=claim_seconds(self.settings))

    def _host_client(self) -> tuple[ClusterClient, str] | None:
```

```python
    # ── SPEC_S4c (#285): the account Lease and the daily ping ────────────────────────────────────────

    def _fleet_lease(self, client: ClusterClient, namespace: str, account: str, **kw):
        """Every bind path's handle on the account's Lease — the lookup, the ping, self-login — with the copy kept
        beside the database (#481), so no path can read an absent Lease as empty."""
        from .fleetstate import FleetLease, claim_seconds
        return FleetLease(client, namespace, account, claim_seconds=claim_seconds(self.settings),
                          backstop=self._fleet_backstop, **kw)

    def _host_client(self) -> tuple[ClusterClient, str] | None:
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            for name in names:
                registry.set_standing_finding("lease", name, None)
            if record.reservation_pending(datetime.now(UTC), lease.claim_seconds):
                continue    # an attempt under way: its reservation is not yet an answer (#419, round 2)
```

```python
            for name in names:
                registry.set_standing_finding("lease", name, None)
            if leader and record.resource_version is None and (
                    record.seed is not None or (account in declared and account in targets)):
                # AN ABSENT LEASE THIS ACCOUNT HAD (#481): kept beside the database, or implied by clusters retrieved as
                # it. Put back now, once, so a gated account whose ping stands down has its gate on the object again.
                record = lease.restore(record)
            if record.reservation_pending(datetime.now(UTC), lease.claim_seconds):
                continue    # an attempt under way: its reservation is not yet an answer (#419, round 2)
```

<!-- block: local-development/gsd/selflogin.py | edit -->
```python
from .fleetlogin import FleetLogin, FleetSession, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, fleet_account, fleet_password
from .fleetstate import ClaimHeld, FleetLease, FleetStateUnavailable, claim_seconds, lease_digest, lease_name, stamp
from .kube import AUTH_FAILED, OK, UNREACHABLE

```

```python
from .fleetlogin import FleetLogin, FleetSession, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, fleet_account, fleet_password
from .fleetstate import ClaimHeld, FleetStateUnavailable, lease_digest, lease_name, stamp
from .kube import AUTH_FAILED, OK, UNREACHABLE

```

<!-- block: local-development/gsd/selflogin.py | edit -->
```python
    def _acquire(self, cluster, client, namespace, account, password, salt, key, held) -> ClusterConfig | None:
        poller = self._poller
        lease = FleetLease(client, namespace, account, claim_seconds=claim_seconds(poller.settings), clock=self._clock)
        try:
            lease.claim()
```

```python
    def _acquire(self, cluster, client, namespace, account, password, salt, key, held) -> ClusterConfig | None:
        poller = self._poller
        lease = poller._fleet_lease(client, namespace, account, clock=self._clock)
        try:
            lease.claim()
```

<!-- block: local-development/tests/test_fleet_gate_backstop.py | create -->
```python
"""#481 (SPEC_S4f): the fleet gate's backstop — a deleted fleet Lease is put back from the copy kept beside the
database, so `crc start` (which deletes every Lease on the cluster) sends no refused password again and pings no
second time in a day.

The harness is SPEC_S4c's (`tests/test_fleet_lifecycle.py`): `wire` counts authorize requests on the fake OAuth
server — the unit every budget is stated in — and a new `Poller` over the same fake API server is a restarted pod.
Every process's database sits in `tmp_path`, so the copy beside it, `tmp_path/fleet-gate.json`, is one data volume
that outlives the pods. Two events are modelled:

  crc_start(host)   every Lease deleted — crc-org/crc pkg/crc/cluster/cluster.go:509, `oc delete -A lease --all`, run
                    on every cold start — and the caller builds new processes: every pod restarted, its memory gone.
  delete_leases     the same deletion while a process keeps running.

`ApiServer` is the suite's `LeaseAPI` plus the two API-server behaviours a deleted Lease meets (Kubernetes v1.35.6,
`fc0e7a6c`): every create stamps a `metadata.uid`; and a PUT to an absent name creates it only when its body carries no
uid (pkg/registry/coordination/lease/strategy.go:84, AllowCreateOnUpdate; registry/generic/registry/store.go:646-712),
while a body carrying one — every PUT the dashboard sends, built from the object it read — is a UID precondition that
an absent object fails with 409 (registry/rest/update.go:188-203, storage/interfaces.go:150-155,
storage/errors/storage.go:80-81). No test logs in as the fleet account of any cluster: USER is the harness's own
name."""

from __future__ import annotations

import json
import logging
import uuid

import pytest

from gsd.fleetstate import PREFIX, FleetLease, lease_name
from gsd.kube import ClusterError
from gsd.poller import Poller
from gsd.store import Store
from test_fleet_lifecycle import (ANSWERS, LEASES, LeaseAPI, LeaseHost, lines, process, retrieved, self_login,
                                  sessions, stanza)
from test_fleet_login import T0, USER, login_302, refused_401
from test_fleet_lookup import wire  # noqa: F401 - the fixture

REFUSED = PREFIX + "refused"
COPY = "fleet-gate.json"


class ApiServer(LeaseAPI):
    """The suite's LeaseAPI with what the API server does to a PUT that meets a deleted Lease (module docstring)."""

    def write(self, method: str, name: str, obj: dict) -> dict:
        uid = obj["metadata"].get("uid")
        stored = self.objects.get(name)
        if not self.refuse and method == "PUT" and uid and uid != (stored or {}).get("metadata", {}).get("uid"):
            self.writes.append((method, name))
            raise ClusterError("unreachable", f"HTTP 409 on PUT {LEASES}/{name}: Precondition failed: UID")
        if not self.refuse and method == "PUT" and stored is None:
            method = "POST"                                       # no uid in the body: AllowCreateOnUpdate
        created = method == "POST" and name not in self.objects
        out = super().write(method, name, obj)
        if created:
            out["metadata"]["uid"] = self.objects[name]["metadata"]["uid"] = str(uuid.uuid4())
        return out


def api_host() -> LeaseHost:
    return LeaseHost(ApiServer())


def estate(host: LeaseHost) -> LeaseHost:
    """The account's Lease exists, empty, as every retrieval since #285 leaves it: an estate, not a first install."""
    lease = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-0")
    lease.claim()
    lease.release()
    return host


def delete_leases(host: LeaseHost) -> None:
    host.leases.objects.clear()


def crc_start(host: LeaseHost, tmp_path=None) -> None:
    """The Lease half of `crc start`; with `tmp_path`, persistence is off and the copy goes with the pod."""
    delete_leases(host)
    if tmp_path is not None:
        (tmp_path / COPY).unlink(missing_ok=True)


def clear_by_hand(host: LeaseHost) -> None:
    """SPEC_S4c §5 Q7: `oc annotate leases.coordination.k8s.io gsd-fleet-… groupsync-dashboard.io/refused-`."""
    obj = host.leases.objects[lease_name(USER)]
    obj["metadata"]["annotations"].pop(REFUSED)
    host.leases.serial += 1
    obj["metadata"]["resourceVersion"] = str(host.leases.serial)


def kept(tmp_path) -> dict:
    assert (tmp_path / COPY).is_file(), "nothing is kept beside the database"
    return json.loads((tmp_path / COPY).read_text())


class Binds:
    """Authorize requests since the last `step`."""

    def __init__(self, wire):
        self.wire, self.seen, self.steps = wire, 0, []

    def step(self) -> int:
        self.steps.append(len(self.wire.authorize) - self.seen)
        self.seen = len(self.wire.authorize)
        return self.steps[-1]


def run(path: str, p: Poller) -> None:
    """One cycle of one bind path in process `p`."""
    if path == "lookup":
        p._retrieve_pending()
    elif path == "ping":
        p._ping_accounts()
    else:
        sessions(p, [T0]).credential_for(p.settings.cluster("sl"))


CLUSTERS = {"lookup": ((stanza("l1"),), ()), "ping": ((), (retrieved("r1"),)), "self-login": ((self_login("sl"),), ())}


def pod(tmp_path, monkeypatch, host, path: str, name: str) -> Poller:
    clusters, discovered = CLUSTERS[path]
    return process(tmp_path, monkeypatch, host, *clusters, discovered=discovered, name=name)


# ── B2: a refused password stays refused across a deletion ───────────────────────────────────────

@pytest.mark.parametrize("path", sorted(CLUSTERS))
@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_a_refused_password_stays_refused_across_crc_starts(tmp_path, monkeypatch, wire, answer, path):
    """The issue's Definition of Done: a wrong (401) or locked (500) password on each bind path, then a restart with
    the Lease kept, then two `crc start`s. Before #481 each start cost one more bind: [1, 0, 1, 1]."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [ANSWERS[answer]() for _ in range(6)]
    first = pod(tmp_path, monkeypatch, host, path, "boot")
    run(path, first); run(path, first)
    binds.step()
    run(path, pod(tmp_path, monkeypatch, host, path, "restart"))
    binds.step()
    for n in (1, 2):
        crc_start(host)
        run(path, pod(tmp_path, monkeypatch, host, path, f"crc{n}"))
        binds.step()
        assert REFUSED in host.leases.annotations(), "the Lease is not back with its entry, where §5 Q7 can clear it"
    assert binds.steps == [1, 0, 0, 0], binds.steps


def test_an_uncertain_reservation_survives_a_crc_start(tmp_path, monkeypatch, wire):
    """A process that died after the authorize GET left its reservation (#419, D1) on the Lease and beside the
    database; after a `crc start` it still gates. Before #481: +1."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [lambda request: SystemExit("the process dies after the authorize GET"), refused_401()]
    first = process(tmp_path, monkeypatch, host, stanza("l1"), name="boot")
    with pytest.MonkeyPatch.context() as crash, pytest.raises(SystemExit):
        crash.setattr(FleetLease, "release", lambda *a, **k: None)          # nothing runs after a crash
        first._retrieve_pending()
    binds.step()
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="crc")._retrieve_pending()
    binds.step()
    assert binds.steps == [1, 0], binds.steps


def test_a_live_deletion_then_an_ordinary_restart_binds_nothing(tmp_path, monkeypatch, wire):
    """The Lease deleted while the pod runs: its own gate held, but the Lease it re-created carried no entry, so the
    next ordinary restart bound again. Before #481: [1, 0, 1]."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [refused_401() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    p._retrieve_pending()
    binds.step()
    delete_leases(host)
    for state in p._lookups.values():
        state.not_before = 0.0                                               # the lookup's own backoff elapsed
    p._retrieve_pending(); p._retrieve_pending()
    binds.step()
    process(tmp_path, monkeypatch, host, stanza("l1"), name="redeploy")._retrieve_pending()
    binds.step()
    assert binds.steps == [1, 0, 0], binds.steps


def test_a_deletion_while_an_attempt_is_on_the_wire_admits_no_second_bind(tmp_path, monkeypatch, wire):
    """One process, two paths: the lookup's authorize is in flight when every Lease is deleted, and the same process's
    self-login thread tries. The claim was all that stood between them; the reservation, kept beside the database
    before the wire, now gates the second. Before #481: 2 authorizes."""
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), self_login("sl"), name="pod")
    s = sessions(p, [T0])

    def mid_flight(request):
        delete_leases(host)
        s.credential_for(p.settings.cluster("sl"))                          # the other thread, meanwhile
        return refused_401()

    wire.answers = [mid_flight, refused_401(), refused_401()]
    p._retrieve_pending()
    assert len(wire.authorize) == 1, len(wire.authorize)


def test_a_refusal_written_after_a_live_deletion_is_not_lost(tmp_path, monkeypatch, wire):
    """The refusal's PUT carries the uid it read, so the API server answers 409 and does not re-create the Lease
    (retracting #481's research, §1.3): the answer is not on any Lease. The reservation kept beside the database
    still gates the restart. Before #481: 2 authorizes."""
    host = api_host()

    def deleted_in_flight(request):
        delete_leases(host)
        return refused_401()

    wire.answers = [deleted_in_flight, refused_401()]
    process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")._retrieve_pending()
    assert lease_name(USER) not in host.leases.objects, "a PUT carrying the uid it read re-created the Lease"
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 1, len(wire.authorize)


# ── B3: the ping stays once a day across the same events ─────────────────────────────────────────

def test_the_ping_stays_once_a_day_across_crc_starts_and_a_live_deletion(tmp_path, monkeypatch, wire):
    """A VALID password, three retrieved clusters: one ping per interval across a restart, two `crc start`s the same
    day and a live deletion; a day later the next target by name. Before #481: [1, 0, 1, 1, 1, …]."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [login_302() for _ in range(8)]
    fleet = [retrieved("c00"), retrieved("c01"), retrieved("c02")]
    p = process(tmp_path, monkeypatch, host, discovered=fleet, name="boot")
    p._ping_accounts(); p._ping_accounts()
    binds.step()
    process(tmp_path, monkeypatch, host, discovered=fleet, name="restart")._ping_accounts()
    binds.step()
    for n in (1, 2):
        crc_start(host)
        p = process(tmp_path, monkeypatch, host, discovered=fleet, name=f"crc{n}")
        p._ping_accounts()
        binds.step()
    delete_leases(host)
    p._ping_accounts()
    binds.step()
    host.leases.backdate(USER, PREFIX + "ping-last-attempt", 86400)
    p._ping_accounts()
    binds.step()
    assert binds.steps == [1, 0, 0, 0, 0, 1], binds.steps
    assert host.leases.annotations()[PREFIX + "ping-last-target"] == "c01", "the rotation restarted at the first name"


# ── the Lease stays the authority; §5 Q7's clear re-arms; the runbook's second clear ─────────────

def test_the_lease_stays_the_authority_whenever_it_exists(tmp_path, monkeypatch, wire):
    """The copy still holds an entry the Lease no longer does (removed by hand, and no pod read it since): the Lease
    exists, so it decides — one bind, the re-arm — and the copy follows it on that read."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    process(tmp_path, monkeypatch, host, stanza("l1"), name="boot")._retrieve_pending()
    clear_by_hand(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)
    assert REFUSED not in kept(tmp_path)[lease_name(USER)], "the copy did not follow the Lease"


def test_a_clear_the_running_pod_has_read_survives_a_crc_start(tmp_path, monkeypatch, wire):
    """§5 Q7's clear made while the pod runs: its sweep reads the cleared Lease within a cadence and the copy follows
    it, so a `crc start` before the restart does not bring the entry back — the restarted pod binds once, the re-arm."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    p._retrieve_pending()
    clear_by_hand(host)
    p._ping_accounts()                                                     # the sweep's read: no claim, no write
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="crc")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)


def test_q7s_clear_still_rearms_the_gate(tmp_path, monkeypatch, wire):
    """SPEC_S4c §5 Q7, unchanged: the entry removed by hand, the running pod's own gate holds until the restart,
    and the restart binds once."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="pod")
    p._retrieve_pending(); p._ping_accounts()
    clear_by_hand(host)
    p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1, (len(wire.authorize), "the running pod keeps its gate until it restarts")
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)


@pytest.mark.parametrize("path", ["lookup", "ping"])
def test_a_clear_by_hand_then_a_crc_start_before_any_read_is_undone_and_said(tmp_path, monkeypatch, wire, caplog, path):
    """The one ordering the copy changes: the entry removed while no pod read the Lease, then a `crc start` — the copy
    puts it back, an over-block, said once. The runbook's step: the Lease is back (for a ping-only account, the lab's
    shape, the sweep puts it back), so remove the entry again and restart the pod — the re-arm, one bind. Before #481
    the start kept the clear: the first cycle bound."""
    host = estate(api_host())
    wire.answers = [refused_401(), *[login_302() for _ in range(4)]]
    run(path, pod(tmp_path, monkeypatch, host, path, "boot"))
    clear_by_hand(host)
    crc_start(host)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = pod(tmp_path, monkeypatch, host, path, "crc")
        run(path, p); run(path, p)
    assert len(wire.authorize) == 1, (len(wire.authorize), "a clear no pod read survived the start")
    said = lines(caplog, "fleet-lease-absent")
    assert len(said) == 1, said
    assert f"account={USER}" in said[0] and "kept=true" in said[0] and "refused=login-refused" in said[0]
    assert "remove it again and restart the pod" in said[0]
    clear_by_hand(host)
    if path == "ping":
        host.leases.backdate(USER, PREFIX + "ping-last-attempt", 86400)     # the refused attempt's day has passed
    run(path, pod(tmp_path, monkeypatch, host, path, "restarted"))
    assert len(wire.authorize) == 2, len(wire.authorize)


# ── the warning: said once, by the process that puts the Lease back ──────────────────────────────

def test_the_restore_is_said_once_by_the_process_that_creates_it(tmp_path, monkeypatch, wire, caplog):
    """Two processes after a `crc start`, each running the lookup and the sweep twice: one create is admitted, so one
    line, whichever path made it."""
    host = api_host()
    wire.answers = [refused_401() for _ in range(4)]
    process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="boot")._retrieve_pending()
    crc_start(host)
    with caplog.at_level(logging.INFO, logger="gsd"):
        a = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="a")
        b = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="b")
        for p in (a, b, a, b):
            p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1, len(wire.authorize)
    assert len(lines(caplog, "fleet-lease-absent")) == 1, lines(caplog, "fleet-lease-absent")
    assert host.leases.objects[lease_name(USER)]["spec"]["holderIdentity"] == "", "the restore left a claim held"


def test_nothing_kept_is_said_once_and_the_ping_binds_again(tmp_path, monkeypatch, wire, caplog):
    """Persistence off (the copy goes with the pod), then a `crc start`, on an account with retrieved clusters: the
    Lease cannot be put back as it was, and the line says so once — the row #481 does not fix: +1 ping."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [login_302() for _ in range(3)]
    process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="boot")._ping_accounts()
    binds.step()
    crc_start(host, tmp_path)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="crc")
        p._ping_accounts(); p._ping_accounts()
    binds.step()
    assert binds.steps == [1, 1], binds.steps
    said = lines(caplog, "fleet-lease-absent")
    assert len(said) == 1 and "kept=false" in said[0] and "may be sent once more" in said[0], said


@pytest.mark.parametrize("path", ["lookup", "self-login"])
def test_persistence_off_is_the_row_not_fixed(tmp_path, monkeypatch, wire, path):
    """The operator's accepted row (2026-09-29): with the copy gone with the pod, a `crc start` still costs one bind for
    a refused password — as before #481."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [refused_401() for _ in range(4)]
    run(path, pod(tmp_path, monkeypatch, host, path, "boot"))
    binds.step()
    crc_start(host, tmp_path)
    run(path, pod(tmp_path, monkeypatch, host, path, "crc"))
    binds.step()
    assert binds.steps == [1, 1], binds.steps


def test_a_first_install_binds_once_and_says_nothing(tmp_path, monkeypatch, wire, caplog):
    """No Lease and nothing kept, with no retrieved cluster: a first install, not a deletion — the sweep, which runs
    first here, neither creates the Lease nor says a word, and the lookup binds once, as before."""
    host = api_host()
    wire.answers = [refused_401()]
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
        p._ping_accounts()
        assert host.leases.writes == [], "the sweep wrote a Lease for an account with no trace of one"
        p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1 and lines(caplog, "fleet-lease-absent") == []


def test_a_standbys_view_after_a_crc_start_is_the_kept_copy_and_it_writes_nothing(tmp_path, monkeypatch, wire):
    """A standby serves the tab and /metrics from the Lease it reads (SPEC_S4c §3.4); after a `crc start` it reads the
    copy — the last success stays on the page — and, not being the leader, it does not put the Lease back. Before
    #481 `last_ok` read null until the leader's next ping."""
    host = estate(api_host())
    wire.answers = [login_302()]
    leader = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="leader")
    leader._ping_accounts()
    before = leader.signals.fleet_accounts()[USER]["last_ok"]
    crc_start(host)
    standby = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="standby")
    standby.elector = type("Standby", (), {"is_leader": False})()
    standby._ping_accounts()
    assert before and standby.signals.fleet_accounts()[USER]["last_ok"] == before
    assert host.leases.objects == {} and len(wire.authorize) == 1


# ── fail closed ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content", ["{", json.dumps({"gsd-fleet-x": "not a map"}), json.dumps(["a list"])])
def test_an_unreadable_copy_behind_an_absent_lease_binds_nothing(tmp_path, monkeypatch, wire, content):
    """Absent AND unknown: every path fails closed with `fleet-state-unavailable` naming the copy, as for an
    unreadable Lease (SPEC_S4c R8). Before #481 an absent Lease read as empty and every path bound."""
    host = api_host()
    (tmp_path / COPY).write_text(content)
    wire.answers = [refused_401() for _ in range(3)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), self_login("sl"), discovered=[retrieved("r1")], name="pod")
    p._retrieve_pending(); p._ping_accounts()
    assert sessions(p, [T0]).credential_for(p.settings.cluster("sl")) is None
    assert wire.authorize == [], (len(wire.authorize), "a bind behind an absent Lease whose copy cannot be read")
    assert host.leases.writes == [], "a Lease was created over a gate nobody can read"
    found = {f.secret: f for f in p.settings.cluster_registry.findings() if f.code == "fleet-state-unavailable"}
    assert {"gsd-cluster-l1", "gsd-cluster-r1", "sl"} <= set(found), sorted(found)
    assert all(COPY in f.detail for f in found.values())


def test_a_copy_that_cannot_be_written_at_the_reservation_binds_nothing_and_strands_no_entry(tmp_path, monkeypatch,
                                                                                            wire, caplog):
    """The reservation must be kept in both places before the wire. When the copy cannot be written, nothing is sent
    and the reservation goes again — else it would gate, until §5 Q7's clear, a password the directory never saw
    (#481's probe on the research prototype: 0 authorizes, the `uncertain` entry left). Said when the copy starts
    failing, not on every write: three cycles, one line."""
    host = api_host()
    (tmp_path / f"{COPY}.tmp").mkdir()                                       # every write of the copy fails
    wire.answers = [refused_401() for _ in range(3)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    with caplog.at_level(logging.INFO, logger="gsd"):
        for _ in range(3):
            p._retrieve_pending()
    assert wire.authorize == [], len(wire.authorize)
    assert REFUSED not in host.leases.annotations(), "a reservation for a password never sent gates the account"
    found = [f for f in p.settings.cluster_registry.findings() if f.secret == "gsd-cluster-l1"]
    assert [f.code for f in found] == ["fleet-state-unavailable"] and COPY in found[0].detail, found
    said = lines(caplog, "fleet-state-unavailable")
    assert len(said) == 1 and COPY in said[0], said


# ── what is kept, where, and where not ───────────────────────────────────────────────────────────

def test_the_copy_is_the_gate_and_the_ping_instants_as_the_lease_holds_them(tmp_path, monkeypatch, wire):
    """`<the database's directory>/fleet-gate.json`: `{Lease name: {annotation: value}}`, the refusal and the five
    ping annotations byte for byte, never the claim or the account; written by rename, nothing left beside it."""
    host = api_host()
    wire.answers = [login_302(), refused_401()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="pod")
    p._ping_accounts()
    host.rotate("a-wrong-password")
    p._retrieve_pending()
    lease = host.leases.objects[lease_name(USER)]["metadata"]["annotations"]
    assert kept(tmp_path) == {lease_name(USER): {k: v for k, v in lease.items() if k != PREFIX + "account"}}
    assert sorted(kept(tmp_path)[lease_name(USER)]) == sorted(
        PREFIX + k for k in ("refused", "ping-last-attempt", "ping-last-ok", "ping-last-outcome", "ping-last-target",
                             "ping-digest"))
    assert sorted(x.name for x in tmp_path.iterdir() if not x.name.endswith((".db", ".db-wal", ".db-shm"))) == [COPY]


def test_a_database_in_memory_keeps_no_copy(tmp_path, monkeypatch, wire):
    """`:memory:` keeps nothing across a restart, so it keeps no copy either, and writes nothing in the working
    directory: a `crc start` costs +1 there, as before #481."""
    from gsd.config import ClusterConfig, Settings
    from gsd.metrics import RuntimeSignals
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    host = api_host()
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    wire.answers = [refused_401(), refused_401()]

    def memory_pod() -> Poller:
        s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), stanza("l1")],
                     db_path=":memory:", cluster_secrets_writes_enabled=True, fleet_account_username=USER)
        return Poller(Store(":memory:"), s, signals=RuntimeSignals())

    memory_pod()._retrieve_pending()
    crc_start(host)
    memory_pod()._retrieve_pending()
    assert len(wire.authorize) == 2 and list(tmp_path.iterdir()) == []


# Reviewer regressions: test_review_backstop.py
"""Deterministic interleavings of the discovery reader and a self-login writer."""
import threading
from concurrent.futures import ThreadPoolExecutor

from test_fleet_gate_backstop import api_host, estate, clear_by_hand, crc_start
from test_fleet_lifecycle import process, stanza
from test_fleet_login import USER, refused_401, login_302
from test_fleet_lookup import wire
from gsd.fleetstate import FleetLease


def overlap(monkeypatch, observer, newer):
    """An old response pauses immediately before it reaches the file; newer work runs meanwhile."""
    paused, release, started = threading.Event(), threading.Event(), threading.Event()
    original = FleetLease._keep
    def delayed(self, record, **kw):
        if self is observer:
            paused.set()
            assert release.wait(5), "reader was never released"
        return original(self, record, **kw)
    monkeypatch.setattr(FleetLease, "_keep", delayed)
    def newer_work():
        started.set()
        return newer()
    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(observer.read)
        assert paused.wait(5), "reader did not reach the file"
        new = pool.submit(newer_work)
        assert started.wait(5)
        # Old code lets the newer response reach the file first. Serialized code blocks it.
        try:
            new.result(timeout=0.2)
        except TimeoutError:
            pass
        finally:
            release.set()
        old.result(timeout=5)
        new.result(timeout=5)


def test_delayed_read_cannot_erase_a_reserved_and_refused_password(tmp_path, monkeypatch, wire):
    host = estate(api_host())
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    observer = p._fleet_lease(host, "ns", USER)
    wire.answers = [refused_401(), refused_401()]
    overlap(monkeypatch, observer, p._retrieve_pending)
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 1, "a late empty snapshot erased the durable gate: second bind"


def test_delayed_read_cannot_undo_a_clear_another_reader_observed(tmp_path, monkeypatch, wire):
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401(), login_302()]
    p._retrieve_pending()
    observer = p._fleet_lease(host, "ns", USER)
    def observe_clear():
        clear_by_hand(host)
        p._fleet_lease(host, "ns", USER).read()
    overlap(monkeypatch, observer, observe_clear)
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 2, "a late refused snapshot undid an observed Q7 clear"


def test_restore_preserves_a_q7_clear_during_its_release(tmp_path, monkeypatch, wire):
    from test_fleet_gate_backstop import REFUSED, kept
    from gsd.fleetstate import lease_name
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401()]
    p._retrieve_pending()
    crc_start(host)
    lease = p._fleet_lease(host, "ns", USER)
    record = lease.read()
    original = host._send
    def clear_before_release(client, method, path, **kw):
        if method == "PUT":
            monkeypatch.setattr(host, "_send", original)
            clear_by_hand(host)
        return original(client, method, path, **kw)
    monkeypatch.setattr(host, "_send", clear_before_release)
    restored = lease.restore(record)
    assert restored.refused is None
    assert REFUSED not in host.leases.annotations()
    assert REFUSED not in kept(tmp_path)[lease_name(USER)]
    assert len(wire.authorize) == 1, "restore caused a bind"


def test_two_absent_readers_have_only_one_successful_create(tmp_path, monkeypatch, wire, caplog):
    import pytest
    from gsd.fleetstate import ClaimHeld
    from test_fleet_lifecycle import lines
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401()]
    p._retrieve_pending()
    crc_start(host)
    a = p._fleet_lease(host, "ns", USER, identity="a")
    b = p._fleet_lease(host, "ns", USER, identity="b")
    ar, br = a.read(), b.read()
    a.claim(ar)
    with pytest.raises(ClaimHeld):
        b.claim(br)
    assert len(lines(caplog, "fleet-lease-absent")) == 1
    assert len(wire.authorize) == 1


# Reviewer regressions: test_review_scope.py
from pathlib import Path
import pytest
from test_fleet_gate_backstop import api_host, estate, crc_start
from test_fleet_lifecycle import process, retrieved
from test_fleet_login import USER, refused_401, login_302
from test_fleet_lookup import wire


@pytest.mark.parametrize("answer", [refused_401, login_302])
def test_independent_pod_copy_can_miss_a_refusal_before_crc(tmp_path, monkeypatch, wire, answer):
    host = estate(api_host())
    a, b = tmp_path / "pod-a", tmp_path / "pod-b"
    a.mkdir(); b.mkdir()
    first = process(a, monkeypatch, host, discovered=[retrieved("r1")], name="pod-a")
    second = process(b, monkeypatch, host, discovered=[retrieved("r1")], name="pod-b")
    second._fleet_lease(host, "ns", USER).read()  # B has not yet seen A's later refusal.
    wire.answers = [answer(), answer()]
    first._ping_accounts()
    assert len(wire.authorize) == 1
    crc_start(host)
    process(b, monkeypatch, host, discovered=[retrieved("r1")], name="pod-b")._ping_accounts()
    assert len(wire.authorize) == 2
    # The code's residual is accepted explicitly, rather than described as covered at each pod.
    import gsd
    spec = Path(gsd.__file__).resolve().parents[2] / "docs/specs/SPEC_S4f_fleet_gate_backstop.md"
    scope = spec.read_text().split("### 3.9 Above one replica, and with persistence off", 1)[1].split("## 4.", 1)[0]
    assert "A stale per-pod copy can allow +1 bind or +1 ping after a Lease deletion" in scope


# Reviewer regressions: test_review_docs.py
from pathlib import Path
import gsd

ROOT = Path(gsd.__file__).resolve().parents[2]

def test_proof_heading_distinguishes_regressions_from_unchanged_controls():
    spec = (ROOT / 'docs/specs/SPEC_S4f_fleet_gate_backstop.md').read_text()
    section = spec.split('## 5. The documents, and the proof', 1)[1].split('### 5.1', 1)[0]
    text = ' '.join(section.split())
    assert '22 assertion failures and 6 passing controls' in text
    assert '28 passes with the blocks' in text


def test_runbook_describes_reservation_failures_and_present_lease_saves():
    runbook = (ROOT / 'charts/group-sync-dashboard/RUNBOOK.md').read_text()
    text = ' '.join(runbook.split('## 7.', 1)[1].split())
    assert "a path already gated need not attempt a reservation or publish another finding" in text
    assert "Saving a present Lease also parses the existing file" in text
    assert "Run one replica for the +0 guarantee" in text
```

<!-- block: local-development/tests/test_cluster_rejoin.py | edit -->
```python
# ── the runbook (the 2026-09-23 requirement) ───────────────────────────────────────────────────────────────

def test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it():
    runbook = REPO / "charts/group-sync-dashboard/RUNBOOK.md"
    headings = re.findall(r"^## (\d)\. ", runbook.read_text(), re.M)
    assert headings == ["1", "2", "3", "4", "5", "6"], headings
    assert "../charts/group-sync-dashboard/RUNBOOK.md" in (REPO / "docs/README.md").read_text()
    assert "(RUNBOOK.md)" in (REPO / "charts/group-sync-dashboard/README.md").read_text()
```

```python
# ── the runbook (the 2026-09-23 requirement) ───────────────────────────────────────────────────────────────

def test_the_runbook_sits_beside_the_values_with_seven_sections_and_docs_links_it():
    """Six for Refresh and Rejoin (#316); the seventh clears the fleet account's entry by hand (#481, SPEC_S4f)."""
    runbook = REPO / "charts/group-sync-dashboard/RUNBOOK.md"
    headings = re.findall(r"^## (\d)\. ", runbook.read_text(), re.M)
    assert headings == ["1", "2", "3", "4", "5", "6", "7"], headings
    assert "../charts/group-sync-dashboard/RUNBOOK.md" in (REPO / "docs/README.md").read_text()
    assert "(RUNBOOK.md)" in (REPO / "charts/group-sync-dashboard/README.md").read_text()
```

<!-- block: .gitignore | edit -->
```text
*.db-wal
*.db-shm
clusters.yaml
.pytest_cache/
```

```text
*.db-wal
*.db-shm
# The fleet Leases' gate, kept beside the database (#481): runtime state, like the database itself.
fleet-gate.json*
clusters.yaml
.pytest_cache/
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
there before the password is sent; a session clears it and a refusal replaces it, so a restart, a crash or
another replica reads it and does not send the password again; a success is still not recorded there. Keep one
replica.

Companion to [`docs/CLUSTER_STANZA.md`](../../docs/CLUSTER_STANZA.md), which covers *what a stanza may
```

```markdown
there before the password is sent; a session clears it and a refusal replaces it, so a restart, a crash or
another replica reads it and does not send the password again; a success is still not recorded there. Keep one
replica. Since #481 the same record is also kept beside the database, in `fleet-gate.json` on the data volume, because
`crc start` deletes every Lease on the cluster: a deleted Lease is put back from that copy, so it sends no refused
password again and pings no second time that day, and deleting the Lease no longer clears its entry (clear it as
[`RUNBOOK.md`](RUNBOOK.md) section 7 says). With `persistence.enabled: false` the copy lasts only as long as the pod.

Companion to [`docs/CLUSTER_STANZA.md`](../../docs/CLUSTER_STANZA.md), which covers *what a stanza may
```

<!-- block: charts/group-sync-dashboard/RUNBOOK.md | edit -->
```markdown
oc --context="$REMOTE" delete useroauthaccesstokens <name>
~~~
```

```markdown
oc --context="$REMOTE" delete useroauthaccesstokens <name>
~~~

## 7. The fleet account is held back: clear its entry by hand

A `saTokenLookup` cluster whose lookup reads `login-refused` or `login-failed`, a `userSelfLogin` cluster reading
`self-login-suspended`, or a `fleet-ping-failed … gave_up=true` line all mean the same thing: the directory answered the
fleet account's password with a failure, and the dashboard will not send that password again. The answer is recorded on
the account's Lease in this namespace, and the finding and the line name it. A 401 is a wrong password: rotate the
fleet password Secret, and the new password is tried by itself. Clear the entry by hand only when the password is right
and the answer was about something else: a sick target's 500, or an account the directory has since unlocked.

~~~sh
LEASE=gsd-fleet-...   # the Lease the finding or the line names
oc get leases.coordination.k8s.io "$LEASE" -n $NS -o jsonpath='{.metadata.annotations.groupsync-dashboard\.io/refused}{"\n"}'
oc annotate leases.coordination.k8s.io "$LEASE" -n $NS groupsync-dashboard.io/refused-
oc rollout restart deployment.apps/$REL -n $NS      # the running pod keeps its own copy of the refusal until it restarts
~~~

**After a `crc start`, or a Lease deleted by hand.** `crc start` deletes every Lease on the cluster. The dashboard keeps
each fleet Lease's entry and its daily ping's instants beside its database, in `/data/fleet-gate.json`
(`/data/<pod>/fleet-gate.json` above one replica), and puts a deleted Lease back from it within one discovery interval,
saying so once. Run one replica for the +0 guarantee: independent per-pod copies may be stale, so the replica that
recreates the Lease can still allow another bind or ping (SPEC_S4f §3.9):

~~~sh
oc logs -n $NS deployment.apps/$REL -c dashboard --since=15m | grep fleet-lease-absent
~~~

So deleting the Lease does not clear its entry; removing the annotation does. One order undoes a clear: the entry
removed, then a `crc start` before any dashboard pod had read the Lease again — a running pod reads it once per
discovery interval (300 s by default), and `crc start` restarts the pod without that read. The copy still held the
entry and puts it back, and the line says `kept=true refused=<code>`. Wait until `oc get leases.coordination.k8s.io
"$LEASE" -n $NS` finds the Lease again, then remove the entry and restart the pod with `oc rollout restart`, as above. With
`persistence.enabled: false` the copy lives only as long as the pod: a new pod whose Lease was deleted says
`kept=false`, and a password the entry held back may be sent once more.

**If an absent Lease's copy cannot be read, or a reservation cannot be kept**, nothing binds and the attempting path
reports `fleet-state-unavailable` naming the file. Other saves log the failure while the Lease remains authoritative;
a path already gated need not attempt a reservation or publish another finding. Free space on the data volume. Saving
a present Lease also parses the existing file. Move an unreadable file aside only after checking that every fleet
Lease exists:

~~~sh
oc get leases.coordination.k8s.io -n $NS -l groupsync-dashboard.io/lease-type=fleet-account
oc exec -n $NS deployment.apps/$REL -c dashboard -- mv /data/fleet-gate.json /data/fleet-gate.json.unreadable
~~~
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
  (sitecustomize, an sqlite transport and an oc stub) and a pending report under reports/
  were **rejected**: too heavy for a document test; the lab walk is the acceptance.

## 0. The requirement, in business terms
```

```markdown
  (sitecustomize, an sqlite transport and an oc stub) and a pending report under reports/
  were **rejected**: too heavy for a document test; the lab walk is the acceptance.
- **#481 (`docs/specs/SPEC_S4f_fleet_gate_backstop.md`, the operator's option (c2) of 2026-09-29): a deleted Lease is
  no longer "+1 per act".** §3.2's B2 says "the entry removed by hand, or the Lease deleted, is **+1 per act**, an
  operator's act by a principal that can already read the password Secret", and §4's and §8.2's rows say the same.
  Neither half held. `crc start` deletes every Lease on the cluster at every cold start (crc-org/crc
  pkg/crc/cluster/cluster.go:509, since crc 2.29.0), and no operator decides it. A namespace `admin` or `edit` can
  delete the fleet Lease without reading a password Secret kept in another namespace. Since #481 the gate and the ping's
  instants are also kept beside the database, and an absent Lease is read from that copy and put back: a deletion costs
  +0 with persistence on at one replica. Independent per-pod copies above one replica may be stale and can allow
  +1 after a deletion (SPEC_S4f §3.9). §5 Q7's clear still re-arms, +1, and the runbook entry Q7 asked for is
  `charts/group-sync-dashboard/RUNBOOK.md` section 7. SPEC_S4f §4 restates B2's and B3's budgets over the system,
  scope by scope, with the rows it leaves: persistence off, an etcd restore, a reinstall into another namespace, and a
  clear by hand followed by a `crc start`. The body below is unchanged.

## 0. The requirement, in business terms
```

<!-- block: docs/specs/SPEC_D6_scrub_span.md | edit -->
```markdown
  (4) The token read's 403 sentence says "the ServiceAccount lacks list permission here" while the reader is the
  person's own login. Wording only.

## 1. The point, in one table
```

```markdown
  (4) The token read's 403 sentence says "the ServiceAccount lacks list permission here" while the reader is the
  person's own login. Wording only.
- **#481 (`docs/specs/SPEC_S4f_fleet_gate_backstop.md`) adds three emit call sites to `gsd/fleetstate.py`**: the
  `fleet-lease-absent` line in `claim()` and in `restore()`, and the copy's `fleet-state-unavailable` in `_keep()`. With
  it applied, `event` and `failure` have 45 call sites in 6 consuming modules. §2.3's 42 is the count at `ece9298`, and
  `tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds this document to the live count.

## 1. The point, in one table
```

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **A deleted fleet Lease is put back from a copy beside the database (#481, Epic C #383,
  `docs/specs/SPEC_S4f_fleet_gate_backstop.md`).** The fleet account's gate and daily-ping instants lived only on its
  Lease, and `crc start` deletes every Lease on the cluster (crc 2.29.0 and later), so after each start a refused or
  locked password was sent once more and the ping ran a second time that day (on the lab on 2026-09-28, at 10:30:01Z
  and 17:57:01Z). Every fleet Lease the dashboard reads or writes is now also kept, entry and ping instants only, in
  `fleet-gate.json` beside `gsd.db`: an absent Lease reads as that copy, the next claim or the leader's next discovery
  puts it back, and `fleet-lease-absent` says so once. Measured in the hermetic harness, one `crc start` cost +1 bind
  and +1 ping on every path before, and +0 after at one replica with persistence on. Independent per-pod copies can
  be stale, so above one replica a deletion can still allow +1 bind or ping. The Lease stays the authority whenever it
  exists, and a copy that
  cannot be read behind an absent Lease, or written at a reservation, binds nothing (`fleet-state-unavailable`).
  SPEC_S4c §5 Q7's clear still re-arms the gate, and `charts/group-sync-dashboard/RUNBOOK.md` section 7 now carries
  it. Not covered, as the operator accepted: persistence off, an etcd restore, a reinstall into another namespace,
  and a clear followed by a `crc start` before any pod had read the cleared Lease (the entry comes back; clear it
  again). No RBAC or schema change.
```
