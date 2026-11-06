# OpenClaw Efficiency Rating (OER) - Specification v0.1.0

> How much useful software engineering work can an AI coding system perform for a given budget?

OER is to coding agents what MPG is to cars: a fixed, repeatable workload, run to a fixed protocol, reported as work per unit of resource. Token counts and context-window sizes are fuel-tank sizes; OER measures miles.

Status: **draft with a runnable MVP**. Sections 11 and 12 list what is provisional.

---

## 1. Principles

1. **Work is verified, not self-reported.** Work counts only if hidden tests (and structural checks) pass.
2. **Absolute scores.** Fixed, versioned reference anchors, so a score today is comparable to one next year. A relative "best system = 100" column is derived on the leaderboard only.
3. **Cost is real money.** Every result states how cost was measured (`cost_basis`).
4. **Humans are a metered input.** Interventions are counted (Human Takeover Rate).
5. **Vendor-neutral.** One adapter interface; the harness never looks inside the agent.
6. **Honest labelling.** Synthetic, partial-coverage and cost-unknown runs are marked and excluded from the leaderboard.

## 2. Definitions

| Term | Definition |
|---|---|
| Task | A prompt, a seed repository state, hidden tests, optional structural checks, a calibrated human baseline `H` (minutes), a timeout. |
| Attempt | One invocation of the agent on a fresh copy of the seed repo. |
| Session | One pass over the selected tasks (the "standard session" is the full suite). |
| Cycle | A task family: city, highway, heavy, longctx, autonomous. |

### 2.1 OpenClaw Mile (OCM)

```
1 OCM = the work a reference engineer completes, to a verified standard, in 30 minutes.

OCM(task) = H_task / 30                     (H_task = calibrated human baseline, minutes)
OCM earned = OCM(task) if the task passes verification, else 0     (binary gate)
```

Why this is defensible:
- **Common unit.** A bug fix, a refactor and a feature all convert through the same quantity, human effort, which is what an engineering buyer pays for.
- **Calibration, not opinion.** `H_task` is the **median of at least 3 engineers** (not the task author) working in the same repo without AI assistance, to the same hidden tests. Tasks whose human times differ by more than 2x are rewritten or dropped.
- **Verified.** Earned OCM requires the hidden tests to pass, so wrong-but-plausible output earns 0.
- **Additive and scale-free.** OCM sums across tasks; OCM/$ and OCM/hour are simple ratios.

Binary gating is deliberate for v0.1: partial credit invites gaming by padding easy sub-tests. A later version may add graded credit from per-test weights.

**v0.1.0 caveat:** the 7 MVP tasks carry *author estimates* of `H`, not calibrated medians. Treat MVP OCM values as provisional.

### 2.2 Cycles

| Cycle | EPA analogue | Workload | Cycle weight |
|---|---|---|---|
| `city` | city driving | single-file or few-file fixes: failing test, rename, logging, small change | 0.25 |
| `highway` | highway | medium feature, 10-20 files, tests, PR | 0.25 |
| `heavy` | towing | cross-cutting refactor, subsystem rename, data-model migration, API version bump | 0.15 |
| `longctx` | mountain pass | whole-repo analysis, architecture map, distributed bug trace + fix | 0.15 |
| `autonomous` | highest-value | open-ended feature: investigate, design, code, test, debug, document, no human help | 0.20 |

Cycle weights are renormalised over the cycles actually run.

## 3. Scoring

Per cycle, over that cycle's task runs:

```
Success   = OCM earned / OCM available
Cost      = eff(cost_usd / OCM earned,      REF_COST  = $0.75 per OCM)
Autonomy  = 1 - min(1, interventions / attempts)
Speed     = eff(agent minutes / OCM earned, REF_SPEED = 6 min per OCM)
Quality   = OCM-weighted mean of per-task quality (passed tasks only)

eff(x, ref) = 1                       if x <= ref
            = 1 / (1 + log2(x / ref)) otherwise          (x unknown, or no work done -> 0)

Cycle OER = 100 * (0.40*Success + 0.20*Cost + 0.20*Autonomy + 0.10*Speed + 0.10*Quality)
Overall OER = sum(cycle_weight * Cycle OER) / sum(cycle_weight over cycles present)
```

`eff` is 1.0 at the anchor, 0.5 at 2x the anchor, 0.33 at 4x: smooth, bounded, scale-free, and it never rewards being 100x cheaper by more than the anchor (so a free-but-useless system cannot win; Success carries 40%).

Quality (v0.1.0): `0.5 * (code compiles) + 0.5 * (share of changed files inside the task's declared scope)`. This is crude and should be replaced by lint/complexity/review-rubric scoring (see 12).

Anchors and weights live in `oer/config.py` and are frozen per suite version.

## 4. Human Takeover Rate (HTR)

```
HTR = human interventions / agent attempts
```

| Event | Interventions |
|---|---|
| Answering a clarification question | 0 |
| Manually editing code during the run | 1 each |
| Restarting the agent after a failed attempt | 1 |
| Task still failing after the last attempt (a human must fix it) | 1 |

Automated runs default to `--attempts 1`, so HTR is then the task failure rate; use `--attempts 2+` to separate "needed a retry" from "needed a rescue". The Manual adapter records interventions you report.

## 5. Headline metrics

| Metric | Definition |
|---|---|
| Productivity per dollar | `OCM earned / total cost` |
| Productivity per hour | `OCM earned / agent wall-clock hours` |
| Session cost | `total cost / sessions run` (failures included: you pay for them) |
| Session Endurance | `budget / session cost` - sessions of the full suite before the budget runs out (projected; `--stop-at-usd` measures depletion directly) |
| Estimated monthly cost | `session cost * 40` (standard month = 40 sessions) |

## 6. Cost accounting

`cost_basis` is one of: `metered` (the tool reported dollars), `token_estimate` (tokens x published price), `quota_fraction` (share of a subscription allowance converted to dollars), `manual` (user-entered), `ledger_apportioned` (total read from the plan's usage page, split by wall time; see 6.2), `synthetic`, `unknown`.

Rules: subscription tools are priced at their **API-equivalent** or documented quota value, stated in the result. Unknown cost is never imputed as zero; it zeroes the Cost component and the report says so. Ratings should only be compared within a `cost_basis` class, or with the basis shown next to the score.

### 6.1 Pinned cohort: Claude Sonnet 5.5 at medium effort

v0.1 rates **one model at one effort**: `claude-sonnet-5-5`, `medium` (`oer/config.py: PINNED`), because Sonnet 5.5 is available through both the Claude Pro and GitHub Copilot Pro subscriptions. Holding the model fixed means score differences come from the **harness and plan** (prompting, tool loop, context handling, tokens burned per task, quota accounting), not from model quality.

- The runner refuses a non-pinned model or effort unless `--allow-unpinned` is passed; such runs are labelled exploratory and kept off the leaderboard.
- **Declared vs verified.** Each result records the model the tool itself reported (`observed_models`). `model_verified` is true only if every run reported exactly the pinned model, false if anything else appeared (for example a smaller model used for background work), null if the tool never says. Claude Code reports this; the Copilot CLI is documented to show the model only in its non-silent output, so its pin is declared, not verified, until a parser is written. (Update 2026-11-06: one live run shows the Copilot CLI's JSON output (`--output-format json`) does report the model and effort, and the `copilot_jsonl` parser now extracts the model. Based on a single run.)
- **Effort.** Claude Code takes `--effort medium` on the command line. The Copilot CLI 1.0.105 has `--reasoning-effort <level>` (confirmed in `copilot --help`), which the preset now passes. An earlier draft relied on an `effortLevel` key in `~/.copilot/settings.json`, which I could not find in that CLI's config help; the `settings` effort mode remains in the code but no preset uses it.
- Model ids differ per vendor (`claude-sonnet-5-5` vs `claude-sonnet-5.5`); they are normalised for comparison.

### 6.2 Subscription plans: what "depletion" means

| | Claude Code on Claude Pro | Copilot CLI on Copilot Pro |
|---|---|---|
| What runs out | a usage allowance; this project has not found a published numeric limit, so it is **measured, not assumed** | monthly AI Credits (Copilot moved to usage-based billing on June 1, 2026; 1 credit = $0.01; tokens are priced at model rates. GitHub's [billing page](https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing) (read 2026-11-06) lists Pro as $10/month with 1,000 base credits plus a 500-credit *flex allotment* (1,500 total, variable by design), reset 00:00 UTC on the 1st. Earlier drafts said "$10 of credits"; the budget used for projections must state which figure it assumes) |
| Cost signal | `total_cost_usd` in the JSON output: an **API-equivalent** price, not what the plan charges | the CLI's JSON output ends with a usage checkpoint (`totalNanoAiu` = credits x 1e9; 1 credit = $0.01) which the parser turns into cost (`metered`). **Unreconciled:** on the first live run (`city-001`) the CLI reported 8.06 credits ($0.081) while the usage page rose $0.32; other account activity may explain it. Until reconciled over a clean multi-task run, cross-check with the usage page and `oer apply-cost` |
| Endurance | measured: the run continues session after session until the plan's limit stops the agent, and the number of full sessions completed is reported (`endurance_basis: measured`) | measured the same way if the CLI reports exhaustion, otherwise projected as `$10 / session cost` |

Rules:
- **Measured beats projected.** When the plan's own limit stops the agent (`quota_exhausted`), that partial task is *not scored* (it says something about the plan, not the agent) and endurance is the count of completed sessions. Otherwise endurance is projected as `budget / session cost` and labelled so. For Claude Pro the dollar budget is only an API-equivalent yardstick, so treat its projection as indicative.
- **Ledger costs.** `python -m oer apply-cost result.json --total-usd X` spreads the credits consumed across tasks by agent wall-clock time. The total is exact; the per-task split is an approximation. Run it with nothing else using the account.
- **Ledger cross-check (Copilot).** `oer run --ledger-user USER` reads GitHub's AI-credit usage API (`GET /users/{username}/settings/billing/ai_credit/usage`, [REST docs](https://docs.github.com/en/rest/billing/usage)) before and after the run and records `ledger_check` (`match` | `mismatch` | `unavailable` | `no_reported_cost`) against the tool-reported cost. The token (fine-grained, user permission \"Plan\" read) comes from `$OER_GITHUB_BILLING_TOKEN` and is never written to results or errors. It is account-wide and month-level, so other Copilot use during the run shows up as a mismatch; it is informational and never changes the recorded cost. Response parsing follows GitHub's published OpenAPI schema and has **not been observed live**: run `python -m oer ledger-snapshot --user USER` once to confirm. No equivalent exists for Claude Pro that this project could verify.
- **Billing mode.** Each result records `billing_mode` (`--billing-mode`): `plan_allowance`, `extra_usage` (pay-as-you-go past a plan limit), `api`, or `unknown` (default, never guessed). Only `plan_allowance` runs say how far a subscription goes. `extra_usage` and `api` runs compare harnesses only; the report shows a banner, endurance stays projected, and the dashboard badges them. On 2026-11-06 the two full Claude Code runs were made after the Claude Pro weekly limit had been reached, so they are `extra_usage` (or unknown) runs, not plan-allowance measurements; the account's remaining-balance figure did not change across those runs, so what they were actually billed is **unverified**.
- **Resets and windows.** Plans reset on their own schedule (Copilot monthly counters, Claude rolling windows). Record the start time of a depletion run and do not span a reset.
- Sources for plan terms were read in November 2026 and will change; re-check before publishing a rating.

## 7. Benchmark repository (target design)

The MVP ships a 6-module, ~100-line seed (`seed_repo/`) so the harness can be exercised anywhere. The production benchmark repo ("`openclaw-bench-repo`") should be:

| Property | Target |
|---|---|
| Size | 50k-100k LOC, ~600-1000 files |
| Languages | Python backend (~40%), TypeScript services (~25%), React frontend (~25%), SQL migrations/queries (~10%) |
| Shape | Realistic order/inventory/billing platform: API layer, domain services, ORM + raw SQL, React admin UI, background jobs |
| Tests | Unit (fast), integration (DB in a container), a few UI tests; CI definition included |
| Debt | Legacy modules with inconsistent naming, dead code, duplicated logic, a deprecated v1 API still in use |
| Seeded defects | 30-60 catalogued bugs (off-by-one, unit mismatch, race, wrong join, stale cache) each with a failing hidden test |
| Docs | README, partial and partly stale architecture notes (so navigation matters) |

Construction: generate a clean, well-tested codebase, then derive each task commit by *injecting* a defect or *removing* a feature, so every task has a known-good solution and hidden tests by construction (the MVP reference `solution/` overlays work this way).

Integrity rules:
- Hidden tests live outside the agent's workdir and replace `tests/` only in a verification copy.
- A **private, rotating held-out task set** (about 30%) is used for official ratings; public tasks are for development. This limits training-data contamination.
- Each task must fail on the unmodified seed and pass with its reference solution (enforced by `tests/test_suite.py`).
- Run agents in a container with no access to the harness or task directories and with network policy declared in the result.

## 8. Harness architecture

```
                 +----------------------------- oer run ------------------------------+
tasks/*.json --> | Runner                                                              |
seed_repo/   --> |  for session, task:                                                 |
                 |    1. fresh workdir = copy(seed_repo); baseline = hash(files)        |
                 |    2. Adapter.run(prompt, workdir, timeout) --> cost, time, tokens,  |
                 |          interventions        (agent CLI / mock / manual)            |
                 |    3. Verifier: copy workdir, swap tests/ for hidden_tests/, pytest, |
                 |          structural checks, compile + scope -> passed, quality      |
                 |    4. retry (counts as intervention) or record task run             |
                 |  scoring.summarize(runs) --> cycle OER, overall, HTR, OCM/$, ...     |
                 +----------------------------------+----------------------------------+
                                                    v
                              results/<run>.json  (schemas/result.schema.json)
                                                    v
                    oer report  (EPA text)      oer leaderboard  (LEADERBOARD.md + .json)
```

**Adapter contract** (`oer/adapters/base.py`): take `{prompt, workdir, timeout_s}`, edit files in `workdir`, return `{exit_code, duration_s, cost_usd, cost_basis, tokens, interventions, timed_out}`.

| Adapter | How | Status |
|---|---|---|
| `mock` | overlays the reference solution with probability `skill`; synthetic cost/time | tested, CI |
| `claude-code` | `claude -p ... --model claude-sonnet-5-5 --effort medium --output-format json`, parses cost, tokens and model | live-tested on 1 task |
| `copilot-cli` | `copilot -p ... --allow-all-tools --no-ask-user --model=claude-sonnet-5.5 --reasoning-effort medium --trust-folder --output-format json`; cost via `apply-cost` | flags checked against `copilot --help` v1.0.105, **never run end to end**; model reporting, cost output and the exhaustion message are unconfirmed. Set `OER_RAW_LOG_DIR` to save full agent output while investigating |
| `codex`, `aider`, `cursor-agent` | `CliAdapter` presets; out of scope while the cohort is pinned to Sonnet 5.5 | **untested** presets |
| `custom` | any command with `{prompt}` `{workdir}` `{model}` placeholders | generic |
| `manual` | prompts a human to run IDE/cloud agents (Cursor IDE, Windsurf, Copilot agent) and enter cost and interventions | generic |

GitHub Copilot's cloud agent and IDE-only tools have no stable headless entry point; use `manual` or write an adapter that drives their API.

## 9. Result schema and leaderboard

- Result file: `schemas/result.schema.json` (JSON Schema 2020-12). Contains suite version, system identity, environment, config, coverage, per-task runs (OCM, passed, attempts, interventions, cost + basis, wall time, quality, changed files, failure log tail), and the computed summary. Validate with `python -m oer validate FILE`.
- Leaderboard: `python -m oer leaderboard results/*.json` writes `leaderboard/LEADERBOARD.md` and `leaderboard.json`. Eligibility: not synthetic, coverage = 100%. One row per (system, model), best run. Columns: rank, system, model, OER, OER-rel, five cycle scores, HTR, OCM/$, sessions, $/month. Submissions are result JSON files via pull request; CI validates schema and recomputes the summary from the task runs.

Sample report format (mock agent; not a real rating):

```
OPENCLAW EFFICIENCY RATING
System:   mock (skill=0.7)
Overall OER: 48
City: 72 | Highway: 0 | Heavy Refactor: 100 | Long Context: 100 | Autonomous Feature: 0
Human Takeover Rate: 43%
Productivity: 2.5 OCM/$  (7.4 OCM/hour)
Session Endurance: 12 OpenClaw Sessions (on a $20 budget)
Estimated Monthly Cost: $67 (40 sessions)
```

### 9.1 Results dashboard (proposed, not built)

A static web page that monitors and tracks results. Design only; nothing here is implemented yet.

**Approach.** A static site (no server, no database) built from the committed `results/*.json` files and deployed with GitHub Pages by CI. The result files stay the single source of truth, so the page can never show a number that is not reproducible from a schema-valid file. The build recomputes every summary with `oer.scoring` and fails if it differs from the file's stored summary. A small `python -m oer site` command emits `site/data.json`, and a dependency-free HTML/JS page (for example with Chart.js) reads it.

**Views.**
1. **Head-to-head (Claude Code / Claude Pro vs Copilot CLI / Copilot Pro).** Overall OER, five cycle scores, HTR, OCM per dollar, OCM per hour, session cost, endurance, monthly cost. Every number carries its badges (below).
2. **Run history.** OER, cost and endurance over time per system. This shows drift from CLI or model updates and the run-to-run noise floor (mean and spread once there are 3 or more sessions, see 12).
3. **Run detail.** Per-task table: passed, OCM, cost and `cost_basis`, wall time, interventions, quality, failure log tail, observed model.
4. **Depletion tracker.** For each plan, the cumulative spend per session against the plan budget, the point where a limit stopped the agent (if any), and the `endurance_basis` (`measured` or `projected`).
5. **Task health.** Per-task pass rate across runs, to spot rotten or unfairly hard tasks.

**Honesty rules (mandatory, from section 1).**
- No score is shown without its `cost_basis` mix, coverage (tasks run / suite), suite version and pinned-cohort status. A score without these is not rendered.
- Badges: `SYNTHETIC` (mock), `UNVERIFIED MODEL` (`model_verified` false or null), `PROJECTED` endurance, `PARTIAL` coverage, `EXPLORATORY` (unpinned), `UNKNOWN COST`. Synthetic, partial, unpinned and cost-unknown runs are listed in a separate "not rankable" section and never mixed into the ranked table.
- Different suite versions are never plotted on one trend line without a visible break at the version change.
- Plan facts and anchors shown on the page cite their source and read date, or say they could not be verified. No plan limit or price is stated without a source.
- Held-out task contents and hidden tests are never published. The page shows aggregate per-task results only, so contamination risk does not grow.

**Data flow.**
```
oer run -> results/<run>.json -> PR (CI: schema + recompute) -> merge to main
        -> oer site -> site/data.json + static page -> GitHub Pages
```
Live in-progress monitoring is out of scope for v1 of the page. A run is published only after it finishes. A later option is for the runner to append a heartbeat file (current session, task, spend so far) that the page polls, but that needs somewhere to host it and must never expose secrets or workdir paths.

**Decisions (2026-11-06).**
- **Any run is accepted into `results/`**, including synthetic, unpinned, partial and cost-unknown runs. Nothing is rejected for being unrankable; it is labelled instead. The page still shows ranked and not-rankable runs in separate sections (honesty rules above). The leaderboard eligibility rule in section 9 is unchanged.
- **Hosting:** public GitHub Pages is acceptable to start.
- Because everything is public, `log_tail` and `changed_files` are published. Add redaction (home paths, tokens, env values) before the first real-agent result is committed.

**Schema audit (is every view fed?).** Checked by `tests/test_dashboard_fields.py` against a mock run. Present: all run-level fields (suite version, cohort, coverage, depletion reason, model verification, summary metrics, `endurance_basis`) and all per-task fields (OCM, cost and `cost_basis`, wall time, interventions, quality, quota flag, observed models, log tail). Derivable without schema change: per-session spend, cost-basis mix, unrankable reasons.

Four gaps found by the audit are now closed (and tested):
- `system.version`: `CliAdapter` records the first line of `<tool> --version` (null if unreadable).
- `finished_at`: run end time.
- `harness_commit`: git HEAD of the harness, suffixed `+dirty` if the tree has uncommitted changes (null outside git). Treat `+dirty` results as not reproducible.
- `plan_window_start`: set with `--plan-window-start ISO_TIME` and recorded exactly as given, never guessed; null otherwise. Depletion runs should always pass it.

Also noted: the schema's `cost_basis` enum has `mixed`, which section 6 does not list, and per-task start times are absent. Neither is blocking; resolve when building `oer site`. This audit used mock output only, so it shows field presence, not that real Claude Code or Copilot CLI results fill them.

## 10. GitHub layout and CI/CD

```
openclaw-oer/
  oer/                    harness: config, scoring, tasks, verify, runner, report, CLI
    adapters/             base, mock, cli (+presets.json), manual
  tasks/<cycle>/<id>/     task.json, hidden_tests/, solution/ (reference overlay)
  seed_repo/              the repository under test (MVP: tiny; production: 50-100k LOC)
  schemas/                result.schema.json
  results/                submitted result files
  leaderboard/            generated LEADERBOARD.md / leaderboard.json
  tests/                  scoring unit tests + suite integrity + mock end-to-end
  docs/SPEC.md            this file
  .github/workflows/      ci.yml (tests, mock run, schema, leaderboard), benchmark.yml (manual real-agent run)
```

`ci.yml` runs on every push: unit and integrity tests, a full mock benchmark, schema validation, leaderboard build. `benchmark.yml` is a manual dispatch that installs an agent CLI, runs the suite with secrets, validates, and uploads the result artifact. Recommended additions: a nightly job to detect task rot, and a PR check that recomputes submitted summaries.

## 11. Known limitations of v0.1.0

- Human baselines `H` are author estimates; anchors (`$0.75/OCM`, `6 min/OCM`) are placeholders until calibrated on real systems.
- The seed repo is ~100 lines, not 50-100k; Highway "10-20 files" and Long Context "whole repo" are not truly exercised yet.
- Quality is a crude proxy. Binary pass/fail ignores partial progress.
- One run per task is noisy. Agents are stochastic; official ratings need >= 3 sessions with the mean and spread reported.
- Cost comparability across API-metered tools and subscription tools is unresolved (see 6).
- Verification is Python/pytest only; the TypeScript, React and SQL parts of the target repo need their own verifiers (vitest, Playwright, a SQL test DB).
- Agents can in principle read files outside their workdir; production runs must be containerised.

## 12. Roadmap

1. Build the 50-100k LOC polyglot repo and 40+ tasks via defect/feature injection.
2. Human baseline study (>= 3 engineers per task) to fix `H`.
3. Calibrate anchors on several real systems; freeze v1.0.
4. Replace the quality proxy (lint, complexity delta, rubric review).
5. Multi-session statistics: mean, confidence interval, and a published noise floor.
6. Results dashboard: static site from `results/*.json` (section 9.1).
7. Private held-out set and submission verification service.
8. Verified adapters for each named tool; a quota-to-dollar convention for subscription plans.
