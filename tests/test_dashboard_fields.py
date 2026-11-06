"""Audit: does a result file carry every field the dashboard views (SPEC 9.1) need?
"""

import json
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


def test_billing_mode_defaults_to_unknown_and_is_recorded(result):
    assert result["billing_mode"] == "unknown"


def test_billing_mode_is_validated_and_shown_in_report():
    from oer import report
    with pytest.raises(ValueError, match="billing_mode"):
        run_suite(build_adapter("mock"), TASKS[:1], TASKS, ROOT / "seed_repo", billing_mode="free", progress=lambda *_: None)
    res = run_suite(build_adapter("mock"), TASKS[:1], TASKS, ROOT / "seed_repo", billing_mode="extra_usage",
                    progress=lambda *_: None)
    assert res["billing_mode"] == "extra_usage"
    assert "EXTRA_USAGE" in report.render_epa(res)


def test_extra_usage_never_yields_measured_endurance():
    class Dry(build_adapter("mock").__class__):
        def run(self, req):
            out = super().run(req)
            out.quota_exhausted = True
            return out
    res = run_suite(Dry(), TASKS, TASKS, ROOT / "seed_repo", billing_mode="extra_usage", progress=lambda *_: None)
    assert res["summary"]["endurance_basis"] != "measured"


def _usage(amount):
    return {"timePeriod": {"year": 2026, "month": 11}, "user": "u", "usageItems": [
        {"product": "copilot", "sku": "s", "model": "claude-sonnet-5.5", "unitType": "ai-credits",
         "pricePerUnit": 0.01, "grossQuantity": amount * 100, "grossAmount": amount, "discountQuantity": 0,
         "discountAmount": 0, "netQuantity": amount * 100, "netAmount": amount}]}


def test_ledger_watch_is_pending_then_settles_and_no_token_leak():
    from oer import billing
    seen = []
    readings = iter([_usage(3.10), _usage(3.10), _usage(3.50)])

    def fake_get(url, token):
        seen.append((url, token))
        return next(readings)

    watch = billing.LedgerWatch("u", "SECRET-TOKEN", http_get=fake_get, sleep=lambda s: None)
    watch.start()
    pending = watch.finish(0.40)
    assert pending["status"] == "pending" and pending["user"] == "u" and len(seen) == 1
    still = billing.settle_check(pending, "SECRET-TOKEN", http_get=fake_get)
    assert still["status"] == "pending"
    check = billing.settle_check(pending, "SECRET-TOKEN", http_get=fake_get)
    assert check["status"] == "match" and check["delta_usd"] == pytest.approx(0.40)
    assert "SECRET-TOKEN" not in json.dumps(check)
    assert "year=" in seen[0][0] and "/users/u/settings/billing/ai_credit/usage" in seen[0][0]
    assert billing.compare(check["before"], check["after"], 0.10)["status"] == "mismatch"


def test_ledger_failure_is_recorded_not_fatal():
    from oer import billing

    def boom(url, token):
        raise billing.LedgerUnavailable("HTTP 403")

    watch = billing.LedgerWatch("u", "t", http_get=boom, sleep=lambda s: None)
    watch.start()
    check = watch.finish(0.1)
    assert check["status"] == "unavailable" and check["errors"] == ["before: HTTP 403"]


def test_ledger_unexpected_shape_and_month_boundary():
    from oer import billing
    with pytest.raises(billing.LedgerUnavailable):
        billing.fetch_snapshot("u", "t", http_get=lambda u, t: {"nope": 1})
    a = {"year": 2026, "month": 10, "gross_amount": 1.0}
    b = {"year": 2026, "month": 11, "gross_amount": 2.0, "settled": True}
    assert billing.compare(a, b, 1.0)["status"] == "unavailable"


def test_run_suite_records_ledger_check_and_validates(tmp_path):
    import jsonschema
    from oer import billing
    readings = iter([_usage(1.0)] * 40)
    watch = billing.LedgerWatch("u", "t", http_get=lambda u, t: next(readings), sleep=lambda s: None)
    res = run_suite(build_adapter("mock"), TASKS[:1], TASKS, ROOT / "seed_repo", ledger_watch=watch,
                    progress=lambda *_: None)
    assert res["ledger_check"]["status"] in ("pending",)
    jsonschema.validate(res, json.loads((ROOT / "schemas" / "result.schema.json").read_text()))


def test_fetch_items_returns_raw_items():
    from oer import billing
    raw = [{"sku": "a", "grossAmount": 1.0}, {"sku": "b", "grossAmount": 2.0}]
    assert billing.fetch_items("u", "tok", http_get=lambda url, tok: {"usageItems": raw}) == raw


def _multi(sonnet55, other):
    return {"usageItems": [
        {"model": "Claude Sonnet 5.5", "grossAmount": sonnet55},
        {"model": "Claude Sonnet 5", "grossAmount": other}]}


def test_ledger_filters_to_pinned_model_and_partial_lag():
    from oer import billing
    readings = iter([_multi(5.00, 2.00), _multi(5.00, 9.00), _multi(5.10, 9.00), _multi(5.40, 9.00)])
    watch = billing.LedgerWatch("u", "t", http_get=lambda u, t: next(readings), model="claude-sonnet-5-5")
    watch.start()
    pending = watch.finish(0.40)
    assert billing.settle_check(pending, "t", http_get=lambda u, t: _multi(5.00, 9.00))["status"] == "pending"
    partial = billing.settle_check(pending, "t", http_get=lambda u, t: _multi(5.10, 9.00))
    assert partial["status"] == "mismatch" and "catching up" in partial["note"]
    check = billing.settle_check(pending, "t", http_get=lambda u, t: _multi(5.40, 9.00))
    assert check["status"] == "match" and check["delta_usd"] == pytest.approx(0.40)
