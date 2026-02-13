from celery import Celery
from dotenv import load_dotenv
from app.config import settings

# Load .env file
load_dotenv()

celery_app = Celery(
    "kids_story_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.story_tasks"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    # Rate limiting for external APIs
    task_acks_late=True,
    worker_disable_rate_limits=False,
)
