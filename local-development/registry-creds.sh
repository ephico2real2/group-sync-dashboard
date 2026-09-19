#!/usr/bin/env bash
# Put the registry credentials into the environment, from the credential store a single
# `podman login` already wrote. No .env file, nothing carried between machines.
#
# The variable names are deliberately the SAME as the GitHub repository secrets
# (REGISTRY_USERNAME, REGISTRY_PASSWORD), so a script reads identically in CI and on a laptop:
# in CI the workflow injects them, here this shim fills them from the local store.
#
#   . ./local-development/registry-creds.sh          # source it: exports the variables, prints nothing
#   ./local-development/registry-creds.sh --login    # run it: also logs podman in to $REGISTRY
#   ./local-development/registry-creds.sh --check    # run it: reports what it found, masking the secret
#
# Everything else has a default from a tracked file, so only the credential comes from the store:
#   REGISTRY / REGISTRY_NAMESPACE  .github/workflows/helm.yaml  (the `vars.* || '...'` fallbacks)
#   IMAGE_NAME / K8S_NAMESPACE     build-and-push-external.sh
#
# This file never prints a secret. --check prints lengths only.
#
# Precedence: the environment (CI) > the local podman login > the vaulted copy in the private
# claude-config repository (needs ~/.vault-key). The last is what makes a new machine one command.
#
# The CRC internal registry does NOT come through here: release-crc.sh logs in with
# `oc whoami -t`, a token minted at login rather than a stored password.

# Sourced or executed? A sourced script must not `set -e` or `exit` — that would kill the caller's shell.
if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "${0}" ]; then
  _rc_sourced=1
else
  _rc_sourced=0
  set -euo pipefail
fi

: "${REGISTRY:=quay.io}"
: "${REGISTRY_NAMESPACE:=ephico2real}"
: "${IMAGE_NAME:=group-sync-dashboard}"
: "${K8S_NAMESPACE:=group-sync-dashboard}"
: "${IMAGE_PULL_SECRET:=}"
export REGISTRY REGISTRY_NAMESPACE IMAGE_NAME K8S_NAMESPACE IMAGE_PULL_SECRET

# Already in the environment (CI injects the same names) — trust it and do not touch the store.
if [ -n "${REGISTRY_USERNAME:-}" ] && [ -n "${REGISTRY_PASSWORD:-}" ]; then
  _rc_source_of_truth="the environment (CI injects these names)"
else
  _rc_creds=$(REGISTRY="$REGISTRY" python3 - <<'PY'
import base64, json, os, pathlib, sys
reg = os.environ["REGISTRY"]
for store in (pathlib.Path.home() / ".config/containers/auth.json",
              pathlib.Path.home() / ".docker/config.json"):
    if not store.is_file():
        continue
    try:
        auths = json.loads(store.read_text()).get("auths", {})
    except (ValueError, OSError):
        continue
    # A login is recorded under the bare host, or with a port, or as a v1 URL. Try each.
    for key in (reg, f"{reg}:443", f"https://{reg}/v1/", f"https://{reg}"):
        entry = auths.get(key)
        if not entry:
            continue
        if entry.get("auth"):
            user, _, pw = base64.b64decode(entry["auth"]).decode("utf-8").partition(":")
            if user and pw:
                print(user); print(pw); sys.exit(0)
        if entry.get("username") and entry.get("password"):
            print(entry["username"]); print(entry["password"]); sys.exit(0)
sys.exit(1)
PY
  ) && {
    REGISTRY_USERNAME=$(printf '%s\n' "$_rc_creds" | sed -n 1p)
    REGISTRY_PASSWORD=$(printf '%s\n' "$_rc_creds" | sed -n 2p)
    _rc_source_of_truth="the local credential store, from your podman login"
  }
  unset _rc_creds
fi

# No local login yet: the vaulted copy, if this machine holds the key. The ciphertext lives in the
# private claude-config repository (`gh repo clone ephico2real2/claude-config`), encrypted with
# ~/.claude/tools/vault.sh and a passphrase only the operator has; decrypting it here is how a NEW
# machine gets the credential without anyone typing the token again (2026-09-19). The file is the
# `auths` entry podman itself writes, so the same parser reads it. Read to stdout only — nothing is
# written to disk — and it is a fallback: a `podman login` on this machine always wins above.
if [ -z "${REGISTRY_USERNAME:-}" ] || [ -z "${REGISTRY_PASSWORD:-}" ]; then
  _rc_vault="${REGISTRY_CREDS_VAULT:-$HOME/gitRepos/claude-config/2026-09-18-design-programme/secrets/quay-robot.json.vault}"
  if [ "$REGISTRY" = "quay.io" ] && [ -f "$_rc_vault" ] && [ -x "$HOME/.claude/tools/vault.sh" ]; then
    _rc_creds=$("$HOME/.claude/tools/vault.sh" view "$_rc_vault" 2>/dev/null | REGISTRY="$REGISTRY" python3 -c '
import base64, json, os, sys
reg = os.environ["REGISTRY"]
entry = json.load(sys.stdin).get("auths", {}).get(reg) or {}
if entry.get("auth"):
    user, _, pw = base64.b64decode(entry["auth"]).decode("utf-8").partition(":")
    if user and pw:
        print(user); print(pw); sys.exit(0)
sys.exit(1)
') && {
      REGISTRY_USERNAME=$(printf '%s\n' "$_rc_creds" | sed -n 1p)
      REGISTRY_PASSWORD=$(printf '%s\n' "$_rc_creds" | sed -n 2p)
      _rc_source_of_truth="the vault (${_rc_vault##*/}, decrypted with ~/.vault-key)"
    }
    unset _rc_creds
  fi
  unset _rc_vault
fi

if [ -z "${REGISTRY_USERNAME:-}" ] || [ -z "${REGISTRY_PASSWORD:-}" ]; then
  echo "no credential for ${REGISTRY}. Run:  podman login ${REGISTRY}" >&2
  echo "   (or, on a new machine: clone ephico2real2/claude-config, recreate ~/.vault-key, and run this again)" >&2
  [ "$_rc_sourced" = "1" ] && return 1 || exit 1
fi
export REGISTRY_USERNAME REGISTRY_PASSWORD

case "${1:-}" in
  --login)
    podman login -u "$REGISTRY_USERNAME" -p "$REGISTRY_PASSWORD" "$REGISTRY" >/dev/null
    echo "logged in to ${REGISTRY} as ${REGISTRY_USERNAME}"
    ;;
  --check)
    echo "credentials in state, from ${_rc_source_of_truth}:"
    echo "  REGISTRY           ${REGISTRY}"
    echo "  REGISTRY_NAMESPACE ${REGISTRY_NAMESPACE}"
    echo "  IMAGE_NAME         ${IMAGE_NAME}"
    echo "  K8S_NAMESPACE      ${K8S_NAMESPACE}"
    echo "  IMAGE_PULL_SECRET  ${IMAGE_PULL_SECRET:-<empty — public repo>}"
    echo "  REGISTRY_USERNAME  ${REGISTRY_USERNAME}"
    echo "  REGISTRY_PASSWORD  <${#REGISTRY_PASSWORD} chars, not shown>"
    echo "  image ref          ${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}"
    ;;
esac
