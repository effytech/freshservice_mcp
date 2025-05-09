# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
# syntax=docker/dockerfile:1
# Use Python 3.13 slim for compatibility (requires >=3.13)
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition
COPY pyproject.toml ./
COPY src ./src

# Install project and dependencies
RUN pip install --no-cache-dir .

# Use python module entrypoint to start the MCP server
ENTRYPOINT ["python", "-m", "freshservice_mcp.server"]
