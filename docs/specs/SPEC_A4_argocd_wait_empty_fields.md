# SPEC A4 — `argocd-wait.sh` compares the Application's source the way Argo CD stores it: an empty field is absent (#534)

| | |
|---|---|
| Programme | none: lab tooling, the operator's go-ahead of 2026-10-03 on #534 ("Fix it now") |
| Batch | A — release |
| Release | — (post-programme; its own pull request) |
| Version on release | no version change (a repository tool and its test) |
| Issue | [#534](https://github.com/ephico2real2/group-sync-dashboard/issues/534) |
| Status | specified |
| Source | Written by the orchestrator on 2026-10-03, from main `94f5ebbb`. The facts are measured on the CRC lab, in the walk logs on main, and in Argo CD's own source (§2). |

## How to read this spec

`release-crc.sh --argocd <branch>` writes `spec.source.helm.parameters: []`, which clears any image a previous
commit-pinned deploy left behind. Argo CD then writes its comparison, `status.sync.comparedTo.source`, from Go structs
whose fields are `omitempty`, so the empty list is not there. `argocd-wait.sh` compared the two as JSON text and
called them different. Whenever no sync ran, it waited out its whole 900 s with "status is for the previous spec",
although the Application was Synced and Healthy on the right revision.

The fix compares both sides the way Go's `omitempty` writes them: a key whose value is empty is dropped first. Every
real difference still fails.

## Orchestrator's notes

1. **Where the fix goes: the waiter, not the writer (decided).** `release-crc.sh` writes `parameters: []` on purpose.
   `test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit` pins it, because the empty list is what
   clears a commit-pinned image. The issue says "make the wait compare what Argo CD reports. Do not loosen the wait",
   and a comparison under `omitempty`'s rule is exactly what Argo CD reports.
2. **Not loosened.** Only zero values are dropped (an empty list, map or string, `null`, `false`, `0`), and Go's
   `encoding/json` omits exactly those under `omitempty`. Any non-empty difference fails as before, which
   §4's second half proves: another values file is still "the previous spec".
3. **Why a sync seemed to make the difference** (the issue's open point) is not needed for the fix, and is not
   explained here.
   - The record: the wait passed whenever the target revision changed and a sync ran, and timed out whenever none
     ran. Today's walk logs show both: `reports/2026-10-03_platform-users-255/walk.log` passed at 05:59 and timed
     out at 06:21; `reports/2026-10-03_release-4.0.0-walk/walk.log` timed out.
   - The fix makes the comparison right in both cases, so the open point no longer decides anything.

## 1. The mandate, and what is out of scope

The issue's change: find the cause from the script and Argo CD's status, then make the wait compare what Argo CD
reports, without loosening the wait. Out of scope:
- what `release-crc.sh` writes;
- the revision check (`rev_ok`);
- the Synced, Healthy and Succeeded conditions.

## 2. Research, measured

- **The lab, 2026-10-03, after `release-crc.sh --argocd main --values environments/crc.yaml`:**
  - `spec.source.helm` has the keys `parameters`, `releaseName`, `valueFiles` and `valuesObject`, with
    `parameters` = `[]`.
  - `status.sync.comparedTo.source.helm` has `releaseName`, `valueFiles` and `valuesObject`.
  - A recursive diff finds one difference, `only in spec: /helm/parameters = []`, and the JSON equality is `False`.
- **Argo CD v3.4.7, `pkg/apis/application/v1alpha1/types.go`** (read raw, line numbers from `nl -ba`):
  - L540: `` ValueFiles []string `json:"valueFiles,omitempty" …` ``
  - L542: `` Parameters []HelmParameter `json:"parameters,omitempty" …` ``
  - L1287–1290: `BuildComparedToStatus` builds `ComparedTo` from the spec's sources, so `comparedTo` is those structs
    marshalled with their `omitempty` tags.
- **Go `encoding/json`**: the `omitempty` option omits a field whose value is `false`, `0`, a nil pointer or
  interface, or an empty array, slice, map or string.

## 2a. Alternatives considered

- **Write no `parameters` key when it is empty, in `release-crc.sh`.** Rejected.
  - `oc apply`'s three-way merge would then remove the key only because last-applied held it. That is a quieter,
    order-dependent way to clear an image than the explicit empty list the existing test pins.
  - Any other writer of an empty field (an empty `valueFiles`) would still break the wait.
- **Ignore `comparedTo` and trust `sync.status` with the revision.** Rejected. The header records why the guard
  exists: the controller reports the previous comparison for a while after a source change.
- **Normalise `parameters` alone.** Rejected as narrower than the cause: the rule is Go's, for every `omitempty`
  field.

**Reconciliation.** The research says Argo CD drops zero values under `omitempty`. The code now drops the same values
from both sides before comparing (`local-development/argocd-wait.sh`, the `present` function).

## 3. The design

In `argocd-wait.sh`'s Python reader, `present(v)` returns `v` with every key whose (normalised) value is empty
removed, recursively. The values removed are `[]`, `{}`, `None`, `""`, `False` and `0`. `same` compares
`present(spec.source)` with `present(comparedTo.source)`. Nothing else changes.

## 4. Tests

`test_waiter_reads_an_empty_field_as_argo_cd_does` in `local-development/tests/test_release_crc.py`, two halves:
1. **The same source.** The spec carries `helm.parameters: []` and `comparedTo` does not. The wait exits 0. Without
   the change it times out with "status is for the previous spec": this is #534.
2. **A real difference.** `comparedTo` names another values file. The wait still exits 1 with "status is for the
   previous spec". This proves the change is not a loosening.

## 5. On the lab

`release-crc.sh --argocd main --values environments/crc.yaml` when nothing has changed returns 0, with
"argocd  : group-sync-dashboard Synced/Healthy", within one waiter interval.

## 6. What an operator sees, and what it costs

A release deploy that needs no sync no longer spends 900 s timing out. It costs one recursive function in the waiter.

## 7. Implementation blocks

#### Block 1 — local-development/argocd-wait.sh: compare under `omitempty`'s rule

<!-- block: local-development/argocd-wait.sh | edit -->

Old text:

```python
same = json.dumps(a["spec"]["source"], sort_keys=True) == json.dumps(sy.get("comparedTo", {}).get("source"), sort_keys=True)
```

New text:

```python
def present(v):
    # Argo CD writes status.sync.comparedTo from Go structs whose fields are `omitempty` (argo-cd v3.4.7
    # types.go L540 valueFiles, L542 parameters), so an empty list, map or string, null, false or 0 in the
    # spec is absent there. Both sides drop those first; any other difference is still the previous spec (#534).
    if isinstance(v, dict):
        kept = {k: present(x) for k, x in v.items()}
        return {k: x for k, x in kept.items() if x not in ([], {}, None, "", False)}
    if isinstance(v, list):
        return [present(x) for x in v]
    return v
same = present(a["spec"]["source"]) == present(sy.get("comparedTo", {}).get("source") or {})
```

#### Block 2 — local-development/tests/test_release_crc.py: the failing-then-passing test

<!-- block: local-development/tests/test_release_crc.py | edit -->

Old text:

```python
def test_waiter_matches_the_expected_commit_by_prefix_either_way(lab):
```

New text:

```python
def test_waiter_reads_an_empty_field_as_argo_cd_does(lab):
    """#534: the branch path writes `helm.parameters: []`, and Argo CD writes status.sync.comparedTo from Go structs whose
    fields are `omitempty` (argo-cd v3.4.7 types.go L542), so the empty list is absent there. The same source with and
    without the empty key is the current comparison; another values file is still the previous spec."""
    synced_status(lab, "abc")
    d = json.loads((lab["tmp"] / "app-status.json").read_text())
    d["spec"]["source"]["helm"] = {"parameters": [], "valueFiles": ["../../environments/crc.yaml"]}
    d["status"]["sync"]["comparedTo"]["source"]["helm"] = {"valueFiles": ["../../environments/crc.yaml"]}
    (lab["tmp"] / "app-status.json").write_text(json.dumps(d))
    assert wait(lab, "2", "abc").returncode == 0
    d["status"]["sync"]["comparedTo"]["source"]["helm"]["valueFiles"] = ["../../environments/other.yaml"]
    (lab["tmp"] / "app-status.json").write_text(json.dumps(d))
    r = wait(lab, "2", "abc")
    assert r.returncode == 1 and "status is for the previous spec" in r.stdout


def test_waiter_matches_the_expected_commit_by_prefix_either_way(lab):
```

#### Block 3 — docs/CHANGELOG.md: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```markdown
## Application 4.0.0 — chart 0.66.4 — 2026-10-03
```

New text:

```markdown
## Unreleased

- **`release-crc.sh --argocd` no longer times out when nothing needs syncing (#534, `docs/specs/SPEC_A4_argocd_wait_empty_fields.md`;
  lab tooling, no version change).** `argocd-wait.sh` compared the Application's `spec.source` with Argo CD's
  `status.sync.comparedTo.source` as JSON text. Argo CD writes the latter from `omitempty` Go structs, so the
  `helm.parameters: []` the branch path writes was never there, and the wait ran out its 900 s although the
  Application was Synced and Healthy. Both sides now drop empty values first. Any other difference is still "the
  previous spec".

## Application 4.0.0 — chart 0.66.4 — 2026-10-03
```
