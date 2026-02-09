#!/bin/bash

echo "======================================"
echo "Starting Influencer Matcher..."
echo "======================================"
echo ""

# Activate virtual environment
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "ERROR: Virtual environment not found"
    echo "Please run ./setup.sh first"
    exit 1
fi

# Run the app
echo "Opening web app at http://localhost:5000"
echo "Press CTRL+C to stop the server"
echo ""
python app.py
