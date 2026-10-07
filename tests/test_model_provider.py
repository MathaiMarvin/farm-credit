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
        for status, retryable in (
            (429, True),
            (503, True),
            (401, False),
            (402, False),
            (400, False),
        ):
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
        self.assertIn("did not respond within 0.01 seconds", str(caught.exception))
        for payload in (b"not json", b"{}", b"x" * (256 * 1024 + 1)):
            with self.assertRaises(ProviderFailure):
                self.call(lambda request: httpx.Response(200, content=payload))

    def test_connection_failure_is_distinct_from_timeout_and_hides_raw_details(self):
        def disconnected(request):
            raise httpx.ConnectError("secret connection detail", request=request)

        with self.assertRaises(ProviderFailure) as caught:
            self.call(disconnected)
        self.assertIn("Could not connect", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertTrue(caught.exception.retryable)

    def test_payment_failure_uses_only_documented_metadata(self):
        cases = (
            ("openrouter_in_flight_budget", "in_flight_budget_exhausted", "temporary in-flight"),
            ("openrouter_key_limit", "", "key's spending limit"),
            ("openrouter_credits", "weight_exceeds_budget", "Waiting alone will not resolve"),
        )
        for source, reason, expected in cases:
            with self.subTest(source=source), self.assertRaises(ProviderFailure) as caught:
                self.call(
                    lambda request: httpx.Response(
                        402,
                        json={
                            "error": {
                                "message": "secret provider detail",
                                "metadata": {"limit_source": source, "reason": reason},
                            }
                        },
                    )
                )
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))

    def test_temporary_budget_failure_honours_retry_after(self):
        from farmcredit.adapters.model_provider import provider_error

        error = provider_error(
            402,
            json.dumps(
                {
                    "error": {
                        "metadata": {
                            "limit_source": "openrouter_in_flight_budget",
                            "reason": "in_flight_budget_exhausted",
                        }
                    }
                }
            ),
            "12",
        )
        self.assertTrue(error.retryable)
        self.assertEqual(error.retry_after, 12)
        self.assertFalse(provider_error(402, b"{}", "12").retryable)
        transient = json.dumps(
            {
                "error": {
                    "metadata": {
                        "limit_source": "openrouter_in_flight_budget",
                        "reason": "in_flight_budget_exhausted",
                    }
                }
            }
        )
        for invalid_delay in (None, "NaN", "-1", "unknown"):
            self.assertFalse(provider_error(402, transient, invalid_delay).retryable)
