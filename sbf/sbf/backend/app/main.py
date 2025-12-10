"""
Strategist's Best Friend - Main FastAPI Application
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import structlog

from .core.config import settings
from .api.endpoints import router as api_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(
        "starting_application",
        environment=settings.ENVIRONMENT,
        rate_limit=settings.RATE_LIMIT_PER_HOUR
    )

    # Initialize cache directory
    import os
    os.makedirs(settings.CACHE_DIR, exist_ok=True)
    logger.info("cache_directory_initialized", path=settings.CACHE_DIR)

    # Note: Workflows are initialized lazily on first request
    # This keeps startup fast and avoids loading unused workflows

    yield

    # Shutdown
    logger.info("shutting_down_application")


# Initialize FastAPI app
app = FastAPI(
    title="Strategist's Best Friend",
    description="""
## AI-powered brand research and analysis tool for strategists

### Features
- **7 Report Types**: Brand Audit, Meeting Brief, Industry Profile, Brand House, Four C's, Competitive Landscape, Audience Profile
- **Streaming Responses**: Real-time progress updates via NDJSON
- **PDF Upload**: Enhance reports with uploaded brand guidelines
- **Caching**: 24-hour cache to reduce API costs

### Authentication
Currently no authentication required. Rate limited to 3 requests/hour per IP.

### Response Format
All report endpoints return NDJSON (newline-delimited JSON) streams:
```json
{"type": "progress", "message": "Analyzing...", "progress_percent": 50}
{"type": "result", "markdown": "# Report...", "chart": {...}, "metadata": {...}}
```
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "reports", "description": "Report generation endpoints"},
        {"name": "cache", "description": "Cache management"},
        {"name": "health", "description": "Health checks"}
    ]
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://sbf.saffronbrand.com",
        "https://sbf-*.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware for tracing
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID to each request for tracing."""
    import uuid
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }


# Include API router
app.include_router(api_router, prefix="/api/v1")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "type": "error",
            "message": "Internal server error",
            "request_id": request_id,
            "details": str(exc) if settings.DEBUG else None
        }
    )
