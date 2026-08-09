from src.providers.base import ProviderRegistry

# Register all STT providers
try:
    from src.providers.stt.local import LocalWhisperProvider
    ProviderRegistry.register_stt("local", LocalWhisperProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register local STT: {e}")

try:
    from src.providers.stt.deepgram import DeepgramProvider
    ProviderRegistry.register_stt("deepgram", DeepgramProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register deepgram STT: {e}")

try:
    from src.providers.stt.assemblyai import AssemblyAIProvider
    ProviderRegistry.register_stt("assemblyai", AssemblyAIProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register assemblyai STT: {e}")

try:
    from src.providers.stt.speechmatics import SpeechmaticsProvider
    ProviderRegistry.register_stt("speechmatics", SpeechmaticsProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register speechmatics STT: {e}")

try:
    from src.providers.stt.revai import RevAIProvider
    ProviderRegistry.register_stt("revai", RevAIProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register revai STT: {e}")

try:
    from src.providers.stt.aws import AWSProvider
    ProviderRegistry.register_stt("aws", AWSProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register aws STT: {e}")

# Register all LLM providers
try:
    from src.providers.llm.ollama import OllamaProvider
    ProviderRegistry.register_llm("ollama", OllamaProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register ollama LLM: {e}")

try:
    from src.providers.llm.ollama import GroqProvider
    ProviderRegistry.register_llm("groq", GroqProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register groq LLM: {e}")

try:
    from src.providers.llm.ollama import AnthropicProvider
    ProviderRegistry.register_llm("anthropic", AnthropicProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register anthropic LLM: {e}")

try:
    from src.providers.llm.ollama import OpenAIProvider
    ProviderRegistry.register_llm("openai", OpenAIProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register openai LLM: {e}")

try:
    from src.providers.llm.ollama import OpenRouterProvider
    ProviderRegistry.register_llm("openrouter", OpenRouterProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register openrouter LLM: {e}")

try:
    from src.providers.llm.ollama import MistralProvider
    ProviderRegistry.register_llm("mistral", MistralProvider)
except ImportError as e:
    print(f"[ProviderRegistry] Failed to register mistral LLM: {e}")

print(f"[ProviderRegistry] Registered STT: {ProviderRegistry.list_stt()}")
print(f"[ProviderRegistry] Registered LLM: {ProviderRegistry.list_llm()}")
