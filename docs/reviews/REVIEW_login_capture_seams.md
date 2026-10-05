# Review of the login-capture read seams

Fable 5 (high reasoning), three lenses, over the two fixes on `test/login-capture-cross-seam` and the
seam they sit in. **Reproduced verbatim from the reviewer's structured output** — the arbiter works from
this text, not from a summary of it. Its own words are unedited; anything I add is under `### Arbiter`.

Baseline at the time of review: 1069 passed, 1 skipped, with both fixes applied.

---

## Lens 1 — the loginlog.py success-cause fix
**Reviewer's summary.** Measured: the full suite passes in the worktree (1069 passed, 1 skipped, 4 deselected, exit 0, gsd resolving to wt-crossseam). Grep proves named_at has exactly three occurrences — field, single construction at loginlog.py:408, one read at :361 — and `pending[user] =` exists only at :408, so no second construction path exists (causes go to `orphans`, never create pendings). Probes against real fixture lines show: (Q1) the only sequence where a success carries its OWN bind code is a multi-LDAP-IdP chain (bind 49 on ldap-1, SUCCEEDED on ldap-2), and suppression there is consistent with the field's documented meaning and with the already-discarded failures list — FIX_IS_CORRECT; (Q2) named_at differs from first_at only after adopt(), the expiry check at :396 is untouched by the diff, and conclusion timing is byte-identical pre/post — FIX_IS_CORRECT; (Q3) proven by grep — FIX_IS_CORRECT; (Q4) the residue is real but PRE-EXISTING, not new: running the exact stranger-bind → success → stranger-verdict scenario against the pre-fix parser (git show HEAD:) produced the identical degraded row for the stranger ('failed', no reason, stamped at the verdict) that the post-fix parser produces. However, the fix made success-side adoption output-inert — conclude() now suppresses everything a success adopts — so consuming the orphan has exactly one remaining effect: destroying the cause a real later failure owns. An adopt-time guard (skip unidentified orphans when the creating verdict is "succeeded") restores the stranger's bad_password@bind-ts, passes all 81 parser/capture tests unchanged, and my test fails on the fix as shipped and passes with the guard. Reported as PRE_EXISTING_DEFECT_MISSED, medium.

### LENS1-Q4-orphan-destroyed-by-inert-adoption — PRE_EXISTING_DEFECT_MISSED — medium
**Claim.** gsd/loginlog.py:adopt — a success-creating verdict still adopts (and deletes) an unidentified bind-failure orphan even though conclude() now suppresses everything it took, so the adoption's only remaining effect is robbing the real later failure of its cause; the fix's new comment ('necessarily before any outcome is known') is refuted by its own call site, where v.group("verdict") is in scope and a succeeded verdict concludes immediately.
**Trigger.** Within one ATTEMPT_WINDOW: a bind error for a foreign DN with no found-dn line in the read (unidentified orphan), then a SUCCEEDED verdict for another user (creates a pending, adopt() consumes the orphan), then the failed verdict of the user the bind actually belonged to.
**Consequence.** The stranger's wrong-password login shows as outcome 'failed' with detail "provider 'ldap-local' reported no reason" stamped at the verdict, instead of bad_password with ldap_result_code=49 stamped at the bind — the dashboard loses the one field that tells an operator what to do, whenever a success interleaves. NOT introduced by this fix: measured identical pre-fix. But pre-fix the adoption at least fed the success's own (wrong) row; post-fix it feeds nothing.
**Evidence.** Probe (scratchpad/probe_lens1.py) against the WORKTREE parser: Q4a [bind(cn=Someone Else, code 49, unidentified) at .100 -> jane SUCCEEDED at .400 -> sam.other failed at .700] => sam.other 'failed' at=.700 code=None detail="provider 'ldap-local' reported no reason"; Q4b counterfactual without jane's line => sam.other 'bad_password' at=.100 code=49. Same scenario against PRE-FIX parser (git show HEAD:local-development/gsd/loginlog.py, probe_prefix.py): sam.other 'failed' at=.700 code=None — identical, so pre-existing. With the guard below: sam.other 'bad_password' at=.100 code=49, jane 'success' code=None; all 81 tests in test_loginlog.py + test_login_capture_cross_seam.py + test_login_capture.py pass against the guarded copy; my test fails on the shipped fix (AssertionError at outcome=='failed') and passes guarded.

**Replacement code, as supplied:**

```python
# In parse(), replacing the whole nested adopt() — and its ONE call site changes from
    #     adopt(p, user, ts)
    # to
    #     adopt(p, user, ts, succeeded=v.group("verdict") == "succeeded")

    def adopt(p: _Pending, user: str, ts: datetime, succeeded: bool) -> None:
        """Give a fresh pending attempt the orphan cause that belongs to it, if one is waiting.

        An IDENTIFIED orphan (its evidence names a login) is taken only by that login's verdict —
        adopting by arrival order is how one person's diagnosis reached another. An UNIDENTIFIED
        orphan (a bind whose `found dn=` fell outside this read, so nothing ties its DN to a login)
        goes to the first verdict inside the window: refusing it would discard every cause on a
        directory whose DNs do not carry the login, which is a systematic loss, where the adjacency
        guess is only wrong in a sliced read that also interleaves two people inside one second.

        EXCEPT when the verdict creating this attempt is a SUCCESS — and at this call site the
        verdict IS known, because the pending is created by the verdict line itself. A bind failure
        cannot explain a login that succeeded, and conclude() suppresses whatever a success adopted,
        so taking the orphan here would have exactly one effect: it is destroyed, and the failure it
        genuinely belonged to concludes with no reason. Passed by instead, it is still in the list
        when its owner's verdict arrives inside the window. Only the unidentified path needs this:
        an identified orphan already refuses every verdict that its evidence does not name.
        """
        for i, o in enumerate(orphans):
            if not timedelta(0) <= ts - o["at"] <= ATTEMPT_WINDOW:
                continue
            if o["identified"]:
                if not _cause_mentions_user(o["evidence"], user):
                    continue
            elif succeeded:
                continue
            p.first_at = o["at"]
            p.saw_no_entries = o["no_entries"]
            p.bind_code = o["code"]
            p.bind_diagnostic = o["diagnostic"]
            del orphans[i]
            return
```

**Test, as supplied:**

```python
# Added to TestASuccessNeverBorrowsAnotherAttemptsCause in tests/test_loginlog.py.
# Verified: FAILS against the fix as shipped (sam.other == 'failed'), PASSES with the adopt guard.

    def test_a_success_does_not_destroy_the_orphan_a_later_failure_owns(self):
        """Suppressing the cause on the success row is half the guard: the adoption also DELETED the
        orphan, so the failure it belonged to concluded with no reason at the wrong instant."""
        # sam's bind error is unidentified (foreign DN, no `found dn=` in the read); jane's success
        # lands between it and sam's own verdict, all inside ATTEMPT_WINDOW.
        sam_bind = _restamp(
            WEB_LDAP_BADPW_BIND.replace("uid=jane.smith,ou=People", "cn=Sam Other,ou=People"),
            "2026-08-08T00:01:51.000000000Z")
        sam_verdict = _restamp(
            WEB_LDAP_BADPW_VERDICT.replace('"jane.smith"', '"sam.other"'),
            "2026-08-08T00:01:51.500000000Z")
        got = {a.user_name: a for a in parse([sam_bind, WEB_LDAP_OK_VERDICT, sam_verdict])}
        assert got["jane.smith"].outcome == loginlog.OUTCOME_SUCCESS
        assert got["jane.smith"].ldap_result_code is None
        assert got["sam.other"].outcome == loginlog.OUTCOME_BAD_PASSWORD, got["sam.other"]
        assert got["sam.other"].ldap_result_code == 49
        assert got["sam.other"].at == _at("2026-08-08T00:01:51.000000000Z")
```

### Arbiter

_Pending._

### LENS1-Q1-suppression-on-success — FIX_IS_CORRECT — low
**Claim.** gsd/loginlog.py:conclude — suppressing ldap_result_code and detail on a success is correct; the one real sequence where a success attempt carries its OWN bind error is a multi-LDAP-IdP chain, and that code is chain noise the parser already discards in every other form.
**Trigger.** Two LDAP identity providers, account exists in both with different passwords: ldap.go:148 found dn="uid=jane..." -> ldap.go:152 error binding ... LDAP Result Code 49 -> basicauth.go:48 failed for login "jane.smith" (ldap-1) -> basicauth.go:51 succeeded for login "jane.smith" (ldap-2).
**Consequence.** None false. The sequence exists and the fix does drop ldap-1's code 49 from the success row (measured: pre-fix row would carry code=49; post-fix code=None). But keeping it would preserve exactly the ambiguity defect B exploits: the row's provider field names only the decider (ldap-2), so a 49 beside outcome=success is unattributable and indistinguishable from a stranger's adopted failure; the field's own docstring says 'Only the bad-password path emits one'; and the parser already discards the chain's failures list on success. Search-bind failure cannot produce this (lookup fails -> login fails), htpasswd logs no bind error, and a user-bind failure within one provider cannot be followed by that provider succeeding.
**Evidence.** Probe Q1 (scratchpad/probe_lens1.py) with the four-line two-IdP sequence above: post-fix output 'jane.smith' 'success' code=None detail=None provider='ldap-2'. Grammar docstring (loginlog.py:21-38) shows all five measured cases — none has a bind error inside a success; ldap.go:152 fires only for the user-password bind after found dn (loginlog.py:189-194 comment + regex). LoginAttempt.ldap_result_code docstring at loginlog.py:217: 'Only the bad-password path emits one'. Reference cluster has one LDAP provider (docstring line 18), so the destroyed datum does not occur there at all.

### Arbiter

_Pending._

### LENS1-Q2-named_at-stamp — FIX_IS_CORRECT — low
**Claim.** gsd/loginlog.py:conclude — stamping a success at named_at changes nothing for any legitimate success on the measured grammar, and the expiry check still using first_at is unchanged by the diff, so which attempts conclude when is identical pre/post.
**Trigger.** n/a — verified absence of change: named_at != first_at only after adopt() (the sole first_at mutation besides construction, loginlog.py:382), and adopt runs only at the single construction site; a success with no adopted cause (every measured single-IdP shape — browser and CLI successes carry no cause lines) stamps identically to pre-fix.
**Consequence.** Nothing false. The stamp differs from pre-fix only when the success's pending adopted a cause — which was the defect being fixed (foreign cause) or the multi-IdP own-cause chain (measured probe Q2: at moves from the cause .150 to the first naming verdict .300, milliseconds, and becomes window-stable, which is the cross-seam dedup goal). The expiry loop at :396 (ts - p.first_at > ATTEMPT_WINDOW) is byte-identical pre/post (the diff touches only the _Pending field, the ctor, and conclude's output construction), so conclusion timing cannot have changed; probe Q2b's cause-anchored chain split (bad_password@.150 + success@1.400 when the chain spans >1s from the adopted cause) is the pre-existing expiry semantic, not a product of this fix. A succeeded pending is popped immediately, so its moved first_at never feeds the expiry loop.
**Evidence.** git diff local-development/gsd/loginlog.py shows exactly three hunks: the named_at field, `at=p.named_at if succeeded else p.first_at` + the two suppressions, and the ctor gaining named_at=ts — line 396 absent from the diff. grep -n first_at gsd/loginlog.py: set only at :408 (ctor) and :382 (adopt). Probes Q2/Q2b output above; full suite 1069 passed with every pre-existing stamp assertion intact.

### Arbiter

_Pending._

### LENS1-Q3-single-construction-site — FIX_IS_CORRECT — low
**Claim.** gsd/loginlog.py:_Pending — named_at is set at the one construction site and never mutated, and no second construction site should exist because only a verdict line ever creates a pending.
**Trigger.** n/a — structural proof by grep.
**Consequence.** None.
**Evidence.** grep -n named_at gsd/*.py tests/*.py => exactly loginlog.py:248 (field), :361 (read in conclude), :408 (ctor). grep -n '_Pending(' across gsd/ and tests/ => only :408. grep -n 'pending\[' => :408 (the sole assignment of a new entry) and :455/:457/:458/:459 (field mutation of an EXISTING entry on the direct cause-attach path). Cause lines that match nobody in flight append to `orphans` (:466) rather than constructing a pending — the browser-LDAP shape that starts at ldap.go:131 (docstring :48-50, fixture WEB_LDAP_SEARCHING path) is handled by the orphan list until login.go:183 names the user, at which point :408 constructs with named_at=ts, which is precisely 'the first line that NAMED this user'.

### Arbiter

_Pending._

### Technical debt (reviewer)

DEBT-ACCEPTED: on a multi-LDAP-IdP chain (not the reference cluster's shape) a success row no longer says which earlier directory refused the account before another accepted it — measured as code 49 dropped from the ldap-1/ldap-2 probe; the trade is documented in conclude()'s comment and keeps ldap_result_code true to its docstring. DEBT-ACCEPTED: a one-time upgrade-seam duplicate is possible — a success recorded pre-fix at a foreign cause's timestamp that is still inside the 60s overlap when the fixed code deploys will be re-recorded at named_at (different 'at' => different unique key); it affects only rows that were already wrong, and only for one overlap window. DEBT-INTRODUCED (pre-existing behavior made pointless rather than new, finding LENS1-Q4): success-side adoption is now output-inert but still deletes an unidentified orphan a real later failure owns, so the interleaved-stranger case concludes as 'failed / reported no reason' instead of bad_password@bind-ts — the adopt-time guard in the finding closes it and passed all 81 parser/capture tests. DEBT-AVOIDED: the fixes add no state outside parse() (named_at is per-pending, _not_clipped is a pure filter), so nothing new persists across cycles or replicas.

---

## Lens 2 — the logincapture.py _not_clipped guard
**Reviewer's summary.** Measured, not argued: (1) an exhaustive clip-boundary sweep — 12 realistic line sequences (CLI/browser grammars, OpenLDAP/AD, adoption chains stretched to found→bind 1s + bind→verdict 1s, interleaved strangers) sliced at every inter-line phase — produced 0 cases where an attempt kept by _not_clipped differed from the full parse on any persisted column, so the ATTEMPT_WINDOW bound holds (the guard needs only backward reach from `at`, which parse() caps at ATTEMPT_WINDOW even though an attempt's total influence span can reach 2x it); (2) stamping now AFTER the read does bound the kubelet's true boundary from above, and a real-capture_once multi-cycle simulation with an injected clock confirmed the steady-state accounting: 14/14 attempts recorded exactly once at 0.5s fetch latency; (3) but the same simulation refuted the accounting under latency — one slow fetch permanently lost a login that _recordable had withheld the previous cycle, with loss beginning at a measured 58.6s of single-fetch wall time, and the pre-fix control run recorded that same login — a NEW silent data-loss path; it is reachable because httpx's timeout caps the gap between chunks, not the transfer (measured: timeout=1.0 consumed a 3.14s dribble without raising), so the 15s config bounds nothing about total latency on a dribbling 8 MiB Debug log; (4) _recordable and _not_clipped are pure predicates on a.at and commute (500 random attempts, both orders identical). Net: the fix kills the duplicate-row defect completely and its declared loss cases are honest, but the "in the ordinary case that costs nothing" claim carries an undeclared assumption — fetch latency under ~58s — that nothing in the codebase enforces; the right-layer closure is a wall-clock budget on the streamed log read in kube.py, which lands slow reads on the existing cap-hit deferral path.

### L2-1-attempt-window-bound — FIX_IS_CORRECT — low
**Claim.** gsd/logincapture.py:_not_clipped — the ATTEMPT_WINDOW bound on the leading edge is sufficient: no clipped read can produce a surviving attempt that disagrees with the full parse.
**Trigger.** Any read window boundary falling inside an attempt's line group, including the worst constructible case: found dn= at t0, adopted bind cause at t0+1s (= the attempt's `at`), verdict at t0+2s — backward reach from `at` is exactly ATTEMPT_WINDOW and the guard's strict `>` drops the equality case.
**Consequence.** None — confirmed correct. Note for the author: the docstring sentence 'An attempt's lines span at most ATTEMPT_WINDOW' is literally false (total influence span reaches 2x ATTEMPT_WINDOW via found->bind->verdict chains, since parse() expiry runs from the adopted first_at while the found line sits up to 1s before it); the guard is right anyway because only backward reach from `at` matters, and that is capped at ATTEMPT_WINDOW by the found/orphan expiry rules at loginlog.py:396-400.
**Evidence.** scratchpad/q1_boundary_sweep.py against the worktree gsd (PYTHONPATH forced; gsd.__file__ verified in wt-crossseam): 12 sequences x all inter-line cut phases (0.25/0.5/0.75 fractions plus +-1e-6 epsilons), every survivor of _not_clipped(parse(clipped), ws) compared to the full parse on (user, outcome, at, provider, code, detail). Output: '21 surviving attempts checked across all sequences/cuts, 0 leaks'. The 'AD cause-first max stretch: found->bind 1s, bind->verdict 1s' sequence exercised the exact boundary.

### Arbiter

_Pending._

### L2-2-stamp-after-direction — FIX_IS_CORRECT — low
**Claim.** gsd/logincapture.py:capture_once — stamping datetime.now(UTC) after fetch_pod_log returns (line 231) bounds the kubelet's true window boundary from above, which is the safe direction for the duplicate defect.
**Trigger.** true_boundary = kubelet_receive - since, and receive <= now2 always, so derived edge >= true edge: nothing clipped by the kubelet can survive the guard. Stamping BEFORE the request would under-shoot by up to one connect+request latency and re-open the duplicate.
**Consequence.** None for correctness of the direction. The cost of erring late is real but bounded: attempts in (true_edge+1s, derived_edge+1s] are dropped though fully parsed; the multi-cycle simulation showed this band is harmless (already recorded a cycle earlier) up to a measured 58.4s of fetch latency, and harmful from 58.6s — see finding L2-3, which is where that band crosses into never-recorded territory. One premise worth naming: 'derived >= true' assumes the local and kubelet clocks agree; a kubelet clock ahead of local by more than one response-transfer time would re-open the duplicate leak. That trust is pre-existing — _recordable and _settle_horizon already compare kubelet stamps to local now — not introduced here.
**Evidence.** Read gsd/logincapture.py:213-232 (stamp after fetch, comment states the kubelet-receive premise) and kube.py:477-481 (httpx.Client(timeout=self._timeout)). Simulation threshold sweep output: 'latency 0.1/15/30/45/55/57/58/58.4 -> victim recorded: True; 58.6/60/65 -> False'. Steady-state run: 'A: 14 attempts, 14 rows, missing=[], duplicated=[]'.

### Arbiter

_Pending._

### L2-3-slow-read-permanent-loss — FIX_INTRODUCES_DEFECT — low
**Claim.** gsd/logincapture.py:_not_clipped + capture_once — one log fetch whose wall-clock exceeds ~58.5s makes the guard permanently drop a login that _recordable withheld the previous cycle and that NO cycle ever recorded; the docstring's accounting ('in the ordinary case that costs nothing', losses only at first sight and restart) omits this case, and the pre-fix code recorded the same login.
**Trigger.** Cycle P: attempt at `a` with now_P-31 < a <= now_P-30 is withheld by _recordable while the settle horizon advances the watermark to wm ~ now_P-30 (>= a). Cycle P+1: the kubelet resolves since = age+60 at receive time and RETURNS the attempt's lines complete, but the response body takes >58.5s to stream (httpx timeout=15.0 caps only the gap between chunks — measured: timeout=1.0 consumed a 3.14s dribble without raising; an 8 MiB Debug log at <~140 KiB/s sustained qualifies); window_start is stamped after the body, so edge = wm-59+L >= a and the fully-parsed attempt is dropped. The watermark meanwhile advances ~L+30s past it, so cycle P+2's window no longer reaches `a`. Reproduced end-to-end against the real capture_once and Store.
**Consequence.** A named person's login attempt vanishes from the durable record with no trace — the dashboard says nobody logged in at that instant when someone did, in the module whose stated purpose is that a row, once seen, is kept. Before this fix the identical sequence recorded the row (the slow read clips nothing; the guard alone rejects it). Rare — needs one >58.5s dribbling fetch AND a login inside a ~(L-58.5)s sliver of the withheld band — but silent and permanent, and 'dropped for good' here is NOT one of the two loss cases the docstring declares.
**Evidence.** scratchpad/q34_cycle_sim.py: real capture_once + real Store, clock injected via sys.modules['datetime'] shim (the gsd functions re-import datetime inside their bodies), fake client slicing by since_seconds at fetch time then advancing the clock by the latency. Output: 'B slow-fetch (guard ON): []' vs 'B slow-fetch (guard disabled = pre-fix): [(victim, failed, ...T16:14:49.500000Z)]'. Threshold sweep: recorded through 58.4s, lost from 58.6s. httpx semantics measured with a local socket server: 'timeout=1.0, total wall time 3.14s, got 40 bytes, no timeout raised'. Composition order (the other half of lens Q4) measured immaterial: '_not_clipped(_recordable(x)) == _recordable(_not_clipped(x))' over 500 random attempts -> 'orders agree: True'. kube.py:731-743 streams with no wall-clock bound; config.py:222,460 shows requestTimeoutSeconds is a plain float with no clamp.

**Replacement code, as supplied:**

```python
# gsd/kube.py — add `import time` to the module imports, add this constant near the other
# module constants, and replace fetch_pod_log with the version below. This closes the loss at
# its true layer: the guard's overshoot equals the fetch's wall-clock latency, so bounding the
# fetch bounds the overshoot for every consumer, and a read the budget interrupts lands on the
# byte-cap path that already defers instead of losing.

# One pod-log read's wall-clock budget. The httpx timeout on _client caps the SILENCE between
# chunks, not the transfer, so a stream dripping just under it can run for minutes (measured:
# a timeout=1.0 client consumed a 3.1s dribble without raising). logincapture stamps the clock
# behind its leading-edge guard AFTER this returns, and its no-loss accounting holds only while
# that stamp lags the kubelet's window resolution by less than OVERLAP_SECONDS minus the settle
# margin — loss measured from ~58.5s of latency with the shipped constants. Twenty seconds keeps
# the overshoot far inside that, and a read this interrupts is deferred, not lost: the truncation
# path keeps the oldest lines and the watermark machinery re-reads the rest next cycle.
LOG_READ_BUDGET_SECONDS = 20.0


def fetch_pod_log(
    self,
    namespace: str,
    pod_name: str,
    since_seconds: int | None = None,
    max_bytes: int = 8 * 1024 * 1024,
) -> list[str] | None:
    """Timestamped log lines for one pod, or None when this pod cannot be read right now.

    NOT THROUGH `_get()`, and that is mandatory rather than stylistic: `_get` always calls
    `response.json()`, and this endpoint returns TEXT. `_client()` IS used — it only supplies the
    bearer token and CA verification, which this needs exactly as much as any other call.

    STREAMED, AND BYTE-BOUNDED — in BYTES, counted before any line is assembled. The previous
    draft counted characters of lines `iter_lines()` had already buffered whole, so a single
    line larger than the cap was held in memory before it could be measured, and a multi-byte
    log undercounted. Stopping at the cap also ends the transfer instead of paying for lines
    that would be discarded.

    A CAP HIT KEEPS THE OLDEST LINES OF THE WINDOW, deliberately. The kubelet streams oldest
    first, and oldest-first is the direction the watermark machinery REQUIRES: the cursor only
    advances through lines actually returned, so the deferred newest lines fall inside the next
    cycle's window and nothing is lost — only late. Keeping the newest instead would let the
    cursor advance past everything the cap displaced and silently drop it forever; recency is
    what the next cycle gets back anyway, completeness is not. (An earlier comment here claimed
    the newest lines were kept; it described the opposite of what the code did.) The line the
    cap cuts in half is dropped for the same reason: a truncated diagnostic can mis-parse — a
    bind error losing its `data` sub-code reads as a plain wrong password — and the whole line
    is inside the next cycle's overlap.

    BOUNDED IN WALL-CLOCK TIME as well, and on the same path as the cap. The client's timeout
    only caps the gap between chunks, so it bounds nothing about the whole transfer — and the
    capture loop derives its leading-edge guard from a clock stamped AFTER this returns, so
    every second spent here widens the band of attempts that guard throws away for good. See
    LOG_READ_BUDGET_SECONDS for the measured threshold where that band reaches rows no cycle
    ever recorded.

    `timestamps=true` is what makes the result usable at all — it prefixes each line with the
    kubelet's RFC3339 UTC stamp. klog's own stamp carries no year and no timezone.

    RETURNS None FOR THE ORDINARY ROLL, RAISES FOR THE REST, and the distinction is the point:

      404              the pod went away between listing and reading. Every roll does this.
      400 not-ready    the container has not started, so there is no log yet. Measured message:
                       "container nope is not valid for pod ..." — reason BadRequest.
      403              the grant is missing. LOGGED AT WARNING, because it is permanent and will
                       not fix itself, and a silent None here looks identical to "nobody logged
                       in" forever.
      any other        raised, so a real outage is not mistaken for roll noise.
    """
    params: dict[str, Any] = {"timestamps": "true"}
    if since_seconds is not None:
        params["sinceSeconds"] = str(since_seconds)
    path = f"{POD_API_TMPL % namespace}/{pod_name}/log"

    chunks: list[bytes] = []
    size = 0
    truncated = False
    over_budget = False
    started = time.monotonic()
    try:
        with self._client() as client:
            with client.stream("GET", path, params=params) as response:
                if response.status_code >= 400:
                    response.read()
                    return self._log_read_refused(response, namespace, pod_name)
                for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max(1, max_bytes))):
                    if time.monotonic() - started > LOG_READ_BUDGET_SECONDS:
                        # Checked before the chunk is kept: a chunk that arrived past the budget
                        # proves the transfer is the slow kind, and keeping it would end the
                        # batch mid-line anyway — the pop below drops the tail either way.
                        truncated = over_budget = True
                        break
                    room = max_bytes - size
                    if len(chunk) >= room:
                        chunks.append(chunk[:room])
                        size = max_bytes
                        truncated = True
                        break
                    chunks.append(chunk)
                    size += len(chunk)
    except httpx.HTTPError as exc:
        # A connect error or timeout reading ONE pod must not fail the cycle: the other pods still
        # have lines, and this one is retried next time from the same watermark.
        log.info("%s: could not read %s log (%s: %s)",
                 self.cluster.name, pod_name, type(exc).__name__, exc)
        return None

    # errors="replace" cannot corrupt a kept line: the only place a multi-byte character can be
    # split is the cap boundary, and the line holding it is popped below.
    lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
    if truncated:
        if lines:
            lines.pop()
        if over_budget:
            log.info(
                "%s: %s log read exceeded its %.0fs budget after %d lines; the OLDEST lines of "
                "this window are kept, and the rest fall inside the next cycle's window once the "
                "watermark has advanced",
                self.cluster.name, pod_name, LOG_READ_BUDGET_SECONDS, len(lines),
            )
        else:
            log.info(
                "%s: %s log hit the %d-byte cap after %d lines; the OLDEST lines of this window "
                "are kept, and the rest fall inside the next cycle's window once the watermark "
                "has advanced",
                self.cluster.name, pod_name, max_bytes, len(lines),
            )
    return lines
```

**Test, as supplied:**

```python
# tests/test_kube_reader.py — alongside the existing cap tests, using its Chunks/_client_for
# helpers. Fails on the worktree code (no budget: all lines returned, nothing logged) and
# passes with the replacement.


def test_a_read_that_outlives_its_budget_is_cut_like_a_cap_hit(monkeypatch, caplog):
    """The httpx timeout caps the gap BETWEEN chunks, not the transfer, so a stream dripping
    just under it can run for minutes — and the capture loop stamps the clock behind its
    leading-edge guard after this returns, so past ~58.5s of read latency (measured) that
    guard permanently drops logins nothing ever recorded. A read the budget interrupts must
    land on the cap-hit path: oldest lines kept, the half-read tail deferred, said out loud."""
    import types

    from gsd import kube

    # One tick for the start stamp, one per chunk; the second chunk lands past the budget.
    # The last value repeats so an extra clock read cannot exhaust the fake.
    ticks = [0.0, 5.0, kube.LOG_READ_BUDGET_SECONDS + 30.0]
    monkeypatch.setattr(
        kube, "time",
        types.SimpleNamespace(monotonic=lambda: ticks.pop(0) if len(ticks) > 1 else ticks[0]))
    stream = Chunks([b"kept-1\nkept-2\n", b"late-and-untrusted\n"])
    client = _client_for(monkeypatch, stream)
    with caplog.at_level(logging.INFO):
        got = client.fetch_pod_log("ns", "pod")
    assert got == ["kept-1"], got          # the kept batch's own tail may be half a line: popped
    assert stream.yielded < 2 or got == ["kept-1"], "the read continued past the budget"
    assert "budget" in caplog.text
```

### Arbiter

_Pending._

### Technical debt (reviewer)

DEBT-AVOIDED: the fix removed the duplicate-row debt completely — the boundary sweep found zero cases where a clipped read can seat a second, contradictory row beside a recorded one, and the 11 new tests pin both the parser premise and the loop seam, so this class of defect cannot silently return. DEBT-ACCEPTED (declared): the guard converts deferral into permanent drop at the window's leading edge, and the docstring names two loss cases (first sight's hour boundary, a restart landing within a second of a withheld attempt) as the absent-beats-false trade; those are honest and the steady-state simulation confirms they cost nothing at ordinary latency. DEBT-INTRODUCED (undeclared, the finding): the no-loss accounting rests on an unstated invariant — single-fetch wall-clock latency < OVERLAP_SECONDS − SETTLE_SECONDS − ATTEMPT_WINDOW (~58.5s measured) — that no code enforces and httpx's per-chunk timeout semantics do not provide; until the read is wall-clock-bounded (the proposed LOG_READ_BUDGET_SECONDS), a dribbling log read silently and permanently loses any login sitting in the previous cycle's withheld band. Related latent debt worth an assert or a comment tying the constants together: the safety margin is a pure arithmetic relationship between OVERLAP_SECONDS, SETTLE_SECONDS and ATTEMPT_WINDOW — anyone tuning OVERLAP_SECONDS down toward 32 collapses the loss threshold toward zero and every cycle starts bleeding rows, with nothing in the test suite positioned to notice.

---

## Lens 3 — what both fixes do not address
**Reviewer's summary.** Measured in the worktree (gsd resolves to wt-crossseam, suite 1069 passed / 1 skipped): the two fixes hold for their stated targets, but the same two defect classes — one login stored as two rows, and a stored row asserting something false about a named person — survive through four other doors in the same seam, each reproduced with a script against the real parse()/capture_once()/fetch_pod_log()/Store objects. (1) parse() expires a pending attempt on age-since-FIRST-line, so any login whose lines span more than ATTEMPT_WINDOW=1s (slow directory bind, 3-provider chain) is concluded twice — measured as a fabricated ('jane.smith','failed') row beside the real ('jane.smith','success'), mid-log where neither _recordable nor _not_clipped can see it. (2) The 8 MiB byte cap in fetch_pod_log is a third read seam with no guard: an attempt straddling the cap parses half in cycle 1 and whole in cycle 2 — measured end-to-end through the real cap logic and real SQLite store as ('jane.smith','failed') + ('jane.smith','success') for one successful login. (3) adopt() hands unidentified orphan causes out in arrival order: with two waiting bind errors and verdicts returning in the other order, the codes CROSS — measured bob recorded bad_password with alice's code 49 and alice recorded password_expired with bob's 53. (4) found{} keeps ONE entry per DN, so two logins resolving the same directory entry inside a window trade evidence, and the blind bind_code overwrite then records one named person's expired password (AD data 532) as a wrong one (data 52e) — measured. All four replacement fixes were applied to a scratch copy and validated: the 5 new regression tests fail on the worktree code and pass on the fixed copy; all 124 seam tests and the full suite pass on the fixed copy (1247 passed; the only 2 failures are tests/test_docs_citations.py rglobbing parents[2] of the scratch location and tripping on unrelated scratchpad *.md artifacts — environmental). Probed and found clean: _cause_mentions_user's boundaries (bob/bobby, dotted suffix, group-name-as-username, '='/',' in usernames — no wrong-person match; an escaped-comma DN loses its cause, which is the documented absent-beats-false trade), and provider-outside-the-UNIQUE-key (measured INSERT 1 then 0, first writer wins; after the two fixes the only same-(user,at,outcome) pair one pod can produce is a re-read of the same fully-parsed attempt, where parse is deterministic, so the collapse is safe). Also verified the idle-expiry replacement does not weaken the shipped guards: a chained attempt clipped at the leading edge still dies in _not_clipped (measured, survives=[]), because any unseen line of one attempt is within ATTEMPT_WINDOW of a visible one. Artifacts: /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/325dfd2f-469e-4bd4-b279-331704911184/scratchpad/attack{1,2,3,5}*.py and scratchpad/fixcheck/ (validated fixed copy + tests).

### LENS3-1 — PRE_EXISTING_DEFECT_MISSED — high
**Claim.** local-development/gsd/loginlog.py:parse() — the expiry loop (`ts - p.first_at > ATTEMPT_WINDOW`, line 396) concludes a still-running attempt mid-flight, so one login whose lines span more than 1s becomes two stored rows, including a fabricated `failed` row beside a real `success`; this is defect (A)'s class alive mid-log, where neither _recordable nor _not_clipped applies. The window's own docstring claims 'three orders of magnitude of headroom' over the measured 30-125 ms, but 125 ms to 1 s is 8x, and a directory under ppolicy/AD lockout delay or plain load crosses it.
**Trigger.** Any attempt whose lines span > ATTEMPT_WINDOW: (a) htpasswd chain-noise `failed` at T0, LDAP success verdict at T0+1.1s — recorded as failed AND success; (b) three providers at 600 ms each — two `failed` rows; (c) slow bind (1.2s) before a bad-password verdict — `failed` plus `bad_password`.
**Consequence.** The dashboard shows a failed login that never happened for a named person — a break-glass or governed account appears to have failed authentication at an instant when it actually succeeded — and every slow-directory login is double-counted. `at` and `outcome` both differ between the halves, so UNIQUE(cluster_id, pod_name, user_name, at, outcome) can never collapse them.
**Evidence.** scratchpad/attack2_slow_attempt.py against the worktree: Case C printed LoginAttempt(user_name='jane.smith', outcome='failed', at=12:00:00, provider='developer', detail="provider 'developer' reported no reason") AND LoginAttempt(user_name='jane.smith', outcome='success', at=12:00:01.100000) for ONE login (lines: failed "developer" at T0, succeeded "ldap-local" at T0+1.1s). Case B (three providers, 600 ms apart) printed two 'failed' rows. After replacing the expiry with `ts - p.last_at`, Case B is one row (provider='ldap-b'); tests/test_lens3_regressions.py::TestASlowProviderChainStaysOneAttempt fails on the worktree ('one login's provider chain became 2 rows') and passes on the fixed copy; full suite on the fixed copy: 1247 passed. Leading-edge guard re-verified under the new semantics: a chained attempt clipped at window_start had its half-parse dropped by _not_clipped (printed 'survives _not_clipped: []').

**Replacement code, as supplied:**

```python
# Complete replacement for parse() in gsd/loginlog.py. This one function also carries the
# corrections for findings LENS3-3 (adopt) and LENS3-4 (found-slot) — the three defects share it.
# RESIDUAL, measured and deliberate: a single SILENT gap wider than ATTEMPT_WINDOW inside one
# attempt (a bind that takes >1s to answer, cases A/C in the evidence) still splits, because no
# line arrives to keep the attempt alive; closing that means revisiting ATTEMPT_WINDOW itself,
# which changes the two-humans-one-account guarantee and is a separate decision.
def parse(lines: list[str] | str) -> list[LoginAttempt]:
    """Every login attempt in these lines, oldest first.

    Correlates by username within ATTEMPT_WINDOW: the provider-order noise means one attempt spans
    several lines, and a `failed` for the same person can be part of a SUCCESS. An attempt is concluded
    when a verdict arrives for a provider after the deciding one, when the window expires, or at the end
    of the input.

    CAUSE LINES NAME NO USER, so attribution is by evidence with a narrow adjacency fallback, never by
    recency between two people: under interleaving, "the most recent attempt" assigned one person's
    directory diagnosis to another, and a false cause is worse than the provider's honest no-reason
    result. The evidence is the cause's own text plus the `found dn=` line that resolved its bind DN —
    the latter because an Active Directory DN (`CN=Jane Smith,...`) never repeats the login (`jsmith`),
    and requiring the cause itself to name the user would silently discard every AD cause.

    Lines with no kubelet timestamp are skipped rather than guessed at — a record whose instant is
    invented is worse than one that is absent.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()

    pending: dict[str, _Pending] = {}
    out: list[LoginAttempt] = []
    # A cause can arrive BEFORE any line names its user, and on a cluster whose only identity provider
    # is LDAP it always does — the attempt starts at `ldap.go:131 searching`, so nothing has created a
    # pending entry yet. That is the ordinary production shape, not an edge case: this cluster only
    # gets a username first because htpasswd is tried before ldap and logs a failure. Dropping these
    # would lose every cause on a single-provider cluster, including expired passwords. A LIST, not a
    # slot: an identified orphan waits for the verdict that names its person, so an interleaved
    # stranger's verdict must be able to pass it by without destroying it.
    orphans: list[dict] = []
    # Recent `found dn=` lines by DN, kept one window: the bind error that follows quotes the DN, and
    # this is what lets it be attributed on a directory whose DNs do not contain the login. A LIST
    # per DN, not a slot: two logins can resolve the SAME entry inside one window (sAMAccountName and
    # userPrincipalName both name it on AD), and a slot silently rewrote the first login's tie to the
    # DN with the second's — every bind error for that DN then read as the second person's.
    found: dict[str, list[dict]] = {}

    def conclude(user: str) -> None:
        p = pending.pop(user, None)
        if p is None:
            return
        if p.succeeded:
            outcome = OUTCOME_SUCCESS
        elif p.bind_code is not None:
            outcome = _classify_bind(p.bind_code, p.bind_diagnostic)
        elif p.saw_no_entries:
            outcome = OUTCOME_REJECTED
        elif p.failures:
            outcome = OUTCOME_FAILED
        else:
            # Progress lines only, no verdict — nothing happened worth recording.
            return
        # A BIND FAILURE CANNOT EXPLAIN A LOGIN THAT SUCCEEDED. `adopt` attaches an unidentified cause
        # on adjacency alone, necessarily before any outcome is known, so a stranger's wrong password
        # one second earlier could reach a success — measured as `jane.smith / success` carrying
        # `ldap_result_code=49, detail="LDAP result code 49"`, three false claims on the one row a
        # reader trusts most. It also dragged her stamp back onto that foreign cause, which is a second
        # way for one login to become two rows: `at` is in the dedup key, so the same success read with
        # and without the cause in window does not collapse. On a success the cause is dropped and the
        # stamp comes from the line that named her.
        succeeded = outcome == OUTCOME_SUCCESS
        out.append(LoginAttempt(
            user_name=user,
            outcome=outcome,
            at=p.named_at if succeeded else p.first_at,
            provider=p.provider,
            ldap_result_code=None if succeeded else p.bind_code,
            detail=None if succeeded else _detail(p, outcome),
        ))

    def adopt(p: _Pending, user: str, ts: datetime) -> None:
        """Give a fresh pending attempt the orphan cause that belongs to it, if one is waiting.

        An IDENTIFIED orphan (its evidence names a login) is taken only by that login's verdict —
        adopting by arrival order is how one person's diagnosis reached another. An UNIDENTIFIED
        orphan (a bind whose `found dn=` fell outside this read, so nothing ties its DN to a login)
        goes to the first verdict inside the window ONLY WHEN IT IS ALONE: refusing the lone one
        would discard every cause on a directory whose DNs do not carry the login, which is a
        systematic loss, and adjacency to a single cause is only wrong when a stranger's verdict
        beats the owner's to it. With TWO unidentified causes waiting, arrival order is the only
        tiebreak left, and it is exactly wrong whenever the directory answers out of order —
        measured as two strangers' bind codes swapped, an expired password recorded as somebody
        else's wrong one. Two waiting causes with no evidence have no honest owner; both verdicts
        degrade to the provider's own result, which is true.
        """
        def take(i: int) -> None:
            o = orphans.pop(i)
            p.first_at = o["at"]
            p.saw_no_entries = o["no_entries"]
            p.bind_code = o["code"]
            p.bind_diagnostic = o["diagnostic"]

        in_window = [(i, o) for i, o in enumerate(orphans)
                     if timedelta(0) <= ts - o["at"] <= ATTEMPT_WINDOW]
        # Evidence outranks adjacency: a cause that NAMES this login wins even when an
        # unidentified one arrived first.
        for i, o in in_window:
            if o["identified"] and _cause_mentions_user(o["evidence"], user):
                take(i)
                return
        unidentified = [i for i, o in in_window if not o["identified"]]
        if len(unidentified) == 1:
            take(unidentified[0])

    for raw in lines:
        ts = parse_timestamp(raw)
        if ts is None:
            continue

        # Expire anything that has gone QUIET for a window, so a long-running read does not merge two
        # attempts by the same person minutes apart — and so stale correlation state cannot leak
        # forward. Quiet since the LAST line, not old since the first: two attempts are separated by
        # silence, while one slow attempt is separated by nothing — a provider chain whose directory
        # answers slowly can stretch a single login past any fixed span, and expiring it mid-flight
        # concluded the chain noise as its own `failed` row beside the real outcome.
        for user in [u for u, p in pending.items() if ts - p.last_at > ATTEMPT_WINDOW]:
            conclude(user)
        orphans[:] = [o for o in orphans if ts - o["at"] <= ATTEMPT_WINDOW]
        for dn in list(found):
            found[dn] = [f for f in found[dn] if ts - f["at"] <= ATTEMPT_WINDOW]
            if not found[dn]:
                del found[dn]

        v = _VERDICT.search(raw)
        if v:
            user = v.group("user")
            provider = v.group("provider")
            p = pending.get(user)
            if p is None:
                p = pending[user] = _Pending(first_at=ts, last_at=ts, named_at=ts)
                adopt(p, user, ts)
            p.last_at = ts
            if v.group("verdict") == "succeeded":
                p.succeeded = True
                p.provider = provider
                conclude(user)          # a success ends the attempt; nothing after it can change it
            else:
                p.failures.append(provider)
                # The provider that decided a FAILURE is the last one to reject, so this is overwritten
                # deliberately as later providers are tried.
                p.provider = provider
            continue

        f = _FOUND.search(raw)
        if f:
            found.setdefault(f.group("dn"), []).append({"at": ts, "raw": raw})
            continue

        no_entries = bool(_NO_ENTRIES.search(raw))
        b = None if no_entries else _BIND_ERROR.search(raw)
        if not no_entries and b is None:
            continue

        # What this cause can prove about WHO it belongs to. `no entries matching` quotes the search
        # filter, which embeds the typed login on every directory. A bind error only quotes the DN, so
        # it is identifying evidence only together with the `found dn=` line that resolved it — and
        # only when that line is UNIQUE: two logins resolving this DN inside one window mean the bind
        # errors that follow cannot be told apart by their own text, and attributing either is a coin
        # flip between named humans. Dropped, the same trade as everywhere else here.
        evidence = raw
        identified = no_entries
        if b is not None:
            ctxs = found.get(b.group("dn"), [])
            if len(ctxs) > 1:
                continue
            if ctxs:
                evidence = f'{raw} {ctxs[0]["raw"]}'
                identified = True

        mentioned = [u for u in pending if _cause_mentions_user(evidence, u)]
        if len(mentioned) == 1:
            target = mentioned[0]
        elif not mentioned and not identified and len(pending) == 1:
            # A bind whose found line fell outside this read window: adjacency is the only evidence
            # left, and with exactly one attempt in flight it is sound.
            target = next(iter(pending))
        else:
            target = None

        if target is not None:
            if no_entries:
                pending[target].saw_no_entries = True
            else:
                pending[target].bind_code = int(b.group("code"))
                pending[target].bind_diagnostic = b.group("diagnostic") or ""
            pending[target].last_at = ts
        elif len(mentioned) > 1:
            # One cause naming two in-flight logins has no honest owner. Dropping it degrades both
            # to the provider's own verdict, which is true; guessing would make one of them false.
            pass
        elif identified or not pending:
            # Held for the verdict that names this person — see `orphans` above.
            orphans.append({
                "at": ts,
                "evidence": evidence,
                "identified": identified,
                "no_entries": no_entries,
                "code": None if b is None else int(b.group("code")),
                "diagnostic": "" if b is None else (b.group("diagnostic") or ""),
            })
        # An unidentified cause with SEVERAL people in flight is dropped: any attachment would be a
        # guess between named humans, and the guess is exactly the defect this branch replaced.

    for user in list(pending):
        conclude(user)

    out.sort(key=lambda a: (a.at, a.user_name))
    return out
```

**Test, as supplied:**

```python
class TestASlowProviderChainStaysOneAttempt:
    """Expiring on age-since-FIRST-line split any attempt spanning over ATTEMPT_WINDOW in two rows."""

    def test_a_chain_of_slow_providers_is_one_failure_not_two(self):
        # Three providers at 600ms each: no single gap beats the window, but the span does.
        lines = [
            '2026-08-08T11:00:00.000000Z E0808 11:00:00.000000       1 basicauth.go:48] Login with provider "developer" failed for login "jane.smith"',
            '2026-08-08T11:00:00.600000Z E0808 11:00:00.600000       1 basicauth.go:48] Login with provider "ldap-a" failed for login "jane.smith"',
            '2026-08-08T11:00:01.200000Z E0808 11:00:01.200000       1 basicauth.go:48] Login with provider "ldap-b" failed for login "jane.smith"',
        ]
        got = parse(lines)
        assert len(got) == 1, f"one login's provider chain became {len(got)} rows: {got}"
        # The provider that decided it is the LAST one tried, same as the fast-chain rule.
        assert got[0].provider == "ldap-b"

    def test_two_attempts_separated_by_silence_stay_two(self):
        # The guarantee the expiry exists for: same account, minutes apart, never merged.
        lines = [
            '2026-08-08T11:00:00.000000Z E0808 11:00:00.000000       1 login.go:183] Login with provider "developer" failed for "jane.smith"',
            '2026-08-08T11:02:00.000000Z E0808 11:02:00.000000       1 login.go:191] Login with provider "developer" succeeded for "jane.smith": &groupmapper...',
        ]
        got = parse(lines)
        assert [a.outcome for a in got] == [loginlog.OUTCOME_FAILED, loginlog.OUTCOME_SUCCESS], got
```

### Arbiter

_Pending._

### LENS3-2 — PRE_EXISTING_DEFECT_MISSED — medium
**Claim.** local-development/gsd/kube.py:fetch_pod_log() — the byte cap (line 737, `if len(chunk) >= room`) is a THIRD read seam with no guard: an attempt straddling the cap byte is returned half (its head), parsed to a false conclusion, recorded, and then recorded AGAIN whole when the next cycle's overlap re-reads it. _recordable cannot see it (a capped backlog's attempts are minutes old) and _not_clipped cannot (they are nowhere near the leading edge). Distinct from the known-agreed exact-cap final-line drop.
**Trigger.** A read that hits the 8 MiB cap with an attempt's lines astride the cut — most likely a first-sight/backlog read (3600s window) at Debug verbosity. Cycle 1 returns the htpasswd chain-noise `failed` line, cuts the `succeeded` line; cycle 2's overlap returns both.
**Consequence.** One successful login is stored as BOTH ('jane.smith','failed') and ('jane.smith','success') — the dashboard asserts a failed login that never happened for a named person, and outcome is in the UNIQUE key so the pair never collapses.
**Evidence.** scratchpad/attack5_cap_straddle.py — real ClusterClient cap logic over httpx.MockTransport, real capture_once, real SQLite Store; cap set between the two lines of a success attempt placed 600s in the past. Output: cycle1 recorded: 1 ... cycle2 recorded: 1 ... ('jane.smith', 'success', ...) AND ('jane.smith', 'failed', ...). With the replacement applied (scratchpad/fixcheck): cycle1 recorded: 0, watermark: {}, cycle2 recorded: 1, single ('jane.smith','success') row. tests/test_cap_straddle.py::test_an_attempt_straddling_the_cap_is_deferred_not_half_parsed fails on the worktree ('the half of a straddling attempt was returned for parsing') and passes on the fixed copy; the companion test pins that lines behind a quiet window survive. All existing test_kube_reader.py tests still pass (their cap fixtures carry no kubelet stamps, and the guard leaves unstamped lines alone).

**Replacement code, as supplied:**

```python
# gsd/kube.py. Requires `from datetime import timedelta` added to the module imports.
# New module-level constant + helper (place above `class ClusterClient`), and fetch_pod_log's
# truncation branch gains one call — the complete method follows the helper.

# How much log time _drop_capped_tail may discard hunting for silence. Five windows is far past any
# attempt the grammar has measured (30-125 ms of lines) while keeping the worst case — a pod with no
# quiet second anywhere — to a bounded deferral instead of an empty read that stalls the watermark.
_CAP_TAIL_LIMIT = timedelta(seconds=5)


def _drop_capped_tail(lines: list[str]) -> list[str]:
    """The kept lines of a capped read, minus any tail the cap may have severed mid-attempt.

    The cap lands on a BYTE, not on an attempt boundary: whatever attempt was mid-flight at the cut
    has its head inside this read and its verdict beyond it, and a parse of the head alone concludes
    honestly on partial evidence — measured end to end as one successful login stored twice, `failed`
    from the capped read and `success` when the next cycle's overlap returned the whole attempt.
    Neither settle guard can see it: an attempt deep in a capped backlog is minutes old (past
    `_recordable`) and nowhere near the window's leading edge (past `_not_clipped`). So the cut gets
    the same treatment as the leading edge, applied HERE because only this function knows a cut
    happened: walk back from the cut until a full ATTEMPT_WINDOW of silence separates kept from
    dropped — no attempt's lines can span that silence, so nothing kept can continue past it. The
    dropped tail is deferred, not lost: the watermark stops at the newest KEPT line and the next
    cycle's overlap re-reads from behind it.

    Bounded at _CAP_TAIL_LIMIT of log time so a pod that logs continuously — no window of silence
    anywhere — cannot turn this into an empty read forever: the watermark would never advance and
    capture would stall, which is worse than the sliver of risk the bound leaves (an attempt whose
    lines span the whole limit is not a login shape the grammar produces). Lines with no kubelet
    stamp carry nothing the parser reads, so they follow their timestamped neighbours.
    """
    from .loginlog import ATTEMPT_WINDOW, parse_timestamp
    newest = None
    cut_at = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        ts = parse_timestamp(lines[i])
        if ts is None:
            continue
        if newest is None:
            newest = ts
        elif newest - ts > _CAP_TAIL_LIMIT:
            break
        prior = parse_timestamp(lines[i - 1]) if i else None
        if prior is not None and ts - prior > ATTEMPT_WINDOW:
            cut_at = i
            break
        cut_at = i
    if newest is None:
        return lines                      # nothing timestamped, nothing the parser will read anyway
    return lines[:cut_at]


# Complete replacement for ClusterClient.fetch_pod_log — the only change from the shipped version
# is the _drop_capped_tail call in the truncation branch.
    def fetch_pod_log(
        self,
        namespace: str,
        pod_name: str,
        since_seconds: int | None = None,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> list[str] | None:
        """Timestamped log lines for one pod, or None when this pod cannot be read right now.

        NOT THROUGH `_get()`, and that is mandatory rather than stylistic: `_get` always calls
        `response.json()`, and this endpoint returns TEXT. `_client()` IS used — it only supplies the
        bearer token and CA verification, which this needs exactly as much as any other call.

        STREAMED, AND BYTE-BOUNDED — in BYTES, counted before any line is assembled. The previous
        draft counted characters of lines `iter_lines()` had already buffered whole, so a single
        line larger than the cap was held in memory before it could be measured, and a multi-byte
        log undercounted. Stopping at the cap also ends the transfer instead of paying for lines
        that would be discarded.

        A CAP HIT KEEPS THE OLDEST LINES OF THE WINDOW, deliberately. The kubelet streams oldest
        first, and oldest-first is the direction the watermark machinery REQUIRES: the cursor only
        advances through lines actually returned, so the deferred newest lines fall inside the next
        cycle's window and nothing is lost — only late. Keeping the newest instead would let the
        cursor advance past everything the cap displaced and silently drop it forever; recency is
        what the next cycle gets back anyway, completeness is not. (An earlier comment here claimed
        the newest lines were kept; it described the opposite of what the code did.) The line the
        cap cuts in half is dropped for the same reason: a truncated diagnostic can mis-parse — a
        bind error losing its `data` sub-code reads as a plain wrong password — and the whole line
        is inside the next cycle's overlap.

        `timestamps=true` is what makes the result usable at all — it prefixes each line with the
        kubelet's RFC3339 UTC stamp. klog's own stamp carries no year and no timezone.

        RETURNS None FOR THE ORDINARY ROLL, RAISES FOR THE REST, and the distinction is the point:

          404              the pod went away between listing and reading. Every roll does this.
          400 not-ready    the container has not started, so there is no log yet. Measured message:
                           "container nope is not valid for pod ..." — reason BadRequest.
          403              the grant is missing. LOGGED AT WARNING, because it is permanent and will
                           not fix itself, and a silent None here looks identical to "nobody logged
                           in" forever.
          any other        raised, so a real outage is not mistaken for roll noise.
        """
        params: dict[str, Any] = {"timestamps": "true"}
        if since_seconds is not None:
            params["sinceSeconds"] = str(since_seconds)
        path = f"{POD_API_TMPL % namespace}/{pod_name}/log"

        chunks: list[bytes] = []
        size = 0
        truncated = False
        try:
            with self._client() as client:
                with client.stream("GET", path, params=params) as response:
                    if response.status_code >= 400:
                        response.read()
                        return self._log_read_refused(response, namespace, pod_name)
                    for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max(1, max_bytes))):
                        room = max_bytes - size
                        if len(chunk) >= room:
                            chunks.append(chunk[:room])
                            size = max_bytes
                            truncated = True
                            break
                        chunks.append(chunk)
                        size += len(chunk)
        except httpx.HTTPError as exc:
            # A connect error or timeout reading ONE pod must not fail the cycle: the other pods still
            # have lines, and this one is retried next time from the same watermark.
            log.info("%s: could not read %s log (%s: %s)",
                     self.cluster.name, pod_name, type(exc).__name__, exc)
            return None

        # errors="replace" cannot corrupt a kept line: the only place a multi-byte character can be
        # split is the cap boundary, and the line holding it is popped below.
        lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
        if truncated:
            if lines:
                lines.pop()
            lines = _drop_capped_tail(lines)
            log.info(
                "%s: %s log hit the %d-byte cap after %d lines; the OLDEST lines of this window "
                "are kept, and the rest fall inside the next cycle's window once the watermark "
                "has advanced",
                self.cluster.name, pod_name, max_bytes, len(lines),
            )
        return lines
```

**Test, as supplied:**

```python
"""The byte cap is a third read seam, and it had no guard.

`_recordable` distrusts the newest lines (wall-clock) and `_not_clipped` the oldest (the window's
leading edge). The cap cuts in the MIDDLE of a backlog: an attempt straddling it is minutes old and
nowhere near the leading edge, so both guards wave its half-parse through. Measured end to end: one
successful login stored twice — `failed` from the capped read, `success` from the next cycle's
overlap — two rows contradicting each other about a named person.
"""
from __future__ import annotations

import httpx

from gsd.config import ClusterConfig
from gsd.kube import ClusterClient

FAIL = ('2026-08-08T12:00:00.000000Z I0808 12:00:00.000000       1 basicauth.go:48] '
        'Login with provider "developer" failed for login "jane.smith"\n')
OK = ('2026-08-08T12:00:00.500000Z I0808 12:00:00.500000       1 basicauth.go:51] '
      'Login with provider "ldap-local" succeeded for login "jane.smith"\n')
# A complete attempt a quiet three seconds earlier: nothing of it can continue past the cut.
EARLIER = ('2026-08-08T11:59:57.000000Z I0808 11:59:57.000000       1 login.go:191] '
           'Login with provider "developer" succeeded for "settled.user": &groupmapper...\n')


def _client_for(monkeypatch, body: bytes) -> ClusterClient:
    cluster = ClusterConfig("c", "https://api.example", token_env="X")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=body, request=request))
    client = ClusterClient(cluster)
    monkeypatch.setattr(
        client, "_client",
        lambda: httpx.Client(transport=transport, base_url="https://api.example"))
    return client


def test_an_attempt_straddling_the_cap_is_deferred_not_half_parsed(monkeypatch):
    """The cap lands between a success's chain-noise failure and its verdict.

    Returning the failure line alone makes the parse conclude `failed` for a person who succeeded,
    and the next cycle's full re-read then stores the success BESIDE it — `outcome` is in the dedup
    key, so nothing collapses them. The failure line must be deferred with the verdict it belongs to.
    """
    body = (EARLIER + FAIL + OK).encode()
    cap = len((EARLIER + FAIL).encode()) + 10          # cuts inside the success verdict line
    client = _client_for(monkeypatch, body)
    got = client.fetch_pod_log("ns", "pod", max_bytes=cap)
    assert got is not None
    assert not any("jane.smith" in line for line in got), (
        f"the half of a straddling attempt was returned for parsing: {got}"
    )


def test_lines_behind_a_window_of_silence_survive_the_cap(monkeypatch):
    """The guard must stop at the first quiet ATTEMPT_WINDOW, or a cap hit would defer good rows."""
    body = (EARLIER + FAIL + OK).encode()
    cap = len((EARLIER + FAIL).encode()) + 10
    client = _client_for(monkeypatch, body)
    got = client.fetch_pod_log("ns", "pod", max_bytes=cap)
    assert got is not None
    assert any("settled.user" in line for line in got), (
        f"a complete attempt three quiet seconds before the cut was thrown away: {got}"
    )
```

### Arbiter

_Pending._

### LENS3-3 — PRE_EXISTING_DEFECT_MISSED — medium
**Claim.** local-development/gsd/loginlog.py:adopt() (line 377) — an unidentified orphan is taken by the FIRST verdict in the window in LIST order, so with two unidentified bind errors waiting and their verdicts returning in the other order, the two people's causes CROSS: each named person gets the other's diagnosis. The docstring defends adjacency for the LONE orphan; nothing contemplates two.
**Trigger.** Two bind errors inside one ATTEMPT_WINDOW whose `found dn=` context is missing (a slow directory pushes the bind >1s past its found line, expiring it — precisely the lockout-delay regime a password spray provokes — or a clipped read), followed by the two verdicts in the opposite order to the errors.
**Consequence.** The dashboard tells bob his password was wrong (it was expired — he needs a reset, not a retype) and alice hers was expired (it was wrong): two false operational claims about two named people, each row also stamped at the OTHER person's bind instant.
**Evidence.** scratchpad/attack1_orphan_order.py against the worktree: alice's bind error (code 49) at T+0.1s, bob's (code 53) at T+0.2s, verdicts bob-then-alice. Output: LoginAttempt(user_name='bob', outcome='bad_password', ldap_result_code=49, at=...100000) and LoginAttempt(user_name='alice', outcome='password_expired', ldap_result_code=53, at=...200000) — both crossed. With the replacement adopt(): both degrade to outcome='failed', ldap_result_code=None (tests/test_lens3_regressions.py::TestTwoUnidentifiedOrphansDoNotSwap fails on worktree, passes on fixed copy; the lone-orphan path is pinned green by the existing test_a_browser_wrong_password_reads_the_code_through_the_orphan_path).

**Replacement code, as supplied:**

```python
# Complete replacement for the adopt() closure inside parse() in gsd/loginlog.py.
# (Already contained verbatim in finding LENS3-1's complete parse().)
    def adopt(p: _Pending, user: str, ts: datetime) -> None:
        """Give a fresh pending attempt the orphan cause that belongs to it, if one is waiting.

        An IDENTIFIED orphan (its evidence names a login) is taken only by that login's verdict —
        adopting by arrival order is how one person's diagnosis reached another. An UNIDENTIFIED
        orphan (a bind whose `found dn=` fell outside this read, so nothing ties its DN to a login)
        goes to the first verdict inside the window ONLY WHEN IT IS ALONE: refusing the lone one
        would discard every cause on a directory whose DNs do not carry the login, which is a
        systematic loss, and adjacency to a single cause is only wrong when a stranger's verdict
        beats the owner's to it. With TWO unidentified causes waiting, arrival order is the only
        tiebreak left, and it is exactly wrong whenever the directory answers out of order —
        measured as two strangers' bind codes swapped, an expired password recorded as somebody
        else's wrong one. Two waiting causes with no evidence have no honest owner; both verdicts
        degrade to the provider's own result, which is true.
        """
        def take(i: int) -> None:
            o = orphans.pop(i)
            p.first_at = o["at"]
            p.saw_no_entries = o["no_entries"]
            p.bind_code = o["code"]
            p.bind_diagnostic = o["diagnostic"]

        in_window = [(i, o) for i, o in enumerate(orphans)
                     if timedelta(0) <= ts - o["at"] <= ATTEMPT_WINDOW]
        # Evidence outranks adjacency: a cause that NAMES this login wins even when an
        # unidentified one arrived first.
        for i, o in in_window:
            if o["identified"] and _cause_mentions_user(o["evidence"], user):
                take(i)
                return
        unidentified = [i for i, o in in_window if not o["identified"]]
        if len(unidentified) == 1:
            take(unidentified[0])
```

**Test, as supplied:**

```python
class TestTwoUnidentifiedOrphansDoNotSwap:
    """adopt() by arrival order crossed two strangers' bind codes when verdicts returned out of order."""

    LINES = [
        # Two bind errors whose `found dn=` lines fell outside this read: both orphans, neither
        # DN carries the login. alice's code is 49 (wrong password), bob's 53 (ppolicy expiry).
        '2026-08-08T10:00:00.100000Z E0808 10:00:00.100000       1 ldap.go:152] error binding password for "CN=Alice Adams,OU=People,DC=example,DC=com": LDAP Result Code 49 "Invalid Credentials":',
        '2026-08-08T10:00:00.200000Z E0808 10:00:00.200000       1 ldap.go:152] error binding password for "CN=Bob Brown,OU=People,DC=example,DC=com": LDAP Result Code 53 "Unwilling To Perform":',
        # The verdicts return in the OTHER order — bob's first.
        '2026-08-08T10:00:00.300000Z E0808 10:00:00.300000       1 basicauth.go:48] Login with provider "ldap-local" failed for login "bob"',
        '2026-08-08T10:00:00.400000Z E0808 10:00:00.400000       1 basicauth.go:48] Login with provider "ldap-local" failed for login "alice"',
    ]

    def test_neither_verdict_takes_the_other_persons_cause(self):
        got = {a.user_name: a for a in parse(self.LINES)}
        assert set(got) == {"alice", "bob"}
        # First-orphan-in-list-order gave bob alice's 49 and alice bob's 53: bob was told his
        # password was wrong (it was expired) and alice that hers was expired (it was wrong).
        # With two unidentified causes waiting there is no honest owner; both must degrade.
        assert got["bob"].ldap_result_code is None, got["bob"]
        assert got["alice"].ldap_result_code is None, got["alice"]
        assert got["bob"].outcome == loginlog.OUTCOME_FAILED
        assert got["alice"].outcome == loginlog.OUTCOME_FAILED
```

### Arbiter

_Pending._

### LENS3-4 — PRE_EXISTING_DEFECT_MISSED — low
**Claim.** local-development/gsd/loginlog.py:parse() — `found` holds ONE entry per DN (line 424 overwrites), and the bind-cause attach blindly overwrites `pending[target].bind_code` (line 457): two logins resolving the SAME directory entry inside one window (sAMAccountName + userPrincipalName on AD) both read as the SECOND login's, and the later bind error's code overwrites the earlier's on that one person.
**Trigger.** jsmith (wrong password, AD data 52e) and jane.smith@corp.example.com (correct-but-expired password, data 532) both resolve dn=CN=Jane Smith,... within one second; the binds complete out of order (expiry first, wrong-password second).
**Consequence.** The UPN login is recorded outcome='bad_password', detail='LDAP result code 49, sub-code 52e' — her password was CORRECT (expired, sub-code 532); the row sends her to retype a credential that needs a reset. jsmith's row degrades to 'failed'.
**Evidence.** scratchpad/attack3_dn_and_regex.py against the worktree: printed LoginAttempt(user_name='jane.smith@corp.example.com', outcome='bad_password', ldap_result_code=49, detail='LDAP result code 49, sub-code 52e') — 52e is jsmith's code; her own bind line in the fixture carries data 532. With the replacement (found as list-per-DN; a bind error whose DN has >1 found context in window is dropped as ownerless), tests/test_lens3_regressions.py::TestTwoLoginsBehindOneDnDoNotTradeCauses fails on the worktree and passes on the fixed copy.

**Replacement code, as supplied:**

```python
# The correction spans three sites inside parse() (the `found` declaration, its expiry, and the
# bind-context read), so the complete replacement is the same parse() given verbatim in finding
# LENS3-1 — apply that one function once for LENS3-1, LENS3-3 and LENS3-4 together. The three
# scoped changes it carries for THIS finding are:
#
#   found: dict[str, list[dict]] = {}          # a LIST per DN, not a slot (comment in situ says why)
#
#   for dn in list(found):                      # expiry filters each DN's list
#       found[dn] = [f for f in found[dn] if ts - f["at"] <= ATTEMPT_WINDOW]
#       if not found[dn]:
#           del found[dn]
#   ...
#   found.setdefault(f.group("dn"), []).append({"at": ts, "raw": raw})
#   ...
#   if b is not None:
#       ctxs = found.get(b.group("dn"), [])
#       if len(ctxs) > 1:
#           continue                            # two logins behind one DN: no honest owner, dropped
#       if ctxs:
#           evidence = f'{raw} {ctxs[0]["raw"]}'
#           identified = True
#
# See LENS3-1's replacement_code for the full function these live in.
```

**Test, as supplied:**

```python
class TestTwoLoginsBehindOneDnDoNotTradeCauses:
    """found{} held ONE entry per DN, so the second login's found line rewrote the first's tie."""

    LINES = [
        # jsmith (sAMAccountName) and jane.smith@corp... (UPN) resolve to the SAME entry. jsmith's
        # password is wrong (data 52e); the UPN login's is right but expired (data 532).
        '2026-08-08T10:00:00.000000Z E0808 10:00:00.000000       1 basicauth.go:48] Login with provider "developer" failed for login "jsmith"',
        '2026-08-08T10:00:00.020000Z E0808 10:00:00.020000       1 ldap.go:148] found dn="CN=Jane Smith,OU=People,DC=corp,DC=example,DC=com" for (&(objectClass=person)(sAMAccountName=jsmith))',
        '2026-08-08T10:00:00.050000Z E0808 10:00:00.050000       1 basicauth.go:48] Login with provider "developer" failed for login "jane.smith@corp.example.com"',
        '2026-08-08T10:00:00.070000Z E0808 10:00:00.070000       1 ldap.go:148] found dn="CN=Jane Smith,OU=People,DC=corp,DC=example,DC=com" for (&(objectClass=person)(userPrincipalName=jane.smith@corp.example.com))',
        # The binds complete out of order: the UPN login's expiry first, jsmith's wrong password second.
        '2026-08-08T10:00:00.150000Z E0808 10:00:00.150000       1 ldap.go:152] error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example,DC=com": LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9, comment: AcceptSecurityContext error, data 532, v4563',
        '2026-08-08T10:00:00.180000Z E0808 10:00:00.180000       1 ldap.go:152] error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example,DC=com": LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9, comment: AcceptSecurityContext error, data 52e, v4563',
        '2026-08-08T10:00:00.200000Z E0808 10:00:00.200000       1 basicauth.go:48] Login with provider "ldap-ad" failed for login "jane.smith@corp.example.com"',
        '2026-08-08T10:00:00.210000Z E0808 10:00:00.210000       1 basicauth.go:48] Login with provider "ldap-ad" failed for login "jsmith"',
    ]

    def test_an_expired_password_is_not_recorded_as_somebody_elses_wrong_one(self):
        got = {a.user_name: a for a in parse(self.LINES)}
        # Both bind errors read as the UPN login's (the slot kept only its found line), and the
        # second OVERWROTE the first on her pending: she was recorded bad_password/52e when her
        # bind actually said 532 — a correct password she is told was wrong. Neither error can be
        # honestly owned once the DN is shared, so both rows degrade to the provider's verdict.
        her = got["jane.smith@corp.example.com"]
        assert her.outcome != loginlog.OUTCOME_BAD_PASSWORD, her
        assert (her.detail or "").find("52e") == -1, her
```

### Arbiter

_Pending._

### Technical debt (reviewer)

DEBT-INTRODUCED: the two fixes deepen a per-seam-guard pattern — the read now has three distinct distrust mechanisms (_recordable for the wall-clock tail, _not_clipped for the leading edge, and after this review a fourth is needed at the byte cap), each with its own arithmetic, each discovered by its own production defect, spread across logincapture.py and kube.py; a single invariant ("record an attempt only when the read provably contains its whole window") enforced in one place would have covered all three seams at once. Both new guards' docstrings also lean on the premise "an attempt's lines span at most ATTEMPT_WINDOW", which the parser does not actually enforce (measured: a 1.2 s bind splits one attempt) — the guards happen to survive under the weaker adjacent-lines-within-a-window invariant (verified empirically for _not_clipped), but the written justification is thinner than it claims. DEBT-ACCEPTED, explicitly and documented in the diff: _not_clipped drops leading-edge attempts for good rather than deferring them (a row lost at a first sight or a restart-adjacent second — the absent-beats-false trade); a success row now never carries a bind cause even when the cause was genuinely its own; the 1 s ATTEMPT_WINDOW remains load-bearing against real directory latency, and the slow-bind residual in finding LENS3-1 is the visible interest on that. DEBT-AVOIDED: named_at gives successes a stable stamp instead of a store-side special case or a dedup-key change; dropping causes on success rather than filtering "impossible" combinations avoids a taxonomy of which causes can explain which outcomes; taking window_start after the read returns avoids a latency-dependent false edge without adding a clock abstraction.

---

## Arbitration

Every finding was reproduced before it was applied, and every applied line was traced back to the
reviewer's own text above — 12 of 13 matched verbatim; the one that did not is named below as mine.

### Applied

| # | verdict | what I verified before applying |
|---|---|---|
| **L2-3** slow read loses a row | **APPLIED** | Derived the 58.5 s threshold independently: with the attempt at `now_P − 30.5` and `wm = now_P − 30`, cycle P+1 gets `since = Δ + 90`, so a stamp taken after an `L`-second body puts `edge = now_P + L − 89`, and dropping needs `L ≥ 58.5`. **My earlier sweep was wrong because it held `L = 0`.** Also verified the premise: a local dribbling server delivered a **4.17 s** transfer through a `timeout=1.0` client with no exception, so the httpx timeout bounds only the inter-chunk gap. Fix applied as supplied (`LOG_READ_BUDGET_SECONDS = 20.0`), diffed first — exactly four intended hunks, no silent drift. |
| **LENS1-Q4** a success destroys an orphan | **APPLIED** | Reproduced, and confirmed the "pre-existing" claim by loading the parser from `git show HEAD:` rather than trusting it: pre-fix, bob was already `failed / no reason`. Post-guard he is `bad_password code=49` stamped at the bind. |
| **LENS3-1** mid-flight expiry splits one login | **APPLIED, PARTIAL — see below** | Three providers 600 ms apart: 2 rows → 1 row. The over-suppression guard also holds — two attempts two minutes apart stay two rows. |
| **LENS3-3** two orphans cross | **APPLIED** | Two unidentified causes with verdicts in the other order: both now degrade to the provider's own verdict instead of swapping an expired password for a wrong one. |
| **LENS3-4** one slot per DN | **APPLIED** | Two logins behind one AD entry no longer read each other's sub-code. |
| **L2-1, L2-2, LENS1-Q1/Q2/Q3** | **NO CHANGE** | Five `FIX_IS_CORRECT` verdicts. Spot-checked Q3 by grep — `named_at` has one construction site — and accepted the rest. |

### The one line that is mine, not the reviewer's

`if len(unidentified) == 1 and not succeeded:` appears in no snippet above. Lens 3 rewrote `adopt`
**without** the `succeeded` parameter Lens 1 had just added, so applying its function wholesale would
have reverted LENS1-Q4 — and would also have reinstated the `conclude()` comment Lens 1 itself proved
false. The two were merged rather than swapped, keeping both rules: only a lone unidentified orphan is
adopted, and never into a success. A provenance check flagged this line automatically, which is how it
comes to be declared here rather than passed off as review output.

### LENS3-1 is only partly closed, and the doc must not claim otherwise

The reviewer scoped its residual as "a single SILENT gap wider than ATTEMPT_WINDOW". Measured, the
residual is wider than that. `last_at` advances only on **verdict** and **cause** lines; the progress
lines of a real login — `ldap.go:131 searching`, `ldap.go:148 found dn=`, `ldap.go:76 identitymapper` —
never touch a pending. So the measured production shape still splits:

```
htpasswd failed 12:00:00.0 -> searching .4 -> found dn= .8 -> identitymapper 1.2 -> succeeded 1.6
  => 2 rows: (jane.smith, failed, 12:00:00) and (jane.smith, success, 12:00:01.6)
```

That is the headline consequence of the finding — a fabricated `failed` beside a real `success` for a
named person — and it survives the fix. What closes it is advancing `last_at` from progress lines that
name a pending login (the `searching` filter and the `found dn=` line both embed it), which is new
design in the riskiest function in the module and is therefore **not** taken on this branch.

### Corrections to my own work that the review earned

1. The comment in `conclude()` said `adopt` runs "necessarily before any outcome is known". The call
   site has `v.group("verdict")` in scope, so it was false. Rewritten, and the guard now uses it.
2. `_not_clipped`'s docstring said "an attempt's lines span at most ATTEMPT_WINDOW". The influence span
   reaches twice that through `found → bind → verdict`, because expiry runs from the adopted `first_at`.
   The bound still holds; the reason given for it did not.
3. My poll-interval sweep concluded the two guards "cannot both bite the same attempt". True only at
   zero read latency, which is the one variable I failed to vary.

### One reviewer test was wrong and was rewritten

L2-3's test asserted against two 33-byte source chunks. `iter_bytes(chunk_size=65536)` re-chunks
whatever the transport yields, so the two were coalesced into one, the loop body ran once, the late
clock tick was never read, and the test failed against working code. Measured: `source supplied 2
chunks; iter_bytes yielded 1: [33]`. Rewritten to exceed `chunk_size`, which is what forces a second
iteration. A tautological assertion in the same test (`stream.yielded < 2 or got == [...]`, unreachable
after the line above it) was dropped.

### Suite

Measured, not estimated: `origin/main` in a pristine worktree gives **1057 passed, 1 skipped**; this
branch gives **1076 passed, 1 skipped**. The +19 matches the node-ID diff exactly — 17 new test
functions plus 2 parametrised doc-fence cases this document itself creates. Every new test was checked
to fail against the pre-fix code and pass after.

(The 1058 baseline quoted earlier in this session, and in PR #13's description, was off by one. It was
never measured against `origin/main` itself, only against the branch it came from. Counting `def test_`
cannot settle this either, because parametrised tests expand — which is why the figure above comes from
a node-ID diff between two worktrees.)
