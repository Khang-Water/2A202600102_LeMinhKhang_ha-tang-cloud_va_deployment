# Day 12 Lab - Mission Answers

> Student Name: Lê Minh Khang  
> Student ID: 2A202600102  
> Date: 2026-04-17

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1. Hardcoded secrets in source code (`OPENAI_API_KEY`, `DATABASE_URL`).
2. `DEBUG=True` in runtime code.
3. Logging secrets to console (`print` includes API key).
4. No `/health` endpoint for liveness probe.
5. Fixed port (`8000`) and localhost bind only (`host="localhost"`).
6. No graceful shutdown handling.

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcoded values | Environment variables | Safe secrets + portable across environments |
| Logging | `print()` | Structured JSON logging | Better observability on cloud logs |
| Health check | Missing | `/health` + `/ready` | Auto-restart and smart traffic routing |
| Shutdown | Abrupt stop | Graceful shutdown | Avoid dropped requests during deploy/restart |
| Host/Port | `localhost:8000` fixed | `0.0.0.0` + `PORT` env | Required by Railway/Render runtime |
| CORS/Security headers | Basic/no control | Configurable | Better API exposure control |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** `python:3.11` (develop Dockerfile).
2. **Working directory:** `/app`.
3. **Why COPY requirements first:** to maximize Docker layer cache, avoid reinstalling deps on every code change.
4. **CMD vs ENTRYPOINT:** `CMD` sets default command (easily overridden), `ENTRYPOINT` makes container behave like fixed executable.

### Exercise 2.3: Image size comparison
> Docker CLI was unavailable in this environment, so values are estimated from base image families and stage design.

- Develop: ~1000 MB (`python:3.11` full image + app layer)
- Production: ~220 MB (`python:3.11-slim` runtime stage + minimal files)
- Difference: ~78%

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: `https://agent-api-production-1679.up.railway.app`
- Screenshot: `screenshots/running.png`

### Exercise 3.2: Render vs Railway config
- `railway.toml`: simple build/deploy blocks and health path.
- `render.yaml`: declarative service blueprint + environment variables + optional keyvalue service.
- Render config is more infrastructure-as-code style for multi-service setup.

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results
Public deployment smoke test results (`2026-04-17`, Railway):

```text
GET /health -> 200
GET /ready -> 200
POST /ask (no X-API-Key) -> 401
POST /ask (valid X-API-Key) -> 200
rate_statuses: 200 200 200 200 200 200 200 200 200 200 429
```

### Exercise 4.4: Cost guard implementation
- Implemented in `app/cost_guard.py` with per-user monthly tracking key (`budget:YYYY-MM`).
- Uses Redis hash for persistent stateless accounting (with in-memory fallback for local dev).
- Flow:
  1. Estimate cost before model call (`check_budget`).
  2. Reject with `402` if exceeded.
  3. Record actual cost after response (`record_usage`).
- Default budget: `$10/month/user` via `MONTHLY_BUDGET_USD`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
- **5.1 Health & readiness**
  - `GET /health`: liveness, uptime, storage mode, in-flight requests.
  - `GET /ready`: returns `503` when shutting down or not ready.
- **5.2 Graceful shutdown**
  - `SIGTERM`/`SIGINT` handlers + lifespan shutdown flow.
  - Stops readiness, waits for in-flight requests before exit.
- **5.3 Stateless design**
  - Conversation history and limiter/budget states stored in Redis keys.
  - No user conversation state in process memory (memory fallback only for local degraded mode).
- **5.4 Load balancing readiness**
  - App is stateless and safe for horizontal scaling behind reverse proxy.
  - Rate limit and budget logic use shared Redis store.
- **5.5 Validation**
  - `python3 check_production_ready.py` => **20/20 checks passed (100%)**.
