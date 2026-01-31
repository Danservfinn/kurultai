FROM registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest

# Railway provides PORT as environment variable
ENV PORT=8080

# Set config directory to match signal-cli-rest-api volume path
# This allows reusing the existing Signal account data
ENV SIGNAL_CLI_CONFIG=/home/.local/share/signal-cli

# Start signal-cli daemon with explicit config directory
ENTRYPOINT ["signal-cli", "--config", "/home/.local/share/signal-cli"]
CMD ["daemon", "--http", "0.0.0.0:8080"]
