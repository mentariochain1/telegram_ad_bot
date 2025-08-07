#!/bin/bash

# Setup script for Telegram Ad Bot

echo "Setting up Telegram Ad Bot..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Please edit .env file with your bot token and other settings"
fi

# Create logs directory
mkdir -p logs

echo "Setup complete!"
echo "Next steps:"
echo "1. Edit .env file with your bot token"
echo "2. Run: source venv/bin/activate"
echo "3. Run: python main.py"