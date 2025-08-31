#!/bin/bash

# Change to the script's directory (important for relative paths within your project)
cd /home/runo/code/Bedehus/

# Activate the virtual environment
source venv/bin/activate

# Run your Python script
python main.py

# Deactivate the virtual environment (optional, as the script will exit anyway)
deactivate

# You can add other commands here if needed
