-- =============================================================================
# PostgreSQL Initial Schema
# =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- =============================================================================
# Enum Types
# =============================================================================

CREATE TYPE job_status AS ENUM (
    'pending',
    'queued',
    'processing',
    'completed',
    'failed',
    'retrying',
    'dead_letter'
);

CREATE TYPE error_severity AS ENUM (
    'info',
    'warning',
    'error',
    'critical'
);

CREATE TYPE proxy_status AS ENUM (
    'active',
    'throttled',
    'banned',
    'retiring'
);

CREATE TYPE worker_status AS ENUM (
    'online',
    'busy',
    'idle',
    'offline',
    'error'
);

-- =============================================================================
# Table: scrape_jobs
# =============================================================================

CREATE TABLE scrape_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255),
    url TEXT NOT NULL,
    method VARCHAR(10) DEFAULT 'GET',
    headers JSONB DEFAULT '{}',
    cookies JSONB DEFAULT '{}',
    post_data TEXT,
    country_code VARCHAR(2) DEFAULT 'US',
    session_id VARCHAR(64),
    priority INTEGER DEFAULT 5,
    status job_status DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    timeout_seconds INTEGER DEFAULT 180,
    metadata JSONB DEFAULT '{}',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scrape_jobs_status ON scrape_jobs(status);
CREATE INDEX idx_scrape_jobs_external_id ON scrape_jobs(external_id);
CREATE INDEX idx_scrape_jobs_created_at ON scrape_jobs(created_at);
CREATE INDEX idx_scrape_jobs_scheduled_at ON scrape_jobs(scheduled_at) WHERE scheduled_at IS NOT NULL;
CREATE INDEX idx_scrape_jobs_priority ON scrape_jobs(priority DESC, created_at ASC);

-- =============================================================================
# Table: scrape_results
# =============================================================================

CREATE TABLE scrape_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES scrape_jobs(id) ON DELETE CASCADE,
    status_code INTEGER,
    headers JSONB DEFAULT '{}',
    cookies JSONB DEFAULT '{}',
    content_type VARCHAR(100),
    content_length BIGINT,
    html_content TEXT,
    extracted_data JSONB DEFAULT '{}',
    llm_processed BOOLEAN DEFAULT FALSE,
    llm_summary TEXT,
    screenshot_path VARCHAR(500),
    pdf_path VARCHAR(500),
    proxy_used VARCHAR(255),
    response_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scrape_results_job_id ON scrape_results(job_id);
CREATE INDEX idx_scrape_results_created_at ON scrape_results(created_at);
CREATE INDEX idx_scrape_results_llm_processed ON scrape_results(llm_processed);

-- =============================================================================
# Table: scrape_errors
# =============================================================================

CREATE TABLE scrape_errors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES scrape_jobs(id) ON DELETE SET NULL,
    error_code VARCHAR(50),
    error_type VARCHAR(100),
    error_message TEXT,
    severity error_severity DEFAULT 'error',
    proxy_error BOOLEAN DEFAULT FALSE,
    proxy_address VARCHAR(255),
    stack_trace TEXT,
    context JSONB DEFAULT '{}',
    retryable BOOLEAN DEFAULT TRUE,
    retry_count INTEGER DEFAULT 0,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scrape_errors_job_id ON scrape_errors(job_id);
CREATE INDEX idx_scrape_errors_error_code ON scrape_errors(error_code);
CREATE INDEX idx_scrape_errors_severity ON scrape_errors(severity);
CREATE INDEX idx_scrape_errors_created_at ON scrape_errors(created_at);
CREATE INDEX idx_scrape_errors_resolved ON scrape_errors(resolved) WHERE NOT resolved;

-- =============================================================================
# Table: scrape_proxies
# =============================================================================

CREATE TABLE scrape_proxies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    address VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    country_code VARCHAR(2) DEFAULT 'US',
    status proxy_status DEFAULT 'active',
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    throttle_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_failure_at TIMESTAMP WITH TIME ZONE,
    last_throttle_at TIMESTAMP WITH TIME ZONE,
    avg_response_time_ms INTEGER,
    cooldown_until TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_scrape_proxies_address ON scrape_proxies(address);
CREATE INDEX idx_scrape_proxies_status ON scrape_proxies(status);
CREATE INDEX idx_scrape_proxies_country_code ON scrape_proxies(country_code);
CREATE INDEX idx_scrape_proxies_last_used ON scrape_proxies(last_used_at);

-- =============================================================================
# Table: worker_instances
# =============================================================================

CREATE TABLE worker_instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_id VARCHAR(100) NOT NULL UNIQUE,
    hostname VARCHAR(255),
    ip_address VARCHAR(45),
    status worker_status DEFAULT 'offline',
    current_job_id UUID REFERENCES scrape_jobs(id) ON DELETE SET NULL,
    jobs_processed INTEGER DEFAULT 0,
    jobs_succeeded INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    last_heartbeat_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    stopped_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_worker_instances_worker_id ON worker_instances(worker_id);
CREATE INDEX idx_worker_instances_status ON worker_instances(status);
CREATE INDEX idx_worker_instances_last_heartbeat ON worker_instances(last_heartbeat_at);

-- =============================================================================
# Table: scrape_sessions (for tracking sticky sessions)
# =============================================================================

CREATE TABLE scrape_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(64) NOT NULL UNIQUE,
    proxy_id UUID REFERENCES scrape_proxies(id) ON DELETE SET NULL,
    proxy_address VARCHAR(255),
    country_code VARCHAR(2) DEFAULT 'US',
    sticky_until TIMESTAMP WITH TIME ZONE,
    request_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scrape_sessions_session_id ON scrape_sessions(session_id);
CREATE INDEX idx_scrape_sessions_sticky_until ON scrape_sessions(sticky_until) WHERE sticky_until > NOW();

-- =============================================================================
# Function: Update updated_at timestamp
# =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_scrape_jobs_updated_at BEFORE UPDATE ON scrape_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_scrape_proxies_updated_at BEFORE UPDATE ON scrape_proxies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_worker_instances_updated_at BEFORE UPDATE ON worker_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_scrape_sessions_updated_at BEFORE UPDATE ON scrape_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
# Grant Permissions (adjust role names as needed)
# =============================================================================

-- CREATE ROLE scraper_app WITH LOGIN PASSWORD 'scraper_app_password';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scraper_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scraper_app;

-- =============================================================================
# Comments
# =============================================================================

COMMENT ON TABLE scrape_jobs IS 'Main table for tracking scrape jobs';
COMMENT ON TABLE scrape_results IS 'Stores extracted data and content from scrape jobs';
COMMENT ON TABLE scrape_errors IS 'Error logging and retry tracking';
COMMENT ON TABLE scrape_proxies IS 'Proxy pool health tracking';
COMMENT ON TABLE worker_instances IS 'Worker registration and health monitoring';
COMMENT ON TABLE scrape_sessions IS 'Sticky session management for proxy rotation';
