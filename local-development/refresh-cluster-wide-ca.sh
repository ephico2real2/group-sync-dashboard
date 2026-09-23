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
# written to the backup directory first. HOW you revert depends on what the proxy named BEFORE, and
# the run prints the right command for the case it is in (dry run included):
#   another ConfigMap -> one `oc patch` back to that name;
#   this script's own output -> `oc apply` the backed-up ConfigMap, because only its CONTENTS changed;
#   nothing at all -> `oc patch` the trustedCA name back to "", since no ConfigMap was backed up.
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
# `|| true` here would make an UNREADABLE proxy indistinguishable from one with no trustedCA set —
# and the difference decides both the loss guard below and which revert command is correct. An unset
# name is exit 0 with empty output; a read failure is a nonzero exit, and must stop the run.
current="$(oc get proxy cluster -o jsonpath='{.spec.trustedCA.name}' 2>/dev/null)" \
  || die "cannot read proxy/cluster — refusing to guess what this cluster trusts today"
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
  # A ConfigMap that EXISTS but carries a different data key reads as empty and exits 0 — measured on
  # the lab: `oc get cm ca-config-map -o jsonpath='{.data.ca-bundle\.crt}'` is exit 0, zero bytes,
  # empty stderr, because its key is `ca.crt`. Without this guard a mistyped ENTERPRISE_CM contributes
  # nothing and the bundle ships without the enterprise root, silently.
  [ -s "$work/enterprise.crt" ] \
    || die "ConfigMap '$src' in openshift-config has no 'ca-bundle.crt' key (or it is empty) — set ENTERPRISE_CM to the ConfigMap that really holds the enterprise root"
  say "enterprise source      : openshift-config/$src"
else
  : > "$work/enterprise.crt"
  say "NOTE: no enterprise source; the bundle will carry this cluster's CAs only."
fi

oc get cm kube-root-ca.crt -n default -o jsonpath='{.data.ca\.crt}' > "$work/cluster-raw.crt" \
  || die "cannot read kube-root-ca.crt in the default namespace"
[ -s "$work/cluster-raw.crt" ] \
  || die "kube-root-ca.crt in the default namespace has no 'ca.crt' key (or it is empty) — refusing to build a bundle without this cluster's own CAs"

# ---------------------------------------------------------------- CA certs only, with expiry
# Split the concatenated PEM and keep what is genuinely an authority. `openssl x509 -ext` is used
# rather than a text grep of the whole file: a bundle is many certificates and only some are CAs.
is_anchor() {   # $1 = one PEM certificate -- true when a verifier would accept it as a trust anchor
  # TWO ways to be an anchor, and the CA flag is only the first.
  #
  # The match is ANCHORED to the start of a line and whitespace is stripped first. `openssl x509 -ext`
  # falls back to printing an extension it CANNOT parse as raw octets, so a leaf whose basicConstraints
  # DER merely spells the string matched an unanchored grep and was kept (measured by two reviewers,
  # independently). Stripping spaces also accepts a `CA: TRUE` rendering: between keeping a non-anchor
  # (inert — it can sign nothing) and dropping a real one (every injected bundle on the cluster loses
  # it), the asymmetry says be permissive here and catch the rest on the RESULT guard below.
  openssl x509 -in "$1" -noout -ext basicConstraints 2>/dev/null \
    | tr -d '[:blank:]' | grep -qiE '^CA:TRUE(,|$)' && return 0
  # A SELF-SIGNED certificate anchors a chain whatever its CA flag says, and pinning a service by its
  # own self-signed certificate is a real deployment. A leaf signed by something ELSE — kube-root-ca's
  # `*.apps-crc.testing`, say — fails this and is still dropped.
  openssl verify -no_check_time -CAfile "$1" "$1" >/dev/null 2>&1 && return 0
  return 1
}

split_and_filter() {   # $1 = input PEM, $2 = label for the report
  local in="$1" label="$2" i=0 kept=0 unreadable=0
  # `/BEGIN CERT/` does NOT match `-----BEGIN TRUSTED CERTIFICATE-----`, so a trusted-certificate block
  # was invisible to the splitter and vanished without a word. Match any CERTIFICATE banner.
  awk 'BEGIN{n=0} /^-----BEGIN [A-Z ]*CERTIFICATE-----/{f=sprintf("'"$work"'/%s-%03d.pem","'"$label"'",n++)} {if(f) print > f} /^-----END [A-Z ]*CERTIFICATE-----/{f=""}' "$in"
  for f in "$work/$label"-*.pem; do
    [ -e "$f" ] || continue
    i=$((i+1))
    local subj end days
    # `|| subj=""` is load-bearing: `set -o pipefail` fails this whole pipeline when openssl cannot
    # read the block, and an unguarded assignment then ends the script under `set -e` with NO message
    # at all. Name the bad block instead of dying silently.
    subj="$(openssl x509 -in "$f" -noout -subject 2>/dev/null | sed 's/^subject=//' | cut -c1-54)" || subj=""
    end="$(openssl x509 -in "$f" -noout -enddate 2>/dev/null | sed 's/notAfter=//')" || end=""
    if [ -z "$end" ]; then
      unreadable=$((unreadable+1))
      printf '  BAD        -  PEM block %s of %s is not a readable certificate\n' "$i" "$label"
      continue
    fi
    days="$(( ( $(date -j -f "%b %d %H:%M:%S %Y %Z" "$end" +%s 2>/dev/null || date -d "$end" +%s) - $(date +%s) ) / 86400 ))"
    if is_anchor "$f"; then
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
      printf '  drop  %6sd  %s  (not an anchor — not a CA and not self-signed)\n' "$days" "$subj"
    fi
  done
  say "  $label: $kept of $i kept"
  [ "$unreadable" -eq 0 ] \
    || die "$unreadable PEM block(s) in '$label' could not be read — refusing to build a bundle from a partly unreadable source"
  # Content that yielded no certificate at all is a malformed source, not an empty one.
  if [ -s "$in" ] && [ "$i" -eq 0 ]; then
    die "source '$label' has content but no PEM certificate in it"
  fi
}

: > "$work/keep.crt"; : > "$work/seen.txt"
say ""; say "enterprise CA (from openshift-config/${src:-<none>}):"; split_and_filter "$work/enterprise.crt" enterprise
say ""; say "this cluster's CAs (kube-root-ca.crt):";            split_and_filter "$work/cluster-raw.crt" cluster

total="$(grep -cE '^-----BEGIN [A-Z ]*CERTIFICATE-----' "$work/keep.crt" || true)"
[ "$total" -gt 0 ] || die "no CA certificates survived filtering — refusing to write an empty bundle"
say ""; say "combined: $total CA certificate(s), $(wc -c < "$work/keep.crt" | tr -d ' ') bytes"

# ---------------------------------------------------------------- nothing trusted today is lost
# THE INVARIANT THIS SCRIPT MUST NOT BREAK. proxy/cluster.spec.trustedCA feeds EVERY ConfigMap
# labelled config.openshift.io/inject-trusted-cabundle — 20 of them on the reference lab, including
# openshift-apiserver, authentication, console, image-registry, monitoring and cert-manager. An anchor
# that disappears here disappears for all of them, not just for this app.
#
# The guards above each close ONE known way to lose an anchor. This one is on the RESULT, so it also
# closes the ways nobody enumerated: compare by fingerprint against what the proxy names TODAY, and
# refuse if anything that can anchor a chain would be missing. Refusing beats silently unioning the
# old bundle in — a union would also resurrect a deliberately rotated-out CA and keep it forever.
inventory() {   # $1 = PEM bundle, $2 = scratch label -> one "<sha256>\t<subject>" line per anchor
  local in="$1" label="$2" f fp subj
  rm -f "$work/$label"-*.pem
  awk 'BEGIN{n=0} /^-----BEGIN [A-Z ]*CERTIFICATE-----/{f=sprintf("'"$work"'/%s-%04d.pem","'"$label"'",n++)} {if(f) print > f} /^-----END [A-Z ]*CERTIFICATE-----/{f=""}' "$in"
  for f in "$work/$label"-*.pem; do
    [ -e "$f" ] || continue
    is_anchor "$f" || continue
    fp="$(openssl x509 -in "$f" -noout -fingerprint -sha256 2>/dev/null | sed 's/.*=//')" || fp=""
    [ -n "$fp" ] || continue
    subj="$(openssl x509 -in "$f" -noout -subject 2>/dev/null | sed 's/^subject=//')" || subj="(unreadable subject)"
    printf '%s\t%s\n' "$fp" "$subj"
  done
}

if [ -n "$current" ]; then
  oc get cm "$current" -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' > "$work/current.crt" 2>/dev/null \
    || : > "$work/current.crt"
  inventory "$work/current.crt" curinv | sort -u > "$work/current.inv"
  inventory "$work/keep.crt"    outinv | sort -u > "$work/output.inv"
  lost="$(comm -23 <(cut -f1 "$work/current.inv" | sort -u) <(cut -f1 "$work/output.inv" | sort -u))"
  if [ -n "$lost" ]; then
    say ""
    say "REFUSING TO WRITE. These anchors are in openshift-config/$current, which the proxy names"
    say "today, and would NOT be in the bundle this run writes:"
    while IFS= read -r fp; do
      [ -n "$fp" ] || continue
      say "  LOST  $(grep -F "$fp" "$work/current.inv" | cut -f2 | head -1)"
      say "        $fp"
    done <<< "$lost"
    say ""
    say "Set ENTERPRISE_CM to the ConfigMap that really holds the enterprise root. If dropping these"
    say "is deliberate — a rotated-out authority — re-run with ALLOW_DROP=1."
    [ "${ALLOW_DROP:-}" = "1" ] || die "$(printf '%s\n' "$lost" | grep -c .) anchor(s) this cluster trusts today would be dropped"
    say "ALLOW_DROP=1 — proceeding anyway."
  fi
fi

# ---------------------------------------------------------------- idempotency
if [ "$current" = "$NAME" ] && oc get cm "$NAME" -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' 2>/dev/null \
     | diff -q - "$work/keep.crt" >/dev/null 2>&1; then
  say ""; say "Already current: proxy names '$NAME' and its contents match. Nothing to do."
  exit 0
fi

# THE REVERT IS NOT ONE SENTENCE. Which command undoes this run depends on what the proxy named
# BEFORE it, and the empty case is the one that bites: with no trustedCA there is no ConfigMap to back
# up, so an instruction to `oc apply` one names a file that was never written.
revert_hint() {
  if [ -z "$current" ]; then
    say "Revert:  the proxy named NO trustedCA before this run, and no ConfigMap was backed up."
    say "         oc patch proxy cluster --type=merge -p '{\"spec\":{\"trustedCA\":{\"name\":\"\"}}}'"
  elif [ "$current" != "$NAME" ]; then
    say "Revert:  oc patch proxy cluster --type=merge -p '{\"spec\":{\"trustedCA\":{\"name\":\"$current\"}}}'"
  else
    say "Revert:  the proxy already named '$NAME', so only its CONTENTS changed."
    say "         oc apply -f $BACKUP_DIR/$NAME.yaml     # restores the previous bundle"
    say "         (a live export carries optimistic-concurrency metadata: strip"
    say "          metadata.resourceVersion, uid and creationTimestamp first)"
  fi
}

if [ "$APPLY" != true ]; then
  say ""; say "DRY RUN — nothing changed. Re-run with --apply to:"
  say "  1. back up proxy/cluster and ConfigMap '${current:-<none>}' to $BACKUP_DIR"
  say "  2. create or replace ConfigMap '$NAME' in openshift-config"
  say "  3. point proxy/cluster.spec.trustedCA at it"
  say ""; say "NOTE: patching the proxy rolls cluster operators; the API is briefly unavailable."
  say ""; revert_hint
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
say ""
revert_hint
