# Kids Story Agent

A scalable FastAPI backend for generating children's stories with AI-generated illustrations and videos. The system uses LangGraph for multi-agent workflow orchestration, Celery for distributed task processing, and supports multiple LLM providers (OpenAI, Anthropic, Ollama).

## 🎯 Features

- **AI Story Generation**: Generate age-appropriate stories (3-5, 6-8, 9-12 years) using GPT-4, Claude, or Ollama
- **Image Generation**: Create illustrations using DALL-E 3
- **Video Generation**: Generate short videos using Sora (OpenAI)
- **Parallel Processing**: LangGraph orchestrates parallel image and video generation
- **Async Processing**: Celery-based task queue for scalable background processing
- **Webhook Support**: Get notified when story generation completes
- **Rate Limiting**: Redis-backed distributed rate limiting
- **Multiple Storage Options**: Support for local storage or AWS S3 with CloudFront CDN
- **Scalable Architecture**: Designed to handle high-volume requests

## 🏗️ Architecture

### System Components

- **FastAPI**: REST API with async support and automatic OpenAPI documentation
- **LangGraph**: Multi-agent workflow orchestration with parallel execution
- **Celery + Redis**: Distributed task queue for background processing
- **PostgreSQL**: Persistent storage for stories, jobs, and metadata
- **AWS S3 + CloudFront**: Optional cloud storage and CDN for media files
- **Gunicorn**: Production WSGI server with multiple workers

### LangGraph Workflow

The story generation process follows a sophisticated multi-agent workflow:

```
┌──────────────┐
│ story_writer │
└──────┬───────┘
       │
       ├──────────────┬──────────────┐
       │              │              │
       ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│image_prompter│ │video_prompter│ │  (parallel) │
└──────┬───────┘ └──────┬───────┘ └─────────────┘
       │                │
       │                │
       ▼                ▼
┌─────────────────────────────────────┐
│   route_to_generators (fan-out)      │
│  Creates Send instances for each     │
│  image/video prompt                  │
└──────┬────────────────┬──────────────┘
       │                │
       ▼                ▼
┌─────────────┐ ┌─────────────┐
│generate_    │ │generate_    │
│single_image │ │single_video │
│  (×N)       │ │  (×M)       │
└──────┬───────┘ └──────┬───────┘
       │                │
       └────────┬───────┘
                │ (fan-in)
                ▼
         ┌──────────┐
         │assembler │
         └────┬─────┘
              │
              ▼
            END
```

**Key Workflow Features:**

1. **Prompter Parallelism**: After story generation, both `image_prompter` and `video_prompter` run in parallel (static edges from `story_writer`)

2. **Dynamic Fan-out**: The `route_to_generators` function creates one `Send` instance per image/video prompt, enabling parallel generation of all media

3. **Automatic Fan-in**: LangGraph automatically waits for all `Send` instances to complete before proceeding to the `assembler` node

4. **State Reducers**: Results accumulate via `operator.add` reducers on `image_urls`, `image_metadata`, `video_urls`, and `video_metadata` fields

5. **Validation & Assembly**: The `assembler` node validates results, sorts by display order, and prepares the final story output

See the [Graph Structure](#graph-structure) section below for a visual diagram.

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- AWS S3 bucket (optional, for cloud storage)
- API Keys:
  - OpenAI API key (required for DALL-E 3 and Sora)
  - Anthropic API key (optional, if using Claude)
  - AWS credentials (optional, if using S3)

## 🚀 Quick Start

### 1. Clone and Install Dependencies

```bash
cd kids_story_agent
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the project root:

```bash
# Use the setup script
./setup_env.sh

# Or manually create .env with:
```

**Required Configuration:**

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/kids_story_db

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Provider (choose one: openai, anthropic, ollama)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
# ANTHROPIC_API_KEY=your_anthropic_api_key_here  # If using Anthropic
# OLLAMA_BASE_URL=http://localhost:11434  # If using Ollama
# OLLAMA_MODEL=llama3.2  # If using Ollama

# Storage (choose: s3 or local)
STORAGE_TYPE=local
LOCAL_STORAGE_PATH=storage/images
LOCAL_VIDEO_STORAGE_PATH=storage/videos

# AWS S3 (if using cloud storage)
# AWS_ACCESS_KEY_ID=your_access_key
# AWS_SECRET_ACCESS_KEY=your_secret_key
# AWS_REGION=us-east-1
# S3_BUCKET_NAME=kids-stories-media
# CLOUDFRONT_DOMAIN=your-cloudfront-domain.cloudfront.net

# API Settings
API_KEY=your_api_key_here  # Optional, leave empty to disable auth
RATE_LIMIT_PER_MINUTE=100
MAX_REQUEST_SIZE_MB=10

# CORS (comma-separated origins, or "*" for all)
CORS_ORIGINS=*

# Environment
ENVIRONMENT=development
```

### 3. Start Infrastructure

Start PostgreSQL and Redis using Docker Compose:

```bash
docker-compose up -d
```

This will start:
- PostgreSQL on port 5432
- Redis on port 6379

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start Services

**Terminal 1 - Celery Worker:**
```bash
celery -A app.celery_app worker --loglevel=info
```

**Terminal 2 - API Server:**
```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn app.main:app -c gunicorn.conf.py
```

**Terminal 3 - Streamlit UI (Optional):**
```bash
./run_streamlit.sh
# Or: streamlit run streamlit_app.py
```

Then open http://localhost:8501 in your browser.

### 6. Verify Installation

Check the API health:
```bash
curl http://localhost:8000/health
```

View API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📚 API Documentation

### Authentication

All endpoints require API key authentication via the `Authorization` header:

```http
Authorization: Bearer your_api_key_here
```

Or set `API_KEY` in `.env` to enable authentication. Leave it empty to disable (not recommended for production).

### Generate Story

Create a new story generation job:

```http
POST /api/v1/stories/generate
Content-Type: application/json
Authorization: Bearer your_api_key

{
  "prompt": "A brave little mouse goes on an adventure to find a magical cheese",
  "age_group": "6-8",
  "num_illustrations": 3,
  "generate_images": true,
  "generate_videos": false,
  "webhook_url": "https://your-app.com/webhook"  # Optional
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Story generation started. Use the job_id to check status."
}
```

**Request Parameters:**
- `prompt` (string, required): Story prompt/idea
- `age_group` (string, required): One of `"3-5"`, `"6-8"`, `"9-12"`
- `num_illustrations` (integer, required): Number of images/videos to generate (1-10)
- `generate_images` (boolean, optional): Enable image generation (default: true)
- `generate_videos` (boolean, optional): Enable video generation (default: false)
- `webhook_url` (string, optional): URL to receive completion notification

### Check Job Status

Get the status of a story generation job:

```http
GET /api/v1/stories/jobs/{job_id}
Authorization: Bearer your_api_key
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "story_id": "660e8400-e29b-41d4-a716-446655440001",
  "error": null,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:01:00Z"
}
```

**Status Values:**
- `pending`: Job is queued
- `processing`: Story generation in progress
- `completed`: Story ready
- `failed`: Generation failed (check `error` field)

### Get Story

Retrieve a completed story:

```http
GET /api/v1/stories/{story_id}
Authorization: Bearer your_api_key
```

**Response:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "title": "The Brave Little Mouse",
  "content": "Once upon a time, in a cozy little house...",
  "age_group": "6-8",
  "prompt": "A brave little mouse goes on an adventure",
  "created_at": "2024-01-01T00:00:00Z",
  "images": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "image_url": "http://localhost:8000/api/v1/stories/images/stories/.../image.png",
      "prompt_used": "A brave little mouse standing at the edge of a magical forest...",
      "scene_description": "The mouse begins its adventure",
      "display_order": 0
    }
  ],
  "videos": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "video_url": "http://localhost:8000/api/v1/stories/videos/stories/.../video.mp4",
      "prompt_used": "A brave little mouse running through a magical forest...",
      "scene_description": "The mouse runs through the forest",
      "display_order": 0
    }
  ]
}
```

**Note:** You can use either `story_id` or `job_id` in the URL path.

### Regenerating the Graph Diagram

To regenerate the graph structure diagram:

```bash
python generate_graph_diagram.py
```

This creates `docs/graph_structure.svg`. To convert to PNG, install dependencies:
```bash
pip install cairosvg pillow
```

The script will automatically generate a PNG version if these packages are available.

### List Stories

Get a paginated list of all completed stories:

```http
GET /api/v1/stories?limit=10&offset=0
Authorization: Bearer your_api_key
```

**Response:**
```json
{
  "stories": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "title": "The Brave Little Mouse",
      "age_group": "6-8",
      "prompt": "A brave little mouse goes on an adventure",
      "created_at": "2024-01-01T00:00:00Z",
      "num_images": 3
    }
  ],
  "total": 42
}
```

### Serve Media Files

Images and videos are served via dedicated endpoints:

```http
GET /api/v1/stories/images/{file_path}
GET /api/v1/stories/videos/{file_path}
```

**Example:**
```
GET /api/v1/stories/images/stories/{story_id}/{image_id}.png
GET /api/v1/stories/videos/stories/{story_id}/{video_id}.mp4
```

## 🎨 Graph Structure

The LangGraph workflow orchestrates the story generation process through a series of interconnected nodes:

![Graph Structure](docs/graph_structure.svg)

**Node Descriptions:**

1. **story_writer**: Generates the story text and title based on the user prompt and age group
2. **image_prompter**: Extracts key scenes and creates DALL-E-optimized image prompts (runs in parallel with video_prompter)
3. **video_prompter**: Extracts key scenes and creates Sora-optimized video prompts (runs in parallel with image_prompter)
4. **route_to_generators**: Fan-out function that creates `Send` instances for each image/video prompt
5. **generate_single_image**: Generates a single image using DALL-E 3 (executed N times in parallel)
6. **generate_single_video**: Generates a single video using Sora (executed M times in parallel)
7. **assembler**: Validates results, sorts by display order, and prepares final output

**Parallelism Strategy:**

- **Static Parallelism**: `image_prompter` and `video_prompter` run simultaneously after story generation
- **Dynamic Parallelism**: Each image/video prompt triggers a separate `Send` instance, enabling parallel generation of all media
- **Automatic Synchronization**: LangGraph waits for all parallel tasks to complete before proceeding to the assembler

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` | Yes |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | Yes |
| `LLM_PROVIDER` | LLM provider: `openai`, `anthropic`, or `ollama` | `ollama` | Yes |
| `OPENAI_API_KEY` | OpenAI API key (for DALL-E, Sora, or OpenAI stories) | - | If using OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic API key | - | If using Anthropic |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` | If using Ollama |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2` | If using Ollama |
| `STORAGE_TYPE` | Storage backend: `s3` or `local` | `local` | Yes |
| `LOCAL_STORAGE_PATH` | Local image storage path | `storage/images` | If using local |
| `LOCAL_VIDEO_STORAGE_PATH` | Local video storage path | `storage/videos` | If using local |
| `AWS_ACCESS_KEY_ID` | AWS access key | - | If using S3 |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | - | If using S3 |
| `S3_BUCKET_NAME` | S3 bucket name | `kids-stories-media` | If using S3 |
| `CLOUDFRONT_DOMAIN` | CloudFront CDN domain | - | Optional |
| `API_KEY` | API authentication key | - | Optional |
| `RATE_LIMIT_PER_MINUTE` | Rate limit per minute | `100` | No |
| `MAX_REQUEST_SIZE_MB` | Maximum request body size | `10` | No |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | - | No |
| `ENVIRONMENT` | Environment: `development` or `production` | `development` | No |

### LLM Provider Configuration

**OpenAI:**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

**Anthropic:**
```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**Ollama (Local):**
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Storage Configuration

**Local Storage:**
```env
STORAGE_TYPE=local
LOCAL_STORAGE_PATH=storage/images
LOCAL_VIDEO_STORAGE_PATH=storage/videos
```

**AWS S3:**
```env
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=kids-stories-media
CLOUDFRONT_DOMAIN=your-domain.cloudfront.net  # Optional
```

## 🧪 Testing

### Using Streamlit UI

The included Streamlit interface provides an easy way to test the API:

1. Start the API server (see [Quick Start](#-quick-start))
2. Start Streamlit:
   ```bash
   ./run_streamlit.sh
   ```
3. Open http://localhost:8501
4. Use the interface to:
   - Generate stories with different prompts
   - Check job status with auto-polling
   - View completed stories with images and videos

### Using cURL

**Generate a story:**
```bash
curl -X POST http://localhost:8000/api/v1/stories/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "prompt": "A magical forest adventure",
    "age_group": "6-8",
    "num_illustrations": 3,
    "generate_images": true,
    "generate_videos": false
  }'
```

**Check status:**
```bash
curl http://localhost:8000/api/v1/stories/jobs/{job_id} \
  -H "Authorization: Bearer your_api_key"
```

**Get story:**
```bash
curl http://localhost:8000/api/v1/stories/{story_id} \
  -H "Authorization: Bearer your_api_key"
```

## 🛠️ Development

### Project Structure

```
kids_story_agent/
├── app/
│   ├── agents/          # LangGraph workflow nodes
│   │   ├── graph.py     # Workflow definition
│   │   ├── state.py     # State schema
│   │   ├── story_writer.py
│   │   ├── image_prompter.py
│   │   ├── video_prompter.py
│   │   ├── image_generator.py
│   │   ├── video_generator.py
│   │   └── assembler.py
│   ├── api/             # FastAPI routes
│   │   ├── stories.py
│   │   └── auth.py
│   ├── db/              # Database session management
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # External service clients
│   │   ├── llm.py
│   │   ├── openai_client.py
│   │   ├── s3.py
│   │   └── redis_client.py
│   ├── tasks/           # Celery tasks
│   ├── utils/           # Utility functions
│   ├── config.py        # Configuration
│   └── main.py          # FastAPI app
├── alembic/             # Database migrations
├── storage/             # Local file storage
├── docs/                # Documentation
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### Running Tests

```bash
# Run tests (when available)
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check app/

# Format code
black app/

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## 🚀 Production Deployment

### 1. Environment Setup

Set production environment variables:
```env
ENVIRONMENT=production
API_KEY=strong_random_api_key_here
CORS_ORIGINS=https://yourdomain.com
```

### 2. Database

Use managed PostgreSQL (AWS RDS, Google Cloud SQL, etc.) or run PostgreSQL in production:
```bash
# Run migrations
alembic upgrade head
```

### 3. Start Services

**API Server (Gunicorn):**
```bash
gunicorn app.main:app -c gunicorn.conf.py
```

**Celery Worker:**
```bash
celery -A app.celery_app worker --concurrency=4 --loglevel=info
```

**Celery Beat (if using scheduled tasks):**
```bash
celery -A app.celery_app beat --loglevel=info
```

### 4. Reverse Proxy

Use nginx or Traefik in front of Gunicorn:

**nginx example:**
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 5. Monitoring

Monitor:
- **Celery**: Task queue length, worker health, task execution times
- **API**: Response times, error rates, request throughput
- **External APIs**: Rate limits for OpenAI/Anthropic
- **Database**: Connection pool, query performance
- **Redis**: Memory usage, connection count

### 6. Scaling

- **Horizontal Scaling**: Run multiple Gunicorn workers and Celery workers
- **Load Balancing**: Use a load balancer (nginx, AWS ALB) in front of multiple API instances
- **Database**: Use connection pooling and read replicas for high read loads
- **Redis**: Use Redis Cluster for high availability

## 🔒 Security Considerations

1. **API Authentication**: Always set `API_KEY` in production
2. **CORS**: Configure `CORS_ORIGINS` explicitly (avoid `*` in production)
3. **Rate Limiting**: Adjust `RATE_LIMIT_PER_MINUTE` based on your needs
4. **Input Validation**: All inputs are validated and sanitized
5. **SSRF Protection**: Webhook URLs are validated to prevent SSRF attacks
6. **Path Traversal**: File serving endpoints prevent directory traversal
7. **Request Size Limits**: `MAX_REQUEST_SIZE_MB` prevents DoS attacks

## 📝 License

MIT

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

For issues and questions, please open an issue on GitHub.
