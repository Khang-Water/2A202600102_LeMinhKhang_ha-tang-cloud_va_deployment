# Deployment Information

## Public URL
`https://agent-api-production-1679.up.railway.app`

## Platform
Railway (Dockerfile deploy) + Redis service

## Test Commands

### Health Check
```bash
curl https://agent-api-production-1679.up.railway.app/health
# Expected: {"status":"ok", ...}
```

### Readiness Check
```bash
curl https://agent-api-production-1679.up.railway.app/ready
# Expected: {"ready":true}
```

### API Test (authentication required)
```bash
curl -X POST https://agent-api-production-1679.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

### Authentication check (should fail)
```bash
curl -X POST https://agent-api-production-1679.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
# Expected: 401
```

### Rate-limit check
```bash
for i in {1..15}; do
  curl -X POST https://agent-api-production-1679.up.railway.app/ask \
    -H "X-API-Key: YOUR_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"test","question":"rate test"}'
done
# Expected: eventually returns 429
```

## Environment Variables Set
- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `RATE_LIMIT_PER_MINUTE`
- `MONTHLY_BUDGET_USD`
- `LOG_LEVEL`

Get current API key from Railway CLI:
```bash
cd 06-lab-complete
railway variables list -s agent-api | grep AGENT_API_KEY
```

## Local verification evidence
- `python3 06-lab-complete/check_production_ready.py` → `20/20 checks passed (100%)`
- Public smoke test (2026-04-17):
  - `/health` = 200
  - `/ready` = 200
  - `/ask` without API key = 401
  - `/ask` with API key = 200
  - repeated requests trigger 429

## Deployment log evidence (no screenshots)

Build/runtime evidence captured from Railway logs:

```text
Deploy complete
Build time: 57.26 seconds
Starting Healthcheck
[1/1] Healthcheck succeeded!
```

App runtime evidence:

```text
INFO: Uvicorn running on http://0.0.0.0:8080
GET /health -> 200 OK
GET / -> 200 OK
```
