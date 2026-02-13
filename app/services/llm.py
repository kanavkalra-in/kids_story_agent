from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models import BaseChatModel
from app.config import settings
from typing import Optional, Literal
import logging

logger = logging.getLogger(__name__)


def get_llm(provider: Optional[Literal["openai", "anthropic", "ollama"]] = None) -> BaseChatModel:
    """
    Factory function to get the configured LLM provider.
    
    Args:
        provider: Optional LLM provider to use. If None, uses the default from settings.
                  Options: "openai", "anthropic", "ollama"
    
    Returns:
        BaseChatModel instance (ChatOpenAI, ChatAnthropic, or ChatOllama)
    """
    # Use provided provider or fall back to default from settings
    llm_provider = provider or settings.llm_provider
    
    if llm_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI")
        logger.debug(f"Creating ChatOpenAI instance (model: gpt-4o)")
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
    elif llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when using Anthropic")
        logger.debug(f"Creating ChatAnthropic instance (model: claude-3-5-sonnet-20241022)")
        return ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            api_key=settings.anthropic_api_key,
        )
    elif llm_provider == "ollama":
        logger.debug(f"Creating ChatOllama instance (model: {settings.ollama_model}, base_url: {settings.ollama_base_url})")
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.7,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}")
