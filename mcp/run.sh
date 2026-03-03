#!/bin/sh
cd "$(dirname "$0")" && exec python -m taiga_mcp.server "$@"
