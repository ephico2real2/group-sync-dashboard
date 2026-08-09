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

{{- define "gsd.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{/*
Route TLS. The proxy terminates TLS itself using the service-ca certificate, so the router
must RE-ENCRYPT to it. Leaving this as edge sends plaintext to a port that only speaks TLS
and the Route silently fails.

Kept here rather than inline so the rule lives in one place: it is the kind of coupling that
gets forgotten when someone later adds another ingress path.
*/}}
{{- define "gsd.routeTermination" -}}
{{- if .Values.oauthProxy.enabled -}}
reencrypt
{{- else -}}
{{ .Values.ingress.termination }}
{{- end -}}
{{- end -}}

{{/*
The externally reachable URL. Required when the OAuth proxy is on, because the
ServiceAccount must advertise a literal callback URL.

It cannot be derived: OpenShift's ingress-to-route controller names the generated Route
`<ingress-name>-<random>` (observed: probe-ingress-7669p), so the redirectREFERENCE form —
which points at a Route by name — cannot be used with an Ingress. Hence redirectURI, hence
a host that must be stated.
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
{{- fail "ingress.host is not set and the cluster apps domain could not be read.\n\nThe domain is normally auto-detected, so a plain `helm install`/`helm upgrade` needs no flag. It cannot be detected in three cases, and one of them is probably yours:\n\n  1. GitOps. ArgoCD, Flux and anything else built on `helm template` render with NO cluster connection, so the lookup returns nothing. Set ingress.host in your Application values.\n  2. `helm template` or `--dry-run` run by hand. Use `--dry-run=server`, or pass the host.\n  3. The installing identity cannot read ingresses.config/cluster. It is cluster-scoped and NOT readable by an ordinary user, so a namespace-scoped installer must be given the host.\n\nSet it with:\n  --set ingress.host=group-sync-dashboard.$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')\n\nThis fails the render on purpose. An Ingress without a host produces NO Route on OpenShift, so the alternative is a release that installs cleanly, reports healthy, and is unreachable." -}}
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

# How many key bytes the proxy would actually derive from a cookie secret. Mirrors its
# secretBytes(): a value that reads as URL-safe base64 (padding tolerated) is decoded and
# the DECODED length padded up to a multiple of four; anything else counts raw. The mirror
# matters in BOTH directions — a naive `len` would reject secrets the proxy accepts (32 hex
# characters decode to 24 bytes) and accept ones it refuses.
{{- define "gsd.cookieSecretBytes" -}}
{{- $s := . -}}
{{- $n := len $s -}}
{{- if not (or (contains "+" $s) (contains "/" $s)) -}}
{{- $t := $s | replace "-" "+" | replace "_" "/" -}}
{{- $t = print $t (repeat (int (mod (sub 4 (mod (len $t) 4)) 4)) "=") -}}
{{- $d := b64dec $t -}}
{{- if not (contains "illegal base64" $d) -}}
{{- $n = add (len $d) (mod (sub 4 (mod (len $d) 4)) 4) -}}
{{- end -}}
{{- end -}}
{{- $n -}}
{{- end -}}
# ── Per-user visibility ──────────────────────────────────────────────────────────────
# Every read below is nil-safe on purpose: commenting out the sub-keys in a values file
# leaves `visibility:` (or `adminSar:`) present-but-nil, which a bare field access — and
# sprig's dig — panics on. Intermediates are defaulted to a dict and a nil leaf is
# treated as "not set", which falls back to the shipped default, never to "off".

# Returns the word true or false. Only the exact word false — bool or string — disables:
# the switch guards personal data, so anything unrecognised must fail toward restricted.
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
user.openshift.io
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
groups
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
