# skill-sync-service Dockerfile
FROM node:22-bookworm-slim

# Install git for cloning repos and su-exec for privilege drop
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    su-exec \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source and entrypoint
COPY src ./src
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create non-root user
RUN useradd -m -u 1001 skillsync && \
    chown -R skillsync:skillsync /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Expose port
EXPOSE 3000

# Run entrypoint as root to create /data directories, then drop privileges
# Railway strips Docker CMD - use ENTRYPOINT [] to preserve CMD
ENTRYPOINT []
CMD ["/app/entrypoint.sh"]
