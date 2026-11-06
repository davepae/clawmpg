"""Suite integrity and end-to-end checks using the mock adapter."""

import json
from pathlib import Path

import pytest

from oer import report
from oer.adapters import build_adapter
from oer.adapters.base import AdapterRequest
from oer.runner import run_suite
from oer.tasks import load_tasks
from oer.verify import copy_tree, snapshot, verify

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed_repo"
TASKS = load_tasks(ROOT / "tasks")


def test_every_cycle_has_a_task():
    assert {t.cycle for t in TASKS} == {"city", "highway", "heavy", "longctx", "autonomous"}


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_seed_fails_each_task(task, tmp_path):
    """A task that the untouched seed already passes measures nothing."""
    work = tmp_path / "repo"
    copy_tree(SEED, work)
    out = verify(work, task, snapshot(work))
    assert not out["passed"], f"{task.id} passes without any work"


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_reference_solution_passes_each_task(task, tmp_path):
    """Every task must be solvable, otherwise a 0 score would be the task's fault."""
    work = tmp_path / "repo"
    copy_tree(SEED, work)
    baseline = snapshot(work)
    build_adapter("mock", mock_skill=1.0).run(AdapterRequest(
        prompt=task.prompt, workdir=work, timeout_s=10, task_id=task.id, cycle=task.cycle,
        solution_dir=task.solution_dir, solution_deletes=task.solution_deletes))
    out = verify(work, task, baseline)
    assert out["passed"], out["log_tail"] + str(out["check_failures"])
    assert out["quality"] == 1.0


def _run(skill, **kw):
    return run_suite(build_adapter("mock", mock_skill=skill), TASKS, TASKS, SEED,
                     progress=lambda *_: None, **kw)


def test_perfect_agent_end_to_end():
    res = _run(1.0)
    s = res["summary"]
    assert res["synthetic"] is True
    assert res["coverage"] == 1.0
    assert all(t["passed"] for t in res["tasks"])
    assert s["human_takeover_rate"] == 0.0
    assert s["overall_oer"] > 90
    assert abs(s["ocm_earned"] - sum(t.ocm for t in TASKS)) < 1e-3  # per-task OCM stored to 4 dp


def test_useless_agent_scores_zero():
    res = _run(0.0)
    s = res["summary"]
    assert not any(t["passed"] for t in res["tasks"])
    assert s["overall_oer"] == 0.0
    assert s["human_takeover_rate"] == 1.0


def test_retries_count_as_interventions():
    res = _run(0.0, max_attempts=2)
    t = res["tasks"][0]
    assert t["attempts"] == 2 and t["interventions"] == 2  # restart + takeover


def test_stop_at_budget_marks_depleted():
    res = _run(1.0, sessions=5, stop_at_usd=1.0)
    assert res["depleted"] is True
    assert len(res["tasks"]) < 5 * len(TASKS)


def test_result_schema_and_leaderboard(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    res = _run(1.0)
    schema = json.loads((ROOT / "schemas" / "result.schema.json").read_text())
    jsonschema.validate(res, schema)

    assert report.build_leaderboard([res]) == []                       # synthetic hidden by default
    rows = report.build_leaderboard([res], include_synthetic=True)
    assert rows[0]["relative_oer"] == 100.0
    assert "OPENCLAW EFFICIENCY RATING" in report.render_epa(res)
    assert "SYNTHETIC" in report.render_epa(res)
