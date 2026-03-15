# Ollama Integration Status

**Date:** 2026-03-04  
**Status:** ✅ COMPLETE  
**Model:** qwen3.5:9b (9.7B, Q4_K_M quantization)

---

## Installation

```bash
# Install Ollama
brew install ollama
brew services start ollama

# Pull model
ollama pull qwen3.5:9b
```

**Model Size:** 6.6 GB  
**Location:** `~/.ollama/models/`

---

## Configuration

### OpenClaw Provider (`~/.openclaw/openclaw.json`)

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "apiKey": "not-needed",
      "api": "openai-completions",
      "models": [
        {
          "id": "qwen3.5:9b",
          "name": "Qwen 3.5 9B (Ollama)",
          "contextWindow": 32768,
          "maxTokens": 8192
        }
      ]
    }
  }
}
```

### Skill Location

`~/.openclaw/agents/main/skills/ollama-inference/`

- `SKILL.md` - Documentation and usage guide
- `ollama_client.py` - Python client library

---

## Usage

### CLI

```bash
# Simple query
ollama run qwen3.5:9b "Your prompt here"

# Interactive mode
ollama run qwen3.5:9b
```

### Python

```python
from skills.ollama_inference.ollama_client import OllamaClient

client = OllamaClient(model="qwen3.5:9b")

# Text generation
response = client.generate("Summarize this text...")
print(response["response"])

# Chat completion
messages = [{"role": "user", "content": "Hello!"}]
response = client.chat(messages)
print(response["message"]["content"])

# Check availability
if client.is_available():
    print("Ollama is running")
```

### curl (Direct API)

```bash
# Generate
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:9b","prompt":"Hello","stream":false}'

# Chat
curl -X POST http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:9b","messages":[{"role":"user","content":"Hello"}]}'

# List models
curl http://localhost:11434/api/tags
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Model Size** | 6.6 GB (9.7B params, Q4_K_M) |
| **Context Window** | 32K tokens |
| **Cold Start** | ~5-10 seconds |
| **Token Generation** | ~10-15 tokens/sec |
| **Memory Usage** | ~8-10 GB RAM |

**Note:** First request after idle period includes model load time (~2-5 seconds).

---

## Use Cases

1. **Fallback Inference** - When cloud APIs are unavailable
2. **Privacy-Sensitive Tasks** - Data never leaves the machine
3. **Rapid Prototyping** - Test prompts before deploying to production
4. **Cost Savings** - Free local inference for non-critical tasks
5. **Draft Generation** - Generate drafts for refinement by larger models

---

## Health Check

```bash
# Check service
brew services list | grep ollama

# Check models
ollama list

# Test inference
ollama run qwen3.5:9b "Test" 2>&1 | head -1
```

---

## Troubleshooting

### Model not responding
```bash
# Restart Ollama service
brew services restart ollama

# Check logs
tail -f ~/.ollama/logs/server.log
```

### Out of memory
```bash
# Reduce context window in request
# Or close other memory-intensive applications
```

### Slow responses
- First request after idle: Model loading (~5-10s)
- Subsequent requests: ~10-15 tokens/sec
- Consider using cloud APIs for latency-sensitive tasks

---

## Integration with Kurultai Agents

Agents can use Ollama as a fallback by configuring:

```json
{
  "model": "ollama/qwen3.5:9b",
  "fallbackChain": ["bailian/qwen3.5-plus", "ollama/qwen3.5:9b"]
}
```

---

*Last updated: 2026-03-04*
