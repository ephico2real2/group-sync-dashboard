# How the app talks to SQLite, and what it would take to swap it

Answering: *how do you connect to the SQLite layer currently, and is it designed so we can
decouple later?*

Short answer: **the call sites are already decoupled; the operational surface is not.**
Swapping the engine is a contained job. Swapping it without also changing the deployment
model is not, and that is the part worth knowing before anyone plans it.

Everything below is measured against the tree at `81b91142cb`, not asserted.

---

## 1. How the connection actually works

One class, `gsd/store.py::Store`, constructed in exactly one place:

```
gsd/api.py:34    store = Store(settings.db_path, busy_timeout_ms=…, …)
```

That single construction site is the whole dependency-injection story. `Poller`,
`DashboardCollector` and `ActivityRecorder` all receive the instance; none of them creates
one. Replacing the implementation means changing one line plus whatever the constructor
signature becomes.

Inside, the connection model is deliberate and is documented at `store.py:212`:

| | |
|---|---|
| **Writer** | one `sqlite3.Connection`, every write serialised behind a `threading.RLock` |
| **Readers** | one connection per thread, created lazily, never taking the write lock |
| **Why** | WAL gives a reader a consistent committed snapshot without blocking the writer. Before this split, exactly one read completed during a 0.92s bulk write. |
| **`:memory:`** | special-cased to reuse the writer connection, because each `:memory:` connection is its own empty database |

## 2. What is already clean

Measured, not estimated:

| Check | Result |
|---|---|
| References to `sqlite3` / `PRAGMA` / `.db` **outside** `store.py` | **0** |
| Raw SQL statements outside `store.py` | **0** (all 50 are inside it) |
| Public methods on `Store` | **31** |
| Places that construct a `Store` | **1** |

Callers speak in domain verbs, never SQL — `record_sync_event`, `replace_group_state`,
`sync_members`, `groupsyncs`, `binding_findings`, `record_user_activity`. That is a
repository interface in everything but the `abc` declaration. If you wanted a
`PostgresStore`, the 31 method signatures are the contract, and nothing above the store
would need to know.

**So the honest answer to "did you design it to decouple later" is: the seam exists and is
respected.** It was not built for engine-swapping — it was built so the locking story
lived in one file — but it produces the same shape.

## 3. What would actually leak

Four things, in increasing order of annoyance.

### 3.1 Non-portable SQL — contained, mechanical

All inside `store.py`:

| Construct | Count | Postgres equivalent |
|---|---|---|
| `ON CONFLICT … DO UPDATE` | 6 | works as-is |
| `PRAGMA …` | 7 | delete; server-side config |
| `AUTOINCREMENT` | 2 | `GENERATED … AS IDENTITY` / `BIGSERIAL` |
| `INSERT OR IGNORE` | 1 | `ON CONFLICT DO NOTHING` |
| two-arg `min()` / `max()` | in `record_user_activity` | `LEAST()` / `GREATEST()` |

Also `sqlite3.Row` as the row factory, and `?` placeholders rather than `%s`. None of this
is hard; it is a day of careful work with the existing test suite as the oracle.

### 3.2 SQLite concepts on the public API — the real leak

Six call sites outside the store know that storage is SQLite, because the *method names and
metrics say so*:

```
gsd/poller.py:241    self.store.maybe_checkpoint()
gsd/metrics.py:89    gsd_sqlite_wal_bytes          <- store.wal_bytes()
gsd/metrics.py:98    gsd_sqlite_checkpoint_busy_total
gsd/metrics.py:116   gsd_sqlite_wal_enabled        <- store.journal_mode
```

`wal_bytes()` and `maybe_checkpoint()` are on the 31-method public surface, and three
Prometheus metrics carry `sqlite` in their **names** — which means they are also in the
alert rules (`templates/monitoring.yaml`) and in any dashboard anyone has built on them.
Renaming a metric is a breaking change for whoever is alerting on it.

If decoupling ever becomes real, this is the piece to fix *first and independently*: give
the store a generic health surface (`storage_health() -> dict`) and let the collector
decide what to export, so the engine name stops appearing in the metric namespace.

### 3.3 Configuration — visible to operators

`config.sqlite.{busyTimeoutMs, readerBusyTimeoutMs, synchronous, walCheckpointMb}` is a
documented, supported part of `values.yaml`, mirrored into the ConfigMap and into
`Settings`. Those keys are engine-specific by definition. They would need a deprecation
window, not a rename.

### 3.4 The deployment model — the expensive part

This is the one that matters, and it is not in `store.py` at all.

**SQLite being a single-writer file is the premise of the whole deployment design:**

- `replicaCount: 1` is the recommendation, and the reason given is a shared database file.
- Leader election exists so only one pod writes.
- Three Helm `fail` guards exist to make "two pods, one file" unrenderable.
- `strategy: Recreate` at one replica exists so an outgoing and incoming pod never overlap.
- The RWX-vs-`ReadWriteOncePod` argument, the WAL-on-NFS warning, and the
  `GroupSyncDashboardWalDisabled` alert all exist for the same reason.

Move to Postgres and **all of that becomes dead weight** — you would want to delete the
leader election, drop the guards, allow `RollingUpdate`, and scale horizontally, because
the reason for each of them is gone. That is a much larger change than swapping the store,
and it is mostly in the chart rather than in Python.

## 4. What I would do if this became a real requirement

In this order, because each step is independently useful:

1. **Break the metric/API leak first** (§3.2). Rename `wal_bytes`/`maybe_checkpoint` behind
   a neutral `storage_health()` / `maintain()`, and decide the metric-naming migration.
   Do this while still on SQLite, so it is a refactor with no behaviour change.
2. **Extract the contract.** Turn the 31 methods into a `Protocol` and type the callers
   against it. Cheap, and it makes the second implementation's job unambiguous.
3. **Write the second implementation against the existing tests.** The suite (234 tests)
   is engine-agnostic wherever it goes through `Store`, so it becomes the conformance
   suite. Two known exceptions to fix: `test_sqlite_locking.py` is deliberately
   engine-specific, and the `:memory:` fixture would need a real database.
4. **Only then** revisit the chart, and delete what SQLite forced on it.

## 5. What I would not claim

- Nobody has tried this, so §3.1's "day of careful work" is an estimate, not a measurement.
- The `Store` methods were designed for the app's needs, not for portability. Some are
  wholesale-replace operations (`replace_group_state`) shaped by the fact that a SQLite
  delete-then-insert inside one transaction is cheap. On a network database, those become
  the obvious performance problem, and a few would want rewriting rather than porting.
- There is no abstract base class, `Protocol`, or interface today. The decoupling described
  here is a property of how the code is *used*, which convention currently protects and
  nothing enforces. A single `import sqlite3` in `api.py` would end it, and no test would
  fail.
