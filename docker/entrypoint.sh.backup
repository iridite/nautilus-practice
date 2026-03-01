#!/bin/bash
set -e

# Print environment info
echo "=========================================="
echo "NautilusTrader Practice - Docker Container"
echo "=========================================="
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "=========================================="

# Check if config files exist
if [ ! -f "config/environments/dev.yaml" ]; then
    echo "ERROR: Config files not found!"
    exit 1
fi

# Run the main application with passed arguments
exec python main.py "$@"
