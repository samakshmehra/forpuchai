#!/bin/bash
# Install system dependencies for Playwright
playwright install-deps chromium
# Install Playwright browsers
playwright install chromium
# Start the MCP server
python forpuchai.py 