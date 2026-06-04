#!/bin/bash
# Script to manage project dependencies
# Usage: ./manage_deps.sh install package
#      ./manage_deps.sh update
#      ./manage_deps.sh freeze

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
        PIP_EXE="pip.exe"
        ;;
    *)
        PYTHON_SUBDIR="bin"
        PYTHON_EXE="python"
        PIP_EXE="pip"
        ;;
esac

VENV_PYTHON="$PROJECT_DIR/$VENV_NAME/$PYTHON_SUBDIR/$PYTHON_EXE"
VENV_PIP="$PROJECT_DIR/$VENV_NAME/$PYTHON_SUBDIR/$PIP_EXE"

# If pip does not exist as a separate executable, use it as a module
if [ -f "$VENV_PIP" ]; then
    PIP_CMD=("$VENV_PIP")
else
    PIP_CMD=("$VENV_PYTHON" -m pip)
fi

if [ ! -d "$VENV_NAME" ]; then
    echo "ERROR: Virtual environment not found"
    echo "Create it first: python -m venv $VENV_NAME"
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python not found at: $VENV_PYTHON"
    exit 1
fi

case "${1:-help}" in
    install)
        if [ -z "${2:-}" ]; then
            echo "Usage: $0 install package_name [version]"
            exit 1
        fi
        echo "Installing $2..."
        "${PIP_CMD[@]}" install "$2"
        echo "Updating requirements.txt..."
        "${PIP_CMD[@]}" freeze > requirements.txt
        ;;
    update)
        echo "Updating all dependencies..."
        "${PIP_CMD[@]}" install --upgrade -r requirements.txt
        "${PIP_CMD[@]}" freeze > requirements.txt
        ;;
    freeze)
        echo "Generating updated requirements.txt..."
        "${PIP_CMD[@]}" freeze > requirements.txt
        echo "requirements.txt updated with current dependencies"
        ;;
    list)
        echo "Installed dependencies:"
        "${PIP_CMD[@]}" list
        ;;
    help|*)
        echo "FlightGear Framework dependency management"
        echo "Usage: ./manage_deps.sh [command] [arguments]"
        echo ""
        echo "Available commands:"
        echo "  install <package>  - Install a new package"
        echo "  update             - Update all dependencies"
        echo "  freeze             - Generate updated requirements.txt"
        echo "  list               - List installed dependencies"
        echo "  help               - Show this help"
        ;;
esac
