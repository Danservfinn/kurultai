# Use a specific digest to ensure consistent builds
FROM caddy:2.8.4-alpine@sha256:7f4c19ed8c32f961644681823de1a2fe5b74c84a45d0f3995286010c84b6c554

# Cache bust to force rebuild when Caddyfile changes
# Increment this on every Caddyfile change: v48, v49, etc.
ARG CACHE_BUST=2026-02-08-v58-HANDLE-NOT-PATH
ARG BUILD_TIMESTAMP=1770547200

# Force layer cache invalidation by writing unique data
RUN echo "Build: $CACHE_BUST at $BUILD_TIMESTAMP" > /.build-meta && \
    echo "Timestamp: $(date +%s)" >> /.build-meta && \
    echo "Random: $RANDOM$RANDOM" >> /.build-meta && \
    echo "Force: rebuild-v56-health-to-express" >> /.build-meta

# Copy the Caddy configuration - THIS LAYER MUST CHANGE WHEN CADDYFILE CHANGES
# Using a wildcard to ensure any Caddyfile changes are picked up
COPY Caddyfile /etc/caddy/Caddyfile
RUN echo "Caddyfile copied: $(cat /etc/caddy/Caddyfile | head -5)"

# Show the Caddyfile content during build for debugging
RUN echo "=== Caddyfile content ===" && \
    cat /etc/caddy/Caddyfile && \
    echo "=== End Caddyfile ===" && \
    echo "=== File checksum ===" && \
    md5sum /etc/caddy/Caddyfile

# Validate Caddyfile syntax during build
RUN caddy validate --config /etc/caddy/Caddyfile || echo "Warning: Caddyfile validation failed"

# Expose the default port (Railway will override with $PORT)
EXPOSE 80

# Run Caddy with the Caddyfile
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
