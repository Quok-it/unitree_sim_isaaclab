#!/usr/bin/env bash
# Launch the Isaac sim inside the unitree-sim docker container.
# Standalone-testable: run ./run-sim.sh and it blocks until sim exits.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# SIM_DIR resolution order:
#   1. SIM_DIR env var (ad-hoc override — points at any repo path)
#   2. WALDO_ISAAC_DIR env var (matches updater.ts convention)
#   3. $HOME/unitree_sim_isaaclab (customer install layout per updater.ts:95)
# This avoids deriving from $SCRIPT_DIR — when the script is `cp`'d to
# /opt/waldo/bin/ by the updater, $SCRIPT_DIR/.. would resolve to /opt/waldo
# which doesn't contain the repo content (sim_main.py, tasks/, etc.).
SIM_DIR="${SIM_DIR:-${WALDO_ISAAC_DIR:-$HOME/unitree_sim_isaaclab}}"
DOCKER_IMAGE="${DOCKER_IMAGE:-unitree-sim}"
SUDO="${SUDO:-}"               # export SUDO=sudo if your user isn't in the docker group
WARMUP_SECS="${WARMUP_SECS:-15}" # pre-python delay inside container — lets FastDDS discovery settle
                                # (without this, the sim crashes at [Observations Dex3] with a tensor
                                # shape mismatch because subscribers spin up before any publisher has
                                # announced on the DDS bus)

SIM_TASK="${SIM_TASK:-Isaac-PickPlace-Cylinder-G129-BrainCo-Joint}"
HAND_DDS_FLAG="${HAND_DDS_FLAG:---enable_brainco_dds}"  # one of: --enable_dex3_dds | --enable_brainco_dds | --enable_dex1_dds | --enable_inspire_dds

if [[ -z "${DISPLAY:-}" ]]; then
    echo "ERROR: DISPLAY is not set. Run this from a graphical session." >&2
    exit 1
fi

if [[ ! -d "$SIM_DIR" ]]; then
    echo "ERROR: SIM_DIR does not exist: $SIM_DIR" >&2
    exit 1
fi

cd "$SIM_DIR"

xhost +SI:localuser:root >/dev/null

exec $SUDO docker run --gpus all -it --rm --network host \
    -e NVIDIA_VISIBLE_DEVICES=all \
    -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video,graphics,display \
    -e DISPLAY="$DISPLAY" \
    -v /usr/share/vulkan/icd.d:/usr/share/vulkan/icd.d:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$SIM_DIR/assets:/home/code/unitree_sim_isaaclab/assets" \
    -v "$SIM_DIR/sim_main.py:/home/code/unitree_sim_isaaclab/sim_main.py:ro" \
    -v "$SIM_DIR/action_provider:/home/code/unitree_sim_isaaclab/action_provider:ro" \
    -v "$SIM_DIR/dds:/home/code/unitree_sim_isaaclab/dds:ro" \
    -v "$SIM_DIR/tasks:/home/code/unitree_sim_isaaclab/tasks:ro" \
    -v "$SIM_DIR/robots:/home/code/unitree_sim_isaaclab/robots:ro" \
    "$DOCKER_IMAGE" \
    /bin/bash -c "
        source /opt/conda/etc/profile.d/conda.sh &&
        conda activate unitree_sim_env &&
        echo 'Warming up for ${WARMUP_SECS}s before starting sim...' &&
        sleep ${WARMUP_SECS} &&
        cd unitree_sim_isaaclab &&
        python sim_main.py \
            --device cpu \
            --enable_cameras \
            --task ${SIM_TASK} \
            ${HAND_DDS_FLAG} \
            --robot_type g129 \
            --kit_args '--/app/renderer/waitIdle=false --/app/hydraEngine/waitIdle=false'
    "
