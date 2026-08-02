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
{{- $cfg := (lookup "config.openshift.io/v1" "Ingress" "" "cluster") -}}
{{- if and $cfg $cfg.spec.domain -}}
{{ printf "%s-%s.%s" (include "gsd.fullname" .) .Release.Namespace $cfg.spec.domain }}
{{- else -}}
{{- fail "ingress.host is not set and the cluster apps domain could not be read. Set it explicitly:\n  --set ingress.host=<name>.$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')\nAn Ingress without a host produces NO Route on OpenShift, so the release would install cleanly and be unreachable." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* The port anything external should reach: the proxy when enabled, else the app. */}}
{{- define "gsd.servicePort" -}}
{{- if .Values.oauthProxy.enabled -}}
{{ .Values.oauthProxy.port }}
{{- else -}}
8080
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
