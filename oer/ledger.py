"""Post-hoc cost from the plan's own usage ledger.

Some tools (GitHub Copilot CLI) print no cost or token usage. For those, read the credits
consumed over the whole run from the provider's usage page (before/after the run), then
apportion the total across task runs by agent wall-clock time and recompute the scores.

Apportioning is an approximation: it assumes cost accrues in proportion to time. It is
labelled ``ledger_apportioned`` and the total itself is exact. Prefer a metered adapter when
one exists, and run the suite with nothing else using the account so the ledger delta is clean.
"""

from __future__ import annotations

from oer import scoring


def apply_ledger_cost(result: dict, total_usd: float) -> dict:
    tasks = result["tasks"]
    if not tasks:
        raise ValueError("result has no task runs")
    wall = sum(t["wall_s"] for t in tasks)
    for t in tasks:
        share = t["wall_s"] / wall if wall else 1 / len(tasks)
        t["cost_usd"] = round(total_usd * share, 4)
        t["cost_basis"] = "ledger_apportioned"

    cfg = result["config"]
    suite_tasks = cfg.get("suite_tasks") or len(tasks)
    measured = None
    if result.get("depletion_reason") == "quota":
        measured = len(tasks) / suite_tasks
    result["summary"] = scoring.summarize(tasks, suite_tasks=suite_tasks, budget_usd=cfg["budget_usd"],
                                          measured_sessions=measured)
    result["ledger_total_usd"] = round(total_usd, 4)
    return result
