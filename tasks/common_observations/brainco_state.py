# Copyright (c) 2025, Unitree Robotics Co., Ltd. All Rights Reserved.
# License: Apache License, Version 2.0
"""
BrainCo Revo 2 hand state observation extractor

Joint ordering per hand (6 actuated joints):
  0: thumb_metacarpal_joint  (rotation, 0-1.52 rad)
  1: thumb_proximal_joint    (bend,     0-1.05 rad)
  2: index_proximal_joint    (0-1.47 rad)
  3: middle_proximal_joint   (0-1.47 rad)
  4: ring_proximal_joint     (0-1.47 rad)
  5: pinky_proximal_joint    (0-1.47 rad)

Each finger also has a mimic distal joint (multiplier 1.155) handled by the USD.
"""

from __future__ import annotations

import torch
from typing import TYPE_CHECKING
import sys
import os
if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


# Joint names in DDS ordering: left 6, then right 6
_BRAINCO_JOINT_NAMES = [
    # Left hand (6)
    "left_thumb_metacarpal_joint",
    "left_thumb_proximal_joint",
    "left_index_proximal_joint",
    "left_middle_proximal_joint",
    "left_ring_proximal_joint",
    "left_pinky_proximal_joint",
    # Right hand (6)
    "right_thumb_metacarpal_joint",
    "right_thumb_proximal_joint",
    "right_index_proximal_joint",
    "right_middle_proximal_joint",
    "right_ring_proximal_joint",
    "right_pinky_proximal_joint",
]

_obs_cache = {
    "device": None,
    "batch": None,
    "brainco_idx_t": None,
    "brainco_idx_batch": None,
    "pos_buf": None,
    "vel_buf": None,
    "torque_buf": None,
    "dds_last_ms": 0,
    "dds_min_interval_ms": 20,
}

# global variable to cache the DDS instance
_brainco_dds = None
_dds_initialized = False


def _get_brainco_dds_instance():
    """get the DDS instance, delay initialization"""
    global _brainco_dds, _dds_initialized

    if not _dds_initialized or _brainco_dds is None:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dds'))
            from dds.dds_master import dds_manager
            _brainco_dds = dds_manager.get_object("brainco")
            print("[Observations BrainCo] DDS communication instance obtained")

            import atexit
            def cleanup_dds():
                try:
                    if _brainco_dds:
                        dds_manager.unregister_object("brainco")
                        print("[brainco_state] DDS communication closed correctly")
                except Exception as e:
                    print(f"[brainco_state] Error closing DDS: {e}")
            atexit.register(cleanup_dds)

        except Exception as e:
            print(f"[Observations BrainCo] Failed to get DDS instances: {e}")
            _brainco_dds = None

        _dds_initialized = True

    return _brainco_dds


def _resolve_joint_indices(env):
    """Resolve BrainCo joint indices from joint names in the articulation.

    This is called once and cached. It maps _BRAINCO_JOINT_NAMES to their
    indices in the articulation's joint_pos tensor.
    """
    joint_names = env.scene["robot"].data.joint_names
    name_to_idx = {name: i for i, name in enumerate(joint_names)}
    indices = []
    for jname in _BRAINCO_JOINT_NAMES:
        if jname in name_to_idx:
            indices.append(name_to_idx[jname])
        else:
            print(f"[brainco_state] WARNING: joint '{jname}' not found in articulation. "
                  f"Available: {joint_names}")
            indices.append(0)  # fallback
    return indices


def get_robot_brainco_joint_names() -> list[str]:
    return list(_BRAINCO_JOINT_NAMES)


def get_robot_brainco_joint_states(
    env: ManagerBasedRLEnv,
    enable_dds: bool = True,
) -> torch.Tensor:
    """Get the BrainCo hand joint states and publish them to DDS

    Args:
        env: ManagerBasedRLEnv
        enable_dds: whether to publish to DDS

    Returns:
        torch.Tensor of shape (batch, 12) — 6 left + 6 right joint positions
    """
    joint_pos = env.scene["robot"].data.joint_pos
    joint_vel = env.scene["robot"].data.joint_vel
    joint_torque = env.scene["robot"].data.applied_torque
    device = joint_pos.device
    batch = joint_pos.shape[0]

    global _obs_cache
    if _obs_cache["device"] != device or _obs_cache["brainco_idx_t"] is None:
        brainco_joint_indices = _resolve_joint_indices(env)
        _obs_cache["brainco_idx_t"] = torch.tensor(brainco_joint_indices, dtype=torch.long, device=device)
        _obs_cache["device"] = device
        _obs_cache["batch"] = None

    idx_t = _obs_cache["brainco_idx_t"]
    n = idx_t.numel()

    if _obs_cache["batch"] != batch or _obs_cache["brainco_idx_batch"] is None:
        _obs_cache["brainco_idx_batch"] = idx_t.unsqueeze(0).expand(batch, n)
        _obs_cache["pos_buf"] = torch.empty(batch, n, device=device, dtype=joint_pos.dtype)
        _obs_cache["vel_buf"] = torch.empty(batch, n, device=device, dtype=joint_pos.dtype)
        _obs_cache["torque_buf"] = torch.empty(batch, n, device=device, dtype=joint_pos.dtype)
        _obs_cache["batch"] = batch

    idx_batch = _obs_cache["brainco_idx_batch"]
    pos_buf = _obs_cache["pos_buf"]
    vel_buf = _obs_cache["vel_buf"]
    torque_buf = _obs_cache["torque_buf"]

    try:
        torch.gather(joint_pos, 1, idx_batch, out=pos_buf)
        torch.gather(joint_vel, 1, idx_batch, out=vel_buf)
        torch.gather(joint_torque, 1, idx_batch, out=torque_buf)
    except TypeError:
        pos_buf.copy_(torch.gather(joint_pos, 1, idx_batch))
        vel_buf.copy_(torch.gather(joint_vel, 1, idx_batch))
        torque_buf.copy_(torch.gather(joint_torque, 1, idx_batch))

    # publish to DDS (first environment only)
    if enable_dds and len(pos_buf) > 0:
        try:
            import time
            now_ms = int(time.time() * 1000)
            if now_ms - _obs_cache["dds_last_ms"] >= _obs_cache["dds_min_interval_ms"]:
                brainco_dds = _get_brainco_dds_instance()
                if brainco_dds:
                    pos = pos_buf[0].contiguous().cpu().numpy()
                    vel = vel_buf[0].contiguous().cpu().numpy()
                    torque = torque_buf[0].contiguous().cpu().numpy()
                    # split into left (0:6) and right (6:12)
                    brainco_dds.write_hand_states(
                        pos[:6], vel[:6], torque[:6],
                        pos[6:], vel[6:], torque[6:],
                    )
                    _obs_cache["dds_last_ms"] = now_ms
        except Exception as e:
            print(f"[brainco_state] Failed to write to shared memory: {e}")

    return pos_buf
