#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
STATUS_CMD=("${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/run_autonomous_loops.py" "--status")
LOG_PATH="${REPO_ROOT}/.codex/local/auto-loop/supervisor.log"
LOG_LINES=20
SHOW_LOG=1

usage() {
  cat <<'EOF'
Usage: scripts/monitor_autonomous_loops.sh [--no-log] [--log-lines N]

Print a compact terminal summary of the autonomous loop supervisor heartbeat and
the latest result for each lane.

Examples:
  scripts/monitor_autonomous_loops.sh
  scripts/monitor_autonomous_loops.sh --no-log
  watch -n 30 ./scripts/monitor_autonomous_loops.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-log)
      SHOW_LOG=0
      shift
      ;;
    --log-lines)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --log-lines" >&2
        exit 2
      fi
      LOG_LINES="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "${LOG_LINES}" =~ ^[0-9]+$ ]]; then
  echo "--log-lines must be a non-negative integer" >&2
  exit 2
fi

if [[ ! -x "${STATUS_CMD[0]}" ]]; then
  echo "Missing Python virtualenv at ${STATUS_CMD[0]}" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Missing required dependency: jq" >&2
  exit 1
fi

STATUS_JSON="$("${STATUS_CMD[@]}")"

printf '%s\n' "${STATUS_JSON}" | jq -r '
  def squash:
    tostring
    | gsub("[\r\n\t]+"; " ")
    | gsub("  +"; " ")
    | sub("^ "; "")
    | sub(" $"; "");
  def short($n):
    (squash) as $s
    | if ($s | length) > $n then ($s[0:($n - 1)] + "…") else $s end;
  def current_lane:
    (.heartbeat // {} | .lane // "");
  def lane_heartbeat($lane):
    .lanes[$lane].heartbeat // {};
  def lane_state($lane):
    .lanes[$lane].state // {};
  def lane_branch($lane):
    lane_state($lane).branch // lane_heartbeat($lane).branch // "-";
  def lane_live_status($lane):
    if current_lane == $lane then
      lane_heartbeat($lane).status
      // (.heartbeat // {}).status
      // lane_state($lane).status
      // "unknown"
    else
      lane_heartbeat($lane).status
      // lane_state($lane).status
      // "unknown"
    end;
  def lane_live_phase($lane):
    if current_lane == $lane then
      lane_heartbeat($lane).phase
      // (.heartbeat // {}).phase
      // "-"
    else
      lane_heartbeat($lane).phase
      // "-"
    end;
  def lane_result($lane):
    if current_lane == $lane and lane_live_status($lane) == "running" then
      "RUNNING"
    elif lane_state($lane).status == "accepted" then
      "PASS"
    elif (lane_state($lane).status == "failed") or (lane_state($lane).status == "rejected") then
      "FAIL"
    elif lane_heartbeat($lane).status == "accepted" then
      "PASS"
    elif (lane_heartbeat($lane).status == "failed") or (lane_heartbeat($lane).status == "rejected") then
      "FAIL"
    else
      (lane_live_status($lane) | ascii_upcase)
    end;
  def lane_timestamp($lane):
    lane_state($lane).completed_at
    // lane_state($lane).failed_at
    // lane_heartbeat($lane).updated_at
    // "-";
  def lane_detail($lane):
    (
      lane_state($lane).task_title
      // lane_state($lane).summary
      // lane_state($lane).error
      // lane_heartbeat($lane).error
      // (if current_lane == $lane then ((.heartbeat // {}).reason // (.heartbeat // {}).priority_note) else empty end)
      // "n/a"
    ) | short(180);
  def lane_meta($lane):
    [
      (lane_state($lane).task_id | select(. != null) | "task_id=\(.)"),
      (lane_state($lane).changed_paths | select(type == "array") | "changed_paths=\(length)"),
      (lane_state($lane).last_commit | select(. != null) | "last_commit=\(.)"),
      (lane_state($lane).backoff_until | select(. != null) | "backoff_until=\(.)"),
      (lane_state($lane).consecutive_failures | select(. != null) | "consecutive_failures=\(.)")
    ] | map(select(length > 0)) | join(" | ");

  "Autonomous Loop Monitor",
  "generated_at: \(((.heartbeat // {}).updated_at // "n/a"))",
  "supervisor_running: \(.supervisor_running)",
  "supervisor_pid: \((.supervisor_pid // "n/a"))",
  "current_lane: \((current_lane | if . == "" then "none" else . end))",
  "current_phase: \(((.heartbeat // {}).phase // "n/a"))",
  "current_status: \(((.heartbeat // {}).status // "n/a"))",
  "current_branch: \((if current_lane == "" then "n/a" else lane_branch(current_lane) end))",
  "reason: \((((.heartbeat // {}).reason // "n/a") | short(220)))",
  "priority_note: \((((.heartbeat // {}).priority_note // "n/a") | short(220)))",
  "",
  "Lane Summary",
  (
    ["infra", "model", "ux"][] as $lane
    | "- \($lane) | result=\(lane_result($lane)) | live=\(lane_live_status($lane))/\(lane_live_phase($lane)) | branch=\(lane_branch($lane)) | at=\(lane_timestamp($lane))",
      "  detail: \(lane_detail($lane))",
      (lane_meta($lane) | select(length > 0) | "  meta: \(.)")
  )
'

if [[ "${SHOW_LOG}" -eq 1 ]]; then
  printf '\nRecent Log\n'
  if [[ -f "${LOG_PATH}" ]]; then
    if [[ -s "${LOG_PATH}" ]]; then
      tail -n "${LOG_LINES}" "${LOG_PATH}"
    else
      echo "(log file exists but is empty)"
    fi
  else
    echo "(no supervisor log found at ${LOG_PATH})"
  fi
fi
