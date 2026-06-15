# Specification: Requirements:
(1) We will setup a fresh instance of our framework and scrapers that you can work with. You can see and change the Python code.
(2) We will pay based on results, not per hour: Given an input batch to scrape we need valid scraped results beyond a certain threshold plus an explanation of why some parts could not be scraped. We need an explanation and a process to recover the failed submissions or mark them as permanent errors.

We run Python/Playwright scrapers against certain websites. The extraction works — our problem is stability and throughput at scale. We've already shipped multiple fixes and know the target sites well. We need an expert to help close the long tail, not someone to start from scratch.

Stack: Python, Playwright (headed Chromium + Xvfb, stealth), Oxylabs residential proxy, RabbitMQ worker fleet (Docker Compose, scaled) with custom retry/dead-letter/circuit-break logic, PostgreSQL, LLM post-processing.

Failure modes we're fighting:
- Proxy throttling — colliding exits trip Oxylabs ERR_TUNNEL on a shared IP under scale (one incident: 8 workers, ~2,200 tunnel errors, ~250 dropped keys). We've added unique exits/sticky sessions/backoff and want an expert second opinion.
- Transient-vs-terminal misclassification — keys silently dropped or retried for minutes, starving workers.
- Anti-bot — cookie banners, intermittent captchas, headless detection.
- Infra races — Xvfb lock/stale-DISPLAY on container restart; slow renders tripping fixed timeouts.

## 1. Project Overview

**Project:** Requirements:
(1) We will setup a fresh instance of our framework and scrapers that you can work with. You can see and change the Python code.
(2) We will pay based on results, not per hour: Given an input batch to scrape we need valid scraped results beyond a certain threshold plus an explanation of why some parts could not be scraped. We need an explanation and a process to recover the failed submissions or mark them as permanent errors.

We run Python/Playwright scrapers against certain websites. The extraction works — our problem is stability and throughput at scale. We've already shipped multiple fixes and know the target sites well. We need an expert to help close the long tail, not someone to start from scratch.

Stack: Python, Playwright (headed Chromium + Xvfb, stealth), Oxylabs residential proxy, RabbitMQ worker fleet (Docker Compose, scaled) with custom retry/dead-letter/circuit-break logic, PostgreSQL, LLM post-processing.

Failure modes we're fighting:
- Proxy throttling — colliding exits trip Oxylabs ERR_TUNNEL on a shared IP under scale (one incident: 8 workers, ~2,200 tunnel errors, ~250 dropped keys). We've added unique exits/sticky sessions/backoff and want an expert second opinion.
- Transient-vs-terminal misclassification — keys silently dropped or retried for minutes, starving workers.
- Anti-bot — cookie banners, intermittent captchas, headless detection.
- Infra races — Xvfb lock/stale-DISPLAY on container restart; slow renders tripping fixed timeouts.
**GitHub Repo:** https://github.com/9KMan/JOB-20260615143959-000098
**Lead:** 
**Client:** Upwork Client (Worldwide)
**Tier:** EXPERT
**Budget:** 
**Rate:** N/A
**Timeline:** 4-8 weeks

## 2. Technical Stack

Python · Playwright · Chromium · Oxylabs · RabbitMQ · PostgreSQL · Docker

## 3. Architecture

- Backend: Python (FastAPI/Flask/Django) REST API
- Database: PostgreSQL with proper indexing
- AI/ML: Model integration (OpenAI/Anthropic API or self-hosted)
- DevOps: Docker + docker-compose for containerization

### API Design
- RESTful endpoints with JSON request/response
- Authentication via JWT (HS256) or bcrypt
- Middleware for logging, error handling, CORS
- Versioned routes (/api/v1/...) where applicable

### Data Layer
- PostgreSQL as primary datastore
- Connection pooling via PGBouncer or similar
- Migration management via Alembic or raw SQL
- Indexes on foreign keys and high-cardinality columns

### Frontend (if applicable)
- Single-page application or server-rendered pages
- Responsive UI with modern CSS/JS framework
- State management for complex client-side logic

## 4. Data Model

### Core Entities
- Define entity schema based on job requirements
- Use UUIDs for primary keys (not auto-increment)
- Add created_at / updated_at timestamps to all tables
- Soft-delete pattern where appropriate

### Relationships
- Foreign key constraints with ON DELETE CASCADE
- Many-to-many via junction tables
- Eager loading for nested relationships in API

## 5. Project Structure

```
├── api/                  # FastAPI / Express routes + schemas
├── models/               # DB models / SQLAlchemy / Prisma
├── services/             # Business logic layer
├── workers/              # Background jobs (Celery, BullMQ, etc.)
├── migrations/           # DB migrations (Alembic / Flyway)
├── tests/                # Unit + integration tests
├── Dockerfile            # Production container
├── docker-compose.yml    # Local dev environment
└── README.md             # Setup instructions
```

## 6. Out of Scope

- Mobile apps (web only unless explicitly specified)
- Multi-tenant / white-label customization

## 7. Acceptance Criteria

- [ ] Database schema created with migrations applied
- [ ] Frontend UI implemented, responsive, and functional
- [ ] Docker image builds and runs successfully
- [ ] AI/ML pipeline integrated and functional

**GitHub Repo:** https://github.com/9KMan/JOB-20260615143959-000098
