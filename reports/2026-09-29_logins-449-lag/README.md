# #449 on the lab: when a newly added entry's Logins shows a login — 2026-09-29

**Outcome: the row was delayed by the first-sight backfill; no lost row was observed in this run.** The lab served
application 1.19.0 at `ad102d9f1f` at both ends (`evidence/before-version.txt`, `evidence/after-version.txt`). A
throwaway entry, `logins-449`, was added on the same CRC API as the host entry `dashboard`. Its Secret creation was
logged at 17:31:45Z, a timestamp with one-second precision. One `oc login` as `developer` then ran from
17:31:45.991829Z to 17:31:46.169090Z (`evidence/secret-create.txt`, `evidence/login.txt`). From the login's audit event
to the log line recording it, the lag was 2.1 s on `dashboard` and 226.8 s on `logins-449`. The new entry recorded the
row at its **fourth** audit read, **179.3 s (three configured 60 s poll intervals)** after its first read, the
`first sight: backfill` one (`evidence/after-podlog.txt`, `evidence/login-audit.txt`, `evidence/reads.jsonl`). It came
no earlier because a first sight reads `audit.log` from byte 0, oldest first, under an 8 MiB per-node body-read budget
per capture pass. Just after the login, `audit.log` held 31,004,795 bytes, and the login's auditID matched lines
starting at bytes 31,002,229 and 31,002,906 (`evidence/login-auditfile.txt`, `evidence/login-audit.txt`). The code is
under "The cause" below.

The API reads of the throwaway entries in #448 also came before those entries' backfills had finished. That is
consistent with the same mechanism, but #448's records do not establish when its own login rows were captured (under
"What #448 saw").

## What was measured

- **The entry.** `logins-449` was declared by a Secret on `https://api.crc.testing:6443`, with no annotation, no
  `saTokenLookup` and no `ldapConnectionBootstrap`. Discovery resolved it as `credential=bearer tls=trusted-bundle
  visibility=remote-sar identity=same-as-host` (`evidence/after-podlog.txt`).
- **The login.** One `oc login` as `developer` went into a throwaway kubeconfig. The password went in on stdin, and TLS
  was verified against the lab kubeconfig's CA. It answered `Login successful.`, exit 0, and `whoami` `developer`
  (`evidence/login.txt`). The audit log holds exactly one annotated login event since the start: `cli allow 302` at
  `2026-09-29T17:31:46.149663Z`, auditID `7abcf1bc-1207-4e92-99fd-241ffe54aabb` (`evidence/login-audit.txt`,
  `evidence/after-audit.txt`).
- **The reads.** `scripts/read.sh` read `GET /api/clusters/<id>/logins?kind=cli&limit=50` for `logins-449` and for
  `dashboard` (the control) through the pod's loopback as `developer`. That local route starts no OAuth login.
  Successful answers had `scope: self`; the first request for the new entry answered 404 (`evidence/reads.jsonl`).
  `scripts/run.sh` watched the pod log for new audit reads, waited 5 s after one, then read the API, so with detection
  and command overhead the API reads came more than 5 s after the audit reads. It read after the entry's reads 1–4 and
  after the control's first audit read following the login, and stopped when the row appeared. Its fallback bound was
  six audit reads of the entry, with wall-clock guards besides. The selection threshold,
  `2026-09-29T17:31:45.837912Z`, was recorded before the login script was invoked
  (`evidence/login-start-instant.txt`); the command itself started at 17:31:45.991829Z (`evidence/login.txt`). The row
  looked for is a `cli` `success` row for `developer` at or after that threshold.

## The timeline

| Instant (UTC) | What happened | Evidence |
|---|---|---|
| 17:31:44–17:31:45 | The run began at 17:31:44Z after arming its exit trap; the before captures ran across these two seconds | `evidence/start-instant.txt`, `evidence/run-output.txt`, `evidence/before-version.txt`, `evidence/before-kubeconfig.txt`, `scripts/run.sh` |
| 17:31:45 | `secret/gsd-cluster-logins-449 created` from a mode-600 manifest | `evidence/secret-create.txt` |
| 17:31:45.992 – 17:31:46.169 | The one `oc login`, timed inside the login script. The audit event was stamped 17:31:46.149663Z. The offset capture lists two lines carrying its auditID, at bytes 31,002,229 and 31,002,906 of `audit.log`, which then held 31,004,795 bytes; it does not label the stage of each line | `evidence/login.txt`, `evidence/login-audit.txt`, `evidence/login-auditfile.txt` |
| 17:31:48.190–17:31:48.203 | **Control**: `dashboard` read 19,347 bytes from offset 30,985,448, then logged 1 recorded login attempt. 30,985,448 + 19,347 = 31,004,795 | `evidence/after-podlog.txt` |
| 17:31:57 | API: `dashboard` had the row (`observed_at` 17:31:48Z). `logins-449` answered 404 (`unknown cluster`) because discovery had not added it yet | `evidence/reads.jsonl` line 1 |
| 17:32:31 | Discovery cycle 28 added `logins-449`, and polling started | `evidence/after-podlog.txt` |
| 17:32:33.614 | **Read 1**: `audit.log read 8388608 byte(s) from offset 0 (first sight: backfill)`; 317 recorded | `evidence/after-podlog.txt` |
| 17:32:39 | API: `logins-449` 200, `total` 38, row **absent**. `dashboard` had the row | `evidence/reads.jsonl` line 2 |
| 17:33:33.216 | **Read 2**: 8,388,608 bytes from offset 8,387,795; 3 recorded | `evidence/after-podlog.txt` |
| 17:33:41 | API: `total` 39, row **absent** | `evidence/reads.jsonl` line 3 |
| 17:34:33.496 | **Read 3**: 8,388,608 bytes from offset 16,776,336; 160 recorded | `evidence/after-podlog.txt` |
| 17:34:43 | API: `total` 119, row **absent** | `evidence/reads.jsonl` line 4 |
| 17:35:32.906 | **Read 4**: 5,905,295 bytes from offset 25,164,790, ending at 31,070,085. That range covers the login's line at 31,002,906. 35 recorded, logged at 17:35:32.917 | `evidence/after-podlog.txt` |
| 17:35:40 | API: `total` 149, row **present**, `at` 17:31:46.149663Z, `observed_at` 17:35:32Z. `dashboard`'s `total` was also 149 | `evidence/reads.jsonl` line 5 |
| 17:35:42 | The throwaway login was logged out and the Secret deleted by label | `evidence/logout.txt`, `evidence/delete.txt` |
| 17:36:32 | Read 5: 16,072 bytes from offset 31,070,085. The entry had caught up | `evidence/after-podlog.txt` |
| 17:37:31–17:37:32 | Discovery cycle 29 logged `removed=logins-449` at 17:37:31.989Z. The poll cycle that had polled at 17:37:31.848Z went on to a sixth audit read, 16,072 bytes from offset 31,086,157, logged at 17:37:32.106Z; the poll thread stopped at 17:37:32.186Z (`history kept`) | `evidence/after-podlog.txt` |

**The lag.** From the first-sight read's log line (17:32:33.614Z) to the fourth read's recording line (17:35:32.917Z,
`recorded 35 login attempt(s)`) was 179.3 s. From the login's audit event at 17:31:46.149663Z to the recording lines
was 226.8 s on `logins-449` and 2.1 s on `dashboard`; the control's preceding read line, at 17:31:48.190Z, was 2.0 s
after the event. These are recording times taken from the pod log. The first API reads that showed the row were at
17:31:57Z for the control and 17:35:40Z for the new entry (`evidence/after-podlog.txt`, `evidence/login-audit.txt`,
`evidence/reads.jsonl`). Before first sight, discovery added the entry about 46 s after the Secret's creation, whose
timestamp has one-second precision. The lab's discovery interval is 300 s (`reports/2026-09-29_rejoin-465-walk/README.md`
item 2). That is the wait between discovery passes, not a deadline for one: the work of a pass comes on top of it
(`local-development/gsd/poller.py#Poller._run_discovery`).

## The cause, as the code shows it

The line numbers are those of `44ee52c`. `git diff ad102d9f1f 44ee52c` is empty for `auditlog.py`, `kube.py`,
`poller.py`, `store.py` and `api.py`, so they match the deployed commit (`evidence/code-diff.txt`).

- **A first sight reads oldest-first, with `audit.log` last.** `local-development/gsd/auditlog.py#capture_once`, lines
  496–506: rotated files are sorted by their stamp. `audit.log` goes first only when its cursor is past 0; when its
  cursor is 0 or missing it is appended at the end. The run's recorded reads name only `audit.log`
  (`evidence/after-podlog.txt`), and a directory listing taken after the run, at 17:40:56Z, also names only
  `audit.log` (`evidence/auditdir.txt`).
- **Each capture pass has an 8 MiB body-read budget per node.** `local-development/gsd/kube.py#AUDIT_READ_MAX_BYTES`
  (line 83, `8 * 1024 * 1024`) is the budget set at `auditlog.py` line 507. It is passed as `max_bytes` at line 538
  and spent at line 570; the loop breaks when it is spent (line 510). Fingerprint probes are reads outside that budget.
  Reads 1–3 each returned exactly 8,388,608 body bytes.
- **The live file's cursor advances only through whole lines.** `local-development/gsd/auditlog.py#complete_lines`
  and the `set_audit_cursor` call at lines 599–603 do this. Read 1 consumed 8,387,795 of its 8,388,608 bytes, which is
  why read 2 starts there. A closed rotated file has a separate end-of-file exception at lines 562–567.
- **One capture per poll cycle.** `local-development/gsd/poller.py` line 1330 calls `capture_once` after `poll_once`
  in the cluster's loop, and the loop waits the rest of `pollIntervalSeconds`, at least 1 s (60 s on the lab;
  `read_interval_seconds: 60` in `evidence/reads.jsonl`).

So a newly added entry records the newest login only when its cursor passes that login's line. The nominal count,
ceil(31,070,085 / 8,388,608) = 4 reads, agrees with the observed offsets: read 3 left the cursor at 25,164,790, and
read 4 reached 31,070,085, past the login's line at 31,002,906. Rereading partial lines did not change the number of
reads in this run. The rows were stored under the entry's own key (`store.py#Store.record_audit_login_events`, keyed
on `cluster_id` and `audit_id`), so the host entry's copy did not suppress the new entry's. Once drained, both self
views reported `total: 149` and returned 43 CLI rows (`evidence/reads.jsonl` line 5). Only those counts and the
target row's summary were saved, so equality of every row is not recorded.

For a new entry, unread rotated files inside `loginRetentionDays` add work before the live file, since rotated files
are read first. The bytes to drain divided by the 8 MiB budget give a nominal count of reads; rereads of partial
lines, partial reads, rotation, failures and other poll work can add more. Retention, the identity filter and the
API's scope also decide whether a given event is kept and shown, so passing its byte offset is not on its own a
guarantee. This run's row was kept and shown at the API read after the fourth capture. The scaling was read from the
code above and was not measured beyond this one file. The first-sight backfill and its 8 MiB-per-cycle drain are the
documented design (`docs/AUDIT_LOG_CAPTURE.md`, section 5; `docs/REVIEW_D1.md`: "drained in four cycles under the 8
MiB budget"). This measurement supports that design as the explanation for this row.

## What #448 saw

These are its own records (`reports/2026-09-27_rejoin-walk/`):

- **Run 1.** `rejoin-walk`'s first sight read 8,388,608 bytes from 0 at 23:45:03. The Logins API was read at
  23:45:06, 3 s later. The entry's third read, at 23:47:03, ended the drain at offset 24,569,183
  (`evidence/end-podlog.txt` and `evidence/walk-output.txt` there).
- **Run 2.** `rejoin-walk-2`'s first sight was at 23:58:28. The API was read at 23:59:21, 53 s later and before its
  second read at 23:59:28. The drain ended with the third read at 00:00:29, at offset 24,635,082
  (`evidence/r2-end-podlog.txt` and `evidence/r2-walk-output-resumed.txt` there).

In both runs the API read came after the entry's first read and before its second, while the backfill was incomplete:
the next read resumed at byte 8,387,795 of a file of more than 24 MB. The empty results there are consistent with the
lag measured here. The byte offsets of #448's own login lines, and any later read of those entries' rows, were not
captured, so which read held those logins is not measured and this evidence does not settle why they were absent.

## Before and after

| | Before (17:31:44Z–17:31:45Z) | During | After (17:37:34Z–17:37:36Z) |
|---|---|---|---|
| `/api/version` | 1.19.0, `ad102d9f1f`, `dirty: false` | — | the same |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` | — | identical |
| `gsd-cluster-shared-qa` | resourceVersion 2981054 | — | 2981054 |
| fleet-account Lease | 1 Lease, resourceVersion 6761163, holder `""` | — | 6761163, `""` |
| `developer` tokens, `openshift-challenging-client` | 5 | 6 after the login | 5 after the logout, and at the end |
| the fleet account's tokens | 2 | 2 | 2 |
| the fleet account's username-annotated login events in the audit log | — | 0 events, 0 authorizes since 17:31:44Z | 0 and 0 |
| the lab kubeconfig (sha256 prefix of the file) | `10e7822a3c585576` | the same after the login | the same |
| `gsd-cluster-logins-449` | absent | created 17:31:45, deleted 17:35:42 | absent; the label selects nothing |

The rows come from `evidence/{before,login,deleted,after}-{version,pvcs,sharedqa,lease,tokens,kubeconfig,secret}.txt`,
`evidence/after-audit.txt` and `evidence/trap-delete.txt`. In the pod log for the window, `fleet-login`,
`fleet-logout`, `fleet-lookup`, `fleet-ping`, `cluster-rejoin-failed`, `cluster-rejoined`, Traceback and ERROR each
count 0. Lines naming the fleet account also count 0 (`evidence/after-podlog.txt`). The scripts make no change to
`shared-qa` or to a PVC. The unchanged PVC UIDs show that the PVC objects persisted; they do not measure writes to the
volumes' data.

## The credential, and why it was chosen

The method #448 used was Rejoin as `developer` behind a disposable `cluster-admin` binding. It cannot run on 1.19.0:
on this lab `developer`'s password equals its username, and #447 refuses such a password with `422
rejoin-password-within-username` before sending anything (`reports/2026-09-29_rejoin-465-walk/README.md`, row C).
Rejoin would also have made another `developer` login. So the throwaway Secret carries a copy of
`gsd-cluster-shared-rnd`'s `bearerToken` and `tlsClientConfig`. `scripts/lab.sh` copies those two fields through a jq
pipe into a temporary manifest under `umask 077`, removes it with an EXIT trap, and records its mode
(`evidence/secret-create.txt`: `manifest mode 600`). The token was never printed and never on an external command's
argv. No annotation or bootstrap field was copied, so the fleet account's name, which `shared-rnd` records, stayed out.
`shared-rnd`'s Secret itself was only read. No Secret capture ran while the copy existed, so the two tokens were
never compared (observation 4); the copy's successful polls and its six reads of `audit.log` through `nodes/proxy`
show that it worked (`evidence/after-podlog.txt`). The run created no RBAC grant: `developer`'s self view carries
its own rows, and both entries answered `scope: self` (`evidence/reads.jsonl`; the tier rule is
`local-development/gsd/api.py#viewer_scope`).

The Secret carried the run's label and was deleted by that label. The throwaway OAuth token was revoked separately by
the logout, and the exit trap removed the temporary kubeconfig and CA directory (`evidence/delete.txt`,
`evidence/logout.txt`, `evidence/trap-delete.txt`). The scripts make only the one `developer` login; the audit capture
counts one annotated login event since the start, `developer`'s, and none by the fleet account
(`evidence/after-audit.txt`). The application keeps the entry's history after its removal.

## What came back that the brief does not say

1. **During the drain, the Logins API gave no sign that it was behind.** `last_read_at` advanced on every read
   (17:32:33Z, 17:33:33Z, 17:34:33Z) while the row was absent, and `total` grew from 38 to 39 to 119
   (`evidence/reads.jsonl` lines 2–4), then reached 149 when the row appeared (line 5). A reader of the tab in those
   three minutes sees a fresh "last read" and a history that lacks the newest attempts. A later capture of the
   answer's keys, at 17:40:56Z, lists no backfill-progress field, and its `note` promises "history back to the oldest
   rotated audit file on a first read" without saying when (`evidence/api-keys.txt`). This is a design observation,
   not a lost row. A "backfill in progress" signal would be a separate change.
2. **Discovery added the entry about 46 s after its creation, not up to 300 s.** The Secret was logged at 17:31:45Z
   and cycle 28 added the entry at 17:32:31.748Z (`evidence/secret-create.txt`, `evidence/after-podlog.txt`).
3. **The new entry's first poll announced 20 unmanaged grants as `UNMANAGED GRANT DISCOVERED`.** The 20 lines fell at
   17:32:34–17:32:35 (`evidence/after-podlog.txt`) and include operator-version binding names such as
   `metallb-operator.v4.22.0-…`. They are grants without the markers the line names (no config-source label, no
   exception annotation), not necessarily hand-made ones. The announcements are capped per cycle
   (`local-development/gsd/poller.py#refresh_bindings`; the chart's default `maxPerCycle` is 20), so the 20 lines are
   not a census of every such grant.
4. **The capture script's own gap.** No Secret capture ran while the entry existed. The `secret` captures are before,
   after the delete and at the end, all `[]`. So the copy's equality with `shared-rnd`'s token is not recorded. The
   entry's successful polls and audit reads are the evidence that the credential worked.
5. **The exit trap's `oc logout` found no token** (`error: You must have a token in order to logout.`,
   `evidence/trap-delete.txt`). The explicit logout at 17:35:42 had already revoked it. The trap's delete found
   nothing and removed the throwaway directory.

## Redaction in this folder

- No password value is written. `developer`'s password went to `oc login` on stdin from a variable and was unset
  afterwards (`scripts/lab.sh`). The captured prompt line is `Password: Login successful.`: the input is not echoed.
- No token is written. The captures select metadata and counts, or redact `sha256~` values; none stores the raw
  Secret, kubeconfig or audit log (`scripts/capture.sh`, `scripts/lab.sh`, `scripts/read.sh`). A search of this
  folder's 43 files for `sha256~` followed by six or more token characters, a JWT prefix, a private-key block or a
  literal long `Bearer` credential matched nothing. Those searches do not prove the absence of every possible secret.
- The pod-log capture counts 0 lines naming the fleet account (`evidence/after-podlog.txt`), and
  `scripts/capture.sh` replaces that name with `<fleet account>` in what it writes. The name and the search for it
  run before the commit are not archived, so that search cannot be repeated from this folder alone.
- The long operator-version strings in `evidence/after-podlog.txt` are ClusterRoleBinding and role names in the
  logged RBAC fields, not tokens. Their shape is that of OLM-generated bindings; their owner metadata was not captured.
- The lab kubeconfig is recorded only as a 16-hex-digit prefix of the file's sha256.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig>
reports/2026-09-29_logins-449-lag/scripts/run.sh    # trap, before, Secret, login, reads, logout, delete, after
```

`scripts/run.sh` stops at the row or at six audit reads of the entry. The reads use `scripts/read.sh`, the captures
use `scripts/capture.sh`, and the writes are `scripts/lab.sh` (`secret`, `login`, `logout`, `delete`).
