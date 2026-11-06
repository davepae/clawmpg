"""Adapter interface: the only thing a new agent integration has to implement."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AdapterRequest:
    prompt: str
    workdir: Path
    timeout_s: int
    task_id: str
    cycle: str
    # Only the mock adapter may look at this; real adapters must ignore it.
    solution_dir: Optional[Path] = None
    solution_deletes: list = field(default_factory=list)


@dataclass
class AdapterResult:
    exit_code: int = 0
    duration_s: float = 0.0
    cost_usd: Optional[float] = None
    # metered | token_estimate | quota_fraction | manual | synthetic | unknown
    cost_basis: str = "unknown"
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    interventions: int = 0
    timed_out: bool = False
    log_tail: str = ""
    notes: str = ""
    # Model the tool itself reported using (None if it does not say).
    observed_model: Optional[str] = None
    # True when the plan's usage limit stopped the agent (credits/quota depleted).
    quota_exhausted: bool = False


class Adapter:
    name = "base"
    synthetic = False
    plan: Optional[str] = None

    def describe(self) -> dict:
        """System identity recorded in the result file."""
        return {"system": self.name, "model": None, "model_id": None, "effort": None,
                "plan": self.plan, "version": None}

    def run(self, req: AdapterRequest) -> AdapterResult:  # pragma: no cover - interface
        raise NotImplementedError
