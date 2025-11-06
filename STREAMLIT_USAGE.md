# Streamlit UI Usage Guide

## Overview

The Streamlit UI provides a web-based interface to control all aspects of the B2B OSINT Tool pipeline. You can run the full pipeline, execute individual stages, query RAG, and monitor status - all from a browser interface.

## Installation

1. **Install Streamlit** (if not already installed):
```bash
pip install streamlit
```

Or install all requirements:
```bash
pip install -r requirements.txt
```

## Running the UI

```bash
streamlit run streamlit_app.py
```

This will:
- Start a local web server
- Open your default browser automatically
- Display the UI at `http://localhost:8501`

## Features

### 1. Full Pipeline ⭐
Run the complete pipeline end-to-end:
- Discovery → Vetting → Crawling → Extraction → (optional) RAG Embedding

**Parameters:**
- Industry keyword
- Max discovery results
- Max pages per site
- Crawl depth
- Concurrency settings
- Optional auto-embed for RAG

**Features:**
- Real-time progress tracking
- Status updates at each stage
- Automatic resume from cached data

### 2. Individual Stages 🔧
Run each stage independently:

#### Discovery
- Discover new domains for a given industry
- View discovered domains

#### Vetting
- Run rule-based vetting
- Run local LLM vetting for unclear domains
- View YES/NO decisions

#### Crawling
- Crawl vetted domains
- Configure pages, depth, concurrency
- See crawl status (fully crawled, in progress, not started)

#### Extraction
- Extract company profiles and products
- Filter by industry
- View extraction progress

#### RAG Embedding
- Embed all domains or specific domain
- Force re-embed option
- Track embedding progress

### 3. RAG Query 💬
Query your embedded data:
- Natural language queries
- Filter by domain, brand
- Select collections to search
- Get LLM-generated answers
- View raw results with metadata

**Example Queries:**
- "What companies do we have?"
- "goalkeeper gloves under $50"
- "professional gloves from Aviata Sports"

### 4. Status & Monitoring 📊
Monitor pipeline status:
- Discovered domains count
- Vetted domains (YES/NO breakdown)
- Crawl status (fully crawled, in progress, not started)
- Total pages crawled
- Extraction status (domains extracted, products count)
- RAG status (domains embedded, chunk counts per collection)

## Usage Tips

1. **Start with Status & Monitoring** to see what data you already have
2. **Use Individual Stages** to run specific operations
3. **Full Pipeline** is best for fresh runs or complete workflows
4. **RAG Query** requires embeddings first - run RAG Embedding stage
5. All operations are resumable - the pipeline detects existing data

## Navigation

Use the sidebar to switch between pages:
- **Full Pipeline** - Complete workflow
- **Individual Stages** - Run specific stages
- **RAG Query** - Query interface
- **Status & Monitoring** - View current status

## Troubleshooting

### UI not loading
- Check that Streamlit is installed: `pip install streamlit`
- Ensure port 8501 is available
- Try `streamlit run streamlit_app.py --server.port 8502`

### Pipeline errors
- Check that all dependencies are installed
- Verify `OPENAI_API_KEY` is set (for extraction and RAG)
- Check console/logs for detailed error messages

### RAG query not working
- Ensure you've run RAG Embedding first
- Check Status & Monitoring page for RAG status
- Verify ChromaDB collections exist

### Progress not updating
- Some operations (like crawling) may take time
- Check browser console for errors
- Large operations may take several minutes

## Keyboard Shortcuts

- `R` - Rerun the app
- `C` - Clear cache
- `?` - Show keyboard shortcuts

## Advanced

### Custom Port
```bash
streamlit run streamlit_app.py --server.port 8502
```

### Share Network Access
```bash
streamlit run streamlit_app.py --server.address 0.0.0.0
```

### Theme Customization
Edit `.streamlit/config.toml` (created automatically on first run)

## Example Workflow

1. **Check Status** - See what data you have
2. **Run Discovery** - Discover new domains (if needed)
3. **Run Vetting** - Filter to relevant domains
4. **Run Crawling** - Crawl the vetted domains
5. **Run Extraction** - Extract structured data
6. **Run RAG Embedding** - Embed for queries
7. **Query RAG** - Ask questions about your data

Or simply use **Full Pipeline** to do steps 1-5 (or 1-6) automatically!

