#!/usr/bin/env bash
# Rebuild the cluster-wide trust bundle that proxy/cluster.spec.trustedCA names, from the enterprise
# CA plus this cluster's OWN certificate authorities, and point the proxy at it.
#
# WHY THIS EXISTS. OpenShift fills any ConfigMap labelled `config.openshift.io/inject-trusted-cabundle`
# with the system trust store MERGED with whatever proxy/cluster.spec.trustedCA names. The dashboard
# reads that injected bundle (GSD_TRUSTED_CA_FILE) for every cluster that declares no CA of its own,
# which is the normal case for an external, corporate-signed cluster. If the bundle does not carry a
# target's CA, the login fails at phase=tls -- safely, before any password is sent, but the cluster
# never connects.
#
# WHY IT MUST BE RE-RUNNABLE. Measured on the reference cluster 2026-09-22:
#
#     kube-apiserver-lb-signer                3594 d   (2036-07-26)
#     kube-apiserver-localhost-signer         3594 d
#     kube-apiserver-service-network-signer   3594 d
#     ...operator_localhost-recovery          3594 d
#     ingress-operator@...                     674 d   (2028-07-28)   <- rotates
#
# The API signers last a decade; the INGRESS CA does not. When it rotates, a bundle built from the
# old one stops verifying the OAuth route and every lookup fails at phase=tls. Re-run this then.
#
# WHY CA CERTS ONLY. kube-root-ca also carries the `*.apps-crc.testing` LEAF -- a server certificate,
# not an authority. It cannot sign anything, so it adds nothing to a trust bundle, and it is among
# the first things to rotate. This script keeps certificates with basicConstraints CA:TRUE and drops
# the rest, so the bundle contains only what can actually anchor a chain.
#
# SAFETY. Nothing is changed without --apply. The current proxy spec and the ConfigMap it names are
# written to the backup directory first, and reverting is a single `oc patch` back to the old name.
set -euo pipefail

NAME="${NAME:-enterprise-and-cluster-ca-bundle}"   # the ConfigMap this writes, in openshift-config
# WHERE THE ENTERPRISE CA COMES FROM. Defaulting to "whatever the proxy names" is wrong on the SECOND
# run: by then the proxy names this script's OWN output, so the cluster CAs would be read back in and
# added again. Set ENTERPRISE_CM to the original source; when the proxy already names $NAME, that is
# what this falls back to. Certificates are deduplicated by fingerprint regardless, so a mistake here
# costs a warning rather than a broken bundle.
ENTERPRISE_CM="${ENTERPRISE_CM:-}"
BACKUP_DIR="${BACKUP_DIR:-./ca-backup-$(date +%Y%m%d-%H%M%S)}"
WARN_DAYS="${WARN_DAYS:-90}"                        # complain about anything expiring sooner
APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v oc      >/dev/null || die "oc is not on PATH"
command -v openssl >/dev/null || die "openssl is not on PATH"
oc whoami >/dev/null 2>&1     || die "not logged in: run 'oc login' first"

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT

# ---------------------------------------------------------------- what is there now
current="$(oc get proxy cluster -o jsonpath='{.spec.trustedCA.name}' 2>/dev/null || true)"
say "proxy/cluster trustedCA : ${current:-<none>}"

src="$ENTERPRISE_CM"
if [ -z "$src" ]; then
  if [ "$current" = "$NAME" ]; then
    say "NOTE: the proxy already names '$NAME' — this script's own output. Reading it back as the"
    say "      enterprise source is safe only because certificates are deduplicated by fingerprint."
    say "      Set ENTERPRISE_CM to the original ConfigMap to be explicit."
  fi
  src="$current"
fi
if [ -n "$src" ]; then
  oc get cm "$src" -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' > "$work/enterprise.crt" 2>/dev/null \
    || die "ConfigMap '$src' in openshift-config cannot be read (set ENTERPRISE_CM to the right one)"
  say "enterprise source      : openshift-config/$src"
else
  : > "$work/enterprise.crt"
  say "NOTE: no enterprise source; the bundle will carry this cluster's CAs only."
fi

oc get cm kube-root-ca.crt -n default -o jsonpath='{.data.ca\.crt}' > "$work/cluster-raw.crt" \
  || die "cannot read kube-root-ca.crt in the default namespace"

# ---------------------------------------------------------------- CA certs only, with expiry
# Split the concatenated PEM and keep what is genuinely an authority. `openssl x509 -ext` is used
# rather than a text grep of the whole file: a bundle is many certificates and only some are CAs.
split_and_filter() {   # $1 = input PEM, $2 = label for the report
  local in="$1" label="$2" i=0 kept=0
  awk 'BEGIN{n=0} /BEGIN CERT/{f=sprintf("'"$work"'/%s-%03d.pem","'"$label"'",n++)} {if(f) print > f} /END CERT/{f=""}' "$in"
  for f in "$work/$label"-*.pem; do
    [ -e "$f" ] || continue
    i=$((i+1))
    local subj end days
    subj="$(openssl x509 -in "$f" -noout -subject 2>/dev/null | sed 's/^subject=//' | cut -c1-54)"
    end="$(openssl x509 -in "$f" -noout -enddate 2>/dev/null | sed 's/notAfter=//')"
    days="$(( ( $(date -j -f "%b %d %H:%M:%S %Y %Z" "$end" +%s 2>/dev/null || date -d "$end" +%s) - $(date +%s) ) / 86400 ))"
    if openssl x509 -in "$f" -noout -ext basicConstraints 2>/dev/null | grep -q 'CA:TRUE'; then
      # Deduplicate by fingerprint: the same authority reaching us from two sources is one anchor,
      # and a bundle that lists it twice is merely larger. This is also what makes a second run safe
      # when the proxy already names this script's own output.
      local fp; fp="$(openssl x509 -in "$f" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')"
      if grep -qxF "$fp" "$work/seen.txt" 2>/dev/null; then
        printf '  dup   %6sd  %s\n' "$days" "$subj"; continue
      fi
      printf '%s\n' "$fp" >> "$work/seen.txt"
      cat "$f" >> "$work/keep.crt"; kept=$((kept+1))
      printf '  KEEP  %6sd  %s\n' "$days" "$subj"
      [ "$days" -lt "$WARN_DAYS" ] && printf '        ^^ EXPIRES IN UNDER %s DAYS — re-run this script after it rotates\n' "$WARN_DAYS"
    else
      printf '  drop  %6sd  %s  (not a CA — a leaf cannot anchor a chain)\n' "$days" "$subj"
    fi
  done
  say "  $label: $kept of $i kept"
}

: > "$work/keep.crt"; : > "$work/seen.txt"
say ""; say "enterprise CA (from the proxy's current bundle):"; split_and_filter "$work/enterprise.crt" enterprise
say ""; say "this cluster's CAs (kube-root-ca.crt):";            split_and_filter "$work/cluster-raw.crt" cluster

total="$(grep -c 'BEGIN CERTIFICATE' "$work/keep.crt" || true)"
[ "$total" -gt 0 ] || die "no CA certificates survived filtering — refusing to write an empty bundle"
say ""; say "combined: $total CA certificate(s), $(wc -c < "$work/keep.crt" | tr -d ' ') bytes"

# ---------------------------------------------------------------- idempotency
if [ "$current" = "$NAME" ] && oc get cm "$NAME" -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' 2>/dev/null \
     | diff -q - "$work/keep.crt" >/dev/null 2>&1; then
  say ""; say "Already current: proxy names '$NAME' and its contents match. Nothing to do."
  exit 0
fi

if [ "$APPLY" != true ]; then
  say ""; say "DRY RUN — nothing changed. Re-run with --apply to:"
  say "  1. back up proxy/cluster and ConfigMap '${current:-<none>}' to $BACKUP_DIR"
  say "  2. create or replace ConfigMap '$NAME' in openshift-config"
  say "  3. point proxy/cluster.spec.trustedCA at it"
  say ""; say "NOTE: patching the proxy rolls cluster operators; the API is briefly unavailable."
  exit 0
fi

# ---------------------------------------------------------------- apply
mkdir -p "$BACKUP_DIR"
oc get proxy cluster -o yaml > "$BACKUP_DIR/proxy-cluster.yaml"
[ -n "$current" ] && oc get cm "$current" -n openshift-config -o yaml > "$BACKUP_DIR/$current.yaml"
say ""; say "backed up to $BACKUP_DIR"

oc create configmap "$NAME" -n openshift-config --from-file=ca-bundle.crt="$work/keep.crt" \
  --dry-run=client -o yaml | oc apply -f - >/dev/null
say "ConfigMap openshift-config/$NAME written ($total CA certificate(s))"

oc patch proxy cluster --type=merge -p "{\"spec\":{\"trustedCA\":{\"name\":\"$NAME\"}}}" >/dev/null
say "proxy/cluster.spec.trustedCA -> $NAME"

say ""; say "Injection is asynchronous. Watch a consumer pick it up, e.g.:"
say "  oc get cm -n <release-ns> -l config.openshift.io/inject-trusted-cabundle -o yaml | grep -c 'BEGIN CERT'"
# The revert hint is only useful when the proxy named something ELSE before this run. When it
# already named $NAME, patching back to the same name reverts nothing — the backup is the source
# of truth then, because what changed was the ConfigMap's CONTENTS, not which one is named.
say ""
if [ -n "$current" ] && [ "$current" != "$NAME" ]; then
  say "Revert:  oc patch proxy cluster --type=merge -p '{\"spec\":{\"trustedCA\":{\"name\":\"$current\"}}}'"
else
  say "Revert:  the proxy already named '$NAME', so only its CONTENTS changed."
  say "         oc apply -f $BACKUP_DIR/$NAME.yaml     # restores the previous bundle"
fi
