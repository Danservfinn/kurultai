FROM ghcr.io/goauthentik/server:2025.10

# Authentik 2025.10 Worker
# Must run as root for proper permissions (matching docker-compose.yml)
USER root

# Run the worker using the standard command
CMD ["worker"]
