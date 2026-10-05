# #598 on the lab: the first promotion, and the lab on `release` and back, 2026-10-05

**Outcome.** #614 merged at `cb832a6a69` (application 5.2.0, chart 0.70.3). The first real promotion went as SPEC_P1
says, and SPEC_P1 §5's lab check passed. The PVC UIDs were the same throughout
(`evidence/run.log`, `evidence/promotion.txt`).

## The first promotion
- **The push run** (`37252212147`, at 01:38:25Z) started before publish.yml had pushed the images. It printed the
  designed notice and wrote nothing: "immutable image `…:5.2.0-cb832a6a69` is not ready; its successful publish run
  promotes main".
- **The publish-completion run** (`37252414796`, at 01:41:30Z) promoted.
  - It pushed `1f3c3303..2cca5d78 -> release`. This was the deploy key's first real push through the ruleset, as a
    plain fast-forward.
  - `release` is now `2cca5d78`, "promote: main cb832a6a…". It holds exactly `charts`, `environments` and
    `promotion.yaml`.
- **`promotion.yaml` pins each image by digest, and the registry agrees.** `oc image info …:5.2.0`, read for
  linux/amd64, gives the same digests:

  | Image | Digest |
  |---|---|
  | dashboard | `sha256:cfd0cd28…` |
  | report | `sha256:2172be1b…` |

## The lab, switched to `release` and back
1. **Before.** Argo CD deployed 5.2.0 from `main`. It was Synced and Healthy at 01:43:06Z, both pods were Ready, and
   there were 0 restarts.
2. **`release-crc.sh --argocd release`** (01:43:53Z to 01:44:56Z).
   - It read both pinned digests back as application 5.2.0, then pointed the Application at `release` (`2cca5d78`).
   - The Application read `targetRevision: release` and `valueFiles [../../environments/crc.yaml,
     ../../promotion.yaml]`, Synced and Healthy.
   - **The running pods' image IDs are exactly the pinned digests:** `…dashboard@sha256:cfd0cd28…` and
     `…report@sha256:2172be1b…`.
3. **`release-crc.sh --argocd main`** (01:45:15Z to 01:46:18Z) put the development default back.
   - The Application read `targetRevision: main` and `valueFiles [../../environments/crc.yaml]` at `cb832a6a`, Synced
     and Healthy.
   - The dashboard answered 5.2.0 at `cb832a6a69`, and the pods ran the `:5.2.0` tags, which resolve to the same
     digests.

**The PVC UIDs** were unchanged before and after: data `f065b7a4-…`, report-artifacts `08c7d45c-…`, offsite
`7f505595-…`.

## Recorded elsewhere
- **The one-time GitHub setup** is in `docs/RELEASE_BRANCH_SETUP.md`, with the record of 2026-10-05: the deploy key,
  the environment and its secret, the empty branch, and the ruleset with a deploy-key bypass. A hand push to `release`
  was refused with GH013.
- **Seen, not ours:**
  - an `oc exec` into the dashboard container printed two `ld.so` errors, both for Dynatrace's `liboneagentproc.so`;
  - one came from `LD_PRELOAD`, the other from `/etc/ld.so.preload`;
  - both were ignored.
  So Dynatrace, installed on the CRC at 22:48:31Z on 2026-10-04, is injecting into this namespace's pods without its
  library. These lines are removed from `evidence/run.log`.

| Path | Contents |
|---|---|
| `evidence/promotion.txt` | the two promote runs, the push run's notices, the publish run's prepare and push and promoted lines, `release`'s log and tree, `promotion.yaml`, and the registry digests |
| `evidence/run.log` | `release-crc.sh --argocd release`, then `--argocd main`, with the Application, the pods' image IDs and the PVC UIDs |
