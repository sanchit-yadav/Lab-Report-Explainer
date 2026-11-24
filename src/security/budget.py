"""Per-user token and cost budget tracker enforcing daily usage ceilings.

Protects against resource exhaustion, API quota drains, and denial-of-wallet attacks.
"""

from __future__ import annotations

import datetime
import logging
import os
import threading
from datetime import timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("security.budget")


class UserBudgetManager:
    """Tracks and limits daily token and dollar budgets per user."""

    _instance: Optional[UserBudgetManager] = None
    _lock = threading.Lock()

    def __init__(self):
        self.max_daily_tokens = int(os.environ.get("MAX_DAILY_USER_TOKENS", "100000"))
        self.max_daily_cost_usd = float(os.environ.get("MAX_DAILY_USER_COST_USD", "1.00"))
        # In-memory daily tracking map: {user_id: {"date": "YYYY-MM-DD", "tokens": N, "cost_usd": X}}
        self._usage_map: Dict[str, Dict[str, Any]] = {}
        self._map_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> UserBudgetManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = UserBudgetManager()
            return cls._instance

    def _get_current_date(self) -> str:
        return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def check_budget(self, user_id: str, estimated_tokens: int = 1500) -> Tuple[bool, str]:
        """Verify whether the user has remaining budget for the estimated request."""
        if not user_id:
            user_id = "anonymous"

        today = self._get_current_date()
        with self._map_lock:
            entry = self._usage_map.get(user_id)
            if not entry or entry.get("date") != today:
                # Reset or initialize for today
                self._usage_map[user_id] = {"date": today, "tokens": 0, "cost_usd": 0.0}
                return True, "Budget OK"

            curr_tokens = entry["tokens"]
            curr_cost = entry["cost_usd"]

            if curr_tokens + estimated_tokens > self.max_daily_tokens:
                msg = f"Daily token budget exceeded ({curr_tokens}/{self.max_daily_tokens} tokens). Resets at 00:00 UTC."
                logger.warning(f"User {user_id} exceeded token budget: {curr_tokens}")
                return False, msg

            if curr_cost >= self.max_daily_cost_usd:
                msg = f"Daily computation budget exceeded (${curr_cost:.2f}/${self.max_daily_cost_usd:.2f} USD). Resets at 00:00 UTC."
                logger.warning(f"User {user_id} exceeded cost budget: {curr_cost}")
                return False, msg

        return True, "Budget OK"

    def record_usage(self, user_id: str, tokens: int, cost_usd: Optional[float] = None) -> None:
        """Record consumed tokens and compute expenditure."""
        if not user_id:
            user_id = "anonymous"

        today = self._get_current_date()
        computed_cost = cost_usd if cost_usd is not None else (tokens * (0.15 / 1_000_000))

        with self._map_lock:
            entry = self._usage_map.get(user_id)
            if not entry or entry.get("date") != today:
                self._usage_map[user_id] = {
                    "date": today,
                    "tokens": tokens,
                    "cost_usd": computed_cost,
                }
            else:
                entry["tokens"] += tokens
                entry["cost_usd"] += computed_cost

    def get_user_usage(self, user_id: str) -> Dict[str, Any]:
        """Retrieve current consumption statistics for a given user."""
        today = self._get_current_date()
        with self._map_lock:
            entry = self._usage_map.get(user_id, {"date": today, "tokens": 0, "cost_usd": 0.0})
            if entry.get("date") != today:
                entry = {"date": today, "tokens": 0, "cost_usd": 0.0}
            return {
                "user_id": user_id,
                "date": today,
                "tokens_used": entry["tokens"],
                "max_tokens": self.max_daily_tokens,
                "cost_usd": round(entry["cost_usd"], 5),
                "max_cost_usd": self.max_daily_cost_usd,
                "remaining_tokens": max(0, self.max_daily_tokens - entry["tokens"]),
                "remaining_cost_usd": max(
                    0.0, round(self.max_daily_cost_usd - entry["cost_usd"], 5)
                ),
            }
