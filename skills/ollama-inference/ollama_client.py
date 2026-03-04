#!/usr/bin/env python3
"""
Ollama Client for Local LLM Inference
Provides a simple interface to interact with local Ollama instances.
"""

import requests
import json
from typing import Optional, List, Dict, Any, Generator


class OllamaClient:
    """Client for interacting with local Ollama LLM server."""
    
    def __init__(
        self,
        model: str = "qwen3.5:9b",
        host: str = "http://localhost:11434",
        timeout: int = 120
    ):
        self.model = model
        self.host = host
        self.timeout = timeout
        self._session = requests.Session()
    
    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate text completion."""
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            }
        }
        
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """Chat completion with conversation history."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            }
        }
        
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def embeddings(self, text: str) -> List[float]:
        """Generate embeddings for text."""
        url = f"{self.host}/api/embeddings"
        payload = {
            "model": self.model,
            "prompt": text
        }
        
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("embedding", [])
    
    def list_models(self) -> List[Dict[str, Any]]:
        """List available models."""
        url = f"{self.host}/api/tags"
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("models", [])
    
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            self.list_models()
            return True
        except requests.exceptions.ConnectionError:
            return False
    
    def show_model_info(self) -> Dict[str, Any]:
        """Get model information."""
        url = f"{self.host}/api/show"
        payload = {"name": self.model}
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


# Convenience functions for quick usage
_default_client: Optional[OllamaClient] = None


def get_client(model: str = "qwen3.5:9b") -> OllamaClient:
    """Get or create default client."""
    global _default_client
    if _default_client is None or _default_client.model != model:
        _default_client = OllamaClient(model=model)
    return _default_client


def generate(prompt: str, **kwargs) -> str:
    """Quick text generation."""
    client = get_client()
    response = client.generate(prompt, **kwargs)
    return response.get("response", "")


def chat(messages: List[Dict[str, str]], **kwargs) -> str:
    """Quick chat completion."""
    client = get_client()
    response = client.chat(messages, **kwargs)
    return response.get("message", {}).get("content", "")


if __name__ == "__main__":
    # Test the client
    client = OllamaClient()
    
    print("Checking Ollama availability...")
    if client.is_available():
        print("✓ Ollama is running")
        
        print("\nAvailable models:")
        for model in client.list_models():
            print(f"  - {model['name']} ({model['size'] / 1e9:.1f}GB)")
        
        print("\nTest generation:")
        response = client.generate("Hello! Respond in one sentence.", max_tokens=50)
        print(f"  {response.get('response', 'No response')}")
    else:
        print("✗ Ollama is not running. Start with: brew services start ollama")
