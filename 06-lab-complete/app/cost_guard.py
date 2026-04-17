"""Monthly budget guard for LLM usage."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException


@dataclass
class UsageSummary:
    user_id: str
    month: str
    used_usd: float
    budget_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, round(self.budget_usd - self.used_usd, 6))


class CostGuard:
    def __init__(
        self,
        *,
        monthly_budget_usd: float,
        price_per_1k_input_tokens: float,
        price_per_1k_output_tokens: float,
    ):
        self.monthly_budget_usd = monthly_budget_usd
        self.price_per_1k_input_tokens = price_per_1k_input_tokens
        self.price_per_1k_output_tokens = price_per_1k_output_tokens
        self._fallback_usage: dict[str, dict[str, float]] = {}

    @staticmethod
    def _month_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @staticmethod
    def _seconds_until_next_month() -> int:
        now = datetime.now(timezone.utc)
        if now.month == 12:
            next_month = datetime(year=now.year + 1, month=1, day=1, tzinfo=timezone.utc)
        else:
            next_month = datetime(year=now.year, month=now.month + 1, day=1, tzinfo=timezone.utc)
        return max(3600, int((next_month - now).total_seconds()) + 3600)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        input_cost = (max(0, input_tokens) / 1000) * self.price_per_1k_input_tokens
        output_cost = (max(0, output_tokens) / 1000) * self.price_per_1k_output_tokens
        return round(input_cost + output_cost, 6)

    def check_budget(self, user_id: str, estimated_cost: float, redis_client=None) -> UsageSummary:
        summary = self.get_usage(user_id, redis_client=redis_client)
        if summary.used_usd + estimated_cost > summary.budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Monthly budget exceeded",
                    "used_usd": summary.used_usd,
                    "estimated_next_call_usd": estimated_cost,
                    "budget_usd": summary.budget_usd,
                    "resets": "first day of next month (UTC)",
                },
            )
        return summary

    def record_usage(self, user_id: str, cost_usd: float, redis_client=None) -> UsageSummary:
        month = self._month_key()
        key = f"budget:{month}"

        if redis_client is not None:
            redis_client.hincrbyfloat(key, user_id, cost_usd)
            redis_client.expire(key, self._seconds_until_next_month())
            return self.get_usage(user_id, redis_client=redis_client)

        month_store = self._fallback_usage.setdefault(month, {})
        month_store[user_id] = round(month_store.get(user_id, 0.0) + cost_usd, 6)
        # cleanup old months in fallback to avoid unbounded growth
        for old_month in list(self._fallback_usage.keys()):
            if old_month != month:
                self._fallback_usage.pop(old_month, None)
        return self.get_usage(user_id, redis_client=None)

    def get_usage(self, user_id: str, redis_client=None) -> UsageSummary:
        month = self._month_key()
        used = 0.0
        if redis_client is not None:
            raw = redis_client.hget(f"budget:{month}", user_id)
            used = float(raw or 0.0)
        else:
            used = float(self._fallback_usage.get(month, {}).get(user_id, 0.0))
        return UsageSummary(
            user_id=user_id,
            month=month,
            used_usd=round(used, 6),
            budget_usd=self.monthly_budget_usd,
        )

