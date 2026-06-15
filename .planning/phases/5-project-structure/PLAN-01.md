---
title: "Phase 05: Project Structure"
objective: "Scaffold complete project directory structure with all source files, configuration, entry points, and Docker infrastructure for the scalable Playwright scraping system."
done_when:
  - "Complete directory tree created with all __init__.py files"
  - "All Python modules stubbed with functional code"
  - "Docker configuration files ready for local and production deployment"
  - "Configuration management via environment variables and config files"
  - "Package dependencies properly specified"
---

## Objective

Create a production-ready project structure for the scalable web scraping system. The architecture must support:

- **Worker Fleet**: Horizontally scalable Playwright workers consuming from RabbitMQ
- **Stability**: Circuit breakers, dead-letter queues, retry logic with exponential backoff
- **Proxy Management**: Oxylabs residential proxy integration with sticky sessions and failover
- **Data Persistence**: PostgreSQL for job tracking, scraped data, and error logging
- **Post-Processing**: LLM-based extraction refinement and error classification

## Deliverables

- `src/scraper/` — Core scraper modules
  - `__init__.py`
  - `browser.py` — Playwright browser pool and context management
  - `page.py` — Page interaction helpers (stealth, captcha, cookies)
  - `scraper.py` — Base scraper class
  - `extractors/` — Data extraction logic per target site

- `src/workers/` — RabbitMQ worker fleet
  - `__init__.py`
  - `consumer.py` — Main queue consumer with retry/dead-letter logic
  - `publisher.py` — Job submission and result publishing
  - `circuit_breaker.py` — Circuit breaker implementation
  - `backoff.py` — Exponential backoff strategies

- `src/proxy/` — Proxy management
  - `__init__.py`
  - `oxylabs.py` — Oxylabs API client and session management
  - `rotator.py` — Proxy rotation and health checking
  - `sticky.py` — Sticky session management for exit node consistency

- `src/database/` — PostgreSQL integration
  - `__init__.py`
  - `connection.py` — Connection pool management
  - `models.py` — SQLAlchemy models
  - `migrations/` — Alembic migration scripts
  - `repositories/` — Data access layer

- `src/llm/` — LLM post-processing
  - `__init__.py`
  - `client.py` — OpenAI/Anthropic API integration
  - `classifier.py` — Error classification and recovery suggestions
  - `extractor.py` — Structured data extraction refinement

- `src/api/` — REST API (FastAPI)
  - `__init__.py`
  - `main.py` — FastAPI application
  - `routes/` — API endpoints
  - `schemas.py` — Pydantic models
  - `middleware.py` — Logging, error handling, CORS

- `src/config/` — Configuration management
  - `__init__.py`
  - `settings.py` — Pydantic settings from env
  - `sites.py` — Per-site configuration

- `src/utils/` — Utilities
  - `__init__.py`
  - `logging.py` — Structured logging setup
  - `metrics.py` — Prometheus metrics
  - `health.py` — Health check utilities

- `tests/` — Test suite
  - `__init__.py`
  - `conftest.py` — Pytest fixtures
  - `unit/` — Unit tests
  - `integration/` — Integration tests
  - `fixtures/` — Test data

- `docker/` — Docker assets
  - `worker.Dockerfile` — Multi-stage worker image
  - `api.Dockerfile` — API image
  - `docker-compose.yml` — Full stack orchestration
  - `docker-compose.dev.yml` — Development overrides
  - `nginx.conf` — Reverse proxy config

- `scripts/` — Operational scripts
  - `entrypoint.sh` — Container entry point
  - `migrate.sh` — Database migrations
  - `seed.sh` — Test data seeding

- `pyproject.toml` — Poetry/Pyproject configuration
- `pytest.ini` — Pytest configuration
- `.env.example` — Environment variable template
- `Makefile` — Common operations
- `README.md` — Setup and operational documentation

## Done When

- All Python files contain functional stub code (not just pass/...)
- Docker images build successfully without errors
- docker-compose up launches all services
- Environment variables documented in .env.example
- Unit tests pass for core components (circuit breaker, backoff, connection pool)
- Import paths consistent throughout codebase

## Technical Details

### Key Architecture Decisions

**Browser Management**: Browser instances pooled per worker, contexts created per job with fresh profiles to minimize fingerprint collision. Stealth mode via playwright-stealth and custom navigator properties.

**Queue Design**: Primary queue → Worker → Success/Failed. On transient failure: dead-letter exchange → retry queue with backoff → re-queue. On terminal failure: permanent failure table for manual review.

**Proxy Strategy**: Each worker maintains a pool of sticky sessions (IP:port pairs). On ERR_TUNNEL: mark session unhealthy, borrow from pool, apply cooldown. Sessions rotate on schedule or on error threshold.

**Circuit Breaker**: Per-target-site circuit breaker. Opens after N consecutive failures, half-open after cooldown, closes after M successes. Prevents cascade failures under anti-bot blocks.

**Database Schema**:
- `jobs` — Job definitions with target URL, site, parameters
- `runs` — Execution instances linking jobs to queue messages
- `results` — Scraped data with validation status
- `errors` — Classified errors with transient/terminal flag
- `proxy_sessions` — Session health tracking
- `circuit_states` — Per-site circuit breaker state

### File Organization

```
src/
├── __init__.py
├── scraper/           # Scraper logic (site-agnostic base)
│   └── extractors/    # Site-specific extraction
├── workers/           # Queue consumers and retry logic
├── proxy/             # Proxy abstraction layer
├── database/          # DB models and repos
├── llm/               # Post-processing
├── api/               # FastAPI routes
├── config/            # Settings
└── utils/             # Shared utilities
```

### Entry Points

- `src/workers/consumer.py` — CLI: `python -m workers.consumer`
- `src/workers/publisher.py` — CLI: `python -m workers.publisher`
- `src/api/main.py` — CLI: `uvicorn src.api.main:app`

### Docker Scaling

```yaml
services:
  worker:
    deploy:
      replicas: 8  # Scale via: docker-compose up -d --scale worker=16
    environment:
      - WORKER_ID=${WORKER_ID:-worker-${HOSTNAME}}
```

### Configuration Priority

1. Environment variables (highest priority)
2. .env file
3. config/settings.py defaults
4. Site-specific YAML (lowest priority)