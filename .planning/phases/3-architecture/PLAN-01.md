---
title: "Phase 03: Architecture"
objective: "Define the complete system architecture including component interactions, data flows, API contracts, and infrastructure layout for the distributed scraping fleet."
done_when:
  - Architecture diagram with all components and their relationships
  - API contracts documented (request/response schemas)
  - Data flow diagrams for each scraping lifecycle path
  - Directory structure defined and agreed upon
  - Container orchestration strategy defined
  - Message queue topology and exchange patterns designed
  - Error classification taxonomy established
---

## Objective

Design the complete system architecture for a distributed web scraping platform that handles proxy throttling, anti-bot detection, and transient vs terminal error classification at scale. The architecture must support horizontally scalable workers, reliable message processing, and LLM-assisted result enrichment.

## Deliverables

## 1. System Architecture Overview

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SYSTEMS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────────┐   │
│  │   Input     │     │   Target Sites  │     │    Oxylabs Proxy        │   │
│  │   Batch     │     │   (Playwright)  │     │    Residential API      │   │
│  │   (JSON)    │     └────────┬────────┘     └───────────┬─────────────┘   │
│  └──────┬──────┘              │                         │                 │
│         │                     │                         │                 │
└─────────┼─────────────────────┼─────────────────────────┼─────────────────┘
          │                     │                         │
          ▼                     ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            API LAYER (FastAPI)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  /api/v1/    │  │  /api/v1/    │  │  /api/v1/    │  │  /api/v1/    │   │
│  │  batches     │  │  jobs        │  │  results     │  │  errors      │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Authentication Middleware                        │   │
│  │                    Rate Limiting / CORS                             │   │
│  │                    Request Logging                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                     │                         │
          ▼                     ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MESSAGE QUEUE LAYER (RabbitMQ)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Exchange: scraping.direct                    │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │   │
│  │  │ Queue: scraping  │  │ Queue: scraping  │  │ Queue: scraping  │   │   │
│  │  │ .work.primary    │  │ .work.retry      │  │ .work.dead       │   │   │
│  │  │ (durable)        │  │ (durable, TTL)   │  │ (durable)        │   │   │
│  │  └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘   │   │
│  └───────────┼────────────────────┼────────────────────────────────────┘   │
│              │                    │                                        │
│              ▼                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              DLX: scraping.dlx (dead-letter-exchange)                │   │
│  │  • Retry attempts exhausted → dead letter                            │   │
│  │  • Circuit breaker tripped → pause processing                        │   │
│  │  • Permanent error detected → mark terminal                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WORKER LAYER (Docker Fleet)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  Worker Node 1  │  │  Worker Node N  │  │  Worker Node N   │             │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │             │
│  │  │ Playwright│  │  │  │ Playwright│  │  │  │ Playwright│  │             │
│  │  │ Browser   │  │  │  │ Browser   │  │  │  │ Browser   │  │             │
│  │  │ Instance  │  │  │  │ Instance  │  │  │  │ Instance  │  │             │
│  │  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │             │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │             │
│  │  │ Proxy     │  │  │  │ Proxy     │  │  │  │ Proxy     │  │             │
│  │  │ Session   │  │  │  │ Session   │  │  │  │ Session   │  │             │
│  │  │ Manager   │  │  │  │ Manager   │  │  │  │ Session   │  │             │
│  │  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Circuit Breaker State Machine                          │   │
│  │  CLOSED → OPEN → HALF-OPEN → CLOSED                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER (PostgreSQL)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  batches     │  │  scrape_jobs │  │  results     │  │  error_log   │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │  proxies     │  │  circuit_    │  │  retry_      │                      │
│  │              │  │  breaker_    │  │  attempts    │                      │
│  │              │  │  state       │  │              │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LLM POST-PROCESSING LAYER                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  Result Queue   │──│  LLM Worker     │──│  Enriched       │             │
│  │  (separate MQ)  │  │  (async)        │  │  Results        │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • Structured extraction from raw HTML/text                        │   │
│  │  • Error explanation generation                                    │   │
│  │  • Data validation and normalization                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. API Design

### Base URL Structure
```
/api/v1/
```

### Authentication
- JWT Bearer tokens (HS256)
- Token expiry: 24 hours
- Refresh token rotation

### Endpoints

#### Batches

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/batches` | Create new scraping batch |
| GET | `/batches` | List batches (paginated) |
| GET | `/batches/{id}` | Get batch details with progress |
| DELETE | `/batches/{id}` | Cancel/soft-delete batch |

**POST /batches**
```json
// Request
{
  "name": "string",
  "priority": "normal|high|low",
  "items": [
    {
      "url": "https://target-site.com/page/1",
      "metadata": {
        "batch_id": "ext-123",
        "category": "products"
      },
      "site_config": "default"  // references pre-configured site profile
    }
  ],
  "callback_url": "https://client.com/webhook" // optional
}

// Response 202 Accepted
{
  "batch_id": "uuid",
  "status": "queued",
  "total_items": 100,
  "estimated_completion": "2024-01-15T10:00:00Z"
}
```

**GET /batches/{id}**
```json
// Response
{
  "batch_id": "uuid",
  "name": "January Product Scrape",
  "status": "in_progress",
  "progress": {
    "total": 1000,
    "pending": 200,
    "in_progress": 50,
    "completed": 740,
    "failed": 10
  },
  "created_at": "2024-01-15T08:00:00Z",
  "updated_at": "2024-01-15T09:30:00Z"
}
```

#### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/jobs` | List jobs with filters |
| GET | `/jobs/{id}` | Get job details |
| POST | `/jobs/{id}/retry` | Manually retry failed job |
| POST | `/jobs/{id}/mark-terminal` | Mark as permanent failure |

**GET /jobs/{id}**
```json
// Response
{
  "job_id": "uuid",
  "batch_id": "uuid",
  "url": "https://target-site.com/page/1",
  "status": "failed",
  "error": {
    "code": "ERR_TUNNEL_PROXY",
    "category": "transient",
    "message": "Oxylabs tunnel establishment failed",
    "attempts": 5,
    "last_attempt": "2024-01-15T09:28:00Z",
    "proxy_exit": "us-tx-1.proxyscrape.net:7777"
  },
  "result": null,
  "created_at": "2024-01-15T08:00:00Z",
  "completed_at": null
}
```

#### Results

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/results` | List results with filters |
| GET | `/results/{id}` | Get full result with enriched data |
| GET | `/batches/{id}/results` | Download batch results (CSV/JSON) |

#### Errors

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/errors/summary` | Aggregate error statistics |
| GET | `/errors/recoverable` | List recoverable errors |
| POST | `/errors/bulk-retry` | Retry multiple failed jobs |

### Error Response Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": [
      {"field": "items[0].url", "issue": "Invalid URL format"}
    ]
  },
  "request_id": "uuid"
}
```

## 3. Directory Structure

```
scraping-platform/
├── api/                          # FastAPI application
│   ├── __init__.py
│   ├── main.py                   # App entry point
│   ├── config.py                 # Configuration loader
│   ├── dependencies.py           # FastAPI dependencies
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── batches.py            # Batch CRUD endpoints
│   │   ├── jobs.py               # Job management endpoints
│   │   ├── results.py            # Results endpoints
│   │   └── errors.py             # Error handling endpoints
│   ├── schemas/                  # Pydantic models
│   │   ├── __init__.py
│   │   ├── batch.py
│   │   ├── job.py
│   │   ├── result.py
│   │   └── common.py
│   └── middleware/
│       ├── __init__.py
│       ├── auth.py               # JWT authentication
│       ├── logging.py            # Request logging
│       └── rate_limit.py         # Rate limiting
│
├── workers/                      # Worker implementations
│   ├── __init__.py
│   ├── base.py                   # Base worker class
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── browser.py            # Playwright browser management
│   │   ├── page.py               # Page interaction logic
│   │   ├── stealth.py            # Stealth mode configurations
│   │   └── site_configs/         # Per-site extraction configs
│   │       ├── __init__.py
│   │       ├── default.py
│   │       ├── site_a.py
│   │       └── site_b.py
│   ├── proxy/
│   │   ├── __init__.py
│   │   ├── manager.py            # Proxy session management
│   │   ├── oxylabs.py            # Oxylabs API client
│   │   └── health_checker.py     # Proxy health monitoring
│   ├── queue/
│   │   ├── __init__.py
│   │   ├── consumer.py           # RabbitMQ consumer
│   │   ├── publisher.py          # RabbitMQ publisher
│   │   └── handlers.py           # Message handlers
│   └── llm/
│       ├── __init__.py
│       ├── processor.py          # LLM result enrichment
│       └── prompts.py            # Prompt templates
│
├── core/                         # Core shared utilities
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   ├── logging.py                # Structured logging
│   ├── metrics.py                # Prometheus metrics
│   └── circuit_breaker.py        # Circuit breaker implementation
│
├── models/                       # SQLAlchemy models
│   ├── __init__.py
│   ├── base.py                   # Base model class
│   ├── batch.py
│   ├── job.py
│   ├── result.py
│   ├── error_log.py
│   └── proxy_state.py
│
├── services/                     # Business logic services
│   ├── __init__.py
│   ├── batch_service.py
│   ├── job_service.py
│   ├── scrape_service.py
│   ├── error_classifier.py       # Transient vs terminal classification
│   └── recovery_service.py       # Error recovery logic
│
├── migrations/                   # Alembic migrations
│   ├── versions/
│   │   └── 001_initial_schema.py
│   └── alembic.ini
│
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── unit/
│   │   ├── test_error_classifier.py
│   │   ├── test_circuit_breaker.py
│   │   └── test_proxy_manager.py
│   ├── integration/
│   │   ├── test_api_batches.py
│   │   ├── test_worker_scraping.py
│   │   └── test_queue_handling.py
│   └── fixtures/
│       ├── sample_batch.json
│       └── site_responses.py
│
├── docker/
│   ├── api/
│   │   └── Dockerfile
│   ├── worker/
│   │   └── Dockerfile
│   └── xvfbd/
│       └── Dockerfile
│
├── docker-compose.yml            # Full stack orchestration
├── docker-compose.dev.yml        # Development overrides
├── docker-compose.prod.yml       # Production overrides
├── pyproject.toml
├── poetry.lock
├── pytest.ini
├── .env.example
└── README.md
```

## 4. Message Queue Topology

### Exchange Configuration

```
Exchange: scraping.direct (type: direct, durable: true)
├── Queue: scraping.work.primary
│   ├── Routing Key: scrape
│   ├── durable: true
│   ├── x-dead-letter-exchange: scraping.dlx
│   ├── x-dead-letter-routing-key: dead
│   └── arguments:
│       └── x-max-priority: 10
│
├── Queue: scraping.work.retry
│   ├── Routing Key: retry
│   ├── durable: true
│   ├── x-message-ttl: {exponential backoff}
│   └── x-dead-letter-exchange: scraping.direct
│   └── x-dead-letter-routing-key: scrape
│
└── Queue: scraping.work.dead
    ├── Routing Key: dead
    ├── durable: true
    └── Max length: 100000

Exchange: scraping.dlx (type: direct, durable: true)
└── Dead letter handling queue for failed jobs
```

### Message Schema

**Scrape Job Message**
```json
{
  "message_id": "uuid",
  "batch_id": "uuid",
  "job_id": "uuid",
  "url": "https://target-site.com/page",
  "site_config": "default",
  "metadata": {
    "attempt": 1,
    "max_attempts": 5,
    "callback_url": null,
    "client_id": "uuid"
  },
  "retry_context": {
    "previous_errors": [],
    "proxy_session_id": null,
    "circuit_breaker_state": "closed"
  },
  "created_at": "2024-01-15T08:00:00Z",
  "headers": {
    "x-request-id": "uuid"
  }
}
```

**Retry Message (TTL-based)**
```json
{
  "message_id": "uuid",
  "original_job_id": "uuid",
  "retry_count": 2,
  "delay_seconds": 60,
  "reason": "ERR_TUNNEL_PROXY",
  "next_retry_at": "2024-01-15T08:01:00Z"
}
```

## 5. Error Classification Taxonomy

### Error Categories

```
Error Classification
├── TRANSIENT
│   ├── Proxy Errors
│   │   ├── ERR_TUNNEL_CONNECTION_FAILED
│   │   ├── ERR_TUNNEL_TIMEOUT
│   │   └── ERR_PROXY_AUTH_FAILED
│   ├── Network Errors
│   │   ├── ERR_CONNECTION_TIMEOUT
│   │   ├── ERR_CONNECTION_RESET
│   │   └── ERR_DNS_RESOLUTION
│   ├── Anti-Bot (Potentially bypassable)
│   │   ├── ERR_CLOUDFLARE_CHECK
│   │   ├── ERR_RATE_LIMIT (soft)
│   │   └── ERR_COOKIE_REQUIRED
│   └── Browser Errors
│       ├── ERR_PAGE_TIMEOUT
│       └── ERR_RESOURCE_LOAD_FAILED
│
├── TERMINAL
│   ├── Blocked
│   │   ├── ERR_IP_BANNED
│   │   ├── ERR_DOMAIN_BLOCKED
│   │   └── ERR_CAPTCHA_UNSOLVABLE
│   ├── Not Found
│   │   ├── ERR_404
│   │   └── ERR_410
│   ├── Invalid Target
│   │   ├── ERR_INVALID_URL
│   │   ├── ERR_MALFORMED_RESPONSE
│   │   └── ERR_PARSING_FAILED
│   └── Permanent Failure
│       └── ERR_SITE_MOVED_PERMANENTLY
│
└── UNKNOWN (requires LLM analysis)
```

### Classification Rules Engine

```python
# Pseudo-code for error classification
classification_rules = {
    # Immediate terminal
    "ERR_404": Terminal,
    "ERR_410": Terminal,
    "ERR_IP_BANNED": Terminal,
    "ERR_CAPTCHA_UNSOLVABLE": Terminal,
    "ERR_INVALID_URL": Terminal,
    
    # Likely transient with retry budget
    "ERR_TUNNEL_CONNECTION_FAILED": Transient(max_retries=5, backoff="exponential"),
    "ERR_CONNECTION_TIMEOUT": Transient(max_retries=3, backoff="linear"),
    "ERR_RATE_LIMIT": Transient(max_retries=2, backoff="fixed"),
    "ERR_CLOUDFLARE_CHECK": Transient(max_retries=2, backoff="exponential"),
    
    # Unknown - queue for LLM analysis
    "ERR_UNKNOWN": RequiresAnalysis,
}
```

## 6. Circuit Breaker Design

### State Machine

```
┌─────────┐                    ┌─────────┐
│ CLOSED  │──── failure ≥ 5 ───▶│  OPEN   │
│ (0.05)  │◀─── success ≥ 3 ───│ (1.0)   │
└─────────┘                    └─────────┘
     ▲                              │
     │                              │ timeout (30s)
     │                              ▼
     │                         ┌──────────┐
     └─────────────────────────│ HALF-OPEN│
                               │  (0.5)   │
                               └──────────┘
```

### Per-Proxy Circuit Breaker

- Track failure rate per proxy exit IP
- Trip at 50% failure rate over 10 requests
- Half-open: allow 1 request through
- Reset on 3 consecutive successes
- Global circuit breaker: trip all if >30% of proxies failing

## 7. Data Flow Diagrams

### Happy Path Flow

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Input  │───▶│  API    │───▶│RabbitMQ │───▶│ Worker  │───▶│Target   │
│  Batch  │    │  Store  │    │  Queue  │    │ Browser │    │ Site    │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                     │                                                     │
                     │ Job Created                                        │
                     ▼                                                     │
               ┌─────────┐                                                │
               │Postgres │◀───────────────────────────────────────────────┘
               │  Jobs   │                                                │
               └─────────┘                                                │
                     │                                                     │
                     │ HTML/Response                              ┌─────────┴───┐
                     ▼                                              │  Extract &  │
               ┌─────────┐                                    ┌─────────┴─┴───┐  │
               │ LLM     │                                    │ Proxy Health  │
               │ Enrich  │                                    │ Update        │
               └─────────┘                                    └───────────────┘  │
                     │                                                     │
                     ▼                                                     │
               ┌─────────┐                                                │
               │Postgres │                                                │
               │ Results │                                                │
               └─────────┘                                                │
```

### Error Recovery Flow

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Error  │───▶│ Error   │───▶│ Class-  │───▶│ Transit-│───▶│  Retry  │
│ Occurs  │    │  Logger │    │  ifier  │    │  ive?   │    │  Queue  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
                                                           │
                    ┌──────────────────────────────────────┤
                    │                                      │
                    ▼                                      ▼
              ┌─────────┐                           ┌─────────────┐
              │ Max     │────── No ─────────────────│ Backoff &   │
              │ Retries?│                           │ Re-enqueue  │
              └─────────┘                           └─────────────┘
                    │
                    │ Yes
                    ▼
              ┌─────────┐
              │ Mark    │──────▶ Dead Letter Queue
              │ Terminal │              (for review)
              └─────────┘
                    │
                    ▼
              ┌─────────┐
              │ Postgres│
              │ Update  │
              │ Status  │
              └─────────┘
```

## 8. Docker Orchestration

### Service Definitions

```yaml
# docker-compose.yml structure
services:
  # API Layer
  api:
    build: ./docker/api
    environment:
      - DATABASE_URL
      - RABBITMQ_URL
      - JWT_SECRET
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  # Worker Fleet
  scraper-worker:
    build: ./docker/worker
    environment:
      - BROWSER_HEADLESS=false
      - DISPLAY=:99
    volumes:
      - /tmp/.X99-lock
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2'
          memory: 4G
    depends_on:
      - xvfbd
      - rabbitmq

  # X Virtual Framebuffer
  xvfbd:
    build: ./docker/xvfbd
    ports:
      - "5999:99"
    volumes:
      - /tmp/.X99-lock

  # RabbitMQ
  rabbitmq:
    image: rabbitmq:3.12-management
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    environment:
      - RABBITMQ_DEFAULT_USER
      - RABBITMQ_DEFAULT_PASS

  # PostgreSQL
  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    command: postgres -c max_connections=200

  # Prometheus (metrics)
  prometheus:
    image: prom/prometheus:latest

  # Grafana (dashboards)
  grafana:
    image: grafana/grafana:latest

volumes:
  rabbitmq_data:
  postgres_data:
```

### Worker Scaling Strategy

```yaml
# Scale based on queue depth
# HPA configuration (Kubernetes-style) for docker-compose or K8s
worker_scaling:
  min_replicas: 2
  max_replicas: 20
  scale_up_threshold: 100  # messages in queue
  scale_up_cooldown: 60s
  scale_down_threshold: 10
  scale_down_cooldown: 300s
```

## 9. Component Responsibilities

### API Layer
- Batch ingestion and validation
- Job status queries
- Result retrieval
- Authentication/authorization
- Rate limiting

### Worker Layer
- Browser lifecycle management
- Proxy rotation and health
- Page scraping and extraction
- Error handling and classification
- Message acknowledgment

### Core Services
- `ErrorClassifierService`: Analyzes errors to determine retry strategy
- `RecoveryService`: Handles recoverable error recovery
- `ProxyHealthService`: Monitors and rotates proxy pool
- `CircuitBreakerService`: Manages failure thresholds

### Database Layer
- Persistent job state
- Result storage
- Error logging and analysis
- Proxy performance tracking

## 10. Key Design Decisions

1. **Dual Queue Pattern**: Separate retry queue with TTL for exponential backoff, avoiding requeue complexity
2. **Per-Worker Proxy Sessions**: Each worker maintains a sticky proxy session to reduce tunnel collisions
3. **Async LLM Processing**: Results flow to separate queue for LLM enrichment, not blocking scrape pipeline
4. **Circuit Breaker Hierarchy**: Per-proxy → Per-site → Global breakers for granular failure isolation
5. **Terminal Error Marking**: Human-in-the-loop for terminal classification on edge cases
6. **Dead Letter Review**: Failed jobs accumulate in DLQ for batch recovery operations

---

## Done When Criteria

- [x] Complete component diagram with all systems and interfaces
- [x] All API endpoints defined with request/response schemas
- [x] Message queue topology designed with DLX pattern
- [x] Error classification taxonomy established
- [x] Circuit breaker design documented
- [x] Data flow diagrams for all major paths
- [x] Directory structure defined
- [x] Docker orchestration strategy specified
- [x] Component responsibilities clearly assigned
- [x] Key design decisions rationale documented