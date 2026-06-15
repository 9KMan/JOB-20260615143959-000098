// src/api/routes/batches.py
"""Batch management endpoints."""
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import get_db, get_current_user, get_pagination_params, get_client_id
from src.api.schemas.batch import (
    BatchCreateRequest,
    BatchResponse,
    BatchListResponse,
    BatchProgressResponse,
    BatchCancelResponse,
)
from src.api.schemas.common import ErrorResponse, ValidationErrorItem
from src.services.batch_service import BatchService
from src.services.queue_service import QueueService
from src.core.logging import get_logger
from src.core.metrics import get_metrics

router = APIRouter()
logger = get_logger(__name__)
metrics = get_metrics()


@router.post(
    "",
    response_model=BatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_batch(
    request: BatchCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new scraping batch.
    
    Creates a batch with the specified items and queues them for processing.
    Returns immediately with batch details and estimated completion time.
    """
    client_id = get_client_id(current_user)
    
    # Validate items
    if not request.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "At least one item is required",
                    "details": [{"field": "items", "issue": "List cannot be empty"}],
                }
            }
        )
    
    # Validate URLs
    for i, item in enumerate(request.items):
        if len(item.url) > 2048:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"URL too long at index {i}",
                        "details": [{"field": f"items[{i}].url", "issue": "URL exceeds 2048 characters"}],
                    }
                }
            )
    
    try:
        # Create batch service
        batch_service = BatchService(db)
        queue_service = QueueService()
        
        # Create batch
        batch = await batch_service.create_batch(
            name=request.name,
            items=request.items,
            priority=request.priority,
            callback_url=request.callback_url,
            metadata=request.metadata,
            client_id=client_id,
        )
        
        # Queue jobs in background
        background_tasks.add_task(
            queue_service.publish_batch_jobs,
            batch_id=batch.id,
            items=request.items,
            priority=request.priority,
            callback_url=request.callback_url,
            client_id=client_id,
        )
        
        # Record metrics
        metrics.record_batch_created(len(request.items))
        
        logger.info(f"Batch created: {batch.id} with {len(request.items)} items")
        
        return BatchResponse(
            batch_id=batch.id,
            status=batch.status.value,
            total_items=batch.total_items,
            estimated_completion=batch.estimated_completion,
        )
        
    except Exception as e:
        logger.exception(f"Failed to create batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "BATCH_CREATION_FAILED",
                    "message": "Failed to create batch",
                }
            }
        )


@router.get(
    "",
    response_model=BatchListResponse,
    responses={
        401: {"model": ErrorResponse},
    },
)
async def list_batches(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    pagination: dict = Depends(get_pagination_params),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List batches with optional status filter and pagination.
    """
    client_id = get_client_id(current_user)
    
    batch_service = BatchService(db)
    
    batches, total = await batch_service.list_batches(
        client_id=client_id,
        status_filter=status_filter,
        skip=pagination["skip"],
        limit=pagination["limit"],
    )
    
    return BatchListResponse(
        items=[BatchResponse(**b.to_dict()) for b in batches],
        total=total,
        page=pagination["page"],
        page_size=pagination["page_size"],
    )


@router.get(
    "/{batch_id}",
    response_model=BatchProgressResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get batch details with current progress.
    """
    client_id = get_client_id(current_user)
    
    batch_service = BatchService(db)
    batch = await batch_service.get_batch(batch_id, client_id)
    
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BATCH_NOT_FOUND",
                    "message": f"Batch {batch_id} not found",
                }
            }
        )
    
    return BatchProgressResponse(**batch.to_dict())


@router.delete(
    "/{batch_id}",
    response_model=BatchCancelResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def cancel_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Cancel/soft-delete a batch.
    
    Cancels all pending jobs and marks the batch as cancelled.
    Already completed jobs will retain their results.
    """
    client_id = get_client_id(current_user)
    
    batch_service = BatchService(db)
    
    try:
        success = await batch_service.cancel_batch(batch_id, client_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "BATCH_NOT_FOUND",
                        "message": f"Batch {batch_id} not found",
                    }
                }
            )
        
        logger.info(f"Batch cancelled: {batch_id}")
        
        return BatchCancelResponse(
            batch_id=batch_id,
            status="cancelled",
            message="Batch cancelled successfully",
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "BATCH_STATE_CONFLICT",
                    "message": str(e),
                }
            }
        )
