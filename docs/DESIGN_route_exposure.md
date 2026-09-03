# Design — expose the dashboard through a Route the router names

**Status:** implemented in chart 0.8.0 (PR #45). This records why the chart moved from an Ingress
to a Route it owns, why the OAuth callback became a reference rather than a URL, and the platform
precedent that shows the pattern is the documented one and not a local invention.

## The failure this closes

An ArgoCD Application failed at render time:

```text
ingress.host is not set and the cluster apps domain could not be read
```

The cause was structural. An Ingress must carry a host — OpenShift's ingress-to-route controller
creates **no Route at all** for a hostless Ingress — so with `ingress.host` empty the chart read the
cluster's apps domain with Helm's `lookup`. A plain `helm install` has a cluster and that works.
ArgoCD's repo-server renders with `helm template` and **no cluster connection**, so the lookup
returned nothing, every time, on every GitOps cluster. Argo does not support `lookup`
([argo-cd#5202](https://github.com/argoproj/argo-cd/issues/5202), open). Setting the host per
cluster was the documented workaround; the requirement was that auto-discovery work under Argo.

## The design

The chart owns a Route (`templates/route.yaml`, `route.enabled`, default true). The Ingress remains
as the alternative for plain Kubernetes (`ingress.enabled`, default false); the Ingress manifest
itself renders as it did in 0.7.1. Both on fails the render, as a policy of one front door: with
default hosts both would derive the same hostname and the router admits one claim per host and
path, and with two different explicit hosts there would be two doors to keep in step.

| | Route (default) | Ingress |
|---|---|---|
| host known at | admission: the router composes `<fullname>.<apps domain>` from `spec.subdomain` and reports it in `status.ingress[].host` | render time: `ingress.host`, or `lookup` |
| under `helm template` | renders | refuses without a host |
| OAuth callback on the ServiceAccount | `oauth-redirectreference`, the Route by name, resolved at login | `oauth-redirecturi`, a literal URL |
| a host set deliberately | `route.host` (or a carried-over `ingress.host`) becomes `spec.host`; the router admits it if valid and unclaimed | `ingress.host`, likewise |

Two properties were required and both hold on a router that honours `spec.subdomain` (OpenShift
4.11 and later): the hostname is `<fullname>.<apps domain>` with the namespace never appended, and
a host set on purpose is respected. `<fullname>` is not validated by the chart; a `nameOverride` or
`fullnameOverride` that is not a DNS label is rejected by the API server for the Route exactly as
it is for the Service, unchanged from 0.7.1.

## Why `spec.subdomain` and not an empty `spec.host`

Measured on OpenShift 4.18.2 in a scratch namespace:

| Route spec | `spec.host` after create | host in status |
|---|---|---|
| `subdomain: x` only | stays empty, also after re-apply | `x.apps-crc.testing` |
| neither host nor subdomain | server fills `<name>-<namespace>.apps-crc.testing` | same |

The hostless form appends the namespace — the doubled `group-sync-dashboard-group-sync-dashboard`
name — and writes a `spec` field git does not carry, so Argo reports the Route OutOfSync until an
`ignoreDifferences` on `/spec/host` is added
([argo-cd#20305](https://github.com/argoproj/argo-cd/issues/20305) is exactly that report). The
subdomain form has no spec drift and yields the same short hostname the Ingress path derived, so the
URL does not move on upgrade. Two caveats from the Route API, both survivable: an ingress controller
"may choose to ignore this suggested name" and report what it assigned, and a server that does not
support `subdomain` populates `spec.host` itself, which works but brings the drift back. Login still
works in either case, because the redirect reference resolves against whatever host the Route's
status reports.

## The redirect reference, and why `/oauth/callback` matches it

With an Ingress the generated Route has a random name (`probe-ingress-7669p` was observed), so it
cannot be referenced and the ServiceAccount had to carry a literal URL — which is the second reason
the host had to be known at render time. With a Route the chart names, the ServiceAccount carries:

```yaml
serviceaccounts.openshift.io/oauth-redirectreference.primary: >-
  {"kind":"OAuthRedirectReference","apiVersion":"v1","reference":{"kind":"Route","name":"group-sync-dashboard"}}
```

OpenShift resolves that at login time: host from the Route's status, scheme from its TLS. The
reference's own documentation says "all Ingresses for that route will now be considered valid". That
yields a base of `https://<host>`, and the proxy asks for `https://<host>/oauth/callback`. It
matches because of the OAuth server's documented rule for client redirect URIs:

> The `redirect_uri` parameter specified in requests to `<namespace_route>/oauth/authorize` and
> `<namespace_route>/oauth/token` must be equal to or prefixed by one of these URIs.

In code, `openshift/osin`'s `urivalidate.go` accepts an exact path match or a strict sub-path of the
base, with scheme and host required to match. Measured on CRC 4.18.2 on the upgraded release: the
proxy's authorize request was accepted (200, the OpenShift login page), and the same request with a
foreign `redirect_uri` was refused `400 invalid_request`. The acceptance was the reference doing its
job, not a permissive server.

## The precedent: Red Hat's own Jenkins template

`openshift/jenkins`'s `jenkins-ephemeral.json` ships this pattern, and it maps onto the chart almost
one-to-one:

- The ServiceAccount carries `serviceaccounts.openshift.io/oauth-redirectreference.jenkins`, a JSON
  reference to a Route by name. Same annotation family, same JSON shape as ours.
- The Route is named `${JENKINS_SERVICE_NAME}`, so Route and Service share one name. Ours share
  `<fullname>`, which is the release name whenever the release is called after the chart.
- The Route sets neither `host` nor `subdomain`. Its TLS is `edge` with
  `insecureEdgeTerminationPolicy: Redirect`.
- Nothing in the template names a callback path. The Jenkins login plugin calls back on
  `/securityRealm/finishLogin` (`OpenShiftOAuth2SecurityRealm.SECURITY_REALM_FINISH_LOGIN`), and the
  prefix rule above is what makes that valid against a reference resolving to `https://<host>`. That
  is the same relationship as our `/oauth/callback`.

**The one deliberate difference.** Jenkins leaves the Route fully hostless, so the API server writes
`spec.host` as `jenkins-<namespace>.<apps domain>`. We set `spec.subdomain: <fullname>` instead,
which is why we get `group-sync-dashboard.apps-crc.testing` without the namespace, and why
`spec.host` stays empty for Argo. The Jenkins form is the one argo-cd#20305 complains about; the
template predates GitOps concerns and is deployed with `oc new-app`, so it never had to care. The
redirect reference itself does not care either way, since it resolves against whatever host the
Route's status reports.

**TLS differs for a reason, not by accident.** Jenkins terminates at the router with `edge` because
Jenkins speaks plain HTTP behind it. Our proxy terminates TLS itself with the service-ca
certificate, so the router must `reencrypt`. That rule is unchanged from the Ingress path
(`gsd.termination`).

`openshift/oauth-proxy`'s own `contrib/sidecar.yaml` is a second precedent, closer still: a
reference to a Route named `proxy`, `reencrypt`, and the proxy's `/oauth/callback`.

## Upgrade behaviour, measured

The CRC release was upgraded from 0.7.1 with its own values file and image. Helm created the chart's
Route, then deleted the Ingress and with it the controller-generated Route. The new Route was admitted
on the same hostname with `spec.host` empty; the pod was untouched (revision 139).

No `HostAlreadyClaimed` occurs while the two Routes coexist, and the reason is in the router: the
controller-generated Route carries `spec.path: /` (from the Ingress rule) and the chart's Route
carries no path, and `openshift/router`'s `unique_host.go` treats routes on one host as conflicting
only when their paths are equal. Both are admitted; the old one is garbage-collected with its Ingress.
Had a conflict existed, the same code re-activates a displaced route when the claimant is deleted, so
recovery would still need no operator action. A second upgrade
that only flipped `argocd.enabled` to its new default changed metadata only — same pod, no rollout
(revision 140). Sessions, data and RBAC were not involved.

One local side effect worth knowing on a CRC Mac: CRC keeps `/etc/hosts` entries for Routes it saw
at start, and removed `group-sync-dashboard.apps-crc.testing` when the generated Route was deleted.
The cluster served the new Route correctly (verified with `--resolve`); the name resolves again after
a CRC restart or a hosts-file line.

## What is inferred rather than measured

- An actual Argo sync. The reference cluster has no Argo controller. The drift reasoning rests on
  the measured `spec.host` behaviour and the two cited issues.
- Behaviour on a server that does not honour `spec.subdomain` (before OpenShift 4.11). Stated from
  the Route API's field documentation, not measured.

An earlier draft of this document claimed a server-side-apply hazard on a hostless Route and an
upgrade transient with both Routes refused. The Codex review of PR #45 refuted both: the first was
unsupported, the second is ruled out by the router's path-aware admission described above. Both
claims were removed rather than qualified. The review record is `REVIEW_route_exposure.md`.

## References

- Red Hat, OAuthClient `redirectURIs` ("equal to or prefixed by"):
  <https://docs.redhat.com/en/documentation/openshift_container_platform/4.16/html/authentication_and_authorization/configuring-internal-oauth>
- Red Hat, service accounts as OAuth clients (`oauth-redirectreference`):
  <https://docs.redhat.com/en/documentation/openshift_container_platform/4.16/html/authentication_and_authorization/using-service-accounts-as-oauth-client>
- `openshift/osin` redirect-URI validation: <https://github.com/openshift/osin/blob/master/urivalidate.go>
- `openshift/jenkins` template: <https://github.com/openshift/jenkins/blob/master/openshift/templates/jenkins-ephemeral.json>
- `openshift/jenkins-openshift-login-plugin`: <https://github.com/openshift/jenkins-openshift-login-plugin>
- `openshift/oauth-proxy` sidecar example: <https://github.com/openshift/oauth-proxy/blob/master/contrib/sidecar.yaml>
- OpenShift enhancement, route subdomain: <https://github.com/openshift/enhancements/blob/master/enhancements/ingress/route-subdomain.md>
- Route API, `host` and `subdomain` field docs: <https://github.com/openshift/api/blob/master/route/v1/types.go>
- argo-cd#5202 (Helm `lookup` unsupported): <https://github.com/argoproj/argo-cd/issues/5202>
- argo-cd#20305 (hostless Route `spec.host` drift): <https://github.com/argoproj/argo-cd/issues/20305>
- argo-cd#2370 (Route `status` drift): <https://github.com/argoproj/argo-cd/issues/2370>
- `openshift/router` host admission, path-aware: <https://github.com/openshift/router/blob/master/pkg/router/controller/unique_host.go>
