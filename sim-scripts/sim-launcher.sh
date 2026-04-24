#!/usr/bin/env bash
# Orchestrator: launches sim as a detached tmux session.
# Subcommands: start | stop | status | logs | clean | restart

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"

SIM_SESSION="unitree-sim"
DOCKER_IMAGE="${DOCKER_IMAGE:-unitree-sim}"

STARTUP_DELAY="${STARTUP_DELAY:-15}"
SUDO="${SUDO:-}"

mkdir -p "$LOG_DIR"

have_session() { tmux has-session -t "$1" 2>/dev/null; }

count_stale_shm() {
    # FastRTPS shm segments left behind by crashed sim runs
    find /dev/shm -maxdepth 1 \( -name 'fastrtps_*' -o -name 'sem.fastrtps_*' -o -name 'psm_*' \) 2>/dev/null | wc -l
}

clean_stale_shm() {
    # Most segments are owned by root (container runs as root), so we need sudo.
    local n
    n=$(count_stale_shm)
    if [[ "$n" -eq 0 ]]; then
        echo "No stale DDS shm segments."
        return 0
    fi
    echo "Removing $n stale DDS shm segments (may prompt for sudo)..."
    sudo rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/psm_* 2>/dev/null || true
    echo "After cleanup: $(count_stale_shm) remaining."
}

stale_containers() {
    $SUDO docker ps -q --filter ancestor="$DOCKER_IMAGE" 2>/dev/null || true
}

kill_stale_containers() {
    local c
    c=$(stale_containers)
    if [[ -n "$c" ]]; then
        # shellcheck disable=SC2086
        $SUDO docker kill $c >/dev/null 2>&1 || true
    fi
}

start() {
    if have_session "$SIM_SESSION"; then
        echo "Already running. Run '$0 stop' first, or '$0 status' to inspect."
        exit 1
    fi

    if [[ -z "${DISPLAY:-}" ]]; then
        echo "ERROR: DISPLAY is not set. Run from a graphical session." >&2
        exit 1
    fi

    echo "[1/3] Cleaning up any stale '$DOCKER_IMAGE' containers..."
    kill_stale_containers

    local stale
    stale=$(count_stale_shm)
    if [[ "$stale" -gt 0 ]]; then
        echo "WARNING: $stale stale DDS shm segments in /dev/shm — can cause tensor/DDS errors."
        echo "         Run '$0 clean' to remove them (needs sudo)."
    fi

    echo "[2/2] Starting sim in tmux session '$SIM_SESSION'..."
    : > "$LOG_DIR/sim.log"
    tmux new-session -d -s "$SIM_SESSION" -x 220 -y 50 \
        "bash '$SCRIPT_DIR/run-sim.sh' 2>&1 | tee -a '$LOG_DIR/sim.log'; echo '[run-sim.sh exited with '\$?']' >> '$LOG_DIR/sim.log'"

    echo "       Waiting ${STARTUP_DELAY}s for sim to come up..."
    sleep "$STARTUP_DELAY"

    if ! have_session "$SIM_SESSION"; then
        echo "ERROR: sim session exited during startup. Check $LOG_DIR/sim.log" >&2
        exit 1
    fi

    echo
    echo "Started. Useful commands:"
    echo "  $0 status"
    echo "  $0 logs"
    echo "  $0 stop"
    echo "  tmux attach -t $SIM_SESSION     # attach live"
}

stop() {
    echo "Stopping sim session..."
    tmux kill-session -t "$SIM_SESSION" 2>/dev/null || true

    echo "Killing any remaining '$DOCKER_IMAGE' containers..."
    kill_stale_containers

    echo "Stopped."
}

status() {
    local sim_state containers
    if have_session "$SIM_SESSION"; then sim_state="running"; else sim_state="stopped"; fi
    containers=$($SUDO docker ps --filter ancestor="$DOCKER_IMAGE" --format '{{.ID}}  {{.Status}}  {{.Names}}' 2>/dev/null || true)

    echo "sim tmux session:    $sim_state"
    echo "docker containers:   ${containers:-(none)}"
    echo "logs:                $LOG_DIR"
}

logs() {
    tail -n 100 -f "$LOG_DIR/sim.log"
}

usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
    start                       Launch sim in a detached tmux session
    stop                        Kill the sim tmux session and any stale containers
    status                      Print running state of sim + docker
    logs                        Tail the sim log file
  clean                       Remove stale FastRTPS /dev/shm segments (needs sudo)
  restart                     stop + start

Env vars:
    STARTUP_DELAY=<sec>    delay before checking sim startup (default 15)
    DOCKER_IMAGE=<name>    docker image name (default unitree-sim)
    SUDO=sudo              prefix docker commands with sudo (default empty)
EOF
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    status)  status ;;
    logs)    logs ;;
    clean)   clean_stale_shm ;;
    restart) stop; sleep 2; start ;;
    -h|--help|help|"") usage ;;
    *) echo "Unknown command: $1" >&2; usage; exit 1 ;;
esac
