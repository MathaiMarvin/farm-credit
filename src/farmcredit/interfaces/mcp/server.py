# SPDX-License-Identifier: AGPL-3.0-only
"""Local MCP boundary, bound by a trusted launcher to one officer's run."""

import json
from uuid import UUID

from asgiref.sync import sync_to_async
from django.core import signing
from django.db import close_old_connections
from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from farmcredit.adapters.agent_runs import invoke_tool, run_details
from farmcredit.application.run_tools import MAX_RUN_SECONDS, ToolName
from farmcredit.application.tool_schema import DESCRIPTIONS, FIELDS, _object

SALT = "farmcredit.mcp.run.v1"


def issue_run_token(*, run_id: str, officer_id: str) -> str:
    """Trusted launcher only: identity must come from the authenticated session."""
    details = run_details(run_id=run_id, officer_id=officer_id)
    if details["status"] != "active":
        raise ValueError("Start a new run before connecting MCP.")
    return signing.dumps({"run_id": run_id, "officer_id": officer_id}, salt=SALT)


def _binding(token: str) -> dict:
    try:
        binding = signing.loads(token, salt=SALT, max_age=MAX_RUN_SECONDS)
        UUID(binding["run_id"])
        if set(binding) != {"run_id", "officer_id"} or not binding["officer_id"]:
            raise ValueError
        return binding
    except (signing.BadSignature, ValueError, KeyError, TypeError) as error:
        raise PermissionError("Run credential is invalid or expired.") from error


def create_server(token: str) -> Server:
    _binding(token)
    tools = [
        Tool(
            name=name,
            description=DESCRIPTIONS[name]
            + " Supply a UUID operation_id; reuse it only for an identical retry.",
            input_schema=_object({"operation_id": {"type": "string", "format": "uuid"}, **fields}),
        )
        for name, fields in FIELDS.items()
    ]

    def dispatch(name: str, arguments: dict) -> dict:
        close_old_connections()
        try:
            binding = _binding(token)
            ToolName(name)
            arguments = dict(arguments)
            operation_id = arguments.pop("operation_id")
            return invoke_tool(**binding, operation_id=operation_id, tool=name, arguments=arguments)
        finally:
            close_old_connections()

    async def list_tools(ctx, params):
        return ListToolsResult(tools=tools)

    async def call_tool(ctx, params):
        try:
            result = await sync_to_async(dispatch, thread_sensitive=True)(
                params.name, params.arguments or {}
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result))],
                structured_content=result,
                is_error=result["status"] != "succeeded",
            )
        except (ValueError, PermissionError, LookupError):
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text="Tool request rejected. Check the run credential, permission and arguments.",
                    )
                ],
                is_error=True,
            )
        except Exception:
            return CallToolResult(
                content=[
                    TextContent(type="text", text="Tool unavailable; no result was confirmed.")
                ],
                is_error=True,
            )

    return Server(
        "farmcredit",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        get_tool_input_schema=lambda name: next(
            (tool.input_schema for tool in tools if tool.name == name), None
        ),
    )
