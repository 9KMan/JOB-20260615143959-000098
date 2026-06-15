# src/app/api/schemas.py
"""
Pydantic Schemas for API Request/Response Validation.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


# Enums
class JobStatusEnum(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    MANUAL_REVIEW = "manual_review"


class FailureClassEnum(str, Enum):
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    AMBIGUOUS = "ambiguous"


class RecoveryStatusEnum(str, Enum):
    PENDING = "pending"
    ATTEMPTED = "attempted"
    RECOVERED = "recovered"
    FAILED = "failed"
    SKIPPED = "skipped"


class BatchStatusEnum(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime


class UserLogin(BaseModel):
    username: str
    password: str


# Job Schemas
class JobCreate(BaseModel):
    url: str = Field(..., description="URL to scrape")
    target_id: uuid.UUID
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=100)


class JobUpdate(BaseModel):
    status: Optional[JobStatusEnum] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    target_id: uuid.UUID
    worker_id: Optional[str]
    status: JobStatusEnum
    priority: int
    url: str
    parameters: dict[str, Any]
    retry_count: int
    max_retries: int
    created_at: datetime
    queued_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class JobDetailResponse(JobResponse):
    result: Optional["JobResultResponse"] = None
    failure: Optional["JobFailureResponse"] = None


# Job Result Schemas
class JobResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    job_id: uuid.UUID
    extracted_data: dict[str, Any]
    processed_data: Optional[dict[str, Any]]
    is_valid: bool
    validity_score: float
    validation_errors: Optional[list[str]]
    page_load_time_ms: Optional[int]
    extraction_time_ms: Optional[int]
    total_time_ms: Optional[int]
    response_code: Optional[int]
    created_at: datetime


# Job Failure Schemas
class JobFailureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    job_id: uuid.UUID
    error_type: str
    error_message: str
    error_details: Optional[dict[str, Any]]
    failure_category: str
    failure_class: FailureClassEnum
    confidence_score: float
    classification_reason: Optional[str]
    recovery_status: RecoveryStatusEnum
    recovery_attempts: int
    created_at: datetime


# Batch Schemas
class BatchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    jobs: list["JobCreate"] = Field(..., min_length=1)


class BatchUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    description: Optional[str]
    status: BatchStatusEnum
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    pending_jobs: int
    success_rate: float
    validity_rate: float
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class BatchDetailResponse(BatchResponse):
    jobs: list[JobResponse] = []


# Target Schemas
class TargetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url_pattern: str
    base_url: str
    selectors: dict[str, Any] = Field(default_factory=dict)
    stealth_config: dict[str, Any] = Field(default_factory=dict)
    rate_limit_requests: int = Field(default=10, ge=1)
    rate_limit_period: int = Field(default=60, ge=1)


class TargetUpdate(BaseModel):
    name: Optional[str] = None
    url_pattern: Optional[str] = None
    base_url: Optional[str] = None
    selectors: Optional[dict[str, Any]] = None
    stealth_config: Optional[dict[str, Any]] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_period: Optional[int] = None
    is_active: Optional[bool] = None


class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    url_pattern: str
    base_url: str
    selectors: dict[str, Any]
    stealth_config: dict[str, Any]
    rate_limit_requests: int
    rate_limit_period: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Manual Review Schemas
class ManualReviewUpdate(BaseModel):
    status: Optional[ManualReviewStatus] = None
    notes: Optional[str] = None
    decision: Optional[str] = None
    suggested_fix: Optional[str] = None
    final_failure_class: Optional[FailureClassEnum] = None


class ManualReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    failure_id: uuid.UUID
    reviewer_id: Optional[uuid.UUID]
    status: str
    priority: int
    notes: Optional[str]
    decision: Optional[str]
    suggested_fix: Optional[str]
    final_failure_class: Optional[FailureClassEnum]
    created_at: datetime
    assigned_at: Optional[datetime]
    completed_at: Optional[datetime]


# Proxy Schemas
class ProxyHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    proxy_host: str
    proxy_port: int
    status: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    tunnel_errors: int
    health_score: float
    success_rate: float
    tunnel_error_rate: float
    last_used_at: Optional[datetime]
    created_at: datetime


# Monitoring Schemas
class FleetHealthResponse(BaseModel):
    total_workers: int
    active_workers: int
    idle_workers: int
    busy_workers: int
    queue_depth: int
    retry_queue_depth: int
    dead_letter_queue_depth: int
    manual_review_queue_depth: int
    avg_job_duration_ms: float
    success_rate_1h: float
    failure_rate_1h: float


class MetricsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    in_progress_jobs: int
    pending_jobs: int
    retrying_jobs: int
    dead_letter_jobs: int
    manual_review_jobs: int
    success_rate: float
    avg_validity_score: float
    total_proxy_requests: int
    proxy_success_rate: float
    tunnel_error_rate: float


class PaymentCalculationResponse(BaseModel):
    total_jobs: int
    successful_jobs: int
    terminal_failures: int
    transient_failures: int
    valid_results: int
    validity_rate: float
    
    base_payment: float
    terminal_error_credit: float
    quality_bonus: float
    total_payment: float
    
    meets_threshold: bool
    threshold_required: float


# Pagination
class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# Update forward references
JobDetailResponse.model_rebuild()
BatchCreate.model_rebuild()
