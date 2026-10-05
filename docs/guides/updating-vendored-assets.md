# Updating the API-docs bundles

`/api` and `/api/redoc` are rendered by Swagger UI and ReDoc. Those are third-party
JavaScript, and this repository keeps a copy of them in
`local-development/gsd/static/vendor/`, committed to git.

This page is how you refresh that copy. Budget five minutes; most of it is a rebuild.

```bash
cd local-development

./vendor-assets.sh --outdated    # is there anything newer?
./vendor-assets.sh --upgrade     # take it
./vendor-assets.sh               # re-check, offline
```

Then rebuild, deploy, and open `/api` to confirm it still renders.

---

## The four commands

| Command | Network? | What it does |
|---|---|---|
| `./vendor-assets.sh` | no | Checks the committed files against `ASSETS.lock`. This is what CI and `tests/test_vendored_assets.py` run |
| `./vendor-assets.sh --outdated` | yes | Compares the pinned versions against npm's `latest`. Changes nothing |
| `./vendor-assets.sh --update` | yes | Re-fetches the **currently pinned** versions. For repairing a corrupted or missing file |
| `./vendor-assets.sh --upgrade` | yes | Moves to the latest release, rewrites the files and the lock |

`--update` and `--upgrade` differ only in which version they fetch. Reach for `--update`
when a file is damaged and you want the same version back; `--upgrade` when you actually
want the newer release.

## Why the files are in git at all

The obvious alternative is a `curl` in the Containerfile. That was the first implementation
and it was replaced, because it makes every release depend on three things outside our
control:

* **npm being up.** A registry outage becomes a failed release.
* **the version still existing.** npm permits unpublish.
* **the build host having a route out.** A locked-down or air-gapped builder has none.

Each of those fails at the worst possible moment — while you are shipping — and none of them
is your bug to fix. Vendoring inverts it: the repository holds everything the build needs, so
a build works from a checkout alone, offline, years later. The cost is ~2.5MB in git and this
five-minute procedure.

The same reasoning applies at runtime, which is why the files exist in the first place.
FastAPI's stock docs handlers load their JavaScript from `cdn.jsdelivr.net`, and Swagger's
default favicon comes from `fastapi.tiangolo.com`. On a cluster with no route to the internet
— which is what this chart targets, pulling oauth-proxy from the internal registry and
injecting a trusted CA bundle — those pages render blank. Serving them from a CDN also had an
authenticated admin's browser talking to two third parties on every visit.

## Why the script talks to npm and not to the CDN

This is the part worth understanding before you run `--upgrade`.

The intuitive way to pin a file is to download it and hash it:

```bash
curl -sL https://cdn.jsdelivr.net/npm/redoc@2.5.3/... | sha256sum   # DON'T
```

**That is trust on first use.** The hash proves only that the bytes have not changed since
*you* fetched them. If the CDN had served a tampered file, you would pin the tampered hash,
and every future build would verify it happily, forever. The pin would look like diligence
without being it.

So the script never asks a CDN. It goes to the publisher:

1. `GET registry.npmjs.org/<pkg>/<version>` → `.dist.integrity` (sha512, base64)
2. download the release tarball, recompute sha512, compare against that digest
3. only then extract the file and record its sha256

Every network path in the script runs through one function that performs step 2, so no mode
can skip it. A tarball that fails is refused rather than vendored.

**Residual trust, stated plainly:** the npm registry itself, and TLS to it. That is a smaller
and more accountable surface than a CDN edge, but it is not zero. If you need better, mirror
the tarballs into your own artifact store and point the script at that.

## The full procedure

### 1. Check whether anything moved

```console
$ ./vendor-assets.sh --outdated
Checking npm for newer releases
  ✓ redoc 2.5.3 is current
  ↑ swagger-ui-dist 5.32.11 → 5.33.0 available
```

Nothing has changed on disk at this point. If everything is current, stop here.

### 2. Take the update

```console
$ ./vendor-assets.sh --upgrade

1. Resolving versions
  ✓ redoc 2.5.3
  ✓ swagger-ui-dist 5.32.11 → 5.33.0

2. Verifying tarballs against npm's published integrity
  ✓ redoc@2.5.3 tarball matches npm's published integrity
  ✓ swagger-ui-dist@5.33.0 tarball matches npm's published integrity

3. Extracting and recording sha256
  ✓ redoc.standalone.js unchanged (1071 KB)
  ~ swagger-ui-bundle.js updated (1520 KB)
  ~ swagger-ui.css updated (176 KB)
```

Read step 2. If a tarball fails npm's integrity check the script stops and vendors nothing;
that is a genuine supply-chain signal, not a flake — do not retry until you understand it.

### 3. Re-check offline, then look at the diff

```bash
./vendor-assets.sh
cd .. && git status --short local-development/gsd/static/vendor/
```

You will see the changed bundles and a one-line-per-package change in `ASSETS.lock`. The
lock records both the versions and the hashes, so the bump is legible in review even though
the minified diffs are not.

### 4. Rebuild and confirm

```bash
cd local-development
./build-and-push-external.sh --update-values
cd .. && helm upgrade --install group-sync-dashboard charts/group-sync-dashboard \
  -n group-sync-dashboard --set ingress.host=<host>
```

Then open `/api` and `/api/redoc` and confirm both still render. A major version of either
library can change its HTML contract, and no test here catches "the page loads but looks
wrong" — that check is your eyes.

To confirm nothing reaches for a CDN, from inside the cluster:

```bash
POD=$(oc get pods -n group-sync-dashboard -o name | head -1)
oc exec -n group-sync-dashboard $POD -c dashboard -- \
  sh -c 'ls /install/lib/python3.14/site-packages/gsd/static/vendor/'
```

### 5. Commit

```bash
git add local-development/gsd/static/vendor/
git commit -m "chore: bump swagger-ui-dist to 5.33.0"
```

## What is checked automatically

`tests/test_vendored_assets.py` runs on every suite:

* the three bundles exist and are listed in the lock;
* each one's sha256 matches the lock — catches a modified, truncated or half-committed file;
* the lock records which versions were vendored;
* `pyproject.toml` package-data includes `static/vendor/*`;
* the script's offline verify exits zero;
* no bundle is suspiciously small — a truncated download hashes consistently and would
  otherwise sail through the lock check.

`tests/test_api_contract.py` additionally asserts that when the bundles are present, neither
`/api` nor `/api/redoc` references a CDN.

## Things that have already gone wrong here

Recorded because each was invisible until something forced it into the open.

**`package-data` was `static/*`.** That single-level glob excludes `static/vendor/`, so the
wheel would have shipped without the bundles while every file sat correctly in git, and the
built image would have silently fallen back to the CDN. Now `static/*, static/vendor/*`, with
a test.

**The first pins were produced by hashing CDN downloads.** They happened to be correct — later
verified against npm — but the method could not have told the difference. That is why the
script exists rather than a documented `curl | sha256sum`.

**The first pins were also already stale.** `redoc@2.5.0` and `swagger-ui-dist@5.29.4` were
behind at the moment they were written down. `--outdated` exists so that is a five-second
question rather than an assumption.

## If you need to change which files are vendored

Edit the `ASSETS` array near the top of `vendor-assets.sh` — package, path inside the
tarball, destination filename — then run `--upgrade`. Versions deliberately live in the lock
rather than in the array, so a bump is a lock diff and not a script diff.

Anything referenced by `gsd/api.py` must exist under `/static/vendor/`, and the fallback there
will warn loudly and use a CDN if the directory is absent. That fallback is for a source
checkout that has never been through a container build; it should never be what a deployed
image does.
