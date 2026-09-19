# MacBook Migration Runbook — group-sync-dashboard + CRC lab

Execution-ordered. Old machine is an **Intel Mac** (`/usr/local`, `darwin/amd64`, CRC bundle
`crc_vfkit_4.18.2_amd64`). A new **Apple Silicon** Mac uses `/opt/homebrew` and arm64 CRC/podman
bundles — **versions transfer, binaries do not**. Do the steps in order; do not skip the "Before you
move" section — several items exist in exactly one place and are gone the moment the disk is wiped.

Convention used below:

```sh
DASH=/Users/olasumbo/gitRepos/group-sync-dashboard        # old machine
SP=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/4431debc-da47-459e-96d7-9fa404508f41/scratchpad
KEEP=~/migration-carry                                     # off-machine transfer folder (USB / encrypted volume)
```

---

## 1. Executive summary

- **Transfers by `git clone`:** all committed/pushed history in the four repos — the C3 reporting
  microservice is merged to `origin/main`; the app chart (0.32.0 / app 0.24.0), `release-crc.sh`,
  `environments/crc.yaml`, the mock-app source, and the specs/tests/session-changelogs are all in git.
- **At risk (exists in one place only):** the **uncommitted** `environments/crc.yaml` edit (67 insertions)
  and **`stash@{0}`** (a separate 36-line crc.yaml WIP); 6 project-memory notes newer than the
  claude-config backup; and the session scratchpad (`mock-certmanager.yaml`, review briefs, bespoke
  scripts) — which `/private/tmp` will wipe on a reboot, **not just on the move**.
- **Single most important pre-move action:** get the two unrecoverable things off the machine — the
  uncommitted `crc.yaml` working-tree edit and `stash@{0}`. Neither comes back with a clone.
  `local-development/.env` is **not** one of them; see §2.1.
- **A new CRC is rebuilt from scratch.** The 64 GB VM, the mock cluster, the cert-manager chains, the
  LDAP lab, cluster-wide trust, and the dashboard's `mock-creds` volume patch are **live-only** and
  mostly reproduced by **no committed manifest**. `release-crc.sh` deploys **only** the dashboard +
  report images — it is not "the whole lab". Rebuild is a deliberate, ordered sequence (§4).
- **Nothing SSH/keychain-based copies as a file:** the `gh` token, git push cred, cursor/codex logins,
  and the CRC pull secret are all re-established by logging in / re-downloading on the new Mac.

---

## 1b. The whole move at a glance — every step, and how it runs

Read this table first. **Script** means a command you run and it does the work. **Manual** means you
type or click it and there is no way around that, usually because it is interactive or a browser login.
**Hand-edit** means you write a file yourself.

### On this Mac, before you move

| # | Step | How | What it is |
|---|---|---|---|
| 2.0 | make the carry folder | Manual | one `mkdir` |
| 2.1 | registry credentials | **nothing to do** | corrected: they are not carried. See `docs/handoff/registry-credentials.md` |
| 2.2 | commit and push at-risk edits | Manual | `git add` / `commit` / `push` per repo. Already done for the dashboard, the RBAC automation and the NCO fork on 2026-09-18 |
| 2.3 | refresh the claude-config backup | **done** | closed 2026-09-18; re-run only if you work more before moving |
| 2.4 | copy local-only scratchpad files | Manual | `cp`; most of it is already committed |
| 2.5 | copy the optional login shortcuts | Manual | `cp` of `~/.ssh`, codex auth, containers auth |
| 2.6 | record where secrets live | Hand-edit | a note in the password manager. **Locations only, never values** |
| 2.7 | record tool versions | **Script** | one command writes the version snapshot |

### On the new Mac

| # | Step | How | What it is |
|---|---|---|---|
| 4.1 | install the tools | Manual | `brew install` lines, plus three that are NOT brew: codex (npm), cursor (vendor script), CRC (a `.pkg` you download) |
| 4.2 | log in to each tool | Manual | `gh auth login`, `podman login quay.io`, `codex`/`cursor` logins, SSH key. All interactive by design |
| 4.3 | clone the repos | Manual | `git clone` per repo |
| 4.4 | restore working state | Manual | check out the pushed branches, or apply the two carried patches |
| 4.5 | rebuild the venv and Playwright | **Script** | one block; no decisions |
| 4.6 | rebuild CRC | Manual | `crc config set` lines then `crc start`. **Sized for the M5 Pro 18-core / 64 GB — see §4.6** |
| 4.6b | operators and monitoring | Manual | OperatorHub installs; monitoring is ON now that the machine can carry it |
| 4.7 | cert-manager operator | Manual | subscription plus the ClusterIssuer pair |
| 4.8 | deploy the app | **Script** | `release-crc.sh` — builds, pushes, deploys and verifies the commit in-pod. The one fully automated step |
| 4.9 | re-apply the mock cluster | **Script** | `deploy-mock.sh` — was the slowest manual part of the move until 2026-09-18; now one command, with `--verify` |
| 4.9b | application namespaces and hand-made grants | **Script** | three `oc apply` lines and two labels; everything the dashboard's tabs and the NCO policies act on |
| 4.10 | LDAP lab and cluster trust | Manual | only if you need LDAP. `setup-local-ldap-testing/` plus `MISSING-STEPS.md` for what the seeds do not create |
| 4.3b | restore the Claude Code setup | **Script** | two scripts in order: the repo root's `restore.sh`, then `2026-09-18-design-programme/restore.sh`. Proven against an empty home |
| 5 | verification | **Script** | the check block, then `capture-screenshots.py` for the pictures |

### The three scripts that do the heavy lifting

| Script | Run it when | It does |
|---|---|---|
| `claude-config/.../restore.sh` | after cloning claude-config | agents, tools, settings with the hook path re-keyed, and the memory notes. Safe to run twice |
| `local-development/registry-creds.sh` | in any shell that pushes an image | exports the registry credentials from your `podman login`. Source it; it prints nothing |
| `local-development/release-crc.sh` | after CRC is up | builds both images, pushes to the internal registry, deploys, and verifies the running commit |

### What genuinely cannot be scripted

Browser logins (Red Hat pull secret, `gh auth login`, Quay), the CRC `.pkg` install, and §4.9's mock
cluster, which has no committed manifest for the backend Deployment and Service. Everything else is
either a script above or a short block you paste.

## 2. Before you move (on THIS Mac) — ordered checklist

### 2.0 — Make the carry folder

```sh
mkdir -p "$KEEP"        # put this on an encrypted USB / external volume, not iCloud
```

### 2.1 — `local-development/.env` does NOT need carrying (corrected 2026-09-18)

An earlier version of this runbook called this file the top secret and the single most important
pre-move action. That was an overstatement. Of its seven keys, five have defaults in tracked files
(`REGISTRY` and `REGISTRY_NAMESPACE` in `.github/workflows/helm.yaml`; `IMAGE_NAME` and
`K8S_NAMESPACE` in `local-development/build-and-push-external.sh`; `IMAGE_PULL_SECRET` empty because
the quay repository is public). The two that are real secrets already exist as **GitHub repository
secrets**, so CI never depended on this laptop; their values cannot be read back, and do not need to
be, because a Quay robot token is re-mintable on demand — which is the point of a robot account.

So on the new Mac there is no file to restore. Log in once, then source the shim in any shell that
needs to push:

```sh
podman login quay.io                          # once per machine; the only secret you ever type
. ./local-development/registry-creds.sh       # exports the variables; prints nothing
./local-development/build-and-push-external.sh
```

`registry-creds.sh` reads the credential that login stored and exports it under the **same names as
the GitHub repository secrets** (`REGISTRY_USERNAME`, `REGISTRY_PASSWORD`), so a script reads
identically in CI and on a laptop: in CI the workflow injects them, here the shim fills them. If they
are already set it leaves them alone and never touches the store. `--check` reports what it found with
the token masked to a length; `--login` logs podman in.

Measured 2026-09-18: sourcing it prints **0 bytes**; the credential it exports exchanged a quay.io
token for `pull,push` on `quay.io/ephico2real/group-sync-dashboard`, **HTTP 200**; and
`build-and-push-external.sh` then reported `config : environment only (no .env found)` and proceeded
past credential resolution.

**No `.env` is written.** The credential lives in podman's store, where the login already put it, and
in process memory for the life of one shell. A `.env` would be a second copy at rest that can drift,
be committed by accident, or outlive a revoked token. Keeping one is still supported —
`build-and-push-external.sh` reads it, and the environment wins where both set a value — but it is no
longer the documented path and nothing needs to be carried between machines.

The CRC internal registry needs nothing from here at all: `release-crc.sh` authenticates with
`podman login -u kubeadmin -p "$(oc whoami -t)"`, a token minted at login.

Storing the credentials by hand, storing them in GitHub with `gh`, keeping the `gh` session
authenticated, and rotating the token are all in `docs/handoff/registry-credentials.md`.

### 2.2 — Commit/push every at-risk repo change (crc.yaml is the flagged file)

**group-sync-dashboard `environments/crc.yaml` — the operator-flagged uncommitted edit (67 insertions:**
P2 namespace selector on `company.net/mnemonic` + `company.net/app-environment`, the P4
`America/New_York` 22:00–06:00 window, the nightly namespace-access schedule, the second "mock"
cluster entry). A plain clone will **not** bring this back. Preserve it **both** ways:

```sh
# a) belt-and-suspenders patch into the carry folder
git -C "$DASH" diff environments/crc.yaml > "$KEEP/crc.yaml.working.patch"
# b) the durable path — commit to a branch and push
git -C "$DASH" switch -c chore/crc-yaml-p2-p4-mock
git -C "$DASH" add environments/crc.yaml
git -C "$DASH" commit -m "environments(crc): P2 namespace selector, P4 night window, nightly schedule, mock cluster entry"
git -C "$DASH" push -u origin chore/crc-yaml-p2-p4-mock
```

**`stash@{0}` — a SEPARATE 36-line crc.yaml WIP** on `feat/reporting-selector-gui` (base tip
`08a7fa0`). Stashes **never** transfer via clone. This is **not** a duplicate of the 67-line edit —
preserve **both**; applying one over the other may conflict.

```sh
git -C "$DASH" stash show -p 'stash@{0}' > "$KEEP/crc.yaml.stash.patch"
```

Confirm nothing else is unpushed across the group-sync repos (the operator/helm-chart/cilium repos
were audited clean). For a feature branch, compare against its **own upstream**, not `origin/main`:

```sh
for r in group-sync-dashboard group-sync-operator group-sync-operator-helm-chart cilium-implementation-poc; do
  echo "== $r =="; git -C "/Users/olasumbo/gitRepos/$r" status -sb | head -1
  git -C "/Users/olasumbo/gitRepos/$r" log --branches --not --remotes --oneline | head   # anything printed = unpushed
done
```

> `group-sync-operator`'s `990c097` shows "unpushed vs origin/main" but is already on
> `origin/fix/reconcile-group-provenance-labels` — it IS on the remote. Not a loss.

### 2.3 — Refresh the claude-config backup BEFORE relying on restore.sh

**Done on 2026-09-18** — the drift this step existed to catch is closed. The repo held 59 notes and
live memory held 61; they are now identical and pushed, alongside the reviewer agents, the process
sweeper, the merge helper and the changelog resolver, under
`2026-09-18-design-programme/`.

Re-run this only if you do more work before moving:

```sh
# copy the live memory dir into the repo, then:
git -C ~/gitRepos/claude-config add -A
git -C ~/gitRepos/claude-config commit -m "capture: refresh dashboard memory notes before machine move"
git -C ~/gitRepos/claude-config push
```

Check before you leave — silence means the backup is current:

```sh
diff <(ls ~/.claude/projects/*group-sync-dashboard/memory) \
     <(ls ~/gitRepos/claude-config/2026-09-18-design-programme/memory/*/)
```

### 2.4 — Copy the local-only files worth keeping out of the scratchpad

`/private/tmp/...` is wiped by **reboot / OS temp cleanup**, not only by the move — treat as at-risk **now**.

```sh
mkdir -p "$KEEP/scratchpad"
# the mock API TLS cert-manager manifest is now COMMITTED at
#   local-development/mock-app/deploy/certmanager-tls.yaml  (travels via git clone — no carry needed)
# in-flight adversarial-review briefs for the current C3 pass (fold outcomes into docs/REVIEW_C3.md too)
cp "$SP/review_brief_p4.md" "$SP/fable_brief_138.md" "$SP/fable_brief_133.md" "$KEEP/scratchpad/" 2>/dev/null
# the CRC cert-manager rework plan (§4.10) is now COMMITTED at
#   docs/handoff/crc-ca-cert-manager-plan.md  (travels via git clone — no carry needed)
# bespoke session scripts (modest value, hand-authored) — keep only if you want the tools
cp "$SP/reporting_peek.py" "$SP/capture_b3.py" "$SP/capture_p2.py" "$SP/b3_mock_check.py" "$SP/advisory.sh" "$KEEP/scratchpad/" 2>/dev/null
```

Regenerable — **do not** carry: `.venv` (242 MB), `chart-*.tgz`, `crc-*.kubeconfig` (sensitive, re-derive
from CRC), the `reporting-peek*/` and `b3-shots/` PNGs (re-run the capture scripts; the canonical e2e
evidence is already committed under `reports/2026-09-14_e2e-walk*`).

### 2.5 — Carry the credential/state files that ARE copyable (optional shortcuts to re-login)

```sh
mkdir -p "$KEEP/creds"
cp -a ~/.ssh "$KEEP/creds/ssh"                                  # 600 perms preserved (-a); needed for the SSH remotes
cp    ~/.codex/auth.json  "$KEEP/creds/codex-auth.json"         # mode 600; NOT the 314MB logs_*.sqlite
cp    ~/.codex/config.toml "$KEEP/creds/codex-config.toml"
cp    ~/.config/containers/auth.json "$KEEP/creds/containers-auth.json"   # base64 registry creds — secret
```

> Each of these can instead be re-established by logging in on the new Mac (§4.2). Copy = faster; login = cleaner.

### 2.6 — Record (do NOT print) where the secrets and keys live

Write a private note (in the password manager, not the repo) recording **locations only** — never dump values:

- `~/.crc/machines/crc/kubeadmin-password` — **regenerable**; do NOT copy, do NOT print. Re-issued by `crc start`.
- `local-development/.env` — no longer used; `registry-creds.sh` exports the same names from the
  store after one `podman login`, see §2.1. Nothing to carry.
- `~/.config/containers/auth.json` — base64 registry creds.
- **CA PRIVATE KEY in git (security exposure, not a loss):**
  `group-sync-operator-helm-chart/setup-local-ldap-testing/ca-key.pem` is committed and pushed to
  `origin/main`. It survives the move (it clones), but if that repo is/ever becomes public the CA is
  compromised. If committing it was unintentional: rotate the CA and scrub it from history.
- CRC pull secret — **not stored on disk anywhere**; re-download on the new Mac (§4.9).

### 2.7 — Record the tool versions to match

Match these on the new Mac (arm64 builds of the same versions):

| Tool | Version | Install channel |
|---|---|---|
| crc | 2.49.0+e843be (bundles OpenShift 4.18.2) | Red Hat installer `.pkg` |
| oc | 4.13.6 (kustomize v4.5.7) | `brew install openshift-cli` |
| helm | v3.14.0 | `brew install helm` |
| podman | 5.5.2 | `brew install podman` |
| gh | 2.100.0 | `brew install gh` |
| node | v25.9.0 | `brew install node` |
| python3 | 3.13.5 | `brew install python@3.13` |
| actionlint | 1.7.12 | `brew install actionlint` |
| codex-cli | 0.144.1 | `npm i -g @openai/codex` |
| cursor CLI | (vendor) | `curl https://cursor.com/install -fsS \| bash` |
| mermaid-ascii | (manual bin) | `go install github.com/AlexanderGrooff/mermaid-ascii@latest` |

```sh
# optional: snapshot the exact versions to the carry folder
{ crc version; oc version --client; helm version; podman version; gh --version; node -v; python3 -V; \
  actionlint --version; codex --version; cursor --version; } > "$KEEP/tool-versions.txt" 2>&1
```

---

## 3. Transport — what travels how

**By `git clone` (nothing to hand-carry):**

| Repo | Remote | Transport |
|---|---|---|
| group-sync-dashboard | `https://github.com/ephico2real2/group-sync-dashboard.git` | HTTPS (keychain/gh) |
| group-sync-operator | `git@github.com:ephico2real2/group-sync-operator.git` | **SSH** |
| group-sync-operator-helm-chart | `git@github.com:ephico2real2/group-sync-operator-helm-chart.git` | **SSH** |
| cilium-implementation-poc | `https://github.com/ephico2real2/cilium-implementation-poc.git` | HTTPS (keychain/gh) |
| claude-config | (its origin) | for `restore.sh` — refresh+push first (§2.3) |

> The two SSH remotes need `~/.ssh` present **before** you can clone/push them. Carry `~/.ssh` (§2.5) or
> generate a fresh key on the new Mac and register the `.pub` with GitHub.

**Hand-carried in `$KEEP` (unrecoverable working state):**
`crc.yaml.working.patch`, `crc.yaml.stash.patch`, the `scratchpad/` copies
(`mock-certmanager.yaml`, review briefs, `crc-ca-cert-manager-plan.md`, bespoke scripts), and the
`creds/` shortcuts (`~/.ssh`, `codex-auth.json`, `codex-config.toml`, `containers-auth.json`).

**Regenerated on the new Mac — do NOT carry:** `~/.kube/config` (re-issued by `crc start`/`oc login` —
**do not copy the old one**, it points at the old CRC), the 64 GB `crc.img`, the CRC bundle cache (~6 GB),
`kubeadmin-password`, `.venv`, built chart `.tgz`, podman machine SSH identity.

**`~/.claude` project memory/settings:** carried by cloning `claude-config` and running its `restore.sh`
(it re-keys the path slugs to the new home and symlinks the cilium lab memory to the dashboard's). The
`.jsonl` session transcripts are **outside** restore scope — copy them deliberately only if you want the
raw history; the distilled memory notes carry the durable takeaways.

---

## 4. On the NEW Mac — ordered setup

### 4.1 — Install the tools

```sh
# Homebrew (Apple Silicon installs to /opt/homebrew)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install openshift-cli helm podman gh node python@3.13 actionlint

# podman VM
podman machine init && podman machine start          # consider --cpus/--memory > the old 2GiB default

# codex CLI (npm global, not brew)
npm install -g @openai/codex

# cursor CLI (vendor script, not brew)
curl https://cursor.com/install -fsS | bash

# mermaid-ascii (manual binary, NOT a brew formula) — one-liner:
go install github.com/AlexanderGrooff/mermaid-ascii@latest   # then symlink/copy into /usr/local/bin (or /opt/homebrew/bin)
# (or download the release binary from github.com/AlexanderGrooff/mermaid-ascii into your PATH)

# crc (Red Hat installer, NOT brew): download the .pkg from
#   https://console.redhat.com/openshift/create/local  → install the .pkg
```

### 4.2 — Log in to each tool

```sh
gh auth login                       # HTTPS; request scopes: gist,read:org,repo,workflow
gh auth setup-git                   # wires the osxkeychain credential helper for HTTPS pushes
codex login                         # (or drop the carried ~/.codex/auth.json into place, mode 600)
cursor agent login                  # REQUIRED for the adversarial-review pass; binary is `cursor`, subcommand `agent`
podman login <registry>             # per registry (or drop the carried ~/.config/containers/auth.json, mode 600)
# SSH: place carried ~/.ssh (chmod 600 the private key) OR ssh-keygen + add the new .pub to GitHub
```

### 4.3 — Clone the repos

```sh
mkdir -p ~/gitRepos && cd ~/gitRepos
git clone https://github.com/ephico2real2/group-sync-dashboard.git
git clone git@github.com:ephico2real2/group-sync-operator.git                 # SSH — needs the key
git clone git@github.com:ephico2real2/group-sync-operator-helm-chart.git      # SSH — needs the key
git clone https://github.com/ephico2real2/cilium-implementation-poc.git
git clone https://github.com/ephico2real2/claude-config.git
```

### 4.3b — Restore the Claude Code setup (two scripts, in this order)

The repo root's `restore.sh` lays down the global rules, settings, plans and every project's memory.
The dated folder then layers on what this programme added. Run them in that order — the second
overwrites settings deliberately, to add the sweeper's hook.

```sh
cd ~/gitRepos/claude-config
./restore.sh                                   # 1. the base snapshot
./2026-09-18-design-programme/restore.sh       # 2. agents, tools, the hook, the current memory
```

The second was run end to end against an empty `HOME` on 2026-09-18: both reviewer agents and the
sweeper in place, `settings.json` parsed with all three hook events kept and the sweeper hook's
absolute path re-keyed to the new home, 61 memory notes under a re-keyed project slug, and a second
run exiting 0 leaving timestamped backups. It is safe to run twice.

Check it landed:

```sh
ls ~/.claude/agents                            # ob2.md ob3.md
~/.claude/tools/sweep-stale.py --report        # expect "nothing stale" on a fresh machine
```

Read `2026-09-18-design-programme/MIGRATION-READINESS.md` in that repo before you start §4.4 — it is
the list of what a clone cannot bring back.

### 4.4 — Restore the unrecoverable working state into the clones

```sh
NDASH=~/gitRepos/group-sync-dashboard
podman login quay.io   # then `. local-development/registry-creds.sh` in any pushing shell; see §2.1

# crc.yaml working-tree edit: if you pushed the branch in §2.2, just check it out; else apply the patch
git -C "$NDASH" apply "$KEEP/crc.yaml.working.patch"               # (branch checkout is the cleaner path)

# stash@{0}: apply the separate 36-line WIP where it belongs (feat/reporting-selector-gui @08a7fa0)
git -C "$NDASH" checkout feat/reporting-selector-gui
git -C "$NDASH" apply "$KEEP/crc.yaml.stash.patch"                 # keep it distinct from the 67-line edit
```

### 4.5 — Rebuild the python venv + Playwright chromium

```sh
cd "$NDASH/local-development"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # (repo's requirements; .venv is gitignored, do not carry)
python -m playwright install chromium     # for the e2e-walk / capture scripts
```

### 4.6 — Rebuild CRC (a brand-new cluster)

```sh
# fresh pull secret first (nothing to copy):
#   https://console.redhat.com/openshift/create/local  → download pull-secret

# SIZED FOR THE TARGET MACHINE: MacBook Pro, Apple M5 Pro, 18-core CPU, 64 GB unified memory
# (operator, confirmed 2026-09-18). The 18-core M5 Pro is 6 super cores + 12 performance cores.
#
# The old cluster was 5 / 16384 / 60 and sat at 99% CPU requests (4792m/4800m — the #97 report-pod
# preemption cause) and 85% disk (51/60G), BEFORE monitoring or GitOps. Every dimension rises:
crc config set cpus 12                          # of 18; leaves 6 for macOS and the podman build VM
crc config set memory 32768                     # 32 GiB VM, half the machine; 32 GiB left for macOS + podman
crc config set disk-size 100                    # the 85%-full 60G was the real constraint; disk is cheap
crc config set enable-cluster-monitoring true   # NEW requirement; default CRC has monitoring OFF (0 pods)
#
# NOTE ON CORE COUNT: Apple Silicon has no SMT/hyperthreading, so 18 physical cores are 18 logical
# cores — `sysctl -n hw.logicalcpu` returns 18, not 36. Size against 18. Allocating as though there
# were 36 would re-create exactly the over-subscription that preempted the report pod 29 times in
# three hours on the old cluster (#97).
crc config set consent-telemetry yes
crc config set no-proxy local,169.254/16

crc setup
crc start --pull-secret-file ~/Downloads/pull-secret.txt
eval "$(crc oc-env)"
oc login -u kubeadmin -p "$(crc console --credentials | ...)"   # kubeadmin-password is REGENERATED by crc; never carried
oc config current-context        # expect: default/api-crc-testing:6443/kubeadmin
```

**On monitoring.** It is on above, which is the change this move makes possible. Monitoring costs
roughly 3-4 GiB and a real slice of CPU; a 32 GiB / 12-core VM has room for it alongside GitOps and the
LDAP lab, where the old 16 GiB / 5-core one did not. The memory note "Monitoring validation parked for
a bigger CRC" is discharged by this machine — but measure once rather than assume:

```sh
oc adm top node
oc get pods -A --field-selector=status.phase=Pending    # empty means it fits
```

If either looks tight, `crc config set enable-cluster-monitoring false && crc stop && crc start` puts it
back. Over-subscription is what preempted the report pod 29 times in three hours on the old cluster.

**Architecture, if the new Mac is Apple Silicon.** This laptop builds `amd64` (measured:
`podman info` → `amd64/linux`) and the images on quay are **single-architecture**, not manifest lists.
An arm64 CRC cannot run them. What does break is pulling `quay.io/ephico2real/...` onto an arm64
cluster — rebuild and push from the new Mac, or publish a manifest list, before relying on the external
registry there.

**Measured on the M5 Pro, 2026-09-18 — three things the sentence "release-crc.sh builds arm64 natively"
hid, each with its fix:**

1. **The Containerfiles named the x86-64 loader.** The hardened image's proof step ran
   `/lib64/ld-linux-x86-64.so.2 --list` and failed the build at that `RUN` on arm64; the bases are
   manifest lists for both architectures and every packed library is named by soname, so that was the
   only amd64-specific line. Fixed by finding the loader with a guarded glob (`/lib*/ld-linux-*.so.*`;
   it is `/lib/ld-linux-aarch64.so.1` on arm64, not under `/lib64`). Both images then built and the
   in-pod commit verified.
2. **The registry route resolves to `127.0.0.1` inside the podman machine.** gvproxy hands the VM the
   host's resolver answer, and on the VM `127.0.0.1` is the VM. `podman push` failed with
   `dial tcp 127.0.0.1:80: connect: connection refused`. The host's CRC daemon answers at gvproxy's host
   address (`192.168.127.254`, HTTP 401 from the registry), so add it inside the VM once — `/etc/hosts`
   there persists across `podman machine stop/start`:
   ```sh
   podman machine ssh -- sudo sh -c 'echo "192.168.127.254 default-route-openshift-image-registry.apps-crc.testing" >> /etc/hosts'
   ```
3. **`cryptography` ≥ 48 dies with SIGILL (exit 132) on the CRC node**, in the mock image (the dashboard
   image is unaffected). The wheel's statically linked OpenSSL trusts the guest kernel's HWCAP, which under
   Virtualization.framework advertises `sve2`/`svei8mm` the silicon does not implement, and the assembly
   path it selects traps. Bisected in a pod on the node: 48.0.0/49.0.0/50.0.1 exit 132, 46.0.3 and below
   import. `OPENSSL_armcap=0` makes 50.0.1 import and generate a 2048-bit RSA key; it is set on the mock
   Deployment in `local-development/mock-app/deploy/mock-openshift-deployment.yaml`. Harmless on amd64
   and on real arm64 hosts.

### 4.6b — Operators + cluster monitoring (install after `crc start`)

The lab depends on four OperatorHub operators (measured on the old CRC on 2026-09-16), and this move
adds a fifth. Community-source operators need the `community-operators` CatalogSource healthy (see the
memory on CRC catalog pull failures — disable the catalogs you do not use so the ones you do stop
timing out on TLS).

| Operator | Source / channel | CSV observed | Why the lab needs it |
|---|---|---|---|
| cert-manager Operator for Red Hat OpenShift | `redhat-operators` / `stable-v1` | `cert-manager-operator.v1.19.1` | every mock + LDAP cert — details in §4.7 |
| group-sync-operator | `community-operators` / `alpha` | `group-sync-operator.v0.0.36` | the operator the dashboard observes |
| namespace-configuration-operator | `community-operators` / `alpha` | `namespace-configuration-operator.v1.2.6` | namespace label/config automation the lab uses |
| grafana-operator | `community-operators` / `v5` | `grafana-operator.v5.24.0` | validated the B3 Grafana dashboard (ns `grafana-test`) |
| **OpenShift GitOps (ArgoCD)** | `redhat-operators` / `latest` | **NEW this move** | GitOps-manage the chart/app this time (creates an ArgoCD in `openshift-gitops`) |

Install OpenShift GitOps (new this move):

```sh
oc apply -f - <<'EOF'
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-operators
spec:
  channel: latest                 # confirm the channel on the new cluster: `oc get packagemanifest openshift-gitops-operator -o jsonpath='{.status.channels[*].name}'`
  installPlanApproval: Automatic
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
oc rollout status deploy/openshift-gitops-server -n openshift-gitops --timeout=300s
```

**Enable OpenShift cluster monitoring (new this move).** Default CRC ships monitoring OFF — on the old
cluster `openshift-monitoring` had **0 pods** and no `cluster-monitoring-config`, which is why the
chart's `monitoring.serviceMonitor.enabled` / `monitoring.prometheusRule.enabled` were parked (see the
"monitoring validation parked" memory). Turn it on so the ServiceMonitor + PrometheusRule can finally
be validated on-cluster:

```sh
crc config set enable-cluster-monitoring true    # set BEFORE `crc start`; if already started, set then `crc stop && crc start`
# verify after start:
oc -n openshift-monitoring get pods               # prometheus-k8s / alertmanager / etc. should appear
```

> Enabling monitoring costs CPU/RAM on a single node — bump `crc config set memory` accordingly (the
> §4.6 sizing of 16384 MB already leaves headroom; drop other operators first if the node saturates,
> per the report-pod preemption seen at 99% CPU requests, issue #97).

**Enable user-workload monitoring (done on the M5 Pro, 2026-09-19).** Cluster monitoring on is not
enough for the app's own series: those are scraped by the *user-workload* Prometheus, which exists
only once a cluster-admin turns it on — one ConfigMap, once per cluster, and a chart cannot own it
(the ConfigMap is the platform's, shared with every other monitoring setting). This is the one
prerequisite the `openshift-grafana` chart (#162) states; without it Thanos serves no user metrics.

```sh
oc -n openshift-monitoring create configmap cluster-monitoring-config \
  --from-literal=config.yaml='enableUserWorkload: true'       # or add the key to the existing ConfigMap's config.yaml
sleep 60; oc get pods -n openshift-user-workload-monitoring    # prometheus-user-workload-0, thanos-ruler-user-workload-0
```

Then `environments/crc.yaml` turns the app chart's ServiceMonitor, rules and GrafanaDashboard CR on,
and the Grafana chart installs into the app's namespace (`docs/DESIGN_grafana_and_observe.md` §1, §4):

```sh
helm install grafana charts/openshift-grafana -n group-sync-dashboard \
  --set grafana.route.enabled=true --set wait.verifyUserWorkloadMonitoring=true --wait --timeout 15m
# the KPI page's door: grafana.url in environments/crc.yaml is this release's Route host
oc get route grafana-openshift-grafana -n group-sync-dashboard -o jsonpath='{.spec.host}'
```


### 4.7 — cert-manager operator (prerequisite for ALL mock + LDAP certs)

Install **cert-manager Operator for Red Hat OpenShift** (observed `cert-manager-operator.v1.19.1`).
Wait for `cert-manager` / `cert-manager-cainjector` / `cert-manager-webhook` pods **Ready** in ns
`cert-manager`. **Nothing that follows works until this is up.**

### 4.8 — Deploy the app at 0.24.0 (the only fully-automated step)

```sh
cd "$NDASH"
./local-development/release-crc.sh          # builds + pushes + deploys BOTH dashboard and report images
                                            # tagged <version>-<sha>, using environments/crc.yaml as -f
helm list -n group-sync-dashboard           # expect chart 0.32.0 / app 0.24.0, Deployed
```

> `release-crc.sh`'s scope is **exactly two images**. It does **not** create the mock backend,
> cert-manager chains, the LDAP lab, cluster trust, or the `mock-creds` volume patch. Those are §4.9–§4.10.

### 4.9 — Re-apply the mock cluster (one script since 2026-09-18)

**Run the script; the manual sequence below is kept only as the explanation of what it does.**

```sh
cd local-development/mock-app/deploy
./deploy-mock.sh              # build+push, PKI, workload, creds, and the dashboard patch
./deploy-mock.sh --verify     # check only — including the volume patch people forget
```

It was written from the live cluster and verified against it: the token it derives equals the deployed
secret byte for byte, and the `ca.crt` it builds has the same SHA-256 fingerprint as the running one.
`DEPLOY.md` beside it explains each step and why the order matters. Everything below is that same
sequence by hand.

```sh
# 1) build + push the mock image (release-crc.sh does NOT build this)
cd "$NDASH/local-development/mock-app"
podman build -f containerfile/Containerfile -t mock-openshift .
# tag + push to the CRC internal registry as mock-openshift:test (same podman login flow release-crc.sh uses)

# 2) the mock cert-manager chain — COMMITTED; nothing needs carrying
oc apply -n group-sync-dashboard -f local-development/mock-app/deploy/certmanager-tls.yaml
#   chain: Issuer mock-selfsigned (SelfSigned) -> Certificate mock-ca (isCA, secret mock-ca)
#          -> Issuer mock-ca-issuer (CA) -> Certificate mock-tls
#          (dnsNames: mock-openshift, .svc, .svc.cluster.local, localhost; ip 127.0.0.1; secret mock-tls)
oc get certificate -n group-sync-dashboard mock-ca mock-tls    # wait for both Ready

# 3) the mock backend Deployment + Service — COMMITTED since 2026-09-18, captured off the old cluster
oc apply -n group-sync-dashboard \
  -f local-development/mock-app/deploy/mock-openshift-deployment.yaml \
  -f local-development/mock-app/deploy/mock-openshift-service.yaml

# 4) the mock-cluster-creds secret — ca.crt MUST equal the mock-ca CA or the dashboard's TLS verify fails
oc create secret generic mock-cluster-creds -n group-sync-dashboard \
  --from-literal=token='mock-token-reference' \
  --from-literal=ca.crt="$(oc get secret mock-ca -n group-sync-dashboard -o jsonpath='{.data.ca\.crt}' | base64 -d)"

# 5) patch the mock-creds volume onto the dashboard Deployment — INVISIBLE to Helm; re-apply after EVERY fresh install
oc set volume deploy/group-sync-dashboard --add --name mock-creds \
  --secret-name mock-cluster-creds --mount-path /etc/gsd/mock -n group-sync-dashboard
```

> The committed `DESIGN_mock_cluster.md` / `mock-app/README.md` describe a **self-generated ephemeral
> CA** — that **diverges** from the live wiring (cert-manager Issuers/Certificates, CA hand-copied into
> `mock-cluster-creds`). Follow §4.9 above, not the doc verbatim.

### 4.9b — The application namespaces and the hand-made grants (found missing on the M5 Pro, 2026-09-19)

The old cluster had **110 namespaces**, and the ones the dashboard's Namespaces tab, the namespace-access
selector and the NCO baseline policies act on — `demo-*`, `beta-*`, `jeff-*`, `gsd-preexist`, the
`legacy-*` direct-grant demo, `oud-poc-spark` — had all been created by hand and were committed nowhere.
The rebuild found only the `klt-*` Kyverno fixtures. The list was read off the old cluster's own
Namespace-audit screenshot (`reports/2026-09-18_design-programme-release/screenshots/06-namespace-audit.png`,
MNEMONIC and APP-ENVIRONMENT columns) and is committed now, in three places:

```sh
# 1) the RBAC repo's own namespaces (spar-*, trno-*, oud-poc-{trino,crossfamily,platform}) and the klt-* fixtures
cd ~/gitRepos/openshift-rbac-automation/working-sessions/policies
oc apply -f bda-namespace.yaml -f oud-group-namespace.yaml -f kyverno-label-test-namespaces.yaml
# 2) the dashboard's lab namespaces, labelled as the old cluster had them
cd "$NDASH"
oc apply -f local-development/crc/namespaces.yaml
oc label ns group-sync-dashboard company.net/mnemonic=gsd --overwrite   # Helm-created namespaces: a label, not a manifest
oc label ns group-sync-operator  company.net/mnemonic=gso --overwrite
# 3) the hand-made grants the Exposure table and the auditor persona run on — outside the policy system on purpose
oc apply -f local-development/crc/direct-grants.yaml
```

Measured after applying: NCO bound the synced groups **row for row as the screenshot's "via groups"
column** (beta-prod 1, beta-rnd/uat 2, demo-prod and demo-production 1, demo-qa/rnd/uat 2, jeff-qa/rnd 2,
oud-poc-spark 1, oud-poc-trino 1); `dana.lee` can list nodes and is not cluster-admin. The console's
per-login `view` bindings in `openshift-console-user-settings` are not in any file — the console makes
them as people log in.

### 4.10 — LDAP lab + cluster-wide trust (only if the LDAP integration is needed)

**The trust half is not optional on this lab, and "Path B" does not cover it.** The LDAP README's paths
describe how the *chart* gets its CA (copied vs injected); the *cluster's* trust in the root is a
separate step the old CRC had (`proxy/cluster.spec.trustedCA: ldap-enterprise-ca-bundle`, measured) and
the rebuild must repeat. After `15-bootstrap-cert-manager-ca.sh apply` and the server deploy:

```sh
cd ~/gitRepos/group-sync-operator-helm-chart/setup-local-ldap-testing
./15-bootstrap-cert-manager-ca.sh trust-cluster   # backs up proxy/cluster, publishes the root, patches, waits for the merge
oc get proxy cluster -o jsonpath='{.spec.trustedCA.name}{"\n"}'   # ldap-enterprise-ca-bundle
```

Measured 2026-09-18 on the new CRC: the bundle went 146 → 147 certificates, then the MCO rolled the
single node — the API answers `ServiceUnavailable` for the duration, so run it when nothing else is
mid-flight. The fuller rework below is a later PR; this one command is the rebuild step.

This is the `crc-*` cert-manager rework. **Do not duplicate it here** — follow the separate plan carried
in §2.4:

```
$KEEP/scratchpad/crc-ca-cert-manager-plan.md
```

That plan covers: renaming the LDAP-specific PKI to a general CRC enterprise CA (`crc-selfsigned-bootstrap`
→ root `crc-enterprise-root-ca` → issuer `crc-enterprise-ca` → bundle `crc-enterprise-ca-bundle`),
the `proxy/cluster.spec.trustedCA` anchor, the openldap-server/phpldapadmin deployments in ns
`ldap-testing`, and the two execution forks (fresh root = one node roll, vs reuse = zero-reboot). Execute
it as its own PR + post-merge cluster steps. **The `proxy/cluster` trust change triggers a MachineConfig
node roll (~105 s) — it reboots the CRC node** (see §6).

---

## 5. Verification

```sh
# CRC + context
crc status                                   # VM Running
oc config current-context                    # default/api-crc-testing:6443/kubeadmin

# app version + rollout
helm list -n group-sync-dashboard            # chart 0.32.0 / app 0.24.0, Deployed
oc rollout status deploy/group-sync-dashboard -n group-sync-dashboard   # successfully rolled out
oc get pods -n group-sync-dashboard          # dashboard + report Ready; mock-openshift Ready
oc get deploy group-sync-dashboard -n group-sync-dashboard \
  -o jsonpath='{.spec.template.spec.containers[0].image}'; echo   # 0.24.0-<sha>

# in-pod commit stamp (release-crc.sh already verifies the running pod's commit)
oc exec deploy/group-sync-dashboard -n group-sync-dashboard -- <the commit-stamp check release-crc.sh uses>

# both clusters polling: crc-local (in-pod SA) AND mock (https://mock-openshift:6443, /etc/gsd/mock/{token,ca.crt})
oc logs deploy/group-sync-dashboard -n group-sync-dashboard | grep -Ei 'poll|cluster|mock'
#   mock must NOT show token/ca files absent — that means the §4.9 step 5 volume patch is missing (silent fail)

# reporting UI reachable via the Route. The chart's Route sets spec.subdomain and leaves spec.host EMPTY,
# so the name is in status.ingress, not spec — and CRC on macOS writes each Route's spec.host into
# /etc/hosts (its admin-helper log shows `hosts:[""] ... "input rejected"` for this one), so the
# router-assigned name must be added by hand, with the same helper crc uses:
oc get route -n group-sync-dashboard -o jsonpath='{.items[0].status.ingress[0].host}{"\n"}'
/usr/local/crc/crc-admin-helper-darwin add 127.0.0.1 group-sync-dashboard.apps-crc.testing

# review pipeline works
cursor agent login && cursor --version       # non-interactive review fails until logged in
codex --version                              # invoke with `< /dev/null` when scripting (stdin hang)
# then run the adversarial-review skill on an open PR to confirm both reviewers drive end-to-end
```

Green when: CRC Running; 0.24.0 Deployed and the in-pod commit matches; both pods Ready; **both** clusters
poll (mock included, files present at `/etc/gsd/mock`); the Route serves the reporting UI; cursor + codex
both authenticate and the adversarial-review pass completes.

---

## 6. Gotchas (merged, all four audit dimensions)

**Auth / credentials**
- **`gh` token lives in the macOS keyring, not `~/.config/gh/hosts.yml`** (hosts.yml has only
  username + git-protocol). Copying the gh config dir does **not** carry the login — run `gh auth login`.
- **Git remote is HTTPS + `credential.helper=osxkeychain`.** Everyday push/pull uses the keychain/gh
  token, not `~/.ssh`. Migrating without re-auth fails pushes even if you copied `~/.ssh`. Run
  `gh auth setup-git`.
- **`group-sync-operator` and `group-sync-operator-helm-chart` are SSH remotes** — the SSH key must be
  present before you can clone/push them (dashboard + cilium are HTTPS).
- **`cursor agent login` is required for the adversarial-review pass** and fails non-interactively until
  done. Binary is `cursor`, subcommand `agent`; there is no separate `cursor-agent` binary.
- **`codex-cli` 0.144.1 hangs reading stdin** unless invoked with `< /dev/null` — relevant when scripting it.
- When copying `~/.codex`, copy **only** `auth.json` + `config.toml` — it also holds a **314 MB
  `logs_2.sqlite`** and other large state.

**Architecture / versions**
- **Intel → Apple Silicon:** old binaries live under `/usr/local` (`darwin/amd64`, CRC bundle
  `crc_vfkit_4.18.2_amd64`); the new Mac uses `/opt/homebrew` and **arm64** CRC/podman bundles.
  **Versions transfer, binaries do not** — reinstall, don't copy.
- **Version skew to note, not fix:** oc client is **4.13.6** while CRC ships **OpenShift 4.18.2**; the old
  podman machine had only **2 GiB** RAM (size the new one larger).

**Git state**
- **Anything unpushed is gone** if not committed/pushed first — the 67-line `crc.yaml` edit and
  `stash@{0}` are the two items in this project; **preserve both**, they are distinct (67-line working-tree
  edit vs a separate 36-line stash on a different base) and applying one over the other may conflict.
- The opening `gitStatus` (feat/c3-reporting-service, 13 modified files) is a **stale snapshot** — that
  work was committed, reviewed, pushed and **merged to `origin/main`**; not lost.
- For a **feature branch**, compare against its **own upstream** (`@{upstream}`), not `origin/main` —
  `group-sync-operator`'s `990c097` is on `origin/fix/reconcile-group-provenance-labels`, i.e. pushed.
- Unrelated repos under `~/gitRepos` (namespace-configuration-operator, helm-local-development, firewalla,
  k8s-metrics*, kube-objects, fluentd-hec, kyverno, ceph-rbd-troubleshooting, openshift-rbac-automation)
  hold local-only content — **out of scope** for this project; audit separately if doing a full-machine backup.

**CRC / cluster (all rebuilt fresh)**
- **`~/.kube/config` is per-CRC — do NOT copy the old one.** It points at the old cluster; `crc start` /
  `oc login` issue a fresh context, kubeadmin password and SSH key.
- **CRC pull secret is on disk nowhere** — re-download from the Red Hat console every time.
- **`release-crc.sh` is two images only** — reading "the 0.24.0 deploy" as "the whole lab" is the trap.
- **The `mock-creds` volume is invisible to Helm** (`helm get manifest | grep -c mock-creds = 0`). A fresh
  install renders the dashboard **without** it and the mock poll **fails silently** (files absent at
  `/etc/gsd/mock`) while the release still reports a clean rollout. **Re-patch after every fresh install.**
- **~~The mock chain and backend have no committed manifest~~ — CLOSED 2026-09-18.** All of it is in
  git now: the chain in `certmanager-tls.yaml`, and the Deployment and Service captured off the live
  cluster before it was discarded. Nothing needs carrying and nothing needs re-authoring.
- **`mock-cluster-creds.ca.crt` must equal the `mock-ca` CA.** If the cert-manager chain is recreated the
  CA changes, so regenerate the secret from the **new** `mock-ca` or the dashboard's `CERT_REQUIRED` TLS
  verify to the mock fails (UNREACHABLE). (`mock-tls`'s stale `last-applied` annotation is a red herring,
  not a second unmanaged copy — it is genuinely cert-manager-managed now.)
- **The cluster-wide trust change reboots the node.** `proxy/cluster.spec.trustedCA` (the enterprise CA
  bundle) drives a **MachineConfig node roll (~105 s)** — expect a CRC node reboot when you apply §4.10.
- **The single CRC node is CPU-saturated.** Rollouts and hook Jobs run slow/pending under load (transient
  `FailedScheduling: Insufficient cpu`) — this is why `authLogLevel.manage` is `false` in `crc.yaml` (the
  hook Job hung the upgrade). Expect the same on the new CRC; a transient Pending is not a fault.

**Config backup / scratchpad**
- **claude-config is behind live memory by 6 dashboard notes** — refresh, commit and push it **before**
  running `restore.sh`, or the newest reviewer/attribution rules and the `MEMORY.md` index are silently lost.
- **The scratchpad is under `/private/tmp`** — wiped by reboot / temp cleanup, **not just the move**. Copy
  `mock-certmanager.yaml`, the review briefs, and `crc-ca-cert-manager-plan.md` out **now**.
- **Security exposure:** `setup-local-ldap-testing/ca-key.pem` (a CA **private key**) is committed and
  pushed to `origin/main`. Not a loss risk — an exposure. If unintentional, rotate the CA and scrub history.
