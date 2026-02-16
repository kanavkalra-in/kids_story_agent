#!/bin/bash
# Script to run Celery locally for debugging (outside Docker)
# This allows you to debug Celery tasks directly in your IDE

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set default values if not in .env
export DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:5432/kids_story_db}
export REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
export CELERY_BROKER_URL=${CELERY_BROKER_URL:-redis://localhost:6379/0}
export CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-redis://localhost:6379/0}
export ENVIRONMENT=${ENVIRONMENT:-development}
export LOG_LEVEL=${LOG_LEVEL:-debug}

echo "Starting Celery worker in debug mode..."
echo "Database: $DATABASE_URL"
echo "Redis: $REDIS_URL"
echo ""
echo "OPTIONS:"
echo "1. Run with debugpy (for VS Code/PyCharm remote debugging):"
echo "   python -m debugpy --listen 0.0.0.0:5679 --wait-for-client -m celery -A app.celery_app worker --pool=solo --loglevel=debug"
echo ""
echo "2. Run with pdb (interactive debugging):"
echo "   celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1"
echo ""
echo "3. Run normally (for breakpoints in IDE):"
echo "   celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1"
echo ""

# Default: Run with debugpy
if [ "$1" == "pdb" ]; then
    echo "Starting with pdb support..."
    celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1
elif [ "$1" == "normal" ]; then
    echo "Starting normally (use IDE breakpoints)..."
    celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1
else
    echo "Starting with debugpy (attach debugger to localhost:5679)..."
    python -m debugpy --listen 0.0.0.0:5679 --wait-for-client -m celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1
fi
