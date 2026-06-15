# Web Scraping Infrastructure Platform

> Production-grade distributed web scraping system with Python, Playwright, RabbitMQ worker fleet, and LLM post-processing.

---

## Business Problem Solved

### The Core Challenge

This project addresses a critical operational challenge: **achieving reliable, scalable web scraping at production scale** with predictable throughput and comprehensive failure handling. The client runs Python/Playwright scrapers against target websites, and while extraction logic works correctly, the infrastructure struggles with:

1. **Proxy Throttling and IP Collisions**: When scaling to 8+ workers, shared Oxylabs exit nodes collide and trigger `ERR_TUNNEL` errors. One documented incident resulted in ~2,200 tunnel errors and ~250 dropped message keys within a single run.

2. **Transient vs. Terminal Failure Misclassification**: The system cannot reliably distinguish between temporary failures (network timeout, rate limiting) and permanent errors (site blocking, captcha). This causes two problems:
   - Transient failures are retried indefinitely, starving workers
   - Terminal failures are retried unnecessarily, wasting resources

3. **Anti-Bot Evasion Complexity**: Target sites deploy cookie banners, intermittent CAPTCHAs, and headless browser detection that cause intermittent failures.

4. **Infrastructure Races**: Container restarts trigger Xvfb lock conflicts, stale DISPLAY sockets, and slow page renders that exceed fixed timeouts.

### Business Impact

The deliverables solve these specific business problems:

| Problem | Solution Delivered |
|---------|-------------------|
| Proxy collisions | Sticky sessions with unique exit node assignment per worker, exponential backoff with jitter |
| Silent key drops | Dead-letter queue monitoring, circuit-breaker pattern, comprehensive error classification |
| Failure ambiguity | Transient vs terminal error taxonomy with automated recovery workflows |
| Anti-bot blocks | Stealth browser configuration, CAPTCHA detection and handling, retry budgets |
| Infra instability | Graceful shutdown handlers, display server health checks, adaptive timeouts |

### Payment Model Alignment

The client pays based on results, not hours. The system must deliver:

- **Valid scraped results beyond a configurable threshold** (e.g., 95% success rate)
- **Explanations for each failed scrape** with error classification
- **Recovery workflows** for retriable failures
- **Permanent error marking** for non-recoverable failures

This documentation establishes the project context and provides operational guidance for achieving these outcomes.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 15+
- RabbitMQ 3.12+
- Oxylabs account (residential proxies)

### Environment Setup

