# Kids Story Agent Backend

A scalable FastAPI backend for generating children's stories with AI-generated illustrations. The system uses LangGraph for orchestration, Celery for task processing, and supports both OpenAI and Anthropic LLMs.

## Features

- **AI Story Generation**: Generate age-appropriate stories (3-5, 6-8, 9-12) using GPT-4 or Claude
- **Image Generation**: Create illustrations using DALL-E 3
- **Async Processing**: Celery-based task queue for scalable processing
- **Webhook Support**: Get notified when story generation completes
- **Rate Limiting**: Redis-backed rate limiting (500 req/min)
- **Scalable Architecture**: Designed to handle 500+ requests per minute

## Architecture

- **FastAPI**: REST API with async support
- **LangGraph**: Multi-agent workflow orchestration
- **Celery + Redis**: Distributed task queue
- **PostgreSQL**: Story and job storage
- **AWS S3 + CloudFront**: Image storage and CDN
- **Gunicorn**: Production WSGI server

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- AWS S3 bucket (or LocalStack for local dev)
- OpenAI API key (for DALL-E 3)
- OpenAI or Anthropic API key (for story generation)

## Setup

1. **Clone and install dependencies**:
```bash
cd kids_story_agent
pip install -r requirements.txt
```

2. **Set up environment variables**:
```bash
# Create .env file (if it doesn't exist)
./setup_env.sh

# Or manually create .env file with your configuration
# Edit .env and add your API keys:
#   - OPENAI_API_KEY (required for DALL-E and OpenAI stories)
#   - ANTHROPIC_API_KEY (required if using Anthropic)
#   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (required for S3)
```

3. **Start infrastructure** (PostgreSQL, Redis, LocalStack):
```bash
docker-compose up -d
```

4. **Run database migrations**:
```bash
alembic upgrade head
```

5. **Start Celery worker** (in a separate terminal):
```bash
celery -A app.celery_app worker --loglevel=info
```

6. **Start the API server**:
```bash
# Development
uvicorn app.main:app --reload

# Production
gunicorn app.main:app -c gunicorn.conf.py
```

7. **Start Streamlit test interface** (optional, in a separate terminal):
```bash
./run_streamlit.sh
# Or: streamlit run streamlit_app.py
```
Then open http://localhost:8501 in your browser.

## API Endpoints

### Generate Story
```http
POST /api/v1/stories/generate
Content-Type: application/json

{
  "prompt": "A brave little mouse goes on an adventure",
  "age_group": "6-8",
  "num_illustrations": 3,
  "webhook_url": "https://your-app.com/webhook"  # Optional
}
```

Response (202 Accepted):
```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Story generation started. Use the job_id to check status."
}
```

### Check Job Status
```http
GET /api/v1/stories/jobs/{job_id}
```

Response:
```json
{
  "job_id": "uuid",
  "status": "completed",
  "story_id": "uuid",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:01:00Z"
}
```

### Get Story
```http
GET /api/v1/stories/{story_id}
```

Response:
```json
{
  "id": "uuid",
  "title": "The Brave Little Mouse",
  "content": "Once upon a time...",
  "age_group": "6-8",
  "images": [
    {
      "id": "uuid",
      "image_url": "https://cdn.example.com/stories/.../image.png",
      "prompt_used": "...",
      "scene_description": "...",
      "display_order": 0
    }
  ]
}
```

## Configuration

Key environment variables:

- `LLM_PROVIDER`: `openai` or `anthropic`
- `OPENAI_API_KEY`: Required for DALL-E 3, also for story if using OpenAI
- `ANTHROPIC_API_KEY`: Required if using Anthropic for stories
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: For S3 uploads
- `S3_BUCKET_NAME`: Your S3 bucket name
- `CLOUDFRONT_DOMAIN`: Optional CloudFront CDN domain
- `RATE_LIMIT_PER_MINUTE`: Default 500

## Testing with Streamlit

A Streamlit-based test interface is included for easy testing:

1. Start the API server (see Setup step 6)
2. Start the Streamlit app:
```bash
./run_streamlit.sh
```
3. Open http://localhost:8501 in your browser
4. Use the interface to:
   - Generate stories with different prompts
   - Check job status with auto-polling
   - View completed stories with images

## Development

Run tests (when available):
```bash
pytest
```

Run linter:
```bash
ruff check app/
```

Format code:
```bash
black app/
```

## Production Deployment

1. Use Gunicorn with multiple workers:
```bash
gunicorn app.main:app -c gunicorn.conf.py
```

2. Scale Celery workers:
```bash
celery -A app.celery_app worker --concurrency=4
```

3. Use a reverse proxy (nginx/traefik) in front of Gunicorn

4. Set up monitoring for:
   - Celery task queue length
   - API response times
   - Error rates
   - External API rate limits (OpenAI/Anthropic)

## License

MIT
