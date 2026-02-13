#!/bin/bash
# Script to run API server

# Development mode
if [ "$1" == "dev" ]; then
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
else
    # Production mode
    gunicorn app.main:app -c gunicorn.conf.py
fi
