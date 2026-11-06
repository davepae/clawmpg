"""EPA-style report and leaderboard rendering."""

from __future__ import annotations

import json
from pathlib import Path

from oer import config, scoring


def _n(value, fmt="{:.0f}", default="n/a"):
    return default if value is None else fmt.format(value)


def render_epa(result: dict) -> str:
    s = result["summary"]
    sysd = result["system"]
    name = sysd["system"]
    detail = " / ".join(x for x in (sysd.get("plan"), sysd.get("model_id"),
                                    f"{sysd['effort']} effort" if sysd.get("effort") else None) if x)
    if detail:
        name += f" ({detail})"
    lines = ["OPENCLAW EFFICIENCY RATING",
             f"Suite v{result['suite_version']}  |  run {result['run_id']}  |  {result['started_at']}"]
    if result["synthetic"]:
        lines.append("*** SYNTHETIC RUN: NOT A RATING ***")
    if result["coverage"] < 1.0:
        lines.append(f"*** PARTIAL COVERAGE ({result['coverage']:.0%}): NOT AN OFFICIAL RATING ***")
    if not result.get("synthetic") and not result.get("cohort", {}).get("pinned", False):
        lines.append("*** NOT THE PINNED COHORT: EXPLORATORY, NOT RANKABLE ***")
    if sysd.get("model_verified") is False:
        lines.append(f"*** TOOL REPORTED OTHER MODELS: {', '.join(sysd.get('observed_models', []))} ***")
    elif sysd.get("model_verified") is None and not result.get("synthetic"):
        lines.append("*** MODEL NOT REPORTED BY TOOL: PIN IS DECLARED, NOT VERIFIED ***")
    mode = result.get("billing_mode", "unknown")
    if mode in ("extra_usage", "api"):
        lines.append(f"*** BILLING MODE {mode.upper()}: NOT A PLAN-ALLOWANCE MEASUREMENT; ENDURANCE IS PROJECTED ***")
    elif mode == "unknown" and not result.get("synthetic"):
        lines.append("*** BILLING MODE NOT STATED: DO NOT READ COST AS PLAN USAGE ***")
    if s["total_cost_usd"] is None:
        lines.append("*** COST UNKNOWN FOR AT LEAST ONE TASK: COST SCORES ARE 0 ***")
    lc = result.get("ledger_check")
    if lc:
        if lc["status"] in ("match", "mismatch"):
            lines.append(f"Ledger cross-check ({lc['source']}): {lc['status'].upper()}: ledger moved "
                         f"${lc['delta_usd']:.4f} vs tool-reported ${lc['reported_usd']:.4f} (account-wide)")
        else:
            lines.append(f"Ledger cross-check: {lc['status']}")
    lines += ["", "System:", f"  {name}", "", f"Overall OER: {s['overall_oer']:.0f}", ""]
    for c in config.CYCLES:
        cs = s["cycles"].get(c)
        lines.append(f"{config.CYCLE_NAMES[c]}: {_n(cs['oer']) if cs else 'n/a'}")
    lines += [
        "",
        f"Human Takeover Rate: {_n(None if s['human_takeover_rate'] is None else s['human_takeover_rate'] * 100, '{:.0f}%')}",
        "",
        "Productivity:",
        f"  {_n(s['ocm_per_usd'], '{:.1f}')} OCM/$",
        f"  {_n(s['ocm_per_hour'], '{:.1f}')} OCM/hour",
        "",
        "Session Endurance:",
        f"  {_n(s['session_endurance'], '{:.1f}')} OpenClaw Sessions "
        + ("(measured: plan usage limit reached)" if s.get("endurance_basis") == "measured"
           else f"(projected on a ${s['budget_usd']:.0f} budget)"),
        "",
        "Estimated Monthly Cost:",
        f"  {_n(s['estimated_monthly_cost_usd'], '${:.0f}')}  ({config.STANDARD_MONTH_SESSIONS} sessions)",
    ]
    return "\n".join(lines)


def load_results(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        if isinstance(data, dict) and "summary" in data:
            out.append(data)
    return out


def build_leaderboard(results: list[dict], include_synthetic: bool = False,
                      require_full_coverage: bool = True) -> list[dict]:
    """Best run per (system, model), ranked by overall OER."""
    best: dict[tuple, dict] = {}
    for r in results:
        if r["synthetic"] and not include_synthetic:
            continue
        if require_full_coverage and r["coverage"] < 1.0:
            continue
        if not include_synthetic and not r.get("cohort", {}).get("pinned", False):
            continue
        key = (r["system"]["system"], r["system"].get("plan"), r["system"].get("model_id"),
               r["system"].get("effort"))
        if key not in best or r["summary"]["overall_oer"] > best[key]["summary"]["overall_oer"]:
            best[key] = r
    ranked = sorted(best.values(), key=lambda r: r["summary"]["overall_oer"], reverse=True)
    top = ranked[0]["summary"]["overall_oer"] if ranked else 0.0
    rows = []
    for i, r in enumerate(ranked, 1):
        s = r["summary"]
        row = {
            "rank": i,
            "system": r["system"]["system"],
            "plan": r["system"].get("plan"),
            "model": r["system"].get("model_id"),
            "effort": r["system"].get("effort"),
            "model_verified": r["system"].get("model_verified"),
            "endurance_basis": r["summary"].get("endurance_basis"),
            "suite_version": r["suite_version"],
            "overall_oer": s["overall_oer"],
            "relative_oer": scoring.relative_score(s["overall_oer"], top),
            "cycles": {c: s["cycles"][c]["oer"] for c in s["cycles"]},
            "human_takeover_rate": s["human_takeover_rate"],
            "ocm_per_usd": s["ocm_per_usd"],
            "session_endurance": s["session_endurance"],
            "estimated_monthly_cost_usd": s["estimated_monthly_cost_usd"],
            "synthetic": r["synthetic"],
            "run_id": r["run_id"],
        }
        rows.append(row)
    return rows


def render_leaderboard_md(rows: list[dict]) -> str:
    head = ("| Rank | System / plan | Model @ effort | OER | OER-rel | City | Hwy | Heavy | LongCtx | Auto | HTR | OCM/$ | Sessions | $/mo |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines = ["# OpenClaw Efficiency Rating leaderboard", "",
             "OER is absolute (fixed reference anchors). OER-rel rescales so the best listed system is 100.", "", head]
    for r in rows:
        c = r["cycles"]
        htr = "n/a" if r["human_takeover_rate"] is None else f"{r['human_takeover_rate'] * 100:.0f}%"
        lines.append(
            f"| {r['rank']} | {r['system']}{' / ' + r['plan'] if r.get('plan') else ''}{' *(synthetic)*' if r['synthetic'] else ''} | "
            f"{r['model'] or '-'}{' @ ' + r['effort'] if r.get('effort') else ''}{'' if r.get('model_verified') else ' (unverified)'} | "
            f"{r['overall_oer']:.0f} | {r['relative_oer']:.0f} | "
            + " | ".join(_n(c.get(k)) for k in config.CYCLES)
            + f" | {htr} | {_n(r['ocm_per_usd'], '{:.1f}')} | {_n(r['session_endurance'])}{' (measured)' if r.get('endurance_basis') == 'measured' else ''} | "
            f"{_n(r['estimated_monthly_cost_usd'], '${:.0f}')} |")
    if not rows:
        lines.append("| - | no eligible results | | | | | | | | | | | | |")
    return "\n".join(lines) + "\n"
