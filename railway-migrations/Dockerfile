# One-shot migration runner for Railway Neo4j
# Builds, runs migrations, and exits with status

FROM python:3.12-slim

# Install Neo4j driver dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy migration files
COPY requirements.txt /app/
COPY migrations/ /app/migrations/
COPY scripts/ /app/scripts/
COPY openclaw_memory.py /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Default command: run migrations to version 3
CMD ["python", "scripts/run_migrations.py", "--target-version", "3"]
