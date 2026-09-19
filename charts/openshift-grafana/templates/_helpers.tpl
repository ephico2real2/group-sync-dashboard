{{- /*
Names and labels. The release's instance label is what every CR here selects the Grafana by,
so a consumer's GrafanaDashboard needs one line: `app.kubernetes.io/instance: <release>`.
*/ -}}
{{- define "openshift-grafana.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "openshift-grafana.fullname" -}}
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

{{- define "openshift-grafana.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "openshift-grafana.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- /* The labels a datasource or dashboard selects THIS instance by. */ -}}
{{- define "openshift-grafana.instanceSelector" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- with .Values.grafana.labels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "openshift-grafana.validate" -}}
{{- if not (has .Values.thanos.scope (list "namespace" "cluster")) -}}
{{- fail (printf "thanos.scope must be \"namespace\" or \"cluster\"; got %q" .Values.thanos.scope) -}}
{{- end -}}
{{- if and .Values.operatorGroup.create (not .Values.operator.install) -}}
{{- /* Not an error: an OperatorGroup without a Subscription is harmless but pointless; say so in NOTES. */ -}}
{{- end -}}
{{- end -}}
