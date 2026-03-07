#!/usr/bin/env bash
set -euo pipefail

SERVICE="${SERVICE:-svc/cbb-upsets-postgresql}"
NAMESPACE="${NAMESPACE:-default}"
LOCAL_PORT="${LOCAL_PORT:-5432}"
REMOTE_PORT="${REMOTE_PORT:-5432}"
DB_HOST="${PGHOST:-127.0.0.1}"
DB_USER="${PGUSER:-cbb}"
DB_PASSWORD="${PGPASSWORD:-cbbpass}"
DB_NAME="${PGDATABASE:-cbb_upsets}"
LOG_FILE="${LOG_FILE:-/tmp/pgforward.log}"

kubectl port-forward "$SERVICE" "${LOCAL_PORT}:${REMOTE_PORT}" -n "$NAMESPACE" >"$LOG_FILE" 2>&1 &
PF=$!
cleanup() {
  kill "$PF" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 10); do
  if PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$LOCAL_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -c "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

PGPASSWORD="$DB_PASSWORD" psql \
  -h "$DB_HOST" \
  -p "$LOCAL_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 <<'SQL'
SELECT current_database() AS database_name, current_user AS db_user, now() AS connected_at;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
SQL

echo "Postgres smoke test succeeded for ${DB_NAME} via ${SERVICE}"
