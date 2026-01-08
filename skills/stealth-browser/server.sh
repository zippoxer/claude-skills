#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse args
HEADLESS=false
PORT=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --headless) HEADLESS=true ;;
        --port) PORT="$2"; shift ;;
        --port=*) PORT="${1#*=}" ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Setup venv if needed (do this first so we can use Python)
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

# If no port specified, default to 6222
if [ -z "$PORT" ]; then
    PORT=6222
fi

# Check if requested port is available
if ! python -c "
import socket
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', $PORT))
except OSError:
    exit(1)
" 2>/dev/null; then
    # Find next available port
    SUGGESTED_PORT=$(python -c "
import socket
for port in range(6222, 6322):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            print(port)
            break
    except OSError:
        continue
")
    echo "Port $PORT is in use (likely by another session)."
    echo "Each session needs its own server - do not reuse servers started by other sessions."
    echo "Start your own: ./server.sh --port $SUGGESTED_PORT"
    exit 1
fi

echo "Starting stealth-browser server on port $PORT..."
PORT=$PORT HEADLESS=$HEADLESS python server.py

