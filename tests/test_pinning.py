"""Pinned cohort, model verification, subscription depletion and ledger cost."""

import json
import sys
from pathlib import Path

import pytest

from oer import config, report
from oer.adapters import build_adapter
from oer.adapters.base import Adapter, AdapterResult
from oer.adapters.cli import CliAdapter, parse_claude_json
from oer.ledger import apply_ledger_cost
from oer.runner import model_verification, run_suite
from oer.tasks import load_tasks

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed_repo"
TASKS = load_tasks(ROOT / "tasks")


def quiet(*_):
    pass


def test_model_names_normalise():
    assert config.norm_model("claude-sonnet-5.5") == config.norm_model("claude-sonnet-5-5")


def test_unpinned_model_is_refused():
    adapter = build_adapter("custom", command=["true"], model_id="some-other-model")
    with pytest.raises(ValueError, match="pinned cohort"):
        run_suite(adapter, TASKS, TASKS, SEED, progress=quiet)


def test_unpinned_effort_is_refused():
    adapter = build_adapter("custom", command=["true"], effort="high")
    with pytest.raises(ValueError, match="pinned cohort"):
        run_suite(adapter, TASKS, TASKS, SEED, progress=quiet)


def test_defaults_are_the_pinned_cohort():
    d = build_adapter("custom", command=["true"]).describe()
    assert d["model_id"] == config.PINNED["model"] and d["effort"] == "medium"


def test_claude_json_parser_reports_model_and_cost():
    out = json.dumps({"total_cost_usd": 0.05, "is_error": False,
                      "usage": {"input_tokens": 2, "output_tokens": 4},
                      "modelUsage": {"claude-sonnet-5-5": {}}})
    p = parse_claude_json(out)
    assert p["cost_usd"] == 0.05 and p["observed_model"] == "claude-sonnet-5-5" and not p["is_error"]


def test_model_verification_flags_other_models():
    ok = {"observed_models": ["claude-sonnet-5-5"], "all_runs_reported_model": True}
    mixed = {"observed_models": ["claude-sonnet-5-5+claude-haiku-5-5"], "all_runs_reported_model": True}
    silent = {"observed_models": [], "all_runs_reported_model": False}
    assert model_verification([ok])[0] is True
    assert model_verification([ok, mixed])[0] is False
    assert model_verification([silent])[0] is None


def test_copilot_effort_must_match_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    (tmp_path / "settings.json").write_text(json.dumps({"effortLevel": "low"}))
    with pytest.raises(ValueError, match="effortLevel"):
        build_adapter("copilot-cli")
    (tmp_path / "settings.json").write_text(json.dumps({"effortLevel": "medium"}))
    assert build_adapter("copilot-cli").describe()["model_id"] == "claude-sonnet-5.5"


def test_cli_adapter_detects_quota_exhaustion(tmp_path):
    cmd = [sys.executable, "-c", "import sys; print('Usage limit reached'); sys.exit(1)"]
    a = CliAdapter("x", cmd, exhaustion_pattern="usage limit")
    from oer.adapters.base import AdapterRequest
    res = a.run(AdapterRequest(prompt="p", workdir=tmp_path, timeout_s=20, task_id="t", cycle="city"))
    assert res.quota_exhausted is True


class RunsDryAfter(Adapter):
    """Succeeds (no-op) for ``n`` runs, then reports the plan's usage limit."""
    name = "dry"

    def __init__(self, n):
        self.n, self.calls = n, 0

    def describe(self):
        return {"system": "dry", "model": config.PINNED["model"], "model_id": config.PINNED["model"],
                "effort": "medium", "plan": "Test Pro", "version": None}

    def run(self, req):
        self.calls += 1
        if self.calls > self.n:
            return AdapterResult(exit_code=1, quota_exhausted=True)
        return AdapterResult(duration_s=60, cost_usd=0.1, cost_basis="metered",
                             observed_model=config.PINNED["model"])


def test_quota_exhaustion_measures_endurance():
    n = len(TASKS)
    res = run_suite(RunsDryAfter(n + 2), TASKS, TASKS, SEED, sessions=5, progress=quiet)
    assert res["depleted"] and res["depletion_reason"] == "quota"
    assert len(res["tasks"]) == n + 2                  # the cut-off run is not scored
    s = res["summary"]
    assert s["endurance_basis"] == "measured"
    assert s["session_endurance"] == round((n + 2) / n, 1)
    assert res["system"]["model_verified"] is True and res["cohort"]["pinned"] is True


def test_ledger_cost_apportioned_by_wall_time():
    res = run_suite(build_adapter("mock"), TASKS, TASKS, SEED, progress=quiet)
    out = apply_ledger_cost(res, 3.0)
    assert abs(sum(t["cost_usd"] for t in out["tasks"]) - 3.0) < 0.01
    assert {t["cost_basis"] for t in out["tasks"]} == {"ledger_apportioned"}
    assert out["summary"]["total_cost_usd"] == pytest.approx(3.0, abs=0.01)


def test_leaderboard_only_lists_pinned_real_runs():
    pinned = run_suite(RunsDryAfter(10 ** 6), TASKS, TASKS, SEED, progress=quiet)
    assert [r["plan"] for r in report.build_leaderboard([pinned])] == ["Test Pro"]
    unpinned = {**pinned, "cohort": {**pinned["cohort"], "pinned": False}}
    assert report.build_leaderboard([unpinned]) == []
    assert "Test Pro" in report.render_leaderboard_md(report.build_leaderboard([pinned]))
