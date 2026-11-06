"""Deterministic mock agent for CI and harness development.

It "solves" a task by overlaying the task's reference solution, with a
probability derived from ``skill``. Its cost and time are synthetic, so results
are flagged ``synthetic`` and never appear on the public leaderboard.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from oer.adapters.base import Adapter, AdapterRequest, AdapterResult


def _uniform(*parts: str) -> float:
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


class MockAdapter(Adapter):
    name = "mock"
    synthetic = True

    def __init__(self, skill: float = 1.0, seed: str = "0", usd_per_minute: float = 0.05):
        self.skill = skill
        self.seed = seed
        self.usd_per_minute = usd_per_minute

    def describe(self) -> dict:
        return {"system": "mock", "model": f"skill={self.skill}", "model_id": "mock", "effort": None,
                "plan": None, "version": "0"}

    def run(self, req: AdapterRequest) -> AdapterResult:
        u = _uniform(self.seed, req.task_id)
        minutes = 2 + 6 * _uniform(self.seed, req.task_id, "t")
        solved = u < self.skill
        if solved and req.solution_dir and req.solution_dir.exists():
            shutil.copytree(req.solution_dir, req.workdir, dirs_exist_ok=True)
            for rel in req.solution_deletes:
                target = Path(req.workdir) / rel
                if target.exists():
                    target.unlink()
        return AdapterResult(
            exit_code=0,
            duration_s=minutes * 60,
            cost_usd=round(minutes * self.usd_per_minute, 4),
            cost_basis="synthetic",
            tokens_in=int(minutes * 8000),
            tokens_out=int(minutes * 900),
            notes="synthetic result",
        )
