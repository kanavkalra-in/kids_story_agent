from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models import BaseChatModel
from app.config import settings
from typing import Literal, Optional
import logging

logger = logging.getLogger(__name__)

# Module-level cache for LLM clients (keyed by provider)
_llm_cache: dict[str, BaseChatModel] = {}


def _create_llm(provider: str) -> BaseChatModel:
    """Internal function to create a new LLM instance."""
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI")
        logger.debug(f"Creating ChatOpenAI instance (model: gpt-4o)")
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when using Anthropic")
        logger.debug(f"Creating ChatAnthropic instance (model: claude-3-5-sonnet-20241022)")
        return ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            api_key=settings.anthropic_api_key,
        )
    elif provider == "ollama":
        logger.debug(f"Creating ChatOllama instance (model: {settings.ollama_model}, base_url: {settings.ollama_base_url})")
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.7,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_llm(provider: Optional[Literal["openai", "anthropic", "ollama"]] = None) -> BaseChatModel:
    """
    Factory function to get the configured LLM provider.
    Caches instances by provider to avoid creating new clients on every call.
    
    Args:
        provider: Optional LLM provider to use. If None, uses the default from settings.
                  Options: "openai", "anthropic", "ollama"
    
    Returns:
        BaseChatModel instance (ChatOpenAI, ChatAnthropic, or ChatOllama)
    """
    # Use provided provider or fall back to default from settings
    key = provider or settings.llm_provider
    
    # Return cached instance if available
    if key not in _llm_cache:
        _llm_cache[key] = _create_llm(key)
    
    return _llm_cache[key]
