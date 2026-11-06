"""Cross-check a run's reported cost against GitHub's AI-credit usage API.

Endpoint: GET /users/{username}/settings/billing/ai_credit/usage (fine-grained token with the
"Plan" user permission, read). Response shape taken from GitHub's published OpenAPI description;
NOT yet observed live, so the first real call should be checked with `oer ledger-snapshot`.

The check is account-wide and month-level: anything else billed to the account in the same
window (other Copilot use) lands in the delta. It is a cross-check, never a replacement for the
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


def fetch_snapshot(user: str, token: str, now: Optional[datetime] = None,
                   http_get: Callable = _http_get) -> dict:
    now = now or datetime.now(timezone.utc)
    url = f"{API}/users/{user}/settings/billing/ai_credit/usage?year={now.year}&month={now.month}"
    data = http_get(url, token)
    items = data.get("usageItems")
    if not isinstance(items, list):
        raise LedgerUnavailable("unexpected response shape")
    return {
        "at": now.isoformat(timespec="seconds"),
        "year": now.year,
        "month": now.month,
        "gross_amount": round(sum(i.get("grossAmount", 0) or 0 for i in items), 6),
        "net_amount": round(sum(i.get("netAmount", 0) or 0 for i in items), 6),
        "gross_quantity": round(sum(i.get("grossQuantity", 0) or 0 for i in items), 6),
        "unit_types": sorted({i.get("unitType", "?") for i in items}),
        "items": len(items),
    }


def settle(user: str, token: str, http_get: Callable = _http_get, sleep: Callable = time.sleep,
           interval_s: float = 20, max_wait_s: float = 180) -> dict:
    """Poll until two consecutive readings agree (usage data can lag), or give up and return the last one."""
    last = fetch_snapshot(user, token, http_get=http_get)
    waited = 0.0
    while waited < max_wait_s:
        sleep(interval_s)
        waited += interval_s
        cur = fetch_snapshot(user, token, http_get=http_get)
        if cur["gross_amount"] == last["gross_amount"]:
            return {**cur, "settled": True}
        last = cur
    return {**last, "settled": False}


def compare(before: Optional[dict], after: Optional[dict], reported_usd: Optional[float]) -> dict:
    out = {"source": "github_ai_credit_api", "before": before, "after": after, "reported_usd": reported_usd}
    if not before or not after:
        return {**out, "status": "unavailable"}
    if (before["year"], before["month"]) != (after["year"], after["month"]):
        return {**out, "status": "unavailable", "reason": "run spanned a month boundary"}
    delta = round(after["gross_amount"] - before["gross_amount"], 6)
    out["delta_usd"] = delta
    if reported_usd is None:
        return {**out, "status": "no_reported_cost"}
    gap = round(delta - reported_usd, 6)
    out["difference_usd"] = gap
    tol = max(TOLERANCE_ABS_USD, TOLERANCE_REL * reported_usd)
    out["status"] = "match" if abs(gap) <= tol else "mismatch"
    if not after.get("settled", False):
        out["note"] = "ledger had not stopped changing when read; treat as provisional"
    return out


class LedgerWatch:
    """Reads the ledger before and after a run. Failures are recorded, never fatal."""

    def __init__(self, user: str, token: str, http_get: Callable = _http_get, sleep: Callable = time.sleep):
        self.user, self.token, self.http_get, self.sleep = user, token, http_get, sleep
        self.before: Optional[dict] = None
        self.errors: list[str] = []

    def start(self) -> None:
        try:
            self.before = fetch_snapshot(self.user, self.token, http_get=self.http_get)
        except LedgerUnavailable as e:
            self.errors.append(f"before: {e}")

    def finish(self, reported_usd: Optional[float]) -> dict:
        after = None
        try:
            after = settle(self.user, self.token, http_get=self.http_get, sleep=self.sleep)
        except LedgerUnavailable as e:
            self.errors.append(f"after: {e}")
        result = compare(self.before, after, reported_usd)
        if self.errors:
            result["errors"] = self.errors
        return result


def token_from_env() -> Optional[str]:
    return os.environ.get(TOKEN_ENV) or None
