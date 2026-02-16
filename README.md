# 🎨 Kids Story Agent

> **Enterprise-Grade AI Story Generation Platform with Multi-Layer Safety, Quality Evaluation, and Human-in-the-Loop Review**

Transform simple prompts into captivating, age-appropriate children's stories with AI-generated illustrations and videos. Built with production-ready guardrails, comprehensive evaluation metrics, and seamless human oversight—ensuring every story meets the highest standards of safety, quality, and educational value.

---

## ✨ Why Kids Story Agent?

**Most AI story generators are black boxes.** You submit a prompt, get output, and hope it's safe. **Kids Story Agent is different.**

We've built a **production-grade AI system** that combines:

- 🛡️ **Multi-Layer Guardrails**: Three-tier safety framework (OpenAI Moderation API, PII detection, custom LLM analysis) that catches issues before they reach children
- 📊 **Comprehensive Evaluation**: LLM-based quality scoring across 5 dimensions (moral value, theme appropriateness, emotional positivity, age-appropriateness, educational value)
- 👥 **Human-in-the-Loop**: LangGraph-powered interrupt system for seamless human review and approval workflows
- 🔄 **Automatic Retry & Regeneration**: Failed guardrail checks trigger intelligent regeneration with exponential backoff
- ⚡ **Parallel Processing**: LangGraph orchestrates parallel image/video generation, evaluation, and guardrail checks for maximum throughput
- 🎯 **Age-Appropriate Content**: Specialized prompts and safety checks tuned for three age groups (3-5, 6-8, 9-12 years)

**This isn't just a story generator—it's a complete content safety and quality assurance platform.**

---

## 🏗️ High-Level Architecture

```mermaid
graph TB
    subgraph App["Application Layer"]
        API["FastAPI REST API<br/>Authentication, Rate Limiting"]
    end
    
    subgraph Queue["Task Queue"]
        CELERY["Celery Task Queue<br/>Async Job Processing"]
    end
    
    subgraph Workflow["LangGraph Multi-Agent Workflow"]
        INPUT["Input Moderator<br/>OpenAI Moderation API"]
        STORY["Story Writer<br/>LLM: GPT-4/Claude/Ollama"]
        IMG_PROMPT["Image Prompter"]
        VID_PROMPT["Video Prompter"]
        IMG_GEN["Image Generator N instances<br/>DALL-E 3, parallel"]
        VID_GEN["Video Generator M instances<br/>Sora, parallel"]
        ASSEMBLER["Assembler<br/>Validation, sorting"]
        EVAL["Story Evaluator<br/>Quality scoring"]
        STORY_GUARD["Story Guardrail<br/>3-layer text safety"]
        IMG_GUARD["Image Guardrail N instances<br/>Vision-based, with retry"]
        VID_GUARD["Video Guardrail M instances<br/>Prompt moderation"]
        AGGREGATOR["Guardrail Aggregator<br/>Decision logic"]
        REVIEW["Human Review Gate<br/>LangGraph Interrupt"]
        PUBLISHER["Publisher<br/>Final persistence"]
    end
    
    subgraph Storage["Storage & Infrastructure"]
        PG[("PostgreSQL<br/>Stories, jobs, evaluations")]
        REDIS[("Redis<br/>Rate limiting, cache")]
        S3["AWS S3 + CloudFront<br/>Optional media storage"]
        LOCAL["Local Storage<br/>Development"]
    end
    
    API --> CELERY
    CELERY --> INPUT
    INPUT --> STORY
    STORY --> IMG_PROMPT
    STORY --> VID_PROMPT
    IMG_PROMPT --> IMG_GEN
    VID_PROMPT --> VID_GEN
    IMG_GEN --> ASSEMBLER
    VID_GEN --> ASSEMBLER
    ASSEMBLER --> EVAL
    ASSEMBLER --> STORY_GUARD
    ASSEMBLER --> IMG_GUARD
    ASSEMBLER --> VID_GUARD
    EVAL --> AGGREGATOR
    STORY_GUARD --> AGGREGATOR
    IMG_GUARD --> AGGREGATOR
    VID_GUARD --> AGGREGATOR
    AGGREGATOR --> REVIEW
    REVIEW --> PUBLISHER
    
    PUBLISHER --> PG
    API --> REDIS
    ASSEMBLER --> S3
    ASSEMBLER --> LOCAL
```

---

## 🎯 Key Features

### 🛡️ Multi-Layer Guardrails

**Layer 0: OpenAI Moderation API** (Fast Pre-Filter)
- ~50ms latency, zero LLM cost
- Catches: violence, sexual content, self-harm, hate, harassment
- Runs on both input prompts and generated content

**Layer 1: PII Detection** (Regex-Based)
- Zero-latency detection of emails, phone numbers, SSNs, credit cards
- Prevents accidental data leakage in stories

**Layer 2: Custom LLM Safety Analysis** (Domain-Specific)
- Fear intensity scoring (0-1 scale)
- Violence severity assessment
- Brand mention detection
- Political/religious content flags
- Age-group-specific thresholds

**Media Guardrails:**
- Vision-based image safety (NSFW, weapons, realistic children, horror elements)
- Video prompt moderation (text guardrails on Sora prompts; frame sampling planned but not yet implemented)
- Automatic regeneration on hard violations (single retry per media item)

### 📊 Comprehensive Evaluation

Every story receives a **structured quality score** across 5 dimensions:

1. **Moral Score** (1-10): Does the story teach positive values?
2. **Theme Appropriateness** (1-10): Is the theme suitable for the age group?
3. **Emotional Positivity** (1-10): Does it evoke warmth and joy?
4. **Age Appropriateness** (1-10): Is vocabulary/complexity right for the age?
5. **Educational Value** (1-10): Does the child learn something valuable?

**Weighted Overall Score**: Combines all dimensions with configurable weights for final quality assessment.

### 👥 Human-in-the-Loop Review

- **LangGraph Interrupt System**: Graph execution pauses at review gate
- **State Persistence**: Full workflow state saved to PostgreSQL checkpointer
- **Review API**: RESTful endpoints for listing, viewing, and approving/rejecting content
- **Timeout Handling**: Auto-reject after configurable days (default: 3)
- **Review Package**: Includes story, evaluation scores, guardrail results, and media

### ⚡ Advanced Parallelism

**LangGraph Native Parallelism:**
- Static edges: `image_prompter` and `video_prompter` run simultaneously
- Dynamic fan-out: One `Send` instance per image/video prompt → parallel generation
- Guardrail fan-out: All evaluation and guardrail checks run concurrently
- Automatic fan-in: Framework waits for all parallel tasks before proceeding

**Result**: Maximum throughput with minimal latency.

### 🔄 Intelligent Retry & Regeneration

- **Automatic Retry**: Failed guardrail checks trigger single regeneration attempt
- **Exponential Backoff**: Video polling uses configurable backoff strategy
- **Error Handling**: Graceful degradation with detailed error messages

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- OpenAI API key (for DALL-E 3 and Sora)
- Optional: AWS credentials (for S3 storage)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd kids_story_agent

# Install dependencies
pip install -r requirements.txt

# Set up environment
./setup_env.sh  # Or manually create .env file

# Start infrastructure
docker-compose up -d

# Run migrations
alembic upgrade head
```

### Configuration

Create a `.env` file:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/kids_story_db

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Provider (openai, anthropic, or ollama)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Storage (s3 or local)
STORAGE_TYPE=local
LOCAL_STORAGE_PATH=storage/images
LOCAL_VIDEO_STORAGE_PATH=storage/videos

# API Settings
API_KEY=your_api_key_here
RATE_LIMIT_PER_MINUTE=100

# Guardrail Settings
GUARDRAIL_FEAR_THRESHOLD=0.4
GUARDRAIL_VIOLENCE_HARD_THRESHOLD=0.6
MEDIA_GUARDRAIL_MAX_RETRIES=1
GUARDRAIL_AUTO_REJECT_ON_HARD_FAIL=true

# Human Review
REVIEW_TIMEOUT_DAYS=3
```

### Start Services

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
```

### Verify Installation

```bash
curl http://localhost:8000/health
```

View API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 📚 Documentation

Comprehensive documentation is available in the `/docs` folder:

- **[Architecture Deep Dive](docs/architecture.md)**: Detailed system design, LangGraph workflow, and component interactions
- **[Guardrails & Safety](docs/guardrails.md)**: Multi-layer safety framework, violation handling, and configuration
- **[Evaluation System](docs/evaluation.md)**: Quality scoring methodology, metrics, and interpretation
- **[Human-in-the-Loop](docs/human-review.md)**: Review workflow, API usage, and timeout handling
- **[API Reference](docs/api-reference.md)**: Complete endpoint documentation with examples
- **[Deployment Guide](docs/deployment.md)**: Production deployment, scaling, and monitoring
- **[Development Guide](docs/development.md)**: Contributing, testing, and code quality

---

## 🎨 Usage Examples

### Generate a Story

```bash
curl -X POST http://localhost:8000/api/v1/stories/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "prompt": "A brave little mouse goes on an adventure to find a magical cheese",
    "age_group": "6-8",
    "num_illustrations": 3,
    "generate_images": true,
    "generate_videos": false
  }'
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Story generation started. Use the job_id to check status."
}
```

### Check Job Status

```bash
curl http://localhost:8000/api/v1/stories/jobs/{job_id} \
  -H "Authorization: Bearer your_api_key"
```

**Status Values:**
- `pending`: Job is queued
- `processing`: Generation in progress
- `pending_review`: Awaiting human approval
- `completed`: Story ready
- `failed`: Generation failed

### Review Pending Content

```bash
# List pending reviews
curl http://localhost:8000/api/v1/reviews/pending \
  -H "Authorization: Bearer your_api_key"

# Get review details
curl http://localhost:8000/api/v1/reviews/{job_id} \
  -H "Authorization: Bearer your_api_key"

# Approve/Reject
curl -X POST http://localhost:8000/api/v1/reviews/{job_id}/decision \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "decision": "approved",
    "comment": "Looks great!",
    "reviewer_id": "reviewer_123"
  }'
```

### Get Completed Story

```bash
curl http://localhost:8000/api/v1/stories/{story_id} \
  -H "Authorization: Bearer your_api_key"
```

**Response includes:**
- Story text and title
- Evaluation scores (moral, theme, emotional, age, educational)
- Guardrail summary and violations
- Image/video URLs with metadata
- Review decision and comments

---

## 🏛️ System Components

### Core Technologies

- **FastAPI**: High-performance async REST API
- **LangGraph**: Multi-agent workflow orchestration with native parallelism
- **Celery + Redis**: Distributed task queue for background processing
- **PostgreSQL**: Persistent storage with asyncpg driver
- **OpenAI APIs**: DALL-E 3 (images), Sora (videos), Moderation API (safety)
- **Pydantic**: Type-safe data validation and structured LLM outputs

### AI/ML Components

- **LLM Providers**: OpenAI GPT-4, Anthropic Claude, Ollama (local)
- **Image Generation**: DALL-E 3 with optimized prompts
- **Video Generation**: Sora with async polling and exponential backoff
- **Safety Moderation**: OpenAI Moderation API + custom LLM analysis
- **Quality Evaluation**: Structured LLM outputs with weighted scoring

### Infrastructure

- **Storage**: Local filesystem or AWS S3 with CloudFront CDN
- **Rate Limiting**: Redis-backed distributed rate limiting
- **State Management**: PostgreSQL checkpointer for LangGraph interrupts
- **Monitoring**: Structured logging, error tracking, job status cache

---

## 🔒 Security & Safety

### Content Safety

- **Input Moderation**: All user prompts checked before generation
- **Output Guardrails**: Multi-layer safety checks on all generated content
- **PII Detection**: Prevents accidental data leakage
- **Age-Appropriate Filtering**: Specialized checks for each age group

### API Security

- **API Key Authentication**: Bearer token authentication
- **Rate Limiting**: Configurable per-minute limits
- **CORS Protection**: Configurable origin whitelist
- **Request Size Limits**: Prevents DoS attacks
- **SSRF Protection**: Webhook URL validation

### Data Privacy

- **No Data Retention**: Generated content stored only as configured
- **Secure Storage**: S3 encryption, local file permissions
- **Audit Trail**: Review decisions and guardrail violations logged

---

## 📊 Monitoring & Observability

### Logging

- Structured logging with job IDs for traceability
- Log levels: INFO (workflow progress), WARNING (guardrail violations), ERROR (failures)
- All guardrail checks and evaluations logged with details

### Metrics to Monitor

- **API**: Response times, error rates, request throughput
- **Celery**: Task queue length, worker health, execution times
- **Guardrails**: Violation rates, retry counts, auto-reject rates
- **Evaluation**: Average quality scores, score distributions
- **Review**: Pending review count, average review time, approval rates

### Health Checks

```bash
curl http://localhost:8000/health
```

---

## 🚀 Production Deployment

See [Deployment Guide](docs/deployment.md) for detailed instructions.

**Quick Checklist:**
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure strong `API_KEY`
- [ ] Set explicit `CORS_ORIGINS` (avoid `*`)
- [ ] Use managed PostgreSQL (AWS RDS, Google Cloud SQL)
- [ ] Configure S3 storage with CloudFront CDN
- [ ] Set up monitoring and alerting
- [ ] Run multiple Gunicorn workers and Celery workers
- [ ] Configure reverse proxy (nginx/Traefik)

---

## 🤝 Contributing

Contributions are welcome! Please see [Development Guide](docs/development.md) for:
- Code quality standards (ruff, black, mypy)
- Testing guidelines
- Database migration process
- Pull request workflow

---

## 📝 License

MIT

---

## 🆘 Support

- **Documentation**: See `/docs` folder for detailed guides
- **Issues**: Open a GitHub issue for bugs or feature requests
- **API Docs**: Interactive Swagger UI at `/docs` endpoint

---

## 🎓 Learn More

- **LangGraph**: [Official Documentation](https://langchain-ai.github.io/langgraph/)
- **FastAPI**: [Official Documentation](https://fastapi.tiangolo.com/)
- **Celery**: [Official Documentation](https://docs.celeryq.dev/)

---

**Built with ❤️ for safe, high-quality children's content generation.**
