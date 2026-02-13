#!/bin/bash
# Script to create .env file from template

if [ -f ".env" ]; then
    echo "⚠️  .env file already exists. Skipping creation."
    echo "If you want to recreate it, delete .env first and run this script again."
    exit 0
fi

echo "Creating .env file from template..."

cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/kids_story_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# AWS S3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=kids-stories-media
CLOUDFRONT_DOMAIN=

# LLM Provider (openai or anthropic)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# DALL-E
DALLE_MODEL=dall-e-3
DALLE_SIZE=1024x1024
DALLE_QUALITY=standard

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
RATE_LIMIT_PER_MINUTE=500

# Environment
ENVIRONMENT=development
EOF

echo "✅ .env file created successfully!"
echo ""
echo "⚠️  IMPORTANT: Please edit .env file and add your API keys:"
echo "   - OPENAI_API_KEY (required for DALL-E and if using OpenAI for stories)"
echo "   - ANTHROPIC_API_KEY (required if using Anthropic for stories)"
echo "   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (required for S3 uploads)"
echo "   - Update other settings as needed"
