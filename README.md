# ClawMPG: OpenClaw Efficiency Rating (OER)

An EPA-style efficiency benchmark for AI coding agents: how much verified engineering work do you get per dollar, per hour, and per human rescue?

**Current focus:** one pinned cohort, Claude Sonnet 5.5 at medium effort, compared across the Claude Pro (Claude Code) and Copilot Pro (Copilot CLI) subscriptions.

Full design: [docs/SPEC.md](docs/SPEC.md). Status: MVP. The harness, scoring, schema and CI work; the 50-100k LOC benchmark repo is specified but not built (the MVP uses a tiny seed repo and 7 tasks, one or more per cycle).

## Quick start (Linux, Python 3.10+)

```bash
pip install -e ".[dev]"
python -m pytest -q                         # scoring, suite integrity, mock end-to-end

python -m oer run --adapter mock --mock-skill 0.8        # synthetic demo, prints the EPA report
python -m oer run --adapter claude-code                  # Claude Code, Sonnet 5.5 @ medium (needs CLI + login)
python -m oer run --adapter copilot-cli                  # Copilot CLI (set effortLevel=medium in ~/.copilot/settings.json first)
python -m oer apply-cost results/RUN.json --total-usd 3.2   # credits used, read from the Copilot usage page
python -m oer run --adapter claude-code --sessions 50    # keep going; stops when the plan's usage limit is hit
python -m oer run --adapter manual --plan "Copilot Pro in VS Code"   # IDE agents, you drive them
python -m oer leaderboard results/*.json
```

Useful flags: `--cycles city,highway`, `--ids city-001`, `--attempts 2`, `--sessions 3`, `--budget-usd 20`, `--stop-at-usd 5`.

## Agents

| Adapter | Status |
|---|---|
| `mock` | tested; synthetic results, excluded from the leaderboard |
| `claude-code` | live-tested on one task: pinned model verified from the tool's own output |
| `copilot-cli` | built from GitHub's CLI docs, **not run**; the CLI prints no cost, so use `apply-cost` |
| `codex`, `aider`, `cursor-agent` | untested presets, outside the pinned cohort |
| `custom`, `manual` | generic; `manual` covers Cursor/Windsurf/Copilot in the IDE |

Runs with a different model or effort are refused unless `--allow-unpinned`. With no cost source the cost is "unknown" and the Cost score is 0.

## Reading a result

`Overall OER` is 0-100 from fixed reference anchors (not relative to other systems). Partial-coverage, synthetic and cost-unknown runs are labelled in the report and excluded from the leaderboard. See SPEC sections 3-6 for formulas and OCM (OpenClaw Mile) definition.
