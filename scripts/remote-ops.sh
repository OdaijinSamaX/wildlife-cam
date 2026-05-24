#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PARENT_ALIAS="wildlife-parent"
CHILD_ALIAS="wildlife-child"
PARENT_SERVICE="wildlife-cam-parent"
CHILD_SERVICE="wildlife-cam-child"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5)

usage() {
  cat <<'USAGE'
Usage:
  scripts/remote-ops.sh status [parent|child|both]
  scripts/remote-ops.sh logs <parent|child> [-f]
  scripts/remote-ops.sh restart <parent|child|both>
  scripts/remote-ops.sh deploy <parent|child|both>
  scripts/remote-ops.sh ping
  scripts/remote-ops.sh shell <parent|child>

Targets:
  parent  Raspberry Pi 5 via SSH alias wildlife-parent, service wildlife-cam-parent
  child   Raspberry Pi Zero 2 W via SSH alias wildlife-child, service wildlife-cam-child
  both    parent then child

Notes:
  SSH aliases must exist in ~/.ssh/config. Authentication is expected to use the
  forwarded 1Password SSH agent from the mothership machine.
USAGE
}

host_for() {
  case "${1:-}" in
    parent) echo "$PARENT_ALIAS" ;;
    child) echo "$CHILD_ALIAS" ;;
    *) echo "unknown target: ${1:-}" >&2; exit 2 ;;
  esac
}

service_for() {
  case "${1:-}" in
    parent) echo "$PARENT_SERVICE" ;;
    child) echo "$CHILD_SERVICE" ;;
    *) echo "unknown target: ${1:-}" >&2; exit 2 ;;
  esac
}

sudoers_hint() {
  echo "Pi 側で sudoers に \`odaijinsamax ALL=(ALL) NOPASSWD: /bin/systemctl, /usr/bin/systemctl\` を追加してください" >&2
}

journal_hint() {
  echo "Pi 側で \`sudo usermod -aG systemd-journal odaijinsamax\` を実行するか、sudo NOPASSWD で journalctl を許可してください" >&2
}

ssh_unreachable() {
  local target="$1"
  local detail="${2:-}"
  if [ -n "$detail" ]; then
    echo "${target} [ssh-unreachable] host=$(host_for "$target") detail=${detail}" >&2
  else
    echo "${target} [ssh-unreachable] host=$(host_for "$target")" >&2
  fi
}

ssh_run() {
  local target="$1"
  shift
  ssh "${SSH_OPTS[@]}" "$(host_for "$target")" "$@"
}

ensure_ssh() {
  local target="$1"
  local output
  if ! output="$(ssh_run "$target" "true" 2>&1)"; then
    ssh_unreachable "$target" "$(printf '%s' "$output" | head -n 1)"
    return 1
  fi
}

expand_targets() {
  case "${1:-both}" in
    parent) echo "parent" ;;
    child) echo "child" ;;
    both) printf '%s\n' parent child ;;
    *) echo "unknown target: ${1:-}" >&2; exit 2 ;;
  esac
}

run_status() {
  local target
  local service
  local output
  local load_state
  local active_state
  for target in $(expand_targets "${1:-both}"); do
    service="$(service_for "$target")"
    if ! ensure_ssh "$target"; then
      continue
    fi
    if ! output="$(ssh_run "$target" "systemctl show --property=LoadState --property=ActiveState --value ${service}" 2>&1)"; then
      echo "${target} [unit-missing] host=$(host_for "$target") service=${service} detail=$(printf '%s' "$output" | head -n 1)"
      continue
    fi

    load_state="$(printf '%s\n' "$output" | sed -n '1p')"
    active_state="$(printf '%s\n' "$output" | sed -n '2p')"

    if [ "$load_state" = "not-found" ]; then
      echo "${target} [unit-missing] host=$(host_for "$target") service=${service}"
    elif [ "$active_state" = "active" ]; then
      echo "${target} [active] host=$(host_for "$target") service=${service}"
    elif [ -n "$active_state" ]; then
      echo "${target} [inactive] host=$(host_for "$target") service=${service} active_state=${active_state}"
    else
      echo "${target} [unit-missing] host=$(host_for "$target") service=${service} load_state=${load_state:-unknown}"
    fi
  done
}

run_logs() {
  local target="${1:-}"
  local follow="${2:-}"
  if [ -z "$target" ]; then
    echo "logs requires parent or child" >&2
    exit 2
  fi
  ensure_ssh "$target" || exit 1
  if [ "$follow" = "-f" ]; then
    ssh_run "$target" "journalctl -u $(service_for "$target") -f" || {
      journal_hint
      exit 1
    }
  elif [ -z "$follow" ]; then
    ssh_run "$target" "journalctl -u $(service_for "$target") -n 100 --no-pager" || {
      journal_hint
      exit 1
    }
  else
    echo "unknown logs option: $follow" >&2
    exit 2
  fi
}

run_restart() {
  local target
  for target in $(expand_targets "${1:-both}"); do
    echo "== restarting ${target}: $(service_for "$target") =="
    ensure_ssh "$target" || exit 1
    ssh_run "$target" "sudo -n systemctl restart $(service_for "$target")" || {
      sudoers_hint
      exit 1
    }
  done
}

run_deploy() {
  local target
  for target in $(expand_targets "${1:-both}"); do
    echo "== deploying ${target}: $(host_for "$target") =="
    "$ROOT_DIR/deploy.sh" "$(host_for "$target")"
    echo "== restarting ${target}: $(service_for "$target") =="
    ensure_ssh "$target" || exit 1
    ssh_run "$target" "sudo -n systemctl restart $(service_for "$target")" || {
      sudoers_hint
      exit 1
    }
  done
}

run_ping() {
  local target
  for target in parent child; do
    if ! ensure_ssh "$target"; then
      continue
    fi
    printf "%s " "$target"
    ssh_run "$target" '
      hostname_value=$(hostname)
      if command -v bluetoothctl >/dev/null 2>&1; then
        paired_count=$(bluetoothctl devices Paired 2>/dev/null | sed "/^$/d" | wc -l)
        bluetooth_value="paired_devices=${paired_count}"
      else
        bluetooth_value="bluetoothctl=missing"
      fi
      printf "ssh=ok hostname=%s bluetooth=%s\n" "$hostname_value" "$bluetooth_value"
    '
  done
}

run_shell() {
  local target="${1:-}"
  if [ -z "$target" ]; then
    echo "shell requires parent or child" >&2
    exit 2
  fi
  exec ssh "$(host_for "$target")"
}

main() {
  local command="${1:-}"
  case "$command" in
    ""|--help|-h)
      usage
      ;;
    status)
      run_status "${2:-both}"
      ;;
    logs)
      run_logs "${2:-}" "${3:-}"
      ;;
    restart)
      run_restart "${2:-both}"
      ;;
    deploy)
      run_deploy "${2:-both}"
      ;;
    ping)
      run_ping
      ;;
    shell)
      run_shell "${2:-}"
      ;;
    *)
      echo "unknown command: $command" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
