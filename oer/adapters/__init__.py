"""Adapter registry."""

from __future__ import annotations

from typing import Optional

from oer import config
from oer.adapters.base import Adapter, AdapterRequest, AdapterResult
from oer.adapters.cli import CliAdapter, ManualAdapter, load_presets
from oer.adapters.mock import MockAdapter

__all__ = ["Adapter", "AdapterRequest", "AdapterResult", "build_adapter"]


def build_adapter(name: str, model_id: Optional[str] = None, effort: Optional[str] = None,
                  plan: Optional[str] = None, command: Optional[list[str]] = None,
                  cost_per_run: Optional[float] = None, mock_skill: float = 1.0,
                  mock_seed: str = "0") -> Adapter:
    """Build an adapter by name: ``mock``, ``manual``, ``custom`` (needs ``command``) or a preset.

    ``model_id`` and ``effort`` default to the pinned cohort (config.PINNED).
    """
    model_id = model_id or config.PINNED["model"]
    effort = effort or config.PINNED["effort"]
    if name == "mock":
        return MockAdapter(skill=mock_skill, seed=mock_seed)
    if name == "manual":
        return ManualAdapter(model_id=model_id, effort=effort, plan=plan)
    if name == "custom":
        if not command:
            raise ValueError("--command is required for the custom adapter")
        return CliAdapter("custom", command, model_id=model_id, effort=effort, plan=plan,
                          cost_per_run_usd=cost_per_run)
    presets = load_presets()
    if name in presets and not name.startswith("_"):
        p = presets[name]
        # A preset's own model id is the spelling that tool expects for the pinned model.
        use_model = model_id if model_id != config.PINNED["model"] else p.get("model_id", model_id)
        return CliAdapter(name, p["command"], model_id=use_model, effort=effort,
                          effort_mode=p.get("effort_mode", "flag"), plan=plan or p.get("plan"),
                          parser=p.get("parser", "none"), cost_per_run_usd=cost_per_run,
                          exhaustion_pattern=p.get("exhaustion_pattern"), env_unset=p.get("env_unset"),
                          verified=p.get("verified", False))
    known = ["mock", "manual", "custom"] + [k for k in presets if not k.startswith("_")]
    raise ValueError(f"unknown adapter {name!r}; choose from {known}")
