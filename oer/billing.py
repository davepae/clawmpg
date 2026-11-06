"""Cross-check a run's reported cost against GitHub's AI-credit usage API.

Endpoint: GET /users/{username}/settings/billing/ai_credit/usage (fine-grained token with the
"Plan" user permission, read). Response shape taken from GitHub's published OpenAPI description;
observed live 2026-11-06 (items carry product, sku, model, grossAmount, ...).

The check is account-wide and month-level, but filtered to the pinned model's rows when a model is given.
Other use of that model in the same window still lands in the delta, and the API lags and updates in
batches (minutes), so the check waits for the ledger to move. It is a cross-check, never a replacement for the
tool-reported cost, and it is informational: a mismatch is recorded, not corrected.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Optional

from . import config

API = "https://api.github.com"
TOKEN_ENV = "OER_GITHUB_BILLING_TOKEN"
# Allowed gap between the ledger delta and the tool-reported cost: the larger of the two.
TOLERANCE_ABS_USD = 0.02
TOLERANCE_REL = 0.15


class LedgerUnavailable(Exception):
    pass


def _http_get(url: str, token: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise LedgerUnavailable(f"HTTP {e.code}") from None  # never echo headers or the token
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LedgerUnavailable(type(e).__name__) from None


def model_key(name: Optional[str]) -> str:
    """'Claude Sonnet 5.5' (API display name) -> 'claude-sonnet-5-5', matching config.PINNED."""
    return config.norm_model((name or "?").replace(" ", "-"))


def _amount(snap: dict, model: Optional[str]) -> float:
    if model is None:
        return snap["gross_amount"]
    return snap.get("by_model_gross_amount", {}).get(config.norm_model(model), 0.0)


def fetch_items(user: str, token: str, now: Optional[datetime] = None,
                http_get: Callable = _http_get) -> list:
    now = now or datetime.now(timezone.utc)
    url = f"{API}/users/{user}/settings/billing/ai_credit/usage?year={now.year}&month={now.month}"
    items = http_get(url, token).get("usageItems")
    if not isinstance(items, list):
        raise LedgerUnavailable("unexpected response shape")
    return items


def fetch_snapshot(user: str, token: str, now: Optional[datetime] = None,
                   http_get: Callable = _http_get) -> dict:
    now = now or datetime.now(timezone.utc)
    items = fetch_items(user, token, now, http_get)
    by_model: dict = {}
    for i in items:
        key = model_key(i.get("model"))
        by_model[key] = round(by_model.get(key, 0) + (i.get("grossAmount", 0) or 0), 6)
    return {
        "by_model_gross_amount": by_model,
        "at": now.isoformat(timespec="seconds"),
        "year": now.year,
        "month": now.month,
        "gross_amount": round(sum(i.get("grossAmount", 0) or 0 for i in items), 6),
        "net_amount": round(sum(i.get("netAmount", 0) or 0 for i in items), 6),
        "gross_quantity": round(sum(i.get("grossQuantity", 0) or 0 for i in items), 6),
        "unit_types": sorted({i.get("unitType", "?") for i in items}),
        "items": len(items),
    }


def settle(user: str, token: str, baseline: float, model: Optional[str] = None,
           http_get: Callable = _http_get, sleep: Callable = time.sleep,
           interval_s: float = 30, max_wait_s: float = 600) -> dict:
    """Poll until the ledger has moved off `baseline` and then holds still for one more reading.

    The usage API lags and updates in batches, so an unchanged reading is not a final one: if it never
    moves within max_wait_s the result is flagged moved=False (not a mismatch, just not updated yet).
    """
    cur = fetch_snapshot(user, token, http_get=http_get)
    waited = 0.0
    while True:
        moved = _amount(cur, model) != baseline
        if moved or waited >= max_wait_s:
            break
        sleep(interval_s)
        waited += interval_s
        cur = fetch_snapshot(user, token, http_get=http_get)
    if not moved:
        return {**cur, "settled": False, "moved": False}
    while waited < max_wait_s:
        sleep(interval_s)
        waited += interval_s
        nxt = fetch_snapshot(user, token, http_get=http_get)
        if _amount(nxt, model) == _amount(cur, model):
            return {**nxt, "settled": True, "moved": True}
        cur = nxt
    return {**cur, "settled": False, "moved": True}


def compare(before: Optional[dict], after: Optional[dict], reported_usd: Optional[float],
            model: Optional[str] = None) -> dict:
    out = {"source": "github_ai_credit_api", "before": before, "after": after, "reported_usd": reported_usd,
           "model_filter": model}
    if not before or not after:
        return {**out, "status": "unavailable"}
    if (before["year"], before["month"]) != (after["year"], after["month"]):
        return {**out, "status": "unavailable", "reason": "run spanned a month boundary"}
    delta = round(_amount(after, model) - _amount(before, model), 6)
    out["delta_usd"] = delta
    if reported_usd is None:
        return {**out, "status": "no_reported_cost"}
    if after.get("moved") is False:
        return {**out, "status": "not_updated",
                "note": "ledger has not changed yet; its data lags, so no verdict"}
    gap = round(delta - reported_usd, 6)
    out["difference_usd"] = gap
    tol = max(TOLERANCE_ABS_USD, TOLERANCE_REL * reported_usd)
    out["status"] = "match" if abs(gap) <= tol else "mismatch"
    if not after.get("settled", False):
        out["note"] = "ledger had not stopped changing when read; treat as provisional"
    return out


class LedgerWatch:
    """Reads the ledger before and after a run. Failures are recorded, never fatal."""

    def __init__(self, user: str, token: str, http_get: Callable = _http_get, sleep: Callable = time.sleep,
                 model: Optional[str] = None):
        self.user, self.token, self.http_get, self.sleep = user, token, http_get, sleep
        self.model = model
        self.before: Optional[dict] = None
        self.errors: list[str] = []

    def start(self) -> None:
        try:
            self.before = fetch_snapshot(self.user, self.token, http_get=self.http_get)
        except LedgerUnavailable as e:
            self.errors.append(f"before: {e}")

    def finish(self, reported_usd: Optional[float]) -> dict:
        """No waiting: the usage API lags by well over 10 minutes, so the verdict comes later
        from `settle_check` (`oer ledger-settle`)."""
        out = {"source": "github_ai_credit_api", "status": "pending" if self.before else "unavailable",
               "user": self.user, "before": self.before, "reported_usd": reported_usd,
               "model_filter": self.model}
        if self.errors:
            out["errors"] = self.errors
        return out


def settle_check(check: dict, token: str, http_get: Callable = _http_get) -> dict:
    """Re-read the ledger for a stored ledger_check and return the updated check."""
    before, model = check.get("before"), check.get("model_filter")
    if not before or not check.get("user"):
        return check
    snap = fetch_snapshot(check["user"], token, http_get=http_get)
    moved = _amount(snap, model) != _amount(before, model)
    after = {**snap, "moved": moved, "settled": True}
    out = compare(before, after, check.get("reported_usd"), model)
    out["user"] = check["user"]
    out["checked_at"] = snap["at"]
    if moved and out["status"] == "mismatch" and out.get("difference_usd", 0) < 0:
        out["note"] = "ledger moved less than reported; it may still be catching up, re-run ledger-settle later"
    if out["status"] == "not_updated":
        out["status"] = "pending"
    return out


def token_from_env() -> Optional[str]:
    return os.environ.get(TOKEN_ENV) or None
