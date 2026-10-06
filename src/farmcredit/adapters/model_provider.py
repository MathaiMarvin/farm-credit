# SPDX-License-Identifier: AGPL-3.0-only
"""Single hosted open-weights model; secrets never enter the run trace."""

import asyncio
import json
import os
from dataclasses import dataclass, field

import httpx

MODEL = "qwen/qwen3-235b-a22b-2507"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_RESPONSE_BYTES = 256 * 1024


class ProviderFailure(Exception):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


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
                    if response.status_code != 200:
                        raise ProviderFailure(
                            f"Model provider returned HTTP {response.status_code}.",
                            retryable=response.status_code == 429 or response.status_code >= 500,
                        )
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_RESPONSE_BYTES:
                            raise ProviderFailure("Model response exceeded the size limit.")
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
        except (httpx.HTTPError, asyncio.TimeoutError) as error:
            raise ProviderFailure(
                "Model request timed out or could not connect.", retryable=True
            ) from error
