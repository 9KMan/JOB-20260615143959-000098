// migrations/versions/001_initial_schema.py
"""Initial schema for scraping framework.

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

This migration creates:
- PostgreSQL enum types for all status fields
- Core tables: jobs, scrape_tasks, scrape_results, scrape_failures,
  proxy_sessions, worker_instances, retry_policies
- All indexes including partial indexes for query optimization
- Default retry policies for common error codes
"""
from typing import Sequence, Union
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY, TEXT
from sqlalchemy.sql import text


# revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema with all tables and indexes."""
    
    # ============================================
    # Step 1: Create PostgreSQL ENUM types
    # ============================================
    
    # Create job_status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE job_status AS ENUM ('pending', 'running', 'paused', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create task_status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE task_status AS ENUM ('pending', 'claimed', 'processing', 'completed', 'failed', 'dead_letter');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create circuit_state enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE circuit_state AS ENUM ('closed', 'open', 'half_open');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create failure_category enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE failure_category AS ENUM ('transient', 'terminal', 'unknown');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create proxy_status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE proxy_status AS ENUM ('active', 'exhausted', 'error', 'retired');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create worker_status enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE worker_status AS ENUM ('healthy', 'degraded', 'offline');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # ============================================
    # Step 2: Create jobs table
    # ============================================
    
    op.create_table(
        'jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'paused', 'completed', 'failed', name='job_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('total_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        comment='Scraping jobs/batches containing multiple tasks',
    )
    
    # Indexes for jobs
    op.create_index('idx_jobs_status', 'jobs', ['status'])
    op.create_index('idx_jobs_created_at', 'jobs', ['created_at'])
    
    # ============================================
    # Step 3: Create proxy_sessions table
    # ============================================
    
    op.create_table(
        'proxy_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('proxy_host', sa.String(255), nullable=False),
        sa.Column('proxy_port', sa.Integer(), nullable=False),
        sa.Column('exit_ip', sa.String(45), nullable=True),
        sa.Column('session_key', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('active', 'exhausted', 'error', 'retired', name='proxy_status', create_type=False), nullable=False, server_default='active'),
        sa.Column('tunnel_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_tunnel_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('proxy_port > 0 AND proxy_port <= 65535', name='check_valid_port'),
        sa.CheckConstraint('tunnel_error_count >= 0', name='check_tunnel_errors_nonnegative'),
        comment='Proxy session state and health tracking',
    )
    
    # Indexes for proxy_sessions
    op.create_index('idx_proxy_status_cooldown', 'proxy_sessions', ['status', 'cooldown_until'])
    op.create_index('idx_proxy_exit_ip', 'proxy_sessions', ['exit_ip'])
    op.create_index('idx_proxy_last_used', 'proxy_sessions', ['last_used_at'])
    
    # ============================================
    # Step 4: Create scrape_tasks table
    # ============================================
    
    op.create_table(
        'scrape_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('pending', 'claimed', 'processing', 'completed', 'failed', 'dead_letter', name='task_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('circuit_state', sa.Enum('closed', 'open', 'half_open', name='circuit_state', create_type=False), nullable=False, server_default='closed'),
        sa.Column('circuit_opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_by', UUID(as_uuid=True), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_id', UUID(as_uuid=True), nullable=True),
        sa.Column('failure_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', JSONB(), nullable=False, server_default='{}'),
        sa.CheckConstraint('attempt_count >= 0', name='check_attempt_count_positive'),
        sa.CheckConstraint('attempt_count <= max_attempts', name='check_attempt_count_limit'),
        comment='Individual scrape tasks with retry and circuit breaker support',
    )
    
    # Indexes for scrape_tasks
    op.create_index('idx_tasks_poll', 'scrape_tasks', 
        ['status', text('priority DESC'), 'next_retry_at'],
        postgresql_where=text("status IN ('pending', 'claimed')")
    )
    op.create_index('idx_tasks_job_status', 'scrape_tasks', ['job_id', 'status'])
    op.create_index('idx_tasks_claimed_by', 'scrape_tasks', ['claimed_by'])
    op.create_index('idx_tasks_retry', 'scrape_tasks', 
        ['status', 'next_retry_at'],
        postgresql_where=text("status = 'pending' AND next_retry_at IS NOT NULL")
    )
    
    # ============================================
    # Step 5: Create scrape_results table
    # ============================================
    
    op.create_table(
        'scrape_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('scrape_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('raw_html', sa.Text(), nullable=True),
        sa.Column('extracted_data', JSONB(), nullable=False, server_default='{}'),
        sa.Column('llm_processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('llm_result', JSONB(), nullable=True),
        sa.Column('llm_error', sa.Text(), nullable=True),
        sa.Column('scrape_duration_ms', sa.Integer(), nullable=False),
        sa.Column('proxy_session_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        comment='Successful scrape results with LLM processing support',
    )
    
    # Add foreign key for proxy_session_id after table exists
    op.create_foreign_key(
        'fk_results_proxy_session',
        'scrape_results', 'proxy_sessions',
        ['proxy_session_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Indexes for scrape_results
    op.create_index('idx_results_task_id', 'scrape_results', ['task_id'], unique=True)
    op.create_index('idx_results_created_at', 'scrape_results', ['created_at'])
    op.create_index('idx_results_content_hash', 'scrape_results', ['content_hash'])
    
    # ============================================
    # Step 6: Create scrape_failures table
    # ============================================
    
    op.create_table(
        'scrape_failures',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('scrape_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('error_code', sa.String(50), nullable=False),
        sa.Column('error_category', sa.Enum('transient', 'terminal', 'unknown', name='failure_category', create_type=False), nullable=False, server_default='unknown'),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False, default=1),
        sa.Column('proxy_session_id', UUID(as_uuid=True), nullable=True),
        sa.Column('is_retryable', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('retry_count_at_failure', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        comment='Failure records with error classification for retry decisions',
    )
    
    # Add foreign key for proxy_session_id after table exists
    op.create_foreign_key(
        'fk_failures_proxy_session',
        'scrape_failures', 'proxy_sessions',
        ['proxy_session_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Indexes for scrape_failures
    op.create_index('idx_failures_task_id', 'scrape_failures', ['task_id'])
    op.create_index('idx_failures_error_code', 'scrape_failures', ['error_code'])
    op.create_index('idx_failures_category', 'scrape_failures', ['error_category', 'created_at'])
    op.create_index('idx_failures_created_at', 'scrape_failures', ['created_at'])
    op.create_index('idx_failures_retryable', 'scrape_failures', ['is_retryable'])
    
    # ============================================
    # Step 7: Create worker_instances table
    # ============================================
    
    op.create_table(
        'worker_instances',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('instance_name', sa.String(100), nullable=False, unique=True),
        sa.Column('status', sa.Enum('healthy', 'degraded', 'offline', name='worker_status', create_type=False), nullable=False, server_default='healthy'),
        sa.Column('current_job_id', UUID(as_uuid=True), nullable=True),
        sa.Column('claimed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('circuit_breaker_global_state', sa.Enum('closed', 'open', 'half_open', name='circuit_state', create_type=False), nullable=False, server_default='closed'),
        sa.Column('circuit_breaker_opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        sa.CheckConstraint('claimed_tasks >= 0', name='check_claimed_tasks_nonnegative'),
        sa.CheckConstraint('completed_tasks >= 0', name='check_completed_tasks_nonnegative'),
        sa.CheckConstraint('failed_tasks >= 0', name='check_failed_tasks_nonnegative'),
        comment='Worker fleet state and health tracking',
    )
    
    # Add foreign key for current_job_id after table exists
    op.create_foreign_key(
        'fk_workers_current_job',
        'worker_instances', 'jobs',
        ['current_job_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Indexes for worker_instances
    op.create_index('idx_workers_status', 'worker_instances', ['status'])
    op.create_index('idx_workers_circuit_state', 'worker_instances', ['circuit_breaker_global_state'])
    op.create_index('idx_workers_heartbeat', 'worker_instances', ['last_heartbeat_at'])
    
    # ============================================
    # Step 8: Create retry_policies table
    # ============================================
    
    op.create_table(
        'retry_policies',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('error_codes', TEXT(), nullable=False, server_default='{}'),
        sa.Column('base_delay_seconds', sa.Integer(), nullable=False),
        sa.Column('max_delay_seconds', sa.Integer(), nullable=False),
        sa.Column('multiplier', sa.Float(), nullable=False, default=2.0),
        sa.Column('max_attempts', sa.Integer(), nullable=False, default=5),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=text('NOW()')),
        comment='Retry policies for different error types',
    )
    
    # ============================================
    # Step 9: Add foreign key constraints to scrape_tasks
    # ============================================
    
    # Add foreign keys for result_id and failure_id
    op.create_foreign_key(
        'fk_tasks_result',
        'scrape_tasks', 'scrape_results',
        ['result_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_tasks_failure',
        'scrape_tasks', 'scrape_failures',
        ['failure_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # ============================================
    # Step 10: Insert default retry policies
    # ============================================
    
    now = datetime.utcnow()
    
    # ERR_TUNNEL retry policy - exponential backoff
    op.execute(f"""
        INSERT INTO retry_policies (id, name, error_codes, base_delay_seconds, max_delay_seconds, multiplier, max_attempts, is_active, created_at)
        VALUES (
            gen_random_uuid(),
            'ERR_TUNNEL Retry Policy',
            '{{ERR_TUNNEL, TUNNEL_ERROR, PROXY_AUTH_FAILED}}',
            30,
            3600,
            2.0,
            5,
            true,
            '{now.isoformat()}'
        )
    """)
    
    # TIMEOUT retry policy - longer delays
    op.execute(f"""
        INSERT INTO retry_policies (id, name, error_codes, base_delay_seconds, max_delay_seconds, multiplier, max_attempts, is_active, created_at)
        VALUES (
            gen_random_uuid(),
            'TIMEOUT Retry Policy',
            '{{TIMEOUT, CONNECTION_TIMEOUT, NETWORK_ERROR}}',
            60,
            1800,
            1.5,
            3,
            true,
            '{now.isoformat()}'
        )
    """)
    
    # CAPTCHA retry policy - very long delays
    op.execute(f"""
        INSERT INTO retry_policies (id, name, error_codes, base_delay_seconds, max_delay_seconds, multiplier, max_attempts, is_active, created_at)
        VALUES (
            gen_random_uuid(),
            'CAPTCHA Retry Policy',
            '{{CAPTCHA, RECAPTCHA, HCAPTCHA}}',
            300,
            7200,
            2.0,
            3,
            true,
            '{now.isoformat()}'
        )
    """)
    
    # ANTI_BOT retry policy - medium delays
    op.execute(f"""
        INSERT INTO retry_policies (id, name, error_codes, base_delay_seconds, max_delay_seconds, multiplier, max_attempts, is_active, created_at)
        VALUES (
            gen_random_uuid(),
            'ANTI_BOT Retry Policy',
            '{{ANTI_BOT, HEADLESS_DETECTED, CLOUDFLARE_BLOCK, DATADOME_BLOCK}}',
            120,
            3600,
            2.0,
            4,
            true,
            '{now.isoformat()}'
        )
    """)
    
    # RATE_LIMIT retry policy - moderate delays
    op.execute(f"""
        INSERT INTO retry_policies (id, name, error_codes, base_delay_seconds, max_delay_seconds, multiplier, max_attempts, is_active, created_at)
        VALUES (
            gen_random_uuid(),
            'RATE_LIMIT Retry Policy',
            '{{RATE_LIMIT, TOO_MANY_REQUESTS, HTTP_429}}',
            45,
            1800,
            1.8,
            5,
            true,
            '{now.isoformat()}'
        )
    """)


def downgrade() -> None:
    """Drop all tables and enum types in reverse order."""
    
    # Drop foreign keys first
    op.drop_constraint('fk_tasks_result', 'scrape_tasks', type_='foreignkey')
    op.drop_constraint('fk_tasks_failure', 'scrape_tasks', type_='foreignkey')
    op.drop_constraint('fk_results_proxy_session', 'scrape_results', type_='foreignkey')
    op.drop_constraint('fk_failures_proxy_session', 'scrape_failures', type_='foreignkey')
    op.drop_constraint('fk_workers_current_job', 'worker_instances', type_='foreignkey')
    
    # Drop tables in reverse order of creation
    op.drop_table('retry_policies')
    op.drop_table('worker_instances')
    op.drop_table('scrape_failures')
    op.drop_table('scrape_results')
    op.drop_table('scrape_tasks')
    op.drop_table('proxy_sessions')
    op.drop_table('jobs')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS worker_status')
    op.execute('DROP TYPE IF EXISTS proxy_status')
    op.execute('DROP TYPE IF EXISTS failure_category')
    op.execute('DROP TYPE IF EXISTS circuit_state')
    op.execute('DROP TYPE IF EXISTS task_status')
    op.execute('DROP TYPE IF EXISTS job_status')
