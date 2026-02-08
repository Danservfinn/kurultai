FROM caddy:2-alpine

# Cache bust to force rebuild when Caddyfile changes
ARG CACHE_BUST=2026-02-07-v4

# Copy the Caddyfile configuration
COPY Caddyfile /etc/caddy/Caddyfile

# Expose the default port (Railway will override with $PORT)
EXPOSE 80

# Run Caddy with the Caddyfile
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
