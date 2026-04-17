# Day 12 - Lab 06 Complete (Production Agent)

Production-ready FastAPI agent for Day 12 submission.

## Features

- API key authentication (`X-API-Key`)
- Rate limiting: **10 requests/minute** per user
- Cost guard: **$10/month** per user
- Health check: `GET /health`
- Readiness check: `GET /ready`
- Graceful shutdown (`SIGTERM`)
- Stateless conversation history on Redis
- Multi-stage Docker build (non-root runtime)

---

## Project structure

```text
06-lab-complete/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── rate_limiter.py
│   └── cost_guard.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .dockerignore
├── railway.toml
└── render.yaml
```

---

## Run locally (Docker Compose)

```bash
cd 06-lab-complete
cp .env.example .env
docker compose up --build
```

### Quick tests

```bash
# Health
curl http://localhost:8000/health

# Ready
curl http://localhost:8000/ready

# Auth required (expect 401)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"hello"}'

# With API key
API_KEY=$(grep AGENT_API_KEY .env | cut -d= -f2)
curl -X POST http://localhost:8000/ask \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Explain deployment"}'
```

---

## Deploy

- Railway: uses `railway.toml`
- Render: uses `render.yaml` (set `REDIS_URL` as managed Redis URL)

Required environment variables:

- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `RATE_LIMIT_PER_MINUTE`
- `MONTHLY_BUDGET_USD`

