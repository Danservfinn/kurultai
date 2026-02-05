# OpenClaw Multi-Agent System Dockerfile
# Production deployment image for Railway with 6 specialized agents

FROM python:3.12-slim

# =============================================================================
# SECTION 1: System Dependencies
# =============================================================================
# Install required system packages for Python packages, Neo4j driver, and Signal

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    gcc \
    libssl-dev \
    pkg-config \
    openjdk-17-jre-headless \
    libfuse2 \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# SECTION 1a: Install signal-cli
# =============================================================================
# Download and install signal-cli for Signal messaging integration

ARG SIGNAL_CLI_VERSION=0.13.12
RUN curl -L -o /tmp/signal-cli.tar.gz \
    "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}-Linux.tar.gz" \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt \
    && ln -s "/opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli" /usr/local/bin/signal-cli \
    && rm /tmp/signal-cli.tar.gz \
    && signal-cli --version

# =============================================================================
# SECTION 2: Working Directory
# =============================================================================

WORKDIR /app

# =============================================================================
# SECTION 3: Python Dependencies
# =============================================================================
# Copy and install requirements first for better layer caching

COPY requirements.txt /app/requirements.txt

# Create requirements.txt if it doesn't exist (fallback for initial setup)
RUN if [ ! -f /app/requirements.txt ] || [ ! -s /app/requirements.txt ]; then \
    echo "# OpenClaw Multi-Agent System Dependencies" > /app/requirements.txt && \
    echo "neo4j>=5.15.0" >> /app/requirements.txt && \
    echo "pydantic>=2.5.0" >> /app/requirements.txt && \
    echo "httpx>=0.25.0" >> /app/requirements.txt && \
    echo "python-dotenv>=1.0.0" >> /app/requirements.txt && \
    echo "structlog>=23.2.0" >> /app/requirements.txt && \
    echo "tenacity>=8.2.0" >> /app/requirements.txt && \
    echo "pyyaml>=6.0.1" >> /app/requirements.txt; \
    fi

RUN pip install --no-cache-dir -r /app/requirements.txt

# =============================================================================
# SECTION 4: Agent Directory Structure
# =============================================================================
# Create all 6 agent directories under /data/.clawdbot/agents/
# These directories store agent-specific state and configuration

RUN mkdir -p /data/.clawdbot/agents/main \
    && mkdir -p /data/.clawdbot/agents/researcher \
    && mkdir -p /data/.clawdbot/agents/writer \
    && mkdir -p /data/.clawdbot/agents/developer \
    && mkdir -p /data/.clawdbot/agents/analyst \
    && mkdir -p /data/.clawdbot/agents/ops

# =============================================================================
# SECTION 5: Workspace Directory Structure
# =============================================================================
# Create workspace directories for agent "souls" and shared resources
# Souls contain agent identity, skills, and operational memory

RUN mkdir -p /data/workspace/souls/main \
    && mkdir -p /data/workspace/souls/researcher \
    && mkdir -p /data/workspace/souls/writer \
    && mkdir -p /data/workspace/souls/developer \
    && mkdir -p /data/workspace/souls/analyst \
    && mkdir -p /data/workspace/souls/ops \
    && mkdir -p /data/workspace/memory \
    && mkdir -p /data/workspace/logs \
    && mkdir -p /data/workspace/temp \
    && mkdir -p /data/workspace/backups

# =============================================================================
# SECTION 6: Additional State Directories
# =============================================================================
# Create directories for sessions, credentials, and configuration

RUN mkdir -p /data/.clawdbot/sessions \
    && mkdir -p /data/.clawdbot/credentials/signal \
    && mkdir -p /data/.clawdbot/skills \
    && mkdir -p /data/.clawdbot/migrations \
    && mkdir -p /data/.signal

# =============================================================================
# SECTION 6b: Import Signal Data (if available)
# =============================================================================
# Copy pre-linked Signal device data into container

COPY .signal-data/signal-data.tar.gz /tmp/signal-data.tar.gz
RUN if [ -f /tmp/signal-data.tar.gz ]; then \
    tar -xzf /tmp/signal-data.tar.gz -C /data/.signal \
    && chown -R 1000:1000 /data/.signal \
    && chmod -R 755 /data/.signal \
    && rm /tmp/signal-data.tar.gz \
    && echo "Signal data imported successfully"; \
    else \
    echo "No Signal data to import"; \
    fi

# =============================================================================
# SECTION 7: Permissions
# =============================================================================
# Set proper ownership and permissions for all data directories
# Using UID 1000 for non-root user (standard practice)

RUN groupadd -r clawdbot -g 1000 \
    && useradd -r -g clawdbot -u 1000 clawdbot \
    && chown -R 1000:1000 /data \
    && chmod -R 755 /data/.clawdbot \
    && chmod -R 755 /data/workspace \
    && chmod -R 755 /data/.signal \
    && chmod 777 /data/workspace/temp \
    && chmod 777 /data/workspace/logs

# =============================================================================
# SECTION 8: Application Code
# =============================================================================
# Copy application code to the container

COPY --chown=1000:1000 . /app/

# =============================================================================
# SECTION 9: Non-Root User Setup
# =============================================================================
# Switch to non-root user for security

USER 1000:1000

# =============================================================================
# SECTION 10: Environment Variables
# =============================================================================
# Default environment variables (can be overridden at runtime)

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CLAWDBOT_STATE_DIR=/data/.clawdbot
ENV CLAWDBOT_WORKSPACE_DIR=/data/workspace
ENV CLAWDBOT_LOG_LEVEL=info
ENV SIGNAL_DATA_DIR=/data/.signal
ENV SIGNAL_ACCOUNT=+15165643945

# =============================================================================
# SECTION 11: Health Check
# =============================================================================
# Basic health check (customize based on your gateway port)

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:18789/health || exit 1

# =============================================================================
# SECTION 12: Entry Point
# =============================================================================
# This container provides the agent configuration and protocols for OpenClaw.
# The actual OpenClaw gateway runs as a separate service.
# This container keeps running to provide file system access for agents.

EXPOSE 8080 18789

# Simple health check server to keep container running
CMD ["python", "/app/health_server.py"]
