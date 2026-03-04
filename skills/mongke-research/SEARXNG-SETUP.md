# SearXNG Setup Guide for Mongke Research

**Status:** ⚠️ Docker required for self-hosting

---

## Overview

SearXNG is a privacy-focused metasearch engine that aggregates results from 70+ search engines.

**For Mongke Research:** Provides web search capabilities to automatically find research sources.

---

## Option 1: Self-Host with Docker (Recommended)

### Prerequisites

- Docker installed and running
- 512MB RAM available
- Port 8080 available

### Installation

```bash
# Create directory
mkdir -p ~/searxng && cd ~/searxng

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  searxng:
    image: searxng/searxng:latest
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://localhost:8080/
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"
EOF

# Start SearXNG
docker compose up -d

# Wait for startup (30 seconds)
sleep 30

# Test
curl http://localhost:8080/search?q=test\&format=json
```

### Verify Installation

```bash
# Health check
curl http://localhost:8080/healthz

# Test search
curl "http://localhost:8080/search?q=OpenClaw&format=json"
```

### Configure Mongke Research

Once SearXNG is running locally, Mongke research will automatically use it:

```python
from skills.mongke_research.research import MongkeResearchSkill

skill = MongkeResearchSkill()

# With SearXNG running locally, this will auto-find sources
result = skill.research(
    query="OpenClaw agent framework",
    # sources not needed - SearXNG will find them
    output="neo4l,json"
)
```

---

## Option 2: Use Without SearXNG (Manual URLs)

If SearXNG isn't available, provide URLs manually:

```python
from skills.mongke_research.research import MongkeResearchSkill

skill = MongkeResearchSkill()

# Provide URLs directly
result = skill.research(
    query="OpenClaw analysis",
    sources=[
        "https://github.com/openclaw/openclaw",
        "https://docs.openclaw.ai",
        "https://clawhub.com"
    ],
    output="neo4j"
)
```

---

## Option 3: Public Instances (Unreliable)

The search module includes fallback to public SearXNG instances, but:
- Many block automated requests
- Rate limiting is common
- Not suitable for production use

**Current fallback list:**
- https://search.sapti.me
- https://searx.priv.pw
- https://searxng.nicfab.eu

---

## Troubleshooting

### Docker Not Running

```bash
# Check Docker status
docker ps

# Start Docker Desktop (macOS)
open -a Docker

# Or start Docker daemon (Linux)
sudo systemctl start docker
```

### Port 8080 Already in Use

```bash
# Change port in docker-compose.yml
ports:
  - "127.0.0.1:8888:8080"

# Update Mongke research to use new port
search = SearXNGSearch(base_url="http://localhost:8888")
```

### SearXNG Returns No Results

```bash
# Check enabled engines
curl http://localhost:8080/engines

# Enable more engines in searxng/settings.yml
# Edit: use_default_settings: true
```

---

## API Reference

### Search Endpoint

```
GET /search?q={query}&format=json&pageno={page}
```

**Response:**
```json
{
  "query": "search query",
  "number_of_results": 10,
  "results": [
    {
      "title": "Result Title",
      "url": "https://example.com",
      "content": "Snippet text...",
      "engine": "google",
      "category": "general",
      "score": 0.95
    }
  ]
}
```

### Categories

- `general` - General web search
- `news` - News articles
- `social_media` - Social media posts
- `it` - IT/technical content
- `science` - Scientific content
- `images` - Image search
- `videos` - Video search

---

## Integration with Mongke Research

### Automatic Source Discovery

When SearXNG is available:

```python
skill = MongkeResearchSkill()

# Auto-finds sources via SearXNG
result = skill.research(
    query="Your research topic",
    # sources=[] not needed
)
```

### Manual Source Specification

```python
# Provide your own URLs
result = skill.research(
    query="Your topic",
    sources=["https://url1.com", "https://url2.com"]
)
```

### Search-Only Mode

```python
from skills.mongke_research.searxng_search import SearXNGSearch

search = SearXNGSearch()
results = search.search("your query", limit=10)

# Get just URLs
urls = [r['url'] for r in results]
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Search latency** | 1-3 seconds |
| **Results per query** | 10-50 typical |
| **Concurrent requests** | 10+ supported |
| **Memory usage** | ~200MB |

---

## Resources

- **GitHub:** https://github.com/searxng/searxng
- **Docs:** https://docs.searxng.org/
- **Public Instances:** https://searx.space/

---

*Setup complete. Run `docker compose up -d` to start SearXNG.*
