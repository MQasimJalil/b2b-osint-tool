# ⚡ Quick Start Guide - 5 Minutes to Your First MCP Server

Get your first MCP server running in under 5 minutes!

## Use This B2B OSINT MCP Server (Docker MCP Toolkit)

Follow the same pattern as the example below, but point the catalog to this project's image and tools.

### 1) Build the image

```bash
docker build -t b2b-osint-mcp .
```

### 2) Create a custom catalog entry

```bash
mkdir -p ~/.docker/mcp/catalogs
cat > ~/.docker/mcp/catalogs/b2b-osint.yaml << 'EOF'
version: 2
name: b2b
displayName: B2B OSINT Servers
registry:
  b2b-osint:
    description: "Local market intelligence over ChromaDB"
    title: "B2B OSINT MCP"
    type: server
    dateAdded: "2025-01-01T00:00:00Z"
    image: b2b-osint-mcp:latest
    ref: ""
    tools:
      - name: market_search
      - name: filter_search
      - name: get_domains
      - name: get_contacts
      - name: get_stats
      - name: get_recent_crawls
    metadata:
      category: intelligence
      tags:
        - chromadb
        - rag
        - osint
EOF
```

Windows (PowerShell) path variant:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.docker\mcp\catalogs" | Out-Null
@'
version: 2
name: b2b
displayName: B2B OSINT Servers
registry:
  b2b-osint:
    description: "Local market intelligence over ChromaDB"
    title: "B2B OSINT MCP"
    type: server
    dateAdded: "2025-01-01T00:00:00Z"
    image: b2b-osint-mcp:latest
    ref: ""
    tools:
      - name: market_search
      - name: filter_search
      - name: get_domains
      - name: get_contacts
      - name: get_stats
      - name: get_recent_crawls
    metadata:
      category: intelligence
      tags:
        - chromadb
        - rag
        - osint
'@ | Set-Content "$env:USERPROFILE\.docker\mcp\catalogs\b2b-osint.yaml"
```

### 3) Update the MCP registry

```bash
echo "  b2b-osint:" >> ~/.docker/mcp/registry.yaml
echo '    ref: ""' >> ~/.docker/mcp/registry.yaml
```

PowerShell:

```powershell
Add-Content "$env:USERPROFILE\.docker\mcp\registry.yaml" "  b2b-osint:"
Add-Content "$env:USERPROFILE\.docker\mcp\registry.yaml" "    ref: \"\""
```

### 4) Ensure volumes for persistence (recommended)

The gateway will start containers for you. To persist data, run the HTTP server separately (see DOCKER_USAGE.md), or bake volumes into your local run. For gateway-managed runs, ensure your local `rag_data/`, `crawled_data/`, and `extracted_data/` exist before using the tools.

### 5) Configure Claude Desktop gateway entry

Use the same gateway stanza shown below (Docker MCP Toolkit), including your new `b2b-osint.yaml` catalog in the args list.

macOS path example (add alongside the existing dice catalog):

```json
"args": [
  "run", "-i", "--rm",
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  "-v", "/Users/[YOUR_USERNAME]/.docker/mcp:/mcp",
  "docker/mcp-gateway",
  "--catalog=/mcp/catalogs/docker-mcp.yaml",
  "--catalog=/mcp/catalogs/custom.yaml",
  "--catalog=/mcp/catalogs/b2b-osint.yaml",
  "--config=/mcp/config.yaml",
  "--registry=/mcp/registry.yaml",
  "--tools-config=/mcp/tools.yaml",
  "--transport=stdio"
]
```

Windows path example:

```json
"args": [
  "run", "-i", "--rm",
  "-v", "/var/run/docker.sock:/var/run/docker.sock",
  "-v", "C:\\Users\\[YOUR_USERNAME]\\.docker\\mcp:/mcp",
  "docker/mcp-gateway",
  "--catalog=/mcp/catalogs/docker-mcp.yaml",
  "--catalog=/mcp/catalogs/custom.yaml",
  "--catalog=/mcp/catalogs/b2b-osint.yaml",
  "--config=/mcp/config.yaml",
  "--registry=/mcp/registry.yaml",
  "--tools-config=/mcp/tools.yaml",
  "--transport=stdio"
]
```

When using the gateway, set `OPENAI_API_KEY` in your user environment so the container can inherit it if your gateway config passes env through (or run the HTTP server locally with volumes as in DOCKER_USAGE.md).

### Alternative: Run stdio server directly (no gateway)

You can register a stdio server command in Claude Desktop that runs this project's stdio server:

```json
"mcpServers": {
  "b2b-osint-stdio": {
    "command": "python",
    "args": ["mcp_stdio_server.py"],
    "env": {"OPENAI_API_KEY": "${OPENAI_API_KEY}"}
  }
}
```

This exposes the same tools: `market_search`, `filter_search`, `get_domains`, `get_contacts`, `get_stats`, `get_recent_crawls`.



## Step 4: Update Registry (30 seconds)

```bash
# Add to registry
echo "  dice:" >> ~/.docker/mcp/registry.yaml
echo '    ref: ""' >> ~/.docker/mcp/registry.yaml
```

## Step 5: Configure Claude Desktop (1 minute)

### macOS:
```bash
# Edit Claude config
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Windows (PowerShell):
```powershell
# Edit Claude config
notepad "$env:APPDATA\Claude\claude_desktop_config.json"
```

Add this configuration (replace `[YOUR_USERNAME]` with your actual username):

```json
{
  "mcpServers": {
    "mcp-toolkit-gateway": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "-v", "/Users/[YOUR_USERNAME]/.docker/mcp:/mcp",
        "docker/mcp-gateway",
        "--catalog=/mcp/catalogs/docker-mcp.yaml",
        "--catalog=/mcp/catalogs/custom.yaml",
        "--config=/mcp/config.yaml",
        "--registry=/mcp/registry.yaml",
        "--tools-config=/mcp/tools.yaml",
        "--transport=stdio"
      ]
    }
  }
}
```

**Note for Windows:** Use `C:\\Users\\[YOUR_USERNAME]` with double backslashes

## Step 6: Test It! (30 seconds)

1. **Restart Claude Desktop** (Quit completely and reopen)
2. Open a new chat
3. Click the tools icon (or press Cmd/Ctrl+I)
4. You should see "mcp-toolkit-gateway" with dice rolling tools
5. Try it: "Roll 2d6+3 for damage"

## 🎉 Success!

You now have a working MCP server! Claude can now roll dice for you.

## Troubleshooting

**Tools not appearing?**
- Make sure Docker Desktop is running
- Verify the Docker image built successfully: `docker images | grep dice`
- Check Claude logs: Help → Show Logs

**Permission errors?**
- Make sure Docker Desktop has necessary permissions
- On Mac: System Preferences → Security & Privacy

**Still stuck?**
- Check the full [troubleshooting guide](../docs/troubleshooting.md)
- Watch the video tutorial for visual guidance

## What's Next?

- Build your own MCP server using the [MCP Builder Prompt](../mcp-builder-prompt/)
- Learn about [custom server development](../docs/custom-servers.md)
- Explore the [Docker MCP Gateway](../docs/docker-gateway.md)

---

🎥 **Need visual help?** Watch NetworkChuck's full tutorial on YouTube!