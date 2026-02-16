from pydantic_settings import BaseSettings
from typing import Literal, Optional
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address

# Load .env file if it exists
load_dotenv()


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/kids_story_db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # Storage
    storage_type: Literal["s3", "local"] = "local"
    local_storage_path: str = "storage/images"
    local_video_storage_path: str = "storage/videos"
    
    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "kids-stories-media"
    cloudfront_domain: str = ""
    s3_public_read: bool = False  # Whether to make S3 objects publicly readable
    
    # LLM Provider
    llm_provider: Literal["openai", "anthropic", "ollama"] = "ollama"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    
    # DALL-E
    dalle_model: str = "dall-e-3"
    dalle_size: str = "1024x1024"
    dalle_quality: str = "standard"
    
    # API Settings
    api_key: Optional[str] = None  # Set to enable API key auth; leave unset to disable
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    rate_limit_per_minute: int = 100
    max_request_size_mb: int = 10
    
    # CORS Settings
    cors_origins: str = ""  # Comma-separated list of allowed origins, or "*" for all (empty = require explicit config)
    
    # Environment
    environment: str = "development"
    
    # Logging
    log_sql: bool = False  # Whether to echo SQL queries (separate from environment)

    # ── Guardrail Settings ──
    guardrail_fear_threshold: float = 0.4              # 0–1, above this triggers violation
    guardrail_violence_hard_threshold: float = 0.6     # above = hard fail, below = soft warning
    media_guardrail_max_retries: int = 1               # max regeneration retries per image/video
    guardrail_auto_reject_on_hard_fail: bool = True    # skip human review for hard violations

    # ── OpenAI Moderation API ──
    enable_openai_moderation: bool = True               # OpenAI Moderation API pre-filter (input + output)

    # ── Video Guardrail Settings ──
    video_frame_sampling_enabled: bool = True
    video_sample_frames: int = 5                       # number of frames to sample per video

    # ── Human Review Settings ──
    review_timeout_days: int = 3                       # auto-reject after N days with no review

    # ── Checkpointer (for LangGraph interrupt/resume) ──
    checkpointer_conn_string: str = ""                 # defaults to sync database_url if empty

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Rate limiter with Redis storage for distributed rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)
