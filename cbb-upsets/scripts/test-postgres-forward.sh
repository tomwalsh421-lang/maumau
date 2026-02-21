#!/usr/bin/env bash
set -euo pipefail

kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default >/tmp/pgforward.log 2>&1 &
PF=$!
trap "kill $PF" EXIT

sleep 2
PGPASSWORD=cbbpass psql -h 127.0.0.1 -p 5432 -U cbb -d cbb_upsets -c '\l'

echo "Postgres connection succeeded"
