"""
Strategist's Best Friend - FastAPI Main Application
Production-ready API with streaming, rate limiting, and structured logging.
"""

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .api.endpoints import router
from .core.config import settings
from .graph.workflows.brand_audit_workflow import create_brand_audit_workflow
from .graph.workflows.meeting_brief_workflow import create_meeting_brief_workflow
from .graph.workflows.industry_workflow import create_industry_profile_workflow
from .graph.workflows.brand_house_workflow import create_brand_house_workflow
from .graph.workflows.four_cs_workflow import create_four_cs_workflow
from .graph.workflows.competitive_landscape_workflow import create_competitive_landscape_workflow
from .graph.workflows.audience_profile_workflow import create_audience_profile_workflow
from .graph.workflows.base import close_checkpointer

# Setup structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if settings.ENVIRONMENT == "development" else structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "starting_sbf_api",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL
    )

    # Initialize workflows
    try:
        logger.info("initializing_workflows")

        # Import all workflow modules
        import app.graph.workflows.brand_audit_workflow as ba_module
        import app.graph.workflows.meeting_brief_workflow as mb_module
        import app.graph.workflows.industry_workflow as ip_module
        import app.graph.workflows.brand_house_workflow as bh_module
        import app.graph.workflows.four_cs_workflow as fc_module
        import app.graph.workflows.competitive_landscape_workflow as cl_module
        import app.graph.workflows.audience_profile_workflow as ap_module

        logger.info("workflow_modules_imported", count=7)

        # Initialize all 7 workflows at startup
        logger.info("creating_brand_audit_workflow")
        ba_module.brand_audit_workflow = await create_brand_audit_workflow()
        logger.info("brand_audit_workflow_created")

        logger.info("creating_meeting_brief_workflow")
        mb_module.meeting_brief_workflow = await create_meeting_brief_workflow()
        logger.info("meeting_brief_workflow_created")

        logger.info("creating_industry_profile_workflow")
        ip_module.industry_profile_workflow = await create_industry_profile_workflow()
        logger.info("industry_profile_workflow_created")

        logger.info("creating_brand_house_workflow")
        bh_module.brand_house_workflow = await create_brand_house_workflow()
        logger.info("brand_house_workflow_created")

        logger.info("creating_four_cs_workflow")
        fc_module.four_cs_workflow = await create_four_cs_workflow()
        logger.info("four_cs_workflow_created")

        logger.info("creating_competitive_landscape_workflow")
        cl_module.competitive_landscape_workflow = await create_competitive_landscape_workflow()
        logger.info("competitive_landscape_workflow_created")

        logger.info("creating_audience_profile_workflow")
        ap_module.audience_profile_workflow = await create_audience_profile_workflow()
        logger.info("audience_profile_workflow_created")

        logger.info("workflows_initialized", count=7)
    except Exception as e:
        logger.error("workflow_initialization_failed", error=str(e), exc_info=True)
        raise  # Re-raise to prevent server from starting with broken workflows

    yield

    # Shutdown
    logger.info("shutting_down_sbf_api")
    await close_checkpointer()


# Create FastAPI app
app = FastAPI(
    title="Strategist's Best Friend API",
    description="Strategic report generation with GPT-5.1 and comprehensive web research",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint for Render and monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Strategist's Best Friend API",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
