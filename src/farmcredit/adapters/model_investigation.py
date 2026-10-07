# SPDX-License-Identifier: AGPL-3.0-only
"""LangGraph loop over an authorised MCP session; PostgreSQL owns the audit trail."""

import asyncio
import json
from typing import TypedDict
from uuid import uuid4

from asgiref.sync import sync_to_async
from django.utils import timezone
from langgraph.graph import END, START, StateGraph

from farmcredit.adapters.agent_runs import record_event, run_details, stop_run
from farmcredit.adapters.model_provider import ProviderFailure
from farmcredit.adapters.persistence.models import AgentRun
from farmcredit.application.investigation import (
    DEFAULT_TASK,
    MAX_CONTEXT_BYTES,
    MAX_MODEL_CALLS,
    MAX_MODEL_RETRIES,
    MAX_REPORTED_TOKENS,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    validate_task,
)
from farmcredit.application.run_tools import MAX_RUN_SECONDS, ToolName, validate_arguments
from farmcredit.application.saved_assessments import canonical_json


class InvestigationState(TypedDict):
    messages: list[dict]
    turns: int
    retries: int
    tokens: int
    pending: list[dict]
    next: str


async def investigate_model(
    *, run_id, officer_id, provider, client, tools, task=DEFAULT_TASK, previous=None
):
    """The caller binds the MCP session. Model arguments cannot choose its scope."""
    task = validate_task(task)
    event = sync_to_async(record_event, thread_sensitive=True)
    details = sync_to_async(run_details, thread_sensitive=True)
    stop = sync_to_async(stop_run, thread_sensitive=True)
    started = await sync_to_async(
        lambda: AgentRun.objects.get(pk=run_id, officer_id=officer_id).started_at,
        thread_sensitive=True,
    )()

    def remaining():
        return MAX_RUN_SECONDS - (timezone.now() - started).total_seconds()

    async def finish(reason):
        await stop(run_id, officer_id, reason)
        return {"next": END, "pending": []}

    async def model_node(state):
        current = await details(run_id=run_id, officer_id=officer_id)
        if current["status"] != "active":
            return {"next": END}
        if state["turns"] >= MAX_MODEL_CALLS or state["tokens"] >= MAX_REPORTED_TOKENS:
            return await finish("Model call or reported-token budget reached.")
        if remaining() <= 0:
            return await finish("Run deadline exceeded.")
        if len(canonical_json(state["messages"]).encode()) > MAX_CONTEXT_BYTES:
            return await finish("Model context size limit reached.")
        attempt = state["turns"] + 1
        timeout = min(35, remaining())
        await event(
            run_id,
            "model_request",
            {
                "attempt": attempt,
                "provider": "openrouter",
                "model": provider.model,
                "prompt_version": PROMPT_VERSION,
                "messages": state["messages"],
                "tools": tools,
                "timeout_seconds": timeout,
                "max_output_tokens": 3000,
            },
        )
        try:
            result = await provider.complete(state["messages"], tools, timeout=timeout)
        except ProviderFailure as error:
            retry = (
                error.retryable
                and state["retries"] < MAX_MODEL_RETRIES
                and remaining() > error.retry_after + 1
            )
            await event(
                run_id,
                "model_failure",
                {
                    "attempt": attempt,
                    "error": str(error),
                    "usage": None,
                    "cost": None,
                    "retryable": error.retryable,
                    "retry_scheduled": retry,
                    "retry_after": error.retry_after,
                },
            )
            if retry:
                await asyncio.sleep(error.retry_after)
                return {"turns": attempt, "retries": state["retries"] + 1, "next": "model"}
            retry_limit = ""
            if error.retryable:
                retry_limit = (
                    " The single automatic retry has already been used."
                    if state["retries"] >= MAX_MODEL_RETRIES
                    else f" The provider retry delay ({error.retry_after:g}s) exceeds this run's remaining time; no automatic retry was sent."
                )
            return {
                "turns": attempt,
                **await finish(f"{error}{retry_limit} No draft was confirmed."),
            }
        await event(run_id, "model_response", {"attempt": attempt, **result})
        if remaining() <= 0:
            return await finish("Run deadline exceeded after model response.")
        usage = result.get("usage") or {}
        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        tokens = tokens if type(tokens) is int and tokens >= 0 else 0
        message = result["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            return {"turns": attempt, **await finish("Model stopped without saving a draft.")}
        if not isinstance(calls, list) or len(calls) != 1:
            return {"turns": attempt, **await finish("Model must request one tool at a time.")}
        return {
            "turns": attempt,
            "tokens": state["tokens"] + tokens,
            "messages": [*state["messages"], message],
            "pending": calls,
            "next": "tools",
        }

    async def tool_node(state):
        selected = state["pending"][0]
        operation_id = str(uuid4())
        try:
            if not isinstance(selected, dict):
                raise ValueError
            if selected.get("type") != "function" or not isinstance(selected.get("id"), str):
                raise ValueError
            name = ToolName(selected["function"]["name"])
            arguments = json.loads(selected["function"]["arguments"])
            validate_arguments(name, arguments)
        except (ValueError, KeyError, TypeError):
            await event(run_id, "tool_rejected", {"selection": selected})
            return await finish("Model requested an unsupported tool or invalid arguments.")
        await event(
            run_id,
            "mcp_request",
            {
                "operation_id": operation_id,
                "tool": name.value,
                "arguments": arguments,
            },
        )
        try:
            if remaining() <= 0:
                return await finish("Run deadline exceeded before tool execution.")
            result = await asyncio.wait_for(
                client.call_tool(name.value, {**arguments, "operation_id": operation_id}),
                timeout=remaining(),
            )
            outcome = result.structured_content
            await event(
                run_id,
                "mcp_response",
                {
                    "operation_id": operation_id,
                    "is_error": result.is_error,
                    "outcome": outcome,
                },
            )
        except Exception:
            await event(
                run_id,
                "mcp_failure",
                {
                    "operation_id": operation_id,
                    "error": "MCP outcome unconfirmed; inspect tool history.",
                },
            )
            return await finish("MCP connection failed or timed out; outcome may be unconfirmed.")
        current = await details(run_id=run_id, officer_id=officer_id)
        if current["status"] != "active":
            return {"next": END}
        if result.is_error or not isinstance(outcome, dict) or outcome.get("status") != "succeeded":
            return await finish("MCP tool rejected the request; no draft confirmed.")
        return {
            "messages": [
                *state["messages"],
                {
                    "role": "tool",
                    "tool_call_id": selected["id"],
                    "content": canonical_json(outcome),
                },
            ],
            "pending": [],
            "next": "model",
        }

    graph = StateGraph(InvestigationState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "model")
    for node in ("model", "tools"):
        graph.add_conditional_edges(node, lambda state: state["next"], ["model", "tools", END])
    await graph.compile().ainvoke(
        {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": canonical_json(
                        {
                            "officer_request": task,
                            "previous_saved_response": previous,
                            "deliverable": "Investigate the bound application and save a draft for human review.",
                        }
                    ),
                },
            ],
            "turns": 0,
            "retries": 0,
            "tokens": 0,
            "pending": [],
            "next": "model",
        },
        {"recursion_limit": 2 * MAX_MODEL_CALLS + 4},
    )
