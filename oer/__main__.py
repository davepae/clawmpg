"""Command line: python -m oer {run,apply-cost,report,leaderboard,validate}"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime
from pathlib import Path

from oer import config, report
from oer.ledger import apply_ledger_cost
from oer import billing
from oer.adapters import build_adapter
from oer.runner import run_suite
from oer.tasks import load_tasks

ROOT = Path(__file__).resolve().parent.parent


def cmd_run(a: argparse.Namespace) -> int:
    command = shlex.split(a.command) if a.command else None
    try:
        adapter = build_adapter(a.adapter, model_id=a.model_id, effort=a.effort, plan=a.plan, command=command,
                                cost_per_run=a.cost_per_run, mock_skill=a.mock_skill, mock_seed=a.mock_seed)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.plan_window_start:
        try:
            datetime.fromisoformat(a.plan_window_start)
        except ValueError:
            print(f"error: --plan-window-start must be an ISO timestamp, got {a.plan_window_start!r}", file=sys.stderr)
            return 2
    watch = None
    if a.ledger_user:
        token = billing.token_from_env()
        if not token:
            print(f"error: --ledger-user needs a fine-grained token with the 'Plan' user permission (read) "
                  f"in ${billing.TOKEN_ENV}", file=sys.stderr)
            return 2
        watch = billing.LedgerWatch(a.ledger_user, token)
    all_tasks = load_tasks(Path(a.tasks))
    cycles = a.cycles.split(",") if a.cycles else None
    ids = a.ids.split(",") if a.ids else None
    tasks = load_tasks(Path(a.tasks), cycles=cycles, ids=ids)
    if not tasks:
        print("no tasks selected", file=sys.stderr)
        return 2
    try:
        result = run_suite(adapter, tasks, all_tasks, Path(a.seed_repo), sessions=a.sessions,
                           max_attempts=a.attempts, budget_usd=a.budget_usd, stop_at_usd=a.stop_at_usd,
                           allow_unpinned=a.allow_unpinned, plan_window_start=a.plan_window_start,
                           billing_mode=a.billing_mode, ledger_watch=watch)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else ROOT / "results" / f"{result['run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print()
    print(report.render_epa(result))
    print(f"\nresult written to {out}")
    return 0


def cmd_ledger_snapshot(a: argparse.Namespace) -> int:
    token = billing.token_from_env()
    if not token:
        print(f"error: set ${billing.TOKEN_ENV} to a fine-grained token with the 'Plan' user permission (read)",
              file=sys.stderr)
        return 2
    try:
        print(json.dumps(billing.fetch_snapshot(a.user, token), indent=2))
    except billing.LedgerUnavailable as e:
        print(f"ledger unavailable: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_apply_cost(a: argparse.Namespace) -> int:
    path = Path(a.result)
    result = apply_ledger_cost(json.loads(path.read_text()), a.total_usd)
    out = Path(a.out) if a.out else path
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(report.render_epa(result))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    print(report.render_epa(json.loads(Path(a.result).read_text())))
    return 0


def cmd_leaderboard(a: argparse.Namespace) -> int:
    results = report.load_results([Path(p) for p in a.results])
    rows = report.build_leaderboard(results, include_synthetic=a.include_synthetic,
                                    require_full_coverage=not a.allow_partial)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.json").write_text(json.dumps(rows, indent=2) + "\n")
    md = report.render_leaderboard_md(rows)
    (out / "LEADERBOARD.md").write_text(md)
    print(md)
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    try:
        import jsonschema
    except ImportError:
        print("pip install jsonschema to validate", file=sys.stderr)
        return 2
    schema = json.loads((ROOT / "schemas" / "result.schema.json").read_text())
    bad = 0
    for p in a.results:
        try:
            jsonschema.validate(json.loads(Path(p).read_text()), schema)
            print(f"ok   {p}")
        except jsonschema.ValidationError as e:
            bad += 1
            print(f"FAIL {p}: {e.message}")
    return 1 if bad else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="oer", description="OpenClaw Efficiency Rating")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the benchmark against an adapter")
    r.add_argument("--adapter", required=True, help="mock | manual | custom | claude-code | codex | aider | cursor-agent | copilot-cli")
    r.add_argument("--model-id", help=f"model id passed to the tool (default: pinned {config.PINNED['model']})")
    r.add_argument("--effort", help=f"reasoning effort (default: pinned {config.PINNED['effort']})")
    r.add_argument("--plan", help="subscription plan label, e.g. 'Claude Pro' or 'Copilot Pro'")
    r.add_argument("--plan-window-start", help="ISO time the plan's usage window/billing period began "
                   "(for depletion runs; recorded as given, never guessed)")
    r.add_argument("--billing-mode", choices=config.BILLING_MODES, default="unknown",
                   help="what the cost was billed against: plan_allowance, extra_usage (pay-as-you-go past the "
                        "plan's limit), api, or unknown (default; never guessed)")
    r.add_argument("--ledger-user", help="GitHub username: cross-check reported cost against GitHub's AI-credit "
                   f"usage API before/after the run (token in ${billing.TOKEN_ENV}; never written to results)")
    r.add_argument("--allow-unpinned", action="store_true", help="exploratory run with a different model/effort")
    r.add_argument("--command", help="custom adapter command with {prompt}/{workdir}/{model} placeholders")
    r.add_argument("--cost-per-run", type=float, help="fallback USD per agent run when the tool reports no cost")
    r.add_argument("--tasks", default=str(ROOT / "tasks"))
    r.add_argument("--seed-repo", default=str(ROOT / "seed_repo"))
    r.add_argument("--cycles", help=f"comma list from {','.join(config.CYCLES)}")
    r.add_argument("--ids", help="comma list of task ids")
    r.add_argument("--attempts", type=int, default=1, help="max agent attempts per task (default 1)")
    r.add_argument("--sessions", type=int, default=1, help="passes over the suite")
    r.add_argument("--budget-usd", type=float, default=config.DEFAULT_BUDGET_USD, help="budget used for endurance")
    r.add_argument("--stop-at-usd", type=float, help="stop launching tasks once this much is spent")
    r.add_argument("--mock-skill", type=float, default=1.0)
    r.add_argument("--mock-seed", default="0")
    r.add_argument("--out")
    r.set_defaults(fn=cmd_run)

    ls = sub.add_parser("ledger-snapshot", help="print this month's AI-credit usage totals (checks the token works)")
    ls.add_argument("--user", required=True)
    ls.set_defaults(fn=cmd_ledger_snapshot)

    ac = sub.add_parser("apply-cost", help="set cost from the plan's usage ledger (tools with no cost output)")
    ac.add_argument("result")
    ac.add_argument("--total-usd", type=float, required=True, help="credits/dollars consumed over the whole run")
    ac.add_argument("--out")
    ac.set_defaults(fn=cmd_apply_cost)

    rp = sub.add_parser("report", help="print the EPA-style report for a result file")
    rp.add_argument("result")
    rp.set_defaults(fn=cmd_report)

    lb = sub.add_parser("leaderboard", help="build the leaderboard from result files")
    lb.add_argument("results", nargs="+")
    lb.add_argument("--out-dir", default=str(ROOT / "leaderboard"))
    lb.add_argument("--include-synthetic", action="store_true")
    lb.add_argument("--allow-partial", action="store_true")
    lb.set_defaults(fn=cmd_leaderboard)

    v = sub.add_parser("validate", help="validate result files against the JSON schema")
    v.add_argument("results", nargs="+")
    v.set_defaults(fn=cmd_validate)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
