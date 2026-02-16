# Deployment Guide

## Overview

This guide covers production deployment of Kids Story Agent, including infrastructure setup, configuration, scaling, and monitoring.

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** (managed service recommended)
- **Redis 7+** (managed service recommended)
- **AWS Account** (optional, for S3 storage)
- **Domain Name** (optional, for production API)

## Infrastructure Setup

### Database (PostgreSQL)

**Recommended**: Use managed PostgreSQL service:
- **AWS RDS**: PostgreSQL 15+ with Multi-AZ for high availability
- **Google Cloud SQL**: PostgreSQL 15+ with automatic backups
- **Azure Database**: PostgreSQL 15+ with geo-replication

**Configuration**:
- **Instance Size**: Start with `db.t3.medium` (2 vCPU, 4GB RAM), scale as needed
- **Storage**: 100GB+ with autoscaling
- **Backups**: Daily automated backups, 7-day retention
- **Connection Pooling**: Use PgBouncer or connection pooler

**Connection String**:
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/kids_story_db
```

### Redis

**Recommended**: Use managed Redis service:
- **AWS ElastiCache**: Redis 7+ with cluster mode
- **Google Cloud Memorystore**: Redis 7+ with high availability
- **Azure Cache**: Redis 7+ with premium tier

**Configuration**:
- **Instance Size**: Start with `cache.t3.medium` (2 vCPU, 3.22GB RAM)
- **Persistence**: Enable AOF (Append-Only File) for durability
- **High Availability**: Multi-AZ for failover

**Connection String**:
```env
REDIS_URL=redis://host:6379/0
CELERY_BROKER_URL=redis://host:6379/0
CELERY_RESULT_BACKEND=redis://host:6379/0
```

### Storage (AWS S3)

**Setup**:
1. Create S3 bucket: `kids-stories-media`
2. Enable versioning (optional)
3. Configure lifecycle policies (delete old files)
4. Set up CloudFront distribution (optional, for CDN)

**Configuration**:
```env
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=kids-stories-media
CLOUDFRONT_DOMAIN=cdn.example.com  # optional
S3_PUBLIC_READ=false  # Set to true if using CloudFront
```

**IAM Policy** (for S3 access):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::kids-stories-media/*"
    }
  ]
}
```

## Application Deployment

### Environment Variables

Create `.env` file or set environment variables:

```env
# Environment
ENVIRONMENT=production

# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/kids_story_db

# Redis
REDIS_URL=redis://host:6379/0
CELERY_BROKER_URL=redis://host:6379/0
CELERY_RESULT_BACKEND=redis://host:6379/0

# Storage
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=kids-stories-media

# LLM Provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# API Settings
API_KEY=strong_random_api_key_here
RATE_LIMIT_PER_MINUTE=100
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Guardrail Settings
GUARDRAIL_FEAR_THRESHOLD=0.4
GUARDRAIL_VIOLENCE_HARD_THRESHOLD=0.6
MEDIA_GUARDRAIL_MAX_RETRIES=1
GUARDRAIL_AUTO_REJECT_ON_HARD_FAIL=true

# Human Review
REVIEW_TIMEOUT_DAYS=3

# Checkpointer
CHECKPOINTER_CONN_STRING=postgresql://user:password@host:5432/kids_story_db
```

### Database Migrations

**Automatic Migrations (Recommended for Docker)**:
When using Docker Compose, migrations run automatically via a dedicated `migrations` service that executes before the API starts. No manual intervention required.

**Manual Migration (For Non-Docker Deployments)**:
If deploying without Docker, run Alembic migrations manually:

```bash
# Set DATABASE_URL environment variable
export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/kids_story_db

# Run migrations
alembic upgrade head
```

### Docker Deployment

**Dockerfile**:
The Dockerfile includes an entrypoint script that automatically runs migrations before starting the application (unless `MIGRATE=false` is set):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose ports
EXPOSE 8000 8501

# Use entrypoint script (migrations run automatically unless MIGRATE=false)
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
```

**docker-compose.yml**:
The docker-compose configuration includes a dedicated `migrations` service that runs once before the API starts:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: kids_story_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  migrations:
    build: .
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/kids_story_db
      - MIGRATE=true
    depends_on:
      postgres:
        condition: service_healthy
    command: sh -c "alembic upgrade head"
    restart: "no"  # Only run once, don't restart on failure

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - API_KEY=${API_KEY}
      - MIGRATE=false  # Migrations already run by migrations service
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped

  celery:
    build: .
    command: celery -A app.celery_app worker --loglevel=info --concurrency=4
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  postgres_data:
```

**Migration Behavior**:
- The `migrations` service runs once before the API and Celery services start
- If migrations fail, the API and Celery services won't start (prevents running with outdated schema)
- The entrypoint script in the Dockerfile provides a fallback: if `MIGRATE=true` (default), it will run migrations before starting the application
- Set `MIGRATE=false` to skip migrations (useful when using the separate migrations service)

### Kubernetes Deployment

**api-deployment.yaml**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kids-story-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kids-story-api
  template:
    metadata:
      labels:
        app: kids-story-api
    spec:
      containers:
      - name: api
        image: your-registry/kids-story-agent:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: kids-story-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: kids-story-secrets
              key: redis-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: kids-story-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

**celery-deployment.yaml**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kids-story-celery
spec:
  replicas: 5
  selector:
    matchLabels:
      app: kids-story-celery
  template:
    metadata:
      labels:
        app: kids-story-celery
    spec:
      containers:
      - name: celery
        image: your-registry/kids-story-agent:latest
        command: ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: kids-story-secrets
              key: database-url
        resources:
          requests:
            memory: "1Gi"
            cpu: "1000m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
```

## Scaling

### Horizontal Scaling

**API Servers**:
- **Gunicorn Workers**: Start with 4 workers per server
- **Load Balancer**: Use nginx, Traefik, or cloud load balancer
- **Auto-scaling**: Scale based on CPU/memory usage

**Celery Workers**:
- **Concurrency**: 2-4 workers per Celery process
- **Multiple Processes**: Run multiple Celery processes per server
- **Queue Partitioning**: Separate queues for different task types

### Vertical Scaling

**Database**:
- **Connection Pooling**: Use PgBouncer (100-200 connections)
- **Read Replicas**: Use read replicas for read-heavy operations
- **Instance Size**: Scale up based on CPU/memory usage

**Redis**:
- **Memory**: Monitor memory usage, scale up as needed
- **Cluster Mode**: Enable cluster mode for high availability

### Performance Tuning

**Gunicorn Configuration** (`gunicorn.conf.py`):
```python
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
```

**Celery Configuration**:
```python
# app/celery_app.py
task_acks_late = True
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 1000
```

## Monitoring

### Application Metrics

**Key Metrics to Monitor**:
- **API Response Times**: P50, P95, P99 latencies
- **Error Rates**: 4xx, 5xx error percentages
- **Request Throughput**: Requests per second
- **Celery Queue Length**: Pending tasks count
- **Task Execution Times**: Average task duration
- **Database Connection Pool**: Active connections
- **Redis Memory Usage**: Memory consumption

### Logging

**Structured Logging**:
```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

**Log Aggregation**:
- **CloudWatch Logs** (AWS)
- **Stackdriver** (Google Cloud)
- **Azure Monitor** (Azure)
- **ELK Stack** (self-hosted)

### Health Checks

**API Health Endpoint**:
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

**Kubernetes Liveness Probe**:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
```

### Alerting

**Critical Alerts**:
- API error rate > 5%
- Database connection failures
- Redis connection failures
- Celery queue length > 1000
- Pending reviews > 100

**Warning Alerts**:
- API response time P95 > 2s
- Database connection pool > 80% utilized
- Redis memory > 80% utilized

## Security

### API Security

1. **API Key Authentication**: Use strong, randomly generated API keys
2. **Rate Limiting**: Configure appropriate rate limits
3. **CORS**: Set explicit allowed origins (avoid `*`)
4. **HTTPS**: Use TLS/SSL for all API traffic
5. **Request Size Limits**: Prevent DoS attacks

### Database Security

1. **Encryption at Rest**: Enable database encryption
2. **Encryption in Transit**: Use SSL connections
3. **Access Control**: Restrict database access to application servers
4. **Backup Encryption**: Encrypt database backups

### Secrets Management

**Recommended**: Use secrets management service:
- **AWS Secrets Manager**
- **Google Cloud Secret Manager**
- **Azure Key Vault**
- **HashiCorp Vault**

**Never commit secrets to version control!**

## Backup & Recovery

### Database Backups

- **Automated Backups**: Daily automated backups
- **Retention**: 7-30 days
- **Point-in-Time Recovery**: Enable for critical data
- **Test Restores**: Regularly test backup restoration

### Application Data

- **S3 Versioning**: Enable S3 versioning for media files
- **Lifecycle Policies**: Automatically delete old files
- **Cross-Region Replication**: Replicate to backup region

### Disaster Recovery

1. **Backup Strategy**: Regular backups of database and media
2. **Recovery Time Objective (RTO)**: Target < 1 hour
3. **Recovery Point Objective (RPO)**: Target < 15 minutes
4. **Failover Plan**: Document failover procedures

## Cost Optimization

### Infrastructure Costs

1. **Reserved Instances**: Use reserved instances for predictable workloads
2. **Spot Instances**: Use spot instances for Celery workers (with fault tolerance)
3. **Auto-scaling**: Scale down during low-traffic periods
4. **Storage Lifecycle**: Delete old media files automatically

### API Costs

1. **LLM Caching**: Cache common story patterns
2. **Batch Processing**: Process multiple stories in batches
3. **Model Selection**: Use cheaper models when appropriate

## Troubleshooting

### Common Issues

**Database Connection Errors**:
- Check connection string
- Verify database is accessible
- Check connection pool limits

**Redis Connection Errors**:
- Check Redis URL
- Verify Redis is accessible
- Check memory limits

**Celery Task Failures**:
- Check Celery logs
- Verify worker concurrency
- Check task timeout settings

**API Timeouts**:
- Increase Gunicorn timeout
- Check database query performance
- Verify external API response times

## Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure strong `API_KEY`
- [ ] Set explicit `CORS_ORIGINS` (avoid `*`)
- [ ] Use managed PostgreSQL (AWS RDS, Google Cloud SQL)
- [ ] Configure S3 storage with CloudFront CDN
- [ ] Set up monitoring and alerting
- [ ] Run multiple Gunicorn workers and Celery workers
- [ ] Configure reverse proxy (nginx/Traefik)
- [ ] Enable database backups
- [ ] Set up log aggregation
- [ ] Configure secrets management
- [ ] Test disaster recovery procedures
- [ ] Set up rate limiting
- [ ] Enable HTTPS/TLS
- [ ] Configure health checks
- [ ] Set up auto-scaling
- [ ] Document runbooks
