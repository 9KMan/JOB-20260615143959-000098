# Out of Scope Boundaries

This document defines explicit boundaries for this engagement. The client needs stability and throughput fixes for their existing scraper fleet—not a ground-up rebuild.

## Scope Decision Framework

For any proposed work, apply this test:
1. Does it solve a **known failure mode** in the client's list? (proxy throttling, transient-vs-terminal, anti-bot, infra races)
2. Is it within the **existing stack**? (Python, Playwright, Oxylabs, RabbitMQ, PostgreSQL)
3. Does it **improve** an existing component rather than replace it?

If all answers are yes → potentially in scope.
If any answer is no → out of scope.

## Out of Scope Items

### 1. New Scraper Development
- **Not Built:** New website scrapers or target site additions
- **Rationale:** Client states "extraction works" and "know target sites well"
- **Boundary:** Work is limited to improving reliability of existing scrapers

### 2. Scraping Framework Core Architecture
- **Not Built:** Redesign of Playwright/stealth browser framework
- **Not Built:** New browser engine integrations (Firefox, WebKit)
- **Rationale:** Existing framework is functional; focus is on operational stability
- **Boundary:** Only bug fixes and hardening within existing architecture

### 3. Proxy Infrastructure
- **Not Built:** Proxy provider evaluation or switching (e.g., replacing Oxylabs)
- **Not Built:** Custom proxy rotation logic outside existing sticky-session/backoff patterns
- **Rationale:** Client has already invested in Oxylabs and implemented exit/sticky-session fixes
- **Boundary:** Only help optimize existing Oxylabs integration

### 4. Message Broker Redesign
- **Not Built:** Migration from RabbitMQ to alternative (Kafka, Redis Streams, SQS)
- **Not Built:** Fundamental queue topology changes
- **Rationale:** Existing RabbitMQ setup with retry/dead-letter/circuit-break logic exists
- **Boundary:** Only tune existing configuration parameters

### 5. Database Schema Changes
- **Not Built:** New database engines or ORM frameworks
- **Not Built:** Schema migrations that change core entity structure
- **Rationale:** PostgreSQL schema likely stable; focus is scraping reliability
- **Boundary:** Only add indexes or columns needed for failure tracking

### 6. LLM Integration Overhaul
- **Not Built:** Training or fine-tuning of LLM models
- **Not Built:** Switching LLM providers (OpenAI ↔ Anthropic ↔ self-hosted)
- **Not Built:** Vector database or RAG implementation
- **Rationale:** "LLM post-processing" exists; not evaluating the approach itself
- **Boundary:** Only optimize prompts or error classification logic

### 7. User-Facing Components
- **Not Built:** REST API endpoints (beyond minimal job submission/status)
- **Not Built:** Admin dashboard or monitoring UI
- **Not Built:** User authentication/authorization systems
- **Rationale:** No user-facing product mentioned in requirements
- **Boundary:** Only worker/dashboard infrastructure if explicitly needed for debugging

### 8. Mobile & Multi-Platform
- **Not Built:** Mobile applications (iOS/Android)
- **Not Built:** Desktop application packaging
- **Rationale:** Explicitly out of scope per project spec
- **Boundary:** N/A

### 9. Infrastructure Orchestration
- **Not Built:** Kubernetes or ECS migration
- **Not Built:** Helm charts or advanced Kubernetes operators
- **Not Built:** Service mesh implementation (Istio, Linkerd)
- **Rationale:** Client uses Docker Compose at defined scale
- **Boundary:** Only docker-compose scaling optimizations

### 10. CI/CD Pipeline
- **Not Built:** Full CI/CD implementation (GitHub Actions, Jenkins, etc.)
- **Not Built:** Automated deployment pipelines
- **Not Built:** Blue-green or canary deployment infrastructure
- **Rationale:** Not mentioned in requirements; focus is on scraping stability
- **Boundary:** Only provide scripts if needed to reproduce test scenarios

### 11. Performance Optimization (Greenfield)
- **Not Built:** Algorithmic optimizations to working code paths
- **Not Built:** Memory profiling or GC tuning for Python runtime
- **Not Built:** CDN or caching layer implementation
- **Rationale:** "Extraction works" — only broken paths get fixes
- **Boundary:** Only optimize specifically identified failure points

### 12. Security Hardening
- **Not Built:** Penetration testing
- **Not Built:** Security audit or compliance certification
- **Not Built:** SSL/TLS infrastructure changes
- **Rationale:** Not in requirements; assume existing security posture is acceptable
- **Boundary:** Only if security issues block scraping operations

### 13. Documentation
- **Not Built:** User documentation or API documentation site
- **Not Built:** Architecture decision records (ADRs) beyond inline comments
- **Not Built:** Runbook or operational procedure documentation
- **Rationale:** Client already knows the system
- **Boundary:** Only brief inline comments explaining failure classification logic

### 14. Code Review of Working Components
- **Not Built:** Refactoring of code that works but doesn't meet style preferences
- **Not Built:** Dependency version upgrades unless security-critical
- **Not Built:** Technical debt reduction in stable code paths
- **Rationale:** "We've already shipped multiple fixes" — working code stays working
- **Boundary:** Only touch working code if it directly causes failures

## Change Request Process

If client requests out-of-scope work:
1. Identify which out-of-scope category applies
2. Provide rough effort estimate for the request
3. Recommend whether it should be a separate engagement or deferred
4. Do not implement without explicit scope change approval
