FROM registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest

# Create non-root user for security
RUN addgroup -g 1000 signaluser && \
    adduser -D -u 1000 -G signaluser signaluser

# Railway provides PORT as environment variable
ENV PORT=8080

# Set config directory for signal-cli
ENV SIGNAL_CLI_CONFIG=/home/signaluser/.local/share/signal-cli

# Create config directory with proper ownership
RUN mkdir -p /home/signaluser/.local/share/signal-cli && \
    chown -R signaluser:signaluser /home/signaluser

# Switch to non-root user
USER signaluser:signaluser

# Health check - verify daemon is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD signal-cli --config /home/signaluser/.local/share/signal-cli listAccounts > /dev/null 2>&1 || exit 1

# Start signal-cli daemon with explicit config directory
ENTRYPOINT ["signal-cli", "--config", "/home/signaluser/.local/share/signal-cli"]
CMD ["daemon", "--http", "0.0.0.0:8080"]
