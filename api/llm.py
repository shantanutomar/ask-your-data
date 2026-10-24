"""Thin OpenAI wrapper. All LLM calls in the app go through this interface.

Swap providers by implementing the same three methods (`structured`, `stream`, `validate_key`).
Never logs prompts, headers or API keys - only step name, model, token counts and latency.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger("llm")

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base class; `code` maps onto the SSE `error.code`."""

    code = "internal"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class QuotaExhausted(LLMError):
    code = "quota_exhausted"


class InvalidApiKey(LLMError):
    code = "invalid_key"


class LLMUnavailable(LLMError):
    code = "llm_error"


class LLMProtocol(Protocol):
    async def structured(
        self, *, step: str, model: str, system: str, user: str, schema: type[T]
    ) -> T: ...

    def stream(self, *, step: str, model: str, system: str, user: str) -> AsyncIterator[str]: ...

    async def validate_key(self) -> bool: ...

    async def aclose(self) -> None: ...


def _translate(exc: Exception) -> LLMError:
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return InvalidApiKey("The OpenAI API key was rejected.")
    if isinstance(exc, openai.RateLimitError):
        code = getattr(exc, "code", None) or ""
        if code == "insufficient_quota":
            return QuotaExhausted("The OpenAI account has no quota left.")
        return LLMUnavailable("The model is rate limited right now. Please retry in a moment.")
    if isinstance(exc, openai.APIConnectionError | openai.APITimeoutError):
        return LLMUnavailable("Could not reach the model provider.")
    return LLMUnavailable("The model provider returned an error.")


class OpenAILLM:
    def __init__(self, api_key: str, *, owns_client: bool = True) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=60, max_retries=1)
        self._owns_client = owns_client

    def _log(self, step: str, model: str, usage: object, started: float) -> None:
        logger.info(
            "llm step=%s model=%s prompt_tokens=%s completion_tokens=%s ms=%d",
            step,
            model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            (time.perf_counter() - started) * 1000,
        )

    async def structured(
        self, *, step: str, model: str, system: str, user: str, schema: type[T]
    ) -> T:
        started = time.perf_counter()
        try:
            completion = await self._client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=schema,
                temperature=0,
            )
        except openai.OpenAIError as exc:
            logger.warning("llm step=%s failed: %s", step, type(exc).__name__)
            raise _translate(exc) from None
        self._log(step, model, completion.usage, started)
        message = completion.choices[0].message
        if message.parsed is None:
            raise LLMUnavailable("The model returned an unreadable response.")
        return message.parsed

    async def stream(self, *, step: str, model: str, system: str, user: str) -> AsyncIterator[str]:
        started = time.perf_counter()
        usage = None
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
                stream_options={"include_usage": True},
                temperature=0.2,
            )
            async for chunk in response:
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.OpenAIError as exc:
            logger.warning("llm step=%s failed: %s", step, type(exc).__name__)
            raise _translate(exc) from None
        self._log(step, model, usage, started)

    async def validate_key(self) -> bool:
        try:
            await self._client.models.list()
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            return False
        except openai.OpenAIError as exc:
            raise _translate(exc) from None
        return True

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()
