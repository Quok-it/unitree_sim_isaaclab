# sim-scripts

Shell scripts for launching and managing the Unitree Isaac Lab simulation workflow.

The default entrypoint is `sim-launcher.sh`, which orchestrates:
1. `run-sim.sh` (Isaac sim in Docker)

If you also want teleop launched automatically, use `sim-launcher-teleop.sh`.

## How It Works

`sim-launcher.sh` is the sim-only orchestrator.

On `start`, it:
1. Cleans up stale Docker containers for the configured image.
2. Starts `run-sim.sh` in a detached tmux session (`unitree-sim`).
3. Waits for a startup delay (default 15 seconds).
4. Writes logs under `./logs/sim.log`.

On `stop`, it:
1. Kills sim tmux session.
2. Kills leftover Docker containers from the configured image.

It also supports `status`, `logs`, `restart`, and `clean` (stale DDS shared memory cleanup in `/dev/shm`).

`sim-launcher-teleop.sh` is the combined workflow. It keeps the original behavior of starting teleop after sim comes up.

## Scripts

### `sim-launcher.sh` (sim-only orchestrator)
- Manages the sim tmux session.
- Handles startup sequence and delay.
- Provides operational commands (`start/stop/status/logs/clean/restart`).
- Detects and optionally removes stale DDS/FastRTPS shared memory files.

### `sim-launcher-teleop.sh` (combined orchestrator)
- Starts sim, waits, then starts teleop.
- Manages both tmux sessions.
- Uses the same cleanup and log behavior as the original launcher.

### `run-sim.sh` (simulation)
- Runs `unitree_sim_isaaclab` in Docker (`unitree-sim` image by default).
- Requires a graphical session (`DISPLAY` must be set).
- Mounts assets and `sim_main.py` into the container.
- Activates `unitree_sim_env` and runs `python sim_main.py` with task/device flags.
- Includes warmup delay (`WARMUP_SECS`, default 15s) before launching Python.

### `run-teleop.sh` (teleoperation)
- Runs `teleop_hand_and_arm.py` from local teleop source tree.
- Finds a Conda installation and activates env `tv2` by default.
- Starts teleop in simulation mode:
	- `--ee=dex3`
	- `--input-mode=waldo`
	- `--sim`
	- `--record`

## Prerequisites

- Linux host with GUI/X11 session (for Isaac rendering).
- `bash`, `tmux`, `docker`, `xhost` installed.
- NVIDIA GPU + NVIDIA container runtime available (`docker run --gpus all`).
- Docker image available locally (default: `unitree-sim`).
- Unitree sim repo present (default: `$HOME/unitree_sim_isaaclab`).
- Teleop repo present (default: `$HOME/unitree_xr_teleoperate/teleop`).
- Conda installed with required teleop environment (default env: `tv2`).

## Quick Start

From this repo root:

```bash
chmod +x sim-launcher.sh sim-launcher-teleop.sh run-sim.sh run-teleop.sh
./sim-launcher.sh start
```

To run the combined workflow instead:

```bash
./sim-launcher-teleop.sh start
```

Check status:

```bash
./sim-launcher.sh status
```

Follow logs:

```bash
./sim-launcher.sh logs sim
./sim-launcher.sh logs teleop
./sim-launcher.sh logs both
```

Stop everything:

```bash
./sim-launcher.sh stop
```

## Command Reference

```bash
./sim-launcher.sh start
./sim-launcher.sh stop
./sim-launcher.sh status
./sim-launcher.sh logs
./sim-launcher.sh clean
./sim-launcher.sh restart
```

## Environment Variables

Set these before launching if your setup differs from defaults.

### Orchestrator (`sim-launcher.sh`)
- `STARTUP_DELAY` (default `15`): delay before the sim startup check.
- `DOCKER_IMAGE` (default `unitree-sim`): image used to detect/kill stale containers.
- `SUDO` (default empty): set to `sudo` if Docker requires elevated privileges.

### Combined orchestrator (`sim-launcher-teleop.sh`)
- `STARTUP_DELAY` (default `15`): delay between sim and teleop launch.
- `DOCKER_IMAGE` (default `unitree-sim`): image used to detect/kill stale containers.
- `SUDO` (default empty): set to `sudo` if Docker requires elevated privileges.

### Simulation (`run-sim.sh`)
- `SIM_DIR` (default `$HOME/unitree_sim_isaaclab`): local sim workspace.
- `DOCKER_IMAGE` (default `unitree-sim`): Docker image to run.
- `SUDO` (default empty): prefix Docker commands.
- `WARMUP_SECS` (default `15`): delay before starting `sim_main.py`.

### Teleop (`run-teleop.sh`)
- `TELEOP_DIR` (default `$HOME/unitree_xr_teleoperate/teleop`): teleop source directory.
- `CONDA_ENV` (default `tv2`): Conda env used for teleop.

Example:

```bash
export SIM_DIR=$HOME/unitree_sim_isaaclab
export TELEOP_DIR=$HOME/unitree_xr_teleoperate/teleop
export CONDA_ENV=tv2
export DOCKER_IMAGE=unitree-sim
export SUDO=sudo
./sim-launcher.sh start
```

## Operational Notes

- tmux sessions used by default:
- `sim-launcher.sh`: `unitree-sim`
- `sim-launcher-teleop.sh`: `unitree-sim`, `unitree-teleop`
- Attach live:

```bash
tmux attach -t unitree-sim
tmux attach -t unitree-teleop
```

- Log files are written to `./logs` in this repo.

## Troubleshooting

- `DISPLAY is not set`:
- Run from a graphical shell session.

- Sim or teleop directory not found:
- Set `SIM_DIR` / `TELEOP_DIR` to correct paths.

- `conda not found` in teleop:
- Ensure Conda is installed in a standard location or update `run-teleop.sh` search paths.

- DDS/FastRTPS shared memory issues:
- Run `./sim-launcher.sh clean` to remove stale `/dev/shm` segments.

- Already running warning on start:
- Use `./sim-launcher.sh status` and `./sim-launcher.sh stop` first.
