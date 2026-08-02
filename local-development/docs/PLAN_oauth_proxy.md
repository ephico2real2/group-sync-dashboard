# Plan: OpenShift OAuth in front of the dashboard

**Status:** researched, not implemented. Parked 2026-08-01 to work on the group drill-down.
**Goal:** close §13 Q4 of the dashboard plan — the Route is currently unauthenticated and
serves group membership to anyone who can reach the apps domain.

**Access model — decided:** *self-service*. Anyone who can log into the cluster can view the
dashboard. No access requests, no group membership to maintain, no SAR gate.

That is not a shortcut, it is the documented default. From the openshift/oauth-proxy README:

> The OpenShift provider defaults to allowing any user that can log into the OpenShift
> cluster.

So `--openshift-sar` is **omitted deliberately**. The 2023 Janus/Backstage integration omits
it for the same reason. Authentication without authorization is the whole intent here: the
dashboard stops being anonymously readable, and nobody has to file a ticket to see it.

## Shape

```text
Route (reencrypt) ──► Service :8443 ──► oauth-proxy :8443 ──► 127.0.0.1:8080 (dashboard)
                                             │
                                             └──► cluster OAuth server
```

Sidecar in the same pod, not a separate deployment. The point is that the dashboard binds
**127.0.0.1 only**, so there is no port on the pod network that bypasses the proxy.

## Pieces

| # | Piece | Note |
|---|---|---|
| 1 | SA annotation `serviceaccounts.openshift.io/oauth-redirectreference.primary` → the Route | makes the SA an OAuth client with no OAuthClient object to register |
| 2 | Service annotation `service.beta.openshift.io/serving-cert-secret-name` | service-ca issues and rotates the proxy's cert |
| 3 | Session secret, 32 random bytes, in a Secret | cookie signing; cannot be committed to a manifest |
| 4 | oauth-proxy sidecar on 8443 | args below |
| 5 | Service exposes 8443 only; 8080 disappears | |
| 6 | Route → `reencrypt` | router terminates with its trusted cert, re-encrypts to the pod |
| 7 | App binds `127.0.0.1:8080` | needs a `gsd/__main__.py` reading `GSD_HOST`/`GSD_PORT` |

## Args

```text
-provider=openshift
-https-address=:8443
-http-address=
-upstream=http://127.0.0.1:8080
-openshift-service-account=group-sync-dashboard
-openshift-ca=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
-tls-cert=/etc/tls/private/tls.crt
-tls-key=/etc/tls/private/tls.key
-cookie-secret-file=/etc/proxy/secrets/session_secret
-email-domain=*
-skip-provider-button                  # straight to login, no "Log in with OpenShift" click
-skip-auth-regex=^/(healthz|readyz)$   # kubelet probes must not get a 302 to the login page
```

`-skip-provider-button` matters for the self-service goal: without it every visitor clicks
through an interstitial that offers exactly one choice.

`-skip-auth-regex` for the probes is **not optional**. Move the probes to 8443/HTTPS at the
same time; if they still point at 8080 they will pass while proving nothing, because 8080 is
no longer the path anyone reaches.

## Verified on this cluster (2026-08-01)

- `service-ca` operator `Available` — the serving-cert annotation will be honoured.
- Both `service.alpha.` and `service.beta.` serving-cert annotations are in live use here
  (26 and 27 services). **Use `beta`** — `alpha` is what the old contrib example shows.
- `registry.redhat.io/openshift4/ose-oauth-proxy:latest` imports (digest
  `sha256:e68637bc…`), but **the kubelet could not pull it**: `oc import-image` uses cluster
  credentials while the node pull uses its own, and the node's did not work for it.
- The in-cluster `openshift/oauth-proxy:v4.4` imagestream exists but is 16 months old on a
  4.18 cluster.

## Open before implementing

1. **Which image.** Resolve the pull-credential problem for a current `ose-oauth-proxy`, or
   accept `openshift/oauth-proxy:v4.4`. Not yet confirmed that either actually starts here —
   the verification run was not completed.
2. **`system:auth-delegator`.** Neither the README nor the contrib example binds it, and with
   no SAR there may be nothing needing delegated review. Assume not required; confirm by
   watching for TokenReview 403s in the proxy log on first login.
3. **`reencrypt` and `destinationCACertificate`.** Whether the 4.18 router trusts the
   service-CA cert implicitly or needs it supplied on the Route.
4. **Test method.** curl cannot follow the OAuth redirect dance meaningfully; drive a real
   login with Playwright against the route.

## The multi-cluster gap — closed by the deployment model, not by the proxy

The proxy authenticates against the **hosting** cluster only. If one instance observed
several clusters, a user who can log in here would see group membership from clusters they
may have no rights on, and oauth-proxy has no way to express that — it would need per-cluster
authorization inside the app.

**The 2026-08-01 decision to deploy one instance per cluster removes the problem rather than
solving it.** An instance holds exactly one cluster's data and authenticates against that
same cluster, so "can log into this cluster" and "may see this data" become the same
statement. That is what makes the self-service model defensible here: the proxy is not
granting access to anything the user could not already read with `oc`.

This only holds while an instance observes a single cluster. If one is ever pointed at
several — the capability is still there — this gap comes back, and the authorization has to
move into the app.
