# src/app/main.py
"""
FastAPI Application Entry Point.
Provides REST API for job management, monitoring, and results retrieval.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.dependencies import engine, create_tables
from app.core.config import settings
from app.core.logging import setup_logging

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    logger.info("Starting application...")
    
    # Create database tables on startup
    try:
        await create_tables()
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
    
    yield
    
    logger.info("Shutting down application...")
    engine.dispose()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Scraping Infrastructure API",
        description="Production-grade web scraping fleet management with failure handling",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)},
        )
    
    # Include API routes
    app.include_router(api_router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:
        return {"status": "healthy", "version": "1.0.0"}
    
    # Ready check endpoint
    @app.get("/ready")
    async def ready_check() -> dict:
        """Check if the service is ready to accept requests."""
        try:
            # Check database connection
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
            return {"status": "ready", "database": "connected"}
        except Exception as e:
            return {"status": "not_ready", "database": str(e)}
    
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
