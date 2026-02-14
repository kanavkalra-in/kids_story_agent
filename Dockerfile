FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports (API and Streamlit)
EXPOSE 8000 8501

# Default command (can be overridden)
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
