# Ollama Inference Skill

**Name:** ollama-inference  
**Version:** 1.0  
**Author:** Kublai  
**Description:** Local LLM inference using Ollama with qwen3.5:9b model

---

## Purpose

Provides local model inference capabilities for the Kurultai agent system using Ollama. This skill enables:
- Local text generation without API costs
- Privacy-preserving inference (data never leaves the machine)
- Fallback when cloud APIs are unavailable
- Rapid iteration and testing

---

## Configuration

**Model:** `qwen3.5:9b`  
**Host:** `http://localhost:11434`  
**Context Window:** 32768 tokens (Ollama default for qwen3.5)

---

## Usage

### Python API

```python
import requests
import json

def ollama_generate(prompt, model="qwen3.5:9b", stream=False):
    """Generate text using local Ollama instance."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 2048
        }
    }
    
    response = requests.post(url, json=payload)
    return response.json()

def ollama_chat(messages, model="qwen3.5:9b"):
    """Chat completion using local Ollama instance."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9
        }
    }
    
    response = requests.post(url, json=payload)
    return response.json()
```

### CLI Usage

```bash
# Simple generation
ollama run qwen3.5:9b "Your prompt here"

# Interactive mode
ollama run qwen3.5:9b

# With options
ollama run qwen3.5:9b --prompt "Your prompt" --temperature 0.7
```

### OpenClaw Integration

```python
# In agent code
from skills.ollama_inference import OllamaClient

client = OllamaClient(model="qwen3.5:9b")
response = client.generate("Summarize this text...")
```

---

## Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/generate` | POST | Text generation |
| `/api/chat` | POST | Chat completion |
| `/api/embeddings` | POST | Generate embeddings |
| `/api/tags` | GET | List available models |
| `/api/show` | POST | Show model info |

---

## Performance Notes

- **Mac Mini M1/M2:** ~15-25 tokens/sec for qwen3.5:9b
- **Memory Usage:** ~6GB RAM during inference
- **Best For:** Short to medium responses, iterative development
- **Not Ideal For:** Very long context windows, batch processing

---

## Error Handling

```python
def safe_generate(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = ollama_generate(prompt)
            if "response" in response:
                return response["response"]
        except requests.exceptions.ConnectionError:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return None
```

---

## Integration Points

1. **Agent Fallback:** Use when cloud APIs fail
2. **Draft Generation:** Generate drafts for refinement by larger models
3. **Local Testing:** Test prompts before deploying to production
4. **Privacy Tasks:** Handle sensitive data locally

---

## Maintenance

- Update model: `ollama pull qwen3.5:9b`
- Check status: `ollama list`
- Remove model: `ollama rm qwen3.5:9b`
- Service status: `brew services list | grep ollama`

---

*Last updated: 2026-03-04*
