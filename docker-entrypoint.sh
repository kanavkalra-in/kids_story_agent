#!/bin/bash
set -e

# Function to wait for database to be ready
wait_for_db() {
    echo "Waiting for database to be ready..."
    local host=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
    local user=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    
    # Extract host from DATABASE_URL, default to 'postgres' if not found
    if [ -z "$host" ]; then
        host="postgres"
    fi
    
    # Use pg_isready if available, otherwise use a simple connection test
    if command -v pg_isready &> /dev/null; then
        until pg_isready -h "$host" -U "$user" 2>/dev/null; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    else
        # Fallback: try to connect using Python
        until python -c "
import asyncio
import sys
from sqlalchemy import create_engine, text
from app.config import settings

try:
    sync_url = settings.database_url.replace('+asyncpg', '')
    engine = create_engine(sync_url, connect_args={'connect_timeout': 2})
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    fi
    echo "Database is ready!"
}

# Run migrations if MIGRATE environment variable is set to 'true' or not set (default behavior)
if [ "${MIGRATE:-true}" = "true" ]; then
    wait_for_db
    echo "Running database migrations..."
    alembic upgrade head
    echo "Migrations completed successfully!"
else
    echo "Skipping migrations (MIGRATE=false)"
fi

# Execute the main command
echo "Starting application..."
exec "$@"
