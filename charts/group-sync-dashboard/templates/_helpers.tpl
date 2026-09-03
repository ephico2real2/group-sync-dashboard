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
{{- fail "route.enabled and ingress.enabled are both true. They expose the same Service under the same hostname, and the router admits only one claim on a host, so the second object would sit refused with HostAlreadyClaimed after an install that reported success. Choose one: route.enabled=true is the OpenShift default and needs no host at render time; ingress.enabled=true is for plain Kubernetes and needs ingress.host." -}}
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
SAME host, and the second Route is rejected with HostAlreadyClaimed. That is a loud, legible
failure at install time rather than a silent one, and the fix is one flag — set
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
{{- $cookie.expire | default "4h" -}}
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
