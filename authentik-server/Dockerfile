FROM ghcr.io/goauthentik/server:2025.10

# Authentik 2025.10 - no Redis required

# Override entrypoint entirely to prevent Railway from stripping CMD
ENTRYPOINT []
CMD ["dumb-init", "--", "ak", "server"]
