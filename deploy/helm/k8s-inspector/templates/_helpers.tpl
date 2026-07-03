{{- define "k8s-inspector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "k8s-inspector.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "k8s-inspector.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "k8s-inspector.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "k8s-inspector.labels" -}}
helm.sh/chart: {{ include "k8s-inspector.chart" . }}
app.kubernetes.io/name: {{ include "k8s-inspector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "k8s-inspector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k8s-inspector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "k8s-inspector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "k8s-inspector.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "k8s-inspector.basePath" -}}
{{- if or (eq .Values.basePath "") (eq .Values.basePath "/") -}}
{{- "" -}}
{{- else -}}
{{- if hasPrefix "/" .Values.basePath -}}
{{- trimSuffix "/" .Values.basePath -}}
{{- else -}}
{{- printf "/%s" (trimSuffix "/" .Values.basePath) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "k8s-inspector.systemStatusPath" -}}
{{- printf "%s/api/v1/system/status" (include "k8s-inspector.basePath" .) -}}
{{- end -}}
