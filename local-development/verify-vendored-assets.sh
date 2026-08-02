#!/usr/bin/env bash
# Verify the API-docs bundles pinned in the Containerfile against npm's published integrity.
#
#   ./verify-vendored-assets.sh
#
# Run this when bumping a version, and whenever you want to satisfy yourself that the hashes
# in the Containerfile are the publisher's bytes rather than whatever a CDN handed us.
#
# WHY THIS EXISTS, and it is the whole point:
#
# The obvious way to produce a checksum is to download the file and hash it. That is
# trust-on-first-use — it proves only that the bytes have not changed SINCE you downloaded
# them. If the CDN had served a tampered file, you would pin the tampered hash and every
# later build would verify it happily, forever, and the pin would look like diligence.
#
# This script never trusts the CDN. It goes to the npm registry, which publishes an
# `integrity` digest for each release tarball, checks the tarball against that, and only
# then hashes the individual file out of it. What the Containerfile pins is then the
# publisher's byte string.
#
# Residual trust, stated plainly: the npm registry itself, and TLS to it. That is a smaller
# and more accountable surface than a CDN edge, but it is not zero. For a higher bar, mirror
# the tarballs into your own artifact store and pin against that.

set -euo pipefail
cd "$(dirname "$0")"

# name:version:path-inside-tarball:expected-sha256 — keep in step with the Containerfile.
ASSETS=(
  "redoc:2.5.0:package/bundles/redoc.standalone.js:0ec05be285ac885a330289b02f470e1bdbd2b6b3223a9fa213f24bf805a851d1"
  "swagger-ui-dist:5.29.4:package/swagger-ui-bundle.js:91393f3bdd1e7258302bc84ea29fd4e428e29703c1102acfec1e3ed8c2934518"
  "swagger-ui-dist:5.29.4:package/swagger-ui.css:bc5e8d5c013477cf1f35e2fb8ba1dff66be0f72f24e669a509635657145e1acb"
)

# sha256sum on Linux, shasum -a 256 on macOS. Neither is present on both.
if command -v sha256sum >/dev/null 2>&1; then
  sha256() { sha256sum "$1" | awk '{print $1}'; }
  sha512hex() { sha512sum "$1" | awk '{print $1}'; }
else
  sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
  sha512hex() { shasum -a 512 "$1" | awk '{print $1}'; }
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
fail=0

for entry in "${ASSETS[@]}"; do
  IFS=: read -r pkg version path want <<<"$entry"
  tgz="$WORK/$pkg-$version.tgz"

  if [ ! -f "$tgz" ]; then
    # npm's own record of what it published, fetched over TLS from the registry.
    integrity=$(curl -sSfL "https://registry.npmjs.org/$pkg/$version" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["dist"]["integrity"])')
    curl -sSfL -o "$tgz" "https://registry.npmjs.org/$pkg/-/$pkg-$version.tgz"

    # npm publishes sha512 as base64, so the hex digest has to be converted to compare.
    calc="sha512-$(sha512hex "$tgz" | xxd -r -p | base64 | tr -d '\n')"
    if [ "$integrity" != "$calc" ]; then
      echo "TARBALL FAILS NPM INTEGRITY: $pkg@$version" >&2
      echo "  npm published: $integrity" >&2
      echo "  we computed  : $calc" >&2
      fail=1
      continue
    fi
    echo "ok   $pkg@$version tarball matches npm's published integrity"
    tar xzf "$tgz" -C "$WORK"
  fi

  got=$(sha256 "$WORK/$path")
  if [ "$got" = "$want" ]; then
    echo "ok     $(basename "$path") pin verified"
  else
    echo "PIN MISMATCH: $(basename "$path")" >&2
    echo "  Containerfile: $want" >&2
    echo "  npm tarball  : $got" >&2
    fail=1
  fi
done

echo
if [ "$fail" -eq 0 ]; then
  echo "All pins match the bytes npm published. The Containerfile is trustworthy."
else
  echo "VERIFICATION FAILED — do not ship these pins." >&2
  exit 1
fi
