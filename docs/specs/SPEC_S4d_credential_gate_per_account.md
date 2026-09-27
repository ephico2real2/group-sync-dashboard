# SPEC S4d — the credential gate is per account: one answered failed login per (account, password) per process, across every target (#315)

| | |
|---|---|
| Programme | Epic C (#383), keep the shared fleet login account safe. The in-memory half of SPEC_S4c's B2, landed before #285, which seeds it from the account Lease |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4's fourth step, landing ahead of S4c) |
| Version on release | chart 0.58.6 (docs only: `CLUSTER_CREDENTIALS.md`); the application code has no version of its own and rides the next application release, as #291 does |
| Issue | [#315](https://github.com/ephico2real2/group-sync-dashboard/issues/315) |
| Status | specified |
| Source | OB1-lite's specification of 2026-09-26, written before any code from issue #315 in full (its "Where this stands", "The change", "Must not change" and Definition of Done), the operator's ruling in `docs/specs/SPEC_S4c_credential_lifecycle.md` (orchestrator's notes, and §5 question 7), #293's budget in `docs/specs/SPEC_S5_configmap_onboarding.md` §3.3, and main `cbe828b`, measured on this machine. §6's blocks were cut from a copy of `cbe828b` with the design implemented, and applied back to a clean clone for the proof in §4. No cluster was touched. Revised the same day on the review of `555a7e2` by Grok and Codex Astra, on the orchestrator's decisions (Orchestrator's notes), on a branch that merged main `3d1c237`; §6's blocks were cut again from a copy of that merge with the revised design implemented |

## How to read this spec

§1 is the mandate. §2 is what was read and measured, each with its source. §3 is the design, one decision per
subsection with its reason. §4 maps every Definition-of-Done test to its result before and after the change,
measured. §5 is the lab procedure for the implementing pull request. §6 is the whole change as implementation
blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order, applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4d_credential_gate_per_account.md . --apply

Line citations into the code at `cbe828b` are plain text, file:line, to keep them apart from the maintained
`path#anchor` citations. This spec's own row in the index, and its header's Status, move through the lifecycle
by hand: the implementing commit moves both to `merged` beside the applied blocks (a block cannot, because its
Old text would also match inside its own fence), so that `local-development/prepare-release.py` can promote them.

**The id.** S4's steps carry the design's id and a letter in the order they are specified (S4a #283, S4b #284,
S4c #285; `local-development/tests/test_specs_index.py` admits one letter). This change is the in-memory half of
S4c's B2 and its key is S4c's (SPEC_S4c §3.3: "`CredentialGate` stays as the cache"), so it belongs to that
family; S4c's own letter is taken by the Lease design, and a suffix after it (`S4c1`) is not an id the index
admits. S4d is the next free step letter. It is specified after S4c and lands before it, which the index's
issue-number order already shows (#315 sits between #301 and #321).

## Orchestrator's notes

Decisions on the review of `555a7e2` (Grok, Codex Astra; 2026-09-26), recorded first and then applied:

- **F1 (Codex, P1): accepted, with a smaller fix.** The gated detail copied URL credentials: a values stanza's
  `apiUrl` of `https://user:secret@host` is accepted by the values parser (the Secret contract's no-userinfo rule
  does not cover values), httpx's canonical form keeps the userinfo, and the detail would have written it to the
  `fleet-lookup-failed` line and served it in the finding. The displayed target goes through the existing seam
  `gsd/fleetlogin.py#_without_userinfo` instead of Codex's new origin-rebuilding code; the gate's keys and stored
  evidence are unchanged. Verified before use (§3.2): it drops userinfo, query and fragment, keeps the path, and
  returns None — never raises — for an invalid URL, a port that is not a number, a missing host and any non-https
  scheme; None is shown as a fixed phrase. Codex's regression is §6's `test_credential_gate_diagnostics.py`,
  adapted to one URL, the reachable case (§4).
- **F2 (both reviewers): accepted.** Three maintained documents still stated the superseded per-target failure
  rule, and all three are corrected here: SPEC_S5 §3.3's "Different targets still have different #284 gate keys"
  (replaced in place, recorded in S5's notes), `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`'s paragraph
  that left cross-target lockout to #285 (a chart PATCH, 0.58.5 → 0.58.6, with its history line; 0.59.0 stays
  S4c's reservation), and `docs/diagrams/remote-cluster-access/source.html`'s join-figure aria-label and join-table
  row (text only). Codex's document-contract test is §6's `test_credential_gate_docs.py`. §3.5 no longer says the
  chart file is not edited.
- **F3 (Codex): accepted.** The guarantee now states its scope beside it, in the docstring and §3.3: "account" is
  the exact configured username string (one spelling per identity) and "process" is the production Poller's one
  shared gate. The username-case residual stays documented, not solved, and Codex's `test_username_case_residual`
  pins it (two spellings, two authorizes).
- **Main moved** from `cbe828b` to `3d1c237` (#412, reports and a runbook only); it was merged first and every block
  re-cut against it. `## Unreleased` holds #291's entry only; this change's entry goes first under it.

## 1. The mandate

Issue #315, "The change": `CredentialGate` holds two kinds of entry — **refused**, keyed on
`(username, sha256(password)[:16])`, written for every `LoginError.bound` answer and recording the target that
answered as evidence; and **spent**, keyed on `(canonical target, username, digest)`, written only by #293's
success mark, exactly as today. `refused()` answers True for either kind; the gated refusal's `detail` names the
target that answered; the finding code stays `login-refused` and `gated=True` is unchanged. Failures before the
password was sent gate nothing. The docstring and the R2-1 comment are rewritten to the ruling, with the budget
stated with its scope: **at most one answered failed authorize per (account, password) per process, across every
target**; a restart or a second replica is not covered until #285's Lease. Residual, stated and not solved: two
directories that share a username and password over-block each other.

"Must not change": #293's budget table (SPEC_S5 §3.3), every row; the finding codes (`fleetlookup.CODES`) and the
`fleet-lookup` and `fleet-lookup-failed` events with their fields (poller.py:1605, :1625, :1638); password
rotation re-arms the gate by itself; `gsd/fleetlogin.py` untouched (#291's file); no chart template, value or
RBAC change (the chart moves by a docs-only PATCH for `CLUSTER_CREDENTIALS.md`, orchestrator's notes, F2).

## 2. Read and measured

**The ruling.** SPEC_S4c, orchestrator's notes (review of #325, 2026-09-23): "**The operator chose Codex's rule,
reversing R2-1**: a lockout of the account everyone logs in with is the worse outage; the price is that one sick
target's 500 stops binds on every target of the account until the password rotates or the entry is cleared
(§5, question 7)." The reason a 500 cannot stay per target is upstream's, quoted in SPEC_S4a §3.1: the
oauth-server's LDAP authenticator answers 401 only for LDAP result codes 48 and 49, and every other directory
result with 500 (`pkg/osinserver/defaults.go`, `HandleError`) — code 19, the answer of an already-locked
account, included. The ruling needs no issuer in the key: without the target, two URLs for one cluster and two
spellings of one host fold with every other target of the account.

**The code on `cbe828b`.** One gate per `Poller`, in memory (poller.py:968-970). `CredentialGate` (fleetlookup.py:97-125)
keys on `_key` (:108-119) = `(canonical api_url, username, digest)`. `lookup()` consults it at :360, marks it
on a successful ConfigMap session at :370-373 (#293), and on every `LoginError.bound` at :377-385.

**Measured, on a scratch clone of `cbe828b`** (the five fleet test files: `test_fleet_login.py`,
`test_fleet_lookup.py`, `test_configmap_onboarding.py`, `test_lookup_owned_secret.py`,
`test_lookup_record_guards.py`):

- Unchanged: `231 passed`.
- `_key` changed to leave the target out (the naive per-account key): `2 failed, 229 passed`. The two are the
  tests that pin the per-target rule, `test_one_target_spelled_three_ways_is_one_gate_entry`
  (test_fleet_lookup.py:272, its line 280 "a different port is a different target") and
  `test_the_gate_is_per_target_so_a_sick_cluster_does_not_stop_a_healthy_one` (:284).
- The same naive key against §4's #293 probe (two successful ConfigMap onboardings, one account, one gate):
  `LookupRefused: login-refused: east evaluated this password for svc-gsd-fleet already and it has not changed`
  — `1 failed`. No existing test catches it, so the success mark must stay per target and `_key` alone cannot
  carry the ruling. With the design below implemented and only the success mark switched to the account entry,
  the probe is again the only failure: `1 failed, 114 passed` over the new file and `test_configmap_onboarding.py`.

## 3. Design

### 3.1 Two kinds of entry, one gate

`CredentialGate` keeps `_refused: dict[(username, digest)] -> target` and `_spent: set[(target, username,
digest)]`. `refuse()` — called at the one bound-failure site, unchanged — writes the account's entry with
`setdefault`, so the first target that answered stays the evidence. A new `spend()` is the success mark; the
#293 site calls it instead of `refuse()`. A new `answered()` returns the target whose answer gates this call (the
account's refused entry from any target, else this target's own spent entry), or None; `refused()` is
`answered() is not None`, so every existing caller and assertion reads the same. `_key` splits into `_target`
(R3-1's canonicalisation and its never-raise fallback, verbatim) and `_digest` (the 64-bit prefix, verbatim).

Why a second method rather than a changed `refused()` return: `refused()` is a boolean in every caller and test,
and a returned target string would be falsy for an empty `api_url`, which would send a gated password.

### 3.2 The gated refusal names the target that answered

The detail becomes `"<target> evaluated this password for <account> already and it has not changed; <cluster>
does not send it"`: with the entry per account, the answer that stops this cluster may be another cluster's, and
the finding has to say where to look. It is named whichever kind gated, so there is one sentence and no branch.
The action's "until the fleet password Secret or the stanza changes" becomes "or the account the stanza names
changes": an `apiUrl` edit no longer re-arms a refused entry, only the password or the account does. The bound
failure's action "it is not sent there again" becomes "not sent again, to this or any other cluster". Code,
`spent`, `gated`, and the event names and fields are unchanged.

The target is displayed through `gsd/fleetlogin.py#_without_userinfo` (orchestrator's notes, F1): a values `apiUrl`
may carry userinfo, and httpx's canonical form keeps it. Measured on the canonical forms the gate stores:
`https://url-user:url-secret@api.a.example.com:6443` shows as `https://api.a.example.com:6443`;
`https://u:p@h:6443/path?q=…#…` as `https://h:6443/path`; `https://api.crc.testing:6443` unchanged; and
`http://…`, `https://[::1/broken`, `https://host:bad/x` and the empty string all return None, shown as "the
answering target (not shown: its URL is not https with a host)". The gate's keys and the stored evidence are
unchanged; only the display narrows. The refusal still crosses `exc.scrub(secrets)`.

### 3.3 The budget over the system

**The scope of the words** (review F3). *Account* is the exact configured username string, compared as written:
directory aliases and case variants are not resolved, so every stanza for one directory identity must use one
spelling; two spellings are two entries and two answered failures (`test_username_case_residual`). *Process* is
the production Poller's one gate (poller.py:968-970), used serially on its discovery thread; a newly constructed
gate starts a new budget, which is exactly what a restart or a second replica is. Digest collisions and two
directories sharing an exact username and password over-block, the safe direction.

For one wrong or locked password on one account, in one process, measured in authorize requests by §4's harness
(a wire mock counts authorize requests, not directory binds):

| shape | before (`cbe828b`) | after |
|---|---|---|
| N distinct targets on one account, 401 or 500 on the first | N (4 measured) | **1** |
| one cluster under two URLs (`https://api.crc.testing:6443`, `https://kubernetes.default.svc`) | 2 | **1** |
| state reset: a new `CredentialGate` (a restart, a second replica) | 1 more | **1 more** — not covered until #285's Lease |
| an irrelevant config edit (`visibility`) | 0 more | **0 more** |
| two successful ConfigMap onboardings on one account (#293) | 2 | **2** — unchanged by design |

#293's table (SPEC_S5 §3.3) is stated per canonical target, and every row is unchanged per target: a success
still spends only its own target, and a bound failure still stops its own target — it now also stops the others.

### 3.4 What does not change, and the residuals

A failure before the password is written (`ConnectError`, `ConnectTimeout`, TLS) never reaches `refuse()`
(`test_pre_write_failure_can_retry`). Rotation re-arms both kinds: a new password is a new digest
(`test_password_rotation_rearms_the_existing_gate`). `poller.py`, `fleetlogin.py`, the chart's templates and
values, and RBAC are not touched. Residuals, stated: two directories sharing a username and password over-block each other (the safe
direction); the username is compared as written, so two stanzas naming one directory account in different case
are two entries (not measured: whether the estate's LDAP identity provider folds case); a restart or a second
replica starts empty until #285.

### 3.5 Documents

SPEC_S4b's R2-1 (orchestrator's notes, and R2-2's second clause) is marked superseded with a pointer; its §3.12
code is the verbatim design body and keeps its history. SPEC_S4c's §3.3 cache paragraph names the refused kind
as what `FleetRecord.refused` seeds and quotes the docstring sentence this change writes, recorded in its notes.
`docs/DESIGN_remote_cluster_access.md` states the gate per target twice (the join flow and the table row); both
are corrected, and so are the same two statements in `docs/diagrams/remote-cluster-access/source.html` (the
join figure's aria-label and the join table's row). The rendered `joining-a-cluster.*.png` needs no re-render: its
visible SVG text says only "gate: not re-sent once refused", an aria-label is not painted, and the table sits after
the figure's `</figure>`. SPEC_S5 §3.3's "Different targets still have different #284 gate keys" is replaced in
place and recorded in S5's notes; its table is unchanged. `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`'s
paragraph that left cross-target lockout to #285 is rewritten, with a chart PATCH (0.58.6) and its `Chart.yaml`
history line — no template, value or RBAC change. The CHANGELOG entry goes first under `## Unreleased`.

## 4. Tests, before and after

In three new files — `test_credential_gate_account.py`, `test_credential_gate_diagnostics.py` and
`test_credential_gate_docs.py` — and the two rewritten in `test_fleet_lookup.py`; no other existing test is
edited. "Before" is main `3d1c237` (with this spec) plus §6's test blocks only; "after" is the same tree with
every block applied.

| Definition of Done | test | before | after |
|---|---|---|---|
| N ≥ 3 targets (4) and a 500 on the first: 1 authorize, the rest gated naming the first | `test_one_answered_failure_gates_every_target_of_the_account[500]` | FAILED `4 authorize requests` | passed |
| the same with a 401 | `test_one_answered_failure_gates_every_target_of_the_account[401]` | FAILED `4 authorize requests` | passed |
| two URLs for one cluster: 1 authorize | `test_two_urls_for_one_cluster_are_one_authorize` | FAILED `assert 2 == 1` | passed |
| #293 probe: two successful ConfigMap onboardings, 2 authorizes | `test_two_successful_configmap_onboardings_on_one_account_are_two_authorizes` | passed | passed; FAILED under the naive key (§2) |
| the harness: two URLs, two clusters, state reset (+1), irrelevant edit (+0) | `test_the_budget_over_the_system[401]`, `[500]` | FAILED `(1, 1) != (1, 0)` on the first two rows | passed |
| line 280, rewritten to the ruling | `test_one_target_spelled_three_ways_is_one_gate_entry` | FAILED `https://api.example.com:6444` | passed |
| :284, rewritten to the ruling | `test_the_gate_is_per_account_so_a_sick_clusters_500_stops_a_healthy_one_too` | FAILED `DID NOT RAISE LookupRefused` (the second target bound and was written) | passed |
| F1: the gated detail, finding and log line carry no URL credentials | `test_gated_target_never_exports_url_credentials` | FAILED `IndexError: pop from empty list` (not gated: the second target bound); against the first revision's code, without the display seam: FAILED `AssertionError: url-user` | passed |
| F2: five stale per-target statements are gone, each file names #315 | `test_current_docs_do_not_claim_failure_is_target_scoped` (5 cases) | FAILED, 5 of 5 | passed |
| F3: the docstring defines "account" and "process" | `test_the_gate_states_the_scope_of_account_and_process` | FAILED | passed |
| F3: two spellings of one username are two authorizes (a pinned residual) | `test_username_case_residual` | passed | passed |

## 5. On the lab, for the implementing pull request

Nothing here binds as the fleet account (SPEC_S4c: "Nothing in this spec, its tests or its verification logs in
as it"). After the deploy with `local-development/release-crc.sh`, read only: `shared-rnd` keeps polling
(its cluster row's last poll advances), and the dashboard pod's log carries no `fleet-login` line, because
`shared-rnd` already holds its Secret and nothing binds. The evidence goes under `reports/<date>_<slug>/`,
pinned to the merge sha, as the issue's Definition of Done says.

## 6. Implementation blocks

Twenty-two blocks over thirteen files, in apply order.

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
from .fleetlogin import FleetLogin, LoginError
```

```python
from .fleetlogin import FleetLogin, LoginError, _without_userinfo
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
class CredentialGate:
    """SPEC_S4 §6's in-memory half: a password a target evaluated — or may have — is never sent to
    THAT target again while it is the same password. Keyed on (target, username, sha256(password)):
    the target, because a 500 from one cluster must not stop a healthy one on the same account
    (review of #295, second pass, R2-1); the digest, because the password is not in the declaration,
    so the normal fix — rotating the Secret — changes no stanza and must re-arm this by itself.
    Best-effort and per process; the durable, replica-shared gate is #285's."""

    def __init__(self) -> None:
        self._refused: set[tuple[str, str, str]] = set()

    @staticmethod
    def _key(target: str, username: str, password: str) -> tuple[str, str, str]:
        # THE TARGET AS httpx CANONICALISES IT (third pass, R3-1): host case and IDNA, not a whole-string
        # lowercase that would mangle a path or a port. `api.example.com` and `API.example.com/` are one
        # directory-backed target and one gate entry. A malformed URL falls back to the bare string:
        # the gate must never raise. The digest is 64 bits ON PURPOSE — a collision over-blocks, never
        # binds again.
        try:
            canonical = str(httpx.URL(target)).rstrip("/")
        except httpx.InvalidURL:
            canonical = target.rstrip("/")
        return canonical, username, hashlib.sha256(password.encode("utf-8")).hexdigest()[:16]

    def refused(self, target: str, username: str, password: str) -> bool:
        return self._key(target, username, password) in self._refused

    def refuse(self, target: str, username: str, password: str) -> None:
        self._refused.add(self._key(target, username, password))

```

```python
class CredentialGate:
    """SPEC_S4 §6's in-memory half: a password the directory evaluated — or may have — is not sent
    again while it is the same password. Two kinds of entry (#315, SPEC_S4d):

    REFUSED, keyed on (username, sha256(password)[:16]) — the ACCOUNT, never the target. Every
    `LoginError.bound` answer writes it, a 401 and a 500 alike: a directory locks out per account,
    and a locked account's 500 (LDAP code 19) cannot be told from a sick target's 500. The operator's
    ruling at the review of #325 (SPEC_S4c, orchestrator's notes), reversing R2-1 of #295's second
    pass; the price is that one sick target's 500 stops every target of the account until the
    password rotates or the process restarts (SPEC_S4c §5, question 7). The target that answered is
    kept as evidence and named in the gated refusal.

    SPENT, keyed on (target, username, digest) — #293's success mark (SPEC_S5 §3.3): a successful
    ConfigMap session spends THAT target's budget, so onboarding one cluster never gates another.

    The digest, because the password is not in the declaration: rotating the Secret changes no
    stanza and must re-arm both kinds by itself. It is 64 bits ON PURPOSE — a collision over-blocks,
    never binds again; so does one username and password shared by two directories, the safe
    direction, stated and not solved.

    THE BUDGET, with its scope: at most one answered failed authorize per (account, password) per
    process, across every target. "Account" is the exact configured username string, compared as
    written: directory aliases and case variants are not resolved, so every stanza for one identity
    must use one spelling. "Process" is the production Poller's one gate, used serially on its
    discovery thread; a new gate starts a new budget. A restart or a second replica starts empty —
    not covered until #285's account Lease, which this becomes the cache of (SPEC_S4c §3.3)."""

    def __init__(self) -> None:
        self._refused: dict[tuple[str, str], str] = {}
        self._spent: set[tuple[str, str, str]] = set()

    @staticmethod
    def _target(target: str) -> str:
        # THE TARGET AS httpx CANONICALISES IT (third pass, R3-1): host case and IDNA, not a whole-string
        # lowercase that would mangle a path or a port. `api.example.com` and `API.example.com/` are one
        # target. A malformed URL falls back to the bare string: the gate must never raise.
        try:
            return str(httpx.URL(target)).rstrip("/")
        except httpx.InvalidURL:
            return target.rstrip("/")

    @staticmethod
    def _digest(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()[:16]

    def answered(self, target: str, username: str, password: str) -> str | None:
        """The target whose answer gates this password for this account on `target`, or None: the
        account's REFUSED entry from whichever target answered, else `target`'s own SPENT entry."""
        digest = self._digest(password)
        refused = self._refused.get((username, digest))
        if refused is not None:
            return refused
        canonical = self._target(target)
        return canonical if (canonical, username, digest) in self._spent else None

    def refused(self, target: str, username: str, password: str) -> bool:
        return self.answered(target, username, password) is not None

    def refuse(self, target: str, username: str, password: str) -> None:
        """A bound failure: the account's entry, whatever target answered; the first answer stays the evidence."""
        self._refused.setdefault((username, self._digest(password)), self._target(target))

    def spend(self, target: str, username: str, password: str) -> None:
        """#293's success mark: this target's entry only."""
        self._spent.add((self._target(target), username, self._digest(password)))

```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
        if gate.refused(cluster.api_url, account, password):
            raise LookupRefused("login-refused", f"{cluster.name} evaluated this password for {account} already and it "
                                                 f"has not changed",
                                action=("not tried again until the fleet password Secret or the stanza changes — rotate the "
                                        "Secret, or correct ldapConnectionBootstrap; the password is re-read each cycle at no "
                                        "cost and the login resumes when it moves (SPEC_S4 §6)"), spent=False, gated=True)
```

```python
        answered = gate.answered(cluster.api_url, account, password)
        if answered is not None:
            # THE TARGET THAT ANSWERED IS NAMED (#315): the entry is the account's, so it may be another
            # cluster's answer that stops this one, and the finding must say where to look. Shown without
            # userinfo, query or fragment: a values `apiUrl` is not held to the Secret contract's
            # no-credential URL rule, and the gate's evidence keeps whatever the stanza wrote.
            shown = _without_userinfo(answered) or "the answering target (not shown: its URL is not https with a host)"
            raise LookupRefused("login-refused", f"{shown} evaluated this password for {account} already and it "
                                                 f"has not changed; {cluster.name} does not send it",
                                action=("not tried again until the fleet password Secret or the account the stanza names "
                                        "changes — rotate the Secret, or correct ldapConnectionBootstrap; the password is "
                                        "re-read each cycle at no cost and the login resumes when it moves (SPEC_S4 §6)"),
                                spent=False, gated=True)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
                    # #293's strict budget includes successful binds, even if the later read/write fails.
                    # Keep the SAME process-lifetime gate used by every existing lookup caller.
                    gate.refuse(cluster.api_url, account, password)
```

```python
                    # #293's strict budget includes successful binds, even if the later read/write fails.
                    # Keep the SAME process-lifetime gate used by every existing lookup caller — THIS
                    # target's entry only: a success elsewhere must not gate another cluster (#315).
                    gate.spend(cluster.api_url, account, password)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
                # account's code 19 included), answered without a token — or may have: a read timeout
                # after the GET was written. Never sent to THIS target again while it is this password
                # (review of #295, P0-1 and second pass R2-1): re-entering #283's terminal answer from a
                # schedule is the lockout walk one layer up, and an in-memory "final" that any shape
                # change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read as failed.
                gate.refuse(cluster.api_url, account, password)
```

```python
                # account's code 19 included), answered without a token — or may have: a read timeout
                # after the GET was written. Never sent again as this account, to this target or ANY
                # other, while it is this password (review of #295, P0-1; the operator's ruling on #325,
                # SPEC_S4c's orchestrator's notes, which reversed R2-1's per-target key — a locked
                # account's 500 cannot be told from a sick target's): re-entering #283's terminal answer
                # from a schedule is the lockout walk one layer up, and an in-memory "final" that any
                # shape change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read
                # as failed.
                gate.refuse(cluster.api_url, account, password)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
                                            f"or check the account is not locked — it is not sent there again while it "
                                            f"is the same password"), spent=True) from exc
```

```python
                                            f"or check the account is not locked — it is not sent again, to this or any "
                                            f"other cluster, while it is the same password"), spent=True) from exc
```

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->
```python
    def test_one_target_spelled_three_ways_is_one_gate_entry(self):
        """Third pass, R3-1: a stanza edited from api.example.com to API.example.com was a new key and
        the password went to the same target again. httpx canonicalises the host; a malformed URL
        must not raise inside the gate."""
        gate = CredentialGate()
        gate.refuse("https://api.example.com:6443", USER, PASSWORD)
        for spelling in ("https://api.example.com:6443/", "https://API.Example.COM:6443", "https://API.example.com:6443/"):
            assert gate.refused(spelling, USER, PASSWORD), spelling
        assert not gate.refused("https://api.example.com:6444", USER, PASSWORD), "a different port is a different target"
        gate.refuse("https://[::1/broken", USER, PASSWORD)
        assert gate.refused("https://[::1/broken/", USER, PASSWORD), "the fallback key, not an exception"

    def test_the_gate_is_per_target_so_a_sick_cluster_does_not_stop_a_healthy_one(self, wire):
        """Review of #295, second pass, R2-1: keyed without the target, a 500 from A blocked B."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused):
            run(RND, gate=gate)
        other = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
        result, _ = run(other, gate=gate, s=settings(other))
        assert result.written == "created" and len(wire.authorize) == 2
        assert gate.refused(API, USER, PASSWORD) and not gate.refused(other.api_url, USER, PASSWORD)


```

```python
    def test_one_target_spelled_three_ways_is_one_gate_entry(self):
        """Third pass, R3-1: a stanza edited from api.example.com to API.example.com was a new key and
        the password went to the same target again. httpx canonicalises the host; a malformed URL
        must not raise inside the gate. REWRITTEN to the operator's ruling on #325 (SPEC_S4c,
        orchestrator's notes; #315): a bound failure's entry is the ACCOUNT's, so every spelling and
        every port is gated by it; the canonical target still keys #293's success mark, where a
        different port is a different target."""
        gate = CredentialGate()
        gate.refuse("https://api.example.com:6443", USER, PASSWORD)
        for spelling in ("https://api.example.com:6443/", "https://API.Example.COM:6443", "https://api.example.com:6444"):
            assert gate.refused(spelling, USER, PASSWORD), spelling
        spent = CredentialGate()
        spent.spend("https://api.example.com:6443", USER, PASSWORD)
        for spelling in ("https://api.example.com:6443/", "https://API.Example.COM:6443", "https://API.example.com:6443/"):
            assert spent.refused(spelling, USER, PASSWORD), spelling
        assert not spent.refused("https://api.example.com:6444", USER, PASSWORD), "a success spends its own target only"
        spent.spend("https://[::1/broken", USER, PASSWORD)
        assert spent.refused("https://[::1/broken/", USER, PASSWORD), "the fallback key, not an exception"

    def test_the_gate_is_per_account_so_a_sick_clusters_500_stops_a_healthy_one_too(self, wire):
        """REVERSED by the operator's ruling on #325 (SPEC_S4c, orchestrator's notes; #315). R2-1 of
        #295's second pass keyed the gate on the target so a 500 from A would not block B; but a
        locked account's 500 (LDAP code 19) cannot be told from a sick target's, and a lockout is per
        directory account. The price, stated in SPEC_S4c §5 question 7: B waits for the password to
        rotate."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused):
            run(RND, gate=gate)
        other = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
        with pytest.raises(LookupRefused) as exc:
            run(other, gate=gate, s=settings(other))
        assert exc.value.gated and exc.value.spent is False and len(wire.authorize) == 1
        assert exc.value.detail.startswith(f"{API} evaluated this password"), exc.value.detail
        assert gate.refused(API, USER, PASSWORD) and gate.refused(other.api_url, USER, PASSWORD)


```

<!-- block: local-development/tests/test_credential_gate_account.py | create -->
```python
"""#315 (SPEC_S4d): the credential gate is per ACCOUNT for every bound failure — the operator's ruling at
the review of #325 (SPEC_S4c, orchestrator's notes) — while #293's success mark stays per target
(SPEC_S5 §3.3). The fake target is S4a's and `wire` counts authorize requests, the unit the budget is
stated in: a wire mock measures authorize requests, not directory binds."""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.fleetlookup import CredentialGate, LookupRefused, lookup
from test_configmap_onboarding import STANZA, Host, cm, cycle
from test_fleet_login import login_302, refused_401
from test_fleet_lookup import USER, run, sa_secret, settings, wire  # noqa: F401

ANSWERS = {"401": refused_401, "500": lambda: httpx.Response(500, text="Internal Server Error")}


def target(name: str, url: str) -> ClusterConfig:
    return ClusterConfig(name, url, sa_token_lookup=True, ldap_connection_bootstrap=USER)


def attempt(cluster: ClusterConfig, gate: CredentialGate) -> LookupRefused:
    with pytest.raises(LookupRefused) as exc:
        run(cluster, gate=gate, s=settings(cluster))
    return exc.value


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_one_answered_failure_gates_every_target_of_the_account(wire, answer):
    """N = 4 distinct targets on one account and a failure on the first: exactly one authorize, and the
    other three refused as gated, each naming the target that answered. A 500 is what a LOCKED 389-ds
    account answers (LDAP code 19), so it gates exactly like a 401."""
    targets = [target(n, f"https://api.{n}.example.com:6443") for n in ("rnd", "east", "west", "north")]
    wire.answers = [ANSWERS[answer]() for _ in targets]     # enough for a per-target gate to spend them all
    gate = CredentialGate()
    first = attempt(targets[0], gate)
    others = [attempt(other, gate) for other in targets[1:]]
    assert len(wire.authorize) == 1, f"{len(wire.authorize)} authorize requests for one account and one password"
    assert first.spent is True and not first.gated
    for other, refusal in zip(targets[1:], others):
        assert (refusal.code, refusal.gated, refusal.spent) == ("login-refused", True, False), other.name
        assert refusal.detail.startswith(f"{targets[0].api_url} evaluated this password for {USER}"), refusal.detail
        assert refusal.detail.endswith(f"{other.name} does not send it"), refusal.detail


def test_two_urls_for_one_cluster_are_one_authorize(wire):
    """The lab's case 1 (#315): one physical cluster entered as `https://api.crc.testing:6443` and as
    `https://kubernetes.default.svc`. No URL canonicalisation folds two host names; the account key does."""
    wire.answers = [ANSWERS["500"](), ANSWERS["500"]()]
    gate = CredentialGate()
    attempt(target("shared-rnd", "https://api.crc.testing:6443"), gate)
    gated = attempt(target("dashboard", "https://kubernetes.default.svc"), gate)
    assert len(wire.authorize) == 1
    assert gated.gated and gated.detail.startswith("https://api.crc.testing:6443 evaluated this password"), gated.detail


def test_two_successful_configmap_onboardings_on_one_account_are_two_authorizes(wire):
    """#293's budget table (SPEC_S5 §3.3) is unchanged: a SUCCESSFUL ConfigMap session spends its own target
    only, so a second cluster on the same account and password still onboards. Passes before #315 and after;
    fails under a naive per-account key, which gates `east` on `rnd`'s success."""
    east = {**STANZA, "name": "east", "apiUrl": "https://api.east.example.com:6443"}
    host = Host([cm([STANZA, east])])
    s, clusters, _, _ = cycle(host)
    assert sorted(c.name for c in clusters) == ["east", "rnd"] and all(c.onboarding for c in clusters)
    wire.answers = [login_302(), login_302()]
    gate = CredentialGate()
    for cluster in clusters:
        wire.secret = httpx.Response(200, json=sa_secret())
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == 2 and {"gsd-cluster-rnd", "gsd-cluster-east"} <= set(host.secrets)


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_the_budget_over_the_system(wire, answer):
    """The harness (#315's Definition of Done): authorize requests for one account and one wrong or locked
    password, as (the first lookup, what the second adds), per shape. The state reset is a NEW
    CredentialGate — what a restart or a second replica starts with — and it adds ONE: that residual is
    stated, not covered, until #285's account Lease (SPEC_S4c §3.3)."""
    rnd = target("shared-rnd", "https://api.crc.testing:6443")
    shapes = {
        "two URLs, one cluster": (target("dashboard", "https://kubernetes.default.svc"), False),
        "two clusters, one credential": (target("east", "https://api.east.example.com:6443"), False),
        "state reset (a new gate)": (rnd, True),
        "irrelevant config edit (visibility)": (dataclasses.replace(rnd, visibility="self-only"), False),
    }
    measured = {}
    for shape, (second, reset) in shapes.items():
        wire.requests.clear()
        wire.answers = [ANSWERS[answer](), ANSWERS[answer]()]
        gate = CredentialGate()
        attempt(rnd, gate)
        first = len(wire.authorize)
        attempt(second, CredentialGate() if reset else gate)
        measured[shape] = (first, len(wire.authorize) - first)
    assert measured == {
        "two URLs, one cluster": (1, 0),
        "two clusters, one credential": (1, 0),
        "state reset (a new gate)": (1, 1),
        "irrelevant config edit (visibility)": (1, 0),
    }


def test_username_case_residual(wire):
    """PINS A RESIDUAL, not a guarantee (review of SPEC_S4d, Codex F3): "account" is the exact configured
    username string, so two spellings of one directory identity are two entries and two answered failures.
    Folding case would over-block distinct accounts on a case-sensitive provider; every stanza for one
    identity must use one spelling."""
    wire.answers = [ANSWERS["401"](), ANSWERS["401"]()]
    gate = CredentialGate()
    attempt(target("rnd", "https://api.rnd.example.com:6443"), gate)
    upper = dataclasses.replace(target("east", "https://api.east.example.com:6443"), ldap_connection_bootstrap=USER.upper())
    attempt(upper, gate)
    assert len(wire.authorize) == 2
```

<!-- block: local-development/tests/test_credential_gate_diagnostics.py | create -->
```python
"""#315 (SPEC_S4d, review F1): the gated refusal names the target that answered, and must not copy the
credentials a values `apiUrl` may carry — the Secret contract's no-credential URL rule does not cover
values — into the exception, the public finding or the `fleet-lookup-failed` line."""

from __future__ import annotations

import json
import logging

import pytest

from gsd.config import ClusterConfig, parse_cluster_entries
from gsd.fleetlookup import CredentialGate, LookupRefused
from gsd.poller import Poller, _LookupState
from gsd.store import Store
from test_fleet_login import refused_401
from test_fleet_lookup import PASSWORD, USER, run, settings, wire  # noqa: F401


def fail(cluster: ClusterConfig, gate: CredentialGate) -> LookupRefused:
    with pytest.raises(LookupRefused) as caught:
        run(cluster, gate=gate, s=settings(cluster))
    return caught.value


def test_gated_target_never_exports_url_credentials(wire, tmp_path, caplog):
    # A REAL values stanza: the values parser accepts userinfo in apiUrl.
    url = "https://url-user:url-secret@api.a.example.com:6443"
    _, first = parse_cluster_entries([{"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X"},
                                      {"name": "a", "apiUrl": url, "saTokenLookup": True,
                                       "ldapConnectionBootstrap": USER}], "values")
    wire.answers = [refused_401()]
    gate = CredentialGate()
    fail(first, gate)
    second = ClusterConfig("b", "https://api.b.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
    exc = fail(second, gate)
    s = settings(second)
    poller = Poller(Store(str(tmp_path / "detail.db")), s)
    with caplog.at_level(logging.INFO):
        poller._lookup_failed(_LookupState(), "b", "gsd-cluster-b", exc, 0)
    public = json.dumps([f.public() for f in s.cluster_registry.findings()])
    combined = f"{exc}\n{exc.detail}\n{public}\n{caplog.text}"
    assert (exc.code, exc.gated, exc.spent) == ("login-refused", True, False) and len(wire.authorize) == 1
    for secret in ("url-user", "url-secret", PASSWORD):
        assert secret not in combined, secret
    assert exc.detail.startswith("https://api.a.example.com:6443"), exc.detail
```

<!-- block: local-development/tests/test_credential_gate_docs.py | create -->
```python
"""#315 (SPEC_S4d, review F2 and F3): the maintained documents that stated the superseded per-target
failure rule say the per-account one, and the gate states what "account" and "process" mean."""

from __future__ import annotations

import pathlib

import pytest

from gsd.fleetlookup import CredentialGate

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path,stale", [
    ("docs/specs/SPEC_S5_configmap_onboarding.md", "Different targets still have different #284 gate keys;"),
    ("charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md", "Cross-process and cross-target account-wide\nlockout protection is #285"),
    ("docs/diagrams/remote-cluster-access/source.html", "once refused, not re-sent to that target by this process"),
    ("docs/diagrams/remote-cluster-access/source.html", "a password the target already refused is not sent again"),
    ("docs/DESIGN_remote_cluster_access.md", "a password this target already refused is not sent again"),
])
def test_current_docs_do_not_claim_failure_is_target_scoped(path, stale):
    text = (REPO / path).read_text()
    assert stale not in text
    assert "#315" in text


def test_the_gate_states_the_scope_of_account_and_process():
    doc = " ".join((CredentialGate.__doc__ or "").split())
    assert '"Account" is the exact configured username string' in doc
    assert "must use one spelling" in doc
    assert "\"Process\" is the production Poller's one gate" in doc
```

<!-- block: docs/specs/SPEC_S4b_sa_token_lookup.md | edit -->
```markdown
    may have. `final` is gone. The business owner retracted the earlier "keep two tiers" decision
    on the measurement; the stored code stays `login-refused` for a 401 and `login-failed` otherwise.
```

```markdown
    may have. `final` is gone. The business owner retracted the earlier "keep two tiers" decision
    on the measurement; the stored code stays `login-refused` for a 401 and `login-failed` otherwise.
    **Superseded in part (#315, `docs/specs/SPEC_S4d_credential_gate_per_account.md`):** the target
    half of this key, and R2-2's "a different target on the same account still may", were reversed by
    the operator's ruling at the review of #325 (`docs/specs/SPEC_S4c_credential_lifecycle.md`,
    orchestrator's notes): a lockout is per directory account and a locked account's 500 cannot be told
    from a sick target's, so every `bound` answer now gates the ACCOUNT on every target, keyed on
    (username, sha256(password)), with the answering target kept as evidence. The per-target key
    stated here and in §3.12's `CredentialGate` is #284's history, not the code.
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
  rotates or the entry is cleared (§5, question 7). §3.4's ping already stood down on either kind for the
  same reason; every other path now does too.
```

```markdown
  rotates or the entry is cleared (§5, question 7). §3.4's ping already stood down on either kind for the
  same reason; every other path now does too.
- **#315 ships B2's in-memory half first** (`docs/specs/SPEC_S4d_credential_gate_per_account.md`):
  `CredentialGate` holds a refused kind, keyed on (account, digest) and written by every bound answer with
  the answering target as evidence, and a spent kind, #293's per-target success mark (SPEC_S5 §3.3). §3.3's
  cache paragraph now names the refused kind as what `FleetRecord.refused` seeds, leaves the spent kind
  off the Lease, and quotes the docstring sentence #315 wrote, which is the one this spec replaces.
  "Account" there is the exact configured username string (SPEC_S4d §3.3); the Lease inherits that key.
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
`gsd/fleetlookup.py#CredentialGate` stays as the **cache**: seeded from `FleetRecord.refused` at every
read, consulted where it is today. Its docstring's sentence *"Best-effort and per process; the
durable, replica-shared gate is #285's"* is replaced by "the cache of the account Lease's gate
(SPEC_S4c §3.3); seeded on every read, and never the only copy while the Lease is writable."
```

```markdown
`gsd/fleetlookup.py#CredentialGate` stays as the **cache**: its refused kind — the account's entry,
keyed on (account, digest), which #315 made per account in memory
(`docs/specs/SPEC_S4d_credential_gate_per_account.md`) — is seeded from `FleetRecord.refused` at every
read and consulted where it is today; its spent kind, #293's per-target success mark (SPEC_S5 §3.3), is
not on the Lease and stays as it is. Its docstring's sentence *"A restart or a second replica starts
empty — not covered until #285's account Lease, which this becomes the cache of (SPEC_S4c §3.3)"* is
replaced by "the cache of the account Lease's gate (SPEC_S4c §3.3); seeded on every read, and never the
only copy while the Lease is writable."
```

<!-- block: docs/specs/SPEC_S5_configmap_onboarding.md | edit -->
```markdown
noticed by the existing cheap re-read. Different targets still have different #284 gate keys;
account-wide durable/replica-shared fencing belongs to #285. This spec does **not** imply one total
```

```markdown
noticed by the existing cheap re-read. Since #315 (`docs/specs/SPEC_S4d_credential_gate_per_account.md`),
a bound failure gates its account and password on every target in the process; a successful ConfigMap
session still spends only its own canonical target/account/password entry. Account is the exact
configured username string: use one spelling for one directory identity. Durable, replica-shared
fencing belongs to #285. This spec does **not** imply one total
```

<!-- block: docs/specs/SPEC_S5_configmap_onboarding.md | edit -->
```markdown
  in the workspace `phase2-report.md`; baseline research citations remain pinned to phase 1.
```

```markdown
  in the workspace `phase2-report.md`; baseline research citations remain pinned to phase 1.
- #315 (`docs/specs/SPEC_S4d_credential_gate_per_account.md`, 2026-09-26): §3.3's sentence "Different
  targets still have different #284 gate keys" is replaced in place. A bound failure now gates the account
  on every target (the operator's ruling at the review of #325); the success mark this spec added stays per
  target, and every row of §3.3's table, stated per canonical target, is unchanged.
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
The baseline values/Secret trigger still gates bound login failures as #284 specifies; this does not
claim that its successful logins were globally one-shot. Cross-process and cross-target account-wide
lockout protection is #285's work, not measured or implemented by this feature. Keep one replica.
```

```markdown
Since #315, every bound login failure gates that account and password on every target in this
process, for values, Secret and ConfigMap triggers alike. Successful ConfigMap sessions still spend only
their own target's budget; successful values/Secret logins are not globally one-shot. Account means the
exact configured username string: use one spelling for one directory identity. A restart or another
replica starts with an empty gate; durable, replica-shared protection remains #285's work. Keep one replica.
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# CHART 0.58.5 (2026-09-26), PATCH: appVersion moves to application 0.37.0 (below); Epic B: protect
# the data during upgrades (#382).
version: 0.58.5
```

```yaml
# CHART 0.58.5 (2026-09-26), PATCH: appVersion moves to application 0.37.0 (below); Epic B: protect
# the data during upgrades (#382).
# CHART 0.58.6 (2026-09-26), PATCH: docs only — CLUSTER_CREDENTIALS.md states the credential gate per
# account (#315, SPEC_S4d). No template, value or RBAC change; appVersion unchanged.
version: 0.58.6
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
           -> the credential gate: a password this target already refused is not sent again
```

```markdown
           -> the credential gate: a password the account was already refused, by any target, is not sent again (#315)
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| The lookup itself (the join) | the poller, automatically: the leader, or the sole replica without election (more replicas without election are refused) | unchanged | the remote, as the fleet account | the fleet password; once refused, not re-sent to that target by this process (`local-development/gsd/fleetlookup.py#CredentialGate`) |
```

```markdown
| The lookup itself (the join) | the poller, automatically: the leader, or the sole replica without election (more replicas without election are refused) | unchanged | the remote, as the fleet account | the fleet password; once refused, not re-sent as that account to any target by this process (#315) (`local-development/gsd/fleetlookup.py#CredentialGate`) |
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the target already refused is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

```html
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the account was already refused, by any target, is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
          <tr><td>The lookup itself (join)</td><td>the poller, automatically: the leader, or the sole replica without election (more replicas without election are refused)</td><td>unchanged</td><td>remote: the fleet account's login</td><td>the fleet password; once refused, not re-sent to that target by this process</td></tr>
```

```html
          <tr><td>The lookup itself (join)</td><td>the poller, automatically: the leader, or the sole replica without election (more replicas without election are refused)</td><td>unchanged</td><td>remote: the fleet account's login</td><td>the fleet password; once refused, not re-sent as that account to any target by this process (#315)</td></tr>
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

- **The fleet login module is consolidated, behaviour unchanged (#291; application code only, no version of
```

```markdown
## Unreleased

- **The credential gate is per account for every failed login (#315,
  `docs/specs/SPEC_S4d_credential_gate_per_account.md`; application code with no version of its own, chart
  0.58.6 for `CLUSTER_CREDENTIALS.md`).** When the fleet account's password is sent and no session comes back —
  a 401, or the 500 a locked directory account answers — the dashboard no longer sends that password, as that
  account, to any other cluster while it is the same password: at most one answered failed login per account
  and password per process, across every cluster, where it was one per cluster. N clusters sharing the fleet
  account, or one cluster entered under two URLs, now cost one failed login instead of N. "Account" is the
  username exactly as the stanzas write it: two spellings of one directory identity are two accounts, so use
  one. The other clusters' findings stay `login-refused` with `gave_up=true`, and their detail now names the
  API URL that answered, without any credentials the URL carries. A successful ConfigMap onboarding still
  spends only its own cluster (#293's budget, SPEC_S5 §3.3, unchanged). The price, the operator's choice at
  the review of #325: one sick cluster's 500 stops the lookup on every cluster of that account until the
  password is rotated or the pod restarts. A restart or a second replica still starts with an empty gate,
  until #285's account Lease.

- **The fleet login module is consolidated, behaviour unchanged (#291; application code only, no version of
```
