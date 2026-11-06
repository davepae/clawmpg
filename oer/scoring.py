"""Scoring: OCM accounting, cycle scores, overall OER and headline metrics.

Pure functions over plain dicts so they are easy to test and to reuse from
other languages. A *task run* dict has these keys:

    task_id, cycle, session, ocm_available, ocm_earned, passed, attempts,
    interventions, cost_usd (float or None), wall_s, quality (0-1)
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from oer import config


def ocm_for_minutes(human_minutes: float) -> float:
    """OpenClaw Miles for a task whose calibrated human baseline is ``human_minutes``."""
    return human_minutes / config.MINUTES_PER_OCM


def efficiency_score(actual: Optional[float], reference: float) -> float:
    """1.0 at or below the reference, then 1 / (1 + log2(actual / reference)).

    ``None`` (unknown or no work done) scores 0. 2x the reference scores 0.5,
    4x scores 0.33. Smooth, bounded to [0, 1], and scale-free.
    """
    if actual is None:
        return 0.0
    if actual <= reference:
        return 1.0
    return 1.0 / (1.0 + math.log2(actual / reference))


def _sum_cost(runs: list[dict]) -> Optional[float]:
    costs = [r.get("cost_usd") for r in runs]
    if any(c is None for c in costs):
        return None
    return float(sum(costs))


def cycle_score(runs: list[dict]) -> dict:
    """Score one cycle from its task runs."""
    available = sum(r["ocm_available"] for r in runs)
    earned = sum(r["ocm_earned"] for r in runs)
    success = earned / available if available else 0.0

    total_cost = _sum_cost(runs)
    cost_per_ocm = None
    if earned > 0 and total_cost is not None:
        cost_per_ocm = total_cost / earned
    cost = efficiency_score(cost_per_ocm, config.REF_COST_PER_OCM_USD)

    attempts = sum(r["attempts"] for r in runs)
    interventions = sum(r["interventions"] for r in runs)
    htr = interventions / attempts if attempts else 1.0
    autonomy = 1.0 - min(1.0, htr)

    wall_s = sum(r["wall_s"] for r in runs)
    min_per_ocm = (wall_s / 60.0) / earned if earned > 0 else None
    speed = efficiency_score(min_per_ocm, config.REF_AGENT_MINUTES_PER_OCM)

    quality = 0.0
    if earned > 0:
        quality = sum(r["quality"] * r["ocm_earned"] for r in runs) / earned

    components = {
        "success": success,
        "cost": cost,
        "autonomy": autonomy,
        "speed": speed,
        "quality": quality,
    }
    oer = 100.0 * sum(config.COMPONENT_WEIGHTS[k] * v for k, v in components.items())
    return {
        "oer": round(oer, 2),
        "components": {k: round(v, 4) for k, v in components.items()},
        "ocm_available": round(available, 4),
        "ocm_earned": round(earned, 4),
        "cost_usd": None if total_cost is None else round(total_cost, 4),
        "wall_s": round(wall_s, 2),
        "attempts": attempts,
        "interventions": interventions,
        "tasks": len(runs),
    }


def overall_score(cycles: dict[str, dict]) -> float:
    """Weighted mean of cycle OERs, renormalised over the cycles present."""
    total_w = sum(config.CYCLE_WEIGHTS[c] for c in cycles)
    if not total_w:
        return 0.0
    return round(sum(config.CYCLE_WEIGHTS[c] * s["oer"] for c, s in cycles.items()) / total_w, 2)


def summarize(runs: Iterable[dict], suite_tasks: int, budget_usd: float,
              measured_sessions: Optional[float] = None) -> dict:
    """Compute cycle scores, overall OER and the headline metrics for a whole run.

    ``measured_sessions`` is set when the plan's own usage limit stopped the run: endurance is then
    the number of suite sessions actually completed before depletion, not a projection.
    """
    runs = list(runs)
    by_cycle: dict[str, list[dict]] = {}
    for r in runs:
        by_cycle.setdefault(r["cycle"], []).append(r)
    cycles = {c: cycle_score(by_cycle[c]) for c in config.CYCLES if c in by_cycle}

    attempts = sum(r["attempts"] for r in runs)
    interventions = sum(r["interventions"] for r in runs)
    earned = sum(r["ocm_earned"] for r in runs)
    wall_s = sum(r["wall_s"] for r in runs)
    total_cost = _sum_cost(runs)

    sessions_run = len(runs) / suite_tasks if suite_tasks else 0.0
    cost_per_session = None
    if total_cost is not None and sessions_run > 0:
        cost_per_session = total_cost / sessions_run

    endurance = None
    endurance_basis = None
    monthly = None
    if cost_per_session:
        endurance = budget_usd / cost_per_session
        endurance_basis = "projected"
        monthly = cost_per_session * config.STANDARD_MONTH_SESSIONS
    if measured_sessions is not None:
        endurance, endurance_basis = measured_sessions, "measured"

    return {
        "overall_oer": overall_score(cycles) if cycles else 0.0,
        "cycles": cycles,
        "human_takeover_rate": round(interventions / attempts, 4) if attempts else None,
        "ocm_earned": round(earned, 4),
        "ocm_per_usd": round(earned / total_cost, 3) if total_cost else None,
        "ocm_per_hour": round(earned / (wall_s / 3600.0), 3) if wall_s else None,
        "total_cost_usd": None if total_cost is None else round(total_cost, 4),
        "total_wall_s": round(wall_s, 2),
        "sessions_run": round(sessions_run, 3),
        "cost_per_session_usd": None if cost_per_session is None else round(cost_per_session, 4),
        "session_endurance": None if endurance is None else round(endurance, 1),
        "endurance_basis": endurance_basis,
        "estimated_monthly_cost_usd": None if monthly is None else round(monthly, 2),
        "budget_usd": budget_usd,
    }


def relative_score(oer: float, best_observed: float) -> float:
    """Optional leaderboard-relative score: 100 = best observed system."""
    return round(100.0 * oer / best_observed, 2) if best_observed else 0.0
