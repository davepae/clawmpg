import math

from oer import config, scoring


def run(cycle="city", ocm=1.0, passed=True, attempts=1, interventions=0, cost=0.5, wall=300, quality=1.0):
    return {
        "task_id": "t", "cycle": cycle, "session": 1, "ocm_available": ocm,
        "ocm_earned": ocm if passed else 0.0, "passed": passed, "attempts": attempts,
        "interventions": interventions, "cost_usd": cost, "wall_s": wall, "quality": quality,
    }


def test_weights_sum_to_one():
    assert math.isclose(sum(config.COMPONENT_WEIGHTS.values()), 1.0)
    assert math.isclose(sum(config.CYCLE_WEIGHTS.values()), 1.0)


def test_ocm_definition():
    assert scoring.ocm_for_minutes(30) == 1.0
    assert scoring.ocm_for_minutes(90) == 3.0


def test_efficiency_score_shape():
    ref = 1.0
    assert scoring.efficiency_score(0.5, ref) == 1.0
    assert scoring.efficiency_score(1.0, ref) == 1.0
    assert math.isclose(scoring.efficiency_score(2.0, ref), 0.5)
    assert scoring.efficiency_score(4.0, ref) < scoring.efficiency_score(2.0, ref)
    assert scoring.efficiency_score(None, ref) == 0.0


def test_perfect_cycle_scores_100():
    s = scoring.cycle_score([run(cost=0.1, wall=60)])
    assert s["oer"] == 100.0


def test_all_failures_score_low_and_bounded():
    s = scoring.cycle_score([run(passed=False, interventions=1)])
    assert s["components"]["success"] == 0.0
    assert s["components"]["autonomy"] == 0.0
    assert 0.0 <= s["oer"] <= 100.0
    assert s["oer"] == 0.0


def test_unknown_cost_zeroes_cost_component():
    s = scoring.cycle_score([run(cost=None)])
    assert s["components"]["cost"] == 0.0
    assert s["cost_usd"] is None


def test_more_cost_lowers_score():
    cheap = scoring.cycle_score([run(cost=0.2)])["oer"]
    pricey = scoring.cycle_score([run(cost=5.0)])["oer"]
    assert pricey < cheap


def test_overall_renormalises_over_present_cycles():
    summary = scoring.summarize([run("city", cost=0.1, wall=60)], suite_tasks=1, budget_usd=20)
    assert summary["overall_oer"] == 100.0


def test_headline_metrics():
    runs = [run(ocm=2.0, cost=1.0, wall=1800), run(ocm=1.0, passed=False, interventions=1, cost=1.0, wall=1800)]
    s = scoring.summarize(runs, suite_tasks=2, budget_usd=20)
    assert s["human_takeover_rate"] == 0.5
    assert math.isclose(s["ocm_per_usd"], 1.0)           # 2 OCM earned / $2
    assert math.isclose(s["ocm_per_hour"], 2.0)          # 2 OCM / 1 hour
    assert math.isclose(s["session_endurance"], 10.0)    # $20 / $2 per session
    assert math.isclose(s["estimated_monthly_cost_usd"], 2.0 * config.STANDARD_MONTH_SESSIONS)


def test_relative_score():
    assert scoring.relative_score(50, 100) == 50.0
    assert scoring.relative_score(10, 0) == 0.0
