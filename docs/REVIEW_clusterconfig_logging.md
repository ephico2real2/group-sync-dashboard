# Review record — the cluster-connection module's logging (#245, PR #247)

Branch `feat/245-clusterconfig-logging`, base `main`. **First pass** on head `250cc54` (base `62c385a`),
three seats: Codex GPT-5.6 xhigh (a `git archive` export with the venv; probes against the redactor, the
classifier and the Helm render, every mutant executed), Cursor Grok 4.6 (ask mode, from source — it
marks what it could not execute), and OB3 (Opus 5 at max: a harness for C1/C2/C7, the real
`uvicorn --factory` process for C4, four mermaid-cli renders, and a patch with 22 pins). The fixes
landed in the commit that names this record; the **second pass** on the pushed head is recorded below.

**The author ran the mutation exercise first**, before the seats reported, and three of his own pins
did not bite — recorded beside what the seats found, because a test that asserts nothing is the same
defect whoever notices it.

## First pass — claims × decision

| # | Claim | Codex | Grok | OB3 | Decision |
|---|---|---|---|---|---|
| C1 | No secret reaches the log from any phase | **REFUTED** — three holes: a 7-character token (`Bearer abc1234`) below `_MIN_SECRET`; a password in a values-declared `apiUrl`'s userinfo, which httpx puts in its error text; a token `resolve_token()` could no longer read, so nothing was left to redact against | CONFIRMED — `event()` is the only `log.log()` added, and everything passes through it | PLAUSIBLE — the headline holds for a realistic credential; **REFUTED** the PR body's claim that `TestNoCredentialReachesTheLog` "fails if any call site bypasses the helper" (it drives none of the eight sites; four of them pass no `secrets=`); **CONFIRMED** a new echo path: `GSD_LOG_LEVELS=$TOKEN=CHATTY` repeated the token verbatim | **Accepted all.** The floor drops to 4 with the trade-off stated; `_credentials` gains the URL's userinfo password and a last-resolved-token cache read only by the redactor; the `discovery-failed` site passes the host's credentials (its message is a LIST's, which a proxy can echo into); OB3's boundary pin — a credential planted in every field the parser reads reaches neither a `Finding` nor the log — is folded in; the miswired `GSD_LOG_LEVELS` echo is closed (C4). |
| C2 | A cycle that changes nothing logs nothing | **REFUTED** — `api_url` changes were invisible; an omitted `visibility` spelled out explicitly read as a change | **REFUTED, and worse** — the INFO gate said `or findings`, *this cycle's list* rather than a diff, and `reader.discover` logged a WARNING per refused Secret on every LIST: one standing bad Secret logged every binding interval **forever** | **REFUTED, both halves, measured** — a fleet with one oauth Secret and one broken one wrote 3 lines every cycle (864 a day at the default interval), and the shape was blind to a repointed server, a rotated token and a replaced CA; `_discovered_shape` is single-threaded and a failed LIST leaves it intact (cleared) | **Accepted.** The reader no longer logs at all: it returns findings, and the poller, which holds the previous cycle, announces the ones that **appeared** and the ones that **cleared**. The compared shape gains `api_url` and a **digest** of the credential and CA (never the values), and normalises `visibility`/`identity` to the words the log prints. OB3's mechanism (an `announced=` parameter on the reader) was rejected for Grok's (the reader emits nothing): the reader runs every cycle and should own no memory of the last one. |
| C3 | The failure names the right fix | **REFUTED** — a proxy's `HTTP 502` body containing `CERTIFICATE_VERIFY_FAILED` was reported as this cluster's certificate problem; a real failure phrased `certificate verify failed: unable to get local issuer` was missed; `store=` reported the fleet bundle even for a `caData` cluster | **REFUTED** — "substring is not the verifier; `store=` is the env string, not the store used" | **REFUTED on two of three** — `store=` wrong for three of four TLS modes (measured with a two-path `GSD_TRUSTED_CA_FILE`); the remote-body false positive reproduced; the false-negative direction is sound on this stack (CPython 3.14.7 spells the marker in `_ssl.c`, so it does not move with OpenSSL — it retracts its own hypothesis that it would); insecure → not `tls`, confirmed | **Accepted.** OB3's mechanism taken over the first fix's: the question asked first is **who wrote the message** — `ClusterClient._get` spells a transport failure `<ExceptionType>: <text>`, and anything else is a remote's answer, never matched. What remains is matched case-insensitively against the phrases OpenSSL and CPython produce. `store=` names what that cluster read: its own Secret's field, its own file, or the bundle. |
| C4 | The variables | CONFIRMED — child levels override the root in both directions | CONFIRMED on the mechanism; **PLAUSIBLE risk**: `GSD_LOG_LEVELS` echoed the logger *name* on a bad level | **CONFIRMED in the real process** — `python -m uvicorn gsd.api:create_app --factory`: unset → 0 access lines, `INFO` → 4, junk → 0 plus a complaint that does not echo, `GSD_LOG_LEVELS=uvicorn.access=INFO` → 4; the mechanism is that uvicorn's `dictConfig` runs in `Config.__init__`, before the factory. Fuzzed both helpers: 0 exceptions. **One footgun**: `root=CRITICAL` silences the whole app with 0 complaints | **Accepted the risk and the footgun.** Neither half of a bad pair is echoed (OB3's "echo only a dotted identifier" rejected: a value that *looks* like a logger name is still a value, and the length plus the accepted set repair the setting); the root logger is refused with a complaint that points at `GSD_LOG_LEVEL`; the root-override property is stated in the docstring, the values file and the README. |
| C5 | The chart | CONFIRMED — rendered unset, set, and junk (`rc=1`) | CONFIRMED on the templates; says plainly it **did not run** `helm template` | CONFIRMED, five ways, `helm v4.3.0`; **note**: `--set clusterConfigLogLevels="a=DEBUG,b=INFO"` keeps only the first pair — Helm's `--set` eats the comma, and the README's example is that exact string; **nit**: the new define sat between `gsd.logLevel`'s comment block and `gsd.logLevel` | Holds. The README and the values file say to use a values file (or escape the comma); the define moved below `gsd.logLevel`'s end. |
| C6 | The diagrams | **REFUTED** — flow 4 said manage "writes … rotates, deletes", but no such route exists on this branch; they are #237's | PLAUSIBLE on the render; **REFUTED** on the facts — flow 3's oauth line described #119 P2's `credentialRef` rather than what a Secret carries today; the "three TLS modes" omit the values-only `caBundleFile`/`serviceAccount` the poller will log | Renders CONFIRMED (four SVGs, 18–35 KB); **REFUTED** on facts: the worked example's field order put `action=` third where the code puts it after `store=`; flow 2 covers 3 of the 5 `tls=` values; flow 2 omits the empty-`caData` refusal the parser has; `connect` advertised with no producer | **Accepted all.** Flow 4 says the gate exists on main and the routes it guards do not yet; flow 3 separates TODAY from DESIGNED; flow 2 is redrawn as the decision tree the parser runs (key present → empty → both set → loads), with the two values-only modes named beneath it; flow 1 gains the `connect` decision; the worked example carries the code's field order. All four re-rendered with `@mermaid-js/mermaid-cli@11`. |
| C7 | The tests as mutant pins | **REFUTED** — (a), (d) and (g) survived | REFUTED — predicted two survivors from the assertions, without executing | **REFUTED** — the same three, each on its own fresh copy; explains each survivor (a 6-character substring below the floor; a token 211 characters clear of the cut; `gsd-cluster-c` satisfied by `source=`) | **Already fixed in `28c9e89`**, found by the author running the same exercise first; Codex and OB3 confirm the replacements fail their mutants. The four pins added by this pass were each mutated the same way before they were kept (below). |
| C8 | Not asked | **PLAUSIBLE** — a remote's error body with a newline produced **two physical log lines**, the second reading like a real event | the same flood as C2; the stale chart README paragraph; `phase=connect` named and never emitted | **N1** the same newline defect, measured as one event becoming **six** lines from an HTML 502 page; **N2** `cycle=` resets to 1 on every restart; **N3** the first cycle at forty clusters is a 41-line burst; **N4** the `trusted-bundle` action names a Helm value, not an object, and `cluster-unreachable` carries no `namespace=` | **Accepted N1** (control characters are escaped, so a remote cannot forge a line or break a key=value parser) and the README rewrite; `connect` is now **emitted** — a socket that never came up is a different diagnosis from a cluster that answered and said no. **N2 declined**: a pod's log begins at its start and `kubectl logs` is per pod, so `cycle=` is scoped to the log it appears in by construction; seeding it from the clock would make the field mean something else. **N3 noted, wanted.** **N4 deferred** to #237's page work, where the rendered ConfigMap's name is known. |

## What the second pass changed

Rebuilding the fixes found one defect the seats could not have seen, because it was introduced by the
fix for C2: the poller announced **every** finding as `secret-refused phase=parse`. An oauth Secret
parses cleanly and stops one phase later, and a shadowed values entry loads — so `phase=credential`
lost its only producer (the defect Grok and OB3 found for `connect`, one row down) and a cluster that
loads was called refused. `reader.finding_event` now owns the event name and phase per code, beside
the fix text, and the two tests assert the name and the phase rather than the outcome alone.

Each pin added by this pass was mutated before it was kept — the event table flattened, the
`discovery-failed` redaction dropped, the transport check reverted to the status-line heuristic, the
root refusal removed — and exactly the intended test failed each time.

## The author's own mutation run (before the seats reported)

Three of seven pins did not bite, each a test that looked right and asserted nothing:

- **"longest secret first"** used a 6-character substring, which `_MIN_SECRET` skips outright — so
  reversing the sort left the suite green.
- **"truncated only after redaction"** put the token at offset 40 of a 300-character window, well
  inside it, so truncating first removed nothing. It now straddles the cut and also asserts no
  **prefix** survives: a truncated `sha256~t0k3n…` is a credential fragment however short.
- **"a cluster with its own CA is told to fix its own Secret"** asserted `"gsd-cluster-c" in line`,
  which the `source=` **field** satisfies on its own — so deleting the branch entirely passed. It
  parses the `action=` value out and asserts on that.

Fixed in `28c9e89`; each verified by mutating on a throwaway copy — before, zero failures; after,
exactly the intended test.

## What this review changed about the design

Two of the findings were not bugs in the implementation but in its **claims**, which is worse:

1. The PR said "a cycle that changes nothing logs nothing" while a standing refusal logged every
   cycle. The property was the point of the change, and it was false.
2. The diagrams described routes that do not exist and a credential model that is one issue ahead of
   the code. A picture that is ahead of the code teaches the wrong thing confidently.

And one was a claim about the tests: "fails if any call site bypasses the helper" described a test
that drove no call site. The boundary the reader's lines actually rest on — a `Finding` names the key,
never the value — is now pinned instead of asserted in a docstring.

## Second pass

Recorded below when the three seats report on the pushed head.
