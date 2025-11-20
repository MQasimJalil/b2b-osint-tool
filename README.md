# B2B OSINT Tool

## Purpose
End-to-end toolkit to discover, crawl, and extract structured B2B data from ecommerce domains i.e. Goalkeeper Gloves, mine public reviews/discussions, and produce JSONL outputs ready for outreach and analysis. **Includes RAG system for intelligent product intelligence queries.**

---

## Project Structure

```
B2B OSINT Tool/
├── pipeline/                    # End-to-end discovery → vetting → crawling → extraction → RAG → email
│   ├── discover.py              # Selenium-based multi-engine discovery (Google/Bing/Brave)
│   ├── discover_config.yaml     # Config for discovery (queries, engines, pacing, etc.)
│   ├── rule_vet.py              # Rule-based vetting (HTML heuristics)
│   ├── local_vet.py             # Local LLM vetting (Ollama/Mistral)
│   ├── crawl.py                 # Robust async crawler (crawl4ai)
│   ├── extract.py               # OpenAI extraction (company profiles + products)
│   ├── deduplicate.py           # Domain deduplication (pattern + homepage comparison)
│   ├── rag.py                   # RAG system (embeddings, vector search, query interface)
│   ├── rag_cli.py               # CLI tool for RAG operations
│   ├── gemini_agent.py          # Gemini agent for email generation (function calling)
│   ├── agent_tools.py           # RAG tools for Gemini agent (company, products, pricing)
│   ├── gmail_sender.py          # Gmail API integration (OAuth2, send emails)
│   ├── email_tracker.py         # Email tracking system (JSONL, campaigns, stats)
│   └── cache/                   # Discovery & vetting state (JSONL)
│       ├── discovered_domains.jsonl
│       ├── query_cache.jsonl
│       ├── softvet_cache.jsonl
│       ├── local_vet_results.jsonl
│       ├── crawled_domains.jsonl      # Deduplication: crawled domain tracking
│       ├── dedup_results.jsonl        # Deduplication: decisions and scores
│       └── homepage_features/         # Deduplication: cached homepage features
├── crawled_data/                # Raw crawled pages (generated)
│   ├── domains/                 # Per-domain JSONL.GZ content
│   │   ├── example.com.jsonl.gz
│   │   └── ...
│   └── crawl_state/             # Resumable crawl state
│       ├── example.com_visited.txt
│       ├── example.com_hashes.txt
│       └── ...
├── extracted_data/              # Structured data (generated)
│   ├── companies/               # Per-company folders
│   │   ├── example.com/
│   │   │   ├── profile.json     # Company profile (contacts, social, management)
│   │   │   ├── products.jsonl   # Product catalog
│   │   │   └── metadata.json    # Extraction metadata
│   │   └── ...
│   └── indexes/                 # Global searchable indexes
│       ├── all_companies.jsonl
│       └── all_products.jsonl
├── rag_data/                    # RAG vector database (generated)
│   ├── chroma_db/               # ChromaDB vector storage
│   │   ├── raw_pages/           # Raw page chunks collection
│   │   ├── products/            # Product chunks collection
│   │   └── companies/           # Company chunks collection
│   └── .embedded_domains.jsonl  # Tracking of embedded domains
├── utils/
│   └── proxy_handler.py         # Proxy rotation helper
├── main.py                      # **Main pipeline orchestrator** (run this!)
├── run_agentic_flow.py          # **Email generation workflow** (generate drafts)
├── save_drafts_to_gmail.py      # **Save drafts to Gmail** (for manual review/send)
├── email_drafts.jsonl           # Generated email drafts (generated)
├── mcp_server.py                # FastAPI HTTP MCP server
├── mcp_stdio_server.py          # FastMCP stdio MCP server
├── mcp.json                     # MCP manifest for HTTP server
├── Dockerfile                   # Docker container for MCP server
├── credentials.json             # Gmail OAuth2 credentials (user-provided)
├── token.json                   # Gmail OAuth2 token (generated)
├── email_playbook.md            # Email copywriting instructions for agent
├── requirements.txt             # All dependencies
├── DEDUPLICATION.md             # Domain deduplication guide
└── README.md
```

---

## Key Workflows

### **Main End-to-End Pipeline** — `main.py` ⭐
The primary workflow that runs the full discovery → vetting → crawling → extraction pipeline:

1. **Discovery** (`pipeline/discover.py`)
   - Selenium-based multi-engine search (Google, Bing, Brave)
   - Config-driven query generation (negatives, platform hints, geo-targeting)
   - Parallel 3-driver execution with per-driver CAPTCHA pause
   - Soft vetting (HTTP probe for e-commerce signals)
   - Outputs: `pipeline/cache/discovered_domains.jsonl`

2. **Vetting** (`pipeline/rule_vet.py` + `pipeline/local_vet.py`)
   - Rule-based vetting (HTML heuristics for Auto-YES/Auto-NO)
   - Local LLM vetting (Ollama/Mistral) for "unclear" domains
   - Cost-effective: only unclear domains sent to LLM
   - Outputs: `pipeline/cache/local_vet_results.jsonl`

3. **Crawling** (`pipeline/crawl.py`)
   - Robust async crawler using `crawl4ai`
   - Content hashing, state persistence, retry logic
   - Respects robots.txt, adaptive throttling
   - Outputs: `crawled_data/domains/*.jsonl.gz` + `crawled_data/crawl_state/*`

4. **Extraction** (`pipeline/extract.py`)
   - OpenAI-based company profile extraction (contacts, social, management)
   - Product catalog extraction (brand, name, category, price, specs, reviews)
   - Per-company storage: `extracted_data/companies/{domain}/`
     - `profile.json` — Company profile
     - `products.jsonl` — Product catalog
     - `metadata.json` — Extraction metadata
   - Global indexes: `extracted_data/indexes/all_companies.jsonl` & `all_products.jsonl`

5. **RAG (Retrieval-Augmented Generation)** (`pipeline/rag.py` + `pipeline/rag_cli.py`) ⭐
   - Semantic chunking of raw pages (respects markdown structure)
   - Embedding generation using OpenAI `text-embedding-3-small`
   - ChromaDB vector storage (local, persistent)
   - Hybrid search: raw pages + products + companies
   - Auto-detect changes (content hash tracking, incremental updates)
   - Query interface with LLM-generated answers
   - Outputs: `rag_data/chroma_db/` (vector database)

6. **Email Outreach Workflow** (`run_agentic_flow.py` + `save_drafts_to_gmail.py`) ⭐ NEW
   - **Agentic email generation** (`pipeline/gemini_agent.py`)
     - Gemini 2.5 Pro with function calling
     - Automatic research using RAG tools (company profile, products, pricing, competitors)
     - Personalized subject lines (3-5 options) and email body
     - Zero-placeholder outputs (uses real sender identity)
   - **Gmail draft creation** (`save_drafts_to_gmail.py`)
     - Saves drafts to your Gmail account (not sent)
     - OAuth2 authentication (Desktop app)
     - You review and send manually from Gmail UI
   - **Optional email tracking** (`pipeline/email_tracker.py`)
     - Manual tracking for sent emails
     - Statistics and reporting
   - Outputs: `email_drafts.jsonl` (local), Gmail drafts (in your Gmail account)

---

## Setup

1) Python
- Use Python 3.10+ on Windows 10/11.

2) Install dependencies
```powershell
pip install -r requirements.txt
# Note: requirements.txt includes all dependencies including chromadb and tiktoken for RAG
```

**Dependencies include:**
- `crawl4ai` - Web crawling
- `openai` - LLM extraction and embeddings
- `chromadb` - Vector database for RAG
- `tiktoken` - Token counting for semantic chunking
- `selenium`, `undetected-chromedriver` - Browser automation
- `fastapi`, `uvicorn` - HTTP MCP server
- `mcp` - Stdio MCP server framework

3) Playwright note (crawl4ai)
- If Playwright browsers are required under the hood, install them:
```powershell
python -m playwright install
```

4) OpenAI credentials
- Prefer setting an environment variable rather than hardcoding keys.
```powershell
$env:OPENAI_API_KEY="sk-..."
```
- The provided scripts currently instantiate the client directly; update them to read from the environment for safer ops if needed.

---

## Usage

### **Run the Full Pipeline (Discovery → Vetting → Crawling → Extraction → RAG)** ⭐

**Run the complete pipeline:**
```powershell
python main.py --industry "goalkeeper gloves" --max-discovery 100 --max-crawl-pages 200 --depth 2
```

**Skip discovery (resume from cached domains):**
```powershell
python main.py --skip-discovery
```

**Parameters:**
- `--industry` — Target industry to discover ecommerce sites for (default: "goalkeeper gloves")
- `--max-discovery` — Max results to fetch from search (default: 100)
- `--max-crawl-pages` — Max pages per site to crawl (default: 200)
- `--depth` — Max crawl depth per site (default: 2)
- `--skip-discovery` — Skip running discovery; use cached discovered domains

**Outputs:**
- `pipeline/cache/discovered_domains.jsonl` — Discovered domains
- `pipeline/cache/local_vet_results.jsonl` — Vetting decisions
- `crawled_data/domains/*.jsonl.gz` — Raw crawled pages
- `crawled_data/crawl_state/*` — Resumable crawl state
- `extracted_data/companies/{domain}/` — Per-company folders
  - `profile.json` — Company profile
  - `products.jsonl` — Product catalog
  - `metadata.json` — Extraction metadata
- `extracted_data/indexes/all_companies.jsonl` — Global companies index
- `extracted_data/indexes/all_products.jsonl` — Global products index
- `rag_data/chroma_db/` — Vector database (after running RAG embedding)

**Optional: Auto-embed for RAG** (uncomment in `main.py`):
After extraction, the pipeline can automatically embed domains for RAG. Uncomment the RAG section in `main.py` to enable.

**Getting company data for email generation:**
```python
from pipeline.extract import get_company_data

data = get_company_data("example.com")
company = data["company"]  # Company profile with contacts, social, management
products = data["products"]  # List of all products
metadata = data["metadata"]  # Extraction metadata
```

**Searching global indexes:**
```python
import json

# Find all companies
for line in open("extracted_data/indexes/all_companies.jsonl"):
    c = json.loads(line)
    print(c["company"], c["email"])

# Find products by brand
for line in open("extracted_data/indexes/all_products.jsonl"):
    p = json.loads(line)
    if "Nike" in p.get("brand", ""):
        print(p["domain"], p["name"], p["price"])
```

**Using RAG for product intelligence queries:**
```powershell
# Embed domains (after crawling/extraction)
python -m pipeline.rag_cli embed

# Query with natural language
python -m pipeline.rag_cli query "goalkeeper gloves under $50"
python -m pipeline.rag_cli query "professional gloves" --domain aviatasports.com --brand "Stretta"

# Query specific collections
python -m pipeline.rag_cli query "Aviata Sports company information" --collections companies

# Check embedding statistics
python -m pipeline.rag_cli stats
```

**RAG Python API:**
```python
from pipeline.rag import query_rag, get_rag_answer

# Simple query
results = query_rag("goalkeeper gloves under $50", top_k=5)
for result in results:
    print(f"{result['collection']}: {result['content'][:200]}...")

# Query with filters
results = query_rag(
    "professional goalkeeper gloves",
    filters={"domain": "aviatasports.com", "brand": "Stretta"},
    top_k=3
)

# Get LLM-generated answer
answer = get_rag_answer(
    "Does Aviata Sports have gloves under $50?",
    filters={"domain": "aviatasports.com"},
    top_k=5
)
print(answer)
```

### **Email Outreach Workflow** ⭐ NEW

Complete workflow for generating personalized emails, sending via Gmail API, and tracking results.

#### **Prerequisites:**

1. **Set Google API Key** (for Gemini agent):
```powershell
$env:GOOGLE_API_KEY="your-gemini-api-key"
```

2. **Set up Gmail API credentials** (for sending):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Gmail API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download `credentials.json` and place in project root
   - Run authentication flow (first time only):
   ```powershell
   python -c "from pipeline.gmail_sender import test_authentication; test_authentication()"
   ```
   - This creates `token.json` for future use

#### **Step 1: Generate Email Drafts** (`run_agentic_flow.py`)

The agentic flow automatically:
1. Ensures data is crawled, extracted, and embedded (RAG)
2. Uses Gemini agent with function calling to research each company
3. Generates 3-5 personalized subject lines + email body
4. Saves structured drafts to `email_drafts.jsonl`

**Generate emails for specific domains:**
```powershell
python run_agentic_flow.py theoneglove.com bravegk.com aviatasports.com
```

**How the agent works:**
- Automatically calls RAG tools (`get_company_profile`, `get_product_catalog`, `analyze_pricing_strategy`, etc.)
- Researches company's products, pricing, competitors
- Follows playbook instructions from `email_playbook.md`
- Zero placeholders - uses real sender identity (Qasim Jalil, Raqim International)
- Clean output with regex parsing (no "thought" clutter)

**Output format** (`email_drafts.jsonl`):
```json
{
  "domain": "theoneglove.com",
  "subject_lines": [
    "Scaling Your Professional Goalkeeper Gloves Distribution to Pakistan",
    "Partnership Opportunity: B2B Distribution for The One Glove",
    "Expanding The One Glove's Reach in South Asian Markets"
  ],
  "email_body": "Hi [Name],\n\nI came across The One Glove...",
  "raw_output": "..."
}
```

#### **Step 2: Save Drafts to Gmail** (`save_drafts_to_gmail.py`)

The workflow saves drafts to your Gmail account (not sent) so you can review and send manually:
1. Loads drafts from `email_drafts.jsonl`
2. Extracts contact emails from `extracted_data/companies/{domain}/contacts.json`
3. Creates Gmail draft messages (saved to your Drafts folder)
4. You review and send from Gmail UI

**Save all drafts to Gmail:**
```powershell
python save_drafts_to_gmail.py
```

**Save specific domains only:**
```powershell
python save_drafts_to_gmail.py --domains theoneglove.com bravegk.com
```

**Use different subject line:**
```powershell
# Use 2nd subject line option (default is 1st)
python save_drafts_to_gmail.py --subject-index 1
```

**Parameters:**
- `--domains` — Save only these domains (if not specified, saves all drafts)
- `--subject-index` — Which subject line to use (0=first, 1=second, etc. Default: 0)
- `--drafts-file` — Path to email drafts file (default: `email_drafts.jsonl`)

**After saving:**
1. Go to Gmail → Drafts
2. Review each draft
3. Edit if needed
4. Click Send when ready

#### **Optional: Manual Email Tracking**

Since you're sending emails manually from Gmail, you can track them using `pipeline/email_tracker.py` if needed.

**Track a manually sent email:**
```python
from pipeline.email_tracker import track_sent_email
from datetime import datetime

track_sent_email(
    domain="theoneglove.com",
    recipient_email="sales@theoneglove.com",
    subject_line="Partnership opportunity with Raqim International",
    email_body="...",
    send_result={
        "success": True,
        "sent_at": datetime.utcnow().isoformat() + "Z",
        "message_id": "manual"
    }
)
```

**View statistics:**
```python
from pipeline.email_tracker import print_email_report
print_email_report()
```

#### **Complete Example: End-to-End Outreach**

```powershell
# 1. Run full pipeline (if not done already)
python main.py --industry "goalkeeper gloves" --max-discovery 100

# 2. Generate email drafts for vetted domains
python run_agentic_flow.py theoneglove.com bravegk.com aviatasports.com

# 3. Save drafts to Gmail
python save_drafts_to_gmail.py

# 4. Go to Gmail → Drafts
# 5. Review, edit, and send each email manually
```

### **MCP Server (Model Context Protocol)** ⭐

Expose your ChromaDB market intelligence data to LLM clients like Claude Desktop through an MCP server. Two implementations available:

#### **HTTP MCP Server** (`mcp_server.py`)

FastAPI-based server exposing REST endpoints for MCP tools.

**Run locally:**
```powershell
python mcp_server.py
# Server runs on http://localhost:8080
```

**Run in Docker:**
```powershell
docker build -t b2b-osint-mcp .
docker run -p 8080:8080 ^
  -e OPENAI_API_KEY=$Env:OPENAI_API_KEY ^
  -v ${PWD}\rag_data:/app/rag_data ^
  -v ${PWD}\crawled_data:/app/crawled_data ^
  -v ${PWD}\extracted_data:/app/extracted_data ^
  b2b-osint-mcp
```

**Available tools (HTTP endpoints):**
- `POST /tools/market_search` - Semantic search across all collections
- `POST /tools/filter_search` - Search with metadata filters (domain, brand, category, company)
- `GET /tools/domains` - List all available domains
- `GET /tools/contacts` - Get structured contact information
- `GET /tools/stats` - Database statistics (counts, date ranges)
- `GET /tools/recent_crawls` - Recent crawl activity logs

**Example requests:**
```powershell
# Health check
curl http://localhost:8080/health

# Market search
curl -X POST http://localhost:8080/tools/market_search ^
  -H "Content-Type: application/json" ^
  -d '{\"query\":\"goalkeeper gloves under $50\",\"n_results\":5}'

# Filtered search
curl -X POST http://localhost:8080/tools/filter_search ^
  -H "Content-Type: application/json" ^
  -d '{\"query\":\"professional gloves\",\"key\":\"domain\",\"value\":\"aviatasports.com\",\"n_results\":3}'

# Get domains
curl http://localhost:8080/tools/domains

# Get stats
curl http://localhost:8080/tools/stats
```

See `DOCKER_USAGE.md` for detailed Docker instructions.

#### **Stdio MCP Server** (`mcp_stdio_server.py`)

FastMCP-based stdio server for direct integration with Claude Desktop.

**Run locally:**
```powershell
$env:OPENAI_API_KEY="sk-..."
python mcp_stdio_server.py
```

**Configure Claude Desktop:**

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "b2b-osint": {
      "command": "python",
      "args": ["mcp_stdio_server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

**Available tools (same as HTTP server):**
- `market_search(query, n_results)` - Semantic search
- `filter_search(query, key, value, n_results)` - Filtered search
- `get_domains()` - List domains
- `get_contacts()` - Get contacts
- `get_stats()` - Get statistics
- `get_recent_crawls(limit)` - Recent crawls

**Using with Docker MCP Toolkit:**

For Docker-based MCP integration, see `setup-guide.md` for complete instructions on:
- Building the Docker image
- Creating custom catalog entries
- Configuring Claude Desktop with Docker MCP Gateway

**Tips:**
- The pipeline is fully crash-safe and resumable at each stage
- Adjust `pipeline/discover_config.yaml` to tune discovery behavior
- Discovery runs in parallel with 3 drivers (Google/Bing/Brave) by default
- Manual CAPTCHA solving: window titles show which engine needs attention
- Vetting is cost-effective: rule-based first, local LLM (Ollama/Mistral) only for unclear cases
- **RAG**: After extraction, run `python -m pipeline.rag_cli embed` to enable product intelligence queries
- **RAG**: Embedding is incremental - only new/changed content is embedded (auto-detected via content hashes)
- **RAG**: Use `--force` flag to re-embed all domains if needed
- **MCP**: Ensure `OPENAI_API_KEY` is set for query embeddings
- **MCP**: HTTP server requires existing ChromaDB data (run RAG embedding first)
- **MCP**: Both servers connect to the same ChromaDB instance - no data duplication

---

## Data Inputs/Outputs

**Main Pipeline:**
- Inputs: Industry keyword (via `--industry` flag)
- Outputs:
  - `pipeline/cache/*.jsonl` — Discovery & vetting state
  - `crawled_data/domains/*.jsonl.gz` — Raw crawled pages
  - `crawled_data/crawl_state/*` — Resumable crawl state
  - `extracted_data/companies/{domain}/*` — Per-company structured data
  - `extracted_data/indexes/*.jsonl` — Global searchable indexes
  - `rag_data/chroma_db/` — Vector database (after RAG embedding)

**RAG System:**
- Inputs: Crawled pages (`crawled_data/`) + Extracted data (`extracted_data/`)
- Outputs:
  - `rag_data/chroma_db/` — ChromaDB vector database with three collections:
    - `raw_pages` — Semantic chunks of raw crawled pages
    - `products` — Structured product embeddings
    - `companies` — Company profile embeddings
  - `rag_data/.embedded_domains.jsonl` — Tracking of embedded domains

---

## Operational Notes
- Respect robots.txt and site terms; this is a research tool.
- Rate limits and blocking can occur. Use `utils/proxy_handler.py` (or your proxy infra) for requests-based flows.
- Keep keys and secrets out of source; prefer environment variables or secret managers.
- The pipeline is fully crash-safe and resumable at each stage (discovery, vetting, crawling, extraction, RAG).

---

## Troubleshooting

### General
- Missing module errors: ensure you installed `requirements.txt` (includes all dependencies).
- Playwright errors: run `python -m playwright install`.
- OpenAI auth errors: verify `$env:OPENAI_API_KEY` is set in the same PowerShell session.
- Stalled crawls: reduce `--maxc`, increase delays, or limit `--depth`.

### RAG
- RAG embedding errors: ensure you've crawled and extracted data first. Check that `crawled_data/domains/` and `extracted_data/companies/` exist.
- RAG query errors: run `python -m pipeline.rag_cli embed` first to create vector database.
- ChromaDB collection not found: collections are created automatically on first embed. Run `embed` command.

### MCP Server
- MCP server errors: ensure ChromaDB data exists (`rag_data/chroma_db/`). Run RAG embedding first.
- MCP tools not appearing in Claude Desktop: restart Claude Desktop after config changes. Check logs in Help → Show Logs.
- Docker volume permission errors: ensure host directories are writable. On Linux/macOS, check Docker permissions.

### Email Workflow
- **Gemini agent errors:** Verify `$env:GOOGLE_API_KEY` is set (not `OPENAI_API_KEY`).
- **Gmail authentication failed:** Ensure `credentials.json` exists in project root. Download from Google Cloud Console.
- **Gmail "invalid_grant" error:** Delete `token.json` and re-authenticate.
- **No contact emails found:** Check that `extracted_data/companies/{domain}/contacts.json` or `profile.json` exists. Re-run extraction if missing.
- **Draft creation failed:** Check Gmail API is enabled in Cloud Console. Verify you have "Gmail API" (not just "Google API").
- **Empty subject lines:** Check `email_drafts.jsonl` format. Re-generate drafts if corrupted.
- **Drafts not appearing in Gmail:** Refresh Gmail. Check the "Drafts" folder (not "Sent").

### Deduplication
- **False positives (legitimate domains marked as duplicates):** Lower duplicate threshold: `duplicate_threshold=0.80` in `main.py`
- **False negatives (duplicates not detected):** Lower pattern threshold: `pattern_threshold=0.15` or switch to OpenAI extraction: `extraction_method="openai"`
- **Homepage features not cached:** Features are fetched on first comparison (minor delay). Consider running with OpenAI method for better accuracy.

---

## Roadmap Ideas
- Enhanced RAG features: multi-query search, hybrid search with keyword + vector, query expansion
- RAG UI: Web interface for natural language queries
- Product comparison tool: Automated side-by-side product comparisons via RAG
- Streamlit dashboard for monitoring pipeline progress and data quality
- Enhanced discovery: More search engines, better query templates, regional variations
- MCP enhancements: Additional filtering options, batch operations, real-time updates
