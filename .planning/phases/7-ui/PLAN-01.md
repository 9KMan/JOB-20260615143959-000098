---
title: "Phase 07: UI/UX Design"
objective: "Design and implement a web-based admin dashboard for monitoring scraping jobs, analyzing failures, managing retry workflows, and visualizing throughput metrics."
done_when:
  - "Dashboard displays real-time worker status and job queue health"
  - "Failed submissions can be reviewed, retried, or marked permanent error"
  - "Metrics show success rates, tunnel errors, and anti-bot encounters"
  - "Responsive design works on desktop and tablet"
  - "API endpoints integrated with backend for CRUD operations"
---
## Objective

Build a functional admin dashboard for the scraping infrastructure that provides visibility into job status, failure modes, and recovery actions. The UI enables operators to monitor throughput, diagnose failures, and take corrective action on failed submissions.

## Deliverables

- dashboard/src/App.tsx
- dashboard/src/components/JobMonitor.tsx
- dashboard/src/components/FailureAnalyzer.tsx
- dashboard/src/components/WorkerStatus.tsx
- dashboard/src/components/RetryQueue.tsx
- dashboard/src/components/MetricsPanel.tsx
- dashboard/src/components/ErrorDetailModal.tsx
- dashboard/src/services/api.ts
- dashboard/src/types/index.ts
- dashboard/src/hooks/useWebSocket.ts
- dashboard/src/hooks/usePolling.ts
- dashboard/public/index.html
- dashboard/package.json
- dashboard/vite.config.ts
- dashboard/tailwind.config.js
- dashboard/tsconfig.json

## Done When

- Job monitor shows all queued, running, completed, failed, and dead-lettered jobs
- Failure analyzer groups errors by type (tunnel, captcha, timeout, terminal)
- Retry queue allows bulk retry of recoverable failures with configurable backoff
- Permanent error marking workflow confirms intent before final classification
- Metrics panel displays: success rate %, tunnel error rate, avg job duration, throughput (jobs/min)
- Worker status grid shows active/idle/dead workers with last heartbeat
- Real-time updates via WebSocket or polling (configurable)
- Responsive layout renders on 1024px+ screens

## Technical Details

### UI Stack
- **Framework:** React 18 + TypeScript
- **Build:** Vite 5
- **Styling:** Tailwind CSS 3
- **State:** React Query for server state, Zustand for UI state
- **Charts:** Recharts for metrics visualization
- **Icons:** Lucide React

### Dashboard Layout
```
┌─────────────────────────────────────────────────────────┐
│ Header: Logo | Connection Status | Settings | User     │
├─────────────┬───────────────────────────────────────────┤
│             │  Metrics Strip: KPIs in cards             │
│  Sidebar    ├───────────────────────────────────────────┤
│  - Jobs     │  Main Content Area                        │
│  - Workers  │  (tabbed or split view)                   │
│  - Failures │                                           │
│  - Queue    │                                           │
│  - Metrics  │                                           │
└─────────────┴───────────────────────────────────────────┘
```

### API Integration

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/jobs` | GET | List jobs with filters (status, date range) |
| `/api/v1/jobs/{id}` | GET | Job detail with attempts |
| `/api/v1/jobs/{id}/retry` | POST | Queue single job for retry |
| `/api/v1/jobs/bulk-retry` | POST | Bulk retry with failure type filter |
| `/api/v1/jobs/{id}/mark-terminal` | POST | Mark as permanent error |
| `/api/v1/workers` | GET | Worker status list |
| `/api/v1/metrics` | GET | Aggregated stats |
| `/api/v1/failures/summary` | GET | Failure breakdown by type |

### Failure Classification UI

Display failure types with distinct visual indicators:
- **TUNNEL_ERROR** (orange badge): Proxy connectivity issues
- **CAPTCHA** (yellow badge): Anti-bot challenge
- **TIMEOUT** (gray badge): Slow render or network
- **TERMINAL** (red badge): Marked for no retry

### Retry Workflow

1. User selects failed jobs (checkbox or "Select All Filtered")
2. Clicks "Retry Selected" button
3. Confirmation modal shows count and optional delay override
4. Jobs re-queued with `retry_count` incremented
5. UI updates job status to QUEUED_RETRY

### Permanent Error Marking

1. User clicks "Mark Terminal" on a job
2. Modal requires reason selection: `BLOCKED`, `RATE_LIMITED`, `DATA_MISSING`, `OTHER`
3. Optional notes field
4. Confirm marks job `status = terminal` in DB
5. Job excluded from future bulk retry operations

### Real-time Updates

- WebSocket connection to `/ws/jobs` for live status updates
- Fallback to 10s polling if WebSocket unavailable
- Visual indicator showing connection state (green/yellow/red dot)

### Responsive Behavior

- Sidebar collapses to hamburger menu below 1280px
- Metrics strip stacks to 2x2 grid on tablets
- Table views become card views on narrow screens