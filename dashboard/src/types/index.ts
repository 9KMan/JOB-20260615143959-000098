// dashboard/src/types/index.ts

export type JobStatus = 
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'dead_lettered'
  | 'queued_retry'
  | 'terminal';

export type FailureType = 
  | 'TUNNEL_ERROR'
  | 'CAPTCHA'
  | 'TIMEOUT'
  | 'TERMINAL'
  | 'UNKNOWN';

export type TerminalReason = 
  | 'BLOCKED'
  | 'RATE_LIMITED'
  | 'DATA_MISSING'
  | 'OTHER';

export type WorkerStatus = 'active' | 'idle' | 'dead';

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

export interface JobAttempt {
  id: string;
  attempt_number: number;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  success: boolean;
  error_type: FailureType | null;
  error_message: string | null;
  worker_id: string | null;
}

export interface Job {
  id: string;
  url: string;
  status: JobStatus;
  failure_type: FailureType | null;
  failure_message: string | null;
  retry_count: number;
  max_retries: number;
  terminal_reason: TerminalReason | null;
  terminal_notes: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  attempts: JobAttempt[];
  metadata: Record<string, unknown>;
}

export interface Worker {
  id: string;
  name: string;
  status: WorkerStatus;
  current_job_id: string | null;
  last_heartbeat: string;
  jobs_completed: number;
  jobs_failed: number;
  avg_duration_ms: number;
  region: string | null;
  proxy: string | null;
}

export interface Metrics {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  dead_lettered_jobs: number;
  success_rate: number;
  tunnel_error_rate: number;
  captcha_rate: number;
  timeout_rate: number;
  avg_job_duration_ms: number;
  throughput_jobs_per_min: number;
  period_start: string;
  period_end: string;
}

export interface FailureSummary {
  failure_type: FailureType;
  count: number;
  percentage: number;
  avg_retries: number;
  recent_examples: string[];
}

export interface RetryRequest {
  job_ids: string[];
  delay_seconds?: number;
  force: boolean;
}

export interface MarkTerminalRequest {
  job_id: string;
  reason: TerminalReason;
  notes?: string;
}

export interface JobsFilter {
  status?: JobStatus[];
  failure_type?: FailureType[];
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
  limit?: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface WebSocketMessage {
  type: 'job_update' | 'worker_update' | 'metrics_update' | 'connection';
  payload: unknown;
  timestamp: string;
}

export interface ApiError {
  message: string;
  code: string;
  details?: Record<string, unknown>;
}
