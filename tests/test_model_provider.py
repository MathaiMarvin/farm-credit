# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import json
from unittest import TestCase
from unittest.mock import patch

import httpx

from farmcredit.adapters.model_provider import MODEL, OpenRouter, ProviderFailure


class ModelProviderTests(TestCase):
    def call(self, handler, timeout=1):
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        with patch("farmcredit.adapters.model_provider.httpx.AsyncClient", return_value=client):
            return asyncio.run(OpenRouter("test-only-secret").complete([], [], timeout=timeout))

    def test_request_uses_pinned_model_and_does_not_save_reasoning_or_key(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["model"], MODEL)
            self.assertNotIn("parallel_tool_calls", body)
            return httpx.Response(
                200,
                json={
                    "model": MODEL,
                    "id": "provider-id",
                    "usage": {"total_tokens": 10, "cost": 0},
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Question",
                                "reasoning": "private",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        result = self.call(handler)
        self.assertNotIn("reasoning", result["message"])
        self.assertEqual(result["usage"]["cost"], 0)
        self.assertNotIn("test-only-secret", repr(OpenRouter("test-only-secret")))

    def test_retryable_and_permanent_statuses_are_sanitized(self):
        for status, retryable in ((429, True), (503, True), (401, False), (400, False)):
            with self.assertRaises(ProviderFailure) as caught:
                self.call(lambda request: httpx.Response(status, text="secret provider detail"))
            self.assertEqual(caught.exception.retryable, retryable)
            self.assertNotIn("secret", str(caught.exception))

    def test_timeout_malformed_and_oversized_responses(self):
        async def slow(request):
            await asyncio.sleep(1)
            return httpx.Response(200)

        with self.assertRaises(ProviderFailure) as caught:
            self.call(slow, timeout=0.01)
        self.assertTrue(caught.exception.retryable)
        for payload in (b"not json", b"{}", b"x" * (256 * 1024 + 1)):
            with self.assertRaises(ProviderFailure):
                self.call(lambda request: httpx.Response(200, content=payload))
