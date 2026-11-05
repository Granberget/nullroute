#!/usr/bin/env sh
# Starts NULLROUTE on Linux and macOS.
# The first run creates a Python virtual environment in .venv and installs
# Textual into it; later runs start straight away.
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -x ".venv/bin/python" ]; then
    if ! command -v "$PY" >/dev/null 2>&1; then
        echo "Python 3.10+ is required, but '$PY' was not found."
        echo "  Debian/Ubuntu: sudo apt install python3 python3-venv"
        echo "  Fedora:        sudo dnf install python3"
        echo "  macOS:         brew install python   (or get it from python.org)"
        exit 1
    fi
    if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "Python 3.10 or newer is required ($("$PY" --version 2>&1) found)."
        exit 1
    fi
    echo "Setting up the Python environment, one moment..."
    if ! "$PY" -m venv .venv; then
        echo "Could not create a virtual environment."
        echo "  Debian/Ubuntu: sudo apt install python3-venv"
        rm -rf .venv
        exit 1
    fi
fi

if ! .venv/bin/python -c "import textual" >/dev/null 2>&1; then
    echo "Installing Textual..."
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet "textual>=1.0"
fi

exec .venv/bin/python -m nullroute "$@"
