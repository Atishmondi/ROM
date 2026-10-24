#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"
if [ ! -x .venv/bin/python ]; then
    echo 'Run ./scripts/setup.sh once before starting the app.' >&2
    exit 1
fi
exec .venv/bin/python app.py "$@"
