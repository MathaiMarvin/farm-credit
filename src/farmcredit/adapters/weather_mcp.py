# SPDX-License-Identifier: AGPL-3.0-only
"""Reuse the pinned upstream Open-Meteo MCP over stdio; no provider code is copied."""

import asyncio
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from farmcredit.application.saved_assessments import canonical_json, input_fingerprint

WEATHER_CHOICES = (
    ("Nakuru", "Nakuru city reference — seven-day forecast, not exact farm weather"),
)
SERVER_PACKAGE = "open-meteo-mcp==0.2.0"
TOOL = "get_weather_byDateTimeRange"
MAX_RESPONSE_BYTES = 256 * 1024


def parse_weather_response(result: dict) -> dict:
    if result.get("is_error") or len(result.get("content", [])) != 1:
        raise ValueError("Weather MCP did not return one successful data response.")
    text = result["content"][0].get("text", "")
    if len(text.encode()) > MAX_RESPONSE_BYTES:
        raise ValueError("Weather response exceeds the supported size.")
    # Upstream surrounds its JSON with reporting instructions. Discard all prose.
    before, marker, after = text.partition("=== WEATHER DATA ===")
    body, end, remainder = after.partition("=== ANALYSIS INSTRUCTIONS ===")
    if not marker or not end:
        raise ValueError("Weather MCP data envelope is missing.")
    value = json.loads(body)
    if not isinstance(value, dict) or "error" in value:
        raise ValueError("Weather MCP returned invalid data.")
    rows = value["weather_data"]
    if not isinstance(rows, list) or len(rows) > 168:
        raise ValueError("Weather response has unexpected coverage.")
    return {
        **{key: value[key] for key in ("city", "latitude", "longitude", "start_date", "end_date")},
        "weather_data": [
            {key: row[key] for key in ("time", "temperature_c", "precipitation_mm")} for row in rows
        ],
    }


async def fetch_weather(arguments: dict) -> dict:
    interpreter = Path(
        os.environ.get("FARMCREDIT_WEATHER_PYTHON", "tools/weather-mcp/.venv/bin/python")
    ).absolute()
    if not interpreter.is_file():
        raise ValueError("Weather MCP runtime is not installed.")
    params = StdioServerParameters(
        command=str(interpreter), args=["-m", "open_meteo_mcp", "--mode", "stdio"], env={}
    )
    async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
        listing = await client.list_tools()
        if TOOL not in {tool.name for tool in listing.tools}:
            raise ValueError("Required weather tool is unavailable.")
        result = await client.call_tool(TOOL, arguments)
        return parse_weather_response(result.model_dump(mode="json"))


def snapshot_weather(reference: str, *, as_of: date, retrieved_at: datetime) -> str:
    if reference not in dict(WEATHER_CHOICES):
        raise ValueError("Unsupported weather reference.")
    arguments = {
        "city": reference,
        "start_date": as_of.isoformat(),
        "end_date": (as_of + timedelta(days=6)).isoformat(),
    }
    raw, error = None, None
    if as_of != datetime.now(ZoneInfo("Africa/Nairobi")).date():
        error = "Live weather cannot be retrieved for a historical or future review date. Use an appropriately archived forecast."
    else:
        try:
            raw = asyncio.run(asyncio.wait_for(fetch_weather(arguments), timeout=30))
        except Exception:
            # MCP task-group, process, provider and malformed-response failures are all evidence gaps.
            error = "Weather evidence unavailable: the MCP server or provider did not return usable data."
    payload = {
        "schema_version": 1,
        "reference": reference,
        "as_of": as_of,
        "retrieved_at": retrieved_at.isoformat(),
        "completed_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "server_package": SERVER_PACKAGE,
        "tool": TOOL,
        "arguments": arguments,
        "source": "Open-Meteo via the external open-meteo-mcp server",
        "source_url": "https://open-meteo.com/en/docs",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "raw": raw,
        "error": error,
    }
    return canonical_json({**payload, "fingerprint": input_fingerprint(payload)})
