from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.config import settings, limiter
from app.db.session import engine, Base
from app.api.stories import router as stories_router
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    logger.info("Starting Kids Story Agent API...")
    
    # Security check: warn if API key is not set in production
    if settings.environment == "production" and not settings.api_key:
        logger.error(
            "SECURITY WARNING: API key authentication is disabled in production! "
            "Set API_KEY environment variable to enable authentication."
        )
    
    # Create database tables (in production, use Alembic migrations)
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Kids Story Agent API...")
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Kids Story Agent API",
    description="API for generating children's stories with illustrations",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# Request body size limit middleware (before FastAPI parses JSON)
@app.middleware("http")
async def check_request_size(request: Request, call_next):
    """Reject request bodies that exceed the configured size limit."""
    content_length = request.headers.get("content-length")
    if content_length:
        max_size_bytes = settings.max_request_size_mb * 1024 * 1024
        if int(content_length) > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Request body too large. Maximum size is {settings.max_request_size_mb}MB",
            )
    response = await call_next(request)
    return response

# CORS middleware - configure based on environment
if settings.cors_origins:
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    _allow_all = cors_origins == ["*"]
else:
    # Empty string means no CORS allowed (require explicit configuration)
    cors_origins = []
    _allow_all = False

if _allow_all and settings.environment == "production":
    logger.warning("CORS is set to allow all origins in production. This is a security risk!")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    # allow_credentials=True is incompatible with allow_origins=["*"] per CORS spec
    allow_credentials=not _allow_all,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include routers
app.include_router(stories_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Kids Story Agent API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
