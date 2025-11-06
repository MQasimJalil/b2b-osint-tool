FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=off \
    PORT=8080

WORKDIR /app

# System deps (optional, lightweight)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist local data volumes for Chroma and pipeline artifacts
VOLUME ["/app/rag_data", "/app/crawled_data", "/app/extracted_data"]

EXPOSE 8080

CMD ["python", "mcp_stdio_server.py"]


