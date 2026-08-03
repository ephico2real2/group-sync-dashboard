# How the app talks to SQLite, and what it would take to swap it

Answering: *how do you connect to the SQLite layer currently, and is it designed so we can
decouple later?*

Short answer: **the seam is now declared and enforced.** Swapping the engine is a
contained job. Swapping it without also changing the deployment model is not, and that is
the part worth knowing before anyone plans it.

This document originally described a seam that existed by accident. Since then the
`refactor/storage-seam` branch turned it into a contract:

* `gsd/storage.py` declares `StorageBackend`, the Protocol a second implementation must
  satisfy — and nothing more.
* `tests/test_storage_seam.py` enforces it with an AST check per module: no driver import
  and no SQL outside the backend, and `Store` must still satisfy the Protocol.
* The three SQLite nouns that leaked onto the public surface — `wal_bytes()`,
  `maybe_checkpoint()`, `journal_mode` — are private again, behind engine-neutral
  `maintain()` and `health()`.

Everything below is measured, not asserted.

---

## 1. How the connection actually works

One class, `gsd/store.py::Store`, constructed in exactly one place:

```
gsd/api.py#STATIC_DIR    store = Store(settings.db_path, busy_timeout_ms=…, …)
```

That single construction site is the whole dependency-injection story. `Poller`,
`DashboardCollector` and `ActivityRecorder` all receive the instance; none of them creates
one. Replacing the implementation means changing one line plus whatever the constructor
signature becomes.

Inside, the connection model is deliberate and is documented at `store.py#SCHEMA`:

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

### 3.2 SQLite concepts on the public API — FIXED

This was the real leak. Six call sites outside the store knew the engine, because the
method names said so: the poller called `maybe_checkpoint()`, and the collector read
`wal_bytes()`, `checkpoint_busy_total` and `journal_mode` off the store directly.

Now:

```
gsd/poller.py    self.store.maintain()     # "do your upkeep"; SQLite checkpoints, others may not
gsd/metrics.py   health = self.store.health()   # one call, three metrics, no engine nouns
```

The metric NAMES still say `sqlite`, deliberately. They are accurate today, and they appear
in shipped alert rules (`templates/monitoring.yaml`) — renaming them is an operator-visible
breaking change that belongs with an actual engine change, not before it. The difference is
that the rename is now confined to a few lines of `metrics.py` instead of requiring the
poller and collector to be rewritten as well.

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

1. ~~**Break the metric/API leak first**~~ — done. `maintain()` and `health()` replaced the
   engine nouns; the metric-name migration is deferred to the engine change and is now a
   one-file edit.
2. ~~**Extract the contract.**~~ — done. `gsd/storage.py::StorageBackend`, enforced by
   `tests/test_storage_seam.py`.
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
- The Protocol is structural, not nominal: `Store` satisfies it by having the right
  methods, and nothing forces a future implementation to inherit from it. The seam test
  checks `isinstance(Store(...), StorageBackend)`, which catches drift in the existing
  backend but cannot make someone write the second one correctly.
- `runtime_checkable` Protocols check method NAMES, not signatures. A backend with
  `groups(self, cluster)` instead of `groups(self, cluster_id, state="all")` would still
  pass `isinstance`. The conformance guarantee comes from running the existing test suite
  against the new backend, not from the Protocol.
- The former caveat — "one `import sqlite3` in `api.py` would end it and no test would
  fail" — no longer holds. That exact edit now fails
  `test_no_module_imports_a_database_driver[api.py]`, which was verified by making it.
