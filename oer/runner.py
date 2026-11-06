"""Benchmark runner: fresh workdir per attempt -> agent -> hidden-test verification -> scoring."""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from oer import config, scoring
from oer.adapters.base import Adapter, AdapterRequest
from oer.tasks import Task
from oer.verify import copy_tree, snapshot, verify

SCHEMA_VERSION = "1.0"


def run_task(adapter: Adapter, task: Task, seed_repo: Path, session: int, max_attempts: int) -> dict:
    attempts = interventions = 0
    wall_s = 0.0
    cost: Optional[float] = 0.0
    cost_bases: list[str] = []
    tokens_in = tokens_out = 0
    tokens_known = True
    outcome: dict = {}
    last = None
    passed = False
    observed: list[Optional[str]] = []
    quota_exhausted = False

    for attempt in range(1, max_attempts + 1):
        with tempfile.TemporaryDirectory(prefix=f"oer-{task.id}-") as tmp:
            workdir = Path(tmp) / "repo"
            copy_tree(seed_repo, workdir)
            baseline = snapshot(workdir)
            last = adapter.run(AdapterRequest(
                prompt=task.prompt, workdir=workdir, timeout_s=task.timeout_s,
                task_id=task.id, cycle=task.cycle,
                solution_dir=task.solution_dir, solution_deletes=task.solution_deletes,
            ))
            outcome = verify(workdir, task, baseline)

        observed.append(last.observed_model)
        if last.quota_exhausted:
            quota_exhausted = True
            break                       # the plan ran dry; the caller discards this partial run
        attempts += 1
        wall_s += last.duration_s
        interventions += last.interventions
        cost_bases.append(last.cost_basis)
        if cost is not None:
            cost = None if last.cost_usd is None else cost + last.cost_usd
        if last.tokens_in is None or last.tokens_out is None:
            tokens_known = False
        else:
            tokens_in += last.tokens_in
            tokens_out += last.tokens_out

        passed = outcome["passed"]
        if passed:
            break
        if attempt < max_attempts:
            interventions += 1          # restarting the agent counts as a human intervention

    if not passed and not quota_exhausted:
        interventions += 1              # a broken solution needs a human to take over

    return {
        "quota_exhausted": quota_exhausted,
        "observed_models": sorted({m for m in observed if m}),
        "all_runs_reported_model": bool(observed) and all(observed),
        "task_id": task.id,
        "cycle": task.cycle,
        "session": session,
        "title": task.title,
        "human_minutes": task.human_minutes,
        "ocm_available": round(task.ocm, 4),
        "ocm_earned": round(task.ocm, 4) if passed else 0.0,
        "passed": passed,
        "attempts": attempts,
        "interventions": interventions,
        "cost_usd": None if cost is None else round(cost, 4),
        "cost_basis": cost_bases[-1] if len(set(cost_bases)) == 1 else "mixed",
        "tokens_in": tokens_in if tokens_known else None,
        "tokens_out": tokens_out if tokens_known else None,
        "wall_s": round(wall_s, 2),
        "quality": outcome.get("quality", 0.0),
        "timed_out": bool(last and last.timed_out),
        "agent_exit_code": last.exit_code if last else None,
        "changed_files": outcome.get("changed_files", []),
        "check_failures": outcome.get("check_failures", []),
        "log_tail": "" if passed else (outcome.get("log_tail", "") or (last.log_tail if last else ""))[-800:],
    }


def harness_commit() -> Optional[str]:
    """Git commit of the harness, with +dirty if the working tree has changes; None outside git."""
    repo = Path(__file__).resolve().parent.parent
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10)
        if head.returncode != 0:
            return None
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return head.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")


def cohort_status(system: dict, synthetic: bool) -> dict:
    """Is the declared model/effort the pinned cohort? (Synthetic runs are never pinned.)"""
    pinned = (not synthetic
              and config.norm_model(system.get("model_id") or "") == config.norm_model(config.PINNED["model"])
              and (system.get("effort") or "") == config.PINNED["effort"])
    return {"pinned": pinned, "model": config.PINNED["model"], "effort": config.PINNED["effort"]}


def model_verification(runs: list[dict]) -> tuple[Optional[bool], list[str]]:
    """True if the tool itself reported only the pinned model on every run; None if it never says."""
    seen = sorted({m for r in runs for entry in r["observed_models"] for m in entry.split("+")})
    if not runs or not all(r["all_runs_reported_model"] for r in runs):
        return None, seen
    return {config.norm_model(m) for m in seen} == {config.norm_model(config.PINNED["model"])}, seen


def run_suite(adapter: Adapter, tasks: list[Task], all_tasks: list[Task], seed_repo: Path, *,
              sessions: int = 1, max_attempts: int = 1, budget_usd: float = config.DEFAULT_BUDGET_USD,
              stop_at_usd: Optional[float] = None, allow_unpinned: bool = False,
              plan_window_start: Optional[str] = None, billing_mode: str = "unknown",
              progress=print) -> dict:
    if billing_mode not in config.BILLING_MODES:
        raise ValueError(f"billing_mode must be one of {config.BILLING_MODES}, got {billing_mode!r}")
    synthetic = bool(getattr(adapter, "synthetic", False))
    system = adapter.describe()
    cohort = cohort_status(system, synthetic)
    if not synthetic and not cohort["pinned"] and not allow_unpinned:
        raise ValueError(
            f"this suite rates the pinned cohort {config.PINNED['model']} @ {config.PINNED['effort']} effort; "
            f"got model={system.get('model_id')!r} effort={system.get('effort')!r}. "
            "Pass --allow-unpinned for an exploratory (unrankable) run.")

    started = datetime.now(timezone.utc)
    runs: list[dict] = []
    spent: Optional[float] = 0.0
    depleted = False
    reason: Optional[str] = None
    exhausted_task: Optional[str] = None

    for session in range(1, sessions + 1):
        for task in tasks:
            if stop_at_usd is not None and spent is not None and spent >= stop_at_usd:
                depleted, reason = True, "usd_cap"
                break
            run = run_task(adapter, task, seed_repo, session, max_attempts)
            if run["quota_exhausted"]:
                # The plan ran dry mid-task. That says something about the plan, not the agent,
                # so the partial run is not scored; the number of full sessions before it is.
                depleted, reason, exhausted_task = True, "quota", task.id
                progress(f"[s{session}] {task.id:<16} PLAN USAGE LIMIT REACHED - stopping")
                break
            runs.append(run)
            spent = None if (spent is None or run["cost_usd"] is None) else spent + run["cost_usd"]
            progress(f"[s{session}] {task.id:<16} {'PASS' if run['passed'] else 'FAIL'}  "
                     f"cost={run['cost_usd']}  wall={run['wall_s']}s")
        if depleted:
            break

    verified, observed = model_verification(runs)
    system = {**system, "model_verified": verified, "observed_models": observed}
    full_ocm = sum(t.ocm for t in all_tasks)
    run_ocm = sum(t.ocm for t in tasks)
    # Endurance is only "measured" against a real plan allowance; past a limit on extra usage there is no cut-off.
    measured = len(runs) / len(tasks) if reason == "quota" and billing_mode != "extra_usage" else None
    return {
        "schema_version": SCHEMA_VERSION,
        "suite_version": config.SUITE_VERSION,
        "run_id": uuid.uuid4().hex[:12],
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness_commit": harness_commit(),
        "plan_window_start": plan_window_start,
        "billing_mode": billing_mode,
        "synthetic": synthetic,
        "system": system,
        "cohort": cohort,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "config": {
            "cycles": sorted({t.cycle for t in tasks}),
            "suite_tasks": len(tasks),
            "sessions": sessions,
            "max_attempts": max_attempts,
            "budget_usd": budget_usd,
            "stop_at_usd": stop_at_usd,
        },
        "coverage": round(run_ocm / full_ocm, 4) if full_ocm else 0.0,
        "depleted": depleted,
        "depletion_reason": reason,
        "quota_exhausted_task": exhausted_task,
        "tasks": runs,
        "summary": scoring.summarize(runs, suite_tasks=len(tasks), budget_usd=budget_usd,
                                     measured_sessions=measured),
    }
