{{- define "cbb-upsets.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "cbb-upsets.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.labels" -}}
helm.sh/chart: {{ include "cbb-upsets.chart" . }}
{{ include "cbb-upsets.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "cbb-upsets.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cbb-upsets.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "cbb-upsets.nginxSelectorLabels" -}}
{{ include "cbb-upsets.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end }}

{{- define "cbb-upsets.nginxLabels" -}}
{{ include "cbb-upsets.labels" . }}
app.kubernetes.io/component: web
{{- end }}

{{- define "cbb-upsets.runtimeSelectorLabels" -}}
{{ include "cbb-upsets.selectorLabels" . }}
app.kubernetes.io/component: runtime
{{- end }}

{{- define "cbb-upsets.runtimeLabels" -}}
{{ include "cbb-upsets.labels" . }}
app.kubernetes.io/component: runtime
{{- end }}

{{- define "cbb-upsets.middlewareSelectorLabels" -}}
{{ include "cbb-upsets.selectorLabels" . }}
app.kubernetes.io/component: middleware
{{- end }}

{{- define "cbb-upsets.middlewareLabels" -}}
{{ include "cbb-upsets.labels" . }}
app.kubernetes.io/component: middleware
{{- end }}

{{- define "cbb-upsets.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "cbb-upsets.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "cbb-upsets.nginxFullname" -}}
{{- printf "%s-nginx" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.runtimeFullname" -}}
{{- printf "%s-runtime" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.runtimeCronFullname" -}}
{{- printf "%s-runtime-cron" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.runtimeSecretFullname" -}}
{{- printf "%s-runtime-env" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.middlewareFullname" -}}
{{- printf "%s-middleware" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.nginxConfigFullname" -}}
{{- printf "%s-nginx-config" (include "cbb-upsets.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "cbb-upsets.runtimeValidation" -}}
{{- if and .Values.runtime.enabled .Values.runtime.schedule.enabled -}}
{{- fail "runtime.enabled and runtime.schedule.enabled cannot both be true" -}}
{{- end -}}
{{- end }}

{{- define "cbb-upsets.runtimeImage" -}}
{{- printf "%s:%s" .Values.runtime.image.repository (required "runtime.image.tag must be set when a runtime workload is enabled" .Values.runtime.image.tag) -}}
{{- end }}

{{- define "cbb-upsets.middlewareImage" -}}
{{- $repository := coalesce .Values.middleware.image.repository .Values.runtime.image.repository -}}
{{- $tag := coalesce .Values.middleware.image.tag .Values.runtime.image.tag -}}
{{- printf "%s:%s" $repository (required "middleware.image.tag must be set when middleware.enabled is true" $tag) -}}
{{- end }}

{{- define "cbb-upsets.runtimeDatabaseUrl" -}}
{{- if .Values.runtime.databaseUrl }}
{{- .Values.runtime.databaseUrl -}}
{{- else if .Values.postgresql.enabled }}
{{- printf "postgresql+psycopg2://%s:%s@%s-postgresql:5432/%s" .Values.postgresql.auth.username .Values.postgresql.auth.password .Release.Name .Values.postgresql.auth.database -}}
{{- else -}}
{{- fail "runtime.databaseUrl must be set when a runtime workload is enabled and postgresql.enabled is false" -}}
{{- end -}}
{{- end }}

{{- define "cbb-upsets.middlewareDatabaseUrl" -}}
{{- if .Values.middleware.databaseUrl }}
{{- .Values.middleware.databaseUrl -}}
{{- else if .Values.postgresql.enabled }}
{{- printf "postgresql+psycopg2://%s:%s@%s-postgresql:5432/%s" .Values.postgresql.auth.username .Values.postgresql.auth.password .Release.Name .Values.postgresql.auth.database -}}
{{- else -}}
{{- fail "middleware.databaseUrl must be set when middleware.enabled is true and postgresql.enabled is false" -}}
{{- end -}}
{{- end }}
