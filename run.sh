#!/bin/bash
echo "============================================"
echo "  Mattress Price App - Mac/Linux Startup"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install from https://www.python.org/downloads/"
    exit 1
fi

# Install Flask
echo "Installing/checking dependencies..."
pip3 install flask --quiet

echo ""
echo "Starting app..."
echo "Open your browser at: http://localhost:5000"
echo "For other computers on your network, use this machine's IP on port 5000"
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

python3 app.py
