#!/usr/bin/env bash
S=/home/quokka/waldo/unitree_sim_isaaclab
C=/home/code/unitree_sim_isaaclab

docker run --gpus all -it --rm --network host \
    -e NVIDIA_VISIBLE_DEVICES=all \
    -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video,graphics,display \
    -e DISPLAY="$DISPLAY" \
    -v /usr/share/vulkan/icd.d:/usr/share/vulkan/icd.d:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$S/assets:$C/assets" \
    -v "$S/sim_main.py:$C/sim_main.py:ro" \
    -v "$S/action_provider:$C/action_provider:ro" \
    -v "$S/dds:$C/dds:ro" \
    -v "$S/tasks:$C/tasks:ro" \
    -v "$S/robots:$C/robots:ro" \
    unitree-sim /bin/bash
