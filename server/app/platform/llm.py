"""ChatOllama factory.

Centralised so the model name + temperature are configured in one place. The
agents always go through `get_llm()` rather than instantiating ChatOllama
directly — this lets the smoke test swap in a fake without touching agent code.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.platform.config import get_settings


@lru_cache
def get_llm(temperature: float = 0.1) -> ChatOllama:
    settings = get_settings()
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_host,
        temperature=temperature,
    )
