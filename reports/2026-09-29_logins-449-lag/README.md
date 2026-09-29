# #449 on the lab: when a newly added entry's Logins shows a login — 2026-09-29

**Outcome: a lag, not a defect.** The lab served application 1.19.0 at `ad102d9f1f` at both ends
(`evidence/before-version.txt`, `evidence/after-version.txt`). A throwaway entry, `logins-449`, was added on the same
CRC API as the host entry `dashboard`. One `oc login` as `developer` was made 1 s later
(`evidence/secret-create.txt`, `evidence/login.txt`). The login's row was on `dashboard` 2 s after the login. It
reached `logins-449` at the entry's **fourth** audit read. That read came **179.3 s (three 60 s cadences)** after the
entry's first read, the `first sight: backfill` one (`evidence/after-podlog.txt`, `evidence/reads.jsonl`). The row
came exactly at the brief's bound. It did not come earlier because a first sight drains `audit.log` from byte 0,
oldest first, at 8 MiB per node per cycle. This lab's `audit.log` held 31,004,795 bytes, and the login's line was
near its end (`evidence/login-auditfile.txt`, `evidence/login-audit.txt`). The code is under "The cause" below.

The same records explain what #448 saw. Both throwaway-entry reads there came before that entry's drain had finished
(under "What #448 saw").

## What was measured

- **The entry.** `logins-449` was declared by a Secret on `https://api.crc.testing:6443`, with no annotation, no
  `saTokenLookup` and no `ldapConnectionBootstrap`. Discovery resolved it as `credential=bearer tls=trusted-bundle
  visibility=remote-sar identity=same-as-host` (`evidence/after-podlog.txt`).
- **The login.** One `oc login` as `developer` went into a throwaway kubeconfig. The password went in on stdin, and TLS
  was verified against the lab kubeconfig's CA. It answered `Login successful.`, exit 0, and `whoami` `developer`
  (`evidence/login.txt`). The audit log holds exactly one annotated login event since the start: `cli allow 302` at
  `2026-09-29T17:31:46.149663Z`, auditID `7abcf1bc-1207-4e92-99fd-241ffe54aabb` (`evidence/login-audit.txt`,
  `evidence/after-audit.txt`).
- **The reads.** `scripts/read.sh` read `GET /api/clusters/<id>/logins?kind=cli` for `logins-449` and for `dashboard`
  (the control) through the pod's loopback as `developer`. That route makes no login and no audit event. Both answered
  the self view (`scope: self`, `evidence/reads.jsonl`). `scripts/run.sh` ran one read 5 s after every audit read of
  the new entry. It also ran one after the control's first audit read following the login. It would have stopped at
  six reads of the entry. The row is a `cli` `success` row for `developer` at or after the login's start,
  `2026-09-29T17:31:45.837912Z` (`evidence/login-start-instant.txt`).

## The timeline

| Instant (UTC) | What happened | Evidence |
|---|---|---|
| 17:31:44 | The run began; the exit trap was armed and the before captures ran | `evidence/start-instant.txt`, `evidence/run-output.txt` |
| 17:31:45 | `secret/gsd-cluster-logins-449 created` from a mode-600 manifest | `evidence/secret-create.txt` |
| 17:31:45.838 – 17:31:46.169 | The one `oc login`. The audit event was stamped 17:31:46.149663. Its two lines (request received, response complete) start at bytes 31,002,229 and 31,002,906 of `audit.log`, which then held 31,004,795 bytes | `evidence/login.txt`, `evidence/login-audit.txt`, `evidence/login-auditfile.txt` |
| 17:31:48.190 | **Control**: `dashboard` read 19,347 bytes from offset 30,985,448 and recorded 1 login attempt. 30,985,448 + 19,347 = 31,004,795 | `evidence/after-podlog.txt` |
| 17:31:57 | API: `dashboard` had the row (`observed_at` 17:31:48Z). `logins-449` answered 404 (`unknown cluster`) because discovery had not added it yet | `evidence/reads.jsonl` line 1 |
| 17:32:31 | Discovery cycle 28 added `logins-449`, and polling started | `evidence/after-podlog.txt` |
| 17:32:33.614 | **Read 1**: `audit.log read 8388608 byte(s) from offset 0 (first sight: backfill)`; 317 recorded | `evidence/after-podlog.txt` |
| 17:32:39 | API: `logins-449` 200, `total` 38, row **absent**. `dashboard` had the row | `evidence/reads.jsonl` line 2 |
| 17:33:33.216 | **Read 2**: 8,388,608 bytes from offset 8,387,795; 3 recorded | `evidence/after-podlog.txt` |
| 17:33:41 | API: `total` 39, row **absent** | `evidence/reads.jsonl` line 3 |
| 17:34:33.496 | **Read 3**: 8,388,608 bytes from offset 16,776,336; 160 recorded | `evidence/after-podlog.txt` |
| 17:34:43 | API: `total` 119, row **absent** | `evidence/reads.jsonl` line 4 |
| 17:35:32.906 | **Read 4**: 5,905,295 bytes from offset 25,164,790, ending at 31,070,085. That range covers the login's line at 31,002,906. 35 recorded | `evidence/after-podlog.txt` |
| 17:35:40 | API: `total` 149, row **present**, `at` 17:31:46.149663Z, `observed_at` 17:35:32Z. `dashboard`'s `total` was also 149 | `evidence/reads.jsonl` line 5 |
| 17:35:42 | The throwaway login was logged out and the Secret deleted by label | `evidence/logout.txt`, `evidence/delete.txt` |
| 17:36:32 | Read 5: 16,072 bytes from offset 31,070,085. The entry had caught up | `evidence/after-podlog.txt` |
| 17:37:31 | Discovery cycle 29 `removed=logins-449`, and the poll thread stopped (`history kept`) | `evidence/after-podlog.txt` |

**The lag.** From first sight (17:32:33.614) to the row being recorded (17:35:32.917, `recorded 35 login attempt(s)`)
was 179.3 s. From the login to the row was 226.8 s on `logins-449`, against 2.0 s on `dashboard`
(`evidence/after-podlog.txt`, `evidence/login-audit.txt`). Before first sight, discovery took 46 s from the Secret on
this run. It can take up to `discoveryIntervalSeconds` (300 s on the lab, `reports/2026-09-29_rejoin-465-walk/README.md`
item 2) (`evidence/after-podlog.txt`).

## The cause, as the code shows it

The line numbers are those of `44ee52c`. `git diff ad102d9f1f 44ee52c` is empty for `auditlog.py`, `kube.py`,
`poller.py`, `store.py` and `api.py`, so they match the deployed commit (`evidence/code-diff.txt`).

- **A first sight reads oldest-first, with `audit.log` last.** `local-development/gsd/auditlog.py#capture_once`, lines
  496–506: rotated files are sorted by their stamp. `audit.log` goes first only when its cursor is past 0; on a first
  sight it is appended at the end. The lab has no rotated file: the directory listing names only `audit.log` (`evidence/auditdir.txt`). So
  the first sight read `audit.log` from byte 0 (`evidence/after-podlog.txt`, read 1).
- **Each cycle reads at most 8 MiB per node.** `local-development/gsd/kube.py#AUDIT_READ_MAX_BYTES` (line 83,
  `8 * 1024 * 1024`) is the budget set at `auditlog.py` line 507. It is passed as `max_bytes` at line 538 and spent at
  line 570; the loop breaks when it is spent (line 510). Reads 1–3 each returned exactly 8,388,608 bytes.
- **The cursor advances only through whole lines.** `local-development/gsd/auditlog.py#complete_lines` and the
  `set_audit_cursor` call at lines 599–603 do this. Read 1 consumed 8,387,795 of its 8,388,608 bytes, which is why
  read 2 starts there.
- **One read per poll cycle.** `local-development/gsd/poller.py` line 1330 calls `capture_once` after `poll_once` in
  the cluster's loop, and the loop waits `pollIntervalSeconds` (60 on the lab; `read_interval_seconds: 60` in
  `evidence/reads.jsonl`).

So a newly added entry records the newest login only when its cursor passes that login's line. On this lab that took
ceil(31,070,085 / 8,388,608) = 4 reads, which is three cadences after first sight. The rows were stored under the
entry's own key (`store.py#Store.record_audit_login_events`, keyed on `cluster_id` and `audit_id`). So the row was not
lost to the host entry's copy: once drained, the entry's self view held the same 149 rows as the control's
(`evidence/reads.jsonl` line 5).

The drain time scales with the bytes to drain: `audit.log` plus any rotated file inside `loginRetentionDays`, since
rotated files are read first. A larger file or rotated backups lengthen it by one cadence per 8 MiB. That scaling is
read from the code above and was not measured beyond this one file. The first-sight backfill and its 8 MiB-per-cycle
drain are the documented design (`docs/AUDIT_LOG_CAPTURE.md`, section 5; `docs/REVIEW_D1.md`: "drained in four cycles
under the 8 MiB budget").

## What #448 saw

These are its own records (`reports/2026-09-27_rejoin-walk/`):

- **Run 1.** `rejoin-walk`'s first sight read 8,388,608 bytes from 0 at 23:45:03. The Logins API was read at
  23:45:06, 3 s later. The entry's third read, at 23:47:03, ended the drain at offset 24,569,183
  (`evidence/end-podlog.txt` and `evidence/walk-output.txt` there).
- **Run 2.** `rejoin-walk-2`'s first sight was at 23:58:28. The API was read at 23:59:21, 53 s later and before its
  second read at 23:59:28. The drain ended with the third read at 00:00:29, at offset 24,635,082
  (`evidence/r2-end-podlog.txt` and `evidence/r2-walk-output-resumed.txt` there).

In both runs the only read of the throwaway entry came while its cursor was at 0 or 8,387,795 bytes of a file of
more than 24 MB. The 0 rows there are this lag. The byte offset of #448's own login lines was not captured, so which
of those reads held them is not measured.

## Before and after

| | Before (17:31:44Z) | During | After (17:37:34Z–17:37:36Z) |
|---|---|---|---|
| `/api/version` | 1.19.0, `ad102d9f1f`, `dirty: false` | — | the same |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` | — | identical |
| `gsd-cluster-shared-qa` | resourceVersion 2981054 | — | 2981054 |
| fleet-account Lease | 1 Lease, resourceVersion 6761163, holder `""` | — | 6761163, `""` |
| `developer` tokens, `openshift-challenging-client` | 5 | 6 after the login | 5 after the logout, and at the end |
| the fleet account's tokens | 2 | 2 | 2 |
| the fleet account in the audit log | — | 0 events, 0 authorizes since 17:31:44Z | 0 and 0 |
| the lab kubeconfig (sha256 prefix of the file) | `10e7822a3c585576` | the same after the login | the same |
| `gsd-cluster-logins-449` | absent | created 17:31:45, deleted 17:35:42 | absent; the label selects nothing |

The rows come from `evidence/{before,login,deleted,after}-{version,pvcs,sharedqa,lease,tokens,kubeconfig,secret}.txt`,
`evidence/after-audit.txt` and `evidence/trap-delete.txt`. In the pod log for the window, `fleet-login`,
`fleet-logout`, `fleet-lookup`, `fleet-ping`, `cluster-rejoin*`, Traceback and ERROR each count 0. Lines naming the
fleet account also count 0 (`evidence/after-podlog.txt`).

## The credential, and why it was chosen

The method #448 used was Rejoin as `developer` behind a disposable `cluster-admin` binding. It cannot run on 1.19.0: CRC's
`developer` password equals its username, and #447 refuses such a password with `422
rejoin-password-within-username` before sending anything
(`reports/2026-09-29_rejoin-465-walk/README.md`, row C). Rejoin would also have made a second `developer` login. So
the throwaway Secret carries a copy of `gsd-cluster-shared-rnd`'s `bearerToken` and `tlsClientConfig`. `scripts/lab.sh`
copies them through a jq pipe into a mode-600 temporary manifest that it removes afterwards
(`evidence/secret-create.txt`: `manifest mode 600`). The token was never printed and never on an argv. No annotation
was copied, so the fleet account's name, which `shared-rnd` records, stayed out. `shared-rnd`'s Secret itself was
only read. The copy worked: the entry listed nodes and read `audit.log` through `nodes/proxy` six times
(`evidence/after-podlog.txt`). No admin-tier grant was needed. `developer`'s self view carries its own rows, and both entries answered
`scope: self` (`evidence/reads.jsonl`; the tier rule is `local-development/gsd/api.py#viewer_scope`).

## What came back that the brief does not say

1. **During the drain, the Logins API gave no sign that it was behind.** `last_read_at` advanced on every read (17:32:33Z,
   17:33:33Z, 17:34:33Z) while the row was absent, and `total` grew from 38 to 39 to 119 before reaching 149
   (`evidence/reads.jsonl` lines 2–4). A reader of the tab in those three minutes sees a fresh "last read" and a
   history that lacks the newest attempts. No field in the answer says the backfill is still draining. Its keys and its `note` are in
   `evidence/api-keys.txt`, and the `note` promises "history back to the oldest rotated audit file on a first read"
   without saying when. This is a design observation, not a lost row. A "backfill in progress"
   signal would be a separate change.
2. **Discovery took 46 s, not up to 300 s.** Cycle 28 fell 46 s after the Secret (`evidence/after-podlog.txt`).
3. **A new entry's first poll logs every hand-made grant as `UNMANAGED GRANT DISCOVERED`.** There were 20 such lines at
   17:32:34–17:32:35 for `logins-449` (`evidence/after-podlog.txt`).
4. **The capture script's own gap.** No Secret capture ran while the entry existed. The `secret` captures are before,
   after the delete and at the end, all `[]`. So the copy's equality with `shared-rnd`'s token is not recorded. The
   entry's successful polls and audit reads are the evidence that the credential worked.
5. **The exit trap's `oc logout` found no token** (`error: You must have a token in order to logout.`,
   `evidence/trap-delete.txt`). The explicit logout at 17:35:42 had already revoked it. The trap's delete found
   nothing and removed the throwaway directory.

## Redaction in this folder

- No password is written. `developer`'s password went to `oc login` on stdin from a variable and was unset afterwards
  (`scripts/lab.sh`). `login.txt` shows the prompt `Password:` with nothing after it.
- No token is written. `sha256~` values are redacted by every capture. A search of this folder for `sha256~` followed
  by six or more token characters, or for a JWT prefix, matched nothing, and neither did one for the fleet account's
  name, run before the commit.
- The lab kubeconfig is recorded only as a 16-hex-digit prefix of the file's sha256.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig>
reports/2026-09-29_logins-449-lag/scripts/run.sh    # trap, before, Secret, login, reads, logout, delete, after
```

`scripts/run.sh` stops at the row or at six audit reads of the entry. The reads use `scripts/read.sh`, the captures
use `scripts/capture.sh`, and the writes are `scripts/lab.sh` (`secret`, `login`, `logout`, `delete`).
