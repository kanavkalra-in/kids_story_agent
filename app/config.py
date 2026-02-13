from pydantic_settings import BaseSettings
from typing import Literal
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
    
    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "kids-stories-media"
    cloudfront_domain: str = ""
    
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
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    rate_limit_per_minute: int = 500
    
    # Environment
    environment: str = "development"
    
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
