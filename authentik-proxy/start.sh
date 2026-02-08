#!/bin/sh
# Start script for Caddy with debug output

echo "=== Caddy Start Script ==="
echo "Cache bust: 2026-02-08-v38"
echo ""
echo "=== Caddyfile.json contents (first 100 lines) ==="
head -100 /etc/caddy/Caddyfile.json
echo ""
echo "=== Starting Caddy ==="
exec caddy run --config /etc/caddy/Caddyfile.json
