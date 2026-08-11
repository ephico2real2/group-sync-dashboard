# Adversarial review — `d39b747` log-level contract

Scope is exactly `a4db191..d39b747`. Existing worktree edits were ignored. Verdict: **15
CONFIRMED, 4 REFUTED, 3 FIX-INADEQUATE**. Six replacements are required; one replacement closes
both L3 and B3.

## Level machinery

### L1 — CONFIRMED

Cannot refute after checking the installed `httpx`/`httpcore` logger split and every call after
`create_app`: `httpx` emits the semantic method/URL/status record at INFO; `httpcore` emits connection,
TLS, and HTTP framing at DEBUG. Pinning the `httpcore` parent does not affect `httpx`. The propagated
exception still reaches the app when a request fails, and `GSD_DEBUG_HTTP` restores the lower-layer
sequence when that exception is insufficient.

### L2 — CONFIRMED

Measured `1`, whitespace/case variants of `true`, and `yes`: all leave `httpcore` unpinned. Measured
`0`, `false`, `no`, `off`, empty, and arbitrary text: all pin it to WARNING. Nothing else is changed.

### L3 — FIX-INADEQUATE

The resolver did not raise for `None`, non-ASCII, full-width Unicode, or a one-million-character
string. The latter produced a **1,000,369-character WARNING**, however, and arbitrary invalid content
is copied verbatim into the pod log.

**Anchor:** `api.py#_resolve_log_level`

**Trigger:** a direct deployment accidentally wires a token, password, or a very large value into
`GSD_LOG_LEVEL`.

**False operator belief:** an operator reading the new warning believes it contains only safe
logging configuration; it actually republishes the entire arbitrary environment value into the log
pipeline. This is also the B3 refutation.

**Complete replacement:**

```python
def _resolve_log_level(raw: str | None) -> tuple[int, str | None]:
    """One GSD_LOG_LEVEL value to a logging level, never raising. Returns (level, complaint).

    WHY THIS EXISTS RATHER THAN PASSING THE STRING STRAIGHT THROUGH. `logging.basicConfig` raises
    `ValueError: Unknown level: 'debug'` for anything it does not recognise, and this function is
    used by the uvicorn factory — so the container did not start. Case-normalising an understood
    value removes that outage class; an unrecognised value degrades to INFO and says so.

    THE INVALID VALUE IS DELIBERATELY NOT ECHOED. Environment wiring mistakes can put a credential
    or an arbitrarily large string in the wrong variable. The accepted set is enough to repair the
    setting; copying the rejected content into an admin-readable pod log would turn a typo into a
    disclosure or one enormous log record.

    THE OPENSHIFT COLLISION IS NAMED because its `spec.logLevel` uses Normal | Debug | Trace |
    TraceAll and this chart carries `authLogLevel` for that distinct setting. Debug is the only word
    valid in both vocabularies.
    """
    if raw is None or not raw.strip():
        return logging.INFO, None
    wanted = raw.strip().upper()
    if wanted in LOG_LEVELS:
        return getattr(logging, wanted), None
    return logging.INFO, (
        "GSD_LOG_LEVEL is not a log level this app accepts, so it is running at INFO. "
        f"Use one of {', '.join(LOG_LEVELS)} (case does not matter). If you meant OpenShift's "
        "vocabulary — Normal, Debug, Trace, TraceAll — that belongs to operator.openshift.io "
        "objects and is set through the chart's authLogLevel, not logLevel; only Debug means the "
        "same thing in both."
    )
```

**Complete test (`tests/test_log_levels.py`):**

```python
def test_an_invalid_value_is_bounded_and_never_echoed() -> None:
    """A miswired secret or huge value must not be copied into an admin-readable pod log."""
    import logging

    from gsd.api import _resolve_log_level

    for raw in (
        "Bearer eyJhbGciOiJSUzI1NiJ9.review-secret",
        "correct-horse-battery-staple",
        "x" * 1_000_000,
    ):
        level, complaint = _resolve_log_level(raw)
        assert level == logging.INFO and complaint
        assert raw not in complaint
        assert len(complaint) < 2_000, "one invalid setting produced an unbounded log record"
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement; original restored**.

### L4 — CONFIRMED

Measured Python root `NOTSET`: effective level `0`, and a DEBUG record passed its handler. `WARN` and
`FATAL` are aliases only. Rejecting all three preserves one spelling per meaning.

### L5 — CONFIRMED

Uvicorn configures its loggers before loading the factory. `basicConfig` then runs, the `httpcore`
parent is pinned, and neither `build_app` nor any later code calls `dictConfig`, changes that logger,
or re-enables it. The 22 subprocess tests also exercise the effective post-configuration state.

### L6 — CONFIRMED

The complaint is returned before configuration and emitted after `basicConfig` at WARNING. At the
INFO fallback it is visible and contains the complete five-level accepted set. Empty/unset values
quietly mean INFO, as documented by the contract test.

## Chart guard

### C1 — CONFIRMED

Helm 3.14 exit-status measurements with a renderable `ingress.host`:

| value | exit | rendered value |
|---|---:|---|
| `DEBUG`, `debug`, ` WaRnInG ` | 0 | normalized upper-case |
| `TRACE`, `WARN`, `FATAL`, `NOTSET`, `20`, empty | nonzero | none |
| null/missing | 0 | `INFO` |

The decision did not rely on matching `Error:`.

### C2 — REFUTED

Strict chart refusal and direct-environment fallback are defensible, but their diagnostics do
contradict each other. The new helper still says the app passes the raw value to `basicConfig` and
that an invalid value “stops the container from starting at all”; this commit made both statements
false.

**Anchors:** `_helpers.tpl#gsd.logLevel`; `api.py#_resolve_log_level`

**Trigger:** `helm template ... --set-string logLevel=Trace`.

**False operator belief:** the Helm failure tells an operator that the same invalid value in a direct
`GSD_LOG_LEVEL` deployment crash-loops the app; the app actually warns and serves at INFO.

**Complete replacement:**

```gotemplate
# logLevel is validated before rollout because a Helm release value is deterministic input. The app
# has a different boundary: a directly supplied invalid GSD_LOG_LEVEL keeps serving at INFO and
# warns, because a logging typo is not grounds for an outage. The chart can be stricter without an
# outage: refusing here makes the operator correct the value before any workload changes.
#
# CASE IS NORMALISED rather than refused. `logLevel: debug` is the natural thing to write and it
# unambiguously means DEBUG, so upper-casing it removes an avoidable render failure without admitting
# misspellings such as `trace`.
#
# The accepted set is the five the values file documents. `WARN` and `FATAL` are aliases that add a
# spelling and no meaning; `NOTSET` on the root logger means no threshold and therefore behaves as
# DEBUG while reading as off.
{{- define "gsd.logLevel" -}}
{{- $raw := .Values.logLevel -}}
{{- if or (not (hasKey .Values "logLevel")) (kindIs "invalid" $raw) -}}
INFO
{{- else -}}
{{- $l := upper (trim (toString $raw)) -}}
{{- if not (has $l (list "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL")) -}}
{{- fail "logLevel is not a log level for THIS chart. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nIf you were reaching for OpenShift's vocabulary — Normal, Debug, Trace, TraceAll — that belongs to operator.openshift.io resources and means something different. This value configures the dashboard's own Python logging, while authLogLevel manages spec.logLevel on authentications.operator.openshift.io/cluster. Debug is the one word valid in both.\n\nA direct GSD_LOG_LEVEL deployment degrades an unrecognised value to INFO and warns. This chart is stricter because a release value is known before rollout: refusing the render prevents a typo from silently deploying at a level the operator did not request." -}}
{{- end -}}
{{- $l -}}
{{- end -}}
{{- end -}}
```

**Complete test (`tests/test_chart_strategy.py`):**

```python
def test_log_level_refusal_describes_the_app_fallback_truthfully():
    ok, out = render(logLevel="Trace")
    assert not ok, "the invalid chart value rendered successfully"
    assert "direct GSD_LOG_LEVEL" in out and "degrades" in out and "INFO" in out
    assert "stops the container" not in out and "CRASH-LOOPS" not in out
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement; source text restored**.

### C3 — CONFIRMED

The current OpenShift Authentication API documents `spec.logLevel` values as `Normal`, `Debug`,
`Trace`, and `TraceAll`, distinct from `operatorLogLevel` ([Red Hat Authentication Operator API](https://docs.redhat.com/en/documentation/openshift_container_platform/4.17/html/operator_apis/authentication-operator-openshift-io-v1)). The chart's hook selects `Debug`/`Normal` and patches exactly
`authentications.operator.openshift.io cluster` with `{"spec":{"logLevel":...}}`.

## Instrumentation

### I1 — CONFIRMED

Measured through the real predicates with one attempt in each bucket: `parsed=3`, `_recordable=2`,
`_not_clipped=1`, producing `withheld=1`, `dropped=1`, `to-write=1`. `_recordable` is the settling
predicate; `_not_clipped` is applied only to its result. The differences therefore partition exactly
what their labels claim.

### I2 — CONFIRMED

The explanatory line is guarded by `if lines and not parsed`, not by `attempts`. It states both
honest possibilities—no login and authentication operand not at Debug—without blaming that setting
when either local filter removed parsed attempts.

### I3 — FIX-INADEQUATE

`capture_once` moved its line to WARNING, but the real call first emits the old INFO from
`fetch_oauth_pods`. That lower-layer line is also factually reversed: this method is reachable only
after capture was found enabled, yet it says “login capture is off” and tells the operator to enable
it. No existing test asserts the old level; checked `test_logincapture_loop.py` and
`test_kube_reader.py`.

**Anchor:** `kube.py#ClusterClient.fetch_oauth_pods`

**Trigger:** capture enabled, but pod-list RBAC returns 403.

**False operator belief:** the INFO line makes the operator believe capture is disabled and the
feature flag is the repair; capture is already enabled and only its RBAC grant is missing.

**Complete replacement:**

```python
def fetch_oauth_pods(self, namespace: str) -> list[str] | None:
    """Names of the Running oauth-server pods, or None when we may not list them.

    DISCOVERY IS NOT OPTIONAL. Pod names are generated, production runs two or three replicas, and
    every roll replaces them, so there is no fixed name to read. Only Running pods are useful: a
    Pending pod has produced nothing and a Terminating pod is read next cycle if it survives.

    None means FORBIDDEN, deliberately distinct from [] (permitted, no pods found). The feature
    layer in `capture_once` owns the operator-facing WARNING because it knows capture is enabled;
    this transport layer records only the 403 reasoning at DEBUG.
    """
    path = POD_API_TMPL % namespace
    with self._client() as client:
        try:
            items = self._list_all(client, path)
        except ClusterError as exc:
            if exc.outcome == FORBIDDEN and path in exc.message:
                # DEBUG and factual only. `capture_once` has already established that capture is ON
                # and emits the one operator-facing WARNING; repeating that conclusion here would
                # turn one failure into two and this layer cannot truthfully prescribe the setting.
                log.debug(
                    "%s: forbidden listing pods in %s; returning no pods",
                    self.cluster.name,
                    namespace,
                )
                return None
            raise
    return [
        name for obj in items
        if (obj.get("status") or {}).get("phase") == "Running"
        and (name := (obj.get("metadata") or {}).get("name"))
    ]
```

**Complete test (`tests/test_kube_reader.py`):**

```python
def test_forbidden_pod_discovery_is_debug_bookkeeping(monkeypatch, caplog):
    cluster = ClusterConfig("reference", "https://cluster.example", token_env="TOKEN")
    client = ClusterClient(cluster)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            403,
            json={"kind": "Status", "reason": "Forbidden", "message": "forbidden"},
            request=request,
        )
    )
    monkeypatch.setattr(
        client,
        "_client",
        lambda: httpx.Client(transport=transport, base_url=cluster.api_url),
    )

    with caplog.at_level(logging.DEBUG):
        assert client.fetch_oauth_pods("openshift-authentication") is None

    records = [record for record in caplog.records if record.name == "gsd.kube"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert "capture is off" not in records[0].getMessage()
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement; method restored**.

### I4 — CONFIRMED

`age = (now - last).total_seconds()` is correct. Old and new decisions matched at 29.999999s, exactly
30s, 30.000001s, negative age, and an extreme positive age. Both use strict `>` and both set expired
true on `ValueError`; malformed timestamps were exercised. No behavior change found.

### I5 — CONFIRMED

A 401/403 on the leadership gate prevents every poll indefinitely until credentials/RBAC change.
ERROR matches “advertised function broken and will not self-heal”; the generic transient/non-200 path
remains WARNING.

### I6 — FIX-INADEQUATE

Omitting the traceback is acceptable here: type plus message distinguishes the expected SQLite
classes without repeating a stack on each retry. The implementation still emits **two WARNINGs for
one failed write**, however: the cause in `flush`, then the requeue count in `_requeue`. A permanent
failure produces five warnings plus the terminal error across three attempts.

**Anchor:** `activity.py#ActivityRecorder._requeue`

**Trigger:** any activity flush raises before the retry bound.

**False operator belief:** two WARNING records make an operator believe two degraded events occurred;
there was one store failure and one bookkeeping consequence.

**Complete replacement:**

```python
def _requeue(self, pending: list[dict]) -> None:
    """Merge failed buckets back, dropping any that have exhausted their retries.

    Merged rather than reinserted: the same user-day may have accumulated more interactions while
    the failed write was in flight, and overwriting would discard them. Same rule as the SQL upsert
    — counts add, the window widens.
    """
    kept, dropped = 0, 0
    with self._lock:
        for bucket in pending:
            bucket["attempts"] = bucket.get("attempts", 0) + 1
            if bucket["attempts"] >= MAX_FLUSH_ATTEMPTS:
                dropped += 1
                continue
            key = (bucket["user_name"], bucket["day"])
            current = self._buckets.get(key)
            if current is None:
                self._buckets[key] = bucket
            else:
                current["request_count"] += bucket["request_count"]
                current["first_seen_at"] = min(
                    current["first_seen_at"], bucket["first_seen_at"]
                )
                current["last_seen_at"] = max(
                    current["last_seen_at"], bucket["last_seen_at"]
                )
                current["email"] = current.get("email") or bucket.get("email")
                current["attempts"] = bucket["attempts"]
            kept += 1
    if dropped:
        log.error(
            "dropping %d user-activity bucket(s) after %d failed flushes; that usage "
            "is lost. %d bucket(s) still queued for retry",
            dropped,
            MAX_FLUSH_ATTEMPTS,
            kept,
        )
    else:
        # DEBUG because flush() already emitted the failure cause at WARNING. This line explains
        # the retry bookkeeping; keeping it at WARNING makes one failed write look like two faults.
        log.debug("flush failed; %d user-activity bucket(s) requeued for retry", kept)
```

**Complete test (`tests/test_activity.py`):**

```python
def test_one_flush_failure_emits_one_warning_and_debug_bookkeeping(caplog):
    import logging

    class FailingStore:
        def record_user_activity(self, buckets):
            raise RuntimeError("database is locked")

    recorder = ActivityRecorder(FailingStore(), enabled=True)
    recorder.record("alice", None, "2026-08-01T09:00:00Z")
    with caplog.at_level(logging.DEBUG):
        assert recorder.flush() == 0

    cause = [record for record in caplog.records
             if "dashboard-usage flush failed" in record.getMessage()]
    bookkeeping = [record for record in caplog.records
                   if "bucket(s) requeued" in record.getMessage()]
    assert len(cause) == 1 and cause[0].levelno == logging.WARNING
    assert len(bookkeeping) == 1 and bookkeeping[0].levelno == logging.DEBUG
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement; method restored**.

### I7 — REFUTED

The latch is not thread-safe. Both the read and set are outside the lock used by the rest of the
request-path state. A deterministic two-thread probe forced both requests to observe false and
emitted the supposedly once-per-process line twice.

**Anchor:** `activity.py#ActivityRecorder.record`

**Trigger:** the first two username-less requests enter `record` concurrently.

**False operator belief:** duplicate records ending “Said once per process” make an operator believe
multiple processes or multiple configuration transitions were observed; one process saw one
unchanged condition.

**Complete replacement:**

```python
def record(self, user: str | None, email: str | None, at: str | None = None) -> None:
    """Note one request. In-memory only — never touches the database.

    Called from the request path, so it must stay cheap and must never raise: a failure to record who
    read a page is not a reason to fail the page.
    """
    if not self.enabled:
        return
    if not user:
        # The condition is deployment-wide and worth saying once, but request handlers are
        # concurrent. Use the existing state lock for the check-and-set, then log outside it so a
        # slow handler cannot hold up bucket updates or flushes.
        with self._lock:
            if self._warned_missing_user:
                return
            self._warned_missing_user = True
        log.debug(
            "dashboard-usage recording is on but a request carried no username header, so nothing "
            "was recorded for it and nothing will be until the proxy supplies one — check the "
            "oauth-proxy sidecar is passing user headers. Said once per process; the condition is "
            "per-deployment, not per-request"
        )
        return
    at = at or now_iso()
    key = (user, _day(at))
    with self._lock:
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = {
                "user_name": user,
                "day": key[1],
                "email": email,
                "first_seen_at": at,
                "last_seen_at": at,
                "request_count": 1,
            }
            return
        bucket["request_count"] += 1
        # Requests may arrive out of timestamp order, so widen both ends rather than assuming the
        # latest thread carries the latest timestamp.
        if at < bucket["first_seen_at"]:
            bucket["first_seen_at"] = at
        if at > bucket["last_seen_at"]:
            bucket["last_seen_at"] = at
        if email:
            bucket["email"] = email
```

**Complete test (`tests/test_activity.py`):**

```python
def test_missing_username_diagnostic_is_exactly_once_under_concurrency(caplog):
    import concurrent.futures
    import logging
    import threading

    race = threading.Barrier(2)

    class RacingRecorder(ActivityRecorder):
        def __getattribute__(self, name):
            value = super().__getattribute__(name)
            if name == "_warned_missing_user":
                lock = super().__getattribute__("_lock")
                # The fixed implementation reads under the lock. The old implementation lets both
                # request threads observe False before either sets it.
                if not lock.locked():
                    race.wait(timeout=2)
            return value

    recorder = RacingRecorder(object(), enabled=True)
    with caplog.at_level(logging.DEBUG), concurrent.futures.ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(recorder.record, None, None) for _ in range(2)]
        for future in futures:
            future.result(timeout=3)

    messages = [record for record in caplog.records
                if "request carried no username" in record.getMessage()]
    assert len(messages) == 1, f"once-per-process diagnostic emitted {len(messages)} times"
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement; method restored**.

### I8 — CONFIRMED

This is the one path where the app continues to answer health/read requests while unable to replace
a stale success with the failed poll outcome. CRITICAL matches “cannot serve truthfully.”
`log.critical(..., exc_info=True)` is inside the active exception handler and preserves the same
exception tuple and traceback that `log.exception` supplied.

## Volume and disclosure budget

### B1 — CONFIRMED

Controlled steady-state measurement with the real poll/capture code, 62 Groups, capture enabled,
three Running oauth pods, single-page lists, and empty settled pod windows: **10 INFO per cycle**—8
`httpx` request summaries (GroupSync, Groups, Users, OAuth, pod list, three logs) plus 2 app summaries
(display names and completed poll). The six schema-migration INFO records were excluded as startup,
not steady state. No INFO is per Group. Nothing needs moving on this path.

### B2 — CONFIRMED

The same controlled cycle emitted **5 DEBUG**: one user-fetch summary, three per-pod capture accounting
records, and one cycle timing/countdown. All were `gsd.*`; zero were `httpcore`. The supplied live
measurement of 11 DEBUG is consistent with non-empty pod windows adding honest per-pod explanation.
No new record is per Group, login attempt, or raw log line; the highest multiplicity is one per oauth
pod, which is the unit of capture work.

### B3 — REFUTED

The commit adds no metric label/name leak and the existing `/metrics` personnel test remains green.
New login-capture records contain counts, pod names, cluster names, and permitted usernames/DNs only
where already intended. But `api.py#_resolve_log_level` logs any invalid environment content verbatim,
including a miswired credential. The concrete trigger, false belief, complete replacement, complete
test, and fail/pass mutation proof are under **L3**.

## Documentation

### D1 — REFUTED

The old “DEBUG adds HTTP request lines” claim is gone. A different false promise remains in all three
operator-facing descriptions: DEBUG allegedly adds **page counts**, while
`kube.py#ClusterClient._list_all` contains no page-count log (and there is no such `log.debug` anywhere
in `gsd`). The root README also names only DEBUG rather than stating the promised five-level contract.

**Code anchor:** `kube.py#ClusterClient._list_all`

**Documentation anchors:** `README.md#Configuration`; `charts/group-sync-dashboard/README.md#Application`;
`charts/group-sync-dashboard/values.yaml#logLevel`

**Trigger:** an operator enables DEBUG to diagnose Kubernetes list pagination.

**False operator belief:** the docs make the operator believe each page count will appear; DEBUG emits
no pagination record at all.

**Complete replacement blocks:**

`README.md` configuration row plus contract paragraph:

```markdown
| `logLevel` | `INFO` | `DEBUG` adds this app's own reasoning: login-capture accounting per pod, poll timing, fetched-object summaries, and which replica holds the Lease. **Not** HTTP request lines — httpx logs those at `INFO` already. Not the same value as `authLogLevel` |

The level contract is operational: `CRITICAL` means the process cannot serve truthfully; `ERROR`
means advertised behavior is broken and needs action; `WARNING` is scoped or self-healing degradation;
`INFO` is one record per completed unit of work or state change; and `DEBUG` is the app's reasoning,
never third-party protocol framing.
```

`charts/group-sync-dashboard/README.md` application row:

```markdown
| `logLevel` | `INFO` | `DEBUG` adds app reasoning such as login-capture accounting, poll timing, fetched-object summaries and the binding-refresh countdown. Not HTTP request lines — httpx logs those at `INFO` itself, so they are already present at the default |
```

`charts/group-sync-dashboard/values.yaml` DEBUG contract lines:

```yaml
#   DEBUG     THIS APP'S OWN REASONING — what it read, what it skipped, and why a number is the
#             number. Per-pod login-capture accounting, poll timing and binding-refresh countdown,
#             fetched-object summaries, which replica holds the Lease, and why a reader was put on
#             the narrow tier.
```

**Complete test (`tests/test_log_levels.py`):**

```python
def test_debug_documentation_names_only_instrumentation_that_exists() -> None:
    root = (REPO / "README.md").read_text(encoding="utf-8")
    chart_readme = (REPO / "charts/group-sync-dashboard/README.md").read_text(encoding="utf-8")
    values = (REPO / "charts/group-sync-dashboard/values.yaml").read_text(encoding="utf-8")

    for name, text in (("root README", root), ("chart README", chart_readme),
                       ("values", values)):
        assert "page counts" not in text, f"{name} promises DEBUG instrumentation that does not exist"

    for meaning in (
        "cannot serve truthfully",
        "needs action",
        "scoped or self-healing",
        "completed unit of work",
        "app's reasoning",
    ):
        assert meaning in root, f"root README omits the {meaning!r} level contract"
```

Mutation proof: **FAIL on `d39b747`; PASS with the replacement blocks; source strings restored**.

### D2 — CONFIRMED

Measured Uvicorn's configured logger state: `uvicorn.access` is INFO, has its own handler, and has
`propagate=False`; it remains enabled after the root is set to CRITICAL. The chart does not pass
`--no-access-log` or override Uvicorn's level, so inbound access records are outside
`GSD_LOG_LEVEL` exactly as documented.

## Deliberately omitted `loginlog.py` logging

Agreed. The parser is pure, unmatched oauth-server lines are the normal majority, and neither an
unmatched-line log nor a raw count has an operational interpretation. The new accounting at the I/O
boundary is the correct layer; no additional finding.

## Verification record

- Clean exported `d39b747`, excluding browser-only `test_ui.py` because the sandbox forbids localhost
  binds and Chromium Mach ports: **1,199 passed, 4 deselected**.
- Contract-focused `test_log_levels.py`, `test_leader.py`, `test_logincapture_loop.py`, and
  `test_activity.py`: **101 passed**, including all **22** subprocess log-level cases.
- `test_ui.py` attempt: 149 setup errors, all from sandbox `PermissionError`/Chromium
  `MachPortRendezvous ... Permission denied`; no assertion failure. No browser UI file is in this
  commit; Helm was exercised directly for the chart-facing guard.
- Mutation matrix, run against the clean exported commit with runtime replacement and explicit
  restoration: C2, I3, I6, I7, L3/B3, and D1 each **failed before, passed after, restored true**.
