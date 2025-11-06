# B2B OSINT Tool

## Purpose
End-to-end toolkit to discover, crawl, and extract structured B2B data from football/soccer ecommerce domains (with a focus on goalkeeper gear), mine public reviews/discussions, and produce JSONL outputs ready for outreach and analysis. **Includes RAG (Retrieval-Augmented Generation) system for intelligent product intelligence queries.**

---

## Project Structure

```
B2B OSINT Tool/
├── pipeline/                    # End-to-end discovery → vetting → crawling → extraction → RAG
│   ├── discover.py              # Selenium-based multi-engine discovery (Google/Bing/Brave)
│   ├── discover_config.yaml     # Config for discovery (queries, engines, pacing, etc.)
│   ├── rule_vet.py              # Rule-based vetting (HTML heuristics)
│   ├── local_vet.py             # Local LLM vetting (Ollama/Mistral)
│   ├── crawl.py                 # Robust async crawler (crawl4ai)
│   ├── extract.py               # OpenAI extraction (company profiles + products)
│   ├── rag.py                   # RAG system (embeddings, vector search, query interface)
│   ├── rag_cli.py               # CLI tool for RAG operations
│   └── cache/                   # Discovery & vetting state (JSONL)
│       ├── discovered_domains.jsonl
│       ├── query_cache.jsonl
│       ├── softvet_cache.jsonl
│       └── local_vet_results.jsonl
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
├── requirements.txt             # All dependencies
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

5. **RAG (Retrieval-Augmented Generation)** (`pipeline/rag.py` + `pipeline/rag_cli.py`) ⭐ NEW
   - Semantic chunking of raw pages (respects markdown structure)
   - Embedding generation using OpenAI `text-embedding-3-small`
   - ChromaDB vector storage (local, persistent)
   - Hybrid search: raw pages + products + companies
   - Auto-detect changes (content hash tracking, incremental updates)
   - Query interface with LLM-generated answers
   - Outputs: `rag_data/chroma_db/` (vector database)

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

**Tips:**
- The pipeline is fully crash-safe and resumable at each stage
- Adjust `pipeline/discover_config.yaml` to tune discovery behavior
- Discovery runs in parallel with 3 drivers (Google/Bing/Brave) by default
- Manual CAPTCHA solving: window titles show which engine needs attention
- Vetting is cost-effective: rule-based first, local LLM (Ollama/Mistral) only for unclear cases
- **RAG**: After extraction, run `python -m pipeline.rag_cli embed` to enable product intelligence queries
- **RAG**: Embedding is incremental - only new/changed content is embedded (auto-detected via content hashes)
- **RAG**: Use `--force` flag to re-embed all domains if needed

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
- Missing module errors: ensure you installed `requirements.txt` (includes all dependencies).
- Playwright errors: run `python -m playwright install`.
- OpenAI auth errors: verify `$env:OPENAI_API_KEY` is set in the same PowerShell session.
- Stalled crawls: reduce `--maxc`, increase delays, or limit `--depth`.
- RAG embedding errors: ensure you've crawled and extracted data first. Check that `crawled_data/domains/` and `extracted_data/companies/` exist.
- RAG query errors: run `python -m pipeline.rag_cli embed` first to create vector database.
- ChromaDB collection not found: collections are created automatically on first embed. Run `embed` command.

---

## Roadmap Ideas
- Enhanced RAG features: multi-query search, hybrid search with keyword + vector, query expansion
- RAG UI: Web interface for natural language queries
- Product comparison tool: Automated side-by-side product comparisons via RAG
- Streamlit dashboard for monitoring pipeline progress and data quality
- Enhanced discovery: More search engines, better query templates, regional variations
