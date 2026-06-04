#!/bin/bash
# Script to run framework tests
# Usage: ./run_tests.sh [pytest options]

set -e

VENV_NAME="venv_flightgear"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
cd "$PROJECT_DIR"

# Detect operating system
case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*)
        PYTHON_SUBDIR="Scripts"
        PYTHON_EXE="python.exe"
        ;;
    *)
        PYTHON_SUBDIR="bin"
        PYTHON_EXE="python"
        ;;
esac

VENV_PYTHON="$PROJECT_DIR/$VENV_NAME/$PYTHON_SUBDIR/$PYTHON_EXE"

# Verify that the virtual environment exists
if [ ! -d "$VENV_NAME" ]; then
    echo "ERROR: Virtual environment not found"
    echo "Create it first: python -m venv $VENV_NAME"
    echo "Then install dependencies: ./$VENV_NAME/$PYTHON_SUBDIR/$PYTHON_EXE -m pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python not found at: $VENV_PYTHON"
    exit 1
fi

# Create reports directory if it does not exist
mkdir -p reports

echo "Running FlightGear framework tests..."

export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# Run pytest with the virtual environment Python
"$VENV_PYTHON" -m pytest "$@"

echo "Tests completed. Check reports in the 'reports/' directory"
