from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence
import os

import numpy as np

try:
    import pinocchio as pin
except Exception as exc:  # pragma: no cover - import guard for runtime env
    pin = None
    _PIN_IMPORT_ERR = exc
else:
    _PIN_IMPORT_ERR = None


@dataclass
class ModelMapping:
    joint_map: List[int]
    joint_sign: List[float]
    joint_offset_deg: List[float]


class PinocchioModel:
    def __init__(
        self,
        urdf_path: str,
        mapping: ModelMapping | None = None,
    ) -> None:
        if pin is None:
            raise RuntimeError(f"pinocchio import failed: {_PIN_IMPORT_ERR}")
        if not os.path.exists(urdf_path):
            raise FileNotFoundError(f"URDF not found: {urdf_path}")
        self.urdf_path = os.path.abspath(urdf_path)

        try:
            self.model = pin.buildModelFromUrdf(self.urdf_path)
        except Exception as exc:
            raise RuntimeError(f"pinocchio failed loading URDF '{self.urdf_path}': {exc}") from exc
        self.data = self.model.createData()

        if mapping is None:
            mapping = ModelMapping(
                joint_map=[0, 1, 2, 3, 4, 5],
                joint_sign=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                joint_offset_deg=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            )
        self.mapping = mapping

        self._validate_mapping()

    def _validate_mapping(self) -> None:
        if len(self.mapping.joint_map) != 6:
            raise ValueError(f"joint_map must have 6 entries, got {len(self.mapping.joint_map)}")
        if len(self.mapping.joint_sign) != 6:
            raise ValueError(f"joint_sign must have 6 entries, got {len(self.mapping.joint_sign)}")
        if len(self.mapping.joint_offset_deg) != 6:
            raise ValueError(f"joint_offset_deg must have 6 entries, got {len(self.mapping.joint_offset_deg)}")
        for i, idx in enumerate(self.mapping.joint_map):
            if idx < 0 or idx >= self.model.nq:
                raise ValueError(
                    f"joint_map[{i}]={idx} out of range [0, {self.model.nq - 1}] "
                    f"for URDF '{self.urdf_path}' (nq={self.model.nq}, nv={self.model.nv})"
                )

    def compute_gravity_torque_nm(self, q_robot_deg: Sequence[float]) -> np.ndarray:
        if len(q_robot_deg) != 6:
            raise ValueError("q_robot_deg must have 6 elements")

        q_full = np.zeros(self.model.nq, dtype=float)
        for i in range(6):
            idx = self.mapping.joint_map[i]
            sign = float(self.mapping.joint_sign[i])
            offset = float(self.mapping.joint_offset_deg[i])
            q_full[idx] = np.deg2rad((float(q_robot_deg[i]) + offset) * sign)

        try:
            pin.computeGeneralizedGravity(self.model, self.data, q_full)
        except Exception as exc:
            raise RuntimeError(
                f"computeGeneralizedGravity failed for '{self.urdf_path}' with nq={self.model.nq}, nv={self.model.nv}: {exc}"
            ) from exc

        tau_robot = np.zeros(6, dtype=float)
        for i in range(6):
            idx = self.mapping.joint_map[i]
            sign = float(self.mapping.joint_sign[i])
            tau_robot[i] = float(self.data.g[idx]) * sign
        return tau_robot
