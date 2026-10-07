# SPDX-License-Identifier: AGPL-3.0-only
"""Single hosted open-weights model; secrets never enter the run trace."""

import asyncio
import json
import math
import os
from dataclasses import dataclass, field

import httpx

MODEL = "qwen/qwen3-235b-a22b-2507"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_RESPONSE_BYTES = 256 * 1024


class ProviderFailure(Exception):
    def __init__(self, message, *, retryable=False, retry_after=0.5):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def provider_error(status, payload, retry_after=None):
    explanation = {
        401: "The provider rejected the configured credentials. Check the server API key.",
        402: "The provider refused this request under its credit or spending limits. Check provider credits and request limits before retrying.",
        403: "The provider denied access to this request. Check model access and provider restrictions.",
        429: "The provider rate limit was reached.",
        503: "The model service is temporarily unavailable.",
    }.get(status, "The model request was unsuccessful.")
    # Interpret documented categories only; never expose raw provider text or metadata.
    try:
        metadata = json.loads(payload)["error"].get("metadata", {})
        source, reason = metadata.get("limit_source"), metadata.get("reason")
    except (ValueError, KeyError, TypeError, AttributeError):
        source, reason = None, None
    transient_budget = False
    if status == 402:
        if source == "openrouter_in_flight_budget" and reason == "in_flight_budget_exhausted":
            transient_budget = True
            explanation = "The provider's temporary in-flight request budget is exhausted. Wait for outstanding requests to settle before retrying."
        elif source == "openrouter_key_limit":
            explanation = "The configured API key's spending limit was reached. The server operator must check that key's limit."
        elif source == "openrouter_credits" and reason == "weight_exceeds_budget":
            explanation = "This model request exceeds the provider's available request budget. Waiting alone will not resolve it; the server operator must review the request size or provider credits."
        elif source == "openrouter_credits":
            explanation = "The provider's available credits cannot cover this request. The server operator must check account credits."
    try:
        delay = float(retry_after)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError
    except (ValueError, TypeError):
        transient_budget = False
        delay = 0.5
    return ProviderFailure(
        f"Model provider returned HTTP {status}. {explanation}",
        retryable=transient_budget or status == 429 or status >= 500,
        retry_after=delay,
    )


@dataclass(frozen=True)
class OpenRouter:
    api_key: str = field(repr=False)
    model: str = MODEL

    @classmethod
    def configured(cls):
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise ValueError(
                "Set OPENROUTER_API_KEY locally before starting a model investigation."
            )
        return cls(key)

    async def complete(self, messages, tools, *, timeout):
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": 3000,
            "temperature": 0,
            "provider": {"require_parameters": True},
        }

        async def request():
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                async with client.stream(
                    "POST",
                    ENDPOINT,
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                ) as response:
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_RESPONSE_BYTES:
                            raise ProviderFailure("Model response exceeded the size limit.")
            if response.status_code != 200:
                raise provider_error(
                    response.status_code, chunks, response.headers.get("Retry-After")
                )
            try:
                result = json.loads(chunks)
                message = result["choices"][0]["message"]
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    raise ValueError
                # Persist public assistant output and tool selections, never reasoning traces.
                return {
                    "id": result.get("id"),
                    "model": result.get("model"),
                    "message": {
                        k: v for k, v in message.items() if k in {"role", "content", "tool_calls"}
                    },
                    "usage": result.get("usage"),
                    "finish_reason": result["choices"][0].get("finish_reason"),
                }
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise ProviderFailure("Model provider returned an invalid response.") from error

        try:
            return await asyncio.wait_for(request(), timeout=timeout)
        except (httpx.TimeoutException, asyncio.TimeoutError) as error:
            raise ProviderFailure(
                f"The model provider did not respond within {timeout:g} seconds.", retryable=True
            ) from error
        except httpx.HTTPError as error:
            raise ProviderFailure(
                "Could not connect to the model provider. Check the server network connection.",
                retryable=True,
            ) from error
