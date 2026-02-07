#!/bin/sh
set -e

# skill-sync-service entrypoint
# Ensures /data directories exist before starting the service

echo "==> skill-sync-service entrypoint"

# Ensure skills and backup directories exist
# (Railway volume mounts may hide directories created during build)
mkdir -p /data/skills /data/backups/skills

# Fix permissions for non-root user
chown -R skillsync:skillsync /data

echo "==> Ensured /data/skills and /data/backups/skills exist"
echo "==> Starting skill-sync-service..."

# Drop privileges and run the application
exec su-exec skillsync node src/index.js
