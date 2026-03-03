FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    python3 \
    python3-pip \
    nodejs \
    npm \
    xvfb \
    libgtk-3-0 \
    libnotify4 \
    libnss3 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# Install Antigravity (if downloadable - placeholder)
# Note: Actual installation would require official download
RUN mkdir -p /opt/antigravity

# Set up workspace
WORKDIR /workspace

# Expose port for web access
EXPOSE 3000

# Start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
