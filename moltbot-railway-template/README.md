# Moltbot Railway Template

A production-ready Railway template for deploying Moltbot with embedded Signal messaging integration using OpenClaw.

## Features

- **Embedded Signal Integration**: signal-cli runs within the same container as the gateway
- **Auto-Start**: signal-cli daemon starts automatically with the gateway
- **Security Policies**: Configurable DM and group chat policies (pairing/allowlist)
- **Health Checks**: Built-in health monitoring for both gateway and Signal
- **Non-Root User**: Runs as unprivileged user for security
- **Graceful Shutdown**: Proper signal handling for clean shutdowns

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Railway Container                    │
│  ┌─────────────────┐    ┌───────────────────────────┐  │
│  │  Moltbot        │    │  signal-cli daemon        │  │
│  │  Gateway        │◄──►│  (embedded)               │  │
│  │  (Node.js)      │    │                           │  │
│  │  Port: 8080     │    │  Port: 8081 (internal)    │  │
│  └─────────────────┘    └───────────────────────────┘  │
│           │                        │                    │
│           ▼                        ▼                    │
│  ┌──────────────────────────────────────────────┐      │
│  │  /data/.signal (Signal account data)         │      │
│  └──────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository>
cd moltbot-railway-template
cp .env.example .env
# Edit .env with your configuration
```

### 2. Signal Account Setup

The template includes pre-linked Signal data in `.signal-data/signal-data.tar.gz`. This archive contains:

- Signal account keys
- Device pairing information
- Account state

To use your own Signal account:

1. Link a device using signal-cli locally
2. Export the data directory: `tar -czf signal-data.tar.gz -C ~/.local/share/signal-cli/data .`
3. Place in `.signal-data/signal-data.tar.gz`

### 3. Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and link project
railway login
railway link

# Deploy
railway up
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNAL_ENABLED` | `true` | Enable Signal channel |
| `SIGNAL_ACCOUNT` | `+15165643945` | Signal phone number (E.164) |
| `SIGNAL_DATA_DIR` | `/data/.signal` | Signal data location |
| `SIGNAL_CLI_PATH` | `/usr/local/bin/signal-cli` | signal-cli binary path |
| `PORT` | `8080` | Gateway HTTP port |
| `LOG_LEVEL` | `info` | Logging level |

See `.env.example` for all available options.

### Security Policies

**DM Policy** (`SIGNAL_DM_POLICY`):
- `pairing`: Requires explicit authorization for new contacts
- `open`: Accepts messages from anyone
- `allowlist`: Only accepts from `SIGNAL_ALLOW_FROM` list
- `blocklist`: Blocks specific numbers

**Group Policy** (`SIGNAL_GROUP_POLICY`):
- `allowlist`: Only join groups with allowed members
- `open`: Join any group invitation
- `blocklist`: Block specific groups

## API Endpoints

### Health Check
```bash
GET /health
```

Returns service health status including Signal readiness.

### Signal Status
```bash
GET /signal/status
```

Returns Signal channel configuration and status.

### Gateway Info
```bash
GET /
```

Returns gateway information and available endpoints.

## Development

### Local Development

```bash
# Install dependencies
npm install

# Run in development mode
npm run dev

# Run tests
npm test
```

### Docker Build

```bash
# Build image
docker build -t moltbot-railway-template .

# Run locally
docker run -p 8080:8080 --env-file .env moltbot-railway-template
```

## File Structure

```
moltbot-railway-template/
├── Dockerfile              # Container definition with signal-cli
├── railway.toml            # Railway deployment config
├── package.json            # Node.js dependencies
├── .env.example            # Environment variable template
├── README.md               # This file
└── src/
    ├── index.js            # Gateway entry point
    └── config/
        └── channels.js     # Signal channel configuration
```

## Security Considerations

1. **Signal Data**: The `.signal-data/signal-data.tar.gz` contains sensitive cryptographic keys. Never commit this to version control.

2. **Environment Variables**: Set `SIGNAL_ACCOUNT` and other secrets via Railway dashboard, not in code.

3. **Access Control**: Configure `SIGNAL_ALLOW_FROM` to restrict who can message the bot.

4. **Non-Root User**: The container runs as UID 1000 for security isolation.

## Troubleshooting

### Signal CLI Not Starting

Check logs:
```bash
railway logs
```

Verify Signal data:
```bash
docker run --rm -it moltbot-railway-template signal-cli --config /data/.signal listAccounts
```

### Health Check Failing

Ensure Signal data is properly extracted:
```bash
# Check if data exists
docker run --rm -it moltbot-railway-template ls -la /data/.signal
```

## License

MIT
# Deployment trigger Thu Feb  5 16:37:29 EST 2026
