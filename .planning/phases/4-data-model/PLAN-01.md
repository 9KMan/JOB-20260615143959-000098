---
title: "Phase 04: Data Model"
objective: "Define PostgreSQL schema for tracking scrape jobs, tasks, results, failures, proxy sessions, and worker state with proper indexing for high-throughput worker fleet operations."
done_when:
  - Schema supports batch/job/task hierarchy
  - Failure classification (transient vs terminal) is modelable
  - Proxy session state and tunnel errors are tracked
  - Worker state and circuit breaker status is persisted
  - Indexes cover all query patterns used by workers
  - Migrations are reproducible via Alembic
  - Soft-delete pattern implemented where appropriate
---
## Objective

Design PostgreSQL data model for web scraping framework with emphasis on: job orchestration, task state machine, failure tracking with classification, proxy session management, worker fleet state, and LLM post-processing results. Schema must support high-throughput worker operations with proper connection pooling considerations.

## Deliverables

- migrations/versions/001_initial_schema.py
- models/__init__.py
- models/job.py
- models/scrape_task.py
- models/result.py
- models/failure.py
- models/proxy_session.py
- models/worker.py
- models/enums.py
- alembic.ini
- alembic/env.py

## Database Schema

### Core Entities

#### 1. Job (Batch)
```
jobs
├── id (UUID, PK)
├── name (VARCHAR 255, nullable)
├── status (ENUM: pending, running, paused, completed, failed)
├── total_tasks (INTEGER)
├── completed_tasks (INTEGER)
├── failed_tasks (INTEGER)
├── created_at (TIMESTAMP)
├── updated_at (TIMESTAMP)
├── completed_at (TIMESTAMP, nullable)
└── metadata (JSONB) -- input params, priority, etc.
```

#### 2. ScrapeTask
```
scrape_tasks
├── id (UUID, PK)
├── job_id (UUID, FK -> jobs.id)
├── url (TEXT)
├── priority (INTEGER, default 0)
├── status (ENUM: pending, claimed, processing, completed, failed, dead_letter)
├── attempt_count (INTEGER, default 0)
├── max_attempts (INTEGER, default 5)
├── circuit_state (ENUM: closed, open, half_open)
├── circuit_opened_at (TIMESTAMP, nullable)
├── claimed_by (UUID, nullable) -- worker instance ID
├── claimed_at (TIMESTAMP, nullable)
├── result_id (UUID, FK -> scrape_results.id, nullable)
├── failure_id (UUID, FK -> scrape_failures.id, nullable)
├── created_at (TIMESTAMP)
├── updated_at (TIMESTAMP)
├── completed_at (TIMESTAMP, nullable)
├── next_retry_at (TIMESTAMP, nullable)
├── metadata (JSONB) -- page-specific params, selectors, etc.
└── INDEXES: (job_id, status), (status, next_retry_at), (claimed_by)
```

#### 3. ScrapeResult
```
scrape_results
├── id (UUID, PK)
├── task_id (UUID, FK -> scrape_tasks.id)
├── status_code (INTEGER)
├── content_hash (VARCHAR 64, nullable) -- dedup
├── raw_html (TEXT, nullable) -- truncated for storage
├── extracted_data (JSONB) -- structured extraction
├── llm_processed (BOOLEAN, default false)
├── llm_result (JSONB, nullable)
├── llm_error (TEXT, nullable)
├── scrape_duration_ms (INTEGER)
├── proxy_session_id (UUID, FK -> proxy_sessions.id)
├── created_at (TIMESTAMP)
└── INDEXES: (task_id), (created_at)
```

#### 4. ScrapeFailure
```
scrape_failures
├── id (UUID, PK)
├── task_id (UUID, FK -> scrape_tasks.id)
├── error_code (VARCHAR 50) -- e.g., ERR_TUNNEL, CAPTCHA, TIMEOUT, ANTI_BOT
├── error_category (ENUM: transient, terminal, unknown)
├── error_message (TEXT)
├── stack_trace (TEXT, nullable)
├── attempt_number (INTEGER)
├── proxy_session_id (UUID, FK -> proxy_sessions.id, nullable)
├── is_retryable (BOOLEAN)
├── retry_count_at_failure (INTEGER)
├── created_at (TIMESTAMP)
└── INDEXES: (task_id), (error_code), (error_category), (created_at)
```

#### 5. ProxySession
```
proxy_sessions
├── id (UUID, PK)
├── proxy_host (VARCHAR 255)
├── proxy_port (INTEGER)
├── exit_ip (VARCHAR 45, nullable) -- resolved IP
├── session_key (VARCHAR 255, nullable) -- sticky session token
├── status (ENUM: active, exhausted, error, retired)
├── tunnel_error_count (INTEGER, default 0)
├── last_tunnel_error_at (TIMESTAMP, nullable)
├── last_error (TEXT, nullable)
├── last_used_at (TIMESTAMP)
├── created_at (TIMESTAMP)
├── cooldown_until (TIMESTAMP, nullable) -- backoff window
└── INDEXES: (status, cooldown_until), (exit_ip)
```

#### 6. WorkerInstance
```
worker_instances
├── id (UUID, PK)
├── instance_name (VARCHAR 100) -- container hostname
├── status (ENUM: healthy, degraded, offline)
├── current_job_id (UUID, FK -> jobs.id, nullable)
├── claimed_tasks (INTEGER, default 0)
├── completed_tasks (INTEGER, default 0)
├── failed_tasks (INTEGER, default 0)
├── circuit_breaker_global_state (ENUM: closed, open, half_open)
├── circuit_breaker_opened_at (TIMESTAMP, nullable)
├── last_heartbeat_at (TIMESTAMP)
├── created_at (TIMESTAMP)
└── INDEXES: (status), (circuit_breaker_global_state)
```

#### 7. RetryPolicy
```
retry_policies
├── id (UUID, PK)
├── name (VARCHAR 100)
├── error_codes (TEXT[]) -- applicable error codes
├── base_delay_seconds (INTEGER)
├── max_delay_seconds (INTEGER)
├── multiplier (FLOAT)
├── max_attempts (INTEGER)
├── is_active (BOOLEAN)
└── created_at (TIMESTAMP)
```

### Enums (PostgreSQL)

```sql
CREATE TYPE job_status AS ENUM ('pending', 'running', 'paused', 'completed', 'failed');
CREATE TYPE task_status AS ENUM ('pending', 'claimed', 'processing', 'completed', 'failed', 'dead_letter');
CREATE TYPE circuit_state AS ENUM ('closed', 'open', 'half_open');
CREATE TYPE failure_category AS ENUM ('transient', 'terminal', 'unknown');
CREATE TYPE proxy_status AS ENUM ('active', 'exhausted', 'error', 'retired');
CREATE TYPE worker_status AS ENUM ('healthy', 'degraded', 'offline');
```

## Index Strategy

```sql
-- Task polling (workers claim tasks)
CREATE INDEX idx_tasks_poll ON scrape_tasks (status, priority DESC, next_retry_at) 
  WHERE status IN ('pending', 'claimed');

-- Job progress tracking
CREATE INDEX idx_tasks_job_status ON scrape_tasks (job_id, status);

-- Failure analysis
CREATE INDEX idx_failures_category ON scrape_failures (error_category, created_at DESC);
CREATE INDEX idx_failures_error_code ON scrape_failures (error_code);

-- Proxy backoff queries
CREATE INDEX idx_proxy_cooldown ON proxy_sessions (status, cooldown_until) 
  WHERE status = 'active';

-- Worker heartbeat (cleanup stale)
CREATE INDEX idx_workers_heartbeat ON worker_instances (last_heartbeat_at);
```

## Migrations (Alembic)

### 001_initial_schema.py
```python
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create enums
    # Create tables with constraints
    # Create indexes
    # Insert default retry policies
```

## Done When

- [ ] All tables created with proper constraints and defaults
- [ ] UUID primary keys on all entities
- [ ] created_at/updated_at on all tables
- [ ] Enums created as PostgreSQL types
- [ ] Indexes cover: task polling, job status, failure categorization, proxy cooldown, worker heartbeat
- [ ] Alembic migrations apply cleanly (`alembic upgrade head`)
- [ ] Migration rollback works (`alembic downgrade -1`)
- [ ] Foreign keys have appropriate ON DELETE behavior
- [ ] JSONB columns for extensible metadata/extracted_data
- [ ] Default retry policies seeded for: ERR_TUNNEL, TIMEOUT, CAPTCHA, ANTI_BOT

## Technical Details

### Connection Pooling
- Use SQLAlchemy async with `asyncpg` for worker fleet
- Configure PGBouncer: pool_mode=transaction, default_pool_size=20
- Connection timeout: 5 seconds
- Statement timeout: 30 seconds (configurable per query)

### Transaction Handling
- Workers use short transactions (claim task -> process -> update)
- Long-running LLM processing happens outside transaction
- Use `SELECT FOR UPDATE SKIP LOCKED` for task claiming to prevent race conditions

### Failure Classification Heuristics
```
terminal_errors = ['HTTP_403', 'HTTP_451', 'PERMANENT_BLOCK', 'ACCOUNT_LOCKED']
transient_errors = ['ERR_TUNNEL', 'TIMEOUT', 'RATE_LIMIT', 'CONNECTION_RESET']

Classification stored in scrape_failures.error_category
Default to 'unknown', manual review queue for reclassification
```

### Soft Deletes
- Do NOT implement soft delete on scrape_tasks (high volume, cleanup via partition)
- Implement soft delete on jobs (preserve historical context)
- Results and failures: retain for 90 days, then archive/purge

### Partitioning Consideration (Future)
- Partition scrape_tasks by created_at month for archival
- Partition scrape_failures by created_at for retention policies