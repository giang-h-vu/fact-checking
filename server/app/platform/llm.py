"""Chat-model factory.

Centralised so provider + model + temperature are configured in one place. The
agents always go through `get_llm()` rather than instantiating a model
directly — this lets the smoke test swap in a fake without touching agent code.

`LLM_PROVIDER` picks the backend: `ollama` (local) or `openrouter` (hosted,
OpenAI-compatible API).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from openai import ContentFilterFinishReasonError, LengthFinishReasonError

from app.platform.config import get_settings

# The model answered, but not with usable structured output: unparseable or off-schema
# (ValueError covers OutputParserException and pydantic's ValidationError), no parsed
# result (TypeError), truncated, or filtered. Callers turn these into "no passage" /
# NOT_ENOUGH_INFO. Anything else a model call raises (quota, outage, auth) is a provider
# failure and must propagate: reported as weak evidence, it would end as a saved verdict.
UNUSABLE_ANSWER = (ValueError, TypeError, LengthFinishReasonError, ContentFilterFinishReasonError)


@lru_cache
def get_llm(temperature: float = 0.1) -> BaseChatModel:
    settings = get_settings()
    if settings.llm_provider == "openrouter":
        from langchain_openai import ChatOpenAI

        extra_body: dict[str, Any] = {"provider": {"require_parameters": True}}
        if settings.openrouter_fallback_list:
            # OpenRouter tries these in order if the primary errors (rate limit, downtime…).
            extra_body["models"] = [settings.openrouter_model, *settings.openrouter_fallback_list]

        rpm = settings.openrouter_requests_per_minute
        # per process; several replicas sharing one key need a shared limiter.
        limiter = (
            InMemoryRateLimiter(requests_per_second=rpm / 60, max_bucket_size=1) if rpm else None
        )

        return ChatOpenAI(
            model=settings.openrouter_model,
            rate_limiter=limiter,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=temperature,
            # require_parameters: without it OpenRouter may route to a provider that
            # silently drops response_format=json_schema, which the agents need.
            extra_body=extra_body,
        )
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_host,
            temperature=temperature,
            num_ctx=settings.ollama_num_ctx,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
