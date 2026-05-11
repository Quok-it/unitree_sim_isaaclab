# sim-scripts

Shell scripts for launching and managing the Unitree Isaac Lab simulation.

The entrypoint is `sim-launcher.sh`, which manages a detached tmux session running `run-sim.sh` (Isaac sim in Docker).

## How it works

`sim-launcher.sh start`:
1. Cleans up stale Docker containers for the configured image.
2. Resolves `--task` / `--hand` into a sim task ID + hand DDS flag.
3. Starts `run-sim.sh` in a detached tmux session named `unitree-sim`.
4. Waits `STARTUP_DELAY` seconds (default 15), then verifies the session is alive.
5. Streams logs to `./logs/sim.log`.

`sim-launcher.sh stop` kills the tmux session and any leftover containers.

Other commands: `status`, `logs`, `restart`, `clean` (purges stale FastRTPS `/dev/shm` segments).

## Prerequisites

- Linux host with X11 (`DISPLAY` set)
- `bash`, `tmux`, `docker`, `xhost`
- NVIDIA GPU + container runtime (`docker run --gpus all`)
- `unitree-sim` Docker image built locally

## Quick start

```bash
chmod +x sim-launcher.sh run-sim.sh

./sim-launcher.sh start                           # default: arms + brainco
./sim-launcher.sh start --hand dex3               # arms + dex3
./sim-launcher.sh start --task wholebody --hand dex3   # wholebody + dex3
./sim-launcher.sh status
./sim-launcher.sh logs                            # tail -f logs/sim.log
./sim-launcher.sh stop
```

## Launch flags

The launcher takes two orthogonal flags. Defaults are `--task arms --hand brainco`.

### `--task`

| Value | Sim task | Behavior |
|---|---|---|
| `arms` *(default)* | `Isaac-PickPlace-Cylinder-G129-<hand>-Joint` | Fixed base, arms-only joint control |
| `wholebody` | `Isaac-Move-Cylinder-G129-Dex3-Wholebody` | Locomotion + manipulation; auto-enables `dds_wholebody` action mode |

### `--hand`

| Value | DDS flag | Hand |
|---|---|---|
| `brainco` *(default)* | `--enable_brainco_dds` | BrainCo Revo 2 (6 actuated joints/hand, 5 mimic distals) |
| `dex3` | `--enable_dex3_dds` | Unitree Dex3 |

### Unsupported combination

`--task wholebody --hand brainco` is rejected — the wholebody USD only ships with Dex3 hands.

## Command reference

```bash
./sim-launcher.sh start [--task <t>] [--hand <h>]
./sim-launcher.sh restart [--task <t>] [--hand <h>]
./sim-launcher.sh stop
./sim-launcher.sh status
./sim-launcher.sh logs
./sim-launcher.sh clean      # remove stale /dev/shm DDS segments (sudo)
```

`restart` does not remember the previous flags — pass them again to keep the same config.

## Environment variables

### Orchestrator (`sim-launcher.sh`)

| Var | Default | Effect |
|---|---|---|
| `STARTUP_DELAY` | `15` | Seconds to wait after launch before verifying tmux session is alive |
| `DOCKER_IMAGE` | `unitree-sim` | Image name used to detect/kill stale containers |
| `SUDO` | (empty) | Set to `sudo` if your user isn't in the docker group |

### Sim (`run-sim.sh`)

| Var | Default | Effect |
|---|---|---|
| `SIM_DIR` | repo root (auto-detected from script location) | Source dir for bind-mounted code/assets |
| `DOCKER_IMAGE` | `unitree-sim` | Image to run |
| `SUDO` | (empty) | Prefix for `docker run` |
| `WARMUP_SECS` | `15` | In-container delay before `python sim_main.py` (lets FastDDS discovery settle) |
| `SIM_TASK` | (set by launcher, else `Isaac-PickPlace-Cylinder-G129-BrainCo-Joint`) | Task ID |
| `HAND_DDS_FLAG` | (set by launcher, else `--enable_brainco_dds`) | Hand DDS arg passed to `sim_main.py` |

`run-sim.sh` is standalone-runnable; the launcher is just a tmux + lifecycle wrapper.

## Operational notes

- tmux session: `unitree-sim`. Attach live with `tmux attach -t unitree-sim`.
- Logs at `./logs/sim.log`.
- Bind mounts (host → container): `assets/`, `sim_main.py`, `action_provider/`, `dds/`, `tasks/`, `robots/` — so most code edits on the host take effect on the next launch without rebuilding the image.

## Troubleshooting

**`DISPLAY is not set`** — run from a graphical shell.

**`USD file not found`** — verify the asset exists under `$SIM_DIR/assets/...`. By default `SIM_DIR` is the parent of `sim-scripts/`, so it follows wherever you cloned the repo.

**`unrecognized arguments: --enable_brainco_dds`** — the container is running the baked image's `sim_main.py`, not your host copy. Check `mount | grep sim_main` inside the container; if missing, the bind mount didn't apply.

**Hands don't move in sim** — DDS publisher (XR teleop, `send_commands_*.py`, etc.) isn't running, or domain ID mismatches between publisher and subscriber. Sniff `rt/brainco/{left,right}/cmd` (or `rt/dex3/...`) to confirm messages are on the bus.

**Stale DDS segments warning** — `./sim-launcher.sh clean` (needs sudo). Frequent crashes can leave hundreds of `/dev/shm/fastrtps_*` files that cause subtle DDS init errors.

**`Already running` on start** — `./sim-launcher.sh status` to inspect, then `stop` first.
