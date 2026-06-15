// src/api/routes/jobs.py
"""Job management endpoints."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_current_user, get_pagination_params, get_client_id
from src.api.schemas.job import JobResponse, JobListResponse, JobRetryResponse, JobMarkTerminalResponse
from src.api.schemas.common import ErrorResponse
from src.services.job_service import JobService
from src.services.queue_service import QueueService
from src.core.logging import get_logger
from src.core.metrics import get_metrics

router = APIRouter()
logger = get_logger(__name__)
metrics = get_metrics()


@router.get(
    "",
    response_model=JobListResponse,
    responses={
        401: {"model": ErrorResponse},
    },
)
async def list_jobs(
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List jobs with optional filters and pagination.
    """
    client_id = get_client_id(current_user)
    
    job_service = JobService(db)
    
    jobs, total = await job_service.list_jobs(
        client_id=client_id,
        batch_id=batch_id,
        status_filter=status_filter,
        skip=pagination["skip"],
        limit=pagination["limit"],
    )
    
    return JobListResponse(
        items=[JobResponse(**j.to_dict()) for j in jobs],
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get job details including error information if failed.
    """
    client_id = get_client_id(current_user)
    
    job_service = JobService(db)
    job = await job_service.get_job(job_id, client_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            }
        )
    
    return JobResponse(**job.to_dict(include_errors=True))


@router.post(
    "/{job_id}/retry",
    response_model=JobRetryResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manually retry a failed job.
    
    Resets the job status and queues it for another attempt.
    """
    client_id = get_client_id(current_user)
    
    job_service = JobService(db)
    queue_service = QueueService()
    
    try:
        job = await job_service.get_job(job_id, client_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "JOB_NOT_FOUND",
                        "message": f"Job {job_id} not found",
                    }
                }
            )
        
        # Attempt retry
        success = await job_service.retry_job(job_id, client_id)
        
        if success:
            # Queue the job
            await queue_service.publish_job_retry(
                job_id=job_id,
                batch_id=job.batch_id,
                url=job.url,
                site_config=job.site_config,
                metadata=job.metadata,
                client_id=client_id,
            )
            
            logger.info(f"Job retry queued: {job_id}")
            
            return JobRetryResponse(
                job_id=job_id,
                status="queued",
                message="Job queued for retry",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "JOB_RETRY_FAILED",
                        "message": "Job cannot be retried in current state",
                    }
                }
            )
            
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOB_STATE_CONFLICT",
                    "message": str(e),
                }
            }
        )


@router.post(
    "/{job_id}/mark-terminal",
    response_model=JobMarkTerminalResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def mark_job_terminal(
    job_id: str,
    reason: str = Query(..., description="Reason for marking as terminal"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Mark a job as permanently failed (terminal error).
    
    This should be used when manual analysis determines the job
    cannot succeed due to a permanent issue (e.g., banned IP, captcha).
    """
    client_id = get_client_id(current_user)
    
    job_service = JobService(db)
    
    try:
        success = await job_service.mark_terminal(job_id, client_id, reason)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "JOB_NOT_FOUND",
                        "message": f"Job {job_id} not found",
                    }
                }
            )
        
        logger.info(f"Job marked terminal: {job_id}, reason: {reason}")
        
        return JobMarkTerminalResponse(
            job_id=job_id,
            status="terminal",
            message="Job marked as terminal",
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JOB_STATE_CONFLICT",
                    "message": str(e),
                }
            }
        )
