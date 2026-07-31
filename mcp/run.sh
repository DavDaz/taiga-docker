#!/bin/sh
set -e

case $0 in
    /*/*) SCRIPT_DIR=${0%/*} ;;
    /*) SCRIPT_DIR=/ ;;
    */*) SCRIPT_DIR=./${0%/*} ;;
    *) SCRIPT_DIR=. ;;
esac
SCRIPT_DIR=$(CDPATH= cd -P "$SCRIPT_DIR" && pwd)
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Taiga MCP virtual environment is missing at $SCRIPT_DIR/.venv; create it and install $SCRIPT_DIR/requirements.txt" >&2
    exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON" -m taiga_mcp.launcher "$@"
