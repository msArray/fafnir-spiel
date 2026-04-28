#!/bin/bash
# Setup and test script for Fafnir MCCFR AI

cd /workspaces/fafnir-spiel

# Install dependencies if needed
echo "Installing dependencies..."
pip install -q open-spiel python-socketio 2>/dev/null || true

# Run tests
echo "Running tests..."
python test_fafnir.py

echo "Tests completed!"
