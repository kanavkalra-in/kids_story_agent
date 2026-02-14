# Docker Setup Guide

This guide explains how to run all services (API, Celery, and Streamlit) using Docker Compose with a single command.

## Quick Start

1. **Create/Update your `.env` file** with your API keys:
   ```bash
   # If you don't have a .env file, run:
   ./setup_env.sh
   
   # Then edit .env and add your API keys:
   # - OPENAI_API_KEY
   # - ANTHROPIC_API_KEY (if using Anthropic)
   # - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (if using S3)
   ```

2. **Start all services**:
   ```bash
   docker-compose up -d
   ```

3. **Check service status**:
   ```bash
   docker-compose ps
   ```

4. **View logs**:
   ```bash
   # All services
   docker-compose logs -f
   
   # Specific service
   docker-compose logs -f api
   docker-compose logs -f celery
   docker-compose logs -f streamlit
   ```

5. **Stop all services**:
   ```bash
   docker-compose down
   ```

6. **Stop and remove volumes** (clean slate):
   ```bash
   docker-compose down -v
   ```

## Services

The setup includes 6 services:

1. **postgres** - PostgreSQL database (port 5432)
2. **redis** - Redis for Celery broker and caching (port 6379)
3. **localstack** - Local AWS S3 emulator (port 4566)
4. **api** - FastAPI application (port 8000)
5. **celery** - Celery worker for background tasks
6. **streamlit** - Streamlit web UI (port 8501)

## Access Points

- **API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health
- **Streamlit UI**: http://localhost:8501
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **LocalStack S3**: localhost:4566

## Environment Variables

All services automatically load environment variables from the `.env` file. Key variables:

- `DATABASE_URL` - PostgreSQL connection string (auto-configured for Docker)
- `REDIS_URL` - Redis connection string (auto-configured for Docker)
- `CELERY_BROKER_URL` - Celery broker URL (auto-configured for Docker)
- `CELERY_RESULT_BACKEND` - Celery result backend (auto-configured for Docker)
- `OPENAI_API_KEY` - OpenAI API key (required for DALL-E)
- `ANTHROPIC_API_KEY` - Anthropic API key (if using Claude)
- `AWS_ACCESS_KEY_ID` - AWS access key (if using S3)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (if using S3)
- `API_BASE_URL` - API URL for Streamlit (auto-configured for Docker)
- `OLLAMA_BASE_URL` - Ollama API URL (defaults to `http://host.docker.internal:11434` for host Ollama)

## Ollama Configuration

The setup is configured to access Ollama running on your **host machine** at `localhost:11434`. The containers use `host.docker.internal` to reach the host.

**Option 1: Use Ollama on Host (Default)**
- Make sure Ollama is running on your host: `ollama serve`
- The containers will automatically connect to it via `host.docker.internal:11434`
- No additional configuration needed

**Option 2: Run Ollama in Docker**
- Uncomment the `ollama` service in `docker-compose.yml`
- Update `OLLAMA_BASE_URL` in `.env` to: `OLLAMA_BASE_URL=http://ollama:11434`
- Pull the model: `docker exec kids_story_ollama ollama pull llama3.2`

## Troubleshooting

### Services won't start
- Check if ports are already in use: `lsof -i :8000`, `lsof -i :8501`, etc.
- Check logs: `docker-compose logs [service_name]`

### Database connection errors
- Wait for postgres to be healthy: `docker-compose ps`
- Check postgres logs: `docker-compose logs postgres`

### Celery not processing tasks
- Check celery logs: `docker-compose logs celery`
- Verify Redis is running: `docker-compose ps redis`

### Streamlit can't connect to API
- Verify API is healthy: `curl http://localhost:8000/health`
- Check API logs: `docker-compose logs api`

### Ollama connection errors (Cannot assign requested address)
- **If using host Ollama**: Make sure Ollama is running on your host: `ollama serve`
- **If using Docker Ollama**: Uncomment the Ollama service in docker-compose.yml and restart
- Check Ollama is accessible: `curl http://localhost:11434/api/tags` (host) or `docker exec kids_story_ollama curl http://localhost:11434/api/tags` (Docker)
- Verify OLLAMA_BASE_URL is set correctly in your `.env` file

## Rebuilding After Code Changes

If you make code changes, rebuild the containers:

```bash
docker-compose up -d --build
```

## Development vs Production

This setup is configured for **development**. For production:

1. Set `ENVIRONMENT=production` in `.env`
2. Use proper database migrations (Alembic)
3. Configure proper CORS origins
4. Use production-grade secrets management
5. Set up proper logging and monitoring
6. Configure SSL/TLS for HTTPS
