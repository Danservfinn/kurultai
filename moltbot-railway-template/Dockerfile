# Moltbot Railway Template - OpenClaw Gateway with embedded Signal
# Replaces Express gateway with full OpenClaw gateway including built-in webchat UI
# CACHE_BUST: 2026-02-07-v5 - Force rebuild with Express server runtime install

FROM node:22-bookworm-slim

# =============================================================================
# SECTION 1: System Dependencies
# =============================================================================
# Java for signal-cli, Python for Neo4j migrations, curl for healthcheck

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    ca-certificates \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Install Eclipse Temurin JRE 21 (signal-cli 0.13.x requires Java 21, class version 65.0)
RUN curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public | tee /etc/apt/keyrings/adoptium.asc \
    && echo "deb [signed-by=/etc/apt/keyrings/adoptium.asc] https://packages.adoptium.net/artifactory/deb bookworm main" | tee /etc/apt/sources.list.d/adoptium.list \
    && apt-get update && apt-get install -y --no-install-recommends temurin-21-jre \
    && rm -rf /var/lib/apt/lists/* \
    && java -version

# Install Python dependencies for Neo4j migrations
RUN pip3 install --no-cache-dir --break-system-packages \
    neo4j>=5.15.0 \
    pyyaml>=6.0.1 \
    python-dotenv>=1.0.0

# =============================================================================
# SECTION 2: Install signal-cli (JVM version — native binary hangs on Railway)
# =============================================================================
# Using JVM version instead of native GraalVM binary because the native binary
# hangs with "Failed to read local accounts list" on Railway's shared infrastructure.
# Java 17 is already installed above.

ARG SIGNAL_CLI_VERSION=0.13.24
RUN curl -fsSL -o /tmp/signal-cli.tar.gz \
    "https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz" \
    && tar -xzf /tmp/signal-cli.tar.gz -C /opt \
    && rm /tmp/signal-cli.tar.gz \
    && ln -sf /opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli /usr/local/bin/signal-cli \
    && signal-cli --version

# =============================================================================
# SECTION 3: Install OpenClaw Gateway
# =============================================================================
# OpenClaw provides the gateway with built-in webchat UI at :18789

RUN npm install -g openclaw@latest

# =============================================================================
# SECTION 4: Working Directory & Data Directories
# =============================================================================

WORKDIR /app

RUN mkdir -p /data/.signal \
    && mkdir -p /data/.openclaw \
    && mkdir -p /data/workspace \
    && mkdir -p /data/logs

# =============================================================================
# SECTION 5: Import Signal Data (if available)
# =============================================================================

COPY .signal-data/signal-data.tar.gz /opt/signal-data.tar.gz

# =============================================================================
# SECTION 6: Application Files
# =============================================================================
# Copy migration scripts, config, and operational files

# Install Express server dependencies first (for layer caching)
COPY --chown=1000:1000 package*.json /app/
RUN npm install --production

# Copy Express server source files
COPY --chown=1000:1000 src /app/src
COPY --chown=1000:1000 routes /app/routes
COPY --chown=1000:1000 middleware /app/middleware
COPY --chown=1000:1000 config /app/config

COPY --chown=1000:1000 migrations /app/migrations
COPY --chown=1000:1000 openclaw_memory.py /app/
COPY --chown=1000:1000 scripts /app/scripts
COPY --chown=1000:1000 openclaw.json5 /app/openclaw.json5
COPY --chown=1000:1000 openclaw.json /app/openclaw.json
COPY --chown=1000:1000 entrypoint.sh /app/entrypoint.sh
COPY --chown=1000:1000 signal-cli-wrapper.sh /app/signal-cli-wrapper.sh
COPY --chown=1000:1000 souls /app/souls
RUN chmod +x /app/entrypoint.sh /app/signal-cli-wrapper.sh

# =============================================================================
# SECTION 7: Non-Root User Setup
# =============================================================================

RUN groupadd -r moltbot -g 1001 \
    && useradd -r -g moltbot -u 1001 -d /data moltbot \
    && chown -R 1001:1001 /data /app

# NOTE: Do NOT set USER here. entrypoint.sh runs as root to handle
# volume permissions and signal data extraction, then drops to moltbot user.

# =============================================================================
# SECTION 8: Environment Variables
# =============================================================================

ENV NODE_ENV=production
ENV OPENCLAW_STATE_DIR=/data/.openclaw
ENV OPENCLAW_GATEWAY_PORT=18789

# Signal Configuration
# signal-cli uses default XDG path: $HOME/.local/share/signal-cli/ (HOME=/data at runtime)
ENV SIGNAL_ENABLED=true
ENV SIGNAL_ACCOUNT=${SIGNAL_ACCOUNT}

# =============================================================================
# SECTION 9: Health Check
# =============================================================================

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:18789/health || exit 1

# =============================================================================
# SECTION 10: Entry Point
# =============================================================================

EXPOSE 18789

# Railway strips Docker CMD — ENTRYPOINT [] ensures CMD is preserved
ENTRYPOINT []
CMD ["sh", "/app/entrypoint.sh"]
# Build timestamp: Sat Feb  7 23:00:00 EST 2026
# Cache-bust: v3 - Force rebuild with Express server files

# Cache-bust arg - change this to force a full rebuild
ARG CACHE_BUST=2026-02-07-v3
