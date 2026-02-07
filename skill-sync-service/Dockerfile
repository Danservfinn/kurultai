# skill-sync-service Dockerfile
FROM node:22-bookworm-slim

# Install git for cloning repos
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source
COPY src ./src

# Create directories for skills and backups
RUN mkdir -p /data/skills /data/backups/skills

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Expose port
EXPOSE 3000

# Run as non-root user
RUN useradd -m -u 1001 skillsync && \
    chown -R skillsync:skillsync /app /data
USER skillsync

CMD ["node", "src/index.js"]
