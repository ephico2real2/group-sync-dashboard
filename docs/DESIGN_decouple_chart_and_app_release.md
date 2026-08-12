# Design — stop writing the image pin to `main`

**Status:** design only. Nothing implemented. Two reviewers, then arbitration, then a decision.

**The operator's framing, which this document takes as the premise:** the product and the chart are
different artefacts with different release cadences. They are related at exactly two moments — when
the image version changes, and when an app change forces a values or template change. Everything
else about them is independent.

That premise is the documented Helm model, not a preference. `helm.sh/docs/topics/charts`:

> "Note that the `appVersion` field is not related to the `version` field. It is a way of specifying
> the version of the application." … "This field is informational, and has no impact on chart
> version calculations."

This repo currently violates it in one specific way, and that single violation is the measured cause
of three separate problems.

---

## 1. What we do today

`publish.yml` builds an image on every merge to `main` that touches an image input, tags it
`<appVersion>-<10-char sha>`, then **pushes a commit to `main`** rewriting
`charts/group-sync-dashboard/values.yaml`'s `image.tag` and bumping `Chart.yaml`'s patch version.

## 2. What that one decision has cost, measured

| symptom | mechanism |
|---|---|
| **#34** — the published chart pinned an image two merges old, including a self-tier data-exposure fix | the chart is released from the *merge* commit, but the pin for that merge's image lands in a *child* commit, so the release always packaged the previous pin. Compounded because chart-releaser skips an already-released version, so a code-only merge froze the published chart indefinitely. |
| **#37** — a release published nothing while reporting `success` | the dispatch added to fix #34 resolved `--ref main` to the pre-push tip. Measured across four runs: two packaged the pin commit, one packaged the merge commit and published nothing, all four reported `success`. |
| **branch protection is impossible** | CI must write to `main`, so any rule that blocks direct pushes blocks the pin. On a user-owned repo the writer cannot be allowlisted: ruleset bypass → `422 "Actor GitHub Actions integration must be part of the ruleset source or owner organization"`; classic push restrictions → `422 "Only organization repositories can have users and team restrictions"`. |

Three symptoms, one cause. Today `main` carries only force-push and deletion blocks — verified by a
real rejected attempt (`protected branch hook declined`) — because that is the strongest rule set
that does not break the pin.

## 3. What the convention does instead

**cert-manager** builds its own images *and* ships its own chart from one repository, which is the
closest analogue to this repo:

```yaml
# deploy/charts/cert-manager/values.yaml
image:
  name: cert-manager-controller
  repository: ""
  # tag: vX.Y.Z        # "If no value is set, the chart's appVersion is used."
```

```yaml
# deploy/charts/cert-manager/Chart.yaml
version: v0.0.0        # "The version and appVersion fields are set
appVersion: v0.0.0     #  automatically by the release tool"
```

Its `cert-manager.image` helper resolves `tag` → `digest` → the appVersion default. So versions are
**stamped at package time and never committed back to the default branch**, and consumers who want
true immutability pin by digest.

**`group-sync-operator-helm-chart`** — the repo whose `helm.yaml` this one was modelled on — has
**no `git push` to `main` in any workflow**, because it packages third-party images
(`registry.redhat.io/openshift4/ose-cli:v4.14`) that a human bumps in a PR. Its `ci.yaml` documents
the protection this buys:

> "`main` is branch protected with PRs required, admins included, and `Chart changes bump the chart
> version` as a required status check — verified by a rejected direct push (GH006)."

## 4. The change is smaller than it looks

**`gsd.image` already implements the cert-manager pattern.** `templates/_helpers.tpl`:

```
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
```

No template change is required. The pin exists *only* because `values.yaml` sets `image.tag`. Delete
that line and the chart already resolves to `.Chart.AppVersion`.

So the proposal is:

1. `values.yaml`: `image.tag: ""`, with the existing fallback carrying it.
2. `publish.yml`: publish `<appVersion>` **in addition to** the immutable `<appVersion>-<sha>`, and
   **stop pushing to `main`** — no pin commit, no automated chart bump.
3. `Chart.yaml`'s `version` and `appVersion` become human decisions in PRs again, enforced by a
   `Chart changes bump the chart version` check copied from the operator repo.
4. `main` gets the full protection that repo has: PRs required, admins included, required checks.

## 5. The operator's addition: also tag the image with the chart version

Proposed during discussion: publish `:<chartVersion>` as well, whenever we cut to `main` and release
to gh-pages. Worth stating precisely because `.Chart.Version` **is** available in templates, so this
is a real alternative keying and not only a convenience tag.

- As an **additional** tag it costs one `podman tag`/`push` and gives a chart-version ↔ image
  correspondence a human can check by eye.
- As the **keying** (`default .Chart.Version`) it would remove the need for `appVersion` to track the
  image at all — but it makes the chart version increment for app-only changes, which is the
  coupling §0's premise wants gone, and contradicts `Chart.yaml`'s stated meaning for that field.

**OPERATOR RULING: the additional tag is IN.** Publish `:<chartVersion>` alongside the other two
whenever we cut to `main` and release to gh-pages — the operator's position is that there is no harm
in it, and the cost is one `podman tag` and one `push`. This is settled; reviewers should not spend a
verdict on *whether* to do it.

**The keying stays on `appVersion`** — `default .Chart.AppVersion`, unchanged from the helper that
already exists. Keying on `.Chart.Version` is rejected here because it would make the chart version
increment for app-only changes, which is the coupling §0's premise exists to remove.

What reviewers SHOULD attack is the interaction, D6, and one gap the design already suspects: a
**chart-only release** bumps `Chart.yaml`'s version without touching an image input, so `publish.yml`
never runs and no image carries that chart version. `:0.4.4` existing while `:0.5.0` does not is
harmless for a tag nothing resolves — and a trap for the first person who assumes the correspondence
is total. If that is right, this needs a sentence in the chart README, not a code change.

## 6. What this gives up

`<appVersion>` becomes a **moving** tag: two merges at `0.7.0` both publish `:0.7.0`. This repo
deliberately avoided mutable tags for traceability. Mitigations already present or cheap:

- the immutable `<appVersion>-<sha>` keeps being published, so anyone can pin exactly;
- a running pod reports its own commit at `/api/version` and on `gsd_build_info`, so provenance never
  depended on the tag;
- digest support in `gsd.image`, as cert-manager has, would let a consumer pin immutably by digest.

The deeper question, and the one the reviewers should push hardest on: **should a merge to `main`
publish a release at all?** cert-manager's `appVersion` equals its image tag because it cuts one
image per *release*. We cut one per *merge*, which is exactly why we needed somewhere to write the
sha. If published images were per-release, `appVersion` ↔ tag is honest and immutable, and per-merge
builds still exist for the dev cluster without being published artefacts.

---

## Claims to confirm or REFUTE

- **D1.** The three symptoms in §2 share the single cause named there, and removing the pin commit
  removes all three. Refute with a symptom that survives, or a fourth cause.
- **D2.** No template change is needed. `gsd.image`'s `default .Chart.AppVersion` already resolves
  correctly with `image.tag: ""`. Verify by rendering, and say what breaks when `tag` is empty AND
  `appVersion` is unquoted or numeric-looking.
- **D3.** `tests/test_chart_versions.py#test_the_pinned_image_tag_is_a_build_of_that_same_app_version`
  becomes meaningless — there is no pin to check. Say what should replace it, because deleting a
  guard that caught a real drift (`appVersion` read `0.5.2` for weeks) needs a successor, not a hole.
- **D4.** The moving `<appVersion>` tag is acceptable given the mitigations in §6. This is the claim
  most likely to be wrong; argue the strongest case AGAINST it, including what a consumer who
  installed `0.4.4` yesterday gets after the next merge, and whether digest support should ship in
  the same change or later.
- **D5.** Per-merge publishing is the actual root and should change too. Or refute: per-merge
  publishing is fine as long as nothing writes to `main`, and the moving tag is the whole cost.
- **D6.** The operator's §5 addition — image tagged with the chart version *in addition* — has no
  harmful interaction. Consider specifically: two chart versions that package the same appVersion,
  and a chart version published without a new image.
- **D7.** The automated chart patch bump from #34 can be deleted rather than replaced. With human
  bumps plus a required check, is anything lost that the automation was buying?
- **D8.** Branch protection then actually becomes possible on THIS repo. Verify against the two 422s
  in §2 — is there any remaining actor that must write to `main` after this change? Check every
  workflow, not just `publish.yml`.

## Out of scope

- The self-tier projection (#33), the tier-constants rename (#36), the `0.7.0` bump (#35).
- `gh-pages` layout, chart-releaser's own behaviour, and the gh-pages index propagation delay.
- Anything about `oauth-proxy`, visibility tiers, or the app's own behaviour.

## What a finding must carry

1. A verdict per claim: **CONFIRMED**, **REFUTED**, or **FIX-INADEQUATE**. "Cannot refute" only after
   saying what you checked.
2. `file#symbol`, or an exact quoted line. Line numbers are permitted in this file, which is
   registered in `tests/test_docs_citations.py#REVIEW_ARTIFACTS`.
3. For anything you would change: the **full replacement** — the values block, the workflow step, the
   test — not a description. This codebase's comments say WHY, never WHAT.
4. Measurements, not reasoning. Render the chart. Run the suite. The baseline is
   `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
   → **1469 passed, 4 deselected**.
5. A verdict on whether this is worth doing at all. "The pin is fine, protect less" is a legitimate
   conclusion and more useful than inventing a migration.

## Codex — pass 1

<!-- Codex writes verdicts here, using `> **Codex:**` markers. -->

> **Codex:** **D1 — CONFIRMED.** The measured failures do share the post-merge write-back as their
> necessary cause. `.github/workflows/publish.yml#jobs.publish.steps[Pin the published tag on main]`
> is the only path that turns an image build into a child commit (`git push origin HEAD:main`), and
> `.github/workflows/publish.yml#jobs.publish.steps[Publish the chart that pins the image just
> built]` exists only because a `GITHUB_TOKEN` push cannot trigger `helm.yaml`. Removing the child
> commit removes the one-commit packaging lag, the compensating ref-racy dispatch, and the need for
> an Actions actor to bypass protection. `chart-releaser` skipping an existing version amplified
> #34/#37, but it does not independently recreate either failure after the write-back and dispatch
> are gone. This confirmation does **not** validate the proposed moving replacement tag; D4 refutes
> that separately.

> **Codex:** **D2 — CONFIRMED.** Quoting becomes a release invariant.
> `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.image` is exactly
> `printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag)`.
> Measured with Helm 3.14.0 and `--set-string image.tag='' --set-string
> ingress.host=review.example.test`, the application container rendered as
> `image: quay.io/ephico2real/group-sync-dashboard:0.7.0` and
> `imagePullPolicy: Always`; no template edit is needed. Temporary Chart.yaml probes found that
> unquoted `0.7.0` happens to remain `0.7.0`, but unquoted `1.0` rendered `:1`, `123` rendered
> `:123`, and `1e6` rendered `:1e+06`. Once the image reference comes from metadata, quoting is no
> longer cosmetic: a numeric-looking release can silently name the wrong registry tag. The full
> replacement for `charts/group-sync-dashboard/values.yaml#image` should preserve the reason for
> the empty value and the immutable override:
>
> ```yaml
> image:
>   # Empty deliberately: gsd.image falls back to Chart.yaml's quoted appVersion, so an
>   # application release is selected in the same PR that declares that release. Set tag to an
>   # immutable <appVersion>-<git-sha> build when a deployment must select one exact commit.
>   repository: quay.io/ephico2real/group-sync-dashboard
>   tag: ""
>   pullPolicy: Always
>
>   # Only needed for a PRIVATE registry. Leave empty for a public repository: an empty
>   # secret reference makes a pod fail to schedule rather than falling back to anonymous
>   # pull, so it must be absent rather than blank.
>   pullSecrets: []
>   # pullSecrets:
>   #   - name: quay-pull-secret
> ```

> **Codex:** **D3 — CONFIRMED.**
> `local-development/tests/test_chart_versions.py#test_the_pinned_image_tag_is_a_build_of_that_same_app_version`
> cannot call `.startswith()` on the intended empty tag and no longer guards a shipped image.
> The real `0.5.2` drift remains directly guarded by
> `test_appversion_equals_the_application_version`; the successor must additionally hold the new
> empty-default chain and the now-load-bearing quotes. This is the full replacement function (it
> needs no new module-level constant):
>
> ```python
> def test_the_unpinned_image_defaults_to_that_same_app_version() -> None:
>     """An empty tag is safe only while the helper and quoted appVersion complete the chain.
>
>     The old assertion held a committed image pin to appVersion. The replacement must fail if a
>     pin quietly returns, if the helper stops using appVersion, or if YAML is allowed to coerce a
>     numeric-looking release such as 1.0 into the registry tag 1.
>     """
>     values = yaml.safe_load(VALUES.read_text())
>     app = _chart()["appVersion"]
>     assert values["image"]["tag"] == "", (
>         "values.yaml must leave image.tag empty so gsd.image selects Chart.yaml appVersion; "
>         "set an immutable tag in a deployment's own values when a commit pin is required"
>     )
>
>     quoted = re.search(r'^appVersion: "([^"]+)"$', CHART.read_text(), re.M)
>     assert quoted and quoted.group(1) == app, (
>         "Chart.yaml appVersion must be double-quoted. An unquoted numeric-looking version is "
>         "coerced by YAML before gsd.image uses it as a registry tag."
>     )
>
>     helpers = (CHART.parent / "templates" / "_helpers.tpl").read_text()
>     fallback = "(default .Chart.AppVersion .Values.image.tag)"
>     assert fallback in helpers, (
>         "values.yaml no longer pins an image, so gsd.image must fall back from an empty "
>         "image.tag to the appVersion held against pyproject.toml by the preceding test"
>     )
> ```
>
> **Codex:** **D4 — REFUTED.** The strongest case against the moving tag survives, but it starts
> one chart later than the premise's example might suggest. The published
> `group-sync-dashboard-0.4.4` artifact contains `tag: "0.7.0-db8a90510f"`; a consumer who installed
> 0.4.4 yesterday and does not upgrade keeps that exact image after the next merge, restart, or
> node drain. `charts/group-sync-dashboard/templates/deployment.yaml` renders the selected string
> into the Deployment, and no later edit of the chart source mutates an installed release.
>
> The hazard begins when that consumer upgrades across the boundary to the first chart whose tag
> is empty. A running container does not change immediately. On its next container creation,
> `charts/group-sync-dashboard/values.yaml#image.pullPolicy` is `Always`, so kubelet resolves
> `:0.7.0` again and that fixed chart release can start the newest merge carrying the alias. A
> rollback, node drain, crash restart, and scale-out are therefore no longer reproducible from the
> chart version. If the policy were `IfNotPresent`, a node that cached the old tagged image could
> run it while a new node pulls the new image, making replicas disagree; that is not this chart's
> default, but it is a worse, node-dependent failure mode rather than a mitigation. `/api/version`
> and `gsd_build_info` diagnose the mutation after it occurs; they do not prevent it.
>
> If the moving alias is retained, digest support should ship in the same change because the change
> is deliberately removing the default's immutability. Even then it protects only consumers who
> opt in; the existing `<appVersion>-<sha>` override already offers an immutable tag without a
> helper change. The better fix is D5: publish the `:<appVersion>` alias once per deliberate app
> release, never on every merge. With a release-only alias, digest support can follow later.

> **Codex:** **D5 — CONFIRMED.** Narrowly: per-merge *building* and publishing the immutable
> `<appVersion>-<sha>` artifact are fine. Per-merge publication of the semantic `:<appVersion>`
> release alias is the root: `.github/workflows/publish.yml#on.push.paths` intentionally runs for
> every image-input merge while `local-development/pyproject.toml` can remain `0.7.0` across many
> such merges. A default of `.Chart.AppVersion` is honest only if `0.7.0` identifies one application
> release. The release boundary should therefore be a human version bump in a PR; ordinary merges
> may still publish the traceable SHA tag for the dev cluster. This full replacement for the
> current `Build, push, and rewrite the chart's image tag` step removes the write-back and publishes
> the semantic alias only on an app-version transition:
>
> ```yaml
>       - name: Build the commit image and publish an application release only on a version bump
>         if: steps.creds.outputs.configured == 'true'
>         shell: bash
>         working-directory: local-development
>         env:
>           REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
>           REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
>           REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
>           REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
>           BEFORE_SHA: ${{ github.event.before }}
>         run: |
>           set -euo pipefail
>           # Every image-input merge keeps a commit-addressed artifact for dev and provenance.
>           # No values rewrite: a build must not manufacture a child commit on protected main.
>           ./build-and-push-external.sh
>
>           # appVersion is a release name, not a rolling branch name. Manual rebuilds and later
>           # merges at the same version must not retarget clusters that already installed it.
>           if [ "${GITHUB_EVENT_NAME}" != "push" ] || [ -z "${BEFORE_SHA}" ] ||
>              [ "${BEFORE_SHA}" = "0000000000000000000000000000000000000000" ]; then
>             echo "No previous main revision is available; published only the immutable tag."
>             exit 0
>           fi
>
>           version=$(python3 -c "import re,pathlib; print(re.search(r'^version = \"(.+?)\"', pathlib.Path('pyproject.toml').read_text(), re.M).group(1))")
>           previous=$(git show "${BEFORE_SHA}:local-development/pyproject.toml" |
>             python3 -c "import re,sys; print(re.search(r'^version = \"(.+?)\"', sys.stdin.read(), re.M).group(1))")
>           if [ "${version}" = "${previous}" ]; then
>             echo "Application version is still ${version}; published only the immutable tag."
>             exit 0
>           fi
>
>           commit=$(git rev-parse --short=10 HEAD)
>           repository="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
>           # This alias is created only by the PR that declares a new application release, so
>           # imagePullPolicy Always remains reproducible instead of turning it into a rollout.
>           podman tag "${repository}:${version}-${commit}" "${repository}:${version}"
>           podman push "${repository}:${version}"
>           echo "released: ${repository}:${version} from immutable ${version}-${commit}"
> ```

> **Codex:** **D6 — REFUTED.** As currently timed, the additional tag can remain only at the chart
> release boundary. Two chart versions that deliberately package the same appVersion may safely
> have two tags pointing to the same digest. The harmful interaction is the current proposed
> placement: if `publish.yml` pushes `:<chartVersion>` on every image-input merge, `:0.4.4` moves
> even though the already-published chart 0.4.4 still pins `0.7.0-db8a90510f`. The visual
> correspondence then states something false. Conversely, a chart-only release never enters
> `.github/workflows/publish.yml#on.push.paths`, so its chart-version tag is absent. A README sentence
> documents a partial mapping but does not satisfy §5's “whenever we ... release to gh-pages.”
>
> Keep the operator's additional tag, but create it exactly once in the ordered chart-release job
> from the appVersion image that the chart packages. This is the full step; it belongs before
> `.github/workflows/helm.yaml#jobs.release.steps[Run chart-releaser]`, after the application-release
> alias is guaranteed to exist (the two independent workflows need an explicit ordering before
> this is safe):
>
> ```yaml
>       - name: Publish the image alias for this chart release
>         shell: bash
>         env:
>           REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
>           REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
>           REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
>           REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
>         run: |
>           set -euo pipefail
>           # A chart-version alias is truthful only when it is stamped from the image the chart
>           # resolves at release time. Rebuilding here would create different application code.
>           app_version=$(sed -nE 's/^appVersion: "([^"]+)"$/\1/p' charts/group-sync-dashboard/Chart.yaml)
>           chart_version=$(sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' charts/group-sync-dashboard/Chart.yaml)
>           test -n "${app_version}" && test -n "${chart_version}"
>           test -n "${REGISTRY_USERNAME}" && test -n "${REGISTRY_PASSWORD}"
>
>           repository="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
>           printf '%s' "${REGISTRY_PASSWORD}" |
>             podman login --username "${REGISTRY_USERNAME}" --password-stdin "${REGISTRY}" >/dev/null
>           podman pull "${repository}:${app_version}"
>           podman tag "${repository}:${app_version}" "${repository}:${chart_version}"
>           podman push "${repository}:${chart_version}"
>           echo "released: ${repository}:${chart_version} is the ${app_version} image packaged by chart ${chart_version}"
> ```

> **Codex:** **D7 — CONFIRMED.** This requires a real status check rather than documentation. The
> automated patch bump bought one chart release for every image build. Under D5 that is no longer a
> benefit: an immutable commit build is not an application release and must not manufacture a chart
> release. Humans retain major/minor/patch meaning; the check retains the mechanical guarantee that
> a changed packaged chart cannot reuse an already-published version. There is no such check in the
> current `.github/workflows/ci.yml` (the only chart job runs lint and strategy render tests), so it
> must land with the deletion. A complete required-check job, excluding the README-only change that
> `.github/workflows/helm.yaml#on.push.paths` already calls a legitimate no-release case, is:
>
> ```yaml
>   chart-version:
>     name: Chart changes bump the chart version
>     if: github.event_name == 'pull_request'
>     runs-on: ubuntu-latest
>     steps:
>       - uses: actions/checkout@v4
>       - name: Chart changes bump the chart version
>         shell: bash
>         env:
>           BASE_SHA: ${{ github.event.pull_request.base.sha }}
>         run: |
>           set -euo pipefail
>           # Fetch the exact reviewed base. Comparing branch names can move underneath a queued
>           # PR and turn a deterministic required check into a race with somebody else's merge.
>           git fetch --no-tags --depth=1 origin "${BASE_SHA}"
>           changed=$(git diff --name-only "${BASE_SHA}" HEAD -- charts/group-sync-dashboard |
>             grep -v '^charts/group-sync-dashboard/README.md$' || true)
>           if [ -z "${changed}" ]; then
>             echo "No packaged chart change; no chart release is required."
>             exit 0
>           fi
>
>           base_version=$(git show "${BASE_SHA}:charts/group-sync-dashboard/Chart.yaml" |
>             sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p')
>           head_version=$(sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' charts/group-sync-dashboard/Chart.yaml)
>           test -n "${base_version}" && test -n "${head_version}"
>           if [ "${base_version}" = "${head_version}" ]; then
>             echo "::error::the packaged chart changed but Chart.yaml is still ${head_version}; chart-releaser would publish nothing"
>             printf '%s\n' "${changed}"
>             exit 1
>           fi
>           echo "chart version: ${base_version} -> ${head_version}"
> ```

> **Codex:** **D8 — CONFIRMED.** I enumerated every file under `.github/workflows/`: `ci.yml`,
> `helm.yaml`, and `publish.yml`. `.github/workflows/ci.yml#permissions` is `contents: read` and has
> no write command. `.github/workflows/helm.yaml#jobs.release` has `contents: write`, but its only
> publishing actor is `helm/chart-releaser-action`, which writes the `gh-pages` chart repository
> and GitHub releases, not `main`. The sole protected-`main` write is the exact
> `git push origin HEAD:main` in `publish.yml`; the associated `actions: write` scope only dispatches
> `helm.yaml`. Deleting both steps leaves no workflow actor that needs to bypass the proposed
> protection on `main`. Therefore neither quoted 422 matters: no user/team restriction or Actions
> allowlist is needed when all changes to `main` arrive through protected PR merges. Existing
> `gh-pages` publishing remains a separate write and is not made a protected target by this design.

> **Codex:** **Overall — worth doing, but not as written.** Remove the write-back and protect
> `main`; the measured failures justify that direction. Do **not** replace the pin with a moving
> default. Keep per-merge `<appVersion>-<sha>` builds, publish `:<appVersion>` once on a deliberate
> application release, and publish `:<chartVersion>` once in the ordered chart release. That keeps
> the decoupling premise without making an installed chart's next restart select unrelated code.
>
> The migration boundary must be explicit in `charts/group-sync-dashboard/README.md` and should be
> echoed conditionally in `templates/NOTES.txt`. A plain upgrade that adopts the new empty default
> switches from the old SHA tag to `:<appVersion>` and recreates the pod because the Deployment
> image string changes. An installation that supplied the old chart's values file, explicitly set
> `image.tag`, or upgrades with `--reuse-values` can retain the old SHA and never adopt the fallback;
> it must deliberately clear `image.tag` (or retain it as an intentional pin). Do not recommend a
> blanket `--reset-values`, because this chart has many safety-relevant operator overrides that it
> would also discard. NOTES cannot distinguish a deliberate immutable override from a stale reused
> default, so it should report that a non-empty `image.tag` bypasses appVersion and point to the
> README migration rather than call every override an error.

> **Codex:** **Measurements.** The render and metadata probes are recorded under D2. The prescribed
> local suite was run without Chromium: `tests/test_live_smoke.py` and `tests/test_ui.py` were both
> explicitly deselected, as required. Result: **1320 passed, 154 deselected, 1 warning in 184.82s**.
> The stated 1469/4 baseline includes the browser module that this review was instructed not to
> launch; no UI test was attempted.

## Cursor — pass 1

<!-- Cursor writes verdicts here, using `> **Cursor:**` markers. -->

> **Cursor:** **Measurements (run before verdicts).** Suite on this tree (branch tip
> `942f647`, chart `0.4.4`, app `0.7.0`):
> `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
> → **1464 passed, 4 deselected, 1 warning in 249.62s** (exit 0). The design's stated
> **1469/4** baseline is stale on this tip; Codex's **1320/154** deselects `tests/test_ui.py`
> as well, so those numbers are not comparable. `tests/test_ui.py` was not re-run here — no
> claim needed Chromium.
>
> Renders (Helm 3.x, `--set ingress.host=example.apps.test`):
>
> | input | dashboard `image:` | `imagePullPolicy` |
> |---|---|---|
> | shipped `tag: "0.7.0-db8a90510f"` | `quay.io/ephico2real/group-sync-dashboard:0.7.0-db8a90510f` | `Always` |
> | `--set image.tag=""` | `quay.io/ephico2real/group-sync-dashboard:0.7.0` | `Always` |
>
> Temp-chart probes (repo untouched): unquoted `appVersion: 0.7.0` + empty tag still rendered
> `:0.7.0` (YAML kept a string); unquoted `appVersion: 0.7` became a float and rendered `:0.7`.
> Sprig `default .Chart.AppVersion .Values.tag` with `tag: ""` yields the AppVersion. Checked.
> `local-development/build-and-push-external.sh` publishes **only** `${VERSION}-${COMMIT}` —
> one `podman push`, no `:<appVersion>` alias exists today.

> **Cursor:** **D1 — CONFIRMED** (attacked; could not break the three named symptoms). Enumerated
> every workflow under `.github/workflows/` (`ci.yml`, `helm.yaml`, `publish.yml`). The only
> `git push origin HEAD:main` is
> `.github/workflows/publish.yml` step `Pin the published tag on main`. That child commit is
> what makes chart-releaser package the *previous* pin (#34), what forces the compensating
> `gh workflow run helm.yaml --ref main` whose tip-vs-pin race published nothing while reporting
> success (#37 — four runs quoted in the workflow comments), and what makes any
> "require PR / block direct push" rule impossible without allowlisting Actions (the two 422s).
> Removing the pin commit removes all three mechanisms. Adjacent, **not** a refutation of D1:
> `helm/chart-releaser-action` with `skip_existing: true` still exits green when a human forgets
> a `Chart.yaml` bump — `.github/workflows/helm.yaml` already warns; that trap predates the pin
> and survives. It is a fourth *failure mode*, not a fourth *cause* of the three symptoms.

> **Cursor:** **D2 — CONFIRMED.**
> `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.image` is already
> `printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag)`.
> Empty tag renders `:0.7.0` with no template edit (table above). What breaks: once the
> registry tag *is* `.Chart.AppVersion`, an unquoted numeric-looking `appVersion` is no longer
> cosmetic — `0.7` → `:0.7`, and (Codex additionally measured) `1.0` → `:1`. Three-part
> `0.7.0` happens to stay a string in PyYAML/Helm today; that is luck, not a contract. Quoting
> must become a tested invariant (see D3). Full replacement for the shipped values block:
>
> ```yaml
> image:
>   # tag is EMPTY on purpose. gsd.image already does
>   #   default .Chart.AppVersion .Values.image.tag
>   # so the chart deploys whatever appVersion this Chart.yaml declares, without a CI commit
>   # rewriting this file. That write-back is what made branch protection impossible and what
>   # shipped a chart two merges stale (#34). Override with an immutable
>   # <appVersion>-<10-char-sha> when a cluster must stay on one build across restarts —
>   # especially while pullPolicy is Always (the default below).
>   repository: quay.io/ephico2real/group-sync-dashboard
>   tag: ""
>   pullPolicy: Always
>
>   # Only needed for a PRIVATE registry. Leave empty for a public repository: an empty
>   # secret reference makes a pod fail to schedule rather than falling back to anonymous
>   # pull, so it must be absent rather than blank.
>   pullSecrets: []
>   # pullSecrets:
>   #   - name: quay-pull-secret
> ```

> **Cursor:** **D3 — CONFIRMED** that the pin test becomes meaningless; the successor below
> replaces it in full. `test_appversion_equals_the_application_version` still catches the
> historical `0.5.2`↔`0.6.0` drift against `pyproject.toml`. What the pin test *also* caught —
> a chart advertising appVersion X while selecting a different build — has no pin left to
> inspect. Deleting it without a render-level successor opens a hole where the helper stops
> falling back, or where quotes are dropped. Prefer a real `helm template` (this repo's
> `tests/test_chart_strategy.py#render` pattern) over a substring on `_helpers.tpl`: a comment
> can satisfy a string search while the define changes. Full replacement for
> `local-development/tests/test_chart_versions.py#test_the_pinned_image_tag_is_a_build_of_that_same_app_version`
> (keep the other three tests in that module; update the module docstring's chain diagram to
> end at `appVersion` rather than `values.yaml image.tag`):
>
> ```python
> def test_empty_image_tag_renders_the_quoted_app_version() -> None:
>     """Successor to the pin-prefix guard: no committed tag means the render IS the contract.
>
>     The deleted test held values.yaml's pin to appVersion. After the pin is removed, the only
>     thing that still selects an image is gsd.image's fallback, and the only thing that keeps
>     that fallback naming a real registry tag is a double-quoted appVersion. A chart that
>     re-introduces a pin, drops the quotes, or stops falling back would install something
>     other than what appVersion advertises — the same quiet lie the 0.5.2 drift was, one
>     layer further out.
>     """
>     import shutil
>     import subprocess
>
>     values = yaml.safe_load(VALUES.read_text())
>     app = _chart()["appVersion"]
>     assert values["image"]["tag"] == "", (
>         "values.yaml must ship image.tag empty so gsd.image selects Chart.yaml appVersion. "
>         "A committed pin re-introduces the write-back this design removes; pin a build in "
>         "the *release's* values (or --set), not in the chart defaults."
>     )
>
>     quoted = re.search(r'(?m)^appVersion: "([^"]+)"\s*$', CHART.read_text())
>     assert quoted and quoted.group(1) == app, (
>         "Chart.yaml appVersion must be double-quoted. Unquoted numeric-looking versions are "
>         "coerced by YAML before gsd.image uses them as a registry tag (measured: 0.7 -> :0.7)."
>     )
>
>     if shutil.which("helm") is None:
>         pytest.skip("helm not installed")
>     done = subprocess.run(
>         [
>             "helm", "template", "t", str(CHART),
>             "--set", "ingress.host=t.example.com",
>             "--set-string", "image.tag=",
>         ],
>         capture_output=True,
>         text=True,
>         check=False,
>     )
>     assert done.returncode == 0, done.stderr
>     expected = f"image: {values['image']['repository']}:{app}"
>     # Match the dashboard container only: oauth-proxy and authLogLevel jobs carry other images,
>     # and template comments can mention the repository string.
>     dashboard_image = None
>     seen_dashboard = False
>     for line in done.stdout.splitlines():
>         stripped = line.strip()
>         if stripped == "- name: dashboard":
>             seen_dashboard = True
>         elif seen_dashboard and stripped.startswith("- name: "):
>             break
>         elif seen_dashboard and stripped.startswith("image:"):
>             dashboard_image = stripped
>             break
>     assert dashboard_image == expected, (
>         f"with an empty image.tag the dashboard must render {expected!r}; got {dashboard_image!r}. "
>         "gsd.image's default .Chart.AppVersion fallback is the only selection path left."
>     )
>
>
> def test_an_explicit_image_tag_still_belongs_to_this_app_version() -> None:
>     """Overrides remain legal; they must still be builds of the declared appVersion.
>
>     Operators pinning <appVersion>-<sha> (the README upgrade path, --reuse-values, local
>     --update-values) must not be able to leave a 0.6.x tag under an appVersion of 0.7.0 —
>     that is the half of the old pin test that remains meaningful when the default is empty.
>     """
>     tag = yaml.safe_load(VALUES.read_text())["image"]["tag"]
>     if tag in ("", None):
>         return
>     app = _chart()["appVersion"]
>     assert tag.startswith(f"{app}-"), (
>         f"values.yaml sets image.tag {tag!r}, which is not a build of appVersion {app!r}. "
>         "Expected empty (chart default) or <appVersion>-<git-sha>."
>     )
> ```
>
> (Add `import pytest` at module scope if not already present.)

> **Cursor:** **D4 — REFUTED.** Strongest case against the moving `:<appVersion>` alias, measured
> against this chart's actual pull policy — not a generic Kubernetes lecture.
>
> 1. **What a 0.4.4 consumer has today.** Published chart `0.4.4` ships
>    `image.tag: "0.7.0-db8a90510f"`. After the *next merge*, with no `helm upgrade`, a pod
>    restart or node drain re-pulls that **same** immutable tag (`pullPolicy: Always` only
>    re-resolves the *string already in the Deployment*). The running release does not see
>    the new moving alias. Codex is right that the hazard is one chart later.
>
> 2. **What changes across the empty-tag boundary.** First upgrade onto a chart whose default
>    `tag` is `""` selects `:<appVersion>` via `gsd.image`. With
>    `charts/group-sync-dashboard/values.yaml#image.pullPolicy: Always` (README table agrees),
>    **every** subsequent container create — crash, drain, liveness kill, scale-out — re-resolves
>    `:0.7.0`. Two merges at app `0.7.0` both move that alias (`build-and-push-external.sh` does
>    not publish it today; the proposal would). The chart version on the cluster stays put while
>    the process binary changes. A reader of `/api/version` learns after the fact; they do not
>    consent. That is exactly the traceability this repo's tag scheme (`<version>-<sha>`, comment
>    in `build-and-push-external.sh`: "Version + immutable tag derived from the commit") was
>    built to forbid.
>
> 3. **`IfNotPresent` is not a mitigation here.** This chart sets `Always`. If it were
>    `IfNotPresent`, a drained node with a cached manifest could keep the old digest while a
>    new node pulled the moved tag — split-brain replicas, worse than uniform silent advancement.
>    Changing pullPolicy is not a free fix for a moving default.
>
> 4. **§6's mitigations do not close it.** Immutable `<appVersion>-<sha>` helps only consumers
>    who **override** the default the chart is about to ship. `/api/version` / `gsd_build_info`
>    diagnose. Digest support is described in future tense and **is not in `gsd.image` today**
>    (helper is tag-only; no `image.digest` in values). So "acceptable given the mitigations"
>    as written is false: the mitigations that actually ship leave Always×moving-default open.
>
> 5. **Digest: same change or later?** If the design insists on a moving `:<appVersion>` default
>    under Always, digest support must ship **in the same change** — otherwise the chart removes
>    the only default immutability path and tells production users to "just --set the sha" while
>    documenting empty→appVersion as the happy path. If instead `:<appVersion>` is published
>    **once per deliberate appVersion bump** (see D5), digest can follow later: the default tag
>    is immutable again and the sha override remains.
>
> **Migration hazard (must be named if the direction proceeds).** Existing releases carry the
> old SHA in the release's values. `helm upgrade` **without** `--reuse-values` adopts the new
> chart default (`""` → `:appVersion`) and will recreate the pod when the image string changes.
> The chart README's current upgrade recipe uses `--reuse-values --set image.tag=<new-tag>`,
> which **keeps** the old pin until the operator clears it — so clusters can stay immutable by
> accident or by intent, and never adopt the fallback. `NOTES.txt` should state that a non-empty
> `image.tag` bypasses appVersion, and the README needs an explicit "upgrading across the
> unpinning" section: either keep the sha pin deliberately, or set `image.tag=""` / omit it to
> take the fallback, knowing Always will then track the alias. Do **not** prescribe blanket
> `--reset-values` — this chart's overrides are safety-relevant.

> **Cursor:** **D5 — REFUTED** as framed ("per-merge publishing is the actual root and should
> change too"). Attacked by separating the layers the claim glues together.
>
> - The **root of the three §2 symptoms** is the write-back to `main`, not the publish cadence.
>   Per-merge `podman push` of `<appVersion>-<sha>` with **no** git commit and **no** moving
>   alias does not recreate #34, #37, or the protection 422s. Measured: that is almost what
>   `build-and-push-external.sh` already does when called *without* `--update-values`.
> - cert-manager's `appVersion` equals its image tag because it cuts **one image per release**.
>   That analogy argues against a *moving* `:<appVersion>` default, not against per-merge
>   immutable artefacts. Conflating them over-sells "stop publishing per merge."
> - The honest refute offered in the claim — "per-merge is fine once nothing writes to main;
>   the moving tag is the whole cost" — is **directionally right** about the symptoms, and
>   **understates** the moving-tag cost under `pullPolicy: Always` (D4). The cost is not "the
>   whole cost" of keeping per-merge; it is an independent product decision about what the
>   chart default selects.
>
> Adequate shapes, all compatible with removing the pin:
> 1. Per-merge SHA only; empty tag → appVersion; publish `:<appVersion>` **only** when
>    `pyproject.toml` / `appVersion` changes (Codex's workflow). Default becomes honest again.
> 2. Per-merge SHA only; **no** `:<appVersion>` alias; chart default stays empty→appVersion
>    only after a human release job creates the alias; until then installs fail-fast on pull.
> 3. Keep Always + require an explicit sha in values (reject empty) — abandons the cert-manager
>    fallback, keeps this repo's immutability prior, still deletes the write-back.
>
> So: change the **alias cadence** (or the default), not "per-merge publishing" as such.
> Refuting D5's root claim does not defend today's pin.

> **Cursor:** **D6 — FIX-INADEQUATE** (operator ruling that the additional `:<chartVersion>` tag
> is in is respected; the "no harmful interaction" claim is not). Two chart versions packaging
> the same appVersion may both label one digest — fine. The holes:
>
> - If `publish.yml` stamps `:<chartVersion>` on every image-input merge while `Chart.yaml`
>   version is unchanged, **`:0.4.4` moves** even though published chart `0.4.4` still pins
>   `0.7.0-db8a90510f`. The "correspondence a human can check by eye" becomes a lie about
>   already-released charts.
> - A chart-only release (templates/defaults, no path in
>   `.github/workflows/publish.yml#on.push.paths`) never builds an image, so `:<newChartVersion>`
>   is absent unless something in the **chart release** job retags. §5's "whenever we … release
>   to gh-pages" is not satisfied by publish.yml alone.
>
> Full step that closes both, owned by `.github/workflows/helm.yaml` immediately before
> chart-releaser (retags from the immutable app image the chart resolves — SHA override if
> present, else the release alias). Credentials same pattern as publish.yml:
>
> ```yaml
>       - name: Publish the image alias for this chart version
>         shell: bash
>         env:
>           REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
>           REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
>           REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
>           REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
>         run: |
>           set -euo pipefail
>           # WHY HERE AND NOT IN publish.yml. publish.yml's path filter ignores charts/**, so a
>           # template-only release never runs it — :0.5.0 would simply not exist while helm
>           # search showed chart 0.5.0. Stamping at chart-releaser time makes the alias mean
>           # "the image this chart version resolves", including chart-only bumps that repackage
>           # the same appVersion. Retag, do not rebuild: a rebuild here would silently ship
>           # different bits under a chart version that claimed to package an existing app.
>           if [ -z "${REGISTRY_USERNAME}" ] || [ -z "${REGISTRY_PASSWORD}" ]; then
>             echo "::error::REGISTRY_USERNAME / REGISTRY_PASSWORD required to stamp :chartVersion"
>             exit 1
>           fi
>           app_version=$(sed -nE 's/^appVersion: "([^"]+)"$/\1/p' charts/group-sync-dashboard/Chart.yaml)
>           chart_version=$(sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' charts/group-sync-dashboard/Chart.yaml)
>           tag=$(python3 - <<'PY'
>           import pathlib, re
>           text = pathlib.Path("charts/group-sync-dashboard/values.yaml").read_text()
>           m = re.search(r'(?m)^  tag: "?([^"\n]*)"?$', text)
>           print(m.group(1) if m else "")
>           PY
>           )
>           # Empty tag → the appVersion release alias; a remaining sha pin → that exact build.
>           source_tag="${tag:-$app_version}"
>           test -n "${app_version}" && test -n "${chart_version}" && test -n "${source_tag}"
>           repository="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
>           printf '%s' "${REGISTRY_PASSWORD}" |
>             podman login --username "${REGISTRY_USERNAME}" --password-stdin "${REGISTRY}" >/dev/null
>           podman pull "${repository}:${source_tag}"
>           podman tag "${repository}:${source_tag}" "${repository}:${chart_version}"
>           podman push "${repository}:${chart_version}"
>           echo "stamped: ${repository}:${chart_version} <- ${repository}:${source_tag}"
> ```
>
> README sentence still required: `:<chartVersion>` exists only for versions this job has
> stamped after the change; historical `0.4.x` chart versions were never aliased.

> **Cursor:** **D7 — CONFIRMED.** The automated patch bump bought one thing only: a new chart
> version for every pin, so chart-releaser had something to publish. Delete the pin and that
> purchase is worthless — and harmful if kept (chart noise for non-template merges). Major/minor
> meaning stays human. What must not be lost: the mechanical refusal to merge a packaged-chart
> change that reuses an already-released `version:`. There is no such job in `ci.yml` today.
> Copying the operator-repo check is required **in the same change** as deleting the bump;
> documentation alone re-opens the silent-green skip_existing path. Codex's
> `chart-version` job body is adequate; require that check name on `main`. Full job (same
> substance, README-only carve-out preserved because helm.yaml already treats README-only as a
> legitimate no-release):
>
> ```yaml
>   chart-version:
>     name: Chart changes bump the chart version
>     if: github.event_name == 'pull_request'
>     runs-on: ubuntu-latest
>     steps:
>       - uses: actions/checkout@v4
>       - name: Chart changes bump the chart version
>         shell: bash
>         env:
>           BASE_SHA: ${{ github.event.pull_request.base.sha }}
>         run: |
>           set -euo pipefail
>           # Compare against the PR's base sha, not origin/main's moving tip: a queued PR must
>           # not go red because an unrelated merge moved main between open and check.
>           git fetch --no-tags --depth=1 origin "${BASE_SHA}"
>           changed=$(git diff --name-only "${BASE_SHA}" HEAD -- charts/group-sync-dashboard |
>             grep -v '^charts/group-sync-dashboard/README.md$' || true)
>           if [ -z "${changed}" ]; then
>             echo "No packaged chart change; no chart version bump required."
>             exit 0
>           fi
>           base_version=$(git show "${BASE_SHA}:charts/group-sync-dashboard/Chart.yaml" |
>             sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p')
>           head_version=$(sed -nE 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' \
>             charts/group-sync-dashboard/Chart.yaml)
>           test -n "${base_version}" && test -n "${head_version}"
>           if [ "${base_version}" = "${head_version}" ]; then
>             echo "::error::packaged chart files changed but Chart.yaml version is still ${head_version}."
>             echo "::error::chart-releaser would publish NOTHING and still report success."
>             printf '%s\n' "${changed}"
>             exit 1
>           fi
>           echo "chart version: ${base_version} -> ${head_version}"
> ```

> **Cursor:** **D8 — CONFIRMED.** Re-checked every file in `.github/workflows/` immediately
> before this verdict:
>
> | file | writes `main`? | other writes |
> |---|---|---|
> | `ci.yml` | no (`permissions: contents: read`) | none |
> | `helm.yaml` | no | `chart-releaser` → `gh-pages` + GitHub release tags |
> | `publish.yml` | **yes** — `git push origin HEAD:main` | `actions: write` only to dispatch helm |
>
> After deleting the pin push (and its dispatch), **no** workflow actor must write to `main`.
> The two 422s are irrelevant: no Actions allowlist and no org-only push restriction is
> required when every `main` update is a protected PR merge. `gh-pages` remains a separate
> writable ref; this design does not claim to protect it. If a future workflow gains a
> `main` write, D8 collapses — the justification is the enumeration, not the aspiration.
> `local-development/build-and-push-external.sh --update-values` still rewrites a working
> tree on a laptop; that is not an Actions push to `main` and does not block protection.

> **Cursor:** **Overall — remove the pin; do not ship Always × per-merge moving `:<appVersion>`
> as written.** Worth doing: delete the write-back, add the required chart-version check,
> protect `main` (PRs required, admins included). That alone retires #34/#37/protection. Not
> worth doing as proposed: replacing the pin with a default that silently advances under
> `imagePullPolicy: Always` on every restart. Publish `:<appVersion>` on appVersion bumps
> only (or require explicit sha pins); stamp `:<chartVersion>` from the chart-release job;
> put the migration hazard in README + NOTES. "The pin is fine, protect less" is a worse
> conclusion — the measured costs include a published chart that omitted a data-exposure fix.
>
> **Debt.** DEBT-INTRODUCED: `tests/test_publish_pin_step.py` and publish.yml's pin/dispatch
> steps become dead weight and must go with the change; leaving them tests the abandoned
> design. DEBT-ACCEPTED: digest support deferred *only if* `:<appVersion>` is release-scoped
> (otherwise it is FIX-INADEQUATE to defer). DEBT-AVOIDED: not keying `gsd.image` on
> `.Chart.Version`. The debt is worth the feature if and only if the moving-default hole is
> closed in the same change as the unpinning.

---

## Arbitration (Claude, after both passes)

Both reviewers converged on every material point. **The design as written did not survive**: its
central mechanism — a moving `:<appVersion>` default — was refuted by both, and the operator's
additional chart-version tag was placed in the wrong workflow. Both prescribed the same remedies,
with full replacement steps, so what follows is their prescription rather than a new invention.

| claim | Codex | Cursor | ruling |
|---|---|---|---|
| D1 one cause, removing the write-back fixes all three | CONFIRMED | CONFIRMED | adopted |
| D2 no template change needed | CONFIRMED | CONFIRMED | adopted |
| D3 the pin test needs a successor | CONFIRMED | CONFIRMED | adopted, shape below |
| D4 moving `<appVersion>` default is acceptable | **REFUTED** | **REFUTED** | **rejected** |
| D5 per-merge publishing is the root | CONFIRMED | **REFUTED** as framed | Cursor's framing adopted |
| D6 chart-version tag is harmless | **REFUTED** | **FIX-INADEQUATE** | tag kept, **placement moved** |
| D7 the automated chart bump can be deleted | CONFIRMED | CONFIRMED | adopted |
| D8 protection becomes possible | CONFIRMED | CONFIRMED | adopted, sequenced last |

### D4 — rejected, on evidence the design should have gathered

`charts/group-sync-dashboard/values.yaml#image.pullPolicy` is **`Always`**. With an empty tag, every
container creation — crash, drain, liveness kill, scale-out — re-resolves `:<appVersion>`, so the
process binary can change while the chart version on the cluster stays put. Cursor: *"A reader of
`/api/version` learns after the fact; they do not consent."*

Three corrections to this document, all mine:

1. **The digest mitigation was fiction.** §6 offered digest pinning as a mitigation; `gsd.image` is
   tag-only and there is no `image.digest` in values. So "acceptable given the mitigations" was
   false as written.
2. **The blast radius was overstated in one direction.** An existing chart-0.4.4 consumer keeps
   `0.7.0-db8a90510f`: the Deployment holds the resolved string and no chart edit mutates an
   installed release. The hazard begins one chart *later*, on the first upgrade onto an empty-tag
   chart. Both reviewers corrected this independently.
3. **`IfNotPresent` is not a fallback.** A drained node with a cached manifest keeps the old digest
   while a new node pulls the moved tag — split-brain replicas, strictly worse.

**Supporting evidence neither reviewer was given:** `local-development/release-crc.sh` states this
repo's own rule — *"a given `<version>-<sha>` tag always means the same source. Pushing a different
image under an existing tag is refused rather than silently overwritten."* A moving alias cannot
honour that by construction.

**RULING: the `:<appVersion>` alias is published only when `appVersion` changes** — a human bump in a
PR. Ordinary merges publish the immutable `<appVersion>-<sha>` only. The chart's default is then
immutable again, and digest support may follow later instead of blocking this change.

### D5 — Cursor's framing adopted

The root of the three §2 symptoms is the **write-back to `main`**, not the publish cadence. Cursor
measured that per-merge sha pushes with no commit and no alias recreate none of #34, #37, or the
protection 422s. D5 as written conflated "per-merge publishing" with "per-merge *alias* publishing";
only the second is the problem, and D4's ruling already fixes it. Per-merge immutable builds stay.

### D6 — the operator's tag is kept; its placement was wrong

Both refused "no harmful interaction", and neither refused the tag itself. In `publish.yml` it would
stamp `:<chartVersion>` on every image-input merge while the already-published chart of that version
still pinned an older image — the correspondence would be a lie about released charts. And a
chart-only release never enters `publish.yml`'s path filter, so its tag would simply be absent.

**RULING: create it in `helm.yaml`, immediately before chart-releaser, by RETAGGING** the image the
chart resolves. Never rebuild — a rebuild there would ship different bits under a chart version
claiming to package an existing app.

### The one thing neither reviewer designed

Codex flagged that `publish.yml` and `helm.yaml` are independent, so the retag can run before the
alias exists, and left the ordering open. **RULING: no cross-workflow orchestration.** `helm.yaml`
verifies the image it is about to retag exists, and fails loudly with the manual command if not.
This repo already knows what cross-workflow timing assumptions cost: #37 was exactly that, and its
failure reported `success`. A missing image must be a red run, not a silent skip.

### Operator constraints, carried into implementation

1. **`build-and-push-external.sh --update-values` is preserved verbatim.** The local/enterprise path
   genuinely needs a pin — someone building into their own registry must point the chart at their
   own image. Only `publish.yml`'s *use* of the flag goes. Cursor independently measured that the
   script called without it already behaves correctly.
2. **The local path must remain a complete substitute for CI**, because it is the disaster-recovery
   route when Actions is down. The script therefore gains `--release-tags` (default OFF) to publish
   the alias tags too. Default off because a routine laptop build pushing `:<appVersion>` would
   overwrite the canonical alias, which is D4's hazard one layer down.
3. **Humans must be able to run and understand this.** `publish.yml` and its test file are
   rewritten from `-backup` copies rather than edited, because 57% of that workflow is machinery for
   a defect class that will no longer exist, and its comments document races that will be gone.

### D3 — the successor test

The original asserted the pinned tag's prefix equals `appVersion`. With `tag: ""` there is nothing to
check, but deleting a guard that caught a real drift (`appVersion` read `0.5.2` for weeks) needs a
successor. Shape: **`image.tag` is either empty — the chart resolves `.Chart.AppVersion` — or, if
set, its prefix must equal `appVersion`.** That passes on the committed empty value, still catches
the original drift, and does not red the suite for a developer mid-`--update-values`.

### Protection, sequenced last

Measured alternatives, recorded so the choice is on evidence:

| option | direct push blocked | force-push/deletion blocked | CI gate | credential risk |
|---|---|---|---|---|
| today | no | yes (admins too) | no | none |
| PAT + `enforce_admins: false` | non-admins only | **no** — admins exempt | yes | long-lived PAT |
| bot PR + API merge | yes, everyone | yes | no | none |
| **this change** | yes, everyone | yes | yes | none |

The middle two were proven by probe: with `enforce_admins: false` an admin push past a PR
requirement **succeeded**; with `true` it was **rejected** (`protected branch hook declined`).
Protection is applied only AFTER a real publish run proves nothing needs to write to `main` —
applying it first would mean discovering a missed writer by having a release fail.
