# Composio Twitter Integration Setup

This document provides complete instructions for connecting Twitter/X to the Kurultai system via Composio.

## Overview

Composio provides a managed authentication layer and API toolkit for integrating with Twitter/X and 800+ other services. The free tier includes 20,000 API calls per month.

## Quick Start

### 1. Sign Up for Composio

1. Visit [https://platform.composio.dev](https://platform.composio.dev)
2. Create an account (free tier available)
3. Navigate to Settings → API Keys
4. Copy your API key

### 2. Configure Environment

Add your API key to the environment:

```bash
# Add to /data/workspace/souls/main/.env
COMPOSIO_API_KEY=your_composio_api_key_here
```

Or export in your shell:
```bash
export COMPOSIO_API_KEY=your_composio_api_key_here
```

### 3. Install Dependencies

Run the setup script:
```bash
python3 /data/workspace/souls/main/tools/setup_composio_twitter.py
```

Or manually install:
```bash
pip install composio-core
```

### 4. Connect Twitter Account

Authenticate with Twitter/X:
```bash
composio add twitter
```

This will open a browser window for OAuth authentication. Follow the prompts to authorize the connection.

### 5. Verify Connection

Run the verification script:
```bash
python3 /data/workspace/souls/main/tools/verify_composio_twitter.py
```

## Usage Examples

### Basic Twitter Operations

```python
from composio import ComposioToolSet, App, Action

# Initialize toolset
toolset = ComposioToolSet()

# Get Twitter tools
tools = toolset.get_tools(apps=[App.TWITTER])

# Example: Post a tweet (via agent execution)
# The agent will use COMPOSIO_MULTI_EXECUTE_TOOL to call TWITTER_CREATE_TWEET
```

### Using with OpenAI Agents

```python
from openai import OpenAI
from composio_openai import ComposioToolSet, App

# Initialize clients
openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
composio_toolset = ComposioToolSet()

# Get Twitter tools
tools = composio_toolset.get_tools(apps=[App.TWITTER])

# Create assistant with Twitter capabilities
assistant = openai_client.beta.assistants.create(
    name="Twitter Agent",
    instructions="You can post tweets and interact with Twitter",
    tools=tools,
    model="gpt-4-turbo"
)
```

## Available Twitter Actions

Common Twitter/X actions available through Composio:

| Action | Description |
|--------|-------------|
| `TWITTER_CREATE_TWEET` | Post a new tweet |
| `TWITTER_DELETE_TWEET` | Delete a tweet |
| `TWITTER_GET_TWEET` | Get tweet details |
| `TWITTER_SEARCH_TWEETS` | Search for tweets |
| `TWITTER_GET_USER` | Get user profile |
| `TWITTER_FOLLOW_USER` | Follow a user |
| `TWITTER_UNFOLLOW_USER` | Unfollow a user |
| `TWITTER_GET_TIMELINE` | Get home timeline |
| `TWITTER_GET_USER_TWEETS` | Get user's tweets |
| `TWITTER_LIKE_TWEET` | Like a tweet |
| `TWITTER_RETWEET` | Retweet a tweet |

## Troubleshooting

### API Key Not Found
```
Error: COMPOSIO_API_KEY not set
```
**Solution:** Set the environment variable or add to `.env` file.

### Twitter Not Connected
```
Error: No connected account found for Twitter
```
**Solution:** Run `composio add twitter` to authenticate.

### Token Expired
```
Error: Token expired or invalid
```
**Solution:** Re-authenticate with `composio add twitter --force`

## Resources

- [Composio Documentation](https://docs.composio.dev)
- [Twitter Toolkit](https://composio.dev/toolkits/twitter)
- [Composio GitHub](https://github.com/composiohq/composio)
- [Discord Support](https://discord.gg/composio)

## Free Tier Limits

- **API Calls:** 20,000 per month
- **Active Connections:** Unlimited
- **Supported Apps:** All 800+ toolkits

## Security Notes

- The `COMPOSIO_API_KEY` should be treated as a secret
- Never commit the API key to version control
- OAuth tokens are managed securely by Composio
- Connections are scoped per user ID
