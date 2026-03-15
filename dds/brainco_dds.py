# Copyright (c) 2025, Unitree Robotics Co., Ltd. All Rights Reserved.
# License: Apache License, Version 2.0
"""
BrainCo Revo 2 DDS communication class
Handle the state publishing and command receiving of the hand (left and right)

DDS Interface Contract:
- Topics: rt/brainco/left/cmd, rt/brainco/right/cmd, rt/brainco/left/state, rt/brainco/right/state
- Message type: MotorCmds_ / MotorStates_ (unitree_go)
- 6 joints per hand, separate messages per hand
- Values normalized [0.0, 1.0] where 0=open, 1=closed
- Joint ordering per hand: thumb_metacarpal, thumb_proximal, index, middle, ring, pinky
- Joint max ranges (rad): [1.52, 1.05, 1.47, 1.47, 1.47, 1.47]
"""

import threading
from typing import Any, Dict, Optional
import numpy as np
from dds.dds_base import DDSObject
from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorCmds_, MotorStates_
from unitree_sdk2py.idl.default import unitree_go_msg_dds__MotorCmd_, unitree_go_msg_dds__MotorState_


# Max joint angle (rad) per joint index, used for normalize/denormalize
_JOINT_MAX_RAD = [1.52, 1.05, 1.47, 1.47, 1.47, 1.47]
_NUM_JOINTS = 6


class BrainCoDDS(DDSObject):
    """BrainCo Revo 2 DDS communication class - singleton pattern

    Features:
    - Publish the state of the hand to DDS (rt/brainco/left/state, rt/brainco/right/state)
    - Receive the control command of the hand (rt/brainco/left/cmd, rt/brainco/right/cmd)
    - 6 actuated joints per hand, normalized [0,1] over DDS
    """

    def __init__(self, node_name: str = "brainco"):
        """Initialize the BrainCo DDS node"""
        if hasattr(self, '_initialized'):
            return

        super().__init__()
        self.node_name = node_name

        # initialize per-hand state messages (6 motors each)
        self.left_hand_state = MotorStates_()
        self.left_hand_state.states = [unitree_go_msg_dds__MotorState_() for _ in range(_NUM_JOINTS)]

        self.right_hand_state = MotorStates_()
        self.right_hand_state.states = [unitree_go_msg_dds__MotorState_() for _ in range(_NUM_JOINTS)]

        # publishers and subscribers
        self.left_state_publisher = None
        self.right_state_publisher = None
        self.left_cmd_subscriber = None
        self.right_cmd_subscriber = None

        self._initialized = True
        self.existing_data = {"left_hand_cmd": {}, "right_hand_cmd": {}}

        # setup shared memory
        self.setup_shared_memory(
            input_shm_name="isaac_brainco_state",
            input_size=1024,
            output_shm_name="isaac_brainco_cmd",
            output_size=1024,
        )

        print(f"[{self.node_name}] BrainCo Revo 2 DDS node initialized")

    def setup_publisher(self) -> bool:
        """Setup state publishers for both hands"""
        try:
            self.left_state_publisher = ChannelPublisher("rt/brainco/left/state", MotorStates_)
            self.left_state_publisher.Init()

            self.right_state_publisher = ChannelPublisher("rt/brainco/right/state", MotorStates_)
            self.right_state_publisher.Init()

            print(f"[{self.node_name}] BrainCo state publishers initialized")
            return True
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] State publisher initialization failed: {e}")
            return False

    def setup_subscriber(self) -> bool:
        """Setup command subscribers for both hands"""
        try:
            self.left_cmd_subscriber = ChannelSubscriber("rt/brainco/left/cmd", MotorCmds_)
            self.left_cmd_subscriber.Init(
                lambda msg: self.dds_subscriber(msg, "left"), 32
            )

            self.right_cmd_subscriber = ChannelSubscriber("rt/brainco/right/cmd", MotorCmds_)
            self.right_cmd_subscriber.Init(
                lambda msg: self.dds_subscriber(msg, "right"), 32
            )

            print(f"[{self.node_name}] BrainCo command subscribers initialized")
            return True
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Command subscriber initialization failed: {e}")
            return False

    @staticmethod
    def _denormalize(normalized_val, max_rad):
        """Convert normalized [0,1] to joint radians"""
        return np.clip(normalized_val, 0.0, 1.0) * max_rad

    @staticmethod
    def _normalize(rad_val, max_rad):
        """Convert joint radians to normalized [0,1]"""
        return np.clip(rad_val / max_rad, 0.0, 1.0) if max_rad > 0 else 0.0

    def dds_subscriber(self, msg: MotorCmds_, datatype: str = None):
        """Handle incoming hand commands from xr_teleoperate"""
        try:
            cmd_data = self._process_hand_command(msg)
            # print(f"[DEBUG] brainco_dds [{self.node_name}] Received {datatype} hand command: {cmd_data}")
            if cmd_data and self.output_shm:
                self.existing_data[f"{datatype}_hand_cmd"] = cmd_data
                self.output_shm.write_data(self.existing_data)
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Error handling {datatype} hand command: {e}")

    def _process_hand_command(self, msg: MotorCmds_) -> Dict[str, Any]:
        """Process hand command: denormalize DDS values to Isaac Lab joint radians"""
        try:
            n = min(_NUM_JOINTS, len(msg.cmds))
            cmd_data = {
                "positions": [
                    float(self._denormalize(msg.cmds[i].q, _JOINT_MAX_RAD[i]))
                    for i in range(n)
                ],
                "velocities": [float(msg.cmds[i].dq) for i in range(n)],
                "torques": [float(msg.cmds[i].tau) for i in range(n)],
                "kp": [float(msg.cmds[i].kp) for i in range(n)],
                "kd": [float(msg.cmds[i].kd) for i in range(n)],
            }
            return cmd_data
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Error processing hand command: {e}")
            return {}

    def dds_publisher(self) -> Any:
        """Publish hand state: read Isaac Lab state from shared memory, normalize, publish to DDS

        Expected shared memory data format:
        {
            "left_hand": {
                "positions": [6 joint positions in radians],
                "velocities": [6 joint velocities],
                "torques": [6 joint torques]
            },
            "right_hand": {
                "positions": [6 joint positions in radians],
                "velocities": [6 joint velocities],
                "torques": [6 joint torques]
            }
        }
        """
        try:
            data = self.input_shm.read_data()
            if data is None:
                return

            if "left_hand" in data:
                self._update_hand_state(self.left_hand_state, data["left_hand"])
                if self.left_state_publisher:
                    self.left_state_publisher.Write(self.left_hand_state)

            if "right_hand" in data:
                self._update_hand_state(self.right_hand_state, data["right_hand"])
                if self.right_state_publisher:
                    self.right_state_publisher.Write(self.right_hand_state)

        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Error processing publish data: {e}")
            return None

    def _update_hand_state(self, hand_state: MotorStates_, hand_data: Dict[str, Any]):
        """Update hand state message with normalized values"""
        try:
            if not all(key in hand_data for key in ["positions", "velocities", "torques"]):
                return
            positions = hand_data["positions"]
            velocities = hand_data["velocities"]
            torques = hand_data["torques"]

            for i in range(min(_NUM_JOINTS, len(positions))):
                if i < len(hand_state.states):
                    hand_state.states[i].q = float(self._normalize(positions[i], _JOINT_MAX_RAD[i]))
                    if i < len(velocities):
                        hand_state.states[i].dq = float(velocities[i])
                    if i < len(torques):
                        hand_state.states[i].tau_est = float(torques[i])
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Error updating hand state: {e}")

    def get_hand_commands(self) -> Optional[Dict[str, Any]]:
        """Get hand control commands for both hands

        Returns:
            Dict with "left_hand_cmd" and "right_hand_cmd" keys
        """
        if self.output_shm:
            return self.output_shm.read_data()
        return None

    def get_left_hand_command(self) -> Optional[Dict[str, Any]]:
        """Get the left hand command"""
        commands = self.get_hand_commands()
        if commands and "left_hand_cmd" in commands:
            return commands["left_hand_cmd"]
        return None

    def get_right_hand_command(self) -> Optional[Dict[str, Any]]:
        """Get the right hand command"""
        commands = self.get_hand_commands()
        if commands and "right_hand_cmd" in commands:
            return commands["right_hand_cmd"]
        return None

    def write_hand_states(self, left_positions, left_velocities, left_torques,
                         right_positions, right_velocities, right_torques):
        """Write hand states to shared memory for DDS publishing

        Args:
            left_positions: 6 left hand joint positions (radians)
            left_velocities: 6 left hand joint velocities
            left_torques: 6 left hand joint torques
            right_positions: 6 right hand joint positions (radians)
            right_velocities: 6 right hand joint velocities
            right_torques: 6 right hand joint torques
        """
        try:
            combined_data = {
                "left_hand": {
                    "positions": left_positions.tolist() if hasattr(left_positions, 'tolist') else left_positions,
                    "velocities": left_velocities.tolist() if hasattr(left_velocities, 'tolist') else left_velocities,
                    "torques": left_torques.tolist() if hasattr(left_torques, 'tolist') else left_torques,
                },
                "right_hand": {
                    "positions": right_positions.tolist() if hasattr(right_positions, 'tolist') else right_positions,
                    "velocities": right_velocities.tolist() if hasattr(right_velocities, 'tolist') else right_velocities,
                    "torques": right_torques.tolist() if hasattr(right_torques, 'tolist') else right_torques,
                },
            }
            if self.input_shm:
                self.input_shm.write_data(combined_data)
        except Exception as e:
            print(f"brainco_dds [{self.node_name}] Error writing hand states: {e}")
