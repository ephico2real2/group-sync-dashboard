# Deploying the mock cluster on CRC

## How the running one got there: by hand

Measured on the live CRC, 2026-09-18. Every object of the mock cluster carries
`kubectl.kubernetes.io/last-applied-configuration` and belongs to **no Helm release**:

| Object | Created by |
|---|---|
| `deploy/mock-openshift` | `oc apply`, by hand |
| `svc/mock-openshift` | `oc apply`, by hand |
| `secret/mock-cluster-creds` | `oc apply`, by hand |
| `configmap/mock-fixture` | `oc apply`, by hand |
| `issuer/mock-selfsigned`, `issuer/mock-ca-issuer` | `oc apply`, by hand |
| `certificate/mock-ca`, `certificate/mock-tls` | `oc apply`, by hand |

**No script deployed any of it.** The only script in `mock-app/` is `containerfile/entrypoint.sh`, which
runs *inside* the container. That is why the migration runbook called §4.9 the slowest part of a
rebuild. `deploy-mock.sh` beside this file is that missing sequence.

## The six steps, and why the order matters

1. **Build and push the image.** `release-crc.sh` does **not** build this one; it has its own
   Containerfile. It goes to CRC's internal registry as `mock-openshift:test`, and the Deployment runs
   it with `imagePullPolicy: Always`.
2. **The cert-manager chain, before the workload.** `certmanager-tls.yaml` creates
   `Issuer/mock-selfsigned` → `Certificate/mock-ca` (isCA, secret `mock-ca`) → `Issuer/mock-ca-issuer` →
   `Certificate/mock-tls`. The Deployment mounts `mock-tls`, so out of order the pod sits in
   `ContainerCreating`.
3. **The fixture ConfigMap.** `mock-fixture`, mounted at `/fixtures`, holding the one fixture the pod
   serves. The Deployment's `MOCK_FIXTURE` env var points inside that volume, so without the ConfigMap
   the pod cannot start. The live one was byte-for-byte identical to the committed fixture, so it is
   rebuilt straight from the file rather than carried.
4. **The workload.** `mock-openshift-deployment.yaml` and `mock-openshift-service.yaml`, both captured
   from the running cluster before it was deleted. The Service is ClusterIP on 6443. It mounts two
   volumes: `certs` from secret `mock-tls`, and `fixtures` from the ConfigMap above.
5. **The credentials the dashboard reads**, as secret `mock-cluster-creds` with two keys:
   - `ca.crt` — **must be the `mock-ca` root**, or the dashboard's TLS verification of the mock fails.
     Verified: the fingerprint of the live `ca.crt` equals `mock-ca`'s.
   - `token` — not a secret. It is `meta.token` from the fixture the pod serves, `mock-token-reference`
     for the default `reference.yaml`.
6. **Wire it into the dashboard.** A volume `mock-creds` from that secret, mounted at `/etc/gsd/mock`.
   This patch is **invisible to Helm** and must be re-applied after every `helm install` or `upgrade`.
   Without it the dashboard shows the mock cluster's token and ca files as absent and fails quietly.

## Doing it

```sh
cd local-development/mock-app/deploy
./deploy-mock.sh              # all five steps
./deploy-mock.sh --no-build   # skip the image
./deploy-mock.sh --verify     # check only, changes nothing
```

Environment overrides: `NS`, `REGISTRY`, `IMAGE`, `TAG`, and `FIXTURE` to serve a different fixture
(`paging.yaml`, `crd-absent.yaml`, `forbidden.yaml`). The script reads the matching `meta.token`
automatically, so the secret always agrees with the fixture.

Prerequisites it checks rather than assumes: a logged-in cluster, and cert-manager installed.

## Checking it worked

```sh
./deploy-mock.sh --verify
```

It reports the workload, the two certificates, the secret, and — the step most often forgotten —
whether the dashboard actually carries the `mock-creds` volume.

On the dashboard's Overview the mock cluster should appear as a second tile, reachable, alongside
`crc-local`. If it shows the token or ca file as absent, step 5 is missing.

## What the mock is for

It serves a fixture-driven OpenShift API on 6443 so the dashboard can be driven against a second
cluster without a second cluster. The fixtures live in `../fixtures/`; `reference.yaml` is the normal
one, and the other three exist to exercise a missing CRD, a forbidden response, and the continue-token
paging loop.

## Where the mock data comes from

The fixtures are **hand-authored YAML**, not recorded from a real cluster. There is no generator and no
capture tool: `fixtures/*.yaml` is the source of truth and the mock serves whichever one
`MOCK_FIXTURE` names.

| Fixture | What it is for |
|---|---|
| `reference.yaml` | the annotated reference cluster — the normal one, ~10.7 KB |
| `crd-absent.yaml` | GroupSync, operator and OAuth CRDs missing, to drive the plain-404 branches |
| `forbidden.yaml` | users, identities, namespaces, nodes, oauth and pods answer 403 |
| `paging.yaml` | `meta.pageSize` caps the page below the client's `limit=500`, driving its real continue-token loop |

**The format is fail-loud.** One YAML file with a fixed set of top-level keys — `meta`, `groupsyncs`,
`groups`, `users`, `identities`, `namespaces`, `roles`, `bindings`, `operatorConfigs`, `nodes`, `oauth`,
`oauthPods`, `auditLog`, `podLog`. Any unknown top-level key is **rejected** rather than ignored, so a
typo fails immediately instead of producing a quietly wrong cluster.

**Audit lines are shorthand.** You write `{kind, decision, user, at, code, provider?}` and the mock
expands each into the full Kubernetes-audit JSON envelope the dashboard's parser accepts. You never
hand-write the envelope. `kind` is `credential` for `/login`, `cli` for the challenging-client
authorize, and `session` for any other client id.

**`meta.token` is the account.** Whatever it holds is the bearer token the dashboard must present, which
is why `deploy-mock.sh` reads it out of the fixture rather than taking it as an argument — the secret
and the fixture can never disagree.

### Editing the data

Edit the fixture in `../fixtures/`, then re-run the deploy so the ConfigMap is rebuilt from it:

```sh
./deploy-mock.sh --no-build          # rebuilds the ConfigMap and rolls the pod
FIXTURE=paging.yaml ./deploy-mock.sh --no-build   # serve a different scenario
```

The full format, including every key and the `/_mock/*` control surface, is in `../README.md`.
