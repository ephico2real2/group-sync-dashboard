"""SQLite store (PLAN §10).

`sync_event` is the whole point of the store: the API keeps no sync history, so a timeline
exists only if we accumulate it (PLAN §2). Everything else is current-state cache that could
in principle be re-fetched, and is kept only so the API can answer without blocking on a
cluster round-trip.

Two tables here are not in PLAN §10 and are additions the first slice found it needed:

* ``groupsync_state`` — §10 stores group state but not CR state, yet §11's groupsync list
  must return schedule and filter for a CR that has *never* synced and so has no sync_event.
* ``poll_outcome`` — §11's ``GET /api/clusters`` returns ``reachable``/``last_poll``/``error``,
  which §12 step 7 computes but §10 gives nowhere to put.
"""

from __future__ import annotations

import logging
import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

from .storage import SqliteHealth, StorageHealth  # noqa: F401
from .kpi.predicates import GROUP_EMPTY, GROUP_UNATTRIBUTED, qualified
from .kube import SYSTEM_GROUP_PREFIX
from .timeutil import now_iso

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cluster (
    id                  TEXT PRIMARY KEY,   -- the configured name; used in API paths
    api_url             TEXT NOT NULL,
    enabled             INTEGER NOT NULL DEFAULT 1
);

-- One row per OBSERVED sync, written only when lastSyncSuccessTime CHANGES (PLAN §6).
CREATE TABLE IF NOT EXISTS sync_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    groupsync_namespace TEXT NOT NULL,
    synced_at           TEXT NOT NULL,  -- the operator's timestamp
    observed_at         TEXT NOT NULL,  -- ours; observed_at - synced_at is OUR lag
    schedule            TEXT,           -- snapshot: schedules change, old rows must stay readable
    group_count         INTEGER,
    UNIQUE(cluster_id, groupsync_name, synced_at)
);
CREATE INDEX IF NOT EXISTS sync_event_lookup
    ON sync_event(cluster_id, groupsync_name, synced_at DESC);
-- Retention's index (prune_sync_events, history_retained_since): the prune subselect is a
-- range seek and MIN(observed_at) an index seek. Without it an EMPTY prune is a full scan
-- every poll. An index, not a migration: CREATE INDEX IF NOT EXISTS applies at startup on an
-- existing database, which ALTER TABLE ADD COLUMN does not (see _MIGRATIONS).
CREATE INDEX IF NOT EXISTS sync_event_by_time
    ON sync_event(cluster_id, observed_at);

-- Current CR state, replaced each poll.
CREATE TABLE IF NOT EXISTS groupsync_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    namespace           TEXT NOT NULL,
    schedule            TEXT,
    ldap_filter         TEXT,
    last_sync_at        TEXT,
    generation          INTEGER,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name, namespace)
);

-- The sync-provider label values a CR's groups carry, replaced with the CR state above and
-- in the same transaction. A separate table because a CR may declare SEVERAL providers and
-- each produces its own label value; the single `provider_key` column this replaces held
-- only the first, so every group of every later provider had no owner and so was never
-- staleness-checked. Databases created before this keep that column, unwritten and unread:
-- groupsync_state is a per-poll cache, so a vestigial NULL column costs nothing and there
-- is no migration step to get wrong.
CREATE TABLE IF NOT EXISTS groupsync_provider (
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    groupsync_namespace TEXT NOT NULL,
    provider_key        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, groupsync_name, groupsync_namespace, provider_key)
);
CREATE INDEX IF NOT EXISTS groupsync_provider_key
    ON groupsync_provider(cluster_id, provider_key);

-- Current group state, replaced each poll; history not kept (PLAN §10).
CREATE TABLE IF NOT EXISTS group_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    member_count        INTEGER NOT NULL,
    sync_provider       TEXT,
    group_synced_at     TEXT,           -- the group's OWN sync-time annotation
    ldap_uid            TEXT,
    observed_at         TEXT NOT NULL,
    cliff_silence       TEXT,           -- kube.CLIFF_SILENCE_ANNOTATION, raw; migration 8
    PRIMARY KEY(cluster_id, name)
);

-- Last reconcile FAILURE per CR (PLAN §2.1). Separate from sync_event because failures and
-- successes advance independently: a months-old error coexists with a 60s-old success.
CREATE TABLE IF NOT EXISTS reconcile_error (
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    failed_at           TEXT,
    observed_generation INTEGER,
    message             TEXT,
    PRIMARY KEY(cluster_id, groupsync_name)
);

CREATE TABLE IF NOT EXISTS poll_outcome (
    cluster_id          TEXT PRIMARY KEY,
    observed_at         TEXT NOT NULL,
    status              TEXT NOT NULL,  -- ok | auth_failed | forbidden | unreachable
    message             TEXT
);

-- Current membership. Unlike group_state this is NOT wholly replaced each poll: first_seen_at
-- must survive, or "when did this user join?" resets on every cycle and answers nothing.
CREATE TABLE IF NOT EXISTS group_member (
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    first_seen_at       TEXT NOT NULL,  -- when WE first observed them, not when LDAP added them
    last_seen_at        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, group_name, user_name)
);
CREATE INDEX IF NOT EXISTS group_member_by_user
    ON group_member(cluster_id, user_name);

-- Display names for users who have logged in. ONE row per person, joined onto the tables that
-- name them — deliberately not a column on group_member or user_binding, both of which are
-- per-membership and per-binding, so a name there would duplicate N times per person. On
-- group_member it would also outlive its truth: that table is diff-and-append so first_seen_at
-- survives, meaning a name removed upstream would never be cleared.
--
-- Since the Users tab was re-sourced (docs/DESIGN_users_tab_logins.md) this holds EVERY User
-- object, not only the ones with a name: the row IS the fact that the person has logged in, because
-- OpenShift creates the object at first login and never before. full_name is therefore nullable —
-- a User whose provider supplies no name is still a user — and created_at is the first login for a
-- provider-created User. providers is a JSON list of identity-provider names taken from the
-- prefix of each identities[] entry; has_identity=0 marks an object created by hand (`oc create
-- user`) that nobody has ever logged in as.
--
-- Wholly replaced each poll, like group_state and user_binding: an upsert would leave a row
-- behind after the User object is deleted. When the list call is FORBIDDEN the poller does not
-- touch this table and writes ocp_user_status instead, so the API can say "forbidden" rather
-- than letting an empty table read as "nobody has logged in".
CREATE TABLE IF NOT EXISTS ocp_user (
    cluster_id          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    full_name           TEXT,
    created_at          TEXT,
    providers           TEXT NOT NULL DEFAULT '[]',
    has_identity        INTEGER NOT NULL DEFAULT 0,
    identity_created_at TEXT,           -- migration 9: the earliest Identity creationTimestamp naming the User; NULL when not read
    identities          TEXT NOT NULL DEFAULT '[]',  -- migration 10: the raw Identity names (`<provider>:<providerUserName>`), for the audit-log source's identity match
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, user_name)
);

-- Whether the last poll could read the User objects at all. One row per cluster; state is 'ok'
-- or 'forbidden'. Absent means no poll has reported yet.
CREATE TABLE IF NOT EXISTS ocp_user_status (
    cluster_id          TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    observed_at         TEXT NOT NULL
);

-- Whether the last poll could read the Identity objects (rbac.identities). 'ok' | 'forbidden' |
-- 'off' (the read is not switched on). Absent means no poll has reported yet.
CREATE TABLE IF NOT EXISTS ocp_identity_status (
    cluster_id          TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    observed_at         TEXT NOT NULL
);

-- Membership changes, append-only. The API has no history (PLAN §2), and a user quietly
-- dropping out of a group is exactly the invisible absence this dashboard exists for:
-- nothing logs it, no event fires, and the group still looks healthy afterwards.
CREATE TABLE IF NOT EXISTS membership_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    change              TEXT NOT NULL,  -- added | removed
    observed_at         TEXT NOT NULL,
    group_synced_at     TEXT,           -- the group's own sync-time when we saw the change
    -- 1 on a cluster's FIRST observation: the rows are "first seen by this dashboard", not a
    -- change anyone made. Measured on CRC before this existed: 76, 87 and 5 "added" rows in one
    -- instant per cluster, read by the landing page as a bulk onboarding (#175).
    baseline            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS membership_event_lookup
    ON membership_event(cluster_id, group_name, id DESC);
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);
-- Shared by the group-count cliff (Store.group_count_changes: a window of events) and retention
-- (prune_membership_events' subselect is a range seek, history_retained_since's MIN an index
-- seek). Without it both are a scan of every event the cluster has ever recorded. Added by B4
-- as migration 8; B2 reuses it.
CREATE INDEX IF NOT EXISTS membership_event_by_time
    ON membership_event(cluster_id, observed_at);

-- One row per (binding, Group subject). Current state, replaced each refresh: a binding
-- is fully re-readable from the API, so nothing here is irreplaceable history.
CREATE TABLE IF NOT EXISTS rbac_group_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,   -- Role | ClusterRole
    role_name           TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    observed_at         TEXT NOT NULL,
    -- Provenance (migration 1). managed_source is the policy operator's config-source
    -- label; NULL means hand-made. exception is the operator-acknowledged justification
    -- for a deliberate hand-made binding, carried as an annotation on the object itself.
    managed_source      TEXT,
    exception           TEXT,
    -- Migration 2: whether the object already carries the dashboard's own unmanaged
    -- audit label — read back from the cluster each refresh, so it is the cluster's
    -- truth, not a local counter that can drift from it.
    audit_stamped       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
);

-- Bindings that name a USER directly, rather than a group. Replaced each refresh.
--
-- The governance violation in its purest form: access tied to a person instead of to an
-- enterprise-managed group. It survives offboarding — removing someone from an LDAP group
-- revokes their access everywhere, while a direct binding keeps granting to a name nobody
-- reviews — and it is invisible to every group-based audit, this dashboard's own included
-- until now.
--
-- is_platform separates cluster-internal identities (system:*, kube-apiserver, the node
-- identities) from people. Measured on the reference cluster: 36 direct-user bindings, 22
-- of them platform. They are STORED rather than filtered at ingest so the UI can report
-- what it excluded — a tool that silently drops rows cannot be trusted about the ones it
-- keeps.
CREATE TABLE IF NOT EXISTS user_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,
    role_name           TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    is_platform         INTEGER NOT NULL DEFAULT 0,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, user_name)
);
CREATE INDEX IF NOT EXISTS user_binding_by_namespace
    ON user_binding(cluster_id, binding_namespace);

-- Binding changes, append-only — the bindings' membership_event (#167, ruled 2026-09-17).
-- rbac_group_binding and user_binding are replaced every refresh, so a RoleBinding created or
-- deleted between two refreshes left no trace: a namespace had no history, and the landing
-- page's "what changed" was blind to the grant that actually changed what a person can do.
-- One row per (binding, subject) that appeared or disappeared; a role change on the same
-- binding is a `removed` and an `added`, so there is no third verb to explain.
CREATE TABLE IF NOT EXISTS binding_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    subject_kind        TEXT NOT NULL,   -- Group | User
    subject_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,
    role_name           TEXT NOT NULL,
    is_platform         INTEGER NOT NULL DEFAULT 0,
    change              TEXT NOT NULL,   -- added | removed
    baseline            INTEGER NOT NULL DEFAULT 0,  -- 1 on the cluster's first observation
    observed_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS binding_event_by_namespace
    ON binding_event(cluster_id, binding_namespace, id DESC);
CREATE INDEX IF NOT EXISTS binding_event_by_subject
    ON binding_event(cluster_id, subject_kind, subject_name, id DESC);
-- Retention's index (prune_binding_events, history_retained_since), as for membership_event.
CREATE INDEX IF NOT EXISTS binding_event_by_time
    ON binding_event(cluster_id, observed_at);

-- THE FIRST-OBSERVATION MARKER, one row per (cluster, stream), consumed once and kept for good.
-- A baseline has to mean "existed before this dashboard started watching", and the only honest
-- way to know that is to remember that we looked — not to infer it from what is in the tables:
-- an empty first poll leaves no rows, so the NEXT poll would read as the first observation
-- (Codex, review of #177: `first_empty=0 … second_baseline=1`), and retention that emptied a
-- table would reopen the baseline. streams: membership | binding:Group | binding:User.
CREATE TABLE IF NOT EXISTS observation_state (
    cluster_id          TEXT NOT NULL,
    stream              TEXT NOT NULL,
    PRIMARY KEY(cluster_id, stream)
);

-- Health of the namespace-configuration-operator's CRs, replaced on the binding cadence.
-- Reconcile conditions ONLY: these CRs template the RoleBindings that give synced groups
-- their access, so a failing one means RBAC silently stops reconciling — but they have no
-- schedule, so there is no staleness to compute and no timeline worth accumulating.
CREATE TABLE IF NOT EXISTS operator_config_state (
    cluster_id          TEXT NOT NULL,
    kind                TEXT NOT NULL,   -- NamespaceConfig | GroupConfig
    name                TEXT NOT NULL,
    error_at            TEXT,
    error_message       TEXT,
    success_at          TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, kind, name)
);

-- Whether the operator's CRDs even exist on the cluster, auto-detected each refresh.
-- Absent (0) is a different truth from "present with zero CRs", and the UI must not
-- render "all healthy" for a concept the cluster does not have.
CREATE TABLE IF NOT EXISTS operator_config_presence (
    cluster_id          TEXT PRIMARY KEY,
    present             INTEGER NOT NULL,
    observed_at         TEXT NOT NULL
);

-- Same question for the group-sync-operator's own CRD. Tracked for the same reason and one
-- more: a cluster with no GroupSync CRD still HAS groups, and the dashboard reports them, so
-- "0 CRs" on the Overview is indistinguishable from "the operator is not installed" unless
-- absence is recorded. It used to be unmissable for the wrong reason — the poll failed and the
-- cluster showed `unreachable` — which hid every group on the cluster.
CREATE TABLE IF NOT EXISTS groupsync_presence (
    cluster_id          TEXT PRIMARY KEY,
    present             INTEGER NOT NULL,
    observed_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rbac_binding_by_group
    ON rbac_group_binding(cluster_id, group_name);

-- Provenance: group names we have EVER seen carrying an operator sync-provider label.
-- This is what separates "this binding's group broke" from "this binding names something
-- that never existed". Append-only and never replaced — the whole point is that it
-- outlives the Group object's disappearance.
CREATE TABLE IF NOT EXISTS managed_group_seen (
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    sync_provider       TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, group_name)
);

-- Who used the dashboard, aggregated to one row per user per UTC day.
--
-- Deliberately NOT a per-request access log. Aggregating bounds the table at
-- users x days — a hundred users for three years is ~110k rows — where a request log grows
-- without limit and would need the retention policy the event tables still lack. It also
-- keeps this to "who uses this and when", not "who looked at whose membership": the
-- dashboard shows group membership, and a page-view trail of colleagues reading it is a
-- materially different thing to hold.
--
-- Identity comes from the oauth-proxy's X-Forwarded-User header, so rows exist only when
-- the proxy is enabled. With it disabled the app binds 0.0.0.0 with no authentication at
-- all and the header would be trivially forgeable — see activity.py.
CREATE TABLE IF NOT EXISTS dashboard_user_activity (
    user_name           TEXT NOT NULL,
    day                 TEXT NOT NULL,  -- UTC date, YYYY-MM-DD
    email               TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    request_count       INTEGER NOT NULL,
    PRIMARY KEY(user_name, day)
);
CREATE INDEX IF NOT EXISTS dashboard_user_activity_by_day
    ON dashboard_user_activity(day DESC);

-- Login attempts read off the oauth-server's logs. One row per ATTEMPT, not per log line: a single
-- attempt writes several lines across two source files, and gsd/loginlog.py correlates them.
--
-- pod_name IS IN THE UNIQUE KEY, and that is the whole point of it. Reads overlap deliberately (a
-- sinceSeconds window plus a settle horizon), so the same line is seen more than once and must not
-- insert twice — the key suppresses that, because a line stays in its own pod's log and is never
-- copied to a peer. Without pod_name the key ALSO collapses the cross-replica same-instant pair: two
-- requests for the same username, same outcome and same microsecond, one served by each replica.
-- Measured in scratch SQLite: (pod-a,alice,T,success), a re-read of it, then the independent
-- (pod-b,alice,T,success) gives [1,0,1] and two rows with pod_name in the key; [1,0,0] and one row
-- without it — a genuine second attempt silently dropped.
--
-- `at` is the kubelet RFC3339 stamp with microseconds, stored UTC and rendered in the configured
-- zone. klog's own stamp on the same line carries no year and no timezone, so it cannot be resolved
-- to an instant without guessing both. `observed_at` is when WE read it — not the same thing, and
-- worth keeping when a pod's clock and ours disagree.
CREATE TABLE IF NOT EXISTS login_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    outcome             TEXT NOT NULL,
    at                  TEXT NOT NULL,
    provider            TEXT,
    ldap_result_code    INTEGER,
    detail              TEXT,
    observed_at         TEXT NOT NULL,
    -- 'pod-log' or 'audit-log' (migration 10). For an audit row pod_name carries the NODE the
    -- file was read from: the same "unit of log" role in the dedup key.
    source              TEXT NOT NULL DEFAULT 'pod-log',
    -- The audit event's own per-request id. Unique per cluster where present, so a re-read is
    -- free; SET on a pod-log row when an audit event corresponds to it, so one login read from
    -- both sources is one row that keeps its LDAP cause.
    audit_id            TEXT,
    -- What KIND of attempt the audit log recorded (migration 10; docs/specs/SPEC_D1 grounding note):
    -- credential (POST /login[/<idp>] — the interactive form), cli (GET /oauth/authorize with
    -- client_id=openshift-challenging-client — `oc login`), session (GET /oauth/authorize by any
    -- other client — an existing session re-authorising to the console, this dashboard, GitOps).
    -- Pod-log rows are credential attempts by construction.
    kind                TEXT NOT NULL DEFAULT 'credential',
    -- The OAuth client a cli/session row authorised to — the one query parameter kept.
    client_id           TEXT,
    -- The configured identity provider the username resolves to through its Identity object,
    -- matched case-insensitively; NULL for a name that resolves to nothing (kept, visibly
    -- unmatched: a failed attempt against a name that does not exist is still an attempt).
    identity_match      TEXT,
    -- What the audit record carries about a failure, and nothing invented: the HTTP status and the
    -- response message when there is one ("Authentication failed, attempted: basic" on CLI failures;
    -- browser failures are a 302 back to the form with no message).
    status_code         INTEGER,
    error_message       TEXT,
    user_agent          TEXT,
    UNIQUE(cluster_id, pod_name, user_name, at, outcome)
);
CREATE INDEX IF NOT EXISTS login_event_lookup ON login_event(cluster_id, at DESC);
CREATE INDEX IF NOT EXISTS login_event_by_user ON login_event(cluster_id, user_name, at DESC);
-- login_event_by_audit_id (UNIQUE on cluster_id, audit_id WHERE audit_id IS NOT NULL) is created by
-- migration 10 ONLY, not here: SCHEMA runs before _migrate, and on a database from before 0.17.0 the
-- column does not exist yet, so an index on it here raised "no such column: audit_id" and aborted
-- the whole script — the pod could not start on the one upgrade path that matters. Measured on the
-- reference cluster, 2026-09-06. A fresh database gets the index when migration 10 replays.

-- Where each audit FILE on each node has been read to, in bytes. Per file because rotation
-- renames the current file and starts a new one; the cursor follows the bytes, not the name.
-- settled_through is the newest event stamp read from that file — the per-node liveness that
-- gsd_login_capture_audit_settled_timestamp_seconds exports. complete=1 marks a rotated file
-- read to its end (immutable from then on); byte_offset=-1 marks one skipped by retention.
-- head_sha256/head_len fingerprint the file's first bytes so a resume can tell the file it read
-- from a new one under the same name (gsd/auditlog.py#FINGERPRINT_BYTES): audit.log after
-- rotation, with the size alone unable to say so once the new file has grown past the cursor.
CREATE TABLE IF NOT EXISTS login_audit_cursor (
    cluster_id          TEXT NOT NULL,
    node_name           TEXT NOT NULL,
    file_name           TEXT NOT NULL,
    byte_offset         INTEGER NOT NULL,
    head_sha256         TEXT,
    head_len            INTEGER NOT NULL DEFAULT 0,
    settled_through     TEXT,
    complete            INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY(cluster_id, node_name, file_name)
);

-- How far each POD's log has been settled. Per pod because pods are read independently and every roll
-- replaces them; one cluster-wide value would let a lagging pod hold back the others, or a fast pod
-- advance past lines a slow one has not written yet.
CREATE TABLE IF NOT EXISTS login_capture_watermark (
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,
    settled_through     TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY(cluster_id, pod_name)
);

-- The PRODUCT-level boundary, deliberately NOT the watermark above.
--
-- `started_at` is the first successful read ever, set once and never moved, because it is what the UI
-- means by "watching since" — a sparse table must read as "nothing happened since then" rather than
-- as "this feature is broken". The per-pod watermark cannot answer that: it is per pod, it moves
-- constantly, and dead-pod rows get pruned, which would erase the evidence of when watching began.
-- `last_read_at` is liveness: if it stops advancing, capture has stopped.
CREATE TABLE IF NOT EXISTS login_capture_status (
    cluster_id          TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    last_read_at        TEXT NOT NULL
);

-- WHICH GROUP GATES AUTHENTICATION, and where we learned it from.
--
-- One row per cluster because one cluster has one login gate. `source` is stored rather than
-- inferred so the UI can say whether the DN was configured or discovered — an operator debugging
-- 'why is this the wrong group?' needs to know which of the two to change.
--
-- `group_name` is the synced OpenShift Group whose openshift.io/ldap.uid equals `dn`, resolved at
-- poll time. NULL means the DN is known and the group is NOT synced — which is not an error but a
-- prerequisite that has not been met, and the difference matters: without the Group object there
-- is no membership to compare against, and the panel has to say so rather than report zero.
CREATE TABLE IF NOT EXISTS cluster_access_group (
    cluster_id          TEXT PRIMARY KEY,
    dn                  TEXT NOT NULL,          -- the gate group's full DN, as configured or discovered
    source              TEXT NOT NULL,          -- 'config' or 'oauth': which of the two produced it
    group_name          TEXT,                   -- the synced Group whose ldap_uid matches, if any
    observed_at         TEXT NOT NULL
);

-- Namespace objects (rbac.namespaces), for the report service's namespace report: knowing a
-- namespace EXISTS lets it attest absence. Replaced on the binding cadence. Migration 11.
CREATE TABLE IF NOT EXISTS cluster_namespace (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    created_at          TEXT,
    phase               TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name)
);
CREATE TABLE IF NOT EXISTS cluster_namespace_status (
    cluster_id          TEXT PRIMARY KEY,
    state               TEXT NOT NULL,      -- ok | forbidden
    observed_at         TEXT NOT NULL
);
-- Bounded Namespace metadata the namespace-access report selects on (migration 12). Only the
-- configured label keys, replaced whole with cluster_namespace on the binding cadence.
CREATE TABLE IF NOT EXISTS cluster_namespace_label (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    key                 TEXT NOT NULL,
    value               TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name, key),
    FOREIGN KEY(cluster_id, name) REFERENCES cluster_namespace(cluster_id, name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cnl_key_value ON cluster_namespace_label(cluster_id, key, value);
-- What the report service published about itself, PULLED by the poller from GET /report/api/usage
-- (the dashboard's API stays GET-only). One row per finished run; the id is the service's and is
-- the pull watermark. Personnel data — who generated which report — served at the USAGE tier like
-- dashboard_user_activity. No error text: a run's `error` stays on the report service.
CREATE TABLE IF NOT EXISTS report_run (
    id                  TEXT PRIMARY KEY,
    report              TEXT NOT NULL,
    cluster_id          TEXT NOT NULL,
    generated_by        TEXT NOT NULL,
    generated_by_note   TEXT NOT NULL,
    schedule            TEXT,
    status              TEXT NOT NULL,      -- done | failed
    requested_at        TEXT NOT NULL,
    finished_at         TEXT,
    sha256              TEXT,
    snapshot_stamp      TEXT,
    formats             TEXT NOT NULL,      -- JSON list
    bytes_total         INTEGER NOT NULL DEFAULT 0,
    pdf_variant         TEXT,
    pulled_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS report_run_by_time ON report_run(requested_at DESC);
CREATE INDEX IF NOT EXISTS report_run_by_user ON report_run(generated_by, requested_at DESC);

-- The daily KPI rollup (#156): one row per (cluster, UTC day, metric), written by the leader on the
-- first successful poll of each day. The counts it holds (groups, bindings, people) have NO history
-- of their own — group_state and rbac_group_binding are replaced every poll — and user-workload
-- monitoring is off by default on OpenShift, so without this an install with no Prometheus has no
-- trend at all. A handful of rows per cluster per day; pruned after KPI_DAILY_RETENTION_DAYS.
CREATE TABLE IF NOT EXISTS kpi_daily (
    cluster_id          TEXT NOT NULL,
    day                 TEXT NOT NULL,      -- YYYY-MM-DD, UTC
    metric              TEXT NOT NULL,
    value               REAL NOT NULL,
    PRIMARY KEY(cluster_id, day, metric)
);
"""


# -- schema migrations ----------------------------------------------------------------
#
# THIS PROJECT'S FIRST REAL MIGRATION MECHANISM, built because the implicit one silently
# does nothing: the schema is applied with CREATE TABLE IF NOT EXISTS, so on an EXISTING
# database a column added to the SCHEMA string simply never appears — the table already
# exists, the statement no-ops, and the first SELECT naming the new column crashes at
# runtime on upgraded deployments while working perfectly on fresh ones. Measured before
# this existed, not assumed.
#
# PRAGMA user_version is the cursor: 0 on any database created before this mechanism,
# incremented once per applied step. Steps run in order, inside the writer's transaction,
# at startup, before anything reads. They must be written to be safe on a database that
# already has the change (fresh databases get the new SCHEMA and then replay migrations
# against it), which for ALTER TABLE ADD COLUMN means tolerating "duplicate column name".
# A cluster that holds rows of a stream has been observed. Idempotent (INSERT OR IGNORE over the
# primary key) and cheap (every DISTINCT cluster_id is led by an index), so it runs at EVERY open
# and not only inside migration 14: a build without the marker (1f55cb1, which the lab ran) writing
# rows for a new cluster in between would otherwise leave rows with no marker — and, since an
# applied migration never re-runs, that cluster's next real additions would be flagged baseline
# (OB1, review 2 of #177). Three sources prove a membership observation that left no member behind
# — group_state (groups polled with zero members; Grok), groupsync_presence and poll_outcome
# status='ok', both written in the same poll_snapshot transaction as sync_members (Codex, OB1) —
# so a cluster successfully polled EMPTY is marked too. The binding streams have no such witness
# (refresh_bindings deliberately records no poll outcome), so for them rows are the only proof.
_OBSERVATION_SEEDS: tuple[str, ...] = (
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'membership' FROM membership_event""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'membership' FROM group_member""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'membership' FROM group_state""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT cluster_id, 'membership' FROM groupsync_presence""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT cluster_id, 'membership' FROM poll_outcome WHERE status = 'ok'""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'binding:Group' FROM rbac_group_binding""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'binding:User' FROM user_binding""",
    """INSERT OR IGNORE INTO observation_state(cluster_id, stream)
       SELECT DISTINCT cluster_id, 'binding:' || subject_kind FROM binding_event
        WHERE subject_kind IN ('Group', 'User')""",
)


def _seed_observation_markers(conn: sqlite3.Connection) -> None:
    """Mark every (cluster, stream) the store already holds evidence for. See _OBSERVATION_SEEDS."""
    for sql in _OBSERVATION_SEEDS:
        conn.execute(sql)


_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "rbac_group_binding gains provenance: managed_source + exception",
        [
            "ALTER TABLE rbac_group_binding ADD COLUMN managed_source TEXT",
            "ALTER TABLE rbac_group_binding ADD COLUMN exception TEXT",
        ],
    ),
    (
        2,
        "rbac_group_binding records the audit stamp, for stamp idempotency + healing",
        [
            "ALTER TABLE rbac_group_binding ADD COLUMN audit_stamped INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        3,
        "groupsync_presence: is the group-sync-operator's CRD installed at all",
        [
            """CREATE TABLE IF NOT EXISTS groupsync_presence (
                   cluster_id          TEXT PRIMARY KEY,
                   present             INTEGER NOT NULL,
                   observed_at         TEXT NOT NULL
               )""",
            # No backfill row. Absence of a row reads as "not yet observed", which the first
            # poll after upgrade replaces with the truth. Defaulting every existing cluster to
            # present=1 would be a guess, and defaulting to 0 would alert every cluster that
            # upgrades before it next polls.
        ],
    ),
    (
        4,
        "ocp_user: display names for users who have logged in",
        [
            """CREATE TABLE IF NOT EXISTS ocp_user (
                   cluster_id          TEXT NOT NULL,
                   user_name           TEXT NOT NULL,
                   full_name           TEXT NOT NULL,
                   observed_at         TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, user_name)
               )""",
            # IF NOT EXISTS is required, not decorative: _migrate tolerates exactly one error,
            # "duplicate column name", so a bare CREATE TABLE would raise "table already
            # exists" when this replays against a database that got it from SCHEMA.
            #
            # No backfill, and none is possible — the names live on the cluster, not in here.
            # Until the next poll every read outer-joins to NULL, which is the same thing the
            # UI already renders for a user who has never logged in.
        ],
    ),
    (
        5,
        "login_event + capture watermark and status: who logged in, and since when we were watching",
        [
            """CREATE TABLE IF NOT EXISTS login_event (
                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                   cluster_id          TEXT NOT NULL,
                   pod_name            TEXT NOT NULL,
                   user_name           TEXT NOT NULL,
                   outcome             TEXT NOT NULL,
                   at                  TEXT NOT NULL,
                   provider            TEXT,
                   ldap_result_code    INTEGER,
                   detail              TEXT,
                   observed_at         TEXT NOT NULL,
                   UNIQUE(cluster_id, pod_name, user_name, at, outcome)
               )""",
            "CREATE INDEX IF NOT EXISTS login_event_lookup ON login_event(cluster_id, at DESC)",
            """CREATE INDEX IF NOT EXISTS login_event_by_user
                   ON login_event(cluster_id, user_name, at DESC)""",
            """CREATE TABLE IF NOT EXISTS login_capture_watermark (
                   cluster_id          TEXT NOT NULL,
                   pod_name            TEXT NOT NULL,
                   settled_through     TEXT NOT NULL,
                   updated_at          TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, pod_name)
               )""",
            """CREATE TABLE IF NOT EXISTS login_capture_status (
                   cluster_id          TEXT PRIMARY KEY,
                   started_at          TEXT NOT NULL,
                   last_read_at        TEXT NOT NULL
               )""",
            # IF NOT EXISTS on every statement is required, not decorative: _migrate tolerates exactly
            # one error, "duplicate column name", so a bare CREATE would raise "table already exists"
            # on the replay against a database that got these from SCHEMA.
            #
            # No backfill, and none is possible — these logs exist only while the pod that wrote them
            # does, and nothing before capture was enabled was ever recorded anywhere. An empty table
            # on an upgraded cluster is the truth, which is exactly why login_capture_status exists:
            # so the UI can say WHEN watching began rather than implying nobody logged in.
        ],
    ),
    (
        6,
        "cluster_access_group: which group gates authentication, and how we learned it",
        [
            """CREATE TABLE IF NOT EXISTS cluster_access_group (
                   cluster_id          TEXT PRIMARY KEY,
                   dn                  TEXT NOT NULL,
                   source              TEXT NOT NULL,
                   group_name          TEXT,
                   observed_at         TEXT NOT NULL
               )""",
            # One table, no index: it is at most one row per cluster and every read is by primary key.
            #
            # Nothing to backfill. The DN comes from configuration or from the OAuth CR, and both are
            # read on the next poll — so an upgraded cluster is correct within one cycle without a
            # migration that would have to talk to a cluster to fill this in.
        ],
    ),
    (
        7,
        "ocp_user: every User object, not only the named ones; ocp_user_status",
        [
            # DROP, not ALTER. The table was a cache of display names, wholly replaced on every poll,
            # and its contents are a strict subset of what the next poll writes — so nothing in it is
            # worth carrying across, and rebuilding is the one shape that also relaxes full_name from
            # NOT NULL, which ALTER TABLE cannot do in SQLite. Until that poll the Users tab shows
            # last cycle's... nothing: an empty table for at most one poll interval, and
            # ocp_user_status is absent rather than 'ok', so the API reports the source as pending
            # instead of claiming that nobody has logged in.
            "DROP TABLE IF EXISTS ocp_user",
            """CREATE TABLE IF NOT EXISTS ocp_user (
                   cluster_id          TEXT NOT NULL,
                   user_name           TEXT NOT NULL,
                   full_name           TEXT,
                   created_at          TEXT,
                   providers           TEXT NOT NULL DEFAULT '[]',
                   has_identity        INTEGER NOT NULL DEFAULT 0,
                   observed_at         TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, user_name)
               )""",
            """CREATE TABLE IF NOT EXISTS ocp_user_status (
                   cluster_id          TEXT PRIMARY KEY,
                   state               TEXT NOT NULL,
                   observed_at         TEXT NOT NULL
               )""",
            # On a FRESH database SCHEMA has already created both tables — in the CURRENT shape,
            # later than v7's (identity_created_at, identities). The DROP removes an empty table and
            # the CREATE puts back the v7 shape, which migrations 9 and 10 then extend again by
            # ALTER (those do not raise, because the columns are absent at that point). Harmless,
            # and the replay stays idempotent (_migrate tolerates exactly one error; this raises none).
        ],
    ),
    (
        8,
        "group_state carries the cliff-silence annotation; membership_event indexed by time",
        [
            # ADD COLUMN replays with "duplicate column name" on a fresh database, which _migrate
            # tolerates. Nullable: an upgraded cluster's rows are NULL (not silenced) until its
            # next poll rewrites group_state, which is one interval away.
            "ALTER TABLE group_state ADD COLUMN cliff_silence TEXT",
            "CREATE INDEX IF NOT EXISTS membership_event_by_time "
            "ON membership_event(cluster_id, observed_at)",
        ],
    ),
    (
        9,
        "ocp_user: identity_created_at (the Identity creation time); ocp_identity_status",
        [
            # Tolerated on replay by _migrate's one allowed error, "duplicate column name".
            "ALTER TABLE ocp_user ADD COLUMN identity_created_at TEXT",
            """CREATE TABLE IF NOT EXISTS ocp_identity_status (
                   cluster_id          TEXT PRIMARY KEY,
                   state               TEXT NOT NULL,
                   observed_at         TEXT NOT NULL
               )""",
            # No backfill: Identity times arrive with the next poll that may read identities; until then
            # every row's source reads `user`, which is the truth about it.
        ],
    ),
    (
        10,
        "login_event: source, audit_id, kind, client_id, identity_match, status_code, error_message, "
        "user_agent; login_audit_cursor; ocp_user.identities — the audit-log login source (D1)",
        [
            "ALTER TABLE login_event ADD COLUMN source TEXT NOT NULL DEFAULT 'pod-log'",
            "ALTER TABLE login_event ADD COLUMN audit_id TEXT",
            "ALTER TABLE login_event ADD COLUMN kind TEXT NOT NULL DEFAULT 'credential'",
            "ALTER TABLE login_event ADD COLUMN client_id TEXT",
            "ALTER TABLE login_event ADD COLUMN identity_match TEXT",
            "ALTER TABLE login_event ADD COLUMN status_code INTEGER",
            "ALTER TABLE login_event ADD COLUMN error_message TEXT",
            "ALTER TABLE login_event ADD COLUMN user_agent TEXT",
            """CREATE UNIQUE INDEX IF NOT EXISTS login_event_by_audit_id
                   ON login_event(cluster_id, audit_id) WHERE audit_id IS NOT NULL""",
            """CREATE TABLE IF NOT EXISTS login_audit_cursor (
                   cluster_id          TEXT NOT NULL,
                   node_name           TEXT NOT NULL,
                   file_name           TEXT NOT NULL,
                   byte_offset         INTEGER NOT NULL,
                   head_sha256         TEXT,
                   head_len            INTEGER NOT NULL DEFAULT 0,
                   settled_through     TEXT,
                   complete            INTEGER NOT NULL DEFAULT 0,
                   updated_at          TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, node_name, file_name)
               )""",
            "ALTER TABLE ocp_user ADD COLUMN identities TEXT NOT NULL DEFAULT '[]'",
            # Every existing login row is a pod-log credential attempt, which the DEFAULTs state.
            # No backfill of audit_id: the correspondence is established when the audit source
            # first reads — a backfill that walks past every row already here. ocp_user's
            # identities fill at the next poll (replace_users rewrites every row).
        ],
    ),
    (
        11,
        "reporting: Namespace objects for absence attestation, and the runs the report service published",
        [
            # Namespace objects (rbac.namespaces), replaced on the binding cadence. Exists only to let
            # the namespace report attest absence — "this namespace exists and has no grants" —
            # rather than "none observed". Kept from the first C3 design.
            """CREATE TABLE IF NOT EXISTS cluster_namespace (
                   cluster_id          TEXT NOT NULL,
                   name                TEXT NOT NULL,
                   created_at          TEXT,
                   phase               TEXT,
                   observed_at         TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, name)
               )""",
            """CREATE TABLE IF NOT EXISTS cluster_namespace_status (
                   cluster_id          TEXT PRIMARY KEY,
                   state               TEXT NOT NULL,      -- ok | forbidden
                   observed_at         TEXT NOT NULL
               )""",
            # What the report service published about itself, PULLED by the poller from
            # GET /report/api/usage (the dashboard's API stays GET-only). One row per finished run;
            # the id is the service's (chronologically sortable) and is the pull watermark. Personnel
            # data — who generated which report — so it is served at the USAGE tier, like
            # dashboard_user_activity. No error text: a run's `error` stays on the report service.
            """CREATE TABLE IF NOT EXISTS report_run (
                   id                  TEXT PRIMARY KEY,
                   report              TEXT NOT NULL,
                   cluster_id          TEXT NOT NULL,
                   generated_by        TEXT NOT NULL,
                   generated_by_note   TEXT NOT NULL,
                   schedule            TEXT,
                   status              TEXT NOT NULL,      -- done | failed
                   requested_at        TEXT NOT NULL,
                   finished_at         TEXT,
                   sha256              TEXT,
                   snapshot_stamp      TEXT,
                   formats             TEXT NOT NULL,      -- JSON list
                   bytes_total         INTEGER NOT NULL DEFAULT 0,
                   pdf_variant         TEXT,
                   pulled_at           TEXT NOT NULL
               )""",
            "CREATE INDEX IF NOT EXISTS report_run_by_time ON report_run(requested_at DESC)",
            "CREATE INDEX IF NOT EXISTS report_run_by_user ON report_run(generated_by, requested_at DESC)",
        ],
    ),
    (
        12,
        "reporting: bounded Namespace metadata (labels) the namespace-access report selects on",
        [
            # Only the configured label keys, replaced whole each cycle alongside cluster_namespace
            # (docs/DESIGN_reporting_auditors_and_ns_selector.md §3.4). A child table, so adding a key
            # is a values change with no further migration. ON DELETE CASCADE keeps it consistent if a
            # namespace row is removed; replace_namespaces also clears it explicitly in the same write.
            """CREATE TABLE IF NOT EXISTS cluster_namespace_label (
                   cluster_id          TEXT NOT NULL,
                   name                TEXT NOT NULL,
                   key                 TEXT NOT NULL,
                   value               TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, name, key),
                   FOREIGN KEY(cluster_id, name)
                       REFERENCES cluster_namespace(cluster_id, name) ON DELETE CASCADE
               )""",
            "CREATE INDEX IF NOT EXISTS idx_cnl_key_value ON cluster_namespace_label(cluster_id, key, value)",
        ],
    ),
    (
        13,
        "binding_event: append-only binding changes; baseline flag on first observation (#167, #175)",
        [
            """CREATE TABLE IF NOT EXISTS binding_event (
                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                   cluster_id          TEXT NOT NULL,
                   binding_kind        TEXT NOT NULL,
                   binding_namespace   TEXT NOT NULL,
                   binding_name        TEXT NOT NULL,
                   subject_kind        TEXT NOT NULL,
                   subject_name        TEXT NOT NULL,
                   role_kind           TEXT NOT NULL,
                   role_name           TEXT NOT NULL,
                   is_platform         INTEGER NOT NULL DEFAULT 0,
                   change              TEXT NOT NULL,
                   baseline            INTEGER NOT NULL DEFAULT 0,
                   observed_at         TEXT NOT NULL
               )""",
            "CREATE INDEX IF NOT EXISTS binding_event_by_namespace ON binding_event(cluster_id, binding_namespace, id DESC)",
            "CREATE INDEX IF NOT EXISTS binding_event_by_subject ON binding_event(cluster_id, subject_kind, subject_name, id DESC)",
            "CREATE INDEX IF NOT EXISTS binding_event_by_time ON binding_event(cluster_id, observed_at)",
            # Existing rows keep 0: the flood already recorded on an upgraded store stays as it
            # was written; only observations from here on are classified.
            "ALTER TABLE membership_event ADD COLUMN baseline INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        14,
        "observation_state: the first-observation marker, consumed once per stream (review of #177, C4)",
        [
            """CREATE TABLE IF NOT EXISTS observation_state (
                   cluster_id          TEXT NOT NULL,
                   stream              TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, stream)
               )""",
            # Every cluster the store already knows has been observed: the same seeds run at every
            # open (see _OBSERVATION_SEEDS), so an upgrade never re-describes existing rows as a
            # first observation — and neither does a store a marker-less build wrote to.
            *_OBSERVATION_SEEDS,
        ],
    ),
    (
        15,
        "kpi_daily: the leader's daily rollup of the counts that have no history (#156)",
        [
            """CREATE TABLE IF NOT EXISTS kpi_daily (
                   cluster_id          TEXT NOT NULL,
                   day                 TEXT NOT NULL,
                   metric              TEXT NOT NULL,
                   value               REAL NOT NULL,
                   PRIMARY KEY(cluster_id, day, metric)
               )""",
        ],
    ),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply every unapplied migration in numeric order, independent of source layout."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    for target, title, statements in sorted(_MIGRATIONS, key=lambda migration: migration[0]):
        if version >= target:
            continue
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                # Fresh databases already carry additive columns from SCHEMA; only that exact replay
                # is harmless. Every other DDL error must still abort startup.
                if "duplicate column name" not in str(exc):
                    raise
        conn.execute(f"PRAGMA user_version = {target}")
        version = target
        log.info("schema migration %d applied: %s", target, title)


_PRAGMA_WORDS = {"OFF", "NORMAL", "FULL", "EXTRA"}


def _harden(conn: sqlite3.Connection) -> None:
    """Drop capabilities this application never uses, on every connection.

    MITIGATES (partially): CVE-2025-70873 — SQLite information disclosure via a crafted
    ZIP file, reachable only through the zipfile extension. Disabling extension loading
    removes the mechanism it needs.

    RELATED, NOT MITIGATED BY THIS: CVE-2024-0232 — use-after-free in
    jsonParseAddNodeArray. It needs SQL JSON functions; this store uses json_each over JSON it
    serialises itself from Python lists of strings (never over stored or user-supplied JSON
    text), so the malformed-document path the CVE needs is not reachable from here; nothing in
    this function changes that either way.

    NEITHER WAS FIXABLE BY UPGRADING when this was written: UBI9 shipped exactly one build,
    sqlite-libs-3.34.1-10.el9_8, so the surface it exposed was reduced instead. The hardened
    base the image runs on since 0.11.0 carries SQLite 3.53.4, past both advisories; the
    reduction stays because it costs nothing and closes the mechanism whatever the version.

    Extension loading was ENABLED by default — verified in the shipped image, not assumed.
    It lets SQL pull arbitrary shared objects into the process, which beyond CVE-2025-70873
    is a general escalation primitive if a SQL string ever became attacker-influenced. The
    store builds every statement itself and binds every parameter, so nothing legitimate
    needed the capability and turning it off costs nothing.

    Applied to the writer AND to every per-thread reader: this is connection state, so
    hardening only the writer would leave every API request thread unprotected.

    Guarded because sqlite3 may be compiled without the call, in which case the capability
    already does not exist and there is nothing to disable.

    See docs/image-vulnerability-scan.md for the full scan and reachability analysis.
    """
    try:
        conn.enable_load_extension(False)
    except AttributeError:
        pass


def _safe_pragma_word(value: str, default: str) -> str:
    """PRAGMA takes no bound parameters, so its argument is interpolated — allowlist it."""
    word = str(value).strip().upper()
    if word not in _PRAGMA_WORDS:
        log.warning("ignoring unsupported synchronous=%r, using %s", value, default)
        return default
    return word


# `now_iso` is imported at the top and therefore still re-exported from this module for any
# caller that has not moved. Its definition lives in gsd/timeutil.py: it was never a storage
# concern, and keeping it here meant a service split would need the SQLite module just to
# stamp a timestamp.
__all__ = ["Store", "now_iso"]


class Store:
    """SQLite with one writer connection and a reader per thread.

    The locking story has three parts, and all three have to hold or reads stall behind the
    60s bulk write:

    1. WAL, so readers never block on the writer. Verified rather than assumed — see below.
    2. `busy_timeout`, so a connection that does hit contention WAITS instead of failing.
       SQLite's default is 0: it raises "database is locked" the instant a lock is held,
       with no retry at all. That default is the single most common cause of the error.
    3. A checkpoint that actually runs, so the WAL does not grow without bound.
    """

    def __init__(
        self,
        path: str,
        busy_timeout_ms: int = 5000,
        reader_busy_timeout_ms: int = 2000,
        synchronous: str = "NORMAL",
        wal_checkpoint_mb: float = 8.0,
    ):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        # Readers get a SHORTER budget than the writer on purpose: /readyz performs a read
        # and the probe gives up at 5s, so a reader inheriting the writer's 5s would turn
        # a moment of contention into a failed probe and a restarted pod.
        self.reader_busy_timeout_ms = reader_busy_timeout_ms
        self.wal_checkpoint_bytes = int(wal_checkpoint_mb * 1024 * 1024)
        self._checkpoint_busy_total = 0
        self._lock = threading.RLock()
        self._local = threading.local()
        # Transaction depth is PER THREAD, not per Store. A plain attribute here was a
        # real bug: one poller thread opening a snapshot made every OTHER thread's write
        # join a transaction it does not own, which sqlite3 reports as "bad parameter or
        # other API misuse". A transaction belongs to the thread that opened it.

        self._conn = sqlite3.connect(path, check_same_thread=False)
        _harden(self._conn)
        self._conn.row_factory = sqlite3.Row

        # PRAGMA journal_mode returns the mode actually in force, which is NOT always the one
        # requested. WAL coordinates readers and writers through an mmap'd -shm file, so on a
        # filesystem without working shared memory or POSIX locks — NFS, EFS, SMB, most RWX
        # network storage — SQLite refuses the switch and stays in rollback-journal mode.
        # It does that SILENTLY, and the consequence is not subtle: in rollback mode a reader
        # blocks for the whole duration of the writer's transaction, so every API request
        # queues behind the bulk poll. Read it back and say so, because the alternative is
        # diagnosing that from latency graphs.
        self._journal_mode = str(
            self._conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        ).lower()
        if path != ":memory:" and self._journal_mode != "wal":
            log.error(
                "SQLite is in %r mode, not WAL — the filesystem under %s does not support it. "
                "Readers will now BLOCK on every write. This is expected on NFS/EFS/SMB and "
                "is why network storage is not supported for the database file.",
                self._journal_mode,
                path,
            )

        self._conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        # NORMAL is the documented companion to WAL: commits stop fsyncing, and a power loss
        # can lose the most recent transactions but CANNOT corrupt the database. The exposure
        # is one poll interval of history; the alternative is an fsync on every commit of a
        # 50k-row refresh. Set GSD_SQLITE_SYNCHRONOUS=FULL if that trade is wrong for you.
        self._conn.execute(f"PRAGMA synchronous={_safe_pragma_word(synchronous, 'NORMAL')}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        _migrate(self._conn)
        _seed_observation_markers(self._conn)
        self._conn.commit()

    def close(self) -> None:
        # Under the lock: closing while another thread is mid-transaction would
        # otherwise raise from inside that thread rather than here.
        with self._lock:
            self._conn.close()

    def _depth(self) -> int:
        """How many transactions THIS thread has open. Never another thread's."""
        return getattr(self._local, "tx_depth", 0)

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """Write inside the ambient transaction if one is open, else own a new one.

        This is what lets `poll_snapshot()` turn nine transactions into one without every
        store method growing a `conn` parameter. Inside a snapshot the method JOINS — it
        does not commit, so the snapshot still owns the boundary. Outside one, behaviour is
        exactly as before: its own transaction, committed on exit.

        `_tx` stays strict and refuses nesting. The distinction matters: `_write` is a
        deliberate join by a method designed for it, `_tx` nesting is an accident by code
        that believes it owns the transaction and will be surprised when its rollback does
        not roll back.
        """
        if self._depth():
            yield self._conn      # the snapshot commits; we must not
            return
        with self._tx() as conn:
            yield conn

    @contextmanager
    def poll_snapshot(self) -> Iterator[None]:
        """One transaction for a whole poll cycle. All of it lands, or none of it.

        The poll wrote in NINE separate transactions, so any read landing mid-cycle saw a
        mixture — measured at 11,598 torn reads out of 19,208, a 60.38% failure rate, not
        an edge case. A failed cycle could also stamp `record_poll(OK)` over half-written
        state, which is worse than a visible failure because it looks healthy.

        `record_sync_event` is deliberately NOT in here; poll_once commits it first. Its
        uniqueness key is the operator's own lastSyncSuccessTime, so a rollback would lose
        an observation permanently rather than re-deriving it next cycle, and it is
        INSERT OR IGNORE, so committing early costs nothing and repeats harmlessly.

        `membership_event` IS in here, because it self-heals: the next poll re-derives the
        identical change with a later observed_at, degrading only the timestamp by one
        poll interval — which values.yaml already documents as the error bar on "when did
        this person lose access?".

        Measured cost of the change: 26.79 -> 26.81 ms median, with p95 improving.
        """
        with self._lock:
            if self._depth():
                raise RuntimeError("poll_snapshot() is already open on this thread")
            self._local.tx_depth = self._depth() + 1
            try:
                with self._conn:
                    yield
            finally:
                self._local.tx_depth = self._depth() - 1

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        """One consistent view of the database for a whole multi-call handler.

        Making the poll atomic (`poll_snapshot`) took torn reads from 60.38% to 3.00%, not
        to zero, because a handler that calls the store SIX times issues six independent
        statements and a poll can commit between any two of them. `groupsyncs()` alone is
        two reads. WAL gives each statement a consistent snapshot; it does not give a
        SEQUENCE of statements the same one. Only an explicit read transaction does.

        Read-only by construction: it always rolls back, never commits. A rollback is not
        an error path here, it is the only exit — the snapshot exists to be released.

        HOLDING A READ SNAPSHOT HOLDS A WAL READ-MARK, and that has a cost worth knowing
        before anyone widens the scope of one of these blocks: `wal_checkpoint(TRUNCATE)`
        cannot reclaim past the oldest live reader, so a long-held snapshot stalls the
        checkpoint and the WAL grows. Measured: a reader held across a checkpoint blocked
        it for the full writer busy_timeout with zero pages reclaimed. At reference scale
        these blocks are 3-13 ms against a 60 s poll, which is why this is safe today and
        why `tests/test_read_snapshot_scope.py` exists to keep it that way — no generators,
        no streaming, no awaits, no network calls inside one.
        """
        depth = getattr(self._local, "read_depth", 0)
        if depth:
            # Already inside one: join it. Nesting is fine for reads — the inner block
            # wants exactly the snapshot the outer one already took.
            self._local.read_depth = depth + 1
            try:
                yield
            finally:
                self._local.read_depth -= 1
            return

        if self.path == ":memory:":
            # Reads share the writer connection here, so the write lock IS the snapshot.
            with self._lock:
                self._local.read_depth = 1
                try:
                    yield
                finally:
                    self._local.read_depth = 0
            return

        conn = self._reader()
        if conn.in_transaction:
            # A previous snapshot leaked. Left alone this thread would serve permanently
            # stale data with no error at all — measured: a worker pinned to a 2,000-row
            # view while the truth was 4,000. Fail loudly instead.
            raise RuntimeError(
                "this thread's reader is already in a transaction — a read_snapshot "
                "leaked and the connection is pinned to a stale view"
            )
        conn.execute("BEGIN")
        self._local.read_depth = 1
        try:
            yield
        finally:
            self._local.read_depth = 0
            conn.rollback()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Serialise whole transactions, not just statements.

        One connection is shared by a poller thread PER CLUSTER plus every API handler.
        Python's sqlite3 serialises individual statement execution, but NOT the multi-
        statement transaction boundary this block spans — so without the lock, two poller
        threads can interleave inside `with self._conn:` and one thread's commit can commit
        the other's half-written work, or a rollback discard it.

        Latent while only one cluster is configured (the default deployment), real the
        moment a second is added.

        NESTING IS NOW REFUSED, not merely discouraged. The docstring used to say "do not
        nest" and nothing enforced it, because RLock is reentrant: the inner
        ``with self._conn`` COMMITS the shared transaction on exit, so the outer block's
        work is committed early and survives the outer rollback. Measured — an outer
        transaction wrote `phase-one`, called one ordinary store method, then raised, and
        `phase-one` was still there afterwards. Eleven call sites could reach it.

        Depth counting turns that into a loud error at the point of the mistake. The outer
        block owns the transaction; an inner one raises rather than silently committing.
        `poll_snapshot` makes a long outer transaction the normal shape, so nesting stops
        being exotic and this stops being theoretical.
        """
        with self._lock:
            if self._depth():
                raise RuntimeError(
                    "nested Store._tx(): the inner block would COMMIT the outer "
                    "transaction on exit, so the outer block's remaining work would be "
                    "committed early and survive its own rollback. Call the raw _-prefixed "
                    "helper inside an existing transaction, or restructure so only one "
                    "block owns it."
                )
            self._local.tx_depth = self._depth() + 1
            try:
                with self._conn:
                    yield self._conn
            finally:
                self._local.tx_depth = self._depth() - 1

    def _reader(self) -> sqlite3.Connection:
        """A per-thread READ connection, separate from the writer's.

        WAL gives such a connection a consistent snapshot of committed data without taking
        the writer's lock, which fixes both problems at once: it cannot observe a half-
        written transaction, and it does not queue behind one.

        The previous approach — every read taking the write lock — was correct but
        serialising. Measured against a 50k-row binding refresh, exactly ONE read completed
        for the whole duration of the write, at 0.92s on fast local storage. /readyz does a
        read and has a 5s timeout, so on slower storage the pod goes NotReady during a
        routine refresh while /healthz stays green — an outage caused by the fix for a
        different bug.

        `:memory:` is the exception and must keep using the shared connection: each
        connection to `:memory:` is its OWN empty database, so a separate reader would see
        nothing at all. Tests use it; the deployment uses a file.
        """
        if self.path == ":memory:":
            return self._conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            _harden(conn)
            conn.row_factory = sqlite3.Row
            # Every connection needs its OWN busy_timeout — it is connection state, not a
            # property of the database, so the writer's setting does not reach these.
            conn.execute(f"PRAGMA busy_timeout={int(self.reader_busy_timeout_ms)}")
            self._local.conn = conn
        return conn

    def _wal_bytes(self) -> int:
        """Size of the -wal sidecar, or 0 when there is none (`:memory:`, or rollback mode)."""
        if self.path == ":memory:":
            return 0
        try:
            return os.path.getsize(self.path + "-wal")
        except OSError:
            return 0

    def _checkpoint(self) -> tuple[int, int, int] | None:
        """Truncate the WAL once it exceeds the threshold. Returns (busy, log, moved).

        SQLite auto-checkpoints when the WAL passes ~1000 pages, but that runs PASSIVE: it
        copies what it can and gives up the moment a reader holds an older snapshot open.
        Under a steady trickle of API reads "gives up" can be every single time, and then the
        WAL grows without bound while the database file itself stays small. The failure
        surfaces as a FULL VOLUME, not as a database error — which is why the size is also
        exported as a metric rather than only acted on here.

        TRUNCATE waits for readers and then returns the file to zero. It is called from the
        poller thread after a cycle, never from a request, so the wait costs no user latency.
        A busy result is not an error: it means readers were active, and the next cycle
        retries. It IS worth counting, because a busy result EVERY cycle is the starvation
        case and the metric is how you would ever notice.
        """
        if self.path == ":memory:" or self._journal_mode != "wal":
            return None
        if self._wal_bytes() < self.wal_checkpoint_bytes:
            return None
        with self._lock:
            row = self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_frames, moved = int(row[0]), int(row[1]), int(row[2])
        if busy:
            self._checkpoint_busy_total += 1
            log.warning(
                "WAL checkpoint blocked by an open reader (%d frames, %.1f MiB); will retry "
                "next cycle",
                log_frames,
                self._wal_bytes() / 1048576,
            )
        else:
            log.debug("WAL checkpointed: %d frames reclaimed", moved)
        return busy, log_frames, moved

    # -- the engine-neutral half of the seam ---------------------------------------------
    #
    # These two are what the poller and the metrics collector are allowed to call. They
    # used to call wal_bytes(), maybe_checkpoint() and read .journal_mode directly, which
    # meant both of them knew the database was SQLite — the leak that made the "decoupled"
    # claim untrue. See gsd/storage.py.

    def backup(self, directory: str, keep: int = 3) -> str | None:
        """Write a consistent copy of the database to `directory`. Returns its path.

        THE ONLY EXISTENTIAL RISK IN THIS SYSTEM. The accumulated sync and membership
        history cannot be re-fetched from the Kubernetes API — it exists because this
        process observed it — and until now a corrupted or deleted PVC lost it outright.
        Nothing else here is irreplaceable; this is.

        VACUUM INTO rather than copying the file: it takes a read transaction for the
        duration, so the output is a single consistent snapshot even while the poller
        writes. Copying gsd.db with the WAL live produces a torn file that opens without
        complaint and is missing the most recent commits, which is the worst kind of
        backup — one that restores.

        Called from the POLL THREAD only, the same rule as _checkpoint: it holds a read
        transaction for the length of the copy, and doing that from a request handler
        would put a user's page behind it.

        `keep` bounds the directory. Backups live on the same PVC this protects against,
        so they are the first half of the answer, not the whole one — a CronJob shipping
        them off the volume is the other half.
        """
        return self._vacuum_into(directory, keep, what="backup")

    def snapshot(self, directory: str, keep: int = 2) -> str | None:
        """A consistent copy for the REPORT SERVICE, on its own cadence and in its own directory.

        The same VACUUM INTO as backup() — a consistent single-file snapshot while the poller
        writes — and NOT a backup: it is not the retention gate's copy (poller._prune_history reads
        _backup_state, which only _maybe_backup sets), it is overwritten every few minutes, and it
        exists so a second POD can read this database without ever opening the live WAL file
        (docs/specs/SPEC_C3_reporting_microservice.md §4). Written under a `.tmp` name and renamed, so a
        reader listing the directory never opens a half-written file. Logged at DEBUG: every five
        minutes at INFO would bury the log.
        """
        return self._vacuum_into(directory, keep, what="report snapshot")

    def _vacuum_into(self, directory: str, keep: int, *, what: str) -> str | None:
        if self.path == ":memory:":
            return None
        target_dir = Path(directory)
        # Sub-second precision, unlike now_iso(). VACUUM INTO refuses to overwrite —
        # "output file already exists" — so two copies inside the same second collide and
        # the second one fails. now_iso() is deliberately second-resolution because the
        # store relies on its fixed width for lexicographic ordering; a filename has no
        # such constraint and needs the extra digits.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = target_dir / f"gsd-{stamp}.db"
        tmp = target_dir / f"gsd-{stamp}.db.tmp"
        try:
            # Inside the try: an unwritable or read-only directory must return None like every
            # other failure here, not raise into the poll thread.
            target_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                # A bound parameter is not accepted for the VACUUM target, so the path is
                # interpolated. It is built here from a timestamp and an operator-supplied
                # directory, never from request input; the quote-doubling is belt to that
                # brace rather than the only protection. Written to a .tmp name and renamed:
                # a reader listing gsd-*.db never sees a file VACUUM INTO has not finished.
                self._conn.execute(f"VACUUM INTO '{str(tmp).replace(chr(39), chr(39) * 2)}'")
            os.replace(tmp, target)
        except (sqlite3.Error, OSError):
            log.exception("%s to %s failed; the history is still only on the PVC", what, target)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        existing = sorted(target_dir.glob("gsd-*.db"))
        for stale in existing[:-keep] if keep > 0 else []:
            try:
                stale.unlink()
            except OSError:
                log.warning("could not remove old %s %s", what, stale)
        (log.info if what == "backup" else log.debug)("%s written to %s (%d kept)", what, target,
                                                      min(len(existing), keep or len(existing)))
        return str(target)

    # -- namespaces (the report's coverage; rbac.namespaces) -----------------------------------
    def replace_namespaces(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        with self._write() as conn:
            conn.execute("DELETE FROM cluster_namespace WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO cluster_namespace(cluster_id, name, created_at, phase, observed_at)
                   VALUES(:cluster_id,:name,:created_at,:phase,:observed_at)""",
                [{"cluster_id": cluster_id, "name": r["name"], "created_at": r.get("created_at"),
                  "phase": r.get("phase"), "observed_at": observed_at} for r in rows])
            # The bounded per-namespace metadata, replaced in the SAME transaction so a report never
            # reads a namespace whose labels were deleted but not yet re-inserted (design §3.4).
            conn.execute("DELETE FROM cluster_namespace_label WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                "INSERT INTO cluster_namespace_label(cluster_id, name, key, value) VALUES(?,?,?,?)",
                [(cluster_id, r["name"], k, v)
                 for r in rows for k, v in (r.get("metadata") or {}).items() if v is not None and v != ""])
            conn.execute(
                """INSERT INTO cluster_namespace_status(cluster_id, state, observed_at) VALUES(?, 'ok', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='ok', observed_at=excluded.observed_at""",
                (cluster_id, observed_at))

    def mark_namespaces_unavailable(self, cluster_id: str, observed_at: str) -> None:
        with self._write() as conn:
            conn.execute(
                """INSERT INTO cluster_namespace_status(cluster_id, state, observed_at) VALUES(?, 'forbidden', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='forbidden', observed_at=excluded.observed_at""",
                (cluster_id, observed_at))

    def namespaces(self, cluster_id: str, *, user_name: str | None = None,
                   groups: list[str] | None = None, every: bool = False) -> list[dict]:
        """Every namespace the poller sees, with the configured labels and two counts: distinct
        groups of people bound IN the namespace (virtual `system:` groups left out) and non-platform
        grants naming a person there (#167).

        Cluster-wide bindings reach every namespace, so they are counted once by the caller
        (`cluster_wide_*` on the envelope) rather than added to every row — a list where every
        namespace shows twenty "via groups" says nothing about any of them.

        Self tier (`user_name` given): only the namespaces one of the viewer's own `groups` or a
        binding naming the viewer reaches, and the counts are over those paths — "grants
        affecting them" (docs/ACCESS_CONTROL.md), never other people's. `every` is the caller
        saying one of those own paths is cluster-wide: it reaches every namespace, exactly as
        `namespace_reach` answers for the detail, so every row stays (its columns still count what
        is bound IN it) and the envelope names the cluster-wide path as the reason (review of
        #167, OB1 F2).
        """
        own = user_name is not None
        group_list = json.dumps(list(groups or []))
        with self.read_snapshot():
            rows = self._rows(
                "SELECT name, created_at, phase, observed_at FROM cluster_namespace WHERE cluster_id=? ORDER BY name",
                (cluster_id,))
            labels: dict[str, dict[str, str]] = {}
            for r in self._rows(
                    "SELECT name, key, value FROM cluster_namespace_label WHERE cluster_id=? ORDER BY name, key",
                    (cluster_id,)):
                labels.setdefault(r["name"], {})[r["key"]] = r["value"]
            # Groups of people: a virtual `system:` group (system:serviceaccounts:<ns>, bound by the
            # image-pullers RoleBinding in every OpenShift namespace) is on the page, badged, and out of
            # this count as it is out of the envelope's — counted, it read 1 on every row and the card's
            # "zero in both is a result" could never happen (review of #167, pass 3, OB1).
            via = {r["ns"]: r["n"] for r in self._rows(
                f"""SELECT binding_namespace AS ns,
                           COUNT(DISTINCT CASE WHEN substr(group_name, 1, ?) = ? THEN NULL ELSE group_name END) AS n
                      FROM rbac_group_binding WHERE cluster_id=? AND binding_namespace != ''
                      {"AND group_name IN (SELECT value FROM json_each(?))" if own else ""}
                     GROUP BY binding_namespace""",
                (len(SYSTEM_GROUP_PREFIX), SYSTEM_GROUP_PREFIX, cluster_id, group_list) if own
                else (len(SYSTEM_GROUP_PREFIX), SYSTEM_GROUP_PREFIX, cluster_id))}
            direct = {r["ns"]: r["n"] for r in self._rows(
                f"""SELECT binding_namespace AS ns, COUNT(*) AS n
                      FROM user_binding WHERE cluster_id=? AND binding_namespace != '' AND is_platform = 0
                      {"AND user_name = ?" if own else ""}
                     GROUP BY binding_namespace""",
                (cluster_id, user_name) if own else (cluster_id,))}
            # The self tier's rows follow the REACH, as its cluster-wide switch does since pass 2: a
            # binding naming the viewer in the namespace keeps the row, a platform identity's included,
            # while the count beside it stays the review's count (review of #167, pass 3, OB1).
            named = {r["ns"] for r in self._rows(
                "SELECT DISTINCT binding_namespace AS ns FROM user_binding WHERE cluster_id=? AND binding_namespace != '' AND user_name=?",
                (cluster_id, user_name))} if own else set()
        out = []
        for r in rows:
            v, d = via.get(r["name"], 0), direct.get(r["name"], 0)
            if own and not every and not (v or d or r["name"] in named):
                continue
            out.append({"name": r["name"], "created_at": r["created_at"], "phase": r["phase"],
                        "observed_at": r["observed_at"], "labels": labels.get(r["name"], {}),
                        "via_groups": v, "direct_grants": d})
        return out

    def namespace_reach(self, cluster_id: str, name: str, user_name: str, groups: list[str]) -> bool:
        """Whether one of the viewer's own paths — a group they belong to, or a binding naming
        them — reaches the namespace, in the namespace or cluster-wide. Decided BEFORE any
        existence lookup by the self-tier handler, so the refusal is the same for a real and a
        nonexistent name."""
        row = self._row(
            """SELECT EXISTS(SELECT 1 FROM rbac_group_binding
                              WHERE cluster_id=? AND binding_namespace IN (?, '')
                                AND group_name IN (SELECT value FROM json_each(?)))
                   OR EXISTS(SELECT 1 FROM user_binding
                              WHERE cluster_id=? AND binding_namespace IN (?, '') AND user_name=?) AS reach""",
            (cluster_id, name, json.dumps(list(groups)), cluster_id, name, user_name))
        return bool(row and row["reach"])

    def namespace_detail(self, cluster_id: str, name: str, *, user_name: str | None = None,
                         groups: list[str] | None = None, sibling_key: str | None = None) -> dict:
        """One namespace: its labels, who reaches it and through which group, the grants naming
        a person there, the cluster-wide grants that reach it too (naming a group, and naming a
        person), its siblings under the first configured label, and how many distinct people the
        paths add up to (#167).

        Returns a dict even when the store no longer holds the namespace (`present` False): a
        namespace that bindings or history still name is answered, not 404'd — the caller decides.
        Self tier: the viewer's own paths only, and `people` is None — it is a count over other
        people's memberships.
        """
        own = user_name is not None
        group_list = json.dumps(list(groups or []))
        own_groups = " AND b.group_name IN (SELECT value FROM json_each(?))" if own else ""
        with self.read_snapshot():
            ns = self._row("SELECT name, created_at, phase, observed_at FROM cluster_namespace WHERE cluster_id=? AND name=?",
                           (cluster_id, name))
            labels = {r["key"]: r["value"] for r in self._rows(
                "SELECT key, value FROM cluster_namespace_label WHERE cluster_id=? AND name=? ORDER BY key",
                (cluster_id, name))}
            def bound(namespace: str) -> list[dict]:
                return self._rows(
                    f"""SELECT b.group_name, b.binding_kind, b.binding_name, b.role_kind, b.role_name,
                               b.managed_source, COALESCE(g.member_count, 0) AS member_count
                          FROM rbac_group_binding b
                          LEFT JOIN group_state g ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                         WHERE b.cluster_id=? AND b.binding_namespace=?{own_groups}
                         ORDER BY b.role_name, b.group_name""",
                    (cluster_id, namespace, group_list) if own else (cluster_id, namespace))
            # A `system:` subject (system:authenticated, system:nodes, system:serviceaccounts:<ns>) is a
            # virtual group Kubernetes reserves: it authorises real access but no person is a member of
            # it and no review acts on it. Classified and labelled here, never dropped — the deployed
            # demo-prod page listed 54 cluster-wide bindings, 41 of them these (the CRC walk of #167).
            def classify(rows: list[dict]) -> list[dict]:
                out = [dict(r) for r in rows]
                for r in out:
                    r["is_platform"] = 1 if r["group_name"].startswith(SYSTEM_GROUP_PREFIX) else 0
                out.sort(key=lambda r: (r["is_platform"], r["role_name"], r["group_name"]))
                return out
            via_groups = classify(bound(name))
            cluster_wide = classify(bound(""))
            def named(namespace: str) -> list[dict]:
                return self._rows(
                    f"""SELECT user_name, binding_kind, binding_name, role_kind, role_name, is_platform
                          FROM user_binding WHERE cluster_id=? AND binding_namespace=?{" AND user_name=?" if own else ""}
                         ORDER BY is_platform, role_name, user_name""",
                    (cluster_id, namespace, user_name) if own else (cluster_id, namespace))
            direct = named(name)
            # A ClusterRoleBinding naming a person reaches this namespace as surely as one naming a
            # group. The list's envelope already counted these once; a page that left them out said
            # "nobody else" about a cluster-admin (review of #167, Grok F4).
            cluster_wide_grants = named("")
            people = None
            if not own:
                names = sorted({r["group_name"] for r in via_groups} | {r["group_name"] for r in cluster_wide})
                members = self._rows(
                    "SELECT DISTINCT user_name FROM group_member WHERE cluster_id=? AND group_name IN (SELECT value FROM json_each(?))",
                    (cluster_id, json.dumps(names)))
                people = len({r["user_name"] for r in members}
                             | {r["user_name"] for r in [*direct, *cluster_wide_grants] if not r["is_platform"]})
            siblings: list[str] = []
            if sibling_key and labels.get(sibling_key):
                siblings = [r["name"] for r in self._rows(
                    """SELECT name FROM cluster_namespace_label
                        WHERE cluster_id=? AND key=? AND value=? AND name != ? ORDER BY name""",
                    (cluster_id, sibling_key, labels[sibling_key], name))]
        return {"name": name, "present": ns is not None,
                "created_at": ns["created_at"] if ns else None, "phase": ns["phase"] if ns else None,
                "observed_at": ns["observed_at"] if ns else None, "labels": labels,
                "via_groups": via_groups, "cluster_wide_groups": cluster_wide,
                "direct_grants": direct, "cluster_wide_grants": cluster_wide_grants,
                "people": people, "siblings": siblings,
                "sibling_key": sibling_key if labels.get(sibling_key or "") else None}

    def namespaces_source(self, cluster_id: str) -> dict | None:
        return self._row("SELECT state, observed_at FROM cluster_namespace_status WHERE cluster_id=?", (cluster_id,))

    # -- report runs, pulled from the report service ------------------------------------------
    def report_runs_watermark(self) -> str | None:
        """The newest run id recorded, which is exactly what /report/api/usage?since_id wants."""
        row = self._row("SELECT MAX(id) AS id FROM report_run")
        return row["id"] if row else None

    def record_report_runs(self, runs: list[dict], pulled_at: str) -> int:
        """Insert what the pull returned; a run already known is ignored (the service is the
        source of truth and a run never changes once finished)."""
        if not runs:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO report_run(id, report, cluster_id, generated_by, generated_by_note, schedule,
                                                    status, requested_at, finished_at, sha256, snapshot_stamp, formats,
                                                    bytes_total, pdf_variant, pulled_at)
                   VALUES(:id,:report,:cluster,:generated_by,:generated_by_note,:schedule,:status,:requested_at,
                          :finished_at,:sha256,:snapshot_stamp,:formats,:bytes_total,:pdf_variant,:pulled_at)""",
                [{"id": r["id"], "report": r["report"], "cluster": r["cluster"], "generated_by": r["generated_by"],
                  "generated_by_note": r.get("generated_by_note") or "", "schedule": r.get("schedule"),
                  "status": r["status"], "requested_at": r["requested_at"], "finished_at": r.get("finished_at"),
                  "sha256": r.get("sha256"), "snapshot_stamp": r.get("snapshot_stamp"),
                  "formats": json.dumps(sorted(r.get("formats") or [])),
                  "bytes_total": sum((r.get("bytes") or {}).values()), "pdf_variant": r.get("pdf_variant"),
                  "pulled_at": pulled_at} for r in runs])
            return conn.total_changes - before

    def report_runs(self, *, user_name: str | None, limit: int, offset: int = 0) -> list[dict]:
        """Newest first; `user_name` is the privacy scope (the user_activity contract)."""
        sql = """SELECT id, report, cluster_id, generated_by, generated_by_note, schedule, status, requested_at,
                        finished_at, sha256, snapshot_stamp, formats, bytes_total, pdf_variant
                   FROM report_run"""
        params: list = []
        if user_name:
            sql += " WHERE generated_by = ?"
            params.append(user_name)
        sql += " ORDER BY requested_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = self._rows(sql, params)
        for r in rows:
            r["formats"] = json.loads(r["formats"] or "[]")
        return rows

    def count_report_runs(self, *, user_name: str | None) -> int:
        sql, params = "SELECT COUNT(*) AS n FROM report_run", []
        if user_name:
            sql += " WHERE generated_by = ?"
            params.append(user_name)
        return int(self._rows(sql, params)[0]["n"])

    def maintain(self) -> None:
        """Periodic upkeep after a write cycle. For SQLite, a WAL checkpoint.

        Returns nothing. It briefly returned a dict describing the checkpoint, which the
        only caller discarded — a contract that implied a signal it did not deliver. The
        durable signal is the starved-checkpoint count, which is cumulative and reported
        through health() where a scrape can read it.
        """
        self._checkpoint()

    def health(self) -> StorageHealth:
        """Engine-reported operational facts, namespaced under the engine that produced them.

        Not a flat dict. A flat one was described as engine-neutral and was not: the
        collector still had to know `wal_bytes`, `wal_enabled` and `checkpoint_busy_total`
        by name, so the coupling had moved from attributes to string literals. Worse, a
        backend without a WAL would omit `wal_enabled` and a defaulting caller would read
        False — which means "the filesystem refused WAL" and fires an alert on a healthy
        database.
        """
        return {
            "engine": "sqlite",
            "sqlite": {
                "wal_enabled": self._journal_mode == "wal",
                "wal_bytes": self._wal_bytes(),
                "checkpoint_busy_total": self._checkpoint_busy_total,
            },
        }

    def _rows(self, sql: str, params: tuple | list = ()) -> list[dict]:
        """Run a read on the per-thread reader (or under the lock for :memory:).

        Reads share the writer's connection, so they see its UNCOMMITTED state. Without
        this lock a reader can land inside the delete/insert window of
        ``replace_group_state`` and observe a partially-populated table — measured at
        40030 of 40419 concurrent reads returning a wrong count, including zero groups.
        Reporting "0 groups" while a poll is in flight is precisely the false
        everything-vanished alarm this dashboard exists to avoid raising.

        Every read goes through here or _row; a bare ``self._conn.execute`` in a query
        method is a bug.
        """
        if self.path == ":memory:":
            with self._lock:
                return [dict(r) for r in self._conn.execute(sql, params).fetchall()]
        return [dict(r) for r in self._reader().execute(sql, params).fetchall()]

    def _row(self, sql: str, params: tuple | list = ()) -> dict | None:
        if self.path == ":memory:":
            with self._lock:
                row = self._conn.execute(sql, params).fetchone()
        else:
            row = self._reader().execute(sql, params).fetchone()
        return dict(row) if row else None

    # -- configuration -----------------------------------------------------------------

    def upsert_cluster(self, cluster_id: str, api_url: str, enabled: bool) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO cluster(id, api_url, enabled) VALUES(?,?,?)
                   ON CONFLICT(id) DO UPDATE SET api_url=excluded.api_url,
                                                 enabled=excluded.enabled""",
                (cluster_id, api_url, int(enabled)),
            )

    def clusters(self) -> list[dict]:
        return self._rows(
            """SELECT c.id, c.api_url, c.enabled,
                      p.status, p.message, p.observed_at AS last_poll
                 FROM cluster c LEFT JOIN poll_outcome p ON p.cluster_id = c.id
                ORDER BY c.id"""
        )

    def retire_absent_clusters(self, configured_ids: list[str]) -> int:
        """Retire — never delete — every stored cluster the configuration no longer names: set
        enabled=0 so its history and snapshot rows stay, but it leaves the served/active set (#96).
        A cluster disabled in config is already enabled=0 through upsert_cluster; this catches the
        ones the config dropped entirely. Returns how many rows it retired."""
        ids = list(configured_ids)
        with self._tx() as conn:
            if ids:
                marks = ",".join("?" for _ in ids)
                cur = conn.execute(
                    f"UPDATE cluster SET enabled=0 WHERE enabled=1 AND id NOT IN ({marks})", ids)
            else:
                cur = conn.execute("UPDATE cluster SET enabled=0 WHERE enabled=1")
            return cur.rowcount

    # -- poll results ------------------------------------------------------------------

    def record_poll(self, cluster_id: str, status: str, message: str | None) -> None:
        with self._write() as conn:
            conn.execute(
                """INSERT INTO poll_outcome(cluster_id, observed_at, status, message)
                   VALUES(?,?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET observed_at=excluded.observed_at,
                                                          status=excluded.status,
                                                          message=excluded.message""",
                (cluster_id, now_iso(), status, message),
            )

    def record_sync_event(
        self,
        cluster_id: str,
        name: str,
        namespace: str,
        synced_at: str,
        observed_at: str,
        schedule: str | None,
        group_count: int,
    ) -> bool:
        """Insert one observed sync. Returns True if this was a new event.

        The UNIQUE constraint makes this idempotent, so polling faster than the schedule
        costs nothing (PLAN §10) — re-observing the same lastSyncSuccessTime is a no-op
        rather than a duplicate timeline entry.
        """
        with self._write() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO sync_event(
                       cluster_id, groupsync_name, groupsync_namespace,
                       synced_at, observed_at, schedule, group_count)
                   VALUES(?,?,?,?,?,?,?)""",
                (cluster_id, name, namespace, synced_at, observed_at, schedule, group_count),
            )
            return cursor.rowcount > 0

    def replace_groupsync_state(
        self, cluster_id: str, rows: list[dict] | None, observed_at: str
    ) -> None:
        """Replace this cluster's CR rows and their provider attributions together.

        Both in ONE transaction: a CR whose state is visible while its providers are not
        owns nothing for the duration, and every one of its groups would read as
        unattributed — a burst of phantom findings on each poll.

        `rows=None` means the GroupSync CRD is NOT INSTALLED, which is distinct from `[]`
        ("installed, no CRs defined") for the same reason it is for the policy operator: the
        first is a fact about the cluster's shape, the second about its configuration. Both
        store zero CR rows, so only the presence flag can tell them apart — and the Overview
        needs to, or "GroupSync CRs: 0" silently describes two different clusters.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO groupsync_presence(cluster_id, present, observed_at)
                   VALUES(?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET
                       present=excluded.present, observed_at=excluded.observed_at""",
                (cluster_id, 0 if rows is None else 1, observed_at),
            )
            conn.execute("DELETE FROM groupsync_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_state(cluster_id, name, namespace, schedule,
                       ldap_filter, last_sync_at, generation, observed_at)
                   VALUES(:cluster_id,:name,:namespace,:schedule,:ldap_filter,
                          :last_sync_at,:generation,:observed_at)""",
                [
                    {k: v for k, v in r.items() if k != "provider_keys"}
                    | {"cluster_id": cluster_id, "observed_at": observed_at}
                    for r in rows or []
                ],
            )
            conn.execute("DELETE FROM groupsync_provider WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_provider(
                       cluster_id, groupsync_name, groupsync_namespace, provider_key)
                   VALUES(?,?,?,?)""",
                [
                    (cluster_id, r["name"], r["namespace"], key)
                    for r in rows or []
                    for key in r.get("provider_keys") or []
                ],
            )

    def replace_group_state(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's group rows wholesale.

        Delete-then-insert inside one transaction, so a group that disappeared upstream also
        disappears here — an upsert would leave deleted groups behind forever and quietly
        inflate every count on the overview.
        """
        with self._write() as conn:
            conn.execute("DELETE FROM group_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO group_state(cluster_id, name, member_count, sync_provider,
                       group_synced_at, ldap_uid, observed_at, cliff_silence)
                   VALUES(:cluster_id,:name,:member_count,:sync_provider,
                          :group_synced_at,:ldap_uid,:observed_at,:cliff_silence)""",
                # cliff_silence defaults to NULL so every existing caller (and every fixture) that
                # builds rows without it keeps working; the poller always supplies it.
                [{"cliff_silence": None, **r, "cluster_id": cluster_id, "observed_at": observed_at}
                 for r in rows],
            )

    def _first_observation(self, conn: sqlite3.Connection, cluster_id: str, stream: str) -> int:
        """Consume a stream's baseline once — independently of current rows and of retention.

        Returns 1 on the observation that consumes it, 0 ever after. Inside the caller's write
        transaction, so a rolled-back observation does not spend the marker.
        """
        seen = conn.execute(
            "SELECT 1 FROM observation_state WHERE cluster_id=? AND stream=?", (cluster_id, stream),
        ).fetchone()
        if seen:
            return 0
        conn.execute("INSERT INTO observation_state(cluster_id, stream) VALUES(?,?)", (cluster_id, stream))
        return 1

    def sync_members(
        self,
        cluster_id: str,
        memberships: dict[str, list[str]],
        sync_times: dict[str, str | None],
        observed_at: str,
    ) -> int:
        """Reconcile observed membership and append an event for every change.

        ``memberships`` MUST be the complete map for this cluster — every group and every
        member seen in the poll. Any group absent from it is treated as deleted upstream and
        its members are recorded as departures. Passing a partial map (say, one group at a
        time) therefore silently empties every group you left out.

        Diff-and-append rather than replace: the replace strategy used for `group_state`
        would be wrong here, because it destroys `first_seen_at` and can record no history.
        The whole value of this table is the two questions the API cannot answer — when did
        this user join, and who quietly disappeared.

        Returns the number of change events written.
        """
        changes = 0
        with self._write() as conn:
            existing: dict[str, set[str]] = {}
            for row in conn.execute(
                "SELECT group_name, user_name FROM group_member WHERE cluster_id=?",
                (cluster_id,),
            ):
                existing.setdefault(row["group_name"], set()).add(row["user_name"])

            # THE BASELINE. A cluster observed for the first time has no prior state to diff
            # against, so every member would read as "added" in one instant — 76, 87 and 5 rows
            # per cluster on CRC, one of which the landing page reported as a bulk onboarding
            # (#175). The rows are still written (first_seen_at, original_first_seen_at and the
            # cliff's window all depend on them) but flagged, so a consumer says "first observed"
            # rather than "added". A NEW group in an already-observed cluster is a real change
            # and is not flagged: the stream's observation_state marker decides, not the rows.
            # Consumed even when this observation is empty — otherwise the first later addition
            # would be described as the cluster's first observation (review of #177, C4).
            baseline = self._first_observation(conn, cluster_id, "membership")

            for group, members in memberships.items():
                observed = set(members)
                known = existing.get(group, set())
                synced_at = sync_times.get(group)

                for user in sorted(observed - known):
                    conn.execute(
                        """INSERT INTO group_member(cluster_id, group_name, user_name,
                               first_seen_at, last_seen_at)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(cluster_id, group_name, user_name)
                           DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                        (cluster_id, group, user, observed_at, observed_at),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at, baseline)
                           VALUES(?,?,?,'added',?,?,?)""",
                        (cluster_id, group, user, observed_at, synced_at, baseline),
                    )
                    changes += 1

                # Chunked because SQLITE_LIMIT_VARIABLE_NUMBER is per-statement and varies by
                # build: 32766 in the deployment image (measured on both the UBI9 runtime,
                # SQLite 3.34.1, and the hardened base, 3.53.4) but 250000 on a dev Mac
                # (3.53.0). An unchunked IN-list therefore passes every local test and then
                # raises "too many SQL variables" in production on a group with >32k members,
                # which a large LDAP directory can genuinely have.
                observed_users = sorted(observed)
                for start in range(0, len(observed_users), 500):
                    batch = observed_users[start:start + 500]
                    conn.execute(
                        f"""UPDATE group_member SET last_seen_at=?
                             WHERE cluster_id=? AND group_name=?
                               AND user_name IN ({','.join('?' * len(batch))})""",
                        (observed_at, cluster_id, group, *batch),
                    )

                for user in sorted(known - observed):
                    conn.execute(
                        "DELETE FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
                        (cluster_id, group, user),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at)
                           VALUES(?,?,?,'removed',?,?)""",
                        (cluster_id, group, user, observed_at, synced_at),
                    )
                    changes += 1

            # A group deleted upstream takes its membership with it, and each departure is
            # recorded — otherwise the members simply vanish from the store with no trace.
            for group in set(existing) - set(memberships):
                for user in sorted(existing[group]):
                    conn.execute(
                        "DELETE FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
                        (cluster_id, group, user),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at)
                           VALUES(?,?,?,'removed',?,NULL)""",
                        (cluster_id, group, user, observed_at),
                    )
                    changes += 1
        return changes

    def group_members(self, cluster_id: str, group_name: str) -> list[dict]:
        """Current members, with BOTH the current and the original join date.

        `first_seen_at` resets when a user leaves and rejoins, because the row is deleted
        and reinserted — that is correct for "how long has this access been continuous?",
        but on its own it silently overwrites the original grant date, which is the one an
        auditor asking "when did this person get access?" actually wants.

        The original is recovered from membership_event, which is append-only and keeps
        every join even across removals — so no schema change is needed to answer both.
        """
        # LEFT JOIN, not a second query: the handler that calls this is asserted to make exactly
        # one store call (tests/test_api_contract.py, the take-a-snapshot rule), and a name is
        # missing far more often than not — 3 of 10 members on the reference cluster — so NULL is
        # the ordinary result rather than a case to special-case.
        #
        # Ordering stays on user_name. Sorting by display name would reorder the list for the 70%
        # that have one and scatter the rest, and the id is what an operator matches against `oc`.
        return self._rows(
                """SELECT m.user_name, m.first_seen_at, m.last_seen_at, u.full_name,
                          (SELECT MIN(e.observed_at) FROM membership_event e
                            WHERE e.cluster_id = m.cluster_id
                              AND e.group_name = m.group_name
                              AND e.user_name  = m.user_name
                              AND e.change = 'added') AS original_first_seen_at
                     FROM group_member m
                     LEFT JOIN ocp_user u
                            ON u.cluster_id = m.cluster_id
                           AND u.user_name  = m.user_name
                    WHERE m.cluster_id=? AND m.group_name=?
                    ORDER BY m.user_name""",
                (cluster_id, group_name),
        )

    def group_detail(self, cluster_id: str, group_name: str) -> dict | None:
        row = self._row(
            """SELECT name, member_count, sync_provider, group_synced_at, ldap_uid, observed_at,
                      cliff_silence
                 FROM group_state WHERE cluster_id=? AND name=?""",
            (cluster_id, group_name),
        )
        return dict(row) if row else None

    def membership_events(
        self, cluster_id: str, group_name: str | None = None,
        user_name: str | None = None, limit: int = 200,
    ) -> list[dict]:
        sql = """SELECT group_name, user_name, change, observed_at, group_synced_at, baseline
                   FROM membership_event WHERE cluster_id=?"""
        params: list = [cluster_id]
        if group_name:
            sql += " AND group_name=?"
            params.append(group_name)
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def group_count_changes(self, cluster_id: str, since: str) -> dict[str, dict]:
        """Per group, how many members were added and removed strictly after ``since``.

        The group-count cliff's only store read (state.py#compute_alerts). ``since`` is a
        timeutil-format timestamp, compared lexicographically like every other timestamp
        here. The count at the window's start is exactly ``current + removed - added``
        because sync_members writes one event per member transition and nothing else — so
        this is the per-poll history the cliff needs without a second table holding a copy
        of it. STRICTLY after: events stamped exactly at ``since`` were written by the poll
        that defines the window's start, and the count that poll held is the "before" — an
        inclusive bound rewound that poll too and reported the state before it (found in
        review, PR #72). Groups with no later events are absent from the result.
        """
        rows = self._rows(
            """SELECT group_name,
                      SUM(CASE WHEN change = 'added'   THEN 1 ELSE 0 END) AS added,
                      SUM(CASE WHEN change = 'removed' THEN 1 ELSE 0 END) AS removed
                 FROM membership_event
                WHERE cluster_id = ? AND observed_at > ?
                GROUP BY group_name""",
            (cluster_id, since),
        )
        return {
            r["group_name"]: {"added": int(r["added"] or 0), "removed": int(r["removed"] or 0)}
            for r in rows
        }

    def user_groups(self, cluster_id: str, user_name: str) -> list[dict]:
        """Every group a user belongs to — the reverse lookup.

        This is the "why does this person have access?" question, which the cluster can only
        answer by scanning every Group object by hand.
        """
        return self._rows(
                """SELECT m.group_name, m.first_seen_at, m.last_seen_at, g.sync_provider
                     FROM group_member m
                     LEFT JOIN group_state g
                            ON g.cluster_id = m.cluster_id AND g.name = m.group_name
                    WHERE m.cluster_id=? AND m.user_name=?
                    ORDER BY m.group_name""",
                (cluster_id, user_name),
        )

    def users(
        self, cluster_id: str, limit: int = 1000, offset: int = 0, user_name: str | None = None,
        providers: tuple[str, ...] = (),
    ) -> list[dict]:
        """Every person who has logged in to the cluster — one row per User object. BOUNDED.

        The base table is ocp_user, not group_member: a row IS the fact of a login, because OpenShift
        creates the User object at first login and never before (docs/DESIGN_users_tab_logins.md).
        Group membership rides along as an attribute — group_count, which may be 0 for someone who
        logged in and holds no synced access, and first_seen_at, the moment the dashboard first saw
        them in any group. A synced member with no User object is not a row here; see
        synced_members_without_user, which the tab reports as one line.

        `limit + 1` is fetched deliberately: the caller compares the length against the limit to
        know it truncated. `offset` pages, per docs/api-contract.md R3 — a cluster's User count is
        every person who has ever logged in, so the list grows with the organisation.

        `user_name` is the privacy scope — the user_activity() contract. The predicate is on the
        base table, so at the narrowed tier the only row reachable is the viewer's own.

        last_login_at is the newest SUCCESSFUL login-capture event for the id, or NULL: nothing
        before capture began was ever recorded, so the API says whether capture is on at all.
        The two joins are to pre-grouped subqueries, so they are 1:1 and cannot multiply rows.
        Ordering stays on the id: it is what an operator matches against `oc`.
        """
        sql = """SELECT u.user_name, u.full_name, u.created_at, u.providers, u.has_identity, u.identity_created_at,
                        COALESCE(g.group_count, 0) AS group_count, g.first_seen_at, l.last_login_at
                   FROM ocp_user u
                   LEFT JOIN (SELECT cluster_id, user_name, COUNT(*) AS group_count,
                                     MIN(first_seen_at) AS first_seen_at
                                FROM group_member GROUP BY cluster_id, user_name) g
                          ON g.cluster_id = u.cluster_id AND g.user_name = u.user_name
                   LEFT JOIN (SELECT cluster_id, user_name, MAX(at) AS last_login_at
                                FROM login_event WHERE outcome = 'success'
                               GROUP BY cluster_id, user_name) l
                          ON l.cluster_id = u.cluster_id AND l.user_name = u.user_name
                  WHERE u.cluster_id=?"""
        params: list = [cluster_id]
        if user_name:
            sql += " AND u.user_name=?"
            params.append(user_name)
        if providers:
            # The allow-list, on the JSON list the row stores: a User qualifies when ANY of its
            # providers is listed. json_each is SQLite's own JSON1, present in every SQLite this
            # project ships (the image's 3.53.4; 3.38+ builds it in).
            sql += (" AND EXISTS (SELECT 1 FROM json_each(u.providers) je WHERE je.value IN ("
                    + ",".join("?" * len(providers)) + "))")
            params += list(providers)
        sql += " ORDER BY u.user_name LIMIT ? OFFSET ?"
        params += [limit + 1, offset]
        return [self._user_row(r) for r in self._rows(sql, params)]

    @staticmethod
    def _user_row(row: dict) -> dict:
        """Decode the stored record into what the API serves. providers is JSON text in the table;
        logged_in is has_identity, named for what it means; first_login_at is the creation time only
        when an identity proves a login happened — a manual account's creation time is not one."""
        row = dict(row)
        row["providers"] = json.loads(row.pop("providers") or "[]")
        row["logged_in"] = bool(row.pop("has_identity"))
        identity_time = row.pop("identity_created_at", None)
        # The Identity's creation time when it was read, the User's creation time otherwise — and the
        # source says which, so the page can say what each time is (an Identity time is the first
        # login for claim/add mapping and the mapping's creation for lookup; the User time precedes
        # the first login for an administrator-created account).
        row["first_login_at"] = (identity_time or row["created_at"]) if row["logged_in"] else None
        row["first_login_source"] = ("identity" if identity_time else "user") if row["logged_in"] else None
        return row

    def count_users(
        self, cluster_id: str, user_name: str | None = None, logged_in_only: bool = False,
        providers: tuple[str, ...] = (),
    ) -> int:
        """Whole-set count for the paged list, under the same privacy predicate.

        `logged_in_only` counts the rows whose User carries an identity — the people who have
        actually logged in. The plain count is every User object, which includes accounts created
        by hand that nobody has used; the Codex review of #47 caught the headline counting those as
        logins while their own rows said "never logged in". The API serves both numbers.
        """
        sql = "SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=?"
        params: list = [cluster_id]
        if logged_in_only:
            sql += " AND has_identity=1"
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        if providers:
            sql += (" AND EXISTS (SELECT 1 FROM json_each(ocp_user.providers) je WHERE je.value IN ("
                    + ",".join("?" * len(providers)) + "))")
            params += list(providers)
        return int(self._rows(sql, params)[0]["n"])

    def synced_members_without_user(
        self, cluster_id: str, user_name: str | None = None
    ) -> list[str]:
        """Members of synced groups who have never logged in: no User object exists for the id.

        The tab reports these as one line under the headline rather than as rows, because they are
        not users of the cluster yet — but a reviewer wants the number, and the names one click
        away. Same privacy predicate as users(): a narrowed reader learns only about themselves.
        """
        sql = """SELECT DISTINCT m.user_name FROM group_member m
                  WHERE m.cluster_id=?
                    AND NOT EXISTS(SELECT 1 FROM ocp_user u
                                    WHERE u.cluster_id = m.cluster_id AND u.user_name = m.user_name)"""
        params: list = [cluster_id]
        if user_name:
            sql += " AND m.user_name=?"
            params.append(user_name)
        sql += " ORDER BY m.user_name"
        return [r["user_name"] for r in self._rows(sql, params)]

    def user_record(self, cluster_id: str, user_name: str) -> dict | None:
        """One user's row as users() would serve it, or None when no User object exists."""
        rows = self.users(cluster_id, limit=1, user_name=user_name)
        return rows[0] if rows else None

    def users_source(self, cluster_id: str) -> dict | None:
        """The last poll's verdict on reading User objects: {'state': 'ok'|'forbidden', 'observed_at'},
        or None before any poll has reported. The API turns None into 'pending' so that an empty
        table on a fresh install is never presented as an empty cluster."""
        rows = self._rows(
            "SELECT state, observed_at FROM ocp_user_status WHERE cluster_id=?", (cluster_id,)
        )
        return dict(rows[0]) if rows else None

    # -- RBAC bindings -----------------------------------------------------------------

    def replace_bindings(self, cluster_id: str, rows: list[dict], observed_at: str) -> dict[str, int]:
        """Replace this cluster's binding rows wholesale, in one transaction — recording, first,
        every (binding, Group) that appeared or disappeared since the last refresh as a
        binding_event. Returns {"added": n, "removed": m}.

        The current-state table stays a replace (a binding is fully re-readable from the API);
        the history is what the API cannot give back, so it is appended before the replace, in
        the same transaction, from the same rows. A role change on the same binding+subject is
        a `removed` and an `added`. The cluster's first observation is flagged `baseline`
        rather than recorded as a mass grant — see sync_members for why the rows are still
        written.
        """
        with self._write() as conn:
            changes = self._append_binding_events(
                conn, cluster_id, "Group", "group_name",
                current=conn.execute(
                    """SELECT binding_kind, binding_namespace, binding_name, group_name AS subject,
                              role_kind, role_name, 0 AS is_platform
                         FROM rbac_group_binding WHERE cluster_id=?""", (cluster_id,)).fetchall(),
                incoming=rows, observed_at=observed_at,
            )
            conn.execute("DELETE FROM rbac_group_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO rbac_group_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, group_name, observed_at,
                       managed_source, exception, audit_stamped)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:group_name,:observed_at,
                          :managed_source,:exception,:audit_stamped)""",
                [{"managed_source": None, "exception": None, "audit_stamped": 0, **r,
                  "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )
        return changes

    def _append_binding_events(
        self, conn: sqlite3.Connection, cluster_id: str, subject_kind: str, subject_field: str,
        *, current: list, incoming: list[dict], observed_at: str,
    ) -> dict[str, int]:
        """Diff the stored (binding, subject) set against the incoming one; append an event per
        difference. Identity is (binding_kind, binding_namespace, binding_name, subject); the
        value compared is (role_kind, role_name), so a role change is one removed + one added.

        Baseline: the stream's observation_state marker is consumed on its first observation —
        empty or not — and every incoming row of that observation is flagged baseline=1. A
        refresh that returns nothing for a cluster that had rows is a real mass removal and is
        recorded as one; the poller never reaches here on a fetch failure.
        """
        def key(r):  # sqlite3.Row and dict both index by name
            return (r["binding_kind"], r["binding_namespace"], r["binding_name"], r["subject"] if "subject" in r.keys() else r[subject_field])
        before = {key(r): (r["role_kind"], r["role_name"], int(r["is_platform"] or 0)) for r in current}
        after: dict = {}
        for r in incoming:
            k = (r["binding_kind"], r["binding_namespace"], r["binding_name"], r[subject_field])
            after[k] = (r["role_kind"], r["role_name"], int(r.get("is_platform", 0) or 0))
        baseline = self._first_observation(conn, cluster_id, f"binding:{subject_kind}")
        counts = {"added": 0, "removed": 0}
        rows = []
        for k in sorted(set(before) | set(after)):
            was, now = before.get(k), after.get(k)
            # Compared on the role only: is_platform is metadata carried on the event, not part
            # of what changed — a subject reclassified would otherwise read as removed + added.
            if was is not None and now is not None and was[:2] == now[:2]:
                continue
            if was is not None:
                rows.append((*k[:3], subject_kind, k[3], was[0], was[1], was[2], "removed", 0, observed_at))
                counts["removed"] += 1
            if now is not None:
                rows.append((*k[:3], subject_kind, k[3], now[0], now[1], now[2], "added", baseline, observed_at))
                counts["added"] += 1
        if rows:
            conn.executemany(
                """INSERT INTO binding_event(cluster_id, binding_kind, binding_namespace, binding_name,
                       subject_kind, subject_name, role_kind, role_name, is_platform, change,
                       baseline, observed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(cluster_id, *r) for r in rows],
            )
        return counts

    def binding_events(
        self, cluster_id: str, *, namespace: str | None = None, limit: int = 200,
        viewer: str | None = None, viewer_groups: list[str] | None = None,
    ) -> list[dict]:
        """Binding changes newest first. With `viewer`, only the rows that name the viewer or a
        group the viewer belongs to — the self tier's slice, decided by the caller from
        user_groups, so this method takes the scope rather than deciding it."""
        columns = """binding_kind, binding_namespace, binding_name, subject_kind, subject_name,
                     role_kind, role_name, is_platform, change, baseline, observed_at"""
        where = "cluster_id=?"
        scope: list = [cluster_id]
        if namespace is not None:
            where += " AND binding_namespace=?"
            scope.append(namespace)
        if viewer is None:
            return self._rows(
                f"SELECT {columns} FROM binding_event WHERE {where} ORDER BY id DESC LIMIT ?",
                [*scope, limit],
            )
        # Two index-served halves under UNION ALL, not one OR: this store never runs ANALYZE, and
        # without statistics SQLite plans the OR as a walk of the cluster's rows plus a sort —
        # measured 306 ms at 300k rows against 1.8 ms for the union, the same rows back (OB1,
        # review 2 of #177). The groups ride as ONE bound JSON parameter: a viewer in more groups
        # than SQLITE_LIMIT_VARIABLE_NUMBER made a placeholder list raise "too many SQL variables"
        # (Codex, review of #177, reproduced with setlimit).
        sql = f"""SELECT {columns} FROM (
                      SELECT id, {columns} FROM binding_event
                       WHERE {where} AND subject_kind='User' AND subject_name=?"""
        params: list = [*scope, viewer]
        groups = list(viewer_groups or [])
        if groups:
            sql += f"""
                      UNION ALL
                      SELECT id, {columns} FROM binding_event
                       WHERE {where} AND subject_kind='Group'
                         AND subject_name IN (SELECT value FROM json_each(?))"""
            params += [*scope, json.dumps(groups)]
        sql += ") ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def prune_binding_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete binding events observed before `before_at`, at most `max_rows`. Same gates and
        bound as prune_membership_events; served by binding_event_by_time."""
        return self._prune_history("binding_event", cluster_id, before_at, max_rows)

    def record_managed_groups(
        self, cluster_id: str, groups: list[dict], observed_at: str
    ) -> None:
        """Remember which groups the operator manages, so their later absence is meaningful.

        Only groups carrying a sync-provider label are recorded. A group we have never seen
        managed cannot later be called a broken binding — at most an unresolved one.
        """
        managed = [g for g in groups if g.get("sync_provider")]
        if not managed:
            return
        with self._write() as conn:
            conn.executemany(
                """INSERT INTO managed_group_seen(
                       cluster_id, group_name, sync_provider, first_seen_at, last_seen_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cluster_id, group_name) DO UPDATE SET
                       sync_provider=excluded.sync_provider,
                       last_seen_at=excluded.last_seen_at""",
                [
                    (cluster_id, g["name"], g["sync_provider"], observed_at, observed_at)
                    for g in managed
                ],
            )

    def group_bindings(self, cluster_id: str, group_name: str) -> list[dict]:
        """Direct role bindings naming this group. NOT effective permissions."""
        return self._rows(
            """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name
                 FROM rbac_group_binding
                WHERE cluster_id=? AND group_name=?
                ORDER BY binding_kind, binding_namespace, binding_name""",
            (cluster_id, group_name),
        )

    def user_bindings(self, cluster_id: str, user_name: str) -> list[dict]:
        """Every binding reachable by this user THROUGH their current group memberships.

        `via_group` is carried on every row: without it the user page would assert access
        with no way to see which membership confers it, which is the first thing anyone
        asks when revoking it.
        """
        return self._rows(
            """SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name AS via_group
                 FROM group_member m
                 JOIN rbac_group_binding b
                   ON b.cluster_id = m.cluster_id AND b.group_name = m.group_name
                WHERE m.cluster_id=? AND m.user_name=?
                ORDER BY b.binding_kind, b.binding_namespace, b.binding_name""",
            (cluster_id, user_name),
        )

    def memberships_by_cluster(self, user_name: str) -> dict[str, int]:
        """How many synced groups this person is in, per cluster — Home's "you're also on" line
        (#158). One GROUP BY over group_member; the per-cluster detail is `user_groups`. Every cluster
        the store holds, retired ones included: the caller keeps the enabled ones it may name."""
        return {r["cluster_id"]: r["n"] for r in self._rows(
            "SELECT cluster_id, COUNT(*) AS n FROM group_member WHERE user_name=? GROUP BY cluster_id",
            (user_name,))}

    def binding_findings(self, cluster_id: str) -> list[dict]:
        """Classify every binding whose Group subject has no Group object.

        Three tiers, because two would be useless here. On the target cluster 110 of 149
        distinct Group subjects are built-in virtual groups; lumping those in with real
        problems gives 119 findings of which 9 matter, and a list that is 92% noise is one
        operators stop reading.

            built_in    system:* — virtual, authorises real access, no object expected
            dangling    was observed operator-managed, now absent -> something broke
            unresolved  never seen managed -> names a group that has never existed

        `dangling` is the high-confidence tier and is the only one that should alert.
        """
        return [r for r in self.all_bindings(cluster_id) if r["finding"] != "ok"]

    # The classification, written once. Both all_bindings and count_bindings_by_finding
    # need it, and two copies of a five-branch CASE would drift the moment a tier changed —
    # producing counts that disagree with the rows they are counting.
    _FINDING_CASE = """
                      CASE
                        -- Broken-resolution tiers first: a binding that grants NOBODY is
                        -- worse than one that grants outside governance, whoever made it.
                        WHEN g.name IS NULL AND s.group_name IS NOT NULL
                                                           THEN 'dangling'
                        WHEN g.name IS NULL AND b.group_name LIKE 'system:%'
                                                           THEN 'built_in'
                        WHEN g.name IS NULL                THEN 'unresolved'
                        -- The group resolves. Now provenance: an operator-SYNCED group
                        -- granted access by a binding NO policy system manages is somebody
                        -- bypassing governance by hand. Requires the policy operator to be
                        -- in use at all (any managed binding on the cluster), or every
                        -- binding on a cluster that has never heard of config-source
                        -- labels would flag. An exception annotation on the binding
                        -- acknowledges a deliberate one and suppresses the finding.
                        WHEN b.managed_source IS NULL
                             AND b.exception IS NULL
                             AND s.group_name IS NOT NULL
                             AND EXISTS (SELECT 1 FROM rbac_group_binding m
                                          WHERE m.cluster_id = b.cluster_id
                                            AND m.managed_source IS NOT NULL)
                                                           THEN 'unmanaged'
                        ELSE 'ok'
                      END"""

    _FINDING_JOINS = """
                 FROM rbac_group_binding b
                 LEFT JOIN group_state g
                        ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                 LEFT JOIN managed_group_seen s
                        ON s.cluster_id = b.cluster_id AND s.group_name = b.group_name"""
    _FINDING_WHERE = """
                WHERE b.cluster_id = ?"""
    # The name the count query and the docs use; the split above exists so that all_bindings can
    # put one more join between the two halves without touching the classification.
    _FINDING_FROM = _FINDING_JOINS + _FINDING_WHERE

    # WHO A GRANTED BINDING REACHES, joined only on request (all_bindings(reach=True)). The
    # member count is the Group object's own, from group_state, already joined above. The
    # logged-in count is new: of the group's members (group_member, the same poll that wrote
    # group_state), how many have a User object WITH an identity — the 0.9.0 definition of a
    # login (docs/DESIGN_users_tab_logins.md); a hand-created account counts as a member and
    # not as a login. Pre-grouped, like the joins in users(), so it is 1:1 with the binding row
    # and cannot multiply it. Opt-in because all_bindings has three callers that want none of
    # this and are hot: the metrics scrape, the poller's audit planning, and /api/clusters.
    _REACH_JOIN = """
                 LEFT JOIN (SELECT m.cluster_id, m.group_name,
                                   COUNT(*) AS member_count,
                                   SUM(CASE WHEN u.has_identity = 1 THEN 1 ELSE 0 END) AS logged_in_count
                              FROM group_member m
                              LEFT JOIN ocp_user u
                                     ON u.cluster_id = m.cluster_id AND u.user_name = m.user_name
                             GROUP BY m.cluster_id, m.group_name) li
                        ON li.cluster_id = b.cluster_id AND li.group_name = b.group_name
                 LEFT JOIN ocp_user_status ust
                        ON ust.cluster_id = b.cluster_id"""

    def count_bindings_by_finding(self, cluster_id: str) -> dict[str, int]:
        """How many bindings fall in each tier, for the WHOLE cluster.

        Exists so the counts stay true when the rows beside them are paged. Counting a
        truncated page is the "showing 50 of 30" defect this codebase has now hit three
        times; the fix each time is a scalar query over the same predicate.
        """
        rows = self._rows(
            "SELECT" + self._FINDING_CASE + " AS finding, COUNT(*) AS n"
            + self._FINDING_FROM + " GROUP BY finding",
            (cluster_id,),
        )
        return {r["finding"]: r["n"] for r in rows}

    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0, *, reach: bool = False
    ) -> list[dict]:
        """Every group-subject binding, each classified.

        `reach=True` adds two columns that say who the binding reaches today: `member_count`, the
        group's synced members, and `logged_in_count`, how many of those members have logged in
        (a User with an identity) — both from the same membership rows. Both are NULL when no Group object exists — dangling,
        unresolved, built-in — so a consumer can tell "nobody" (0) from "not applicable"; and
        `logged_in_count` is NULL until the User objects have been read at least once. Only
        the findings endpoint asks; see _REACH_JOIN for why it is not unconditional.

        Includes the ones that resolve normally (`ok`). Those are the majority of a healthy
        cluster — 74 of 228 here — and omitting them made a view labelled "Bindings" show
        only the broken subset, which misrepresents what is on the cluster.

        `limit` because this was unbounded and grows with the cluster: measured at 2,280
        rows / 545,800 bytes at ten times the reference cluster, on a 30-second auto-refresh.
        Pair it with `count_bindings_by_finding` — the counts must describe the cluster, not
        the page.
        """
        # logged_in_count is NULL — not 0 — until the User objects have been read at least once
        # (no ocp_user_status row yet: a fresh install, or the cycle after migration 7 rebuilt
        # the table). A confident zero there would say "nobody in this group has logged in" about
        # a cluster the dashboard has not asked yet (Codex second pass, 2026-09-04). Once a read
        # has happened the count stands even if a later read was refused, like the Users tab.
        # Both numbers come from the SAME membership rows, so "members minus logged in" is exactly
        # the members with no login, by construction. group_state.member_count is the Group object's
        # own figure and the poller writes both in one transaction, so they agree — but nothing in
        # the store made them agree, and both second-pass reviewers found the seam (2026-09-04).
        # Group EXISTENCE still comes from group_state: a group with no member rows is 0, not NULL.
        reach_cols = ("""
                      CASE WHEN g.name IS NULL THEN NULL
                           ELSE COALESCE(li.member_count, 0) END AS member_count,
                      CASE WHEN g.name IS NULL OR ust.cluster_id IS NULL THEN NULL
                           ELSE COALESCE(li.logged_in_count, 0) END AS logged_in_count,"""
                      if reach else "")
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name,
                      b.managed_source, b.exception, b.audit_stamped,""" + reach_cols
               + self._FINDING_CASE + " AS finding"
               + self._FINDING_JOINS + (self._REACH_JOIN if reach else "") + self._FINDING_WHERE
               + """
                ORDER BY b.group_name, b.binding_kind, b.binding_namespace, b.binding_name""")
        params: list = [cluster_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def replace_user_bindings(
        self, cluster_id: str, rows: list[dict], observed_at: str
    ) -> dict[str, int]:
        """Replace this cluster's direct-user binding rows wholesale, recording the changes as
        binding_events first (subject_kind User) — see replace_bindings. Returns the counts."""
        with self._write() as conn:
            changes = self._append_binding_events(
                conn, cluster_id, "User", "user_name",
                current=conn.execute(
                    """SELECT binding_kind, binding_namespace, binding_name, user_name AS subject,
                              role_kind, role_name, is_platform
                         FROM user_binding WHERE cluster_id=?""", (cluster_id,)).fetchall(),
                incoming=rows, observed_at=observed_at,
            )
            conn.execute("DELETE FROM user_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO user_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, user_name, is_platform, observed_at)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:user_name,:is_platform,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )
        return changes

    def replace_users(self, cluster_id: str, users: list[dict], observed_at: str,
                      identity_created: dict[str, str] | None = None) -> None:
        """Replace this cluster's User records wholesale, and record that the read succeeded.

        Delete-then-insert rather than upsert, for the same reason replace_group_state gives:
        an upsert would leave a row behind after its User object is deleted, and a departed
        account still listed as a user of the cluster is worse than a missing name ever was.

        The caller must not reach here when the fetch was FORBIDDEN — passing [] would wipe
        every row and read as "nobody has logged in"; mark_users_unavailable is for that.
        Each record is what ClusterClient.fetch_users returns.
        """
        with self._write() as conn:
            conn.execute("DELETE FROM ocp_user WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO ocp_user(
                       cluster_id, user_name, full_name, created_at, providers, has_identity,
                       identity_created_at, identities, observed_at)
                   VALUES(:cluster_id,:user_name,:full_name,:created_at,:providers,:has_identity,
                          :identity_created_at,:identities,:observed_at)""",
                [
                    {"cluster_id": cluster_id,
                     "user_name": u["user_name"],
                     "full_name": u.get("full_name") or None,
                     "created_at": u.get("created_at"),
                     "providers": json.dumps(sorted(u.get("providers") or [])),
                     "has_identity": 1 if u.get("has_identity") else 0,
                     "identity_created_at": (identity_created or {}).get(u["user_name"]),
                     "identities": json.dumps(sorted(u.get("identities") or [])),
                     "observed_at": observed_at}
                    for u in users
                ],
            )
            conn.execute(
                """INSERT INTO ocp_user_status(cluster_id, state, observed_at) VALUES(?, 'ok', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='ok', observed_at=excluded.observed_at""",
                (cluster_id, observed_at),
            )

    def set_identities_status(self, cluster_id: str, state: str, observed_at: str) -> None:
        """The last poll's verdict on reading Identity objects: ok | forbidden | off."""
        with self._write() as conn:
            conn.execute(
                """INSERT INTO ocp_identity_status(cluster_id, state, observed_at) VALUES(?, ?, ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state=excluded.state,
                                                         observed_at=excluded.observed_at""",
                (cluster_id, state, observed_at),
            )

    def identities_source(self, cluster_id: str) -> dict | None:
        rows = self._rows(
            "SELECT state, observed_at FROM ocp_identity_status WHERE cluster_id=?", (cluster_id,))
        return dict(rows[0]) if rows else None

    def mark_users_unavailable(self, cluster_id: str, observed_at: str) -> None:
        """The list call was refused. Rows are left as they were; the status says why the tab
        should not present them — or their absence — as the truth."""
        with self._write() as conn:
            conn.execute(
                """INSERT INTO ocp_user_status(cluster_id, state, observed_at) VALUES(?, 'forbidden', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='forbidden', observed_at=excluded.observed_at""",
                (cluster_id, observed_at),
            )

    def user_full_name(self, cluster_id: str, user_name: str) -> str | None:
        """One display name, or None when that person has no User object or no name on it."""
        rows = self._rows(
            "SELECT full_name FROM ocp_user WHERE cluster_id=? AND user_name=?",
            (cluster_id, user_name),
        )
        return rows[0]["full_name"] if rows else None

    # ── Login capture ─────────────────────────────────────────────────────────────────────────────
    #
    # Every SQL shape below was run against a scratch WAL database with the real captured log fed
    # through gsd/loginlog.py before being written here. Two of them encode decisions that are easy
    # to undo by accident: the watermark upsert refuses to rewind, and the status upsert
    # deliberately does NOT touch started_at — docs/DESIGN_login_capture.md explains why the
    # watermark and the status are two different things, which is why the second looks redundant
    # and is not.

    def record_login_events(self, cluster_id: str, events: list[dict]) -> int:
        """Insert login attempts, ignoring ones already recorded. Returns rows actually inserted.

        INSERT OR IGNORE against UNIQUE(cluster_id, pod_name, user_name, at, outcome), because reads
        overlap ON PURPOSE — a sinceSeconds window plus a settle horizon — so the same line is seen
        more than once and must not insert twice.

        A dict rather than the parser's LoginAttempt, and that is not laziness: an attempt needs the
        POD it was read from to be deduplicated, and LoginAttempt cannot carry that without making the
        parser know where its input came from. gsd/logincapture.event_dict() builds these, so callers
        and tests do not hand-assemble them.
        """
        with self._write() as conn:
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO login_event(
                       cluster_id, pod_name, user_name, outcome, at,
                       provider, ldap_result_code, detail, observed_at, source, audit_id, kind,
                       client_id, identity_match, status_code, error_message, user_agent)
                   VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,
                          :provider,:ldap_result_code,:detail,:observed_at,:source,:audit_id,:kind,
                          :client_id,:identity_match,:status_code,:error_message,:user_agent)""",
                [{"source": "pod-log", "audit_id": None, "kind": "credential", "client_id": None,
                  "identity_match": None, "status_code": None, "error_message": None,
                  "user_agent": None, **e, "cluster_id": cluster_id}
                 for e in events],
            )
            return conn.total_changes - before

    def set_login_watermark(
        self, cluster_id: str, pod_name: str, settled_through: str, updated_at: str
    ) -> None:
        """Advance how far one pod's log is settled. REFUSES TO REWIND.

        `max(settled_through, excluded.settled_through)` rather than a plain assignment: a read that
        returns fewer lines than the last one — a truncated response, a partial failure, a retry with
        a shorter window — would otherwise move the watermark BACKWARDS and cause every attempt after
        it to be re-read and re-inserted. Verified: a second write with an earlier value leaves the
        later one in place.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO login_capture_watermark(
                       cluster_id, pod_name, settled_through, updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(cluster_id, pod_name) DO UPDATE SET
                       settled_through = max(settled_through, excluded.settled_through),
                       updated_at      = excluded.updated_at""",
                (cluster_id, pod_name, settled_through, updated_at),
            )

    def login_watermarks(self, cluster_id: str) -> dict[str, str]:
        """{pod_name: settled_through} for this cluster. Read by the capture loop only."""
        return {
            r["pod_name"]: r["settled_through"]
            for r in self._rows(
                "SELECT pod_name, settled_through FROM login_capture_watermark WHERE cluster_id=?",
                (cluster_id,),
            )
        }

    def prune_login_watermarks(self, cluster_id: str, live_pods: list[str]) -> int:
        """Forget watermarks for pods that no longer exist. Returns rows removed.

        Every oauth roll replaces the pods, so without this the table grows by one row per pod
        forever. The EVENTS those pods produced are kept — only the read position is dropped, and a
        pod that is gone will never produce another line to position against.

        An empty `live_pods` removes nothing rather than everything: a list call that returned no pods
        is far more likely to be a transient failure than a cluster with no oauth server, and treating
        it as authoritative would discard every read position on the cluster.
        """
        if not live_pods:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                "DELETE FROM login_capture_watermark WHERE cluster_id=? AND pod_name NOT IN (%s)"
                % ",".join("?" * len(live_pods)),
                (cluster_id, *live_pods),
            )
            return conn.total_changes - before


    # ── The audit-log login source (gsd/auditlog.py; D1) ─────────────────────────────────────────

    def record_audit_login_events(
        self, cluster_id: str, events: list[dict], correspondence_seconds: float = 0.25
    ) -> tuple[int, int]:
        """Insert audit-source attempts, LINKING one to an existing pod-log row where the two
        describe the same login. Returns (inserted, linked).

        Two checks per event, in order, each one index-served:
          1. its auditID is already stored — a re-read; nothing to do.
          2. a pod-log row for the same user, same success class, within the window and not yet
             linked — the same login seen from the other source: set audit_id on that row and
             keep it, because it carries the cause the audit log cannot.
        Otherwise it is a new row. There is deliberately NO coalescing of a browser login's two
        annotated requests: they are different KINDS (credential, then session) and each is its own
        row (the grounding note measured 133 session re-authorisations, every one with an earlier
        credential allow, up to 21 s apart — a 1 s window would have hidden 77 and left 56 as
        spurious logins). Per event rather than one executemany because check 2 reads before it
        writes; batches are bounded by the byte budget upstream.
        """
        inserted = linked = 0
        stamp = "%Y-%m-%dT%H:%M:%S.%fZ"
        with self._write() as conn:
            for e in events:
                if conn.execute(
                    "SELECT 1 FROM login_event WHERE cluster_id=? AND audit_id=?",
                    (cluster_id, e["audit_id"]),
                ).fetchone():
                    continue
                if e.get("kind", "credential") == "credential":
                    at = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
                    lo = (at - timedelta(seconds=correspondence_seconds)).strftime(stamp)
                    hi = (at + timedelta(seconds=correspondence_seconds)).strftime(stamp)
                    success = 1 if e["outcome"] == "success" else 0
                    twin = conn.execute(
                        """SELECT id FROM login_event
                            WHERE cluster_id=? AND user_name=? COLLATE NOCASE AND source='pod-log'
                              AND audit_id IS NULL AND at BETWEEN ? AND ?
                              AND (outcome='success') = ?
                            ORDER BY abs(julianday(at) - julianday(?)) LIMIT 1""",
                        (cluster_id, e["user_name"], lo, hi, success, e["at"]),
                    ).fetchone()
                    if twin:
                        conn.execute("UPDATE login_event SET audit_id=? WHERE id=?",
                                     (e["audit_id"], twin["id"]))
                        linked += 1
                        continue
                before = conn.total_changes
                conn.execute(
                    """INSERT OR IGNORE INTO login_event(
                           cluster_id, pod_name, user_name, outcome, at,
                           provider, ldap_result_code, detail, observed_at, source, audit_id, kind,
                           client_id, identity_match, status_code, error_message, user_agent)
                       VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,
                              :provider,:ldap_result_code,:detail,:observed_at,:source,:audit_id,
                              :kind,:client_id,:identity_match,:status_code,:error_message,
                              :user_agent)""",
                    {"ldap_result_code": None, "client_id": None, "identity_match": None,
                     "status_code": None, "error_message": None, "user_agent": None,
                     **e, "cluster_id": cluster_id},
                )
                added = conn.total_changes - before
                inserted += added
                if not added:
                    # The pod-log UNIQUE key (cluster, pod/node, user, at, outcome) ignored a row
                    # whose auditID is new: two responses for one person on one node in the same
                    # microsecond with the same outcome. Never observed (zero same-user same-stamp
                    # pairs in the reference cluster's 49,360 records); said here rather than
                    # rebuilt around, so it is a log line and not a silent loss if it ever happens.
                    log.warning("%s: audit event %s ignored — a row with the same node, user, "
                                "stamp and outcome already exists", cluster_id, e["audit_id"])
        return inserted, linked

    def audit_cursors(self, cluster_id: str, node_name: str) -> dict[str, dict]:
        """{file_name: {byte_offset, head, settled_through, complete}} for one node; `head` is
        (sha256 hex, byte count) of the file's first bytes, or None when never fingerprinted."""
        return {
            r["file_name"]: {"byte_offset": r["byte_offset"],
                             "head": ((r["head_sha256"], r["head_len"])
                                      if r["head_sha256"] else None),
                             "settled_through": r["settled_through"],
                             "complete": bool(r["complete"])}
            for r in self._rows(
                """SELECT file_name, byte_offset, head_sha256, head_len, settled_through, complete
                     FROM login_audit_cursor WHERE cluster_id=? AND node_name=?""",
                (cluster_id, node_name),
            )
        }

    def set_audit_cursor(
        self, cluster_id: str, node_name: str, file_name: str, byte_offset: int,
        settled_through: str | None, updated_at: str, *, complete: bool = False,
        head: tuple[str, int] | None = None,
    ) -> None:
        """Write one file's cursor. A plain assignment, not a max(): rotation legitimately moves
        audit.log's cursor BACK to 0, and a late write from a demoted leader is harmless here
        because auditID makes a re-read free — the opposite trade from the pod-log watermark.
        `head` is assigned as given too, so a reset to byte 0 clears the fingerprint."""
        with self._write() as conn:
            conn.execute(
                """INSERT INTO login_audit_cursor(
                       cluster_id, node_name, file_name, byte_offset, head_sha256, head_len,
                       settled_through, complete, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(cluster_id, node_name, file_name) DO UPDATE SET
                       byte_offset     = excluded.byte_offset,
                       head_sha256     = excluded.head_sha256,
                       head_len        = excluded.head_len,
                       settled_through = COALESCE(excluded.settled_through, settled_through),
                       complete        = excluded.complete,
                       updated_at      = excluded.updated_at""",
                (cluster_id, node_name, file_name, byte_offset,
                 head[0] if head else None, head[1] if head else 0,
                 settled_through, int(complete), updated_at),
            )

    def prune_audit_cursors(self, cluster_id: str, node_name: str, live_files: list[str]) -> int:
        """Forget cursors for files that rotated away (audit-log-maxbackup=10 deletes the oldest).
        An empty list removes nothing, for the reason prune_login_watermarks gives."""
        if not live_files:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                "DELETE FROM login_audit_cursor WHERE cluster_id=? AND node_name=? "
                "AND file_name NOT IN (%s)" % ",".join("?" * len(live_files)),
                (cluster_id, node_name, *live_files),
            )
            return conn.total_changes - before

    def audit_settled_by_node(self, cluster_id: str) -> dict[str, str]:
        """{node: newest settled_through across its files} — the per-node liveness the metrics export."""
        return {
            r["node_name"]: r["settled"]
            for r in self._rows(
                """SELECT node_name, MAX(settled_through) AS settled
                     FROM login_audit_cursor WHERE cluster_id=? AND settled_through IS NOT NULL
                    GROUP BY node_name""",
                (cluster_id,),
            )
        }

    def user_identities(self, cluster_id: str) -> dict[str, list[str]]:
        """{user_name: [Identity names]} for every User the last poll read — the join the audit-log
        source resolves a login's identity through (case-insensitively, by the caller)."""
        return {
            r["user_name"]: json.loads(r["identities"] or "[]")
            for r in self._rows(
                "SELECT user_name, identities FROM ocp_user WHERE cluster_id=?", (cluster_id,)
            )
        }
    def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete events older than `before_at`, at most `max_rows` per call. Returns rows deleted.

        BOUNDED, because this runs on the poll thread against a single-writer database: an unbounded
        DELETE across a long retention backlog holds the write lock for as long as it takes, and
        every reader and the next poll wait behind it. The caller treats a return of `max_rows` as
        "backlog remains, continue next cycle". A non-positive limit deletes NOTHING rather than
        everything: SQLite defines `LIMIT -1` as unlimited — the exact opposite of this method's
        promise — so the bound is enforced here instead of trusted to every future caller.

        `DELETE ... LIMIT` is NOT used — that syntax needs SQLITE_ENABLE_UPDATE_DELETE_LIMIT and is
        not compiled into this build (verified: `near "LIMIT": syntax error`). The id-IN-subselect
        form is core SQL and its inner select is index-served (verified: SEARCH login_event USING
        COVERING INDEX login_event_lookup).
        """
        if max_rows <= 0:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                """DELETE FROM login_event WHERE id IN (
                       SELECT id FROM login_event
                        WHERE cluster_id=? AND at < ?
                        ORDER BY at LIMIT ?)""",
                (cluster_id, before_at, max_rows),
            )
            return conn.total_changes - before

    # The history tables retention may touch. A closed tuple, interpolated into SQL by
    # _prune_history — never a caller's string.
    _HISTORY_TABLES = ("membership_event", "sync_event", "binding_event")

    def prune_membership_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete membership events observed before `before_at`, at most `max_rows`. Returns rows deleted.

        THE IRREPLACEABLE TABLE. The poller calls this only after the cycle's backup and only on
        the leader (Poller._prune_history); this method enforces the batch bound, not the policy.
        Same shape and same reasons as prune_login_events: id-IN-subselect because DELETE ... LIMIT
        is not compiled into this build, and a non-positive limit deletes NOTHING because SQLite
        reads LIMIT -1 as unlimited. The subselect is served by membership_event_by_time.
        """
        return self._prune_history("membership_event", cluster_id, before_at, max_rows)

    def prune_sync_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete sync events OBSERVED before `before_at`, at most `max_rows`. Returns rows deleted.

        observed_at, not synced_at: the window is about how long this dashboard keeps what it
        saw, and observed_at is the stamp it controls. Served by sync_event_by_time.
        """
        return self._prune_history("sync_event", cluster_id, before_at, max_rows)

    def _prune_history(self, table: str, cluster_id: str, before_at: str, max_rows: int) -> int:
        if table not in self._HISTORY_TABLES:
            raise ValueError(f"not a history table: {table!r}")
        if max_rows <= 0:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                f"""DELETE FROM {table} WHERE id IN (
                       SELECT id FROM {table}
                        WHERE cluster_id=? AND observed_at < ?
                        ORDER BY observed_at LIMIT ?)""",
                (cluster_id, before_at, max_rows),
            )
            return conn.total_changes - before

    def history_retained_since(self, cluster_id: str) -> dict[str, str | None]:
        """The oldest observed_at still held, per history table — the edge retention has cut to.

        None for a table with no rows for this cluster. Two MIN()s over the (cluster_id,
        observed_at) indexes: an index seek each, not a scan, so a handler can afford it on
        every request. The API pairs it with the configured window so a timeline that begins
        here is read as CUT here rather than started here.
        """
        out: dict[str, str | None] = {}
        for table in self._HISTORY_TABLES:
            row = self._row(
                f"SELECT MIN(observed_at) AS since FROM {table} WHERE cluster_id=?", (cluster_id,)
            )
            out[table] = row["since"] if row else None
        return out

    def record_login_read(self, cluster_id: str, read_at: str) -> None:
        """Record a SUCCESSFUL read. `started_at` is set once; `last_read_at` advances every time.

        This is the PRODUCT boundary, deliberately separate from the per-pod watermark. `started_at`
        answers "watching since", which is what stops a sparse table reading as "nobody logged in" —
        and the watermark cannot answer it, because it is per pod, it moves constantly, and
        prune_login_watermarks removes the rows that would have carried the evidence.

        The upsert omits started_at from its SET clause ON PURPOSE. Adding it there would silently
        turn a stable boundary into "the most recent read", and the UI would then claim it had only
        been watching since a moment ago after months of history.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO login_capture_status(cluster_id, started_at, last_read_at)
                   VALUES(?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET last_read_at = excluded.last_read_at""",
                (cluster_id, read_at, read_at),
            )

    def login_capture_status(self, cluster_id: str) -> dict | None:
        """{started_at, last_read_at}, or None when capture has never succeeded here.

        None is meaningful and must not be flattened into zeros: it means the UI should say capture is
        not running rather than showing an empty result as though it were an answer.
        """
        rows = self._rows(
            "SELECT started_at, last_read_at FROM login_capture_status WHERE cluster_id=?",
            (cluster_id,),
        )
        return rows[0] if rows else None

    def login_events(
        self,
        cluster_id: str,
        user_name: str | None = None,
        outcome: str | None = None,
        since: str | None = None,
        limit: int = 200,
        kinds: tuple[str, ...] | None = None,
    ) -> list[dict]:
        """Login attempts, newest first, enriched with what the dashboard already knows about the user.

        `kinds` narrows to the audit-log source's kinds (credential, cli, session); None means every
        row. Pod-log rows are `credential` by construction, so the default view (credential + cli)
        shows them as before and hides only the audit log's session re-authorisations.

        `full_name` comes from ocp_user, which exists only for people who have logged in — the same
        source the member lists use, so one person reads the same way on both pages.

        `known_user` and `has_history` are the two that make this worth building. A username here that
        is in NO synced group (`known_user = 0`) is the most interesting row this feature produces, and
        `has_history = 1` separates the two reasons for it: somebody whose access was REMOVED and is
        still trying, versus a name nobody has ever governed. Both are EXISTS subqueries against
        indexed columns rather than joins, so neither multiplies rows.

        `since` is here although Designer A's contract dropped it: the index is (cluster_id, at DESC),
        so `at >= ?` is served by it, and the alternative is the API over-fetching and filtering in
        Python. If it ever costs anything, EXPLAIN QUERY PLAN is the check.
        """
        where = ["e.cluster_id = ?"]
        params: list = [cluster_id]
        if user_name:
            where.append("e.user_name = ?")
            params.append(user_name)
        if outcome:
            where.append("e.outcome = ?")
            params.append(outcome)
        if kinds:
            where.append("e.kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        if since:
            where.append("e.at >= ?")
            params.append(since)
        params.append(limit)
        return self._rows(
            """SELECT e.user_name, e.outcome, e.at, e.provider, e.ldap_result_code, e.detail,
                      e.pod_name, e.observed_at, e.source, e.audit_id, e.kind, e.client_id,
                      e.identity_match, e.status_code, e.error_message, e.user_agent,
                      u.full_name,
                      EXISTS(SELECT 1 FROM group_member m
                              WHERE m.cluster_id = e.cluster_id
                                AND m.user_name  = e.user_name) AS known_user,
                      EXISTS(SELECT 1 FROM membership_event h
                              WHERE h.cluster_id = e.cluster_id
                                AND h.user_name  = e.user_name) AS has_history
                 FROM login_event e
                 LEFT JOIN ocp_user u
                        ON u.cluster_id = e.cluster_id AND u.user_name = e.user_name
                WHERE """ + " AND ".join(where) +
            " ORDER BY e.at DESC, e.id DESC LIMIT ?",
            tuple(params),
        )

    def count_login_events(self, cluster_id: str, user_name: str) -> int:
        """This user's whole-record attempt count, for the self tier's `total`.

        The self-scoped logins page must not inherit the cluster-wide total — a number
        computed over rows the viewer cannot see — and must not count its own page (the
        "showing 50 of 30" defect class). One scalar over login_event_by_user, a covering
        index (plan measured on the live database).
        """
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM login_event WHERE cluster_id=? AND user_name=?",
            (cluster_id, user_name),
        )
        return rows[0]["n"] if rows else 0

    # ── The login gate ────────────────────────────────────────────────────────────────────────────
    #
    # Holding RBAC access and being able to LOG IN are different things, and this is the only place the
    # dashboard can see the second. Measured on the reference cluster: 10 people held access through
    # synced groups, 7 were in the gate group, so 3 held access they could not exercise.

    def set_cluster_access_group(
        self, cluster_id: str, dn: str, source: str, group_name: str | None, observed_at: str
    ) -> None:
        """Record which group gates authentication, and which of the two ways we learned it.

        `group_name` is resolved by the CALLER from group_state, not joined here, because the answer
        must be a snapshot taken with the same poll that wrote the groups — resolving it at read time
        would let a group deleted between poll and read turn a known gate into an unknown one.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO cluster_access_group(cluster_id, dn, source, group_name, observed_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET
                       dn=excluded.dn, source=excluded.source,
                       group_name=excluded.group_name, observed_at=excluded.observed_at""",
                (cluster_id, dn, source, group_name, observed_at),
            )

    def clear_cluster_access_group(self, cluster_id: str) -> None:
        """Forget the gate group entirely.

        Called when neither configuration nor discovery produces a DN. DELETE rather than leaving the
        last known value: a gate that has been REMOVED from the identity provider means every account
        in the search base can now sign in, and a stale row would keep reporting findings against a
        group that no longer gates anything — the page would show a shrinking list of "cannot log in"
        people who can all log in perfectly well.
        """
        with self._write() as conn:
            conn.execute("DELETE FROM cluster_access_group WHERE cluster_id=?", (cluster_id,))

    def cluster_access_group(self, cluster_id: str) -> dict | None:
        """The gate group row, or None when no gate is known."""
        rows = self._rows(
            "SELECT dn, source, group_name, observed_at FROM cluster_access_group WHERE cluster_id=?",
            (cluster_id,),
        )
        return rows[0] if rows else None

    def access_without_login(self, cluster_id: str, limit: int = 200) -> list[dict]:
        """People who hold access through a synced group but are NOT in the login-gate group.

        THE FINDING THIS WHOLE FEATURE EXISTS FOR: a role granted to somebody who cannot authenticate
        is access that can never be used, and it is invisible to every other view in this dashboard
        because they all start from RBAC and stop there.

        The gate group is EXCLUDED from "holds access", which is the subtlety that makes the query
        mean anything: it is a synced group like any other, so counting it would make every gate
        member 'someone with access' and the finding would be empty on every cluster.

        A LEFT JOIN for the display name and an aggregate for the group list, so one row per person
        rather than one per membership — a person in four groups is one finding, not four.
        """
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"]:
            return []
        return self._rows(
            """SELECT m.user_name,
                      COUNT(DISTINCT m.group_name) AS group_count,
                      GROUP_CONCAT(DISTINCT m.group_name) AS groups,
                      MIN(m.first_seen_at) AS first_seen_at,
                      u.full_name,
                      EXISTS(SELECT 1 FROM login_event e
                              WHERE e.cluster_id = m.cluster_id
                                AND e.user_name  = m.user_name) AS has_tried
                 FROM group_member m
                 LEFT JOIN ocp_user u
                        ON u.cluster_id = m.cluster_id AND u.user_name = m.user_name
                WHERE m.cluster_id = ?
                  AND m.group_name <> ?
                  AND NOT EXISTS(SELECT 1 FROM group_member g
                                  WHERE g.cluster_id = m.cluster_id
                                    AND g.group_name = ?
                                    AND g.user_name  = m.user_name)
                GROUP BY m.user_name
                ORDER BY group_count DESC, m.user_name
                LIMIT ?""",
            (cluster_id, access["group_name"], access["group_name"], limit),
        )

    def count_access_without_login(self, cluster_id: str) -> int:
        """How many there are in total, so a limited list can say what it truncated."""
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"]:
            return 0
        rows = self._rows(
            """SELECT COUNT(DISTINCT m.user_name) AS n
                 FROM group_member m
                WHERE m.cluster_id = ?
                  AND m.group_name <> ?
                  AND NOT EXISTS(SELECT 1 FROM group_member g
                                  WHERE g.cluster_id = m.cluster_id
                                    AND g.group_name = ?
                                    AND g.user_name  = m.user_name)""",
            (cluster_id, access["group_name"], access["group_name"]),
        )
        return rows[0]["n"] if rows else 0

    def login_without_access(self, cluster_id: str, limit: int = 200) -> list[dict]:
        """People in the login-gate group who hold no access through any other synced group.

        The quieter half, and not automatically a problem: somebody newly onboarded, or an account
        that only ever needs to read something granted to `system:authenticated`. It is worth showing
        because it is also how a service identity inside the gate group surfaces — on the reference
        directory the group's eighth member is the oauth BIND account, which carries a `uid` and so
        syncs like a person.

        The WHERE comes from _login_without_access_where, shared with count_login_without_access so
        the page and its whole-set count cannot disagree — the S3 lesson, applied before it recurs.
        """
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"]:
            return []
        where = self._login_without_access_where()
        return self._rows(
            """SELECT m.user_name, m.first_seen_at, u.full_name,
                      EXISTS(SELECT 1 FROM login_event e
                              WHERE e.cluster_id=m.cluster_id AND e.user_name=m.user_name) AS has_tried
                 FROM group_member m
                 LEFT JOIN ocp_user u
                        ON u.cluster_id=m.cluster_id AND u.user_name=m.user_name"""
            + where + " ORDER BY m.user_name LIMIT ?",
            (cluster_id, access["group_name"], access["group_name"], limit),
        )

    @staticmethod
    def _login_without_access_where() -> str:
        """One predicate for both the page and its whole-set count."""
        return """ WHERE m.cluster_id = ?
                     AND m.group_name = ?
                     AND NOT EXISTS(SELECT 1 FROM group_member g
                                     WHERE g.cluster_id = m.cluster_id
                                       AND g.user_name  = m.user_name
                                       AND g.group_name <> ?)"""

    def count_login_without_access(self, cluster_id: str) -> int:
        """Whole-set count for a list that is deliberately paged."""
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"]:
            return 0
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM group_member m" + self._login_without_access_where(),
            (cluster_id, access["group_name"], access["group_name"]),
        )
        return rows[0]["n"] if rows else 0

    def cluster_access_summary(self, cluster_id: str) -> dict:
        """Whole-cluster counts, never counts inferred from a page."""
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"]:
            return {"gated_members": 0, "with_access": 0, "access_without_login": 0,
                    "login_without_access": 0}
        gate = access["group_name"]
        rows = self._rows(
            """SELECT
                 (SELECT COUNT(*) FROM group_member
                   WHERE cluster_id=? AND group_name=?) AS gated_members,
                 (SELECT COUNT(DISTINCT user_name) FROM group_member
                   WHERE cluster_id=? AND group_name<>?) AS with_access""",
            (cluster_id, gate, cluster_id, gate),
        )
        base = rows[0] if rows else {"gated_members": 0, "with_access": 0}
        return {
            "gated_members": base["gated_members"],
            "with_access": base["with_access"],
            "access_without_login": self.count_access_without_login(cluster_id),
            "login_without_access": self.count_login_without_access(cluster_id),
        }

    def is_in_access_group(self, cluster_id: str, user_names: list[str]) -> dict[str, bool]:
        """Which of these usernames are in the login-gate group.

        A batch lookup rather than one call per row: the logins page asks about up to 200 attempts at
        once, and 200 round trips through _rows would be 200 statements inside one snapshot.

        An empty dict when no gate is known, which the caller must treat as "unknown" rather than
        "nobody is a member" — the difference between those two is the whole point of the panel.
        """
        access = self.cluster_access_group(cluster_id)
        if not access or not access["group_name"] or not user_names:
            return {}
        names = sorted(set(user_names))
        rows = self._rows(
            "SELECT user_name FROM group_member WHERE cluster_id=? AND group_name=? "
            "AND user_name IN (%s)" % ",".join("?" * len(names)),
            (cluster_id, access["group_name"], *names),
        )
        member = {r["user_name"] for r in rows}
        return {name: name in member for name in names}

    @staticmethod
    def _not_local_provider(alias: str, exclude_providers: tuple[str, ...]) -> tuple[str, list]:
        """"This row is not an attempt on a local HTPasswd provider", for one table alias.

        Extracted so the ungoverned WHERE and the `last_outcome` subquery nested inside it cannot
        disagree about what "excluded" means — which they did. The subquery looked at ALL of a user's
        rows, so kubeadmin rendered on the live cluster as `1 attempt, last seen 19:55:58, last
        outcome signed in`, where that outcome came from a 20:10:59 break-glass row the same line
        claimed not to count. Every column of a row has to describe the same set of attempts, or the
        row is not a fact about anything.

        `provider IS NULL OR NOT IN (...)`: a row whose provider was never determined must still
        count. Excluding NULL would quietly drop the failures whose provider could not be identified,
        which are exactly the ones worth looking at.
        """
        if not exclude_providers:
            return "", []
        placeholders = ",".join("?" * len(exclude_providers))
        return (f" AND ({alias}.provider IS NULL OR {alias}.provider NOT IN ({placeholders}))",
                list(exclude_providers))

    def _ungoverned_where(self, exclude_providers: tuple[str, ...]) -> tuple[str, list]:
        """The shared "appears in the logs but is in no synced group" predicate.

        One definition used by both the count and the rows, because two copies of a predicate this
        load-bearing WILL drift — and a count that disagrees with its own list is worse than either.

        `e.provider IS NULL OR NOT IN (...)`: a row whose provider was never determined must still
        count. Excluding NULL would quietly drop the failures whose provider could not be identified,
        which are exactly the ones worth looking at.
        """
        where = """ WHERE e.cluster_id = ?
                      AND NOT EXISTS(SELECT 1 FROM group_member m
                                      WHERE m.cluster_id = e.cluster_id
                                        AND m.user_name  = e.user_name)"""
        clause, params = self._not_local_provider("e", exclude_providers)
        return where + clause, params

    def ungoverned_login_users(
        self, cluster_id: str, exclude_providers: tuple[str, ...] = (), limit: int = 50
    ) -> list[dict]:
        """Usernames in the logs that belong to no synced group, aggregated per person.

        `exclude_providers` is how break-glass accounts are kept out: a success on the HTPasswd
        provider is kubeadmin or developer, which are not people to offboard. Passed in rather than
        read here, because which providers are local is a cluster fact the store has no way to know.
        """
        where, params = self._ungoverned_where(exclude_providers)
        # The SAME exclusion inside the subquery, from the same helper. Without it `last_outcome`
        # reported an attempt that this row's own count, first_at and last_at excluded.
        sub_clause, sub_params = self._not_local_provider("e2", exclude_providers)
        return self._rows(
            """SELECT e.user_name,
                      COUNT(*) AS attempts,
                      MIN(e.at) AS first_at,
                      MAX(e.at) AS last_at,
                      (SELECT e2.outcome FROM login_event e2
                        WHERE e2.cluster_id = e.cluster_id AND e2.user_name = e.user_name"""
            + sub_clause +
            """ ORDER BY e2.at DESC, e2.id DESC LIMIT 1) AS last_outcome,
                      EXISTS(SELECT 1 FROM membership_event h
                              WHERE h.cluster_id = e.cluster_id
                                AND h.user_name  = e.user_name) AS has_history
                 FROM login_event e""" + where +
            " GROUP BY e.user_name ORDER BY last_at DESC LIMIT ?",
            # Placeholder order follows the SQL TEXT, not the logical order: the subquery sits in the
            # SELECT list, so its parameters bind BEFORE the WHERE clause's cluster_id.
            (*sub_params, cluster_id, *params, limit),
        )

    def count_ungoverned_login_users(
        self, cluster_id: str, exclude_providers: tuple[str, ...] = ()
    ) -> int:
        """How many there are in total, so a limited list can say what it truncated.

        Same predicate as the rows above, from the same helper. docs/api-contract.md requires any
        handler taking `limit` to report `total` or `truncated`, and a list that silently stops at 50
        reads as "there are 50".
        """
        where, params = self._ungoverned_where(exclude_providers)
        rows = self._rows(
            "SELECT COUNT(DISTINCT e.user_name) AS n FROM login_event e" + where,
            (cluster_id, *params),
        )
        return rows[0]["n"] if rows else 0

    def login_event_summary(
        self, cluster_id: str, exclude_providers: tuple[str, ...] = ()
    ) -> dict:
        """Cluster-level totals for the page header.

        Designer A's signature, not B's: B also wanted user_name/since here, but a summary filtered to
        one user is that user's row in login_events, and a summary over a window is a different
        question from "what does this cluster look like". Keeping it cluster-level means the header
        cannot disagree with itself depending on which filter is active.
        """
        per_outcome = self._rows(
            """SELECT outcome, COUNT(*) AS n, MIN(at) AS first_at, MAX(at) AS last_at
                 FROM login_event WHERE cluster_id=? GROUP BY outcome""",
            (cluster_id,),
        )
        by_outcome = {r["outcome"]: r["n"] for r in per_outcome}
        distinct = self._rows(
            "SELECT COUNT(DISTINCT user_name) AS n FROM login_event WHERE cluster_id=?",
            (cluster_id,),
        )
        return {
            "total": sum(by_outcome.values()),
            "by_outcome": by_outcome,
            "distinct_users": distinct[0]["n"] if distinct else 0,
            "ungoverned_users": self.count_ungoverned_login_users(cluster_id, exclude_providers),
            "first_at": min((r["first_at"] for r in per_outcome), default=None),
            "last_at": max((r["last_at"] for r in per_outcome), default=None),
        }

    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]:
        """Direct-user grants rolled up per namespace — the migration worklist.

        Ordered worst-first by PRIVILEGE, then cluster-scope, then count, then name — one
        forgotten cluster-admin outranks twenty view grants, and ordering by count alone
        put the twenty first and pushed the cluster-admin below the fold.

        Platform identities are excluded from the rollup (they are not migratable and would
        swamp it) but counted separately by `platform_user_binding_count`, so the page can
        say what it left out rather than quietly shrinking the number.

        `distinct_users` matters as much as the binding count: one person with five
        bindings in a namespace is one offboarding risk, five people is five.

        `users` is a LIST, stitched in from a second read, never a GROUP_CONCAT. Same
        reason as `provider_keys` in `groupsyncs()` below: a delimited string means picking
        a delimiter the value can never contain, and a user name can be an LDAP DN. The page
        unions these lists to count distinct people, so with GROUP_CONCAT a single
        `cn=jdoe,ou=people,dc=example,dc=com` split into four and the KPI read 4 people
        beside a row whose own People column said 1.
        """
        with self.read_snapshot():
            rows = self._rows(
                """SELECT CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          COUNT(*) AS bindings,
                          COUNT(DISTINCT user_name) AS distinct_users,
                          -- The worst privilege granted here, and whether it is
                          -- cluster-wide. Risk is ranked on PRIVILEGE, not on count: one
                          -- forgotten cluster-admin outranks twenty view grants, and a
                          -- list sorted by count puts the twenty first.
                          MAX(CASE role_name WHEN 'cluster-admin' THEN 4 WHEN 'admin' THEN 3
                                             WHEN 'edit' THEN 2 ELSE 1 END) AS worst_privilege,
                          MAX(CASE WHEN binding_namespace = '' THEN 1 ELSE 0 END)
                              AS cluster_scoped
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    GROUP BY namespace
                    ORDER BY worst_privilege DESC, cluster_scoped DESC,
                             bindings DESC, namespace""",
                (cluster_id,),
            )
            people: dict[str, list[str]] = {}
            for row in self._rows(
                """SELECT DISTINCT
                          CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          user_name
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    ORDER BY user_name""",
                (cluster_id,),
            ):
                people.setdefault(row["namespace"], []).append(row["user_name"])
            for row in rows:
                row["users"] = people.get(row["namespace"], [])
            return rows

    # Namespace sentinel for the cluster-scoped rows. Their binding_namespace is '', which
    # an HTTP query string cannot distinguish from "parameter absent", so the API and the
    # UI both speak this token and it is translated here at the boundary.
    CLUSTER_SCOPE = "(cluster-scoped)"

    def _direct_user_binding_where(
        self, cluster_id: str, include_platform: bool, namespace: str | None,
        user_name: str | None = None,
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its COUNT, built once.

        Built once on purpose: a count computed from a different predicate than the rows
        it describes is how "showing 50 of 30" reaches a page, and the two drifting apart
        during a later edit is the likeliest way for that to happen.

        `user_name` is the privacy scope (the user_activity() contract): the self tier
        sees only bindings that name the viewer. Byte-exact — a direct binding names the
        subject in whatever form the administrator typed, so a binding naming `jdoe`
        stays invisible to `john.doe`, which is fail-closed and correct: the dashboard
        cannot prove those are the same person. Bounded scan of the cluster's slice via
        user_binding_by_namespace (45 rows at reference scale, plan measured); no
        dedicated index until a real cluster shows it needed.
        """
        sql, params = " WHERE cluster_id=?", [cluster_id]
        if not include_platform:
            sql += " AND is_platform=0"
        if namespace is not None:
            sql += " AND binding_namespace=?"
            params.append("" if namespace == self.CLUSTER_SCOPE else namespace)
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        return sql, params

    def direct_user_bindings(
        self,
        cluster_id: str,
        include_platform: bool = False,
        namespace: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        user_name: str | None = None,
    ) -> list[dict]:
        """Every binding naming a User subject, worst-first by privilege then namespace.

        NOT to be confused with `user_bindings(cluster_id, user_name)` above, which answers
        the opposite question: what a person reaches THROUGH their group memberships. This
        one is the governance violation — a grant that names the person directly. The
        original name for this collided with that method and silently overrode it, which
        broke two reverse-lookup tests; the names now say which question each answers.

        `namespace` and `limit` exist because this was previously unbounded at every layer:
        the store returned every row, the API returned every row, and the page rendered
        every row. On a cluster with thousands of direct grants that is a payload and a DOM
        nobody asked for, to show a list nobody can read. Pair with
        `count_direct_user_bindings` so the caller can say what it left out — a silently
        truncated audit list is worse than a slow one.
        """
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind,
                         role_name, user_name, is_platform
                    FROM user_binding""" + where +
               # cluster-admin first, then cluster-scoped, then namespaced: the order
               # somebody migrating would work in. Ordering is applied BEFORE the limit, so
               # a truncated page is the worst N rather than an arbitrary N.
               """ ORDER BY CASE WHEN role_name='cluster-admin' THEN 0 ELSE 1 END,
                            CASE WHEN binding_namespace='' THEN 0 ELSE 1 END,
                            binding_namespace, user_name""")
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def count_direct_user_bindings(
        self, cluster_id: str, include_platform: bool = False,
        namespace: str | None = None, user_name: str | None = None,
    ) -> int:
        """How many rows `direct_user_bindings` would return before its limit."""
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + where, tuple(params))
        return rows[0]["n"] if rows else 0

    def platform_user_binding_count(self, cluster_id: str) -> int:
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
            (cluster_id,),
        )
        return int(rows[0]["n"]) if rows else 0

    # -- namespace-configuration-operator health -----------------------------------------

    def replace_operator_configs(
        self, cluster_id: str, configs: list[dict] | None, observed_at: str
    ) -> None:
        """Replace this cluster's operator-config health rows. None means CRDs absent.

        Presence is stored explicitly rather than inferred from row count, because
        "operator not installed" and "operator installed with zero CRs" are different
        truths: the first must render as nothing at all, the second as an empty-but-real
        section. Conflating them shows 'all healthy' for a concept the cluster lacks.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO operator_config_presence(cluster_id, present, observed_at)
                   VALUES(?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET
                       present=excluded.present, observed_at=excluded.observed_at""",
                (cluster_id, 0 if configs is None else 1, observed_at),
            )
            conn.execute("DELETE FROM operator_config_state WHERE cluster_id=?", (cluster_id,))
            if configs:
                conn.executemany(
                    """INSERT INTO operator_config_state(
                           cluster_id, kind, name, error_at, error_message,
                           success_at, observed_at)
                       VALUES(:cluster_id,:kind,:name,:error_at,:error_message,
                              :success_at,:observed_at)""",
                    [{**c, "cluster_id": cluster_id, "observed_at": observed_at}
                     for c in configs],
                )

    def groupsync_present(self, cluster_id: str) -> bool | None:
        """Is the GroupSync CRD installed? None = never observed (no poll since upgrade).

        Three-valued on purpose. False must mean "we looked and it is not there", so it can
        raise an alert; a cluster that has not polled since the migration added this table has
        not been looked at, and alerting on that would fire once for every existing cluster on
        upgrade.
        """
        row = self._row(
            "SELECT present FROM groupsync_presence WHERE cluster_id=?", (cluster_id,)
        )
        return None if row is None else bool(row["present"])

    def operator_configs(self, cluster_id: str) -> dict:
        """Health of the policy operator's CRs: {present: bool, configs: [...]}."""
        presence = self._row(
            "SELECT present FROM operator_config_presence WHERE cluster_id=?", (cluster_id,)
        )
        return {
            "present": bool(presence and presence["present"]),
            "configs": self._rows(
                """SELECT kind, name, error_at, error_message, success_at, observed_at
                     FROM operator_config_state WHERE cluster_id=?
                    ORDER BY kind, name""",
                (cluster_id,),
            ),
        }

    def upsert_reconcile_error(
        self,
        cluster_id: str,
        name: str,
        failed_at: str | None,
        generation: int | None,
        message: str | None,
    ) -> None:
        with self._write() as conn:
            if failed_at is None:
                conn.execute(
                    "DELETE FROM reconcile_error WHERE cluster_id=? AND groupsync_name=?",
                    (cluster_id, name),
                )
                return
            conn.execute(
                """INSERT INTO reconcile_error(cluster_id, groupsync_name, failed_at,
                       observed_generation, message)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cluster_id, groupsync_name) DO UPDATE SET
                       failed_at=excluded.failed_at,
                       observed_generation=excluded.observed_generation,
                       message=excluded.message""",
                (cluster_id, name, failed_at, generation, message),
            )

    # -- dashboard access ----------------------------------------------------------------

    def record_user_activity(self, buckets: list[dict]) -> int:
        """Merge buffered per-user-per-day activity. Returns the number of buckets written.

        One transaction for the whole flush, not one per user: this runs while the poller
        may be mid-cycle, and taking the write lock once for a handful of rows keeps it out
        of the way. Callers buffer in memory and flush on an interval — see activity.py for
        why a write per request is the wrong shape.

        first/last_seen use SQLite's two-argument min/max rather than the caller's values,
        so a flush that arrives out of order — a slow flush overtaken by a later one — still
        widens the window instead of narrowing it. Lexicographic comparison IS chronological
        here because now_iso() emits fixed-width UTC with a Z suffix.
        """
        if not buckets:
            return 0
        with self._tx() as conn:
            conn.executemany(
                """INSERT INTO dashboard_user_activity(
                       user_name, day, email, first_seen_at, last_seen_at, request_count)
                   VALUES(:user_name,:day,:email,:first_seen_at,:last_seen_at,:request_count)
                   ON CONFLICT(user_name, day) DO UPDATE SET
                       email         = COALESCE(excluded.email, email),
                       first_seen_at = min(first_seen_at, excluded.first_seen_at),
                       last_seen_at  = max(last_seen_at, excluded.last_seen_at),
                       request_count = request_count + excluded.request_count""",
                buckets,
            )
        return len(buckets)

    def prune_user_activity(self, before_day: str) -> int:
        """Drop activity rows for days strictly before ``before_day`` (YYYY-MM-DD)."""
        with self._tx() as conn:
            cursor = conn.execute(
                "DELETE FROM dashboard_user_activity WHERE day < ?", (before_day,)
            )
            return cursor.rowcount

    def _user_activity_where(
        self, since_day: str | None, user_name: str | None
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its summary, built once.

        Built once for the same reason as `_direct_user_binding_where`: a total computed
        from a different predicate than the rows it describes is how "showing 50 of 30"
        reaches a page.
        """
        where, params = [], []
        if since_day:
            where.append("day >= ?")
            params.append(since_day)
        if user_name:
            where.append("user_name = ?")
            params.append(user_name)
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def user_activity(
        self,
        since_day: str | None = None,
        limit: int = 500,
        user_name: str | None = None,
    ) -> list[dict]:
        """Activity rows, optionally narrowed to one user.

        `user_name` is the privacy scope, not a convenience filter: the API passes the
        authenticated viewer's own name unless the deployment has opted into showing
        everyone. Filtering in SQL rather than after the fetch matters — `limit` is applied
        by the database, so filtering afterwards would silently return fewer than `limit`
        of the caller's own rows whenever busier colleagues filled the page.

        BOUNDED. Pair with `user_activity_summary` for any headline number: counting these
        rows counts the page, not the record.
        """
        where, params = self._user_activity_where(since_day, user_name)
        sql = ("""SELECT user_name, day, email, first_seen_at, last_seen_at, request_count
                   FROM dashboard_user_activity""" + where +
               " ORDER BY day DESC, user_name LIMIT ?")
        params.append(limit)
        return self._rows(sql, params)

    def user_activity_summary(
        self, since_day: str | None = None, user_name: str | None = None
    ) -> dict:
        """Totals over the WHOLE activity set the caller may see, ignoring any row limit.

        The Usage tab used to compute its KPIs from the returned rows, which are capped:
        measured at 1,092 stored rows it reported 167 days and 5,000 interactions where the
        truth was 364 and 10,920.

        Each `COUNT(DISTINCT ...)` here is one scalar over the whole filtered set, not a
        per-group count that anything adds up — summing per-day distinct users would count
        everybody again on every day they came back.
        """
        where, params = self._user_activity_where(since_day, user_name)
        rows = self._rows(
            """SELECT COUNT(*) AS rows_total,
                      COUNT(DISTINCT user_name) AS distinct_users,
                      COUNT(DISTINCT day) AS days,
                      COALESCE(SUM(request_count), 0) AS interactions
                 FROM dashboard_user_activity""" + where,
            params,
        )
        return dict(rows[0])

    # -- queries -----------------------------------------------------------------------

    def groupsyncs(self, cluster_id: str) -> list[dict]:
        """Current CR state, each row carrying the full list of provider keys it owns.

        `provider_keys` is stitched in from a second read rather than GROUP_CONCAT'd: the
        callers need a list to test membership against, and building one by splitting a
        delimited string means picking a delimiter that a label value can never contain.
        Two reads of a handful of rows is the cheaper correctness.

        THOSE TWO READS TAKE THEIR OWN SNAPSHOT. WAL gives each statement a consistent
        view, not each pair of statements, so a poll committing between them stitched CR
        rows to a different generation of provider rows — a CR listing providers whose
        groups the same response says do not exist. Callers must not have to know this
        method reads twice; nesting is free because read_snapshot joins an open one.
        """
        with self.read_snapshot():
            return self._groupsyncs(cluster_id)

    def _groupsyncs(self, cluster_id: str) -> list[dict]:
        rows = self._rows(
            """SELECT g.name, g.namespace, g.schedule, g.ldap_filter, g.last_sync_at,
                      g.generation, g.observed_at,
                      e.failed_at AS error_at, e.message AS error_message,
                      e.observed_generation AS error_generation,
                      (SELECT COUNT(*) FROM group_state gs
                        WHERE gs.cluster_id = g.cluster_id
                          AND gs.sync_provider IN (
                              SELECT p.provider_key FROM groupsync_provider p
                               WHERE p.cluster_id = g.cluster_id
                                 AND p.groupsync_name = g.name
                                 AND p.groupsync_namespace = g.namespace)) AS group_count
                 FROM groupsync_state g
                 LEFT JOIN reconcile_error e
                        ON e.cluster_id = g.cluster_id AND e.groupsync_name = g.name
                WHERE g.cluster_id = ?
                ORDER BY g.name""",
            (cluster_id,),
        )
        keys: dict[tuple[str, str], list[str]] = {}
        for p in self._rows(
            """SELECT groupsync_name, groupsync_namespace, provider_key
                 FROM groupsync_provider WHERE cluster_id=?
                ORDER BY provider_key""",
            (cluster_id,),
        ):
            keys.setdefault((p["groupsync_name"], p["groupsync_namespace"]), []).append(
                p["provider_key"]
            )
        for row in rows:
            row["provider_keys"] = keys.get((row["name"], row["namespace"]), [])
        return rows

    def sync_events(self, cluster_id: str, name: str, since: str | None, limit: int) -> list[dict]:
        sql = """SELECT synced_at, observed_at, schedule, group_count
                   FROM sync_event
                  WHERE cluster_id=? AND groupsync_name=?"""
        params: list = [cluster_id, name]
        if since:
            sql += " AND synced_at >= ?"
            params.append(since)
        sql += " ORDER BY synced_at DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    @staticmethod
    def _group_state_predicate(state: str, alias: str = "") -> str:
        """The `state` filter, written once for both shapes of groups().

        Two copies of this predicate would drift the way the count-versus-list defects did,
        and the `empty` reading below has already been re-litigated once — it must not fork.
        """
        if state == "empty":
            # EVERY group with no members, whatever created it. This was scoped to
            # `sync_provider IS NOT NULL` on PLAN §7's reading of EMPTY as "synced, then lost
            # its members" — an LDAP-side fault. That reading made the filter USELESS on the
            # cluster that most needs it: with no group-sync-operator installed, every group is
            # unattributed, so `empty` matched nothing however many groups had zero members.
            #
            # `empty` and `unattributed` therefore OVERLAP now, and that is intended: they are
            # two questions, not a partition. "Which groups grant nobody?" and "which groups is
            # no CR managing?" have different answers and a group can be both. Nothing sums
            # them — checked across store, api, metrics and the UI before the change.
            return " AND " + qualified(GROUP_EMPTY, alias)
        if state == "unattributed":
            return " AND " + qualified(GROUP_UNATTRIBUTED, alias)
        if state != "all":
            raise ValueError(f"unknown group state filter {state!r}")
        return ""

    def groups(
        self, cluster_id: str, state: str = "all", user_name: str | None = None
    ) -> list[dict]:
        """Current groups, optionally narrowed to the ones this user is a member of.

        `user_name` is the privacy scope, not a convenience filter — the API passes the
        proxy-authenticated viewer's own name when view restrictions are on, the same
        contract user_activity() documents. One method rather than a scoped sibling so a
        handler has exactly one call site and the state predicate cannot fork.

        Matching is byte-exact on purpose. X-Forwarded-User and the Group objects' member
        names carry the same directory form (measured live: `lateef.o` in both), and a
        case-insensitive match would defeat the group_member index AND cross-leak between
        two OpenShift Users differing only by case — User names are case-sensitive.

        Plan for the scoped shape, measured on the live database: group_state by its PK
        autoindex, group_member by its PK covering index — no new index needed.
        """
        # #174: the one data addition the drill-down needs — how many bindings name the group, in a
        # namespace or cluster-wide — so the list can say what a group grants without a click each.
        # A correlated scalar over rbac_group_binding's (cluster_id, group_name) index, the same count
        # group_detail's bindings list has rows, which a test holds them to.
        grants = """(SELECT COUNT(*) FROM rbac_group_binding b
                      WHERE b.cluster_id = g.cluster_id AND b.group_name = g.name) AS binding_count"""
        if user_name:
            sql = (f"""SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at,
                             g.ldap_uid, g.observed_at, g.cliff_silence, {grants}
                        FROM group_state g
                        JOIN group_member m
                          ON m.cluster_id = g.cluster_id AND m.group_name = g.name
                       WHERE g.cluster_id=? AND m.user_name=?"""
                   + self._group_state_predicate(state, alias="g") + " ORDER BY g.name")
            return self._rows(sql, [cluster_id, user_name])
        sql = (f"""SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at, g.ldap_uid,
                         g.observed_at, g.cliff_silence, {grants}
                    FROM group_state g WHERE g.cluster_id=?"""
               + self._group_state_predicate(state, alias="g") + " ORDER BY g.name")
        return self._rows(sql, [cluster_id])

    def is_group_member(self, cluster_id: str, group_name: str, user_name: str) -> bool:
        """Whether this user is currently a member of this group — the self-tier gate.

        One primary-key probe (covering index, measured). The API asks this BEFORE any
        existence lookup so a non-member's 403 is constant for a real group and a
        nonexistent one alike — a per-name existence oracle would leak the group list
        the self tier exists to withhold.
        """
        rows = self._rows(
            "SELECT 1 AS yes FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
            (cluster_id, group_name, user_name),
        )
        return bool(rows)

    def group_counts(self, cluster_id: str) -> dict:
        # The same fragments as the `empty` / `unattributed` predicates in groups() above and the
        # compliance snapshot's counts (gsd/kpi/predicates.py). A count that disagrees with its own
        # list is the defect class this project keeps rediscovering, so a test pins them together.
        row = self._row(
            f"""SELECT COUNT(*) AS total,
                       SUM(CASE WHEN {GROUP_EMPTY} THEN 1 ELSE 0 END) AS empty,
                       SUM(CASE WHEN {GROUP_UNATTRIBUTED} THEN 1 ELSE 0 END) AS unattributed
                  FROM group_state WHERE cluster_id=?""",
            (cluster_id,),
        )
        return {
            "total": row["total"] or 0,
            "empty": row["empty"] or 0,
            "unattributed": row["unattributed"] or 0,
        }

    # -- the KPI module's scalars (#156) ----------------------------------------------------

    def people_counts(self, cluster_id: str) -> dict:
        """Users known to the cluster and distinct group members — PEOPLE counts, so `internal`:
        they reach the tier-gated JSON surface and never /metrics (gsd/kpi/__init__.py)."""
        users = self._row("SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=?", (cluster_id,))
        members = self._row("SELECT COUNT(DISTINCT user_name) AS n FROM group_member WHERE cluster_id=?",
                            (cluster_id,))
        return {"users": (users or {}).get("n") or 0, "members": (members or {}).get("n") or 0}

    def membership_changes_since(self, cluster_id: str, since_id: int) -> tuple[dict[str, int], int]:
        """Membership events with id > `since_id` that are CHANGES (baseline=0: a cluster's first
        observation is "first seen", not churn — #175), counted by `change`, and the newest id seen.

        The seam under gsd_membership_changes_total: a counter accumulated from the table by an id
        watermark rather than kept beside it, so the store stays the source of truth and retention —
        which deletes OLD rows, always below the watermark — cannot make the counter go backwards.
        AUTOINCREMENT ids never reuse, so a row committed after this read has a higher id.
        """
        # ONE statement for the counts and the watermark: a row committed between two statements
        # would be above the new watermark and never counted. Baseline rows are grouped apart so the
        # watermark still passes them.
        rows = self._rows(
            """SELECT CASE WHEN baseline=1 THEN 'baseline' ELSE change END AS change,
                      COUNT(*) AS n, MAX(id) AS newest
                 FROM membership_event WHERE cluster_id=? AND id>? GROUP BY 1""",
            (cluster_id, since_id),
        )
        newest = max([since_id, *(r["newest"] for r in rows)])
        return {r["change"]: r["n"] for r in rows if r["change"] != "baseline"}, newest

    def login_attempts_since(self, cluster_id: str, since_id: int) -> tuple[dict[tuple[str, str], int], int]:
        """Login attempts with id > `since_id`, counted by (outcome, provider), and the newest id — the
        same watermark seam as membership_changes_since, under gsd_login_attempts_total. A row with no
        provider counts under 'unknown' (an attempt against a name that resolves to no identity)."""
        rows = self._rows(
            """SELECT outcome, COALESCE(provider, 'unknown') AS provider, COUNT(*) AS n, MAX(id) AS newest
                 FROM login_event WHERE cluster_id=? AND id>? GROUP BY outcome, provider""",
            (cluster_id, since_id),
        )
        newest = max([since_id, *(r["newest"] for r in rows)])
        return {(r["outcome"], r["provider"]): r["n"] for r in rows}, newest

    def membership_churn(self, cluster_id: str, since_at: str) -> dict[str, int]:
        """Joiners and leavers observed since `since_at` (baseline rows excluded) — the in-app trend.
        Two scalars over the (cluster_id, observed_at) index."""
        rows = self._rows(
            """SELECT change, COUNT(*) AS n FROM membership_event
                WHERE cluster_id=? AND observed_at>=? AND baseline=0 GROUP BY change""",
            (cluster_id, since_at),
        )
        counts = {r["change"]: r["n"] for r in rows}
        return {"added": counts.get("added", 0), "removed": counts.get("removed", 0)}

    def login_outcomes(self, cluster_id: str, since_at: str) -> dict:
        """Attempts, successes and distinct providers seen since `since_at` — the in-app trend, as
        scalars: never derived from a page of rows."""
        row = self._row(
            """SELECT COUNT(*) AS attempts,
                      SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS successes,
                      COUNT(DISTINCT provider) AS providers
                 FROM login_event WHERE cluster_id=? AND at>=?""",
            (cluster_id, since_at),
        )
        row = row or {}
        return {"attempts": row.get("attempts") or 0, "successes": row.get("successes") or 0,
                "providers": row.get("providers") or 0}

    def report_volume(self, cluster_id: str, since_at: str) -> dict:
        """Report runs recorded for this cluster since `since_at`, and where the recorded timeline
        starts — the mock's "Report volume · timeline starts …" (docs/design/overview-kpi-mock.html).
        Two scalars over report_run; no names."""
        row = self._row(
            """SELECT SUM(CASE WHEN requested_at>=? THEN 1 ELSE 0 END) AS runs,
                      SUM(CASE WHEN requested_at>=? AND status='done' THEN 1 ELSE 0 END) AS done,
                      MIN(requested_at) AS since
                 FROM report_run WHERE cluster_id=?""",
            (since_at, since_at, cluster_id),
        ) or {}
        return {"runs": row.get("runs") or 0, "done": row.get("done") or 0, "since": row.get("since")}

    def kpi_daily_written(self, cluster_id: str, day: str) -> bool:
        return bool(self._row("SELECT 1 AS yes FROM kpi_daily WHERE cluster_id=? AND day=? LIMIT 1",
                              (cluster_id, day)))

    def write_kpi_daily(self, cluster_id: str, day: str, values: dict[str, float]) -> int:
        """Record the day's rollup, once: INSERT OR IGNORE, so a second leader or a retried cycle
        cannot overwrite the day's first reading. Returns rows written."""
        with self._write() as conn:
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO kpi_daily(cluster_id, day, metric, value) VALUES(?,?,?,?)",
                [(cluster_id, day, metric, float(value)) for metric, value in values.items()],
            )
            return conn.total_changes - before

    def kpi_daily_series(self, cluster_id: str, metric: str, since_day: str) -> list[dict]:
        """The rollup's points for one metric from `since_day`, oldest first."""
        return self._rows(
            "SELECT day, value FROM kpi_daily WHERE cluster_id=? AND metric=? AND day>=? ORDER BY day",
            (cluster_id, metric, since_day),
        )

    def kpi_daily_since(self, cluster_id: str) -> str | None:
        """The oldest day the rollup holds for this cluster — where a trend really starts."""
        row = self._row("SELECT MIN(day) AS since FROM kpi_daily WHERE cluster_id=?", (cluster_id,))
        return (row or {}).get("since")

    def prune_kpi_daily(self, cluster_id: str, before_day: str) -> int:
        with self._write() as conn:
            return conn.execute("DELETE FROM kpi_daily WHERE cluster_id=? AND day<?",
                                (cluster_id, before_day)).rowcount

    def oldest_last_sync(self, cluster_id: str) -> str | None:
        row = self._row(
            """SELECT MIN(last_sync_at) AS oldest FROM groupsync_state
                WHERE cluster_id=? AND last_sync_at IS NOT NULL""",
            (cluster_id,),
        )
        return row["oldest"] if row else None
