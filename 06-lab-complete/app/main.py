"""
Day 12 - Production-ready API.

Features:
- API key authentication
- Redis-backed stateless session history
- Rate limiting (10 req/min by default)
- Monthly cost guard ($10/month by default)
- Health + readiness checks
- Graceful shutdown
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import CostGuard
from app.rate_limiter import RateLimiter

try:
    from utils.mock_llm import ask
except ModuleNotFoundError:  # local development from 06-lab-complete/
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.append(str(repo_root))
    from utils.mock_llm import ask

try:
    import redis
except Exception:  # pragma: no cover - fallback path
    redis = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("day12-agent")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
logger.propagate = False


START_TIME = time.time()
state_lock = Lock()
runtime_state = {
    "ready": False,
    "shutting_down": False,
    "in_flight_requests": 0,
}

redis_client = None
memory_history_store: dict[str, list[dict[str, Any]]] = {}

rate_limiter = RateLimiter(max_requests=settings.rate_limit_per_minute, window_seconds=60)
cost_guard = CostGuard(
    monthly_budget_usd=settings.monthly_budget_usd,
    price_per_1k_input_tokens=settings.price_per_1k_input_tokens,
    price_per_1k_output_tokens=settings.price_per_1k_output_tokens,
)


def _connect_redis():
    if redis is None:
        return None
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover - depends on runtime
        logger.warning(json.dumps({"event": "redis_unavailable", "reason": str(exc)}))
        return None


def _history_key(user_id: str) -> str:
    return f"history:{user_id}"


def _append_history(user_id: str, role: str, content: str) -> int:
    payload = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if redis_client is not None:
        key = _history_key(user_id)
        redis_client.rpush(key, json.dumps(payload, ensure_ascii=False))
        redis_client.ltrim(key, -20, -1)
        redis_client.expire(key, settings.session_ttl_seconds)
        return redis_client.llen(key)

    history = memory_history_store.setdefault(user_id, [])
    history.append(payload)
    history[:] = history[-20:]
    return len(history)


def _redis_connected() -> bool:
    if redis_client is None:
        return False
    try:
        redis_client.ping()
        return True
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info(json.dumps({"event": "startup_begin"}))
    redis_client = _connect_redis()

    # In production we require Redis for stateless behavior.
    with state_lock:
        runtime_state["ready"] = redis_client is not None or settings.environment != "production"
        runtime_state["shutting_down"] = False

    logger.info(
        json.dumps(
            {
                "event": "startup_complete",
                "ready": runtime_state["ready"],
                "storage": "redis" if redis_client is not None else "memory-fallback",
                "environment": settings.environment,
            }
        )
    )
    yield

    with state_lock:
        runtime_state["ready"] = False
        runtime_state["shutting_down"] = True
    logger.info(json.dumps({"event": "shutdown_begin"}))

    timeout_seconds = 30
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with state_lock:
            if runtime_state["in_flight_requests"] == 0:
                break
            in_flight = runtime_state["in_flight_requests"]
        logger.info(json.dumps({"event": "draining_requests", "in_flight": in_flight}))
        time.sleep(1)

    logger.info(json.dumps({"event": "shutdown_complete"}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.environment != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_tracking_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    with state_lock:
        is_shutting_down = runtime_state["shutting_down"]
        runtime_state["in_flight_requests"] += 1

    if is_shutting_down and request.url.path not in {"/health", "/ready"}:
        with state_lock:
            runtime_state["in_flight_requests"] -= 1
        return JSONResponse(status_code=503, content={"detail": "Service shutting down"})

    started_at = time.time()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.time() - started_at) * 1000, 2)
        with state_lock:
            runtime_state["in_flight_requests"] -= 1
        logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                }
            )
        )


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
def health():
    with state_lock:
        ready = runtime_state["ready"]
        in_flight = runtime_state["in_flight_requests"]
    redis_ok = _redis_connected()
    status = "ok" if ready else "degraded"
    return {
        "status": status,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "ready": ready,
        "in_flight_requests": in_flight,
        "storage": "redis" if redis_ok else "memory-fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    with state_lock:
        if not runtime_state["ready"] or runtime_state["shutting_down"]:
            raise HTTPException(status_code=503, detail="Service not ready")
    if settings.environment == "production" and not _redis_connected():
        raise HTTPException(status_code=503, detail="Redis not available")
    return {"ready": True}


@app.post("/ask")
def ask_agent(body: AskRequest, _api_key: str = Depends(verify_api_key)):
    with state_lock:
        if not runtime_state["ready"] or runtime_state["shutting_down"]:
            raise HTTPException(status_code=503, detail="Service unavailable")

    rate_info = rate_limiter.check(body.user_id, redis_client=redis_client)

    # conservative estimate before call
    estimated_input_tokens = len(body.question.split()) * 2
    estimated_output_tokens = 200
    estimated_cost = cost_guard.estimate_cost(estimated_input_tokens, estimated_output_tokens)
    cost_guard.check_budget(body.user_id, estimated_cost, redis_client=redis_client)

    turn_number = _append_history(body.user_id, "user", body.question)
    answer = ask(body.question)
    turn_number = _append_history(body.user_id, "assistant", answer)

    output_tokens = len(answer.split()) * 2
    actual_cost = cost_guard.estimate_cost(estimated_input_tokens, output_tokens)
    usage = cost_guard.record_usage(body.user_id, actual_cost, redis_client=redis_client)

    logger.info(
        json.dumps(
            {
                "event": "ask",
                "user_id": body.user_id,
                "question_length": len(body.question),
                "cost_usd": actual_cost,
                "used_usd": usage.used_usd,
            }
        )
    )

    return {
        "user_id": body.user_id,
        "answer": answer,
        "usage": {
            "rate_limit_remaining": rate_info["remaining"],
            "monthly_budget_used_usd": usage.used_usd,
            "monthly_budget_remaining_usd": usage.remaining_usd,
            "monthly_budget_usd": usage.budget_usd,
            "month": usage.month,
        },
        "conversation_messages": turn_number,
        "storage": "redis" if _redis_connected() else "memory-fallback",
    }


@app.get("/usage/{user_id}")
def get_usage(user_id: str, _api_key: str = Depends(verify_api_key)):
    usage = cost_guard.get_usage(user_id, redis_client=redis_client)
    return {
        "user_id": usage.user_id,
        "month": usage.month,
        "used_usd": usage.used_usd,
        "remaining_usd": usage.remaining_usd,
        "budget_usd": usage.budget_usd,
    }


def _handle_signal(signum, _frame):
    signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
    logger.info(json.dumps({"event": "signal_received", "signal": signal_name}))


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
