#!/bin/sh
# Run from any directory. All application dependencies stay in this project.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
if ! command -v uv >/dev/null 2>&1; then
    echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -c 'from rom.yolo_pose import ensure_model; print(ensure_model(download=True))'
.venv/bin/python -m unittest discover -s tests -v
printf '\nSetup complete. Start the upload app:\n  .venv/bin/python app.py\nThen open http://127.0.0.1:8000\n'
