# SPEC_F7 on the lab: windows end at the snapshot's stamp, sealed instants, HTML first, 2026-10-04

**Outcome.** The lab served application 5.1.0, which Argo CD deployed from main at `930796769f` (PR #610). Argo CD
read Synced and Healthy. SPEC_F7 §5's three steps passed, and `scripts/run.sh` exited 0 (`walk.log`). The PVC UIDs
were the same before and after. The walk's grant was removed (`can-i`: no), and the log holds no `sha256~` and no
ticket.

## The three steps

### 1. #592: one snapshot, two clocks, one hash
Runs on `dashboard` by `dana.lee`, generated three minutes apart over snapshot `2026-10-04T17:45:25.793849Z`:

| Report | Runs | sha256 (both) | Generated at |
|---|---|---|---|
| compliance-snapshot | `…174615…-e176`, `…174920…-ad81` | `0c0eff614d00…` | 17:46:15Z, 17:49:20Z |
| login-activity | `…174617…-b479`, `…174922…-e347` | `f6bbb02a7e7b…` | 17:46:17Z, 17:49:22Z |

login-activity's Window "To" reads `2026-10-04T17:45:25Z` in both runs: the snapshot's stamp to the second, not the
generation time.

### 2. #607: `mock-trusted` across two snapshots
- `compliance-snapshot` ran over snapshot `17:45:25Z` (`…174928…-4c98`) and over the next copy, `17:50:25Z`
  (`…175044…-6c33`).
- Their `report-diff`, `…175046…-6022`, reads **No change**: `blocks_changed: 0`, `rows_added: 0`,
  `rows_removed: 0`.
- Page one still shows both runs' "Last poll" (`17:45:24Z — ok`, `17:50:24Z — ok`) and the capture note's "(last read
  …)".
- The two sha256 values still differ, because the snapshot's stamp stays in the sealed provenance by design; only the
  sections a diff compares lost the instants.

Before this change, the same kind of diff on the same cluster reported 2 changed blocks, both instants:
`reports/2026-10-04_epic-f-seal-check/`, and #607.

### 3. #593: the form starts with HTML
As `developer` under the labelled grant, with a fresh browser session per width:
- at 1280 and 375 px, the Reports form opens with only HTML ticked and reads "Generate HTML · JSON";
- ticking PDF makes it "PDF · HTML · JSON";
- nothing scrolls sideways, and there are no page errors.
Nothing was generated (`screenshots/01` to `04`).

## How it ran, and the two runs before it
The check ran three times; this folder holds the third run. Neither earlier failure was the product's.
- **First run:** steps 1 and 2 passed, but step 3 failed at 375 px. The walk reused the 1280 px page, so its PDF tick
  carried over, because the form keeps a reader's choice (#575). It now opens a fresh session per width.
- **Second run:** the in-pod step held one ticket across a retry and the wait for a new snapshot. The dashboard mints
  tickets for 300 s (`reportingTicketTtlSeconds`), so the report service refused it as expired, as F6 intends. The
  script now mints a fresh ticket per phase.

## Redaction
macOS Vision OCR of the 4 PNGs recognised 185 lines (`evidence/ocr-all.txt`). None contains `sha256~`, "password" or
"token". The positive control, "Generate", is found 4 times.

| Path | Contents |
|---|---|
| `walk.log` | each command and its output |
| `screenshots/` | the form at 1280 and 375 px, as opened and with PDF ticked |
| `evidence/ocr-all.txt` | the OCR text |
| `scripts/` | `run.sh`; `in_pod.py` (phases `pair`, `first`, `stamp`, `second`); `walk.py`; `grant.yaml` |

To repeat: `KUBECONFIG=<the lab kubeconfig> scripts/run.sh`. It makes the product's own report runs and a labelled
grant, which it removes.
