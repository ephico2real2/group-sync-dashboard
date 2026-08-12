# `/groupsyncs` at the self tier — design, for review before implementation

## The operator's two constraints, which shape everything below

1. **Cluster admins keep the error message, unchanged.** `error_message` is operational data they act
   on quickly. Nothing about the administrator experience changes. Only the **self tier** narrows.
2. **No technical debt.** The fix must not leave behind a list somebody has to remember to extend,
   an ambiguous payload, or a doc that disagrees with the code.

Constraint 2 is what makes this design bigger than "delete two fields", and the reason is a defect
fixed in this repository an hour ago: `SKIP_AUTH_PATHS` was a denylist of four exact paths, the
proxy's regex grew two more, nothing coupled them, and an unauthenticated caller could write
fabricated audit rows for six days. **A denylist of names is only as good as somebody remembering to
extend it.** `ldap_filter` and `error_message` are two names. The next sensitive field on this CR
would leak by default.

## What actually leaks, and to whom

`docs/SPEC_per_user_visibility.md`'s endpoint ruling for `/groupsyncs` already ruled this:

> `/groupsyncs` and `.../events` → FULL at both tiers … **EXCEPT `ldap_filter` and `error_message`
> are omitted at self tier** — both can embed directory DNs and the gate group, which `/metrics`
> deliberately never carries.

The rule was right. The code never caught up: no field is stripped anywhere, and the test the spec
named (`test_groupsyncs_omits_ldap_filter_at_self`) was drafted and never shipped. No reversal is
recorded in any commit, doc or comment, so this is **unfinished work, not an overruled decision**.

**The Overview tab is admin-only, so an ordinary reader never SEES these fields.** That is true and
it is not the whole story. `gsd/static/index.html#async function refresh` fetches `/groupsyncs` inside `if (view.cluster)`,
which holds on **every** page — so an ordinary reader's browser downloads the payload every 60
seconds regardless of which tab they are on. It lands in their network tab, in page memory, and in
any proxy log on the way. Not shown, but delivered; hiding a field in the UI is not hiding it.

What is in it:

| field | what it carries |
|---|---|
| `ldap_filter` | the directory search string, e.g. `(&(objectClass=groupOfNames)(cn=app-*))`. On a cluster following `docs/examples/clusteraccess-groupsync.yaml` the login-gate group is its own CR, so its filter carries the **gate group's CN**. |
| `error_message` | the operator's own error text, which can carry the **service bind DN** — measured on the repo's fixture: `LDAP bind failed for cn=svc,ou=people: invalid credentials`. |

**Why this is a leak by this project's own standard.** The rule is *gate what a reader cannot already
obtain with `oc`*. The GroupSync CR is not the dashboard's data — it belongs to the
group-sync-operator's CRD (`redhatcop.redhat.io/groupsyncs`) — so the question is whether the reader
could read it directly. Measured:

```
kubeadmin    get/list groupsyncs.redhatcop.redhat.io  yes
dana.lee     get/list groupsyncs.redhatcop.redhat.io  yes     (cluster-reader)
lateef.o     get/list groupsyncs.redhatcop.redhat.io  no
jane.smith   get/list groupsyncs.redhatcop.redhat.io  no
```

The two wide-tier personas can read the CR themselves, so serving it to them is not exposure. The two
narrowed personas cannot — the dashboard is their **only** source. And it is pointed, because
`/api/.../cluster-access` *deliberately refuses* the gate group's name and DN to a narrowed reader on
the stated ground that "the DN maps the directory". This is the same information through another door.

## What needs NO change — measured, so the fix stays small

- **`/groupsyncs/{name}/events` is clean.** Its SQL is
  `SELECT synced_at, observed_at, schedule, group_count FROM sync_event`. No error text, no filter. Its
  hard-coded `"scope": "all"` is honest for timestamps, a schedule and a count. **Leave it alone.**
  (An earlier note of mine said to check it "in the same pass" — checked, nothing to fix.)
- **Everything else on `/groupsyncs`.** The spec rules CR health full-view at both tiers, with the
  two directory diagnostics as its only exceptions. `/metrics` (in the chart's `skipAuthRegex` by
  deliberate ruling) serves the core of it — `gsd_groupsync_state`, `_last_sync_timestamp_seconds`,
  `_groups_total` per CR, to a credential-less `curl` — so REFUSING the endpoint would be theatre.
  The fields with no metrics analogue (`schedule`, `generation`, `observed_at`, `error_at`,
  `provider_keys`, the derived schedule fields) stay because the spec keeps them, NOT because
  `/metrics` serves them: it does not, measured — an earlier draft of this bullet claimed it did for
  all of them, and both round-1 reviewers refuted it (see Q2 below). Narrowing `provider_keys` in
  particular would also cost the Groups tab its per-provider colour slots
  (`gsd/static/index.html#function crSlot` reads `data.groupsyncs`) for nothing.

## Review round 1 — what the two reviewers settled, and what measurement overruled them both

Codex wrote `docs/REVIEW_groupsyncs_self_tier_design.md`; Cursor's findings were taken from a
parallel run. They split on four of six verdicts. Every split below was resolved by a measurement
taken after both reviews, not by preferring a reviewer.

### Q1 — keep the bare list. Cursor REFUTED my object shape, and it was right.

I proposed wrapping the response in `{cluster, scope, viewer, groupsyncs}` on the grounds that
`ACCESS_CONTROL.md` says scope rides every collection. Cursor pointed at a precedent I had not
checked, and the live API settles it:

```
/api/clusters   kubeadmin -> bare list, operator_configs={'total': 11, 'failing': 0}
/api/clusters   lateef.o  -> bare list, operator_configs=None
```

So there are **two classes of tier-varying collection**, not one:

| class | shape | examples |
|---|---|---|
| **field-withholding** | bare list | `/api/clusters` |
| **row-scoping** | object with `scope`/`viewer` | `/groups`, `/logins`, `/alerts` |

`/groupsyncs` after this fix is field-withholding, like `/clusters`. Making it an object would have
created the inconsistency I claimed to be removing. **No shape change, no UI edits, no `API.md`
churn, no breaking change.** Cursor also measured the breakage I would have shipped:
`index.html#function groupsyncTable` paints "None observed on this cluster yet." on a truthy object
whose `.length` is undefined, while the cluster card still shows the CRs.

### Q2 — BOTH reviewers were closer than me and all three of us asked the wrong question.

Both rated my allowlist FIX-INADEQUATE because I justified every member as "already on `/metrics`".
Measured against the live endpoint, `/metrics` carries **five** things per CR and no more:

```
gsd_groupsync_state{groupsync=...,namespace=...,state=...}
gsd_groupsync_groups_total{...}
gsd_groupsync_last_sync_timestamp_seconds{...}
gsd_groupsync_reconcile_error_current{...}
```

That is name, namespace, `state`, `group_count`, `last_sync_at`, and the error **bit**. It does NOT
carry `schedule`, `schedule_valid`, `next_expected`, `interval_seconds`, `generation`,
`observed_at`, `error_at` or `provider_keys`. My justification was false for eight of fourteen
fields, and the two reviewers then disagreed about which of those eight are "safe" —
Codex withholding `error_at`, `generation`, `observed_at`, `provider_keys`; Cursor keeping them.

**Neither question was the right one.** "Which fields are harmless?" is a judgement that will be
re-litigated every time a field is added. "Which fields does the narrowed reader''s own UI
consume?" is a measurement. Taken:

| consumer | fields read from `data.groupsyncs` | reachable at self? |
|---|---|---|
| `index.html#function crSlot` | `provider_keys` | **YES** — Groups tab |
| `index.html#function groupsyncTable` | name, namespace, schedule, schedule_valid, state, last_sync_at, next_expected, group_count, error_is_current | no — Overview is admin-only |
| `index.html#function groupsyncDetail` | the above plus `error_at`, `error_generation`, `error_message`, `ldap_filter` | no — reached only from Overview |

**A narrowed reader''s UI consumes exactly one field: `provider_keys`.** Everything else on this
endpoint feeds pages that render a refusal card for them. So the allowlist is not a safety
judgement at all — it is what the self view actually needs, and everything else is withheld because
it is unused, which is an argument nobody has to re-litigate.

This is stricter than either reviewer proposed and it removes the whole "is this field sensitive?"
conversation for every future field. It also happens to make Q4 moot: `provider_keys` stays not
because it is judged safe but because `crSlot` cannot colour without it — and independently, the
self tier already receives the same string from `/groups`:

```
lateef.o  scope=self  ->  sync_provider='ldap-groupsync_ldap'
                          sync_provider='ldap-clusteraccess-groupsync_ldap'
```

### Q3 — Codex REFUTED it, and this is the most valuable finding of the round.

`/api/alerts` already hands a self-tier reader the full bind DN. Verified independently against the
repo''s own fixture:

```
alice  scope=self  reconcile_error alerts=1
       detail='LDAP bind failed for cn=svc,ou=people: invalid credentials'
```

`gsd/state.py#compute_alerts` copies `error_message` straight into `detail`, and `reconcile_error`
is in `SELF_ALERT_KINDS`. Every narrowed reader fetches `/api/alerts` on every page. **Closing
`/groupsyncs` alone would have shut the quieter door and left the busier one open** — the original
design was incomplete and would have shipped a false sense of closure.

Both reviewers supplied a fix; they took different shapes. Codex uses ONE structure —
`SELF_ALERT_DETAILS: dict[str, str | None]` with `SELF_ALERT_KINDS = frozenset(SELF_ALERT_DETAILS)`
**derived** from it. Cursor uses two sets and argues it is "fail-closed on both axes", which is
true. Codex''s shape is taken, on the operator''s no-debt rule: two structures that must agree is
precisely the shape that produced this morning''s `SKIP_AUTH_PATHS` defect, and a derived set cannot
disagree with its source.

### Q5 — moot, by the Q1 and Q2 outcomes.

Codex proposed unwrapping the object at the transport boundary; there is no object. Its silent-
regression warning — that withholding `provider_keys` would make `crSlot` quietly drop every source
dot, so a narrowed reader reads missing decoration as "unmapped provider" — is exactly why
`provider_keys` is in the allowlist.

### NEW-1 — my own design document broke the build.

Three line-number citations failed `tests/test_docs_citations.py#test_no_citation_uses_a_line_number`,
the rule this repository added after two citations came to point at unrelated code. Converted to
`#anchor` form; 269 citation tests pass.

## The design, as revised

> **SUPERSEDED IN ROUND 2 — see "Review round 2 — outcome" at the end of this document.** The
> `provider_keys`-only allowlist below did not survive review: both round-2 reviewers refuted the
> UI-consumption derivation, and the shipped allowlist is the spec's own ruling — every field
> full-view except the two named directory diagnostics. The MECHANISM below (bare list, allowlist
> projection, one derived alert structure, admin untouched) shipped as designed.

### 1. `/groupsyncs` keeps its bare-list shape and projects at the self tier

```python
#: What a self-tier reader receives of a GroupSync CR — derived from what the SELF VIEW'S OWN UI
#: consumes, not from a judgement about which fields look harmless.
#:
#: Measured: of the three functions that read data.groupsyncs, only crSlot is reachable at the self
#: tier (the Groups tab), and it reads provider_keys alone. groupsyncTable and groupsyncDetail feed
#: the Overview tab and its drill-down, both of which render a refusal card for this reader.
#:
#: So every other field is withheld because it is UNUSED, which is an argument nobody has to
#: re-litigate when a field is added — the opposite of SKIP_AUTH_PATHS, whose denylist of four paths
#: went stale against a regex that grew two more and let an unauthenticated caller write audit rows
#: for six days. A new column on groupsync_state, or a new key from enrich(), is withheld by
#: default and only reaches the self view when a consumer needs it.
#:
#: provider_keys is safe independently as well as necessary: /groups already serves the same
#: <cr>_<provider> string to this reader for their own groups (measured: sync_provider=
#: 'ldap-groupsync_ldap'), so withholding it here would shut one door while another serves it.
SELF_TIER_GROUPSYNC_FIELDS = frozenset({"provider_keys"})
```

The route gains `request` and projects; the administrator row is returned untouched.

### 2. `/api/alerts` narrows the reconcile DETAIL, keeping the signal

One derived structure, so the kind list and the detail policy cannot disagree:

```python
SELF_ALERT_DETAILS: dict[str, str | None] = { ... "reconcile_error": "<generic>" ... }
SELF_ALERT_KINDS = frozenset(SELF_ALERT_DETAILS)
```

`reconcile_error` stays a self-tier kind — `gsd_groupsync_reconcile_error_current` is on public
`/metrics`, so the EXISTENCE of a current failure is not a secret and is actionable. Only the text
is replaced.

### 3. Administrators are unchanged, byte-for-byte

Constraint 1, made executable: a preservation test asserts the wide tier still carries
`ldap_filter`, `error_message` and the full alert `detail`, so nobody tidies the operator's
diagnostic away later.

### 4. The tests that make it durable

- the spec's named `test_groupsyncs_omits_ldap_filter_at_self`
- **an exhaustive partition test**: every key the wide tier returns is either in the allowlist or in
  an explicitly-declared withheld set, so an unclassified new field is a red build rather than a leak
- a test that `crSlot`'s colouring still works at the self tier — Codex's silent-regression case
- admin preservation, for both endpoints
- an honesty test that every allowlist justification claiming `/metrics` coverage is true

### 5. Nothing else drifts

Same commit: `SPEC_per_user_visibility.md` (mark the ruling shipped), `ACCESS_CONTROL.md` §4 (its
table does not currently mention either field), `API.md`, and the route docstring that still claims
"the payload never varies by tier".

## Questions for review round 2

1. **Is `frozenset({"provider_keys"})` too strict?** It is derived from what the self UI consumes
   today. Does any non-UI consumer — an external API caller, a test, a doc example — depend on a
   self-tier reader receiving more? If so, name it; that is a real requirement I have not counted.
2. **Does the partition test actually fail on a new field**, or can a field slip through by being
   absent from the wide payload in the fixture while present in production?
3. **Is replacing the alert `detail` string better than omitting the key?** Omitting is the
   convention chosen for `/groupsyncs`; the alert feed is rendered as text, so a missing key may
   render as "undefined" in the UI. Check what the alert card does with an absent `detail`.
4. **Anything in the alerts path that still carries the error text** — `subject`, a tooltip, the
   `/groupsyncs/{name}/events` note, or the PrometheusRule annotations in the chart.
5. **Did round 1 leave anything unsettled** that this revision silently dropped?

## Review round 2 — outcome, and what shipped (2026-08-11)

Both reviewers' full findings are in the repo: `docs/REVIEW_groupsyncs_round2_codex.md` and
`docs/REVIEW_groupsyncs_round2_cursor.md`. The arbitration, per question:

**Q1 — REFUTED, and the refutation shipped.** `frozenset({"provider_keys"})` was wrong from two
directions. Codex: the endpoint has a documented contract (`local-development/API.md`, the served
OpenAPI document, the requirements and the spec), and deriving what the API returns from what
today's frontend happens to fetch makes the contract an accident of the current UI. Cursor,
sharpest: the design contradicted itself — "delivered counts as leaked" is why this fix exists at
all, so "what the UI consumes" cannot also be the criterion for what is safe; and the spec's ruling
("FULL at both tiers EXCEPT `ldap_filter` and `error_message`") was replaced without any recorded
reversal. **Shipped: the spec's ruling** — `gsd/api.py#SELF_TIER_GROUPSYNC_FIELDS` is every field
the spec keeps, and exactly `ldap_filter` and `error_message` go at self. The allowlist MECHANISM
stays (a two-name denylist is the `SKIP_AUTH_PATHS` shape; a new column is withheld until ruled
on), justified by the spec's ruling — never by "already on `/metrics`", which is false for eight of
the fields and was refuted twice.

**Q2 — the fixture-derived partition was inadequate; the code-derived one shipped.** Codex is right
that a partition asserted against a fixture payload does not prove the invariant for a key that
appears only with production data. Shipped:
`tests/test_visibility.py#test_groupsync_tier_policy_is_exhaustive` derives the expected universe
from the CODE — a row from `gsd/store.py#Store.groupsyncs` (SQL emits every SELECTed column, NULL
or not, plus the stitched `provider_keys`) passed through `gsd/api.py#enrich`, which was moved to
module level with `grace` as an argument precisely so the test can run the real path.

**Q3 — REPLACE the alert detail, do not omit the key.** Both reviewers measured that
`index.html#function esc` collapses a nullish detail to `""`, so an absent key renders as an EMPTY
reason column — "no reason exists" when the truth is "withheld", the fabricated-absence this repo
already bans. Shipped: `gsd/api.py#SELF_ALERT_DETAILS`, one mapping carrying kind admission and
detail policy together, `SELF_ALERT_KINDS` derived from its keys, `reconcile_error` replaced with a
generic sentence at self, admin feed never rewritten.

**Q4 — CONFIRMED, no second path.** `subject` is the CR name, the alert row has no tooltip, the
events payload carries no error text, and the PrometheusRule annotations never receive
`error_message`. The fix stayed on the two endpoints.

**Q5 / NEW-2 — the stale theses were rewritten in the same change.**
`tests/test_view_scoping.py#test_cr_health_stays_full_view_because_metrics_already_publishes_it`
keeps its name (the round-2 reviews cite it as a checked anchor) and its bare-list assertion, with
its docstring rewritten to the spec-exception rationale; the "already served by `/metrics`" bullet
earlier in THIS document was corrected (it was false for eight of fourteen fields); and the
`SELF_ALERT_DETAILS` comment no longer claims CR health is full-view at both tiers.

**What shipped, in one list:** `gsd/api.py#list_groupsyncs` (bare list, `viewer_scope`, allowlist
projection at self, admin rows untouched), `gsd/api.py#SELF_TIER_GROUPSYNC_FIELDS` +
`gsd/api.py#WITHHELD_AT_SELF_GROUPSYNC_FIELDS`, `gsd/api.py#SELF_ALERT_DETAILS` +
`gsd/api.py#_alerts_for_self`, module-level `gsd/api.py#enrich`; tests
`test_groupsyncs_omit_directory_detail_at_self`, `test_groupsync_tier_policy_is_exhaustive`,
`test_reconcile_alert_replaces_only_the_self_tier_detail`,
`test_admin_keeps_the_diagnostic_bytes_on_both_endpoints`,
`test_self_refresh_payload_does_not_carry_the_bind_dn` (all in `local-development/tests/test_visibility.py`) and
`test_group_source_dots_still_colour_at_the_narrowed_tier` (in `local-development/tests/test_ui.py`); doc updates in
`docs/SPEC_per_user_visibility.md` (ruling marked shipped), `docs/ACCESS_CONTROL.md` §4/§5,
`local-development/API.md`, and this document. `/groupsyncs/{name}/events` unchanged, as measured.
