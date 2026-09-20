{{- define "gsd.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "gsd.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "gsd.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "gsd.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
`app` is kept alongside the standard labels because the ServiceMonitor selects the Service
by its metadata labels. Dropping it silently breaks scraping while every object still looks
correct — that exact bug was found on this deployment.
*/}}
{{- define "gsd.selectorLabels" -}}
app.kubernetes.io/name: {{ include "gsd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "gsd.fullname" . }}
{{- end -}}

{{- define "gsd.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "gsd.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
The image reference, resolved digest first, then tag, then appVersion.

WHY THREE FORMS AND NOT ONE. `image.tag` ships EMPTY so the chart deploys the appVersion it
declares (see values.yaml under `image`). That alias is republished when the application version
changes, and `imagePullPolicy` is `Always`, so every container creation re-resolves it — which is
correct for a release channel and wrong for anyone who needs the same bytes after a node drain.
A tag can be repointed by whoever owns the registry; a digest cannot be repointed by anyone. So
`image.digest` is the immutable option, and it wins over both of the others.

`@` AND NOT `:`, which is the whole reason this is a branch rather than another `default` in the
chain: an OCI reference by digest is `repository@sha256:...`. Joining a digest with `:` produces
`repository:sha256:abc...`, which is a syntactically valid TAG that no registry has, so the pod
fails with ImagePullBackOff naming a tag nobody ever pushed.
*/}}
{{- define "gsd.image" -}}
{{- $digest := default "" .Values.image.digest -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}
{{- fail (printf "image.digest %q is not a digest. Expected sha256: followed by 64 lowercase hex characters, for example sha256:aa6a7f5463c6... — get one with:\n\n  skopeo inspect --no-tags docker://%s:%s | grep Digest\n\nRefused at render time on purpose. A malformed digest still produces a reference Kubernetes will accept, so the alternative is a release that installs cleanly and then sits in ImagePullBackOff against a digest no registry has. UPPERCASE hex is rejected too: registries treat the digest as a literal string, so sha256:AB... and sha256:ab... are different references and only one of them exists.\n\nLeave image.digest empty to deploy image.tag, or the chart's appVersion when that is empty too." $digest .Values.image.repository (default .Chart.AppVersion .Values.image.tag)) -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository $digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}
{{- end -}}

{{/*
TLS termination. The proxy terminates TLS itself using the service-ca certificate, so the
router must RE-ENCRYPT to it. Leaving this as edge sends plaintext to a port that only speaks
TLS and the Route silently fails.

Kept here rather than inline so the rule lives in one place: it is the kind of coupling that
gets forgotten when someone later adds another exposure path — which is exactly what happened
when the Route joined the Ingress, so the helper now takes the caller's configured value:
  (dict "root" . "configured" .Values.route.termination)     from route.yaml
  (dict "root" . "configured" .Values.ingress.termination)   from ingress.yaml
*/}}
{{- define "gsd.termination" -}}
{{- if .root.Values.oauthProxy.enabled -}}
reencrypt
{{- else -}}
{{ .configured }}
{{- end -}}
{{- end -}}

{{/*
What exposes the dashboard: "Route", "Ingress" or "" (neither). Two flags in values,
route.enabled and ingress.enabled, validated HERE and in one place so that every template
that branches on them sees the same answer.

Both on fails the render. They would derive the same hostname — <fullname>.<apps domain>,
the Route from spec.subdomain and the Ingress from the cluster lookup — and the second to be
admitted is refused with HostAlreadyClaimed. That is a failure the operator would meet on
the cluster, after a green install; better to meet it at render time with its cause named.
*/}}
{{- define "gsd.exposure" -}}
{{- if and .Values.route.enabled .Values.ingress.enabled -}}
{{- fail "route.enabled and ingress.enabled are both true. This chart exposes the Service through exactly one object, as a policy: with default hosts both would derive the same hostname and the router admits one claim per host and path, leaving the other refused in its status after an install that reported success; with two different explicit hosts you would have two front doors to keep in step. Choose one: route.enabled=true is the OpenShift default and needs no host at render time; ingress.enabled=true is for plain Kubernetes and needs ingress.host." -}}
{{- else if .Values.route.enabled -}}
Route
{{- else if .Values.ingress.enabled -}}
Ingress
{{- end -}}
{{- end -}}

{{/*
The Route's effective host. An explicit route.host wins; an ingress.host set in an older
values file is honoured next, so an upgrade onto the Route default never silently moves a URL
somebody pinned; empty means "let the router name it from spec.subdomain".
*/}}
{{- define "gsd.routeHost" -}}
{{- .Values.route.host | default .Values.ingress.host -}}
{{- end -}}

{{/*
The externally reachable host, WHEN THE ROUTE IS OFF. The Ingress needs it because a hostless
Ingress produces no Route on OpenShift, and with the OAuth proxy on the ServiceAccount must
advertise a literal callback URL: the ingress-to-route controller names the generated Route
`<ingress-name>-<random>` (observed: probe-ingress-7669p), so the redirectREFERENCE form —
which points at a Route by name — cannot be used with an Ingress. Hence redirectURI, hence a
host that must be known here.

The default Route path never calls this. It emits spec.subdomain and lets the router name the
host, and the ServiceAccount references the Route by name, so nothing on that path needs the
host at template time. That is why the chart renders under ArgoCD — see route.yaml.
*/}}
{{- define "gsd.externalHost" -}}
{{- if .Values.ingress.host -}}
{{ .Values.ingress.host }}
{{- else -}}
{{- /*
Derive it from the cluster's published apps domain.

A Route auto-generates its host when spec.host is empty; an Ingress does NOT, and
OpenShift's ingress-to-route controller silently creates no Route at all for a hostless
Ingress. A default install was therefore unreachable with no error anywhere — the Ingress
existed, the pod was healthy, and nothing was serving.

`lookup` returns empty during `helm template` and dry-run, which is why the fallback below
fails loudly rather than emitting a host that would be wrong.
*/ -}}
{{- /*
NAME.DOMAIN, not NAME-NAMESPACE.DOMAIN.

OpenShift's own Route auto-generation uses <name>-<namespace> to keep two namespaces from
claiming one hostname. That convention earns its keep for arbitrary app Routes; it does not
here, where the usual install is one dashboard per cluster and the release name and the
namespace are both `group-sync-dashboard`, so the generated host said the same word twice:
group-sync-dashboard-group-sync-dashboard.apps.example.com.

THE TRADE, stated because it is real: two releases in DIFFERENT namespaces now derive the
SAME host, and the second Route is refused with HostAlreadyClaimed. That is legible — it is
written into the refused Route's status — but it is NOT a Helm failure: the object is accepted
by the API and the install reports success, so check `oc get route`. The fix is one flag — set
`ingress.host` explicitly on the second. Worth it for a URL a human can type and read out in
a meeting.
*/ -}}
{{- $cfg := (lookup "config.openshift.io/v1" "Ingress" "" "cluster") -}}
{{- if and $cfg $cfg.spec.domain -}}
{{ printf "%s.%s" (include "gsd.fullname" .) $cfg.spec.domain }}
{{- else -}}
{{- fail "ingress.host is not set and the cluster apps domain could not be read.\n\nThe domain is normally auto-detected, so a plain `helm install`/`helm upgrade` needs no flag. It cannot be detected in three cases, and one of them is probably yours:\n\n  1. GitOps. ArgoCD, Flux and anything else built on `helm template` render with NO cluster connection, so the lookup returns nothing. You have turned the default Route off (route.enabled=false) and the Ingress on; a Route needs no host at render time because the cluster names it, so either turn it back on or set ingress.host.\n  2. `helm template` or `--dry-run` run by hand. Use `--dry-run=server`, or pass the host.\n  3. The installing identity cannot read ingresses.config/cluster. It is cluster-scoped and NOT readable by an ordinary user, so a namespace-scoped installer must be given the host.\n\nSet it with:\n  --set ingress.host=group-sync-dashboard.$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')\nor use the default Route, which needs no host at all:\n  --set route.enabled=true --set ingress.enabled=false\n\nThis fails the render on purpose. An Ingress without a host produces NO Route on OpenShift, so the alternative is a release that installs cleanly, reports healthy, and is unreachable." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
The effective PVC access mode. Empty in values derives it from replicaCount, because the
right mode is a consequence of the replica count rather than an independent choice:

  1 replica  -> ReadWriteOncePod. One pod owns one SQLite file, and RWOP is the only mode
                that ENFORCES that. Verified on the reference cluster: a second pod claiming
                the same PVC is refused by the scheduler with "node has pod using
                PersistentVolumeClaim with the same name and ReadWriteOncePod access mode".
  >1 replica -> ReadWriteMany. Each pod writes /data/$POD_NAME/gsd.db, so the VOLUME is
                shared while the files are not.

ReadWriteOnce is deliberately not a default for either. It binds one NODE, not one pod, so
two pods landing on the same node can both open the same database file — the guarantee it
appears to give is not the guarantee SQLite needs.
*/}}
{{- define "gsd.accessMode" -}}
{{- if .Values.persistence.accessMode -}}
{{- .Values.persistence.accessMode -}}
{{- else if gt (int .Values.replicaCount) 1 -}}
ReadWriteMany
{{- else -}}
ReadWriteOncePod
{{- end -}}
{{- end -}}

# ---------------------------------------------------------------------------
# Session cookie lifetime
# ---------------------------------------------------------------------------
# ONE absolute number, measured from login, deliberately NOT sliding. There is no
# `refresh` key and no -cookie-refresh flag, and that is a measurement rather than a
# preference: with provider=openshift the proxy's refresh-time revalidation sends the
# token as a QUERY PARAMETER, which the API server ignores — it answered 403 naming the
# caller system:anonymous — so every refresh interval would CLEAR the session instead of
# extending it. A forced-logout timer wearing a keep-alive's name. The cluster-logging
# operator ships Kibana's oauth-proxy the same way on this same provider: -cookie-expire
# with no -cookie-refresh.
#
# The value is OURS, not the cluster's. Kibana derives its cookie lifetime from
# spec.tokenConfig.accessTokenInactivityTimeout because a ServiceAccount-as-OAuth-client
# cannot own a token policy and must defer to whatever the cluster declares. That
# derivation was built and then dropped here: it freezes at render time, it is unreadable
# for a namespace-scoped installer, and it makes the session length depend on a field an
# operator of THIS chart does not control. A plain value they can see and set is better.
#
# `dig` is NOT used here, and that is a measured choice: it panics on an intermediate that
# EXISTS AND IS NIL — `interface conversion: interface {} is nil, not map[string]interface{}`
# — which is what a values file produces the moment somebody comments out the sub-keys under
# `cookie:`. A trailing `| default` cannot rescue it, because the error happens inside dig
# before any value comes back. `default dict` on each hop tolerates both absent and null.
{{- define "gsd.cookieExpire" -}}
{{- $cookie := (.Values.oauthProxy | default dict).cookie | default dict -}}
{{- /* Helm's `default` treats a NUMERIC zero as empty, so an unquoted `expire: 0` silently became
     4h while the string "0" stayed zero (review of C4). A zero the operator typed is returned as
     typed, and the deployment refuses it by name: a zero cap is not a cap. */ -}}
{{- if and (hasKey $cookie "expire") (eq (toString $cookie.expire) "0") -}}
0
{{- else -}}
{{- $cookie.expire | default "4h" -}}
{{- end -}}
{{- end -}}

# Go duration string -> seconds (a float for sub-second units), or -1 when it is not a
# duration the proxy could parse. Exists so the render guard can refuse a malformed value
# before the sidecar refuses it at startup, where the reason would be buried in `oc logs`
# while `helm upgrade` reported success.
{{- define "gsd.durationSeconds" -}}
{{- $s := toString . -}}
{{- if eq $s "0" -}}
0
{{- else if not (regexMatch "^([0-9]+(\\.[0-9]+)?(ns|us|µs|ms|s|m|h))+$" $s) -}}
-1
{{- else -}}
{{- $total := 0.0 -}}
{{- $mult := dict "ns" 0.000000001 "us" 0.000001 "µs" 0.000001 "ms" 0.001 "s" 1.0 "m" 60.0 "h" 3600.0 -}}
{{- range $tok := regexFindAll "[0-9]+(\\.[0-9]+)?(ns|us|µs|ms|s|m|h)" $s -1 -}}
{{- $unit := regexFind "[a-zµ]+$" $tok -}}
{{- $total = addf $total (mulf (float64 (trimSuffix $unit $tok)) (get $mult $unit)) -}}
{{- end -}}
{{- if eq (floor $total) $total -}}{{ int64 $total }}{{- else -}}{{ $total }}{{- end -}}
{{- end -}}
{{- end -}}

# ── Per-user visibility ──────────────────────────────────────────────────────────────
# Every read below is nil-safe on purpose: commenting out the sub-keys in a values file
# leaves `visibility:` (or `adminSar:`) present-but-nil, which a bare field access — and
# sprig's dig — panics on. Intermediates are defaulted to a dict and a nil leaf is
# treated as "not set", which falls back to the shipped default, never to "off".

# Returns the word true or false. The switch guards personal data, so the asymmetry is
# deliberate: the conventional false spellings disable it — false, FALSE, 0, no, all of
# which Helm and the app's own _bool_setting already read as false, and honouring them
# keeps this flag consistent with every other boolean in the chart — while anything
# UNRECOGNISED (a typo like "flase", or "nonsense") resolves to true. Measured both ways.
# A misspelling must never be the thing that quietly switches a safeguard off.
{{- define "gsd.visibilityEnabled" -}}
{{- if eq (toString ((.Values.visibility | default dict).enabled)) "false" -}}
false
{{- else -}}
true
{{- end -}}
{{- end -}}

# The four adminSar fields, each validated where it is resolved so a nonsensical shape
# refuses to render anywhere it would be used. RBAC matching is exact and lowercase, so a
# miscased or misspelt field would not error — it would answer allowed=false for every
# viewer and silently demote every administrator, which is why these fail the render
# instead of passing the string through.

{{- define "gsd.visibilitySarApiGroup" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "apiGroup")) (kindIs "invalid" $sar.apiGroup) -}}
rbac.authorization.k8s.io
{{- else -}}
{{- $g := trim (toString $sar.apiGroup) -}}
{{- if not (regexMatch "^[a-z0-9.-]*$" $g) -}}
{{- fail (printf "visibility.adminSar.apiGroup %q is not an API group. Give the group alone (e.g. user.openshift.io, rbac.authorization.k8s.io), no version suffix, or \"\" for the core group." $g) -}}
{{- end -}}
{{- $g -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarResource" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "resource")) (kindIs "invalid" $sar.resource) -}}
clusterrolebindings
{{- else -}}
{{- $r := trim (toString $sar.resource) -}}
{{- if not (regexMatch "^[a-z0-9-]+(/[a-z0-9-]+)?$" $r) -}}
{{- fail (printf "visibility.adminSar.resource %q is not a resource. Use the lowercase plural (e.g. groups, rolebindings), optionally resource/subresource (e.g. pods/log). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $r) -}}
{{- end -}}
{{- $r -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarVerb" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "verb")) (kindIs "invalid" $sar.verb) -}}
list
{{- else -}}
{{- $v := trim (toString $sar.verb) -}}
{{- if not (regexMatch "^[a-z]+$" $v) -}}
{{- fail (printf "visibility.adminSar.verb %q is not a verb. Kubernetes verbs are lowercase words (list, get, watch, ...). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $v) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarNamespace" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "namespace")) (kindIs "invalid" $sar.namespace) -}}
{{- else -}}
{{- $n := trim (toString $sar.namespace) -}}
{{- if not (regexMatch "^[a-z0-9-]*$" $n) -}}
{{- fail (printf "visibility.adminSar.namespace %q is not a namespace name. Leave it empty for a cluster-scoped check." $n) -}}
{{- end -}}
{{- $n -}}
{{- end -}}
{{- end -}}

# The four usageAdminSar fields — the Usage tab's SEPARATE, STRICTER threshold. Same nil-safe
# style and same render-time validation as adminSar above, because the operator meets one pattern
# twice: a nonsensical shape fails the render here rather than silently answering allowed=false for
# every viewer (RBAC matching is exact and lowercase). The DEFAULT differs — a write verb, `update
# clusterrolebindings`, because no read check separates cluster-admin from cluster-reader, and the
# Usage dataset is the one thing on the cluster that cannot be reproduced with oc. See
# docs/SPEC_usage_admin_tier.md. The dashboard never writes; a SubjectAccessReview only asks.

{{- define "gsd.usageVisibilitySarApiGroup" -}}
{{- $sar := ((.Values.visibility | default dict).usageAdminSar) | default dict -}}
{{- if or (not (hasKey $sar "apiGroup")) (kindIs "invalid" $sar.apiGroup) -}}
rbac.authorization.k8s.io
{{- else -}}
{{- $g := trim (toString $sar.apiGroup) -}}
{{- if not (regexMatch "^[a-z0-9.-]*$" $g) -}}
{{- fail (printf "visibility.usageAdminSar.apiGroup %q is not an API group. Give the group alone (e.g. rbac.authorization.k8s.io, user.openshift.io), no version suffix, or \"\" for the core group." $g) -}}
{{- end -}}
{{- $g -}}
{{- end -}}
{{- end -}}

{{- define "gsd.usageVisibilitySarResource" -}}
{{- $sar := ((.Values.visibility | default dict).usageAdminSar) | default dict -}}
{{- if or (not (hasKey $sar "resource")) (kindIs "invalid" $sar.resource) -}}
clusterrolebindings
{{- else -}}
{{- $r := trim (toString $sar.resource) -}}
{{- if not (regexMatch "^[a-z0-9-]+(/[a-z0-9-]+)?$" $r) -}}
{{- fail (printf "visibility.usageAdminSar.resource %q is not a resource. Use the lowercase plural (e.g. clusterrolebindings, secrets), optionally resource/subresource (e.g. pods/log). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $r) -}}
{{- end -}}
{{- $r -}}
{{- end -}}
{{- end -}}

{{- define "gsd.usageVisibilitySarVerb" -}}
{{- $sar := ((.Values.visibility | default dict).usageAdminSar) | default dict -}}
{{- if or (not (hasKey $sar "verb")) (kindIs "invalid" $sar.verb) -}}
update
{{- else -}}
{{- $v := trim (toString $sar.verb) -}}
{{- if not (regexMatch "^[a-z]+$" $v) -}}
{{- fail (printf "visibility.usageAdminSar.verb %q is not a verb. Kubernetes verbs are lowercase words (update, create, get, ...). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $v) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}

{{- define "gsd.usageVisibilitySarNamespace" -}}
{{- $sar := ((.Values.visibility | default dict).usageAdminSar) | default dict -}}
{{- if or (not (hasKey $sar "namespace")) (kindIs "invalid" $sar.namespace) -}}
{{- else -}}
{{- $n := trim (toString $sar.namespace) -}}
{{- if not (regexMatch "^[a-z0-9-]*$" $n) -}}
{{- fail (printf "visibility.usageAdminSar.namespace %q is not a namespace name. Leave it empty for a cluster-scoped check." $n) -}}
{{- end -}}
{{- $n -}}
{{- end -}}
{{- end -}}

{{/*
The cluster-configuration tier's two SAR blocks (#230): visibility.clusterConfigViewSar and
visibility.clusterConfigManageSar. ONE parameterised helper rather than eight near-identical ones —
the two blocks and their four fields validate identically, and a copy per field is four more places
for a guard to drift. Call it with a dict: {ctx, block, field, default}.

Same discipline as the adminSar helpers: nil-safe (commenting out the sub-keys leaves
`visibility:` present-but-nil, which a bare field access panics on), and a malformed value FAILS
THE RENDER rather than silently answering no for every viewer — which here would not demote an
administrator but lock everyone out of the surface, including the person trying to fix it.
*/}}
{{- define "gsd.clusterConfigSarField" -}}
{{- $sar := (index (.ctx.Values.visibility | default dict) .block) | default dict -}}
{{- if or (not (hasKey $sar .field)) (kindIs "invalid" (index $sar .field)) -}}
{{- .default -}}
{{- else -}}
{{- $v := trim (toString (index $sar .field)) -}}
{{- $ok := dict "apiGroup" "^[a-z0-9.-]*$" "resource" "^[a-z0-9-]+(/[a-z0-9-]+)?$" "verb" "^[a-z]+$" "namespace" "^[a-z0-9-]*$" -}}
{{- if not (regexMatch (index $ok .field) $v) -}}
{{- fail (printf "visibility.%s.%s %q is not a %s. RBAC matching is exact, so anything else would answer no for every viewer and close the Cluster Configurations surface to everyone." .block .field $v .field) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}

# How long a decided tier is cached, per viewer. Whole seconds, and 0 disables caching.
#
# This is the ONE knob whose wrong value is a security consequence rather than a broken render, so
# it is worth saying what each direction costs. Larger: a reader REMOVED from an admin group keeps
# the wide view for up to this long — the fail-open direction, and the reason the default is a
# minute rather than an hour. Smaller: a SubjectAccessReview plus a group read per reader per
# request, measured at 97ms for the 65-group reference cluster (gsd/kube.py, TierResolver).
#
# A decided answer is cached; an ERROR never is, so this number does not extend an outage.
#
# Nil-safe for the same reason the adminSar helpers are: commenting out the sub-keys leaves
# `visibility:` present-but-nil, which a bare field access panics on.
{{- define "gsd.visibilityTierTtl" -}}
{{- $v := .Values.visibility | default dict -}}
{{- if or (not (hasKey $v "tierTtlSeconds")) (kindIs "invalid" $v.tierTtlSeconds) -}}
60
{{- else -}}
{{- $t := trim (toString $v.tierTtlSeconds) -}}
{{- /* Whole non-negative seconds only. A float would reach the app's int() cast and fall back to
       the default with only a log line to say so; a negative would make every entry instantly
       stale, turning the cache off while the values file claims it is on. Both are quieter
       failures than a refused render, which is why this refuses. */ -}}
{{- if not (regexMatch "^[0-9]+$" $t) -}}
{{- fail (printf "visibility.tierTtlSeconds %q is not a whole number of seconds. Use an integer >= 0 (0 disables caching, at the cost of a SubjectAccessReview per reader per request). A fractional or negative value would be silently discarded by the app and leave this file describing a cache that is not running." $t) -}}
{{- end -}}
{{- $t -}}
{{- end -}}
{{- end -}}

# logLevel, validated and case-normalised at render time. THE APP NO LONGER CRASHES ON A BAD VALUE —
# an earlier version of this comment said it did, and the same change that added this helper also
# gave `gsd/api.py#_resolve_log_level` a fallback, which made the claim false. Corrected in review
# rather than left to mislead.
#
# The two boundaries are deliberately different, and it is not an inconsistency:
#   THE CHART REFUSES, because a release value is deterministic input available before any workload
#   changes. Failing at `helm template` costs nothing and forces the value to be corrected once.
#   THE APP DEGRADES — it runs at INFO and warns — because a directly supplied GSD_LOG_LEVEL (a
#   `podman run`, an `oc set env`) reaches a running process, and a logging typo is not grounds for
#   an outage.
# So the chart can be stricter than the app without either being wrong.
#
# The history worth keeping: `create_app` used to pass the value straight to logging.basicConfig,
# and that function IS the uvicorn factory, so Python's `ValueError: Unknown level: 'debug'` stopped
# the container from starting. Measured then: lowercase `debug`, `Debug`, `info`, a numeric `20` and
# an empty string each crash-looped the pod. That is why this guard exists; the app-side fallback is
# the second layer, for deployments that never render this chart.
#
# CASE IS NORMALISED rather than refused. `logLevel: debug` is the natural thing to write and it
# unambiguously means DEBUG, so upper-casing it removes an outage class with no loss of meaning.
# This is not the same as letting a misspelling through: `trace` still fails, because there is no
# level it could have meant.
#
# The accepted set is exactly the five the values file documents. Python itself would take a few
# more spellings, and they are refused on purpose: a level is a promise about what you will see, and
# two ways to write one level — or a name whose effect is the opposite of how it reads — is not one.
{{- define "gsd.httpLogLevel" -}}
{{- $raw := .Values.httpLogLevel -}}
{{- if or (not (hasKey .Values "httpLogLevel")) (kindIs "invalid" $raw) -}}
WARNING
{{- else -}}
{{- $l := upper (trim (toString $raw)) -}}
{{- if not (has $l (list "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL")) -}}
{{- fail (printf "httpLogLevel %q is not a log level. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nThis value governs the HTTP REQUEST RECORD only — httpx (outbound API calls) and uvicorn.access (inbound requests). This app's own loggers are `logLevel`, a different value.\n\nINFO restores the per-request lines that were the default before #245; WARNING keeps the failures and drops the routine 200s." (toString $raw)) -}}
{{- end -}}
{{- $l -}}
{{- end -}}
{{- end -}}

{{- define "gsd.logLevel" -}}
{{- $raw := .Values.logLevel -}}
{{- if or (not (hasKey .Values "logLevel")) (kindIs "invalid" $raw) -}}
INFO
{{- else -}}
{{- $l := upper (trim (toString $raw)) -}}
{{- if not (has $l (list "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL")) -}}
{{- fail (printf "logLevel %q is not a log level. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nIf you are trying to raise the OAUTH-SERVER's verbosity so the Logins tab has something to read, that is the chart's `authLogLevel` value, not this one — a different setting on a different object.\n\nRefused here rather than passed through, because a release value can be corrected before anything is deployed. The app itself is more forgiving with a directly supplied GSD_LOG_LEVEL — it runs at INFO and logs a warning — so this is the stricter of two boundaries, not the only one." (toString $raw)) -}}
{{- end -}}
{{- $l -}}
{{- end -}}
{{- end -}}

{{/*
config.alerts.groupCountCliff, validated at render so a threshold that can never or always
fire is refused here rather than discovered as silence. Emits nothing; include it for effect.
*/}}
{{- define "gsd.groupCountCliff" -}}
{{- $c := ((.Values.config | default dict).alerts | default dict).groupCountCliff | default dict -}}
{{- $ratio := $c.dropRatio | float64 -}}
{{- if or (le $ratio 0.0) (gt $ratio 1.0) -}}
{{- fail (printf "config.alerts.groupCountCliff.dropRatio must be in (0, 1]; got %v" $c.dropRatio) -}}
{{- end -}}
{{- if lt ($c.minMembers | int) 1 -}}
{{- fail (printf "config.alerts.groupCountCliff.minMembers must be >= 1; got %v" $c.minMembers) -}}
{{- end -}}
{{- if le ($c.windowHours | float64) 0.0 -}}
{{- fail (printf "config.alerts.groupCountCliff.windowHours must be > 0; got %v" $c.windowHours) -}}
{{- end -}}
{{- /* The window is reconstructed from polls: shorter than one poll interval, it has no
       observation at its start and a cliff inside it can vanish before the next poll or
       before the rule's pending period (found in review, PR #72). */ -}}
{{- if lt (mulf ($c.windowHours | float64) 3600.0) (.Values.config.pollIntervalSeconds | float64) -}}
{{- fail (printf "config.alerts.groupCountCliff.windowHours must cover at least one poll interval; got %v hours with config.pollIntervalSeconds=%v" $c.windowHours .Values.config.pollIntervalSeconds) -}}
{{- end -}}
{{- end -}}
{{/*
monitoring.grafanaDashboard.enabled is a tri-state: "" follows monitoring.serviceMonitor.enabled,
true/false are explicit. Anything else refuses the render — a misspelt "ture" must not
silently become "off". Returns the string "true" or "false".
*/}}
{{- define "gsd.grafanaDashboardEnabled" -}}
{{- $mon := .Values.monitoring | default dict -}}
{{- $raw := ($mon.grafanaDashboard | default dict).enabled -}}
{{- if or (kindIs "invalid" $raw) (eq (toString $raw) "") -}}
{{- /* nil-safe one hop up too: `--set monitoring=null` must be "off", not a nil-pointer render (review, PR #74). */ -}}
{{- toString (($mon.serviceMonitor | default dict).enabled) -}}
{{- else if eq (toString $raw) "true" -}}
true
{{- else if eq (toString $raw) "false" -}}
false
{{- else -}}
{{- fail (printf "monitoring.grafanaDashboard.enabled must be true, false or \"\" (follow the ServiceMonitor); got %q" (toString $raw)) -}}
{{- end -}}
{{- end -}}

# ── Idle timeout ──────────────────────────────────────────────────────────────────────
# Nil-safe like the cookie helpers: commenting out the sub-keys leaves `session:` or
# `idleTimeout:` present-but-nil, which a bare field access panics on. Each value is validated
# where it is resolved, so a values file that could never work fails at `helm template` with the
# rule named, rather than reaching the app's fallback and describing a countdown it is not running.
{{- define "gsd.idleTimeout" -}}
{{- /* toYaml, not the bare map: `include` returns TEXT, and a map printed as text is Go's
     `map[k:v]`, which fromYaml cannot read — every caller would silently see an empty map and
     the defaults (found at implementation: the spec's form lost every --set). */ -}}
{{- ((.Values.session | default dict).idleTimeout) | default dict | toYaml -}}
{{- end -}}

{{- define "gsd.idleTimeoutEnabled" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- if eq (toString ($t.enabled | default false)) "true" -}}true{{- else -}}false{{- end -}}
{{- end -}}

{{- define "gsd.idleTimeoutMinutes" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- $m := toString ($t.minutes | default 30) -}}
{{- if not (regexMatch "^[1-9][0-9]*$" $m) -}}
{{- fail (printf "session.idleTimeout.minutes %q is not a whole number of minutes >= 1." $m) -}}
{{- end -}}
{{- $m -}}
{{- end -}}

{{- define "gsd.idleTimeoutWarningSeconds" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- $w := toString ($t.warningSeconds | default 60) -}}
{{- if not (regexMatch "^[0-9]+$" $w) -}}
{{- fail (printf "session.idleTimeout.warningSeconds %q is not a whole number of seconds." $w) -}}
{{- end -}}
{{- $m := include "gsd.idleTimeoutMinutes" . | int -}}
{{- if or (lt (int $w) 5) (ge (int $w) (mul $m 60)) -}}
{{- fail (printf "session.idleTimeout.warningSeconds %s must be at least 5 and shorter than the idle window (%d minutes = %d seconds): a countdown longer than the window it warns about is a contradiction the page cannot render." $w $m (mul $m 60)) -}}
{{- end -}}
{{- $w -}}
{{- end -}}

# ── Login capture source ──────────────────────────────────────────────────────────────────
# pod-log | audit-log, validated where it is resolved, and the ONE place the two switches that
# interact are reconciled: audit-log makes Debug unnecessary, so a render that asks for both is a
# contradiction and is refused — never resolved by quietly rolling the OAuth server.
{{- define "gsd.loginCaptureSource" -}}
{{- $lc := .Values.loginCapture | default dict -}}
{{- $s := "pod-log" -}}
{{- if and (hasKey $lc "source") (not (kindIs "invalid" $lc.source)) -}}{{- $s = trim (toString $lc.source) -}}{{- end -}}
{{- if not (has $s (list "pod-log" "audit-log")) -}}
{{- fail (printf "loginCapture.source %q is not one of pod-log, audit-log." $s) -}}
{{- end -}}
{{- if and (eq $s "audit-log") ($lc.enabled) ((.Values.authLogLevel | default dict).enabled) -}}
{{- fail "loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other: the audit log names every login at the DEFAULT verbosity, so Debug on the authentication operator CR buys nothing and costs an OAuth roll. The chart will not roll the OAuth server as a side effect of a read setting. Retire Debug in order:\n  1. --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=false   (converges the cluster to Normal; one last roll — a login outage at one replica)\n  2. --set authLogLevel.manage=false once the rollout has finished.\nPass your whole values file each time (see the chart README)." -}}
{{- end -}}
{{- $s -}}
{{- end -}}

{{/*
Reporting (docs/specs/SPEC_C3_reporting_microservice.md). Nil-safe like every helper here.
*/}}
{{- define "gsd.reportingEnabled" -}}
{{- if eq (toString ((.Values.reporting | default dict).enabled)) "true" -}}true{{- else -}}false{{- end -}}
{{- end -}}

{{- define "gsd.reportName" -}}
{{- printf "%s-report" (include "gsd.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels for the report pod: NOT gsd.selectorLabels — the dashboard Service selects on those. */}}
{{- define "gsd.reportSelectorLabels" -}}
app.kubernetes.io/name: {{ include "gsd.name" . }}-report
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: report
{{- end -}}

{{/* Full report-object labels: the report's selector keys exactly once, never gsd.selectorLabels (which
     carries the dashboard's app.kubernetes.io/name and its `app` key — a second review pass found the
     earlier form produced duplicate YAML keys with different values). */}}
{{- define "gsd.reportLabels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "gsd.reportSelectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* CronJob object labels; the schedule pods use the same identity explicitly in report-cronjob.yaml. */}}
{{- define "gsd.reportScheduleLabels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "gsd.name" . }}-report-schedule
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: report-schedule
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* The image, resolved exactly like gsd.image: digest, then tag, then Chart.AppVersion. */}}
{{- define "gsd.reportImage" -}}
{{- $img := (.Values.reporting | default dict).image | default dict -}}
{{- $digest := default "" $img.digest -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}
{{- fail (printf "reporting.image.digest %q is not a digest (sha256: + 64 lowercase hex). Leave it empty to deploy reporting.image.tag, or the chart's appVersion when that is empty too." $digest) -}}
{{- end -}}
{{- printf "%s@%s" $img.repository $digest -}}
{{- else -}}
{{- printf "%s:%s" $img.repository (default .Chart.AppVersion $img.tag) -}}
{{- end -}}
{{- end -}}

{{/* The in-cluster URL the proxy and the poller use. */}}
{{- define "gsd.reportUrl" -}}
{{- $tls := eq (toString (((.Values.reporting | default dict).tls | default dict).enabled)) "true" -}}
{{- printf "%s://%s.%s.svc:8443" (ternary "https" "http" $tls) (include "gsd.reportName" .) .Release.Namespace -}}
{{- end -}}

{{- define "gsd.reportPdfVariant" -}}
{{- $v := toString (((.Values.reporting | default dict).pdf | default dict).variant) -}}
{{- if eq $v "<nil>" -}}{{- $v = "" -}}{{- end -}}
{{- if not (has $v (list "" "pdf/a-1b" "pdf/a-2b" "pdf/a-2u" "pdf/a-3b" "pdf/a-3u" "pdf/a-4")) -}}
{{- fail (printf "reporting.pdf.variant %q is not a PDF variant. Use \"\" (plain), pdf/a-1b, pdf/a-2b, pdf/a-2u, pdf/a-3b, pdf/a-3u or pdf/a-4 — the profiles fpdf2 enforces." $v) -}}
{{- end -}}
{{- $v -}}
{{- end -}}

{{/*
The catalogue names this deployment enables, comma-joined for GSD_REPORT_ENABLED_REPORTS. Each
switch is a boolean; loginActivity is a tri-state ("" follows loginCapture.enabled). Misspelt values
refuse, and loginActivity=true with capture off refuses — a report over a table nothing writes.
*/}}
{{- /* The Namespace label keys the poller captures: reporting.namespaceMetadata.labels plus the
exact-group label (reporting.namespaceGroupLabel, #149 R7) when set and not already listed — the
report forms resolve a business mnemonic to the group a namespace pins through it, so the poller
must capture it whether or not the operator listed it. */ -}}
{{- define "gsd.namespaceMetadataLabels" -}}
{{- $labels := (((.Values.reporting | default dict).namespaceMetadata) | default dict).labels | default list -}}
{{- $group := (.Values.reporting | default dict).namespaceGroupLabel | default "" -}}
{{- if and $group (not (has $group $labels)) -}}{{- $labels = append $labels $group -}}{{- end -}}
{{- toJson $labels -}}
{{- end -}}

{{- /* The reporting.schedules[] entries the report pod's status page describes: name, schedule, report,
enabled and any per-schedule retention override, as one JSON array (#149 R6). Params, cluster and
formats are the CronJob's business and stay out of it. `enabled` is emitted as the boolean the CronJob
decides on — the literal word false suspends it (report-cronjob.yaml) — so a quoted "false" or a
--set-string cannot leave the page saying On above a CronJob that is paused (review of #221, OB3). */ -}}
{{- define "gsd.reportSchedulesJson" -}}
{{- $out := list -}}
{{- range $s := ((.Values.reporting | default dict).schedules | default list) -}}
{{- $entry := dict "name" $s.name "schedule" $s.schedule "report" $s.report -}}
{{- if hasKey $s "enabled" -}}{{- $_ := set $entry "enabled" (ne (toString $s.enabled) "false") -}}{{- end -}}
{{- with $s.retention -}}{{- $_ := set $entry "retention" . -}}{{- end -}}
{{- $out = append $out $entry -}}
{{- end -}}
{{- toJson $out -}}
{{- end -}}

{{- define "gsd.reportEnabledReports" -}}
{{- $r := (.Values.reporting | default dict).reports | default dict -}}
{{- $names := dict "namespaceAccess" "namespace-access" "accessMatrix" "access-matrix" "privilegedAccess" "privileged-access" "bindingFindings" "binding-findings" "groups" "groups" "users" "users" "dormantAccess" "dormant-access" "groupsyncHealth" "groupsync-health" "complianceSnapshot" "compliance-snapshot" "accessCertification" "access-certification" -}}
{{- $out := list -}}
{{- range $key, $name := $names -}}
{{- $raw := toString ((get $r $key | default dict).enabled) -}}
{{- if or (eq $raw "true") (eq $raw "<nil>") -}}{{- $out = append $out $name -}}
{{- else if ne $raw "false" -}}
{{- fail (printf "reporting.reports.%s.enabled must be true or false; got %q" $key $raw) -}}
{{- end -}}
{{- end -}}
{{- $la := toString ((get $r "loginActivity" | default dict).enabled) -}}
{{- if or (eq $la "") (eq $la "<nil>") -}}
{{- if $.Values.loginCapture.enabled -}}{{- $out = append $out "login-activity" -}}{{- end -}}
{{- else if eq $la "true" -}}
{{- if not $.Values.loginCapture.enabled -}}
{{- fail "reporting.reports.loginActivity.enabled=true requires loginCapture.enabled=true: the report reads login_event, which nothing writes without capture. Leave it \"\" to follow the capture switch." -}}
{{- end -}}
{{- $out = append $out "login-activity" -}}
{{- else if ne $la "false" -}}
{{- fail (printf "reporting.reports.loginActivity.enabled must be true, false or \"\" (follow loginCapture.enabled); got %q" $la) -}}
{{- end -}}
{{- join "," (sortAlpha $out) -}}
{{- end -}}

{{/*
The render guards for reporting, included by report-deployment.yaml AND deployment.yaml (the proxy
args depend on them), so both objects refuse together. Emits nothing.
*/}}
{{/*
reporting.window.enabled as the literal word true or false — the SAME spellings the report service's
_bool_env accepts (true/1/yes on, false/0/no off, case-insensitive); anything else fails the render.
NOT bare Go-template truthiness: a quoted "false" (or --set-string) is a non-empty, truthy string,
which would put spec.timeZone on the CronJob and run the window guard for a window the app treats as
DISABLED (review of P4, C6/F3). One helper so the guard, the CronJob and the Deployment env agree.
*/}}
{{- define "gsd.reportWindowEnabled" -}}
{{- $w := (.Values.reporting | default dict).window | default dict -}}
{{- $raw := "false" -}}
{{- if and (hasKey $w "enabled") (not (kindIs "invalid" $w.enabled)) -}}{{- $raw = lower (trim (toString $w.enabled)) -}}{{- end -}}
{{- if has $raw (list "true" "1" "yes") -}}
true
{{- else if has $raw (list "false" "0" "no") -}}
false
{{- else -}}
{{- fail (printf "reporting.window.enabled %q is not a boolean (true/false)." $raw) -}}
{{- end -}}
{{- end -}}

{{- define "gsd.reportingGuards" -}}
{{- if eq (include "gsd.reportingEnabled" .) "true" -}}
{{- if not .Values.oauthProxy.enabled -}}
{{- fail "reporting.enabled=true requires oauthProxy.enabled=true. The report service is reached only through the proxy's path-routed /report/ upstream, and its tickets are bound to the identity the proxy stamps; without the proxy there is no way in and no identity to bind to. Set reporting.enabled=false to run without the proxy." -}}
{{- end -}}
{{- if not .Values.persistence.enabled -}}
{{- fail "reporting.enabled=true requires persistence.enabled=true. The report pod reads a VACUUM INTO copy the dashboard writes under /data/report on the data claim; an emptyDir cannot be mounted by a second pod. Set reporting.enabled=false for an ephemeral install." -}}
{{- end -}}
{{- if gt (int .Values.replicaCount) 1 -}}
{{- fail "reporting.enabled=true requires replicaCount 1. Above one replica each pod holds its own database and history (templates/deployment.yaml, PER-POD database file), so a report would be built from an arbitrary replica's copy. docs/reference-architecture.md explains why scaling is not the answer; set reporting.enabled=false if you must scale." -}}
{{- end -}}
{{- if not .Values.rbac.bindings -}}
{{- fail "reporting.enabled=true requires rbac.bindings=true: nine of the eleven reports are the RBAC binding surface, which the dashboard does not read without that grant." -}}
{{- end -}}
{{- $mode := include "gsd.accessMode" . -}}
{{- if ne $mode "ReadWriteMany" -}}
{{- fail (printf "reporting.enabled=true requires persistence.accessMode=ReadWriteMany; got %s. ReadWriteOncePod admits one pod only. ReadWriteOnce is refused too: the two pods restart independently, inter-pod affinity is ignored once a pod is scheduled, so replacing only the dashboard can leave the report pod holding the single-node claim on the old node while the new dashboard pod lands on another and cannot attach it. Use ReadWriteMany (the default) or set reporting.enabled=false. accessModes are immutable on an existing claim — docs/RUNBOOK_backup_restore.md §5 covers moving the data." $mode) -}}
{{- end -}}
{{- $snap := (.Values.reporting | default dict).snapshot | default dict -}}
{{- if lt (int ($snap.intervalSeconds | default 300)) 60 -}}
{{- fail (printf "reporting.snapshot.intervalSeconds must be at least 60; got %v. A VACUUM INTO holds a read transaction for its duration." $snap.intervalSeconds) -}}
{{- end -}}
{{- $t := (.Values.reporting | default dict).ticket | default dict -}}
{{- if or (lt (int ($t.ttlSeconds | default 300)) 30) (gt (int ($t.ttlSeconds | default 300)) 3600) -}}
{{- fail (printf "reporting.ticket.ttlSeconds must be between 30 and 3600; got %v" $t.ttlSeconds) -}}
{{- end -}}
{{- /* Namespace-selection guards (docs/DESIGN_reporting_auditors_and_ns_selector.md §3, round 1 N1):
   capture rides the optional rbac.namespaces grant, and the selector must name a captured key, or it
   would be silently empty. `| default` on every hop so a commented-out stanza never panics. */ -}}
{{- $nsMeta := (.Values.reporting | default dict).namespaceMetadata | default dict -}}
{{- $nsLabels := $nsMeta.labels | default list -}}
{{- if and (gt (len $nsLabels) 0) (not .Values.rbac.namespaces) -}}
{{- fail "reporting.namespaceMetadata.labels is set but rbac.namespaces is false: the poll never lists Namespace objects, so the mnemonic selector would always be empty. Set rbac.namespaces=true (the extra RBAC is the 0.14.0 exception the namespace report already needs) or clear the labels list." -}}
{{- end -}}
{{- /* #149 R7: the exact-group label is captured the same way, and needs the same grant. */ -}}
{{- if and ((.Values.reporting | default dict).namespaceGroupLabel | default "") (not .Values.rbac.namespaces) -}}
{{- fail "reporting.namespaceGroupLabel is set but rbac.namespaces is false: the poll never lists Namespace objects, so the label could not be captured. Set rbac.namespaces=true or clear it." -}}
{{- end -}}
{{- $nsSelector := (.Values.reporting | default dict).namespaceSelector | default dict -}}
{{- /* .label was removed in 0.22.0 (the selector is multi-dimension now: .labels). Helm ignores unknown
   keys, so a stale non-empty .label renders clean while its selector silently vanishes — refuse a
   materially-set value. An empty/null .label is 0.21's default, a no-op, and stays allowed. */ -}}
{{- if and (hasKey $nsSelector "label") (not (empty (get $nsSelector "label"))) -}}
{{- fail "reporting.namespaceSelector.label was removed (P2 made the selector multi-dimension; see the 0.22.0 upgrade note in docs/CHANGELOG.md). Move the value into reporting.namespaceSelector.labels: [<your label key>]." -}}
{{- end -}}
{{- range $l := ($nsSelector.labels | default list) -}}
{{- if not (has $l $nsLabels) -}}
{{- fail (printf "reporting.namespaceSelector.labels entry %q is not in reporting.namespaceMetadata.labels %v. The poll would never capture it, so that dimension would always be empty." $l $nsLabels) -}}
{{- end -}}
{{- end -}}
{{- /* Reporting window (design §5): validate at render what the report service validates at startup, so
   an enabled-but-malformed window fails the render, not just the pod. */ -}}
{{- $window := (.Values.reporting | default dict).window | default dict -}}
{{- if eq (include "gsd.reportWindowEnabled" .) "true" -}}
{{- if not (trim ($window.timezone | default .Values.timezone)) -}}
{{- fail "reporting.window.enabled=true needs a timezone: set reporting.window.timezone or .Values.timezone to an IANA zone (e.g. America/New_York)." -}}
{{- end -}}
{{- range $k := (list "start" "end") -}}
{{- if not (regexMatch "^([01][0-9]|2[0-3]):[0-5][0-9]$" (toString (get $window $k))) -}}
{{- fail (printf "reporting.window.%s %q is not HH:MM (24h)." $k (toString (get $window $k))) -}}
{{- end -}}
{{- end -}}
{{- if eq (toString $window.start) (toString $window.end) -}}
{{- fail (printf "reporting.window.start and end are equal (%q); pick a real range, neither empty nor a full day." (toString $window.start)) -}}
{{- end -}}
{{- $days := $window.days | default list -}}
{{- if eq (len $days) 0 -}}
{{- fail "reporting.window.days is empty; give a non-empty subset of Mon..Sun." -}}
{{- end -}}
{{- $valid := dict "Mon" true "Tue" true "Wed" true "Thu" true "Fri" true "Sat" true "Sun" true -}}
{{- $seen := dict -}}
{{- range $d := $days -}}
{{- if not (hasKey $valid (toString $d)) -}}
{{- fail (printf "reporting.window.days entry %q is not one of Mon..Sun." (toString $d)) -}}
{{- end -}}
{{- if hasKey $seen (toString $d) -}}
{{- fail (printf "reporting.window.days has a duplicate: %q." (toString $d)) -}}
{{- end -}}
{{- $_ := set $seen (toString $d) true -}}
{{- end -}}
{{- end -}}
{{- /* Value-returning helpers validate as a side effect; assign their output so nothing prints. */ -}}
{{- $_ := include "gsd.reportPdfVariant" . -}}
{{- $enabled := splitList "," (include "gsd.reportEnabledReports" .) -}}
{{- range $s := ((.Values.reporting | default dict).schedules | default list) -}}
{{- if not (has $s.report $enabled) -}}
{{- fail (printf "reporting.schedules[%s].report %q is not an enabled catalogue name (enabled: %s)" $s.name $s.report (join ", " $enabled)) -}}
{{- end -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9]{0,40}[a-z0-9])?$" (toString $s.name)) -}}
{{- fail (printf "reporting.schedules[].name %q must be a short DNS label (it names a CronJob)" (toString $s.name)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

# ── Per-cluster authorization ────────────────────────────────────────────────────────────
# The same closed vocabulary the app enforces (gsd/config.py CLUSTER_VISIBILITIES), refused at
# render so a typo'd policy fails `helm template` rather than the pod's startup. Nil-safe on
# every hop for the usual reason. Called from configmap.yaml, which always renders.
{{- define "gsd.validateClusters" -}}
{{- $host := "" -}}
{{- range $i, $c := (.Values.clusters | default list) -}}
{{- if or (kindIs "invalid" $c) (not (kindIs "map" $c)) -}}
{{- fail (printf "clusters[%d] is not a cluster entry (it is %s). Helm pads a list index set beyond the list's length with null and never merges lists, so `--set clusters[1].name=…` on a values file that does not define clusters[0] yields [null, {…}]: pass every entry, clusters[0] included, or put the whole list in a values file." $i (kindOf $c)) -}}
{{- end -}}
{{- $name := toString ($c.name | default (printf "clusters[%d]" $i)) -}}
{{- $vis := "" -}}{{- if and (hasKey $c "visibility") (not (kindIs "invalid" $c.visibility)) -}}{{- $vis = trim (toString $c.visibility) -}}{{- end -}}
{{- $id := "" -}}{{- if and (hasKey $c "identity") (not (kindIs "invalid" $c.identity)) -}}{{- $id = trim (toString $c.identity) -}}{{- end -}}
{{- if and $vis (not (has $vis (list "inherit" "self-only" "hidden" "remote-sar"))) -}}
{{- fail (printf "clusters[%d] (%s): visibility %q is not one of inherit, self-only, hidden, remote-sar. See the clusters comment in values.yaml." $i $name $vis) -}}
{{- end -}}
{{- if and $id (not (has $id (list "same-as-host" "none"))) -}}
{{- fail (printf "clusters[%d] (%s): identity %q is not one of same-as-host, none." $i $name $id) -}}
{{- end -}}
{{- /* A word, not truthiness: a quoted "false" is a non-empty string and truthy in Go, and the
       first ENABLED entry is the host (review of D2, second pass, Codex). */ -}}
{{- $enabled := true -}}
{{- if hasKey $c "enabled" -}}
{{- $enabledWord := trim (toString $c.enabled) -}}
{{- if not (has $enabledWord (list "true" "false")) -}}
{{- fail (printf "clusters[%d] (%s): enabled must be true or false." $i $name) -}}
{{- end -}}
{{- $enabled = eq $enabledWord "true" -}}
{{- end -}}
{{- if and $enabled (eq $host "") -}}
{{- $host = $name -}}
{{- if has $vis (list "hidden" "remote-sar") -}}
{{- fail (printf "clusters[%d] (%s) is the hosting cluster — the first enabled entry, the one the oauth-proxy authenticates against — and visibility %q makes no sense there: hidden would hide the login cluster, remote-sar would review the host against itself. Use inherit (the default) or self-only." $i $name $vis) -}}
{{- end -}}
{{- else if and (eq $vis "remote-sar") (ne $id "same-as-host") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host. The review names the host's username on that cluster, which only means something if both clusters share an identity provider — say so explicitly." $i $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- /*
The KPI page's doors (grafana.url, console.url): empty is unset — the Grafana door absent, the console
discovered. A value must be an http(s) URL with a host and no query or fragment, the rule the app's
_door_url enforces at start; refused HERE so a `javascript:` value cannot reach a release and crash
the pod after a successful upgrade (review of #157 and #209, Codex and Grok).
*/ -}}
{{- define "gsd.doorUrl" -}}
{{- $key := index . 0 }}{{- $value := index . 1 }}
{{- if $value }}
{{- if not (regexMatch "^https?://[^/?#[:space:]]+(/[^?#[:space:]]*)?$" $value) }}
{{- fail (printf "%s must be an http(s) URL with a host and no query or fragment; got %q" $key $value) }}
{{- end }}
{{- end }}
{{- end -}}
