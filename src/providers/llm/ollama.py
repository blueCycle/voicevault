import time
from typing import Optional
import httpx

from src.providers.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """Local LLM via Ollama. Zero cost, zero cloud, runs on your hardware."""
    
    name = "ollama"
    requires_api_key = False
    
    def __init__(self, api_key: str = None, model: str = None, base_url: str = None, **kwargs):
        super().__init__(api_key=None, model=model or "llama3.1:8b", **kwargs)
        self.base_url = base_url or "http://localhost:11434"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        start = time.time()
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_ctx": kwargs.get("num_ctx", 4096),
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=300.0,
            )
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        return LLMResponse(
            provider=self.name,
            text=data.get("response", ""),
            model=self.model,
            tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            cost_usd=0.0,
            processing_time_seconds=elapsed,
            metadata={"eval_duration": data.get("eval_duration")},
        )
    
    def health_check(self) -> bool:
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


class GroqProvider(LLMProvider):
    """Groq cloud LLM - fastest inference, SOC 2, zero retention."""
    
    name = "groq"
    requires_api_key = True
    
    COST_INPUT_PER_1K = 0.0001
    COST_OUTPUT_PER_1K = 0.0001
    
    def __init__(self, api_key: str = None, model: str = None, **kwargs):
        super().__init__(api_key=api_key, model=model or "llama-3.1-8b-instant", **kwargs)
        self.base_url = "https://api.groq.com/openai/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        start = time.time()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_tokens": kwargs.get("max_tokens", 4096),
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = (input_tokens / 1000 * self.COST_INPUT_PER_1K) + (output_tokens / 1000 * self.COST_OUTPUT_PER_1K)
        
        return LLMResponse(
            provider=self.name,
            text=text,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            processing_time_seconds=elapsed,
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )
    
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False


class AnthropicProvider(LLMProvider):
    """Anthropic Claude - best quality for nuanced summaries, SOC 2, no training."""
    
    name = "anthropic"
    requires_api_key = True
    
    COST_INPUT_PER_1M = 3.0   # Claude 3.5 Sonnet
    COST_OUTPUT_PER_1M = 15.0
    
    def __init__(self, api_key: str = None, model: str = None, **kwargs):
        super().__init__(api_key=api_key, model=model or "claude-3-5-sonnet-20241022", **kwargs)
        self.base_url = "https://api.anthropic.com/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        start = time.time()
        
        payload = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        text = "\n".join([c.get("text", "") for c in data.get("content", []) if c.get("type") == "text"])
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = (input_tokens / 1_000_000 * self.COST_INPUT_PER_1M) + (output_tokens / 1_000_000 * self.COST_OUTPUT_PER_1M)
        
        return LLMResponse(
            provider=self.name,
            text=text,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            processing_time_seconds=elapsed,
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )
    
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/models", headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False


class OpenRouterProvider(LLMProvider):
    """OpenRouter - aggregates multiple providers, routes to cheapest/fastest model."""
    
    name = "openrouter"
    requires_api_key = True
    
    def __init__(self, api_key: str = None, model: str = None, **kwargs):
        super().__init__(api_key=api_key, model=model or "anthropic/claude-3.5-sonnet", **kwargs)
        self.base_url = "https://openrouter.ai/api/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        start = time.time()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_tokens": kwargs.get("max_tokens", 4096),
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        # Cost is provider-dependent; OpenRouter includes it sometimes
        cost = usage.get("total_cost", None)
        
        return LLMResponse(
            provider=self.name,
            text=text,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            processing_time_seconds=elapsed,
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens, "provider": data.get("provider")},
        )
    
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False


class MistralProvider(LLMProvider):
    """Mistral AI (La Plateforme) - EU-native, GDPR-first, no training on API data."""
    
    name = "mistral"
    requires_api_key = True
    
    # Mistral Large 2 pricing (approximate, competitive)
    COST_INPUT_PER_1M = 2.0
    COST_OUTPUT_PER_1M = 6.0
    
    def __init__(self, api_key: str = None, model: str = None, **kwargs):
        super().__init__(api_key=api_key, model=model or "mistral-large-latest", **kwargs)
        self.base_url = "https://api.mistral.ai/v1"
    
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> LLMResponse:
        start = time.time()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                    "max_tokens": kwargs.get("max_tokens", 4096),
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        
        elapsed = time.time() - start
        
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost = (input_tokens / 1_000_000 * self.COST_INPUT_PER_1M) + (output_tokens / 1_000_000 * self.COST_OUTPUT_PER_1M)
        
        return LLMResponse(
            provider=self.name,
            text=text,
            model=self.model,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost,
            processing_time_seconds=elapsed,
            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )
    
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False
