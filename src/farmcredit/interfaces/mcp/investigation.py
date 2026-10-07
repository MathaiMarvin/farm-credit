# SPDX-License-Identifier: AGPL-3.0-only
"""Trusted launcher: the web officer supplies identity, never the model."""

import asyncio
import os
import sys

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connection, connections
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from farmcredit.adapters.agent_conversation import previous_response
from farmcredit.adapters.agent_runs import record_event, start_run, stop_run
from farmcredit.adapters.application_store import get_application
from farmcredit.adapters.model_investigation import investigate_model
from farmcredit.adapters.model_provider import OpenRouter
from farmcredit.application.investigation import DEFAULT_TASK, validate_task
from farmcredit.application.run_tools import MAX_RUN_SECONDS
from farmcredit.application.tool_schema import DESCRIPTIONS, FIELDS, _object
from farmcredit.interfaces.mcp.server import issue_run_token


def investigate_application_with_model(
    *, application_id, officer_id, run_id=None, task=DEFAULT_TASK
):
    get_application(application_id, officer_id)
    task = validate_task(task)
    previous = previous_response(application_id, officer_id)
    provider = OpenRouter.configured()
    run_id = start_run(
        application_id=application_id,
        officer_id=officer_id,
        model=provider.model,
        run_id=run_id,
        request_context={"task": task, "previous_response": previous},
    )
    env = {
        "FARMCREDIT_SECRET_KEY": settings.SECRET_KEY,
        "FARMCREDIT_MCP_TOKEN": issue_run_token(run_id=run_id, officer_id=officer_id),
    }
    for variable, key in (
        ("PGDATABASE", "NAME"),
        ("PGUSER", "USER"),
        ("PGPASSWORD", "PASSWORD"),
        ("PGHOST", "HOST"),
        ("PGPORT", "PORT"),
    ):
        env[variable] = str(connection.settings_dict[key])
    if os.environ.get("FARMCREDIT_WEATHER_PYTHON"):
        env["FARMCREDIT_WEATHER_PYTHON"] = os.environ["FARMCREDIT_WEATHER_PYTHON"]
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": _object(fields),
            },
        }
        for name, fields in FIELDS.items()
    ]

    async def run():
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "farmcredit.interfaces.mcp.run"],
                env=env,
            ),
            read_timeout_seconds=MAX_RUN_SECONDS,
        ) as client:
            listing = await client.list_tools()
            if {tool.name for tool in listing.tools} != set(FIELDS):
                raise ValueError("Unexpected MCP tool listing.")
            await sync_to_async(record_event, thread_sensitive=True)(
                run_id, "mcp_discovery", {"tools": [tool.name for tool in listing.tools]}
            )
            await investigate_model(
                run_id=run_id,
                officer_id=officer_id,
                provider=provider,
                client=client,
                tools=tools,
                task=task,
                previous=previous,
            )

    async def connected_run():
        try:
            await run()
        finally:
            await sync_to_async(connections.close_all, thread_sensitive=True)()

    try:
        asyncio.run(asyncio.wait_for(connected_run(), timeout=MAX_RUN_SECONDS + 5))
    except Exception:
        record_event(
            run_id,
            "launcher_failure",
            {"error": "Investigation interrupted; inspect recorded outcomes."},
        )
        stop_run(run_id, officer_id, "Investigation interrupted; no further actions will run.")
    return run_id
