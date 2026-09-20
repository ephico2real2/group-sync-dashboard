"""The Kyverno policy module (#165, #170): the CEL policy family, read through the policy reports.

The scope decision (#165): the five CEL kinds — ValidatingPolicy, MutatingPolicy, GeneratingPolicy,
DeletingPolicy, ImageValidatingPolicy — and never the deprecated ClusterPolicy / Policy family, which the API says
will be removed in a future release. The module reads REPORTS, not policy internals, because a report is the one
place Kyverno writes what a policy decided about a resource (`docs/design/kyverno-research-2026-09-17.md`
finding 1), and it treats three things as first-class states rather than as zero: the API not served
(not installed), the deprecated family's results present but not shown, and the report breaker's drops
(`docs/design/kyverno-discovery-2026-09-20.md`).

Nothing in this package names a person. A report names a resource, and the module's own /metrics
families carry policy kinds, results and cluster ids only (`definitions.py`); resource names and
namespaces reach the tier-gated JSON surface alone.
"""

from __future__ import annotations

#: The CEL kinds, in the order the page lists them. A report result's `source` names the family:
#: `pkg/utils/report/source.go` at v1.19.1 defines the four `Kyverno<Kind>` sources (a DeletingPolicy has
#: no report path — it deletes, it does not report) and the two admission-policy sources a GENERATED
#: policy's rows carry, `ValidatingAdmissionPolicy` / `MutatingAdmissionPolicy`, whose `policy` is
#: `vpol-<name>` / `mpol-<name>` — the same policy, once Kyverno has stood down on it (discovery §3). A
#: result whose source is none of these and not `kyverno` is kept under `other`, never dropped.
CEL_KINDS: tuple[str, ...] = ("ValidatingPolicy", "MutatingPolicy", "GeneratingPolicy", "DeletingPolicy", "ImageValidatingPolicy")
CEL_SOURCES: dict[str, str] = {"KyvernoValidatingPolicy": "ValidatingPolicy", "KyvernoMutatingPolicy": "MutatingPolicy",
                               "KyvernoGeneratingPolicy": "GeneratingPolicy", "KyvernoImageValidatingPolicy": "ImageValidatingPolicy"}
#: The generated admission policies' sources and the prefix their `policy` carries (generate-vap.go:34, generate-map.go:60).
GENERATED_SOURCES: dict[str, tuple[str, str]] = {"ValidatingAdmissionPolicy": ("ValidatingPolicy", "vpol-"),
                                                 "MutatingAdmissionPolicy": ("MutatingPolicy", "mpol-")}
#: What the legacy family writes as `source` (discovery §2: 667 of 676 results on the lab).
LEGACY_SOURCE = "kyverno"

#: A report result's `result` field, the vocabulary wgpolicyk8s.io/v1alpha2 fixes.
RESULTS: tuple[str, ...] = ("pass", "fail", "warn", "error", "skip")
#: The results a reader acts on; `skip` is a policy that did not apply, `pass` a resource that conforms.
PROBLEM_RESULTS: tuple[str, ...] = ("fail", "warn", "error")

#: Resource kinds a controller usually owns: a Deployment's finding repeats on every ReplicaSet and Pod
#: under it. Kyverno's CLI collapses those by rule name, which the CEL family has no rule names for
#: (finding 6), so the page offers a VISIBLE filter on these kinds instead of a silent collapse.
CONTROLLED_KINDS: tuple[str, ...] = ("Pod", "ReplicaSet", "Job")
