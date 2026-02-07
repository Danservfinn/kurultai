# Parse Slack Bot

A Slack bot that integrates with [Parse](https://parsethe.media) API to provide article analysis, truth scoring, and bias-free rewrites directly in Slack workspaces.

## Features

| Command | Description | Cost |
|---------|-------------|------|
| `/parse-score <url>` | Quick truth score (0-100) | Free |
| `/parse-analyze <url>` | Full analysis with breakdown | 3 credits |
| `/parse-rewrite <url>` | Bias-free rewrite | 1 credit |
| `/parse-help` | Show command reference | Free |

## Installation

### 1. Clone and Install

```bash
cd /Users/kurultai/molt/slack-bot
pip install -r requirements.txt
```

### 2. Create Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "Parse Bot"
4. Workspace: Select your workspace

### 3. Configure OAuth & Permissions

Under "OAuth & Permissions", add these Bot Token Scopes:

- `commands:run` - Execute slash commands
- `chat:write` - Send messages
- `app_mentions:read` - Receive @mentions

### 4. Create Slash Commands

Under "Slash Commands", create:

| Command | Request URL | Description |
|---------|-------------|-------------|
| `/parse-score` | `https://your-domain.com/slack/score` | Quick truth score |
| `/parse-analyze` | `https://your-domain.com/slack/analyze` | Full analysis |
| `/parse-rewrite` | `https://your-domain.com/slack/rewrite` | Bias-free rewrite |
| `/parse-help` | `https://your-domain.com/slack/help` | Command reference |

### 5. Enable Socket Mode (Development)

Under "Socket Mode":
1. Toggle "Enable Socket Mode" to On
2. Copy the "App-Level Token" (starts with `xapp-`)

### 6. Set Environment Variables

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_SIGNING_SECRET="your-signing-secret"
export SLACK_APP_LEVEL_TOKEN="xapp-your-app-token"
export PARSE_API_KEY="parse_pk_prod_..."
export PARSE_BASE_URL="https://kind-playfulness-production.up.railway.app"
```

### 7. Run the Bot

```bash
python app.py
```

## Deployment (Railway)

### 1. Create Railway Service

```bash
railway login
railway init
# Select "Python" template
```

### 2. Configure Environment Variables

In Railway dashboard, add:

| Variable | Value |
|----------|-------|
| `SLACK_BOT_TOKEN` | xoxb-... |
| `SLACK_SIGNING_SECRET` | Your signing secret |
| `PARSE_API_KEY` | parse_pk_prod_... |
| `PARSE_BASE_URL` | https://parsethe.media |

### 3. Update Slack App URLs

After deployment, update your Slack app slash command URLs to:

- `https://your-service.railway.app/slack/score`
- `https://your-service.railway.app/slack/analyze`
- `https://your-service.railway.app/slack/rewrite`
- `https://your-service.railway.app/slack/help`

## Pricing Model

### Free Tier
- 10 analyses per month
- Quick score unlimited
- Community support

### Pro Tier - $49/month/workspace
- 500 analyses per month
- Full analysis and rewrite
- Priority queue processing
- Email support

### Enterprise - Custom
- Unlimited analyses
- Dedicated support
- Custom integrations
- SLA guarantee

## Revenue Projections

| Workspaces | ARPC | MRR |
|------------|------|-----|
| 10 | $49 | $490 |
| 50 | $49 | $2,450 |
| 100 | $49 | $4,900 |
| 500 | $49 | $24,500 |

**ARPC** = Average Revenue Per Customer

## Usage Tracking

The bot tracks Parse API usage per workspace for billing:

```python
from tools.parse_api_client import ParseClient

# Get usage statistics
stats = ParseClient.get_usage_stats()
print(f"Daily credits used: {stats.daily_credits_used}/{stats.daily_limit}")
print(f"Costs by agent: {stats.costs_by_agent}")
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Slack     │────▶│  Slack Bot  │────▶│  Parse API  │
│  Workspace  │     │  (Python)   │     │ (Analysis)  │
└─────────────┘     └─────────────┘     └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   Stripe    │
                     │  (Billing)  │
                     └─────────────┘
```

## Development

### Running Tests

```bash
cd /Users/kurultai/molt
python tools/test_parse_client.py
```

### Adding New Commands

1. Add command handler in `app.py`:

```python
@app.command("/parse-mycommand")
async def handle_mycommand(ack, body, respond):
    await ack()
    # Your code here
```

2. Register slash command in Slack app settings
3. Deploy

## Troubleshooting

### "Invalid credentials" error
- Check `SLACK_BOT_TOKEN` starts with `xoxb-`
- Verify OAuth scopes are correct

### "Command not found" error
- Verify slash command is registered in Slack app
- Check Request URL matches deployment URL

### Parse API errors
- Check `PARSE_API_KEY` is valid
- Verify Parse account has credits available

## Support

- Email: support@parsethe.media
- Docs: https://parsethe.media/docs
- Issues: https://github.com/danservfinn/parse/issues

## License

Proprietary - All rights reserved
