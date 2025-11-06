## B2B OSINT MCP Server — Docker Usage

This guide shows how to build and run the FastAPI MCP server in Docker, exposing your local ChromaDB-backed market intelligence tools on port 8080.

### Prerequisites
- Docker installed
- Your data directories exist locally (mounted into the container):
  - `rag_data/` (ChromaDB persistent storage)
  - `crawled_data/` (crawler state and logs)
  - `extracted_data/` (structured outputs)
- `OPENAI_API_KEY` available in your environment for query embeddings

### Build the image

```powershell
docker build -t b2b-osint-mcp .
```

```bash
docker build -t b2b-osint-mcp .
```

### Run the container (Windows PowerShell)

```powershell
docker run -p 8080:8080 ^
  -e OPENAI_API_KEY=$Env:OPENAI_API_KEY ^
  -v ${PWD}\rag_data:/app/rag_data ^
  -v ${PWD}\crawled_data:/app/crawled_data ^
  -v ${PWD}\extracted_data:/app/extracted_data ^
  --name b2b-osint-mcp \
  b2b-osint-mcp
```

### Run the container (macOS/Linux bash)

```bash
docker run -p 8080:8080 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -v "$(pwd)/rag_data:/app/rag_data" \
  -v "$(pwd)/crawled_data:/app/crawled_data" \
  -v "$(pwd)/extracted_data:/app/extracted_data" \
  --name b2b-osint-mcp \
  b2b-osint-mcp
```

Notes:
- Volumes ensure Chroma and pipeline artifacts persist across container restarts.
- The app listens on `0.0.0.0:8080` inside the container; mapped to host `8080`.

### Health check

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

### Tool endpoints
All responses are JSON. Example invocations:

- Market search
```bash
curl -X POST http://localhost:8080/tools/market_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"goalkeeper gloves under $50","n_results":5}'
```

- Filtered search (filter keys: domain | brand | category | company)
```bash
curl -X POST http://localhost:8080/tools/filter_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"professional gloves","key":"domain","value":"aviatasports.com","n_results":3}'
```

- List domains
```bash
curl http://localhost:8080/tools/domains
```

- Contacts
```bash
curl http://localhost:8080/tools/contacts
```

- Stats
```bash
curl http://localhost:8080/tools/stats
```

- Recent crawls
```bash
curl "http://localhost:8080/tools/recent_crawls?limit=10"
```

### Using with an MCP client (e.g., Claude Desktop)
1) Ensure the server is running at `http://localhost:8080`.
2) Provide the `mcp.json` manifest to your MCP client, or configure the client to discover the HTTP server at that base URL.
3) The manifest includes all tool definitions with method, path, and parameter schemas.

### Environment variables
- `OPENAI_API_KEY` (required): used by the server to generate query embeddings.
- `PORT` (optional): default `8080` inside the container.

### docker-compose (optional)

```yaml
services:
  b2b-osint-mcp:
    image: b2b-osint-mcp
    build: .
    container_name: b2b-osint-mcp
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - PORT=8080
    ports:
      - "8080:8080"
    volumes:
      - ./rag_data:/app/rag_data
      - ./crawled_data:/app/crawled_data
      - ./extracted_data:/app/extracted_data
```

Start with:

```bash
docker compose up --build
```

### Troubleshooting
- 401/embedding errors: ensure `OPENAI_API_KEY` is set inside the container (`docker exec -it b2b-osint-mcp env | grep OPENAI`).
- Empty results: confirm your embeddings exist in `rag_data/chroma_db/` (run the pipeline and embed if needed).
- Permission issues on volumes (Linux/macOS): ensure the host directories are writable by Docker.


