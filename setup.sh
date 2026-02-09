#!/bin/bash

echo "======================================"
echo "Influencer Matcher - Setup"
echo "======================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo ""
    echo "Install Python from: https://www.python.org/downloads/"
    echo "Or via Homebrew: brew install python3"
    exit 1
fi

echo "Python found!"
python3 --version
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment"
    exit 1
fi
echo "Virtual environment created!"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to activate virtual environment"
    exit 1
fi
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
echo ""

# Create data directories
echo "Creating data directories..."
mkdir -p data/uploads
mkdir -p data/exports
echo ""

echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "To start the app:"
echo "  1. Run: ./run.sh"
echo "  2. Open browser: http://localhost:5000"
echo ""
