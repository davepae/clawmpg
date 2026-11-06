"""Audit: does a result file carry every field the dashboard views (SPEC 9.1) need?
"""

import sys
from pathlib import Path

import pytest

from oer.adapters import build_adapter
from oer.runner import run_suite
from oer.tasks import load_tasks

ROOT = Path(__file__).resolve().parent.parent
TASKS = load_tasks(ROOT / "tasks")


@pytest.fixture(scope="module")
def result():
    return run_suite(build_adapter("mock"), TASKS, TASKS, ROOT / "seed_repo", progress=lambda *_: None)


def has(d, dotted):
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return False
        d = d[part]
    return True


PRESENT = [
    "suite_version", "run_id", "started_at", "synthetic", "coverage", "depleted", "depletion_reason",
    "cohort.pinned", "system.system", "system.plan", "system.model_verified", "system.observed_models",
    "summary.overall_oer", "summary.cycles", "summary.human_takeover_rate", "summary.ocm_per_usd",
    "summary.ocm_per_hour", "summary.session_endurance", "summary.endurance_basis",
    "summary.estimated_monthly_cost_usd", "config.sessions", "config.budget_usd",
]


@pytest.mark.parametrize("path", PRESENT)
def test_run_level_field_present(result, path):
    assert has(result, path)


@pytest.mark.parametrize("key", [
    "task_id", "cycle", "session", "ocm_available", "ocm_earned", "passed", "interventions", "cost_usd",
    "cost_basis", "wall_s", "quality", "quota_exhausted", "observed_models", "log_tail",
])
def test_task_level_field_present(result, key):
    assert all(key in t for t in result["tasks"])


def test_run_records_end_time_commit_and_window(result):
    assert result["finished_at"] >= result["started_at"]
    assert "harness_commit" in result  # None outside a git checkout
    assert "plan_window_start" in result  # None unless supplied; never guessed


def test_plan_window_is_recorded_as_given():
    res = run_suite(build_adapter("mock"), TASKS[:1], TASKS, ROOT / "seed_repo",
                    plan_window_start="2026-11-01T00:00:00+00:00", progress=lambda *_: None)
    assert res["plan_window_start"] == "2026-11-01T00:00:00+00:00"


def test_cli_adapter_records_tool_version():
    version = build_adapter("custom", command=[sys.executable, "-c", "pass"]).describe()["version"]
    assert version and "Python" in version


def test_cli_adapter_version_is_none_when_unreadable():
    assert build_adapter("custom", command=["no-such-tool-xyz"]).describe()["version"] is None
