FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow, fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install geeViz and MCP deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the geeViz package
COPY . /app/geeViz/
ENV PYTHONPATH=/app

# HTTP transport, bind to all interfaces (Cloud Run / Databricks Apps
# handle routing), sandbox ON for remote use
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080
ENV MCP_PATH=/mcp

# Optional: GEE service account key (mount as secret or set as env var)
# ENV GEE_SERVICE_ACCOUNT_KEY=/secrets/ee-sa-key.json
# ENV GEE_PROJECT=your-gee-project-id

EXPOSE 8080

CMD ["python", "-m", "geeViz.mcp.server", "--sandbox"]
