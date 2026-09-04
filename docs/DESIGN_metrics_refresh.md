# DESIGN — refreshing the Prometheus metrics surface

Status: **design only, nothing applied**. Branch `feat/per-user-visibility`, written 2026-08-10
against commit `3d29e81` plus the uncommitted single-flight TierResolver change in
`gsd/kube.py`. Every snippet below anchors on the code as it stands in this worktree; the
live evidence was taken from the running deployment (image `0.6.0-39f61286b9`) in namespace
`group-sync-dashboard` on the reference cluster.

The shape of the argument, stated once: **a fail-closed control with no metric is
indistinguishable from a broken one.** If the SubjectAccessReview behind per-user visibility
began failing cluster-wide, every reader would silently drop to the narrow view and nothing
would say so — the exact silent-stoppage class this dashboard exists to surface for other
systems. The proposals are ranked by that kind of consequence.

---

## 0. Premise checks — what the brief claimed, and what measurement says

The brief asked for verification rather than trust. Three of its premises needed correcting.

**0.1 — metrics.py is NOT hand-rolled and prometheus_client is NOT a new dependency.**
`local-development/pyproject.toml#prometheus-client` declares `prometheus-client>=0.26.0`, and
`gsd/metrics.py` is built on its custom-collector API (`CollectorRegistry`,
`GaugeMetricFamily`, `CounterMetricFamily`). Nothing below adds any dependency; everything
uses machinery the file already imports. The instruction "preserve the no-dependency state"
is therefore moot — the constraint honoured instead is: **no *new* dependency, and the
existing collector-reads-the-store architecture is preserved, not restructured.**

**0.2 — the retention premise is half right.** The brief says rows are aged out of
`login_event` / `membership_event` / `sync_event`. Measured against every `DELETE FROM` in
`gsd/store.py`: retention exists for **`login_event`** (`prune_login_events`, bounded at
5,000 rows/call, driven from `logincapture._prune`) and **`dashboard_user_activity`**
(`prune_user_activity`, driven from `ActivityRecorder.prune`). **`membership_event` and
`sync_event` have no retention mechanism at all** — they grow forever by design (they are
the irreplaceable history the backup exists for). A metric cannot watch a mechanism that
does not exist, so the retention counter below covers the two real prunes and its label
vocabulary is written to be extended if those tables ever gain one.

*(Extended 2026-09-05: `membership_event` and `sync_event` gained retention in application 0.13.0
— `gsd/poller.py#Poller._prune_history`, `docs/specs/SPEC_B2_history_retention.md` — and
`RETENTION_TABLES` now names all four tables. §10's exclusion is therefore closed by a later
change, not by this one.)*

**0.3 — the coverage gap itself is confirmed.** Live scrape, no credential, from outside
the cluster:

```
$ curl -sk https://group-sync-dashboard.apps-crc.testing/metrics
HTTP 200, 6213 bytes — 16 families, 38 samples
```

and in this worktree:

```
$ grep -c "visibility\|tier\|login\|backup\|retention\|duration" gsd/metrics.py   -> 1
```

(the single hit is the word "duration" in the `collect()` docstring). The visibility
subsystem (`viewer_scope`/`usage_scope` in api.py, `TierResolver` in kube.py), login capture
(`logincapture.py`, ~75 login-related lines in store.py), backup (`Poller._maybe_backup`,
`Store.backup`), retention, poll duration and the admin-tier refusals emit **nothing**.
Today their only signals are pod-log lines — verified live: the last 48 h of the dashboard
log contain 3 `backed up to`/`pruned` lines and the tier-failure path's `log.warning` is the
*only* place a failed SubjectAccessReview is visible at all.

---

## 1. Operator rulings, recorded so they are not re-litigated

**Ruling 1 (2026-08-10) — scraping stays credential-free; the disclosure line is absolute.**
`/metrics` is scrapeable without a credential, by deliberate design, so that a third-party
system can consume it. Verified live: `GET /metrics` from outside the cluster answers
HTTP 200 with no credential, admitted by
`-skip-auth-regex=^/(healthz|readyz|metrics|signed-out|static/(app\.css|favicon\.svg))$`.
The trade, stated plainly: the aggregate counts on this endpoint — group totals, binding
totals by finding class, per-CR sync state — are public to anyone who can reach the route,
and that is accepted in exchange for credential-free third-party scraping.

Consequences for every metric in this document:

* **No metric may carry** a username, an LDAP group name, an LDAP DN, a binding or role
  name, or a namespace that names a team. Aggregate counts and enum-valued labels
  (state, finding class, outcome, severity) are the accepted line.
* The existing `gsd_groupsync_*` labels (`groupsync="ldap-groupsync"`,
  `namespace="group-sync-operator"`) are operator-chosen CR names, ship today, and are the
  precedent **for CR-level labels only** — the precedent is explicitly not extended to
  anything naming a person or an LDAP group.
* There is **no "safe once /metrics is authenticated" bucket.** If a metric is unsafe on a
  world-readable endpoint, it is not emitted, or a safe aggregate is emitted instead.

**Ruling 2 (2026-08-10, same day, arrived in two steps — the final shape below
supersedes the intermediate one).** The operator's final shape, in their words: *"just
using the http for in-cluster prometheus monitoring should be sufficient. the metrics
still goes through https://route_url/metrics but in the in-cluster should be :8080."*
Measured immediately against the live pod, the literal `:8080` is not possible — the app
binds `127.0.0.1` (`http://127.0.0.1:8080/metrics` → 200 from inside the pod;
`http://<pod-ip>:8080/metrics` → connection refused), and *making* 8080 reachable would
mean binding the API app to `0.0.0.0`, which is refused in §7.2 as a total bypass of the
visibility control. So the shape that honours the intent is a **dedicated in-pod plaintext
listener for in-cluster Prometheus**, §7:

* in-cluster Prometheus → `http://<pod-ip>:<metricsPort>/metrics`, plain HTTP, served by a
  metrics-only app;
* third-party scrapers → `https://<route>/metrics`, **unchanged**, still through the proxy;
* the API → `127.0.0.1:8080`, unchanged.

Two arguments were weighed on the way here and the doc must keep them straight:

* The **load argument does not hold** and must not be used to justify the change: this is
  one process (`--workers 1`, one uvicorn event loop — measured on the live pod). A second
  listener separates *addressing*, not *capacity*; real isolation would need a second
  process or more workers, and more workers fights the SQLite single-writer design the
  chart already defends (it refuses RollingUpdate at `replicaCount: 1` with persistence).
* An intermediate version of this ruling justified the listener as "delete the `metrics`
  entry from `oauthProxy.skipAuthRegex` and shrink the app's unauthenticated surface."
  **Under the final shape that benefit is NOT collected and must not be claimed**: the
  Route path still serves `/metrics` through the proxy, so the regex entry **stays**. The
  actual benefit is different and smaller, and §7.1 states it as exactly what it is.

The disclosure rule of Ruling 1 is unchanged by Ruling 2: both listeners are
credential-free, so everything in this document is written for a world-readable endpoint
regardless of which port serves it.

---

## 2. Where the new numbers come from — state vs events

`metrics.py`'s architecture is: **a collector that reads the store at scrape time**, because
"the store is already the source of truth, so mirroring it into metric objects would create
a second copy that can drift from the first." That reasoning covers *state*. Three of the
proposals below are state and follow it unchanged (capture last-read, backup last-success,
capture enabled — each read from the store, the filesystem, or Settings at scrape time).

The rest are **events**: a tier check that failed, a 403 the admin gate issued, rows a prune
deleted, a backup that did not happen. No store row records these — the event's only
existence is the moment it happens in this process — so a process-local counter is the
*single* copy, not a second one. The doctrine's drift argument does not apply where there is
no first copy to drift from.

The seam is one small class, `RuntimeSignals`, created per app in `build_app` (never at
module level: "tests build several apps in one interpreter" is why `build_registry` already
uses a dedicated registry) and handed to the code paths that observe events. The collector
reads a lock-guarded snapshot of it at scrape time.

Multi-replica semantics, stated in HELP text where it matters: these counters are
**per replica**. Prometheus's `pod` target label keeps replicas apart and `sum()` is the
correct aggregation — unlike the store-backed gauges, which are cluster facts where `sum()`
double-counts (the existing `gsd_leader` comment). Counters reset on pod restart like every
Prometheus counter; `rate()`/`increase()` absorb that.

Two collector disciplines carried over from the existing code:

* **Every family is always declared** (HELP/TYPE emitted even with zero samples — verified
  against prometheus_client 0.26: a sample-less family still renders its HELP line). This is
  what lets `test_every_metric_an_alert_references_is_declared_by_the_collector` keep
  holding every PrometheusRule expression to a declared metric, including the new rules
  in §8.
* **Enum label sets are pre-seeded to 0** when the signals object is wired (the
  `dict.fromkeys(FINDINGS, 0)` pattern already in the file). A counter that first appears
  at value 1 gives `increase()` no baseline, and the entire point of the failure counters
  is catching the *first* failure.

### 2.1 The shared plumbing (one block, referenced by every proposal)

**`gsd/metrics.py`** — add near the existing `STATES` / `FINDINGS` vocabulary:

```python
import threading
from pathlib import Path

# Vocabularies for the process-event families. Fixed tuples, like STATES and FINDINGS:
# every combination is pre-seeded to 0 so increase() has a baseline before the first event,
# and a typo'd label value fails loudly in tests instead of minting a new series.
TIER_THRESHOLDS = ("admin", "usage")
TIER_CHECK_OUTCOMES = ("allowed", "denied", "unreachable", "auth_failed", "forbidden", "error")
TIERS = ("all", "self")
RETENTION_TABLES = ("login_event", "dashboard_user_activity")


class RuntimeSignals:
    """Process-local counters for events that exist in no table.

    The module docstring's rule — read the store, never mirror it — is about STATE, which
    has a first copy to drift from. These are EVENTS: a tier check that failed, rows a
    prune deleted, a backup that did not happen. No store row records them, so the process
    counter IS the single copy. Per replica by construction: sum() across pods is the
    correct aggregation, unlike the store-backed gauges (see the gsd_leader comment), and
    a restart resets them the way Prometheus counters are allowed to reset.

    Explicit note_* methods rather than a generic inc(name, labels): the call sites are
    then greppable, typo-proof, and each one documents which vocabulary it draws from.
    Never raises — a metrics bug must not become an application bug.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tier_checks: dict[tuple[str, str], int] = {}
        self._decisions: dict[tuple[str, str], int] = {}
        self._admin_refusals = 0
        self._retention: dict[str, int] = {}
        self._backup_failures = 0
        self._poll_seconds: dict[str, float] = {}

    def note_tier_check(self, threshold: str, outcome: str) -> None:
        with self._lock:
            key = (threshold, outcome)
            self._tier_checks[key] = self._tier_checks.get(key, 0) + 1

    def note_decision(self, threshold: str, tier: str) -> None:
        with self._lock:
            key = (threshold, tier)
            self._decisions[key] = self._decisions.get(key, 0) + 1

    def note_admin_refusal(self) -> None:
        with self._lock:
            self._admin_refusals += 1

    def note_retention(self, table: str, rows: int) -> None:
        if rows <= 0:
            return
        with self._lock:
            self._retention[table] = self._retention.get(table, 0) + rows

    def note_backup_failure(self) -> None:
        with self._lock:
            self._backup_failures += 1

    def note_poll_duration(self, cluster: str, seconds: float) -> None:
        with self._lock:
            self._poll_seconds[cluster] = seconds

    def snapshot(self) -> dict:
        """One consistent copy for the collector — a scrape never reads a half-updated dict."""
        with self._lock:
            return {
                "tier_checks": dict(self._tier_checks),
                "decisions": dict(self._decisions),
                "admin_refusals": self._admin_refusals,
                "retention": dict(self._retention),
                "backup_failures": self._backup_failures,
                "poll_seconds": dict(self._poll_seconds),
            }
```

**`DashboardCollector` and `build_registry` grow two optional parameters** (every existing
caller keeps working):

```python
class DashboardCollector:
    """Reads the store on each scrape and yields the current picture."""

    def __init__(self, store: StorageBackend, grace: timedelta, elector=None,
                 signals: "RuntimeSignals | None" = None, settings=None):
        self.store = store
        self.grace = grace
        self.elector = elector
        # The process-event seam (§2 of docs/DESIGN_metrics_refresh.md) and the Settings
        # object, both optional: a collector built without them declares the new families
        # empty, which keeps the alert-rule parity test meaningful on a bare store.
        self.signals = signals
        self.settings = settings
```

```python
def build_registry(store: StorageBackend, grace: timedelta, elector=None,
                   signals=None, settings=None) -> CollectorRegistry:
    """A dedicated registry — the default one carries process/GC collectors we do not want
    duplicated per app instance, and tests build several apps in one interpreter."""
    registry = CollectorRegistry()
    registry.register(DashboardCollector(store, grace, elector,
                                         signals=signals, settings=settings))
    return registry
```

At the end of `_gather` (after the existing final `yield from (...)` tuple):

```python
        yield from self._event_families()
```

and the new generator method on the collector — the concrete families it emits are given
per metric in §3, assembled here once:

```python
    def _event_families(self):
        """Families whose source is the process or the filesystem, not the store.

        Always DECLARED (HELP/TYPE), even when there is nothing to say: the alert-parity
        test in tests/test_metrics.py holds every PrometheusRule expression to a declared
        family, and a family that only exists after its first event would make a rule on
        it unverifiable. Samples are added only when the corresponding source is wired,
        so a bare DashboardCollector(store, grace) claims no measurements it never took.
        """
        snap = self.signals.snapshot() if self.signals is not None else None

        checks = CounterMetricFamily(
            "gsd_visibility_tier_checks_total",
            "Fresh SubjectAccessReview-backed tier resolutions, by threshold and outcome. "
            "allowed/denied are verdicts; every other outcome is a check that FAILED and "
            "served the self view fail-closed — a sustained nonzero rate means readers "
            "are being silently narrowed. Cache hits are not re-decided and single-flight "
            "followers ride the leader's check, so this counts decisions, not requests. "
            "Per replica: aggregate with sum().",
            labels=["threshold", "outcome"],
        )
        decisions = CounterMetricFamily(
            "gsd_visibility_decisions_total",
            "Scope decisions actually served to requests while view restrictions are on, "
            "by threshold and tier — cached, fresh, and no-identity decisions alike. The "
            "all:self mix shifting toward self while tier_checks reports failures is the "
            "everyone-silently-narrowed signature. Per replica: aggregate with sum().",
            labels=["threshold", "tier"],
        )
        refusals = CounterMetricFamily(
            "gsd_visibility_admin_refusals_total",
            "Requests refused (403) by the administrator-tier gate on the cluster-scoped "
            "views (/bindings/findings, /operator-configs). Occasional is a non-admin "
            "clicking a tab; a step change across every viewer alongside tier-check "
            "failures means the gate itself lost its answer. Per replica: sum().",
            labels=[],
        )
        retention = CounterMetricFamily(
            "gsd_retention_rows_deleted_total",
            "Rows removed by retention, by table. login_event deletes are bounded at "
            "5000/cycle, so a rate pinned at that ceiling means the backlog is not "
            "draining. Only tables with a retention mechanism appear; membership_event "
            "and sync_event deliberately have none. Per replica (leader): sum().",
            labels=["table"],
        )
        backup_failures = CounterMetricFamily(
            "gsd_backup_failures_total",
            "Backup attempts that failed (VACUUM INTO error or unwritable backupDir). "
            "Pair with gsd_backup_last_success_timestamp_seconds: failures say it is "
            "breaking, the timestamp says how stale the last good copy already is.",
            labels=[],
        )
        poll_duration = GaugeMetricFamily(
            "gsd_cluster_poll_duration_seconds",
            "Wall time of the most recent poll of this cluster, successful or not. "
            "Emitted by the replica that polls (the leader); compare against "
            "pollIntervalSeconds and the request timeout — a rising duration under a "
            "green gsd_cluster_up is the slow-but-succeeding poll that the timestamp "
            "metrics cannot show.",
            labels=["cluster"],
        )

        if snap is not None:
            for threshold in TIER_THRESHOLDS:
                for outcome in TIER_CHECK_OUTCOMES:
                    checks.add_metric(
                        [threshold, outcome],
                        snap["tier_checks"].get((threshold, outcome), 0))
                for tier in TIERS:
                    decisions.add_metric(
                        [threshold, tier], snap["decisions"].get((threshold, tier), 0))
            refusals.add_metric([], snap["admin_refusals"])
            for table in RETENTION_TABLES:
                retention.add_metric([table], snap["retention"].get(table, 0))
            backup_failures.add_metric([], snap["backup_failures"])
            for cluster, seconds in sorted(snap["poll_seconds"].items()):
                poll_duration.add_metric([cluster], seconds)

        yield from (checks, decisions, refusals, retention, backup_failures, poll_duration)

        capture_enabled = GaugeMetricFamily(
            "gsd_login_capture_enabled",
            "1 when login capture is configured on. While this is 1, absence of "
            "gsd_login_capture_last_read_timestamp_seconds means capture has never once "
            "succeeded — a different failure from capture going stale.",
            labels=[],
        )
        if self.settings is not None:
            capture_enabled.add_metric([], 1 if self.settings.login_capture_enabled else 0)
        yield capture_enabled

        backup_ts = GaugeMetricFamily(
            "gsd_backup_last_success_timestamp_seconds",
            "Modification time of the newest backup file in backupDir. Read from the "
            "files rather than remembered from the last attempt, so it survives restarts "
            "and catches every failure shape, including a misconfigured directory. "
            "Absent when backups are disabled or none exists yet.",
            labels=[],
        )
        if self.settings is not None and self.settings.backup_dir:
            try:
                newest = max(
                    (p.stat().st_mtime
                     for p in Path(self.settings.backup_dir).glob("gsd-*.db")),
                    default=None,
                )
            except OSError:
                # OMITTED, never zeroed — the health() rule above: a failure to measure
                # must not read as a measurement of failure. Epoch 0 here would fire the
                # staleness alert while the backups may be perfectly fine.
                newest = None
            if newest is not None:
                backup_ts.add_metric([], newest)
        yield backup_ts
```

(`gsd_login_capture_last_read_timestamp_seconds` is store-backed and per-cluster, so it is
declared beside the other per-cluster families in `_gather` and filled inside the existing
cluster loop — snippet in §3.4.)

---

## 3. Proposed metrics — nine, ranked by operational consequence

Summary table; each row is expanded below with the 3 a.m. question, the increment site with
its complete snippet, computed cardinality, the disclosure verdict, and a test in the
`tests/test_metrics.py` style.

| # | Metric | Type | Labels | Priority |
|---|--------|------|--------|----------|
| 1 | `gsd_visibility_tier_checks_total` | counter | `threshold`, `outcome` | P1 — the fail-closed control |
| 2 | `gsd_visibility_decisions_total` | counter | `threshold`, `tier` | P1 |
| 3 | `gsd_visibility_admin_refusals_total` | counter | — | P1 |
| 4 | `gsd_login_capture_last_read_timestamp_seconds` | gauge | `cluster` | P2 — silent machinery stoppage |
| 5 | `gsd_backup_last_success_timestamp_seconds` | gauge | — | P2 |
| 6 | `gsd_backup_failures_total` | counter | — | P2 |
| 7 | `gsd_cluster_poll_duration_seconds` | gauge | `cluster` | P2 |
| 8 | `gsd_retention_rows_deleted_total` | counter | `table` | P3 — housekeeping |
| 9 | `gsd_login_capture_enabled` | gauge | — | P3 |

### 3.1 `gsd_visibility_tier_checks_total{threshold, outcome}` — counter

**The question it answers that nothing can today:** *"Every reader is suddenly seeing only
their own data — is the SubjectAccessReview machinery failing, and how: API server
unreachable, the ServiceAccount's token rejected, or someone stripped the auth-delegator
grant?"* Today the only evidence is a per-failed-check `log.warning` in the pod log
(`gsd/kube.py#TierResolver._resolve_and_cache`); measured over the last 48 h of the live
pod there are zero such lines — and zero is exactly what a broken *and* a healthy control
both look like from outside.

**Label vocabulary, all enums:** `threshold` ∈ {`admin`, `usage`} — the two independent
`TierResolver` instances (`docs/SPEC_per_user_visibility.md`,
`docs/SPEC_usage_admin_tier.md`). `outcome` ∈ {`allowed`, `denied`} (clean verdicts) ∪
{`unreachable`, `auth_failed`, `forbidden`} (the `ClusterError.outcome` values kube.py
already uses — `gsd/kube.py#AUTH_FAILED` and friends) ∪ {`error`} (the catch-all `except Exception` branch).
Every non-verdict outcome means one thing: **a reader was served the self view because the
check failed, not because they were denied.**

**Where — `gsd/kube.py`, `TierResolver`.** The resolver is the only place the *cause* is
known, and since the single-flight change the fresh check happens exactly once per
viewer-per-TTL in `_resolve_and_cache` — so instrumenting there counts *decisions*, not
request fan-out (a burst of seven followers riding one failed leader is one failure, not
seven). kube.py must not import metrics.py (it is cluster I/O, buildable without the app),
so the wiring is a callback, injected by `build_app`:

```python
    # __init__ signature — one new keyword, after ttl_seconds:
    def __init__(
        self,
        cluster: ClusterConfig,
        *,
        verb: str,
        resource: str,
        api_group: str = "",
        namespace: str = "",
        subresource: str,
        ttl_seconds: float,
        observe: "Callable[[str], None] | None" = None,
    ):
        ...
        # Observability callback, not a metrics import: kube.py stays buildable and
        # testable without the metrics module, and the app wires the two at build time.
        self._observe = observe
```

```python
    def _note(self, outcome: str) -> None:
        # Best-effort by contract: the tier is already decided by the time this runs, and
        # a metrics bug must never break a security decision or un-fail-closed anything.
        if self._observe is None:
            return
        try:
            self._observe(outcome)
        except Exception:  # noqa: BLE001
            log.exception("visibility tier metrics callback failed; the tier is unaffected")
```

and in `_resolve_and_cache`, one line per existing branch (current code shown for
anchoring):

```python
        except ClusterError as exc:
            # ... existing log.warning unchanged ...
            self._note(exc.outcome)          # unreachable | auth_failed | forbidden
            return TIER_SELF
        except Exception:
            # ... existing log.exception unchanged ...
            self._note("error")
            return TIER_SELF
        tier = TIER_ALL if allowed else TIER_SELF
        self._note("allowed" if allowed else "denied")
```

Deliberately **not** instrumented: the follower fail-closed path in `tier_for` (the leader
already noted the failure once) and the cache-hit path (a hit is not a decision; the served
mix is metric #2's job).

**Wiring in `gsd/api.py` `build_app`** (`functools` is already imported):

```python
    from .metrics import RuntimeSignals, build_registry   # RuntimeSignals joins the import

    signals = RuntimeSignals()          # before the resolvers are constructed

    ...
        resolver = TierResolver(
            local_cluster,
            verb=settings.visibility_admin_sar_verb,
            ...
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "admin"),
        )
    ...
        usage_resolver = TierResolver(
            local_cluster,
            ...
            observe=functools.partial(signals.note_tier_check, "usage"),
        )
    ...
    metrics_registry = build_registry(store, grace, elector,
                                      signals=signals, settings=settings)
```

(A test-injected `tier_resolver` callable bypasses the resolver and therefore the counter —
correct, since an injected callable *is* the decision and measures nothing real.)

**Cardinality, computed:** 2 thresholds × 6 outcomes = **12 series**, constant — independent
of users (62 on the reference directory, thousands in production), groups (65), and
clusters. Pre-seeded to 0.

**Disclosure (world-readable):** outcome counts only. What it reveals: that a visibility
feature exists (already public — `gsd_groupsync_state` reveals the operator; the chart is
public) and roughly how often admins vs non-admins are *checked* — not who, not when
per-person, not from where. Within the aggregate/enum line. A `viewer` label is rejected in
§4.1.

**Test** (`tests/test_metrics.py` style — note prometheus_client serialises labels
alphabetically, so `outcome` precedes `threshold` in the sample keys; verified against the
venv's prometheus_client):

```python
class TestVisibilitySignals:
    def test_tier_check_outcomes_are_counted_and_pre_seeded(self):
        """A counter that first appears at 1 gives increase() no baseline; the whole point
        is catching the FIRST failure, so every enum combination exists at 0."""
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_tier_check("admin", "forbidden")
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_visibility_tier_checks_total")
        assert found[
            'gsd_visibility_tier_checks_total{outcome="forbidden",threshold="admin"}'] == 1
        assert found[
            'gsd_visibility_tier_checks_total{outcome="unreachable",threshold="usage"}'] == 0
        assert len(found) == 12, "2 thresholds x 6 outcomes, nothing else"

    def test_event_families_are_declared_even_unwired(self):
        """The alert-parity test resolves rules against HELP lines, so the families must
        exist on a bare collector — declared empty, claiming no measurements."""
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        assert "# HELP gsd_visibility_tier_checks_total" in text
        assert series(text, "gsd_visibility_tier_checks_total") == {}
```

A second test belongs in `tests/test_visibility_tier.py`, where the `FakeCluster` machinery
lives: resolve once against a fake answering 403 on the SAR path with
`observe=recorder.append`, and assert exactly `["forbidden"]` — one note for a burst of
followers (the single-flight class already builds that burst).

### 3.2 `gsd_visibility_decisions_total{threshold, tier}` — counter

**The question:** *"What view mix is actually being served right now — did the wide-tier
population drop to zero at 03:12, and does that line up with a deploy, an RBAC change, or
tier-check failures?"* Metric #1 sees only *fresh* checks; this one counts every scope
decision served while restrictions are on — cached verdicts, no-identity refusals-to-widen,
and the not-wired-resolver path included. #1 is the cause; this is the effect. The
silent-narrowing signature is: `decisions{tier="all"}` rate falls to zero while
`tier_checks{outcome=~"unreachable|auth_failed|forbidden|error"}` rises.

**Where — `gsd/api.py`, `viewer_scope` and `usage_scope`.** Both are closures over
`signals`. Anchored on the current code, `viewer_scope` becomes:

```python
    def viewer_scope(request: Request) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope). The failure direction IS the control.
        ... existing docstring unchanged ...
        """
        viewer = trusted_viewer(request)
        if not restrict:
            # Deliberately uncounted: with restrictions off there is no decision being
            # made, and counting a permanent "all" would drown the signal this exists for.
            return viewer, "all"
        state_resolver = getattr(app.state, "tier_resolver", None)
        if not viewer or (state_resolver is None and tier_resolver is None):
            signals.note_decision("admin", "self")
            return viewer, "self"
        try:
            tier = (state_resolver.resolve(viewer) if state_resolver is not None
                    else tier_resolver(viewer))
        except Exception:  # noqa: BLE001
            log.exception("tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("admin", "self")
            return viewer, "self"
        scope = "all" if tier == "all" else "self"
        signals.note_decision("admin", scope)
        return viewer, scope
```

`usage_scope` mirrors it with `"usage"`, counting after its `if not restrict` guard for the
same reason (the `userActivity.visibility == "all"` blunt override *is* counted — it is a
served wide decision, and a deployment that sets it should see that fact on the graph):

```python
        if settings.user_activity_visibility == "all":
            signals.note_decision("usage", "all")
            return viewer, "all"
        if not restrict:
            return viewer, "self"          # no tier machinery ran; uncounted, as above
        state_resolver = getattr(app.state, "usage_tier_resolver", None)
        if not viewer or (state_resolver is None and usage_tier_resolver is None):
            signals.note_decision("usage", "self")
            return viewer, "self"
        try:
            tier = (state_resolver.resolve(viewer) if state_resolver is not None
                    else usage_tier_resolver(viewer))
        except Exception:  # noqa: BLE001
            log.exception("usage tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("usage", "self")
            return viewer, "self"
        scope = "all" if tier == "all" else "self"
        signals.note_decision("usage", scope)
        return viewer, scope
```

One request can be counted more than once (`whoami` consults `viewer_scope`, so does
`require_admin_tier`) — the HELP text says "decisions served", not "requests", and the
ratio is what the graph is for.

**Cardinality:** 2 × 2 = **4 series**, constant. Pre-seeded.

**Disclosure:** the all:self ratio reveals, in aggregate, how much of the traffic is
admin-tier. No identity, no timing per person. Within the line.

**Test:**

```python
    def test_decisions_count_what_was_served(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_decision("admin", "self")
        signals.note_decision("admin", "self")
        signals.note_decision("usage", "all")
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_visibility_decisions_total")
        assert found['gsd_visibility_decisions_total{threshold="admin",tier="self"}'] == 2
        assert found['gsd_visibility_decisions_total{threshold="usage",tier="all"}'] == 1
        assert found['gsd_visibility_decisions_total{threshold="usage",tier="self"}'] == 0
```

An end-to-end variant belongs in `tests/test_visibility.py` (it owns the `_MapResolver`
seam): serve one request at each tier through the TestClient and assert the two series off
the app's own `/metrics`.

### 3.3 `gsd_visibility_admin_refusals_total` — counter, no labels

**The question:** *"The RBAC and policy tabs started 403ing — is that one curious non-admin
clicking around, or did every administrator just lose the wide tier at once?"* A step change
in this counter across all viewers, correlated with #1's failure outcomes, distinguishes
"the gate is refusing correctly" from "the gate lost its ability to answer". It also gives
the security-review answer to "is anyone probing the admin endpoints?" — today a refused
probe leaves no trace anywhere (the 403 body is served and nothing is logged).

**Where — `gsd/api.py`, `require_admin_tier`**, immediately before the raise:

```python
    def require_admin_tier(request: Request) -> str:
        """... existing docstring unchanged ..."""
        _, scope = viewer_scope(request)
        if scope != "all":
            # Counted before the raise: a refusal that leaves no trace anywhere is how a
            # gate that broke for everyone stays indistinguishable from one nobody hit.
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="this view reports the cluster's own RBAC binding surface and operator "
                       "configuration rather than anything belonging to the reader, so it is "
                       "reserved to the administrator tier",
            )
        return scope
```

No `endpoint` label: only two views sit behind the gate today and both are refused by the
same decision, so a label would split one signal into two identical ones. Add the label
only if gated views with *different* thresholds ever exist.

**Cardinality:** **1 series.** **Disclosure:** an aggregate refusal count; reveals that
gated views exist (already in the public chart) and how often they are refused. Fine.

**Test** (in `tests/test_visibility.py`, which owns the app fixture with the
`_MapResolver` seam):

```python
    def test_admin_refusals_are_counted_on_the_metric(self, client):
        before = _refusals(client.get("/metrics").text)
        r = client.get("/api/clusters/crc/bindings/findings",
                       headers={"x-forwarded-user": "ordinary.reader"})
        assert r.status_code == 403
        assert _refusals(client.get("/metrics").text) == before + 1
```

### 3.4 `gsd_login_capture_last_read_timestamp_seconds{cluster}` — gauge

**The question:** *"The Logins page has shown nothing new since Tuesday — did people stop
logging in, or did capture silently stop reading?"* Capture has at least four independent
silent-stop modes, each leaving the API healthy and the page quietly frozen: the RBAC grant
for pod logs revoked (`fetch_oauth_pods` returns None — logged at INFO), the oauth pods
unreadable, the operator's `logLevel: Debug` reverted (reads succeed, find nothing — this
one *does* advance the timestamp, correctly: capture is alive, the *log* went quiet), and
the leader thread dying. The store already records exactly the right fact —
`login_capture_status.last_read_at`, advanced only by a successful read
(`gsd/store.py#Store.record_login_read`) — and the API already ships it to the *browser* with an explicit
apology that only the browser can judge staleness (`api.py`, `read_interval_seconds`).
Prometheus can judge it too; it just was never given the number.

**Where — `gsd/metrics.py` `_gather`**, store-backed, inside the existing per-cluster loop
(so it rides the same read snapshot). Declared with the other per-cluster families:

```python
        capture_last_read = GaugeMetricFamily(
            "gsd_login_capture_last_read_timestamp_seconds",
            "Unix time of the last successful oauth-log read for this cluster; advanced "
            "only by a read that reached at least one pod. Alert on staleness against "
            "pollIntervalSeconds — capture rides the poll thread. Absent until the first "
            "successful read: absence means never, not zero.",
            labels=["cluster"],
        )
```

inside the loop, beside the existing `last_poll` handling:

```python
                status = self.store.login_capture_status(cluster)
                read_ts = _epoch((status or {}).get("last_read_at"))
                if read_ts is not None:
                    capture_last_read.add_metric([cluster], read_ts)
```

and added to the final `yield from (...)` tuple. (`login_capture_status` is already on the
`StorageBackend` protocol — `gsd/storage.py#StorageBackend.login_capture_status` — so no
protocol change.)

**Cardinality:** ≤ 1 per cluster (**1** on the reference deployment).
**Disclosure:** a timestamp about the capture *machinery*, not about any person's login.
Fine. (What is *not* proposed for this subsystem matters more — §4.2.)

**Test:**

```python
class TestCaptureAndBackupTimestamps:
    def test_capture_last_read_is_absent_until_recorded_then_a_timestamp(self):
        store = Store(":memory:")
        try:
            store.upsert_cluster("crc", "https://x", True)
            store.record_poll("crc", "ok", None)
            text = generate_latest(build_registry(store, GRACE)).decode()
            assert "gsd_login_capture_last_read_timestamp_seconds{" not in text
            store.record_login_read("crc", "2026-08-10T12:00:00Z")
            text = generate_latest(build_registry(store, GRACE)).decode()
            assert series(text, "gsd_login_capture_last_read_timestamp_seconds")[
                'gsd_login_capture_last_read_timestamp_seconds{cluster="crc"}'
            ] > 1_700_000_000
        finally:
            store.close()
```

### 3.5 `gsd_backup_last_success_timestamp_seconds` — gauge

**The question:** *"The PVC just corrupted. How old is the copy I am about to restore — and
had backup silently stopped weeks ago?"* Backup is the only protection for the one
irreplaceable dataset (`gsd/store.py#Store.backup` calls it "THE ONLY EXISTENTIAL RISK IN THIS SYSTEM"),
it fails soft by design ("a failed backup must never stop the poll"), and its only current
signal is a log line. Verified live: `/data/backup` holds four `gsd-*.db` files, 6 h apart,
`backupKeep: 4` working — and nothing anywhere would say so, or say otherwise.

**Where — the collector, from the filesystem** (snippet already in §2.1's
`_event_families`). Reading the *files* rather than remembering the last attempt is
deliberate: it survives restarts, and it measures the artifact a restore would actually
use — a "successful attempt" gauge would read healthy while `backupKeep` rotation, a wrong
directory, or an emptied PVC left nothing restorable. Omitted (never zeroed) when the
directory is unreadable, per the existing `health()` discipline.

**Cardinality:** **1 series** (absent when `backupDir` is unset).
**Disclosure:** a timestamp. Fine.

**Test:**

```python
    def test_backup_timestamp_reads_the_newest_file(self, tmp_path):
        from types import SimpleNamespace
        (tmp_path / "gsd-20260810T000000.000000Z.db").write_bytes(b"x")
        settings = SimpleNamespace(backup_dir=str(tmp_path), login_capture_enabled=False)
        store = Store(":memory:")
        try:
            text = generate_latest(
                build_registry(store, GRACE, settings=settings)).decode()
        finally:
            store.close()
        value = series(text, "gsd_backup_last_success_timestamp_seconds")[
            "gsd_backup_last_success_timestamp_seconds"]
        assert abs(value - (tmp_path / "gsd-20260810T000000.000000Z.db").stat().st_mtime) < 1
```

### 3.6 `gsd_backup_failures_total` — counter

**The question:** *"Is backup failing right now?"* — hours before #5's staleness threshold
would say so (interval is 6 h; two missed backups is half a day of exposure on the dataset
that cannot be re-fetched).

**Where — `gsd/poller.py`, `Poller._maybe_backup`.** `Poller.__init__` gains
`signals: RuntimeSignals | None = None` (stored as `self.signals`), wired from `build_app`
as `Poller(store, settings, elector, signals=signals)`. The method body becomes:

```python
        self._next_backup = now + self.settings.backup_interval_hours * 3600
        try:
            if self.store.backup(self.settings.backup_dir,
                                 keep=self.settings.backup_keep) is None:
                # None is the method's own failure contract (VACUUM error, unwritable
                # directory) — already logged with the trace in the store; counted here,
                # where the schedule lives. The :memory: engine also returns None, but a
                # production deployment with backupDir set is never :memory:.
                if self.signals is not None:
                    self.signals.note_backup_failure()
        except Exception:  # noqa: BLE001 - a failed backup must never stop the poll
            if self.signals is not None:
                self.signals.note_backup_failure()
            log.exception("backup failed; the poll continues and the history is unprotected")
```

**Cardinality:** **1 series.** **Disclosure:** a failure count. Fine.

**Test:** unit-level, against the signals object plus a store whose `backup` is stubbed to
return `None`, asserting the counter reads 1 after one `_maybe_backup` pass — the pattern
`tests/test_backup.py` already uses for the schedule.

### 3.7 `gsd_cluster_poll_duration_seconds{cluster}` — gauge

**The question:** *"Polls still succeed and the timestamp still advances — but is each poll
now taking 500 of its 900 seconds, quietly creeping toward the timeout it will eventually
hit?"* `gsd_cluster_last_poll_timestamp_seconds` proves the loop is alive; nothing measures
how close it is to not being. The poller already computes a cycle `elapsed` for a DEBUG log
line at the end of `gsd/poller.py#Poller._run_cluster` — the number exists and is thrown
away.

**Type argument:** a gauge of the last duration, not a histogram. Polls happen once per
`pollIntervalSeconds` (60 s live, up to 900 s in other deployments) per cluster — at most
one new observation per scrape, so bucketed percentiles over a hand-maintained
custom-collector histogram add plumbing for a series whose every point Prometheus already
sees individually. `max_over_time()` gives the worst case; the trend is the signal.

**Where — `gsd/poller.py`, `Poller._run_cluster`**, wrapped around `poll_once` (which
returns degraded outcomes rather than raising, so failures are timed too — a poll that
takes the full timeout to fail is precisely the interesting one):

```python
            try:
                poll_started = time.monotonic()
                poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                          access_group_dn=self.settings.cluster_access_group)
                if self.signals is not None:
                    # The whole poll, success or degraded — a poll that needs the full
                    # timeout to fail is the one worth seeing. Set only by the replica
                    # that polls, so standbys emit no series and sum() stays honest.
                    self.signals.note_poll_duration(
                        cluster.name, time.monotonic() - poll_started)
```

(The remainder of the `try` block — capture, maintain, backup — is unchanged and
deliberately outside the measurement: this metric answers for the *cluster poll*, and
capture/backup have their own metrics above.)

**Cardinality:** 1 per polled cluster (**1** live). **Disclosure:** a duration. Fine.

**Test:**

```python
    def test_poll_duration_is_exported_per_cluster(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_poll_duration("crc", 1.42)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        assert series(text, "gsd_cluster_poll_duration_seconds")[
            'gsd_cluster_poll_duration_seconds{cluster="crc"}'] == pytest.approx(1.42)
```

### 3.8 `gsd_retention_rows_deleted_total{table}` — counter

**The question:** *"The PVC keeps growing — is retention actually deleting anything? And is
the bounded prune keeping up, or pinned at its 5,000-row ceiling every cycle while the
backlog grows?"* Saturation is the designed-in failure mode (`gsd/store.py#Store.prune_login_events`: "a return of
`max_rows` means backlog remains"), and it is currently observable only by reading INFO
logs cycle after cycle.

**Where — the two real prune sites (§0.2).** `gsd/logincapture.py`: `capture_once` gains a
trailing `signals=None` parameter, passed through to `_prune` (duck-typed — logincapture
imports nothing from metrics):

```python
def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
    signals=None,
) -> int:
    ...
    _prune(store, cluster, settings, elector, signals)
    return recorded


def _prune(store, cluster, settings, elector=None, signals=None) -> None:
    ...
    removed = store.prune_login_events(cluster.name, before)
    if removed:
        if signals is not None:
            # note_retention never raises — see RuntimeSignals — so no guard beyond None.
            signals.note_retention("login_event", removed)
        log.info("%s: pruned %d login event(s) older than %s", cluster.name, removed, before)
```

with the call site in `gsd/poller.py#Poller._run_cluster` becoming:

```python
                    capture_once(self.store, cluster, self.settings, self.elector,
                                 self.settings.request_timeout_seconds,
                                 signals=self.signals)
```

`gsd/activity.py`: `ActivityRecorder.__init__` gains `signals=None` (stored), wired from
`build_app`; `prune()` notes the same way:

```python
        removed = self.store.prune_user_activity(before)
        if removed:
            if self.signals is not None:
                self.signals.note_retention("dashboard_user_activity", removed)
            log.info("pruned %d dashboard-activity row(s) older than %s", removed, before)
```

**Cardinality:** **2 series** (`RETENTION_TABLES`), pre-seeded; grows only if a table gains
a retention mechanism, which is a code change that would extend the tuple.

**Disclosure — the one in this set that needed actual judgement.** The deletion rate for
`login_event` is a proxy for login volume *lagged by `loginRetentionDays` (400 days)* and
smeared by the 5,000-row bound. The precedent that removed `gsd_dashboard_active_users`
(the `gsd_dashboard_active_users` comment in `gsd/metrics.py#DashboardCollector._gather`)
rejected a *same-day, per-day distinct-person count*; this is a
year-old, mixed, bounded deletion total with no per-person resolution. It sits inside the
aggregate line the operator ruled acceptable, and the operational value (the PVC-growth
question) is real. Verdict: emit. If even the lagged volume proxy is unwanted, the
alternative is dropping only the `login_event` label value — recorded here so the future
discussion starts from the trade, not from scratch.

**Test:**

```python
    def test_retention_deletions_are_counted_by_table(self):
        from gsd.metrics import RuntimeSignals
        signals = RuntimeSignals()
        signals.note_retention("login_event", 5000)
        signals.note_retention("login_event", 137)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, signals=signals)).decode()
        finally:
            store.close()
        found = series(text, "gsd_retention_rows_deleted_total")
        assert found['gsd_retention_rows_deleted_total{table="login_event"}'] == 5137
        assert found['gsd_retention_rows_deleted_total{table="dashboard_user_activity"}'] == 0
```

### 3.9 `gsd_login_capture_enabled` — gauge (0/1)

**The question:** *"#4 has no series for this cluster — is capture broken, or was it never
turned on?"* Absence must be interpretable, and a config bit is the cheapest disambiguator.
Emission is in §2.1 (`self.settings.login_capture_enabled`).

**Cardinality:** **1 series** (unlabelled — the setting is global, not per cluster; a
`cluster` label would claim a per-cluster fact the config cannot express).

**Disclosure:** this announces to an anonymous reader that login attempts are being
recorded. Weighed: the chart and its documentation are public, the oauth-loglevel Jobs that
enable it are visible to any authenticated cluster user, and monitoring that is known to
exist is a deterrent rather than a leak. Verdict: emit. (Contrast with
`gsd_visibility_restrictions_enabled`, which is *rejected* — §4.5 — because that bit is
pure attacker value.)

**Test:** build the registry with `SimpleNamespace(backup_dir="", login_capture_enabled=True)`
and assert `gsd_login_capture_enabled 1.0`; with a bare registry (no settings) assert the
family is declared with no sample.

---

## 4. Rejected metrics — written down so the next contributor does not reach for them

**4.1 Any `viewer`/username label — rejected twice over.** It is the obvious extension
("which admin's checks are failing?") and it is wrong in two independent ways:
*cardinality* — one series per authenticated human, 62 Users on the reference directory,
thousands on production AD, per threshold, per outcome — and *disclosure* — usernames on a
world-readable endpoint, which Ruling 1 forbids absolutely. The per-person answer lives in
the pod log (`kube.py` logs the viewer on every indeterminate check), which is where
identity-carrying diagnostics belong: behind cluster RBAC.

**4.2 Login outcome/volume aggregates** (`gsd_login_attempts_total{outcome=...}`,
distinct-user counts, ungoverned-account counts). The letter of the aggregate/enum rule
would allow them; the application's own precedent refuses them, twice: the
`gsd_dashboard_active_users` removal (`gsd/metrics.py#USED TO BE EXPOSED HERE AND WAS REMOVED` — "a distinct-user-count is still
personnel information"), and `/api/clusters/{id}/logins` itself, which **withholds these
exact aggregates from authenticated self-tier readers** (`summary: None` at self —
`gsd/api.py#list_logins`, "personnel data even without names"). An unauthenticated endpoint sits
*below* the self tier; emitting there what self-tier readers are refused would invert the
access design of the most sensitive endpoint in the application. The operational need is
covered identity-free by #4 and #9 (is capture alive?) — the *content* of what it captured
stays behind the API.

**4.3 Dashboard-usage metrics** (interaction counts, active users). Same precedent,
directly: usage data lives only in this dashboard's database, is gated by the *stricter*
usage tier, and its aggregates are withheld at self. Nothing about it belongs on any
unauthenticated listener.

**4.4 Per-group / per-GroupSync-provider / per-user series** of any kind. Already refused
by the file header and enforced by `TestCardinalityAndLeakage`; restated because every new
subsystem re-raises it. 65 groups today, tens of thousands on a real directory.

**4.5 `gsd_visibility_restrictions_enabled` (0/1 config gauge).** Tempting symmetry with
#9, rejected on disclosure: "view restrictions are off" tells an anonymous reader that any
stolen credential yields the full cluster view — pure attacker value, no defender value the
existing signals lack (the pod logs a WARNING at startup, `/api/whoami` reports the tier to
authenticated readers, and with restrictions off metrics #1/#2 read zero while traffic
flows, which an operator dashboard can key on).

**4.6 A SubjectAccessReview duration histogram.** The check is two HTTP calls, cached for
60 s, single-flighted per viewer, each capped by `TIER_CHECK_TIMEOUT_SECONDS = 5.0`; its
failure *count* is the actionable signal, its latency is bounded by construction, and
hand-maintained buckets in a custom collector are the kind of plumbing that earns its keep
only on hot paths. Revisit only if the TTL is ever raised enough that check latency becomes
user-visible.

**4.7 `gsd_activity_buckets_dropped_total`** (usage rows dropped after
`MAX_FLUSH_ATTEMPTS`). By the time flushes fail repeatedly the store is broken, `/readyz`
is already failing, and every store-backed metric here is screaming; the counter would be
redundant with signals that fire earlier. The `log.error` in `activity._requeue` remains
the record.

---

## 5. The existing surface, reviewed

### 5.1 WRONG: `gsd_leader` carries a vestigial, always-empty `cluster` label

Live evidence: `gsd_leader{cluster=""} 1.0`. Leadership is per-process — one Lease
(`gsd/leader.py#LeaderElector`), one flag — and `gsd/metrics.py#DashboardCollector._gather`
declares `labels=["cluster"]` then fills it
with `[""]` unconditionally. The label asserts a per-cluster fact that does not exist.

Fix — semantics-free in PromQL, because a label with an empty value is indistinguishable
from an absent label (selectors `{cluster=""}` match both), and no shipped PrometheusRule,
README query, or code references `gsd_leader` with a `cluster` matcher (verified by grep
across the repo — the references are the chart README §"which pod is leader" and
`docs/reference-architecture.md`, both label-free):

```python
        leader = GaugeMetricFamily(
            "gsd_leader",
            "1 on the replica holding the poll lease, 0 on standbys. Use it to pick one "
            "replica's series: gsd_groups_total and on(pod) gsd_leader == 1",
            labels=[],
        )
        if self.elector is not None:
            leader.add_metric([], 1 if self.elector.is_leader else 0)
        else:
            leader.add_metric([], 1)
```

Test: `assert "gsd_leader 1.0" in text and "gsd_leader{" not in text`.

### 5.2 WRONG: `gsd_alerts_total` violates its own documented parity with `/api/alerts`, three ways

The collector claims (`gsd/metrics.py#Kept in step with the /api/alerts call site`) that it is "Kept in step with the /api/alerts call site: a kind that exists
in one and not the other makes gsd_alerts_total disagree with the UI, so a Prometheus rule
can never be written against it." Measured against `gsd/api.py#list_alerts`, the
metric disagrees with the feed in three ways today:

1. **Degraded clusters keep exporting computed kinds from stale cache.** The API skips
   `compute_alerts` entirely for a cluster whose poll is failing ("a degraded cluster's
   cached rows are stale by definition"); the metric computes them anyway — so a cluster
   that goes dark keeps exporting yesterday's `empty_group`/`stale_group` counts as if
   current.
2. **The poll-failure alert itself is missing.** The API emits one critical alert with
   `kind` = the poll outcome (`auth_failed` | `forbidden` | `unreachable`); the metric
   emits nothing — the *loudest* alert in the UI is invisible to Prometheus rules. (It is
   partially covered by `gsd_cluster_up`, but the stated contract is parity with the feed.)
3. **`dangling_binding` is missing.** The API emits one critical alert per dangling row;
   the metric never emits the kind, so
   `gsd_alerts_total{kind="dangling_binding"}` is a rule that can never fire — the exact
   silent-alert case `test_every_metric_an_alert_references_is_declared_by_the_collector`
   exists to prevent. (No *shipped* rule references it — the shipped rule uses
   `gsd_bindings_total{finding="dangling"}` — so nothing is broken today; the trap is
   armed for whoever writes one.)

Live confirmation of the vocabulary gap: today's scrape shows only `kind="unattributed"`
and `kind="direct_user_binding"`.

Fix, anchored on the current per-cluster block (the per-CR gauges above it are untouched —
they mirror `/groupsyncs`, which serves computed state for degraded clusters too):

```python
                # Kept in step with /api/alerts — now including the three ways it wasn't
                # (docs/DESIGN_metrics_refresh.md §5.2). A failing cluster contributes ONE
                # critical alert carrying its poll outcome as the kind and NONE of the
                # computed kinds: those would be recomputed from cache that stopped
                # updating when the poll did. A healthy cluster additionally reports one
                # dangling_binding per dangling row — by_finding already holds that count,
                # from the same snapshot the feed's own loop reads.
                if row["status"] and row["status"] != "ok":
                    by_kind[(row["status"], "critical")] = 1
                else:
                    for alert in st.compute_alerts(
                        cluster=cluster,
                        groupsyncs=cluster_groupsyncs,
                        operator_configs=self.store.operator_configs(cluster)["configs"],
                        user_bindings=self.store.direct_user_bindings(cluster),
                        groups=self.store.groups(cluster, "all"),
                        groupsync_present=self.store.groupsync_present(cluster),
                        now=now,
                        grace=self.grace,
                    ):
                        key = (alert.kind, alert.severity)
                        by_kind[key] = by_kind.get(key, 0) + 1
                    if by_finding.get("dangling"):
                        by_kind[("dangling_binding", "critical")] = by_finding["dangling"]
                for (kind, severity), count in by_kind.items():
                    alerts.add_metric([cluster, kind, severity], count)
```

with the HELP text updated to say what it now means:

```python
        alerts = GaugeMetricFamily(
            "gsd_alerts_total",
            "Alerts as /api/alerts serves them at the wide tier, by kind and severity. A "
            "failing cluster reports its poll outcome as one critical alert and none of "
            "the computed kinds (those would come from stale cache); dangling bindings "
            "count under kind=dangling_binding.",
            labels=["cluster", "kind", "severity"],
        )
```

Tests:

```python
class TestAlertsFeedParity:
    def test_a_degraded_cluster_reports_its_poll_outcome_and_nothing_stale(self, scrape):
        """/api/alerts suppresses group-level kinds for a failing cluster and reports the
        poll outcome instead; the metric's own comment promises parity."""
        text, store = scrape
        assert 'kind="unattributed"' in text          # healthy: computed kinds present
        store.record_poll("crc", "auth_failed", "401")
        text2 = generate_latest(build_registry(store, GRACE)).decode()
        found = series(text2, "gsd_alerts_total")
        assert found[
            'gsd_alerts_total{cluster="crc",kind="auth_failed",severity="critical"}'] == 1
        assert 'kind="unattributed"' not in text2, "stale cache must not alert"

    def test_dangling_bindings_reach_the_alert_metric(self):
        """One dangling row -> kind=dangling_binding, count from the same by_finding the
        bindings gauge uses. Managed-then-gone is what makes a binding dangling."""
        now = datetime.now(UTC)
        store = Store(":memory:")
        try:
            store.upsert_cluster("crc", "https://x", True)
            store.record_poll("crc", "ok", None)
            store.record_managed_groups(
                "crc", [{"name": "gone-group", "sync_provider": "p"}], _iso(now))
            store.replace_group_state("crc", [], _iso(now))     # the group is gone
            store.replace_bindings(
                "crc",
                [{"binding_kind": "RoleBinding", "binding_namespace": "ns",
                  "binding_name": "rb", "role_kind": "ClusterRole", "role_name": "edit",
                  "group_name": "gone-group"}],
                _iso(now),
            )
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        assert series(text, "gsd_alerts_total")[
            'gsd_alerts_total{cluster="crc",kind="dangling_binding",severity="critical"}'] == 1
```

### 5.3 HELP-only clarification: `gsd_cluster_up`

"1 if the last poll of this cluster succeeded, 0 otherwise" — but a **never-polled** cluster
(status `NULL`) also reads 0, while the API deliberately distinguishes `reachable: null`
from `false`. No behaviour change (0-until-proven is the right alerting posture for
`GroupSyncClusterUnreachable`, which has a `for:` window); one sentence keeps an operator
from reading a fresh install's 0 as an outage:

```python
            "1 if the last poll of this cluster succeeded, 0 otherwise — including a "
            "cluster never yet polled, which also has no last_poll series.",
```

### 5.4 Known wart, kept: `_total` on gauges

`gsd_groups_total`, `gsd_groups_empty_total`, `gsd_groups_unattributed_total`,
`gsd_bindings_total`, `gsd_groupsync_groups_total`, `gsd_alerts_total` are **gauges** with
the counter suffix — against Prometheus naming conventions, and shipped in the
PrometheusRule expressions and operator dashboards. Renaming is an operator-visible
breaking change with no behavioural payoff; the same reasoning the collector's own comment
(`gsd/metrics.py#The metric NAMES still say sqlite, deliberately`) applies to the `sqlite`
names applies here. Verdict: keep, and hold the line on *new* metrics —
every proposal in §3 uses `_total` only on true counters.

### 5.5 Per-metric disclosure audit of the 16 shipped families

Per Ruling 1, the audit the brief asked for, one verdict each, all against "what does a
person who cannot log in learn":

| Family | Verdict |
|---|---|
| `gsd_build_info` | version/commit/branch of a public image — accepted; it is the same string `oc get deploy` shows and the image tag itself carries. |
| `gsd_leader` | 0/1 — fine. |
| `gsd_cluster_up`, `gsd_cluster_last_poll_timestamp_seconds` | reachability of a named *dashboard* cluster entry — fine; `cluster` values are operator-chosen config keys (`crc-local`). |
| `gsd_groups_total`, `_empty_total`, `_unattributed_total` | aggregate counts — the accepted trade, stated in §1. |
| `gsd_groupsync_state`, `_groups_total`, `_last_sync_timestamp_seconds`, `_reconcile_error_current` | carry `groupsync` + `namespace` label values (live: `ldap-groupsync`, `group-sync-operator`). CR names, operator-chosen, shipped — the explicit precedent of Ruling 1, **not extensible** to person/LDAP-group names. Worth knowing: `gsd/api.py#list_groupsyncs` leans on exactly this ("per-CR identity and state is already public on /metrics") to justify serving `/groupsyncs` at both tiers, and instructs "gate /metrics first if this should ever change" — §7's listener design keeps /metrics credential-free, so that reasoning is undisturbed. |
| `gsd_bindings_total{finding=...}` | counts by enum finding class; `gsd/api.py#binding_findings` already rules "an aggregate is not a target list". Fine. |
| `gsd_alerts_total{kind,severity}` | enum kinds + counts. One nuance, recorded: `gsd_alerts_total{kind="config_reconcile_error"}` is the one figure api.py withholds from self-tier readers on `/clusters` (the `operator_configs` summary) that remains inferable here in aggregate — `gsd/api.py#list_clusters` knows and accepts this ("only the failing count is inferable"). Within the line. |
| `gsd_sqlite_*` | engine internals — fine. |

**Nothing shipped today crosses the line.** The two hygiene guards
(`test_no_group_name_appears_in_any_label`, `test_no_username_appears_anywhere`) stay, and
the new families are all enum-or-count by construction (`RuntimeSignals` cannot even accept
an identity).

---

## 6. What this does to the series budget, computed

Live today: **16 families, 38 samples** (1 cluster, 3 CRs, 5 finding classes).

New, at reference scale (1 cluster): #1 = 12, #2 = 4, #3 = 1, #4 = 1, #5 = 1, #6 = 1,
#7 = 1, #8 = 2, #9 = 1 → **24 samples, so 38 → 62**, plus 9 HELP/TYPE pairs.
General form: **22 fixed + 2 per polled cluster** (#4, #7), independent of users, groups,
CRs, and directory size — the whole point. §5.2's parity fix adds at most a handful of
`kind` series per cluster *while alerts are firing*, exactly matching the feed.

`test_series_count_stays_bounded_as_groups_grow` (500 groups ⇒ < 40 sample lines) still
passes untouched: it builds `build_registry(store, GRACE)` with no signals and no settings,
and unwired families are declared without samples. Its guard now also proves the new
families add nothing per-group, which is worth a comment when applying.

---

## 7. The dedicated in-cluster metrics listener (Ruling 2, final shape)

The end state, one line per audience:

| Audience | Path | Change |
|---|---|---|
| in-cluster Prometheus | `http://<pod-ip>:<metricsPort>/metrics`, plain HTTP | **new** — metrics-only listener |
| third-party scrapers | `https://<route>/metrics` via the oauth-proxy | none |
| browsers / API | `127.0.0.1:8080` behind the proxy | none |

Four things an earlier draft of this section designed are **dropped, deliberately**, so a
reader knows they were considered rather than missed: a second Route (external scraping
keeps its existing URL); TLS / a serving certificate on the metrics listener (in-cluster
plaintext is what the operator asked for, and it is the trust level the kubelet and most
in-cluster scrape targets already operate at); an external-scraper migration (their URL
does not change, so nothing breaks); and the removal of `metrics` from
`oauthProxy.skipAuthRegex` (it **stays** — the Route path still serves `/metrics` through
the proxy, so `gsd/api.py#SKIP_AUTH_PATHS` is also untouched).

### 7.1 The honest rationale — smaller than it first looked

**Not load.** Measured on the live pod: one process,
`python3.14 -m uvicorn gsd.api:create_app --factory --host 127.0.0.1 --port 8080
--workers 1`, one event loop, 8080 the only listening socket in the dashboard container. A
second listener in the same process serves scrapes on resources shared with API requests —
it separates *addressing*, not *capacity*. Real isolation would need a second process or
more workers, and more workers fights the SQLite single-writer design the chart already
defends. **Do not justify this change on load; this section does not.**

**Not surface-shrinking either.** An intermediate ruling justified the listener by deleting
the `metrics` skipAuthRegex entry. Under the final shape that entry stays (the Route path
needs it), so that benefit is not collected and is not claimed.

**What is actually bought:**

* The in-cluster scrape stops needing TLS it cannot straightforwardly verify. Today's
  ServiceMonitor must scrape the *proxy's* TLS port with `scheme: https` plus a CA
  ConfigMap and an explicit `serverName` (the verified block landed this morning in
  monitoring.yaml — correct, but it took a measured `--resolve` experiment to prove).
  Under this shape it becomes `port: metrics`, `scheme: http`, **no tlsConfig at all** —
  simpler than both the current state and this morning's fix.
* Structurally, scraping no longer transits the oauth-proxy container: today the Service's
  `http` port targets the proxy, so a wedged or restarting auth sidecar takes monitoring
  down with it — the metrics port targets the app container directly, decoupling the
  health signal from the auth path. (Structural consequence of the Service shape, not a
  measured incident.)

### 7.2 THE constraint: a metrics-only ASGI app, never the API app on a second port

The API app binds `127.0.0.1` **and that bind is load-bearing, not incidental**: it is the
entire reason `X-Forwarded-User` is believable. Nothing outside the pod can reach the app,
so the only writer of that header is the oauth-proxy sidecar (activity.py's header
docstring and the deployment comments both state this; the visibility design inherits it).

The obvious implementation of the operator's "in-cluster should be :8080" — rebind the
*same* FastAPI app to `0.0.0.0` (on 8080 or any second port) — is therefore not a lesser
variant; **it is a total bypass of the per-user visibility control this branch exists to
add.** Every `/api/*` route would become directly reachable in-cluster past the proxy, at
which point anyone who can reach the pod IP sends `X-Forwarded-User: john.doe` and receives
the full wide view: all 65 groups, all 236 bindings, the entire login record. Measured on
the live pod before ruling: `http://<pod-ip>:8080/metrics` is refused today *because* of
the loopback bind — the refusal is the control working. Written here as a refusal precisely
because it is the tidy-looking simplification a later refactor would reach for.

So the second listener serves a **separate ASGI app containing exactly one route**:

* `GET /metrics` — nothing else. No `/api/*`, no static files, and no duplicated
  `/healthz`/`/readyz` (the existing listener keeps those; duplicating them re-opens a
  smaller version of the same question). If the listener thread dies, Prometheus's own
  `up == 0` for the target is the detector — which is the correct layer for "the exporter
  is down".
* The API app keeps its `127.0.0.1` bind, byte-for-byte unchanged.
* It shares the process's existing `CollectorRegistry`, store and elector — feasibility
  measured: `build_registry(store, grace, elector)` needs no request, no app state, no
  FastAPI (grep of metrics.py for `app.state`/`Request`: no matches). A scrape from the
  second listener is one more concurrent WAL reader, which the store's per-thread reader
  connections already serve (`store._rows` uses `self._reader()` per thread), and
  `collect()` already materialises under one short snapshot precisely so slow readers
  cannot starve checkpoints.

**Implementation — raw ASGI, one dedicated thread.** Raw ASGI rather than a second FastAPI
instance because the strongest guarantee that a socket cannot serve `/api/*` is having **no
router at all**; and a dedicated thread running its own `uvicorn.Server` (rather than a
task on the API app's loop) because the codebase's ownership idiom for background work is
threads with `start()`/`stop()` (Poller, ActivityRecorder, LeaderElector), shutdown is a
flag-and-join with a bounded timeout, and nothing has to reach into the main server's loop.
In `gsd/metrics.py`:

```python
def build_metrics_app(registry: CollectorRegistry):
    """The ENTIRE app for the dedicated metrics listener: GET /metrics, nothing else.

    Raw ASGI on purpose — no FastAPI, no router, no middleware. This socket binds
    0.0.0.0 (§7.3), outside the loopback trust boundary that makes X-Forwarded-User
    believable on the main app, so the safety argument is structural: there is no route
    table to grow, no header is read, and the one handler is read-only. Reusing build_app
    here instead would expose every /api route past the oauth-proxy and let anyone
    in-cluster forge an identity header — the bypass tests/test_metrics_listener.py
    exists to make loud.
    """
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            # Answer the protocol and DO NOTHING: the API app's lifespan owns the poller,
            # the elector and the store, and must keep owning them exactly once.
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            # A websocket probe gets the websocket refusal, not HTTP frames on the wrong
            # protocol — uvicorn would log the latter as a server error.
            await send({"type": "websocket.close"})
            return
        if scope["path"] != "/metrics" or scope["method"] != "GET":
            await send({"type": "http.response.start", "status": 404,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": b"not found"})
            return
        body = generate_latest(registry)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", CONTENT_TYPE_LATEST.encode())]})
        await send({"type": "http.response.body", "body": body})

    return app
```

and the thread owner, started/stopped from the API app's existing lifespan (which is the
only lifespan that ever starts the poller — the metrics app's lifespan handler above is
deliberately inert, so a second server cannot double-start anything):

```python
class MetricsListener:
    """Serves build_metrics_app on its own port, on its own thread, with its own loop.

    A thread rather than a task on the API server's loop: the codebase's background-work
    idiom (Poller, ActivityRecorder, LeaderElector), a shutdown that is flag-and-join
    like theirs, and no reaching into a loop uvicorn owns. This buys ADDRESSING, not
    capacity — the GIL and the store are still shared (§7.1).
    """

    def __init__(self, registry, host: str, port: int):
        import uvicorn
        self._config = uvicorn.Config(
            build_metrics_app(registry), host=host, port=port,
            # No lifespan and no access log: one route, scraped twice a minute. Plain
            # HTTP by ruling — in-cluster scrape, kubelet-style trust level (§7.4).
            lifespan="off", access_log=False, log_level="warning",
        )
        self._server = uvicorn.Server(self._config)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._server.run, name="metrics-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        # uvicorn's own cooperative stop; bounded join like ActivityRecorder.stop() — a
        # wedged socket must not hold pod termination past the grace period.
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                log.warning("metrics listener still serving at shutdown; abandoning it")
```

Wired in `build_app`'s lifespan beside `activity.start()` / `activity.stop()`, constructed
only when `settings.metrics_listener_enabled`, sharing the one `metrics_registry` the
`/metrics` route already uses. Honest costs: one more thread and one more socket; scrapes
still share the GIL and the store with API traffic (unchanged from today in capacity
terms).

### 7.3 Bind address: `0.0.0.0`, and why that is now safe

The point of the listener is in-cluster scraping *without* the proxy, so it binds
`0.0.0.0`. What that socket can do, exhaustively: answer `GET /metrics` with the registry's
exposition, and answer 404 to everything else. It reads no headers (an in-cluster caller
sending `X-Forwarded-User` changes nothing — there is no identity semantics in the app at
all), takes no parameters, writes nothing, and its one handler performs the same read-only
store snapshot every scrape performs today. A scrape flood is serialised by the listener's
single loop and bounded by `collect()`'s gather-then-release snapshot discipline — the same
worst case the proxy-fronted endpoint has now. The trust boundary statement after the
change: *the API app's loopback bind still guarantees no unproxied path to any identity-
bearing route; the metrics socket adds a second door that structurally cannot reach one.*

### 7.4 No TLS on the metrics port — why that is acceptable, and the NetworkPolicy question

The listener is plain HTTP by ruling. Stated rather than left for a reviewer to raise:

* **Confidentiality:** the identical bytes are already world-readable on
  `https://<route>/metrics` with no credential (Ruling 1). Plaintext on the pod network
  cannot leak what the internet is already served; the disclosure control is §1's absolute
  content rule, enforced at the exporter, not the transport.
* **Trust level:** an unauthenticated plaintext (or skip-verified) scrape port is how the
  kubelet and most in-cluster exporters are consumed; in-cluster Prometheus is built for
  it.
* **Integrity:** a pod-network man-in-the-middle able to falsify scrape responses is
  already positioned to do far worse than forge a gauge; it is outside this threat model.

**NetworkPolicy:** the port is newly reachable by anything in the cluster. Given the
content is public by design, restricting it is hardening, not a requirement — the honest
statement is that a policy here protects nothing confidential. If the operator wants it
anyway (defence in depth, scrape-flood hygiene), the shape is an optional
`templates/networkpolicy.yaml` allowing ingress on the metrics port from
`openshift-monitoring` / `openshift-user-workload-monitoring` plus the router namespace
for port 8443, off by default; note the chart ships no NetworkPolicy today, so this would
be the first and should be its own decision, not a rider on this change. **Recommendation:
not now.**

### 7.5 Objects and values surface

One Service, two ports; **no second Route, no second Service, no TLS objects.** Naming
follows the existing `oauthProxy.*` / `monitoring.*` style — a top-level block for the
app-side feature:

```yaml
# values.yaml
metricsListener:
  # Serve /metrics on a dedicated in-pod plaintext listener for in-cluster Prometheus,
  # so the ServiceMonitor can scrape the app directly (scheme http, no tlsConfig)
  # instead of through the oauth-proxy's TLS port. The Route path
  # (https://<host>/metrics, through the proxy) is unchanged and stays in
  # oauthProxy.skipAuthRegex. Content on both is identical and world-readable by
  # design: counts and enum states only, never a name.
  enabled: false          # additive and opt-in; flip on where in-cluster scraping runs
  port: 8081
```

* **Service** (`templates/service.yaml`): add under `ports:` —

  ```yaml
      {{- if .Values.metricsListener.enabled }}
      - name: metrics
        port: {{ .Values.metricsListener.port }}
        # Targets the APP container's metrics-only listener, deliberately NOT the proxy:
        # scrapes stop transiting the auth sidecar, and the listener serves exactly one
        # unauthenticated read-only route (gsd/metrics.py build_metrics_app).
        targetPort: metrics
      {{- end }}
  ```

* **Deployment**: `containerPort: {{ .Values.metricsListener.port }}` named `metrics` on
  the **dashboard** container. The oauth-proxy container, the command override and the
  `127.0.0.1` bind are untouched.
* **ConfigMap / Settings** (config.py's existing camelCase-raw + env-override pattern):
  `metricsListenerEnabled`, `metricsListenerPort` →
  `Settings.metrics_listener_enabled: bool = False`,
  `metrics_listener_port: int = 8081`.

**`/metrics` stays on the app's 8080 listener too** — it must, or the Route path dies. So
metrics is served on two listeners in one process; that duplication is the cost of keeping
both audiences happy, and it is safe because **the two cannot disagree**: `build_app`
builds one `metrics_registry` and hands the same object to the FastAPI route and to
`MetricsListener`, and every scrape on either port runs the same collector against the same
store. There is no second exporter to drift.

### 7.6 ServiceMonitor change

With the listener enabled, the endpoint becomes simpler than both the current state and
this morning's verification fix — no scheme juggling, no CA, no serverName, because there
is no TLS to verify:

```yaml
  endpoints:
    - port: metrics          # was: http (the proxy's TLS port)
      path: /metrics
      interval: {{ .Values.monitoring.serviceMonitor.interval }}
      scrapeTimeout: {{ .Values.monitoring.serviceMonitor.scrapeTimeout }}
```

templated on `metricsListener.enabled`, with the existing `https` + tlsConfig endpoint
remaining the `else` branch for deployments that do not enable the listener. One endpoint
or the other, never both — scraping both would double every series for no information.

### 7.7 Migration: there is none

The change is additive. External scrapers keep `https://<route>/metrics` byte-for-byte;
in-cluster Prometheus moves to the `metrics` port only when the operator flips
`metricsListener.enabled`, which swaps the ServiceMonitor endpoint in the same release of
the same chart. Rollback is the same flag. Nothing is removed, so nothing breaks and no
multi-release schedule is needed.

### 7.8 The guard test — the whole §7.2 argument, enforced

New `tests/test_metrics_listener.py`; the first test is the one that fails if a later
refactor "tidily" reuses `build_app` for both listeners:

```python
"""The dedicated metrics listener structurally cannot serve the application.

The API app's 127.0.0.1 bind is what makes X-Forwarded-User believable; this socket binds
0.0.0.0. The ONLY thing keeping that safe is that this app has no routes to reach — so
these tests fail loudly on the refactor that would quietly reintroduce the bypass by
serving the API app on the metrics port.
"""

from datetime import timedelta

import pytest
# TestClient drives any ASGI3 app synchronously — including this raw one. httpx's
# ASGITransport is async-only, so it would force the whole file onto pytest-asyncio
# for no gain.
from starlette.testclient import TestClient

from gsd.metrics import build_metrics_app, build_registry
from gsd.store import Store

GRACE = timedelta(seconds=120)


@pytest.fixture()
def metrics_client():
    store = Store(":memory:")
    with TestClient(build_metrics_app(build_registry(store, GRACE))) as client:
        yield client
    store.close()


class TestTheListenerServesMetricsAndNothingElse:
    @pytest.mark.parametrize("path", [
        "/api/clusters", "/api/whoami", "/api/alerts",
        "/api/clusters/crc/logins", "/api/dashboard/activity",
        "/", "/static/app.css", "/healthz", "/readyz", "/api/openapi.json",
    ])
    def test_every_application_path_is_404(self, metrics_client, path):
        response = metrics_client.get(
            path,
            # The forged header that would be believed if the API app ever answered
            # here — the exact bypass this listener must make impossible.
            headers={"x-forwarded-user": "kubeadmin"},
        )
        assert response.status_code == 404
        assert "gsd_" not in response.text

    def test_metrics_answers_and_ignores_identity_headers(self, metrics_client):
        anonymous = metrics_client.get("/metrics")
        forged = metrics_client.get(
            "/metrics", headers={"x-forwarded-user": "kubeadmin"})
        assert anonymous.status_code == 200
        assert "gsd_build_info" in anonymous.text
        assert anonymous.text == forged.text, "identity must change nothing here"

    def test_metrics_is_get_only(self, metrics_client):
        assert metrics_client.post("/metrics").status_code == 404
```

### 7.9 Verdict: sound and worth doing, with the costs named — and the losing option named too

The shape is sound. Costs, honestly: ~80 lines of app code (one ASGI function, one thread
owner, lifespan wiring), four chart touch-points (Service port, container port,
ServiceMonitor branch, values/ConfigMap keys), one more thread and socket in the pod, and
`/metrics` served from **two listeners in one process** — which is duplication of
*serving*, not of *truth*: one registry object feeds both, so they cannot disagree, and the
duplication is the price of leaving the external URL untouched.

Weighed against what it removes: the ServiceMonitor sheds a scheme, a CA reference and a
`serverName` that took a measured experiment to get right, and in-cluster monitoring stops
depending on the health of the auth sidecar it was never really about. That trade favours
the listener, narrowly — this is a simplification of the scrape path, not a security win
(the skipAuthRegex entry stays, §7.1), and if the operator weighs "fewer moving parts in
the pod" above "fewer moving parts in the ServiceMonitor", *doing nothing is also
defensible*: the current https scrape is verified and working as of this morning's
monitoring.yaml fix.

What is not defensible is the middle path: the single-app-two-ports version is not a
cheaper variant of this design, it is an unsafe one (§7.2), and this section exists largely
to keep anyone from building it. If the listener is built, it is built as the metrics-only
app with the §7.8 guard test, or not at all.

---

## 8. PrometheusRule additions (chart, `templates/monitoring.yaml`)

Ready to append to the existing rules; every referenced family is *declared* by the
collector even on an empty store (§2), so
`test_every_metric_an_alert_references_is_declared_by_the_collector` keeps passing. New
`values.yaml` knobs shown inline follow the existing `monitoring.prometheusRule.for.*`
shape.

```yaml
        # The fail-closed control, §3.1: every outcome here except allowed/denied is a
        # reader silently narrowed to the self view. Nothing else reports this — the pod
        # log is the only other witness.
        - alert: GroupSyncDashboardVisibilityChecksFailing
          expr: >-
            sum(increase(gsd_visibility_tier_checks_total{
              outcome=~"unreachable|auth_failed|forbidden|error"}[15m])) > 0
          for: {{ .Values.monitoring.prometheusRule.for.visibilityFailing }}   # e.g. 15m
          labels: {severity: critical}
          annotations:
            summary: "Visibility tier checks are failing; readers are being served the self view fail-closed"
            description: >-
              The SubjectAccessReview behind per-user visibility is erroring rather than
              answering. Every affected reader silently receives only their own data.
              outcome=forbidden usually means the ServiceAccount lost `create
              subjectaccessreviews` (system:auth-delegator); unreachable/auth_failed point
              at the API server or the ServiceAccount token.

        # Capture rides the poll thread, so its cadence is pollIntervalSeconds; stale by
        # several multiples means it stopped (grant revoked, pods unreadable, thread dead)
        # while the Logins page silently freezes.
        # `and on()`, not a bare `and` — caught at application time: the enabled gauge is
        # unlabelled while the staleness side carries {cluster} plus target labels, so
        # default matching would never pair them and the alert could never fire. (An
        # earlier draft of this snippet had exactly that bug.)
        - alert: GroupSyncDashboardLoginCaptureStalled
          expr: >-
            (time() - gsd_login_capture_last_read_timestamp_seconds)
              > {{ .Values.monitoring.prometheusRule.captureStalledSeconds }}   # e.g. 1800
            and on() (gsd_login_capture_enabled == 1)
          for: {{ .Values.monitoring.prometheusRule.for.captureStalled }}
          labels: {severity: warning}
          annotations:
            summary: "Login capture has stopped reading the oauth-server log on {{ `{{ $labels.cluster }}` }}"

        # The only copy of the irreplaceable history. Two intervals means at least one
        # whole backup cycle produced nothing restorable.
        - alert: GroupSyncDashboardBackupStale
          expr: >-
            (time() - gsd_backup_last_success_timestamp_seconds)
              > {{ .Values.monitoring.prometheusRule.backupStaleSeconds }}   # e.g. 2 * 6h
          for: {{ .Values.monitoring.prometheusRule.for.backupStale }}
          labels: {severity: critical}
          annotations:
            summary: "No successful database backup within the expected window"
            description: >-
              The sync/membership history exists only in this database; the newest file in
              backupDir is older than two backup intervals. Check
              gsd_backup_failures_total for active failures and the pod log for the cause.
```

(No rule proposed on `gsd_cluster_poll_duration_seconds` — its threshold is
deployment-specific arithmetic on `pollIntervalSeconds` and `request_timeout_seconds`;
graph it, alert when a deployment knows its own numbers. No rule on
`gsd_visibility_admin_refusals_total` — refusals are a legitimate steady state; it exists
for correlation, not paging.)

---

## 9. Test plan and how it was validated

* New assertions live in `tests/test_metrics.py` (§3 snippets — the `series()` helper and
  fixture style are the file's own), `tests/test_visibility.py` /
  `tests/test_visibility_tier.py` (end-to-end tier counting, where the resolver seams
  live), and new `tests/test_metrics_listener.py` (§7.8).
* Existing guards that keep working unchanged, and why: `TestCardinalityAndLeakage` (new
  families carry only enum labels — `RuntimeSignals` cannot accept an identity),
  `test_series_count_stays_bounded_as_groups_grow` (unwired families declare no samples),
  `test_every_metric_an_alert_references_is_declared_by_the_collector` (families always
  declared; §8's rules resolve).
* `TestExposition`-level behaviour of prometheus_client verified empirically against the
  project venv before writing the snippets: `CounterMetricFamily("..._total")` emits the
  name as given (the file's `gsd_sqlite_checkpoint_busy_total` precedent), **labels
  serialise alphabetically** regardless of declaration order (so sample keys in tests use
  `outcome` before `threshold`), and a sample-less family still renders HELP/TYPE.
* Suite baseline at the time of writing: 1230 passed / 0 failed via
  `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
  (venv outside this worktree). Failures appearing in `tests/test_ui.py` /
  `tests/test_accessibility.py` during concurrent UI work are that work, not this design.

## 10. Explicitly out of scope

Restructuring metrics.py; any new dependency; renaming the `_total` gauges (§5.4) or the
`gsd_sqlite_*` family (its own comment already owns that decision); retention for
`membership_event`/`sync_event` (a data-lifecycle decision, not a metrics one — §0.2);
authenticating /metrics or adding a scrape credential (settled by Rulings 1 and 2:
credential-free on both paths — the Route through the proxy's skipAuthRegex, unchanged,
and the in-cluster plaintext listener); TLS on the metrics listener, a second Route, or
removing the `metrics` skipAuthRegex entry (all considered and dropped under Ruling 2's
final shape — §7); a NetworkPolicy (§7.4: recommended not now, and it would be the chart's
first).
