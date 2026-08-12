# Releasing

Two artefacts, two cadences, and they are only related at two moments. That sentence is the whole
model, and everything below is a consequence of it.

| artefact | version | changes when | published to |
|---|---|---|---|
| the application | `pyproject.toml` `version` | the app changes and you decide to ship it | quay.io |
| the chart | `Chart.yaml` `version` | the templates or defaults change | gh-pages |

They meet only here:

- **`Chart.yaml` `appVersion`** names the application release the chart deploys. Held to
  `pyproject.toml` by `tests/test_chart_versions.py`.
- **A chart change forced by an app change** — a new value, a template that has to render something
  new. Then both move, in the same PR.

Nothing else couples them. A patch to the app does not touch the chart. A template fix does not
pretend the app changed.

---

## The whole flow

Every merge goes through one gate, then fans out to two independent workflows:

```
   pull request
        |
        |   ci.yml:  tests(3.11) · tests(3.14) · chart · diagrams · image
        |            "Chart changes bump the chart version"
        v
   merge to main
        |
        +---------------------------+
        |                           |
        v                           v
   publish.yml                 helm.yaml
   THE IMAGE                   THE CHART
   (below)                     (below)
```

**`publish.yml` — the image. It writes to nothing in this repository.**

```
   did an image input change?
   gsd/** · pyproject.toml · README.md · Containerfile · .containerignore · build script
        |
        +-- no --> nothing published
        |
       yes
        |
        v
   did pyproject `version` change since the previous commit?
        |
        +-- no ---> push  :0.7.0-abc1234567          IMMUTABLE, every merge.
        |                                            The dev cluster and anyone
        |                                            who wants a byte-pin.
        |
        +-- yes --> push  :0.7.0-abc1234567    and
                    push  :0.7.0                     THE ALIAS. Releases only.
                                                     This is what the chart
                                                     resolves by default.

   cannot tell? (workflow_dispatch, first push, unreadable base)
        --> immutable tag only, plus a ::warning:: naming --release-tags
```

**`helm.yaml` — the chart.**

```
   did charts/** change?
        |
        +-- no --> nothing published
        |
       yes
        |
        v
   does the image the chart resolves actually exist?
   (its image.tag pin if set, otherwise :<appVersion>)
        |
        +-- no --> RED RUN. Names the manual command. Deliberately not a wait:
        |          #37 was a cross-workflow timing assumption, and it reported
        |          success while publishing nothing.
        |
       yes
        |
        v
   skopeo copy  ->  :0.5.0        label the image this chart version deploys.
        |                          RETAG, never rebuild.
        v
   chart-releaser  (skips a version it has already released)
        |
        v
   gh-pages:  index.yaml + group-sync-dashboard-0.5.0.tgz
```

**Read the two `rel` branches carefully — they are the part people get wrong.** An ordinary merge
publishes an immutable tag and nothing else. The alias the chart actually resolves moves only when a
human changed the application version.

---

## Three tags, and why there are three

```
  quay.io/ephico2real/group-sync-dashboard
  ┌──────────────────────┬───────────┬──────────────────┬─────────────────────────────┐
  │ tag                  │ mutable?  │ pushed when      │ who it is for               │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.7.0-f9fa896778     │ NEVER     │ every merge that │ you, when you need          │
  │                      │           │ touches an image │ byte-identical rollbacks.   │
  │ <appVersion>-<sha>   │           │ input            │ Always this exact source.   │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.7.0                │ moves on  │ only when a      │ THE CHART, by default.      │
  │                      │ an APP    │ human bumps      │ image.tag is "" and         │
  │ <appVersion>         │ release   │ pyproject version│ gsd.image resolves this.    │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.5.0                │ moves on  │ at chart-release │ a human asking "which       │
  │                      │ a CHART   │ time, by retag   │ image does chart 0.5.0      │
  │ <chartVersion>       │ release   │ (never a build)  │ deploy?"                    │
  └──────────────────────┴───────────┴──────────────────┴─────────────────────────────┘

  what the chart deploys, in order of precedence:

      --set image.tag=0.7.0-f9fa896778   ─┐
                                          ├─►  an exact, immutable image
      values.yaml  image.tag: "<pin>"    ─┘

      values.yaml  image.tag: ""         ───►  :<appVersion>   ← the shipped default
                                               resolved via
                                               default .Chart.AppVersion .Values.image.tag
```

`values.yaml` ships `image.tag: ""`, and `gsd.image` resolves `default .Chart.AppVersion`. So the
chart deploys `:<appVersion>` unless you say otherwise.

**`imagePullPolicy` is `Always`**, which is why the distinction matters rather than being pedantry:
every container creation re-resolves the tag. On the immutable form that is a wasted round trip and
nothing else. On an alias it means a republished image is picked up on the next crash, drain,
liveness kill or scale-out. That is exactly why the alias is not republished per merge —
`docs/DESIGN_decouple_chart_and_app_release.md` records the review where both reviewers refused a
design that did.

**Pin when you need byte-identical rollbacks:**

```sh
helm upgrade ... --set image.tag=0.7.0-f9fa896778
```

---

## How to cut a release

### An application release

1. Bump `version` in `local-development/pyproject.toml`.
2. Bump `__version__` in `local-development/gsd/__init__.py` to match — it is what `/api/version` and
   `gsd_build_info` report, and a test holds the two together.
3. Bump `appVersion` in `charts/group-sync-dashboard/Chart.yaml` to match.
4. Bump `Chart.yaml` `version` too, because you just changed the chart. `ci.yml` will fail the PR if
   you forget.
5. Open the PR, merge it. `publish.yml` sees the version change and publishes both the immutable tag
   and the `:<appVersion>` alias.

All three version edits land in one PR, or CI is red. That is the coupling working, not friction.

### A chart-only release

Change the templates or defaults, bump `Chart.yaml` `version`, open the PR, merge. No image is
built — `charts/**` is deliberately absent from `publish.yml`'s path filter — and `helm.yaml` retags
the existing image under the new chart version.

### Neither

An ordinary code merge. An immutable `<appVersion>-<sha>` image is published for traceability and
for the dev cluster. **Consumers see nothing**, because the chart still resolves the previous
appVersion. That is the deliberate-release model: merging is not shipping.

---

## When GitHub Actions is unavailable

The script CI calls is the same one you run by hand, which is the point:

```sh
cd local-development
./build-and-push-external.sh                  # immutable sha tag only
./build-and-push-external.sh --release-tags    # ALSO the appVersion and chartVersion aliases
```

`--release-tags` is what makes a laptop a complete substitute for the pipeline. It is **off by
default** because a routine local build pushing `:<appVersion>` would quietly become the image every
consumer runs on their next restart. It **refuses a dirty tree**: the sha tag is honest about being
unreproducible, and an alias named for a version cannot be.

`--update-values` is the other local path, and it is unrelated to releasing. It writes a pin into
your working copy of `values.yaml`, which is what you want when you build into your own registry — a
fork, an air-gapped mirror — and need the chart pointing at your image rather than ours. CI never
uses it.

---

## What can go wrong, and what it looks like

| symptom | cause | fix |
|---|---|---|
| chart release run is red at "Label the image this chart version deploys" | the image the chart resolves was never published, so there is nothing to retag | run `./build-and-push-external.sh --release-tags` from a clean checkout, then re-run the release |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
| a new pod runs different bits than its neighbour | somebody republished an alias between the two container creations | pin `image.tag` to the sha form |
| `ImagePullBackOff` on a fresh install | the `:<appVersion>` alias does not exist for the chart's declared appVersion | the app release was never published. Check `publish.yml`, then use `--release-tags` |

**The historical failures are worth knowing, because two of them reported success.** #34 published a
chart pinning an image two merges old — including a release that was missing a data-exposure fix.
#37 published nothing at all while its run went green. Both came from CI writing the image pin back
to `main`, which is the thing this design removed. When a release step here cannot do its job it goes
**red and names the command**, deliberately, because a green run that shipped nothing is the failure
mode this repo has paid for most.
