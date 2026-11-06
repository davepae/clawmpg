# Prompt for GitHub Copilot: understand the OpenClaw Efficiency Rating (OER) project

Paste everything below the line into Copilot Chat (agent mode) with the repository open. You can also save it as `.github/copilot-instructions.md`.

---

You are joining a project called **OpenClaw Efficiency Rating (OER)**. Read this brief, then read the files listed under "Read first" before suggesting or making any change. Do not assume details I have not stated; if something is unclear, ask.

## Goal
An EPA-MPG-style benchmark for AI coding agents. It answers: *how much verified software-engineering work does an agent produce per dollar, per hour, and per human rescue, and how many sessions of work does a subscription allow before its limit is hit?*

## Current scope (important)
The benchmark is pinned to one cohort: **Claude Sonnet 5.5 at medium effort** (`oer/config.py: PINNED`, model id `claude-sonnet-5-5`; Copilot spells it `claude-sonnet-5.5`). It is available on both Claude Pro (driven with Claude Code) and GitHub Copilot Pro (driven with the Copilot CLI). Holding the model fixed means score differences come from the harness and plan, not the model. Runs with another model or effort are refused unless `--allow-unpinned`.

## Core concepts
- **OpenClaw Mile (OCM):** the unit of work. 1 OCM = what a reference engineer completes, verified, in 30 minutes. `OCM(task) = human_minutes / 30`, earned only if hidden tests and structural checks pass (binary).
- **Five cycles** (city, highway, heavy refactor, long context, autonomous feature) with weights 0.25/0.25/0.15/0.15/0.20.
- **Cycle OER (0-100)** = 100 * (0.40 Success + 0.20 Cost + 0.20 Autonomy + 0.10 Speed + 0.10 Quality). Cost and Speed use `eff(x, ref) = 1 if x <= ref else 1/(1+log2(x/ref))` against fixed anchors ($0.75 per OCM, 6 agent-minutes per OCM). Overall OER is the weighted mean over cycles present. Scores are absolute; the leaderboard adds a relative column only.
- **Human Takeover Rate (HTR)** = interventions / attempts. A restart counts 1; a task still failing after the last attempt counts 1; answering a clarification counts 0.
- **Headline metrics:** OCM per dollar, OCM per hour, session cost, **Session Endurance**, estimated monthly cost (40 sessions). A session is one pass over the suite.
- **Endurance** is *measured* when a plan's usage limit stops the agent (the cut-off task is not scored, completed sessions are counted), otherwise *projected* as budget / session cost. Results label which.
- **Cost basis** is recorded per task: metered, ledger_apportioned, manual, synthetic, unknown. Unknown cost zeroes the Cost component; it is never imputed as zero cost.

## Plan facts (read in November 2026; re-verify before relying on them)
- Copilot moved to usage-based billing on June 1, 2026: Pro is $10/month with $10 of AI Credits consumed by token usage at model API rates; no fallback model at exhaustion. The Copilot CLI prints no cost, so cost comes from the usage page via `python -m oer apply-cost` (total is exact, per-task split is by wall time).
- Claude Code reports an API-equivalent `total_cost_usd` and the model(s) used. No numeric Claude Pro limit was found, so depletion is measured, not assumed.

## Layout
```
oer/                  config, scoring, tasks, verify, runner, ledger, report, __main__ (CLI)
oer/adapters/         base, mock, cli (CliAdapter + ManualAdapter), presets.json
tasks/<cycle>/<id>/   task.json, hidden_tests/, solution/ (reference overlay used by the mock agent)
seed_repo/            repository under test (MVP: tiny Python "shop" library, deliberate bugs)
schemas/              result.schema.json
tests/                scoring, suite integrity, pinning/depletion/ledger, mock end-to-end
docs/SPEC.md          full specification (formulas, OCM, architecture, plan accounting, roadmap)
.github/workflows/    ci.yml (tests + mock run + schema), benchmark.yml (manual real-agent run)
```

## How it works
For each task: copy the seed repo to a fresh workdir, call an adapter (agent CLI) with the prompt, then verify on a *copy* where `tests/` is replaced by the task's hidden tests. Hidden tests never enter the agent's workdir. Each task must fail on the untouched seed and pass with its reference solution (enforced by tests). Adapters return cost, time, tokens, interventions, observed model, and whether the plan's quota was exhausted.

## Commands
```
pip install -e ".[dev]" && python -m pytest -q
python -m oer run --adapter mock                         # synthetic, for development
python -m oer run --adapter claude-code                  # needs the claude CLI logged in to Claude Pro
python -m oer run --adapter copilot-cli                  # needs effortLevel "medium" in ~/.copilot/settings.json
python -m oer apply-cost results/RUN.json --total-usd X  # credits read from the Copilot usage page
python -m oer leaderboard results/*.json
```

## What is verified and what is not
- Verified: scoring maths, suite integrity, mock end-to-end, schema, depletion logic and ledger cost (41 tests passing). The `claude-code` adapter was run live on single tasks: flags, metered cost, and model reporting all worked; `ANTHROPIC_API_KEY` is stripped from its environment so runs bill the plan, not the API.
- **Not verified:** the `copilot-cli` adapter has never been run. Unconfirmed: the exact model id string, that `--allow-all-tools --no-ask-user` is sufficient, how the CLI signals usage exhaustion (the regex in presets.json is a guess), and whether it reports the model used. `codex`, `aider`, `cursor-agent` presets are untested and out of scope for the pinned cohort.
- Provisional: the human-time baselines per task are author estimates; the cost/speed anchors are placeholders; the quality score is a crude proxy (compiles + changes stay in task scope); the seed repo is about 100 lines, not the 50-100k LOC target; one run per task is noisy.

## Read first
1. `docs/SPEC.md` (especially sections 2, 3, 6.1, 6.2, 11, 12)
2. `oer/config.py`, `oer/scoring.py`, `oer/runner.py`
3. `oer/adapters/cli.py` and `oer/adapters/presets.json`
4. One task folder, e.g. `tasks/autonomous/autonomous-001/`
5. `tests/test_pinning.py`

## Your first job
1. Summarise the project back to me in under 200 words, naming anything in this brief that the code contradicts.
2. Check the `copilot-cli` preset against the installed Copilot CLI's `--help` and the current GitHub docs. List every flag or assumption that is wrong or unverified. Do not change code yet.
3. Propose, in priority order, the next steps toward a first real Claude Pro vs Copilot Pro comparison (suggested order: verify the Copilot adapter on one task; add model reporting and exhaustion detection for it; build the larger seed repo and more tasks; calibrate human baselines; multi-session statistics).

Rules: keep changes small and tested; never weaken hidden-test isolation; never report a score without its cost basis and coverage; label any synthetic or unverified result as such; do not invent plan limits or prices, cite a source or say you could not verify.
