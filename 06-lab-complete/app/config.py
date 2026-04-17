"""
Centralized runtime configuration.

12-factor style: read everything from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _as_bool(value: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: _as_bool(os.getenv("DEBUG", "false")))

    # App
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    allowed_origins: List[str] = field(
        default_factory=lambda: [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
    )

    # Security
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))

    # Rate limiting
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))

    # Cost guard
    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0")))
    # Token pricing (default: GPT-4o mini style pricing)
    price_per_1k_input_tokens: float = field(
        default_factory=lambda: float(os.getenv("PRICE_PER_1K_INPUT_TOKENS", "0.00015"))
    )
    price_per_1k_output_tokens: float = field(
        default_factory=lambda: float(os.getenv("PRICE_PER_1K_OUTPUT_TOKENS", "0.0006"))
    )

    # Stateless storage
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    session_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_SECONDS", "3600")))

    def validate(self) -> "Settings":
        if self.environment == "production" and not self.agent_api_key:
            raise ValueError("AGENT_API_KEY must be set in production")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be > 0")
        if self.monthly_budget_usd <= 0:
            raise ValueError("MONTHLY_BUDGET_USD must be > 0")
        if self.session_ttl_seconds <= 0:
            raise ValueError("SESSION_TTL_SECONDS must be > 0")
        return self


settings = Settings().validate()

