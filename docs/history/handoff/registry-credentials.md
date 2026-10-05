# Registry credentials — storing them, and getting them back

Everything here was run on this machine on 2026-09-18; `gh` is 2.100.0. The repository is
`ephico2real2/group-sync-dashboard`, the registry is `quay.io/ephico2real`.

## What is actually secret

`local-development/.env` has seven keys and only two of them are secrets.

| Key | Secret? | Where it comes from |
|---|---|---|
| `REGISTRY_USERNAME` | **yes** | the Quay robot account |
| `REGISTRY_PASSWORD` | **yes** | the Quay robot token |
| `REGISTRY` | no | defaults to `quay.io` in `.github/workflows/helm.yaml` |
| `REGISTRY_NAMESPACE` | no | defaults to `ephico2real` in the same workflow |
| `IMAGE_NAME` | no | defaults in `local-development/build-and-push-external.sh` |
| `K8S_NAMESPACE` | no | defaults in the same script |
| `IMAGE_PULL_SECRET` | no | empty; the Quay repository is public |

The CRC internal registry appears nowhere here. `local-development/release-crc.sh` logs in with
`podman login -u kubeadmin -p "$(oc whoami -t)"` — a token minted at login, never stored.

## 1. Store them manually, on a machine

Create a **robot account**, not a personal password: Quay → Account Settings → Robot Accounts. A robot
token is revocable on its own, which is what you want if it ever leaks. Give it write on
`ephico2real/group-sync-dashboard` and `ephico2real/group-sync-dashboard-report`.

```sh
podman login quay.io            # prompts for the robot name and token
podman login --get-login quay.io    # confirms which identity is stored
```

Where it lands, measured on this machine:

| Store | Mode | Holds |
|---|---|---|
| `~/.config/containers/auth.json` | 600 | the real credentials, as base64 `user:password` blobs |
| `~/.docker/config.json` | 644 | **nothing** — `credsStore: desktop`, so every entry is empty and the credential is in the Docker Desktop keychain |

Base64 is encoding, not encryption. Anything that can read that file can read the token, which is why
it is mode 600 and why a robot token — revocable alone — is the right thing to put there.

To remove it: `podman logout quay.io`.

## 2. Store them in GitHub, with `gh`

Actions reads them from repository secrets. Set them by the **same names** the scripts use:

```sh
gh secret set REGISTRY_USERNAME          # prompts, input is not echoed
gh secret set REGISTRY_PASSWORD

gh secret set REGISTRY_PASSWORD < token.txt   # or from a file, then shred it
gh secret list                                 # names and timestamps only
```

Do not pass a secret as an argument. Argv is readable by every process on the host, and it lands in
your shell history.

**Secrets are write-only.** `gh secret` offers `set`, `list` and `delete` — there is no `get`, and the
API serves names and timestamps only. So GitHub is where CI reads them, **not** a backup you can
restore from. If you lose the token, you mint a new one; you never read the old one back.

## 3. Authenticate `gh`, and keep the session

Writing a repository secret needs the `repo` scope.

```sh
gh auth status        # who you are, where the token is kept, which scopes it has
gh auth login         # interactive: choose GitHub.com, HTTPS, and authenticate in the browser
gh auth refresh -s repo,workflow   # add scopes to the existing login without starting over
gh auth logout
```

Measured here: logged in to `github.com` as `ephico2real2`, token in the **OS keyring**, scopes
`gist`, `read:org`, `repo`, `workflow`. The keyring is why the session survives reboots and why the
token is not sitting in a dotfile. When no keyring is available `gh` falls back to
`~/.config/gh/hosts.yml`, which it creates mode 600.

For a non-interactive shell (a script, a runner, a remote box) set `GH_TOKEN` instead of logging in:

```sh
GH_TOKEN=<a fine-grained PAT with repo scope> gh secret list
```

`gh auth token` prints the active token. Treat that like the token itself — do not paste it anywhere,
and prefer `gh auth status`, which masks it.

## 4. Pull them into a script

`local-development/registry-creds.sh` exports the two secrets under the **same names GitHub uses**, so
a script reads identically in CI and on a laptop.

```sh
. ./local-development/registry-creds.sh      # sourced: exports the variables, prints nothing
./local-development/build-and-push-external.sh
```

| Invocation | Does |
|---|---|
| sourced | exports `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` and the five non-secret keys |
| `--check` | prints what it found, with the token masked to a length |
| `--login` | logs podman in with what it found |

If the variables are already set — which is the CI case, because the workflow injects them — the shim
leaves them alone and never reads the local store. That is what makes one script correct in both
places.

Measured 2026-09-18: sourcing printed **0 bytes**; the exported credential exchanged a quay.io token
for `pull,push` on `quay.io/ephico2real/group-sync-dashboard`, **HTTP 200**; and
`build-and-push-external.sh` then reported `config : environment only (no .env found)`.

## 4b. A new machine, without typing the token again (2026-09-19)

The robot credential is also kept **encrypted** in the private `claude-config` repository —
`2026-09-18-design-programme/secrets/quay-robot.json.vault`, written by its `tools/vault.sh` with a
passphrase that lives only in `~/.vault-key`. `registry-creds.sh` reads it as the fallback when this
machine has no `podman login` yet, so the order is: the environment (CI) → the local store → the vault.

```sh
gh repo clone ephico2real2/claude-config          # your gh login is the access control
printf '%s' 'the passphrase' > ~/.vault-key && chmod 600 ~/.vault-key
./local-development/registry-creds.sh --login     # podman logged in from the vault; nothing typed
```

Measured 2026-09-19 with the local store moved aside: `--check` reported the vault as its source, the
token exchange for `pull,push` answered **HTTP 200**, `--login` recreated `auth.json` at mode 600, and
with the store back the store won. The plaintext is never written to disk (`vault.sh view` to stdout).

## 5. Rotating, and what a leak costs

1. Quay → Robot Accounts → regenerate the token. The old one dies immediately.
2. `podman login quay.io` again on each machine that pushes.
3. `gh secret set REGISTRY_PASSWORD` to update CI.

The vault holds the only other copy, so a rotation is also `vault.sh encrypt --force` from the fresh
store and a commit. That is the whole point of not carrying a `.env` between machines: a token you
re-mint is a token the old laptop no longer has.
