"""Versioned constants. Changing any value here requires bumping SUITE_VERSION."""

SUITE_VERSION = "0.1.0"

CYCLES = ["city", "highway", "heavy", "longctx", "autonomous"]

CYCLE_NAMES = {
    "city": "City",
    "highway": "Highway",
    "heavy": "Heavy Refactor",
    "longctx": "Long Context",
    "autonomous": "Autonomous Feature",
}

# Weight of each cycle in the overall OER (renormalised over cycles actually run).
CYCLE_WEIGHTS = {
    "city": 0.25,
    "highway": 0.25,
    "heavy": 0.15,
    "longctx": 0.15,
    "autonomous": 0.20,
}

# Weights of the per-cycle score components. Must sum to 1.
COMPONENT_WEIGHTS = {
    "success": 0.40,
    "cost": 0.20,
    "autonomy": 0.20,
    "speed": 0.10,
    "quality": 0.10,
}

# 1 OpenClaw Mile = the work a reference engineer completes in this many minutes.
MINUTES_PER_OCM = 30.0

# Reference anchors (absolute, versioned). A system at or better than the anchor
# scores 1.0 on that component; the score decays logarithmically beyond it.
REF_COST_PER_OCM_USD = 0.75
REF_AGENT_MINUTES_PER_OCM = 6.0

# A "standard month" is this many sessions (one session = one pass of the suite).
STANDARD_MONTH_SESSIONS = 40

DEFAULT_BUDGET_USD = 20.0

# GitHub AI Credits are billed at a fixed rate: 1 credit = $0.01
# (https://docs.github.com/en/copilot/concepts/billing-and-usage/individuals/billing, read 2026-11-06).
AI_CREDIT_USD = 0.01

# What the cost was actually billed against. Only "plan_allowance" runs say anything about how far
# a subscription goes; "extra_usage" (pay-as-you-go past a plan limit) and "api" measure the harness only.
BILLING_MODES = ["plan_allowance", "extra_usage", "api", "unknown"]

# Cohort pinned for official ratings: every system is rated running this exact model
# at this reasoning effort, so the score isolates the harness and plan, not the model.
PINNED = {"model": "claude-sonnet-5-5", "effort": "medium"}


def norm_model(name: str) -> str:
    """Normalise model ids across vendors: claude-sonnet-5.5 == claude-sonnet-5-5."""
    return name.strip().lower().replace(".", "-").replace("_", "-")
