# Review record — PR #295, S4b: the ServiceAccount token lookup (#284)

Written **2026-09-22**, after the fact. Step 5 of the review skill asks for this file per reviewed
PR and it was not written when #295 merged; adversarial review of a later PR noticed its absence.
The rounds themselves were recorded at the time in `docs/specs/SPEC_S4b_sa_token_lookup.md` under
"Orchestrator's notes" and in PR #295's comments — this file is the index, not a new account, and
nothing here is recalled from memory: every round, finding and decision below is transcribed from
those two sources, and the commits are named so each is checkable.

Reviewers: **Codex** (`gpt-5.6-sol`, xhigh) and **Cursor** (`cursor-grok-4.6-high-fast`).
Three rounds, **7 → 5 → 2** findings, on commits `d94887a`, `9e1abb2` and `188930c`; merged as
`e4e59bf`.

## What this PR was measured to have bought

Recorded because the comparison is the argument for spec-first work, and because an earlier version
of this comparison was **wrong and had to be corrected** — see "A correction" at the end.

| | rounds | findings | code |
|---|---|---|---|
| #283 — code first, research late | 5 | 21 | `fleetlogin.py` 443 → 729 lines (**+65%**), tracked as a defect (#291) |
| #284 — research first, spec reviewed before any code | 3 | 7 → 5 → 2 | `fleetlookup.py` 346 → 410 lines (**+18.5%**), 13 → 15 `def`s |

## Round one — seven findings on `d94887a`

| # | finding | decision |
|---|---|---|
| **P0-1** | **The scheduler re-entered a login #283 had made terminal.** Only `AUTH_FAILED` gated the credential; every other answer became `login-failed` and the schedule called `lookup()` again — up to five binds. For a *locked* account (LDAP code 19 → the oauth-server's HTTP 500) that is the lockout walk one layer up. | **accepted; fix shape departs from the brief.** The brief proposed gating on `phase == "credential"`, which misses a transport failure *after* the authorize GET was written (`phase=connect`, `retryable=False`) — the password was on the wire and the target may have bound. `LoginError` now carries **`bound`**. |
| **P0-2** | **The replica rule reached only a values stanza.** The `replicaCount > 1` refusal sat inside `range $modeOf`, so a Secret-declared mode on a two-replica release with election off retrieved on **every** replica. | **accepted.** The rule now holds wherever a lookup is possible — at render, and at runtime through the ConfigMap. |
| **P1-1** | **The retrieved token could reach the tab.** `read_sa_token` raised on the type, owner and `invalid-since` paths *before* decoding `data.token`, so the token was not among the secrets the refusal was scrubbed against. | **accepted.** Token decoded first and rides every refusal's `secrets`; owner and type described by length, never echoed; `scrub` rewrites `detail`, `action` **and `args`**. |
| **P1-2** | The tab's GitOps YAML had the writer's merge-order bug — the app's label emitted first instead of last. | **accepted.** |
| **P1-3** | A quoted `"false"` enabled writes: `_bool_setting`'s ConfigMap path was `bool(raw.get(...))`. | **accepted.** |
| **P1-4** | `lookup(write=True)` trusted its caller to check the switch. | **accepted.** It checks `secrets.enabled and writes.enabled` itself, before any password is read; the rule now lives in one place. |
| **P1-5** | `invalid-since` was tested by truthiness; Kubernetes allows an empty label value. | **accepted.** The label must be *absent*. |

## Round two — five refutations on `9e1abb2`

| # | finding | decision |
|---|---|---|
| **R2-1** | **The gate was too narrow and too broad at once.** Too narrow: a post-write transport failure was made "final" in `_LookupState`, which re-arms on *any* shape change — a `visibility` edit sent the same password to the same target again. Too broad: the key omitted the target, so a 500 from target A blocked a healthy target B on the same account. | **accepted; one fix closes both.** Keyed on **(target `api_url`, username, sha256(password))**, and **every `bound` answer gates**. `final` is gone. The business owner **retracted** the earlier "keep two tiers" decision on the measurement. |
| **R2-2** | The test that blessed the regression is inverted. | **accepted.** |
| **R2-3** | Moving the decode first put a new failure in front of the error handling (`TypeError` on a non-scalar `data.token`); and a `ClusterError` message carries a remote body that can hold the very token being read. | **accepted.** Decode catches `TypeError`; quoted messages cut at the status (`_status_only`). |
| **R2-4** | `_bool_setting` still decided on odd values: `2`, `-1`, `[false]` enabled writes silently. | **accepted.** A real boolean or one of the words, nothing else; the warning names the source. |
| **R2-5** | **The replica guard is best-effort.** Two pollers with `replica_count=1` and no elector, a stale lease holder, a rollout's two pods, an HPA past a ConfigMap that says 1 — none is caught by in-memory state. | **recorded, not patched.** True mutual exclusion needs a claim the cluster arbitrates; SPEC_S4 §9 assigns the durable, replica-shared gate to **#285**, which inherits the requirement *with the measurement*. |

## Round three — two findings on `188930c`

| # | finding | decision |
|---|---|---|
| **R3-1** | **A hostname case change re-entered the walk.** The gate key stripped a trailing slash and nothing else, so `api.example.com` → `API.example.com` was a new key (measured: **+1 authorize**). | **accepted.** The key is the URL as `httpx.URL` canonicalises it — host case and IDNA, not a whole-string lowercase that would mangle a path — with `rstrip("/")` as the fallback so a malformed `apiUrl` cannot raise inside the gate. |
| **R3-2** | **A gated credential looped quietly.** After the gate fired, every cycle re-read the password Secret, took the free refusal, and the operator never saw `gave_up=true`. | **accepted on the fact; BOTH offered fixes rejected.** Setting `gave_up` would be wrong: the schedule's re-arm key cannot see the password *value*, so a rotated password would never be noticed and the cluster would stay stuck until a restart. The per-cycle read (one local `get`, no bind) **is** the rotation detector and stays. What the refusal lacked was the word; it now carries `gave_up=true` and an action naming what must change. |

## Where the implementer departed from the brief, with evidence

Twice, and both departures are in the merged code:

1. **P0-1** — `bound` instead of the brief's `phase == "credential"`, because the narrower gate would
   have left a closed hole open. The two-tier `final` shape attached to it was the *orchestrator's*
   "keep two tiers" decision, and round two's measurement refuted that half.
2. **R3-2** — a third direction where two fixes had been offered, for the rotation-detector reason above.

## What is NOT held

Stated here because an honest gap is worth more than a claim that stops at the process boundary:
**replica mutual exclusion is unsolved.** `CredentialGate` is in-memory and per process — its own
docstring says *"Best-effort and per process; the durable, replica-shared gate is #285's"* — so a
restart or a second replica binds again. A safety claim about this code must therefore be written as
a budget **with its scope** ("at most one bind per (target, credential) **per process**"), never as
"ever". #285 carries the measured cases.

## A correction

An earlier account of this PR — in the review skill, in the session changelog and in a memory note —
said the code "got **simpler** each round" and that "the last round **deleted** a mechanism". Both are
false. Measured 2026-09-22, when adversarial review of a later PR challenged them:

```
fleetlookup.py   cd00f2f 346 lines / 13 defs -> d94887a 388/14 -> 9e1abb2 395/15 -> 188930c 410/15
'final' count    d94887a 4 | 9e1abb2 1 | 188930c 1          -> deleted in round TWO, not the last
```

The module **grew** +18.5% and gained two functions; the defensible claim is that it grew a quarter as
fast as #283's `fleetlogin.py`. A fourth claim — that a reviewer's `CONFIRMED` had missed the retry
defect — was also false: `3 C1: REFUTED`, zero CONFIRMED. The reviewers caught it; the orchestrator
and the implementer are who missed it. All four are corrected at source.
