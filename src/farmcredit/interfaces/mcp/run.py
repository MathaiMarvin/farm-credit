# SPDX-License-Identifier: AGPL-3.0-only
"""Stdio entry point. Credentials belong to the launcher, never model arguments."""

import asyncio
import os


def main():
    if not os.environ.get("FARMCREDIT_SECRET_KEY") or not os.environ.get("FARMCREDIT_MCP_TOKEN"):
        raise SystemExit("FARMCREDIT_SECRET_KEY and FARMCREDIT_MCP_TOKEN are required.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farmcredit.interfaces.web.settings")
    import django

    django.setup()
    from mcp.server.stdio import stdio_server

    from farmcredit.interfaces.mcp.server import create_server

    try:
        server = create_server(os.environ.pop("FARMCREDIT_MCP_TOKEN"))
    except PermissionError:
        raise SystemExit("Run credential is invalid or expired.") from None

    async def serve():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(serve())


if __name__ == "__main__":
    main()
