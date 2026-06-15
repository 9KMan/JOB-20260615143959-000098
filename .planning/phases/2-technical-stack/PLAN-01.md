---
title: "Phase 02: Technical Stack"
objective: "Define the complete technology stack including Python runtime, Playwright/Chromium configuration, proxy infrastructure, message queue system, database, containerization, and tooling required for the scraping framework."
done_when:
  - Python version and virtual environment tooling specified
  - Playwright version and Chromium configuration defined (stealth mode, Xvfb setup)
  - Oxylabs proxy integration strategy documented
  - RabbitMQ version, exchanges, queues, and DLX configuration specified
  - PostgreSQL version and connection pooling strategy defined
  - LLM integration approach specified (OpenAI/Anthropic API or self-hosted)
  - Docker base images and docker-compose structure outlined
  - Retry/dead-letter/circuit-breaker patterns documented
---
## Objective
Define the complete technology stack for the web scraping framework, specifying versions, dependencies, external service integrations, containerization strategy, and operational tooling. This phase establishes the foundation upon which all other phases build.

## Deliverables
- file:requirements.txt
- file:pyproject.toml
- file:Dockerfile
- file:Dockerfile.worker
- file:docker-compose.yml
- file:.env.example
- file:pyvenv.cfg

## Technical Details

### Python Runtime
- **Version:** Python 3.11+ (specify exact minor version, recommend 3.11.8 or 3.12.x)
- **Virtual Environment:** venv with requirements.txt OR Poetry for dependency locking
- **Package Manager:** pip with pip-tools for reproducible builds

### Core Dependencies

**Scraping/Playwright:**
- `playwright>=1.42.0` (latest stable)
- `playwright-stealth>=1.0.6` (anti-detection)
- `xvfbwrapper>=0.2.13` (headless display server)

**Message Queue/Workers:**
- `pika>=1.3.2` (RabbitMQ client, synchronous)
- `aio-pika>=9.4.0` (async RabbitMQ client for async workers)
- `tenacity>=8.2.3` (retry logic with exponential backoff)
- `circuitbreaker>=1.4.0` (circuit breaker pattern)

**Database/ORM:**
- `sqlalchemy>=2.0.25` (ORM)
- `asyncpg>=0.29.0` (async PostgreSQL driver)
- `psycopg2-binary>=2.9.9` (sync PostgreSQL driver)
- `alembic>=1.13.1` (migrations)
- `pgbouncer` (connection pooling - Docker service)

**LLM Integration:**
- `openai>=1.12.0` OR `anthropic>=0.18.0` (API clients)
- `pydantic>=2.6.0` (data validation for LLM inputs/outputs)

**API/Web Framework (if REST API needed):**
- `fastapi>=0.109.0`
- `uvicorn[standard]>=0.27.0`

**Monitoring/Logging:**
- `structlog>=24.1.0` (structured logging)
- `prometheus-client>=0.19.0` (metrics)

**Utilities:**
- `python-dotenv>=1.0.0`
- `pydantic-settings>=2.1.0`
- `httpx>=0.26.0` (HTTP client for proxy testing)

### Proxy Integration (Oxylabs)
- **API Client:** Custom wrapper around `httpx` with retry logic
- **Proxy Format:** `http://username:password@pr.oxylabs.io:7777`
- **Sticky Session:** `session=randomUUID` parameter for exit IP consistency
- **Country Targeting:** `country=US` (or dynamic based on job)
- **Error Handling:** Detect `ERR_TUNNEL_CONNECTION_TIMED_OUT`, `407`, `429`

### RabbitMQ Configuration

**Exchanges:**
- `scraper.direct` (direct exchange for job routing)
- `scraper.dlx` (dead letter exchange)
- `scraper.retry` (retry exchange with TTL)

**Queues:**
- `scraper.jobs` (main job queue, durable)
- `scraper.jobs.retry` (retry queue with message TTL, routes back to main)
- `scraper.jobs.dlq` (dead letter queue for permanent failures)
- `scraper.results` (completed results queue)
- `scraper.heartbeat` (worker health monitoring)

**Queue Arguments:**
```
x-dead-letter-exchange: scraper.dlx
x-dead-letter-routing-key: dlq
x-message-ttl: 30000 (30s for retry)
x-max-priority: 10
```

**Prefetch Count:** 1 (one job per worker at a time for reliability)

### PostgreSQL Schema

**Version:** 15+ (Docker image: `postgres:15-alpine`)

**Connection Pooling:**
- PGBouncer in transaction mode
- Max pool size: 100 connections
- Default pool size: 20
- Reserve pool size: 5

**Key Tables:**
- `scrape_jobs` - job metadata and status
- `scrape_results` - extracted data
- `scrape_errors` - error logs with retry history
- `scrape_proxies` - proxy health tracking
- `worker_instances` - worker registration and heartbeat

### Docker Configuration

**Base Images:**
- Workers: `python:3.12-slim` or `mcr.microsoft.com/playwright/python:v1.42.0-*`
- API (if needed): `python:3.12-slim`
- Database: `postgres:15-alpine`
- Proxy Pool: `pgbouncer:1.22`
- RabbitMQ: `rabbitmq:3.13-management-alpine`

**Docker Compose Services:**
1. `postgres` - PostgreSQL 15
2. `pgbouncer` - Connection pooler
3. `rabbitmq` - Message broker
4. `worker` - Scraper worker (scalable via `docker-compose up --scale worker=8`)
5. `api` - REST API (if applicable)
6. `prometheus` - Metrics collection
7. `grafana` - Dashboards (optional)

**Playwright in Docker:**
- Install Chromium browser: `playwright install chromium`
- Xvfb for headed mode in headless context
- Required system deps: `chromium`, `chromium-sandbox`, `libxkbcommon0`, `libnss3`

### Health Checks & Monitoring

**RabbitMQ Health:**
- HTTP API: `http://rabbitmq:15672/api/health/checks/alarms`
- Queue depth monitoring

**Worker Health:**
- Heartbeat queue with TTL
- Prometheus metrics endpoint
- Graceful shutdown signal handling

**Circuit Breaker Settings:**
- Failure threshold: 5 failures in 60 seconds
- Recovery timeout: 30 seconds
- Half-open max calls: 3

### File Structure for Stack Phase

```
/
├── requirements.txt              # All Python dependencies pinned
├── pyproject.toml               # Poetry config (alternative)
├── Dockerfile                   # Multi-stage build for workers
├── Dockerfile.api              # API service build
├── docker-compose.yml          # Full stack definition
├── docker-compose.override.yml # Local dev overrides
├── .env.example                 # Environment variable template
└── setup/
    └── install-playwright.sh   # Browser installation script
```

## Done When
- `requirements.txt` created with all dependencies and pinned versions
- `Dockerfile` builds successfully for worker image
- `docker-compose.yml` brings up postgres, pgbouncer, rabbitmq, and worker
- RabbitMQ exchanges and queues created via init script or management API
- PostgreSQL migrations run successfully
- Playwright chromium browser installed inside Docker image
- `.env.example` documents all required environment variables