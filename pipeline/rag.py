"""
RAG (Retrieval-Augmented Generation) module for product intelligence.

Implements:
- Semantic chunking of raw pages
- Embedding generation (OpenAI)
- ChromaDB vector storage
- Incremental updates with content hash tracking
- Hybrid search (raw pages + products + companies)
"""

import os
import json
import gzip
import hashlib
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings
import tiktoken
from openai import AsyncOpenAI
import dotenv

dotenv.load_dotenv()

# Configuration
RAG_DATA_DIR = "rag_data"
CHROMA_DB_DIR = os.path.join(RAG_DATA_DIR, "chroma_db")
EMBEDDED_TRACKER = os.path.join(RAG_DATA_DIR, ".embedded_domains.jsonl")
CHUNKS_DIR = os.path.join(RAG_DATA_DIR, "chunks")

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536  # for text-embedding-3-small

# Chunking parameters
CHUNK_SIZE_TOKENS = 800  # Target chunk size
CHUNK_OVERLAP_TOKENS = 150  # Overlap between chunks
MIN_CHUNK_SIZE = 100  # Minimum chunk size (tokens)

# Batch processing
BATCH_SIZE = 100  # Process embeddings in batches


def _ensure_dirs():
    """Create necessary directories"""
    os.makedirs(RAG_DATA_DIR, exist_ok=True)
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)


def _get_embedding_client() -> AsyncOpenAI:
    """Get OpenAI client for embeddings"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return AsyncOpenAI(api_key=api_key)


def _get_chroma_client() -> chromadb.ClientAPI:
    """Get ChromaDB client"""
    return chromadb.PersistentClient(
        path=CHROMA_DB_DIR,
        settings=Settings(anonymized_telemetry=False)
    )


def _get_tokenizer() -> tiktoken.Encoding:
    """Get tiktoken tokenizer for counting tokens"""
    return tiktoken.encoding_for_model("gpt-4")


def _sha256_text(text: str) -> str:
    """Calculate SHA256 hash of text"""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _count_tokens(text: str, tokenizer: tiktoken.Encoding) -> int:
    """Count tokens in text"""
    return len(tokenizer.encode(text))


def semantic_chunk_text(text: str, tokenizer: tiktoken.Encoding, 
                        chunk_size: int = CHUNK_SIZE_TOKENS,
                        overlap: int = CHUNK_OVERLAP_TOKENS) -> List[str]:
    """
    Chunk text semantically, respecting markdown headers and paragraphs.
    
    Strategy:
    1. Split by markdown headers (## ### ####)
    2. Split by double newlines (paragraphs)
    3. Combine into chunks of target size
    4. Add overlap between chunks
    """
    if not text.strip():
        return []
    
    # Split by markdown headers first (priority)
    sections = []
    current_section = []
    
    lines = text.split('\n')
    for line in lines:
        # Check if line is a markdown header
        if line.strip().startswith('#'):
            # Save current section if it has content
            if current_section:
                sections.append('\n'.join(current_section))
                current_section = []
        current_section.append(line)
    
    # Add last section
    if current_section:
        sections.append('\n'.join(current_section))
    
    # If no headers found, split by double newlines (paragraphs)
    if len(sections) == 1:
        sections = [s.strip() for s in text.split('\n\n') if s.strip()]
    
    # Now combine sections into chunks of target size
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for section in sections:
        section_tokens = _count_tokens(section, tokenizer)
        
        # If section itself is too large, split it further
        if section_tokens > chunk_size:
            # Split by sentences or single newlines
            sentences = section.replace('. ', '.\n').split('\n')
            for sentence in sentences:
                sent_tokens = _count_tokens(sentence, tokenizer)
                
                if current_tokens + sent_tokens > chunk_size and current_chunk:
                    # Finalize current chunk
                    chunk_text = '\n'.join(current_chunk)
                    chunks.append(chunk_text)
                    
                    # Start new chunk with overlap
                    if overlap > 0:
                        # Take last N tokens from previous chunk for overlap
                        overlap_text = _get_overlap_text(chunk_text, tokenizer, overlap)
                        current_chunk = [overlap_text, sentence] if overlap_text else [sentence]
                        current_tokens = _count_tokens('\n'.join(current_chunk), tokenizer)
                    else:
                        current_chunk = [sentence]
                        current_tokens = sent_tokens
                else:
                    current_chunk.append(sentence)
                    current_tokens += sent_tokens
        else:
            # Section fits or can be added
            if current_tokens + section_tokens > chunk_size and current_chunk:
                # Finalize current chunk
                chunk_text = '\n'.join(current_chunk)
                chunks.append(chunk_text)
                
                # Start new chunk with overlap
                if overlap > 0:
                    overlap_text = _get_overlap_text(chunk_text, tokenizer, overlap)
                    current_chunk = [overlap_text, section] if overlap_text else [section]
                    current_tokens = _count_tokens('\n'.join(current_chunk), tokenizer)
                else:
                    current_chunk = [section]
                    current_tokens = section_tokens
            else:
                current_chunk.append(section)
                current_tokens += section_tokens
    
    # Add remaining chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        if _count_tokens(chunk_text, tokenizer) >= MIN_CHUNK_SIZE:
            chunks.append(chunk_text)
    
    # Filter out chunks that are too small
    chunks = [c for c in chunks if _count_tokens(c, tokenizer) >= MIN_CHUNK_SIZE]
    
    return chunks


def _get_overlap_text(text: str, tokenizer: tiktoken.Encoding, target_tokens: int) -> str:
    """Get last N tokens from text for overlap"""
    tokens = tokenizer.encode(text)
    if len(tokens) <= target_tokens:
        return text
    # Take last target_tokens tokens
    overlap_tokens = tokens[-target_tokens:]
    return tokenizer.decode(overlap_tokens)


def prepare_raw_page_chunks(domain: str, crawled_data_dir: str = "crawled_data") -> List[Dict]:
    """
    Load and chunk raw pages for a domain.
    Returns list of chunk dictionaries ready for embedding.
    """
    host = domain.replace(':', '_')
    path = os.path.join(crawled_data_dir, "domains", f"{host}.jsonl.gz")
    
    if not os.path.exists(path):
        return []
    
    tokenizer = _get_tokenizer()
    chunks = []
    
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                try:
                    page = json.loads(line)
                    url = page.get("url", "")
                    title = page.get("title", "")
                    content = page.get("content", "")
                    depth = page.get("depth", 0)
                    
                    if not content:
                        continue
                    
                    # Chunk the content semantically
                    page_chunks = semantic_chunk_text(content, tokenizer)
                    
                    # Create chunk records
                    for chunk_idx, chunk_text in enumerate(page_chunks):
                        chunk_id = f"{domain}_page_{line_num}_chunk_{chunk_idx}"
                        content_hash = _sha256_text(chunk_text)
                        
                        chunk_record = {
                            "chunk_id": chunk_id,
                            "domain": domain,
                            "url": url,
                            "title": title,
                            "content": chunk_text,
                            "chunk_index": chunk_idx,
                            "total_chunks": len(page_chunks),
                            "depth": depth,
                            "content_hash": content_hash,
                            "tokens": _count_tokens(chunk_text, tokenizer),
                            "page_line": line_num
                        }
                        chunks.append(chunk_record)
                except Exception as e:
                    print(f"[{domain}] Error processing page {line_num}: {e}")
                    continue
    except FileNotFoundError:
        return []
    
    return chunks


def prepare_product_chunks(domain: str, extracted_data_dir: str = "extracted_data") -> List[Dict]:
    """
    Load and format products for a domain.
    Returns list of product dictionaries ready for embedding.
    """
    products_file = os.path.join(extracted_data_dir, "companies", domain, "products.jsonl")
    
    if not os.path.exists(products_file):
        return []
    
    products = []
    tokenizer = _get_tokenizer()
    
    try:
        with open(products_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    product = json.loads(line)
                    
                    # Format product as text for embedding
                    parts = []
                    if product.get("brand"):
                        parts.append(f"Brand: {product['brand']}")
                    if product.get("name"):
                        parts.append(f"Name: {product['name']}")
                    if product.get("category"):
                        parts.append(f"Category: {product['category']}")
                    if product.get("description"):
                        parts.append(f"Description: {product['description']}")
                    if product.get("specs"):
                        specs_str = json.dumps(product['specs'], ensure_ascii=False)
                        parts.append(f"Specifications: {specs_str}")
                    if product.get("price"):
                        parts.append(f"Price: {product['price']}")
                    if product.get("reviews"):
                        reviews_str = " | ".join(product['reviews'])
                        parts.append(f"Reviews: {reviews_str}")
                    
                    content = "\n".join(parts)
                    content_hash = _sha256_text(content)
                    
                    product_record = {
                        "chunk_id": product.get("product_id", f"{domain}_product_{len(products)}"),
                        "domain": domain,
                        "brand": product.get("brand", ""),
                        "name": product.get("name", ""),
                        "category": product.get("category", ""),
                        "price": product.get("price", ""),
                        "url": product.get("url", ""),
                        "content": content,
                        "content_hash": content_hash,
                        "tokens": _count_tokens(content, tokenizer),
                        "raw_product": product  # Keep full product data for metadata
                    }
                    products.append(product_record)
                except Exception as e:
                    print(f"[{domain}] Error processing product: {e}")
                    continue
    except FileNotFoundError:
        return []
    
    return products


def prepare_company_chunks(domain: str, extracted_data_dir: str = "extracted_data") -> List[Dict]:
    """
    Load and format company profile for a domain.
    Returns list with single company dictionary ready for embedding.
    """
    profile_file = os.path.join(extracted_data_dir, "companies", domain, "profile.json")
    
    if not os.path.exists(profile_file):
        return []
    
    try:
        with open(profile_file, 'r', encoding='utf-8') as f:
            profile = json.load(f)
        
        # Format company as text for embedding
        parts = []
        if profile.get("company"):
            parts.append(f"Company: {profile['company']}")
        if profile.get("description"):
            parts.append(f"Description: {profile['description']}")
        if profile.get("smykm_notes"):
            notes_str = "\n".join([f"- {note}" for note in profile['smykm_notes']])
            parts.append(f"Key Insights:\n{notes_str}")
        if profile.get("main_contacts"):
            contacts = profile['main_contacts']
            contact_parts = []
            if contacts.get("email"):
                contact_parts.append(f"Email: {', '.join(contacts['email'])}")
            if contacts.get("phone"):
                contact_parts.append(f"Phone: {', '.join(contacts['phone'])}")
            if contacts.get("address"):
                contact_parts.append(f"Address: {' | '.join(contacts['address'])}")
            if contact_parts:
                parts.append("Contact Information:\n" + "\n".join(contact_parts))
        
        content = "\n".join(parts)
        tokenizer = _get_tokenizer()
        content_hash = _sha256_text(content)
        
        company_record = {
            "chunk_id": f"{domain}_company",
            "domain": domain,
            "company": profile.get("company", ""),
            "content": content,
            "content_hash": content_hash,
            "tokens": _count_tokens(content, tokenizer),
            "raw_profile": profile  # Keep full profile for metadata
        }
        
        return [company_record]
    except Exception as e:
        print(f"[{domain}] Error processing company profile: {e}")
        return []


def _load_embedded_tracker() -> Dict[str, Dict]:
    """Load tracking of embedded domains and their content hashes"""
    tracker = {}
    if os.path.exists(EMBEDDED_TRACKER):
        try:
            with open(EMBEDDED_TRACKER, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        domain = record.get("domain")
                        if domain:
                            tracker[domain] = record
                    except Exception:
                        continue
        except Exception:
            pass
    return tracker


def _save_embedded_tracker(domain: str, hashes: Dict[str, str], chunk_counts: Dict[str, int]):
    """Save tracking record for embedded domain"""
    record = {
        "domain": domain,
        "embedded_at": datetime.utcnow().isoformat() + "Z",
        "content_hashes": hashes,
        "chunk_counts": chunk_counts
    }
    
    # Append to tracker file
    with open(EMBEDDED_TRACKER, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _get_existing_hashes(domain: str, collection_name: str, chroma_client: chromadb.ClientAPI) -> Dict[str, str]:
    """Get existing content hashes from ChromaDB for a domain"""
    try:
        collection = chroma_client.get_collection(collection_name)
        # Query all documents for this domain
        results = collection.get(
            where={"domain": domain},
            include=["metadatas"]
        )
        
        hashes = {}
        if results and results.get("metadatas"):
            for i, metadata in enumerate(results["metadatas"]):
                chunk_id = results["ids"][i] if results.get("ids") else f"chunk_{i}"
                content_hash = metadata.get("content_hash", "")
                if content_hash:
                    hashes[chunk_id] = content_hash
        return hashes
    except Exception:
        return {}


async def generate_embeddings_batch(texts: List[str], client: AsyncOpenAI) -> List[List[float]]:
    """Generate embeddings for a batch of texts"""
    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generating embeddings: {e}")
        raise


async def embed_domain(domain: str, force_reembed: bool = False,
                      crawled_data_dir: str = "crawled_data",
                      extracted_data_dir: str = "extracted_data") -> Dict:
    """
    Embed all data for a domain (raw pages + products + company).
    
    Returns:
        {
            "domain": domain,
            "raw_pages_chunks": count,
            "products_chunks": count,
            "companies_chunks": count,
            "new_embeddings": count,
            "skipped_embeddings": count
        }
    """
    _ensure_dirs()
    
    print(f"[{domain}] Preparing chunks...")
    
    # Prepare chunks
    raw_chunks = prepare_raw_page_chunks(domain, crawled_data_dir)
    product_chunks = prepare_product_chunks(domain, extracted_data_dir)
    company_chunks = prepare_company_chunks(domain, extracted_data_dir)
    
    print(f"[{domain}] Found {len(raw_chunks)} raw page chunks, {len(product_chunks)} products, {len(company_chunks)} company chunks")
    
    if not raw_chunks and not product_chunks and not company_chunks:
        print(f"[{domain}] No data to embed")
        return {
            "domain": domain,
            "raw_pages_chunks": 0,
            "products_chunks": 0,
            "companies_chunks": 0,
            "new_embeddings": 0,
            "skipped_embeddings": 0
        }
    
    # Get ChromaDB client
    chroma_client = _get_chroma_client()
    
    # Get existing hashes if not forcing re-embed
    existing_hashes = {}
    if not force_reembed:
        existing_hashes["raw_pages"] = set(_get_existing_hashes(domain, "raw_pages", chroma_client).values())
        existing_hashes["products"] = set(_get_existing_hashes(domain, "products", chroma_client).values())
        existing_hashes["companies"] = set(_get_existing_hashes(domain, "companies", chroma_client).values())
    
    # Get embedding client
    embedding_client = _get_embedding_client()
    
    stats = {
        "domain": domain,
        "raw_pages_chunks": len(raw_chunks),
        "products_chunks": len(product_chunks),
        "companies_chunks": len(company_chunks),
        "new_embeddings": 0,
        "skipped_embeddings": 0
    }
    
    # Embed raw pages
    if raw_chunks:
        await _embed_collection(
            chroma_client, embedding_client, "raw_pages", raw_chunks,
            existing_hashes.get("raw_pages", set()), force_reembed, stats
        )
    
    # Embed products
    if product_chunks:
        await _embed_collection(
            chroma_client, embedding_client, "products", product_chunks,
            existing_hashes.get("products", set()), force_reembed, stats
        )
    
    # Embed companies
    if company_chunks:
        await _embed_collection(
            chroma_client, embedding_client, "companies", company_chunks,
            existing_hashes.get("companies", set()), force_reembed, stats
        )
    
    # Save tracking
    all_hashes = {}
    all_hashes["raw_pages"] = {chunk["chunk_id"]: chunk["content_hash"] for chunk in raw_chunks}
    all_hashes["products"] = {chunk["chunk_id"]: chunk["content_hash"] for chunk in product_chunks}
    all_hashes["companies"] = {chunk["chunk_id"]: chunk["content_hash"] for chunk in company_chunks}
    
    chunk_counts = {
        "raw_pages": len(raw_chunks),
        "products": len(product_chunks),
        "companies": len(company_chunks)
    }
    
    _save_embedded_tracker(domain, all_hashes, chunk_counts)
    
    print(f"[{domain}] Embedding complete: {stats['new_embeddings']} new, {stats['skipped_embeddings']} skipped")
    
    return stats


async def _embed_collection(
    chroma_client: chromadb.ClientAPI,
    embedding_client: AsyncOpenAI,
    collection_name: str,
    chunks: List[Dict],
    existing_hashes: set,
    force_reembed: bool,
    stats: Dict
):
    """Embed chunks for a collection"""
    # Get or create collection
    try:
        collection = chroma_client.get_collection(collection_name)
    except Exception:
        collection = chroma_client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    # Filter chunks (skip if hash exists and not forcing re-embed)
    chunks_to_embed = []
    if force_reembed:
        chunks_to_embed = chunks
    else:
        for chunk in chunks:
            if chunk["content_hash"] not in existing_hashes:
                chunks_to_embed.append(chunk)
            else:
                stats["skipped_embeddings"] += 1
    
    if not chunks_to_embed:
        print(f"[{collection_name}] All chunks already embedded, skipping")
        return
    
    # Process in batches
    print(f"[{collection_name}] Embedding {len(chunks_to_embed)} chunks...")
    
    for i in range(0, len(chunks_to_embed), BATCH_SIZE):
        batch = chunks_to_embed[i:i + BATCH_SIZE]
        texts = [chunk["content"] for chunk in batch]
        
        # Generate embeddings
        embeddings = await generate_embeddings_batch(texts, embedding_client)
        
        # Prepare data for ChromaDB
        ids = [chunk["chunk_id"] for chunk in batch]
        metadatas = []
        documents = [chunk["content"] for chunk in batch]
        
        for chunk in batch:
            metadata = {
                "domain": chunk["domain"],
                "content_hash": chunk["content_hash"],
                "tokens": chunk["tokens"]
            }
            
            # Add collection-specific metadata
            if collection_name == "raw_pages":
                metadata.update({
                    "url": chunk.get("url", ""),
                    "title": chunk.get("title", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "total_chunks": chunk.get("total_chunks", 0),
                    "depth": chunk.get("depth", 0)
                })
            elif collection_name == "products":
                metadata.update({
                    "brand": chunk.get("brand", ""),
                    "name": chunk.get("name", ""),
                    "category": chunk.get("category", ""),
                    "price": chunk.get("price", ""),
                    "url": chunk.get("url", "")
                })
            elif collection_name == "companies":
                metadata.update({
                    "company": chunk.get("company", "")
                })
            
            metadatas.append(metadata)
        
        # Add to ChromaDB
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        
        stats["new_embeddings"] += len(batch)
        print(f"[{collection_name}] Embedded batch {i//BATCH_SIZE + 1}/{(len(chunks_to_embed) + BATCH_SIZE - 1)//BATCH_SIZE}")
    
    print(f"[{collection_name}] Complete: {len(chunks_to_embed)} chunks embedded")


def query_rag(query: str, collection_names: List[str] = None, 
               filters: Dict = None, top_k: int = 5) -> List[Dict]:
    """
    Query RAG system and return relevant chunks.
    
    Args:
        query: Search query
        collection_names: List of collections to search (default: all)
        filters: Metadata filters (e.g., {"domain": "example.com", "brand": "Nike"})
        top_k: Number of results per collection
    
    Returns:
        List of relevant chunks with metadata
    """
    _ensure_dirs()
    
    if collection_names is None:
        collection_names = ["raw_pages", "products", "companies"]
    
    chroma_client = _get_chroma_client()
    
    # Generate query embedding (sync)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[query]
        )
        query_embedding = response.data[0].embedding
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        return []
    
    results = []
    
    for collection_name in collection_names:
        try:
            collection = chroma_client.get_collection(collection_name)
            
            # Build where clause from filters
            where_clause = {}
            if filters:
                for key, value in filters.items():
                    if key in ["domain", "brand", "category", "company"]:
                        where_clause[key] = value
            
            # Query
            query_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause if where_clause else None
            )
            
            # Format results
            # ChromaDB returns nested lists when query_embeddings is a list: results[0] for first query
            if query_results and query_results.get("ids"):
                # Handle nested structure - ChromaDB returns list of lists for query_embeddings=[...]
                ids_list = query_results["ids"]
                if ids_list and isinstance(ids_list[0], list):
                    ids_list = ids_list[0]
                
                distances_list = query_results.get("distances", [])
                if distances_list and isinstance(distances_list[0], list):
                    distances_list = distances_list[0]
                
                documents_list = query_results.get("documents", [])
                if documents_list and isinstance(documents_list[0], list):
                    documents_list = documents_list[0]
                
                metadatas_list = query_results.get("metadatas", [])
                if metadatas_list and isinstance(metadatas_list[0], list):
                    metadatas_list = metadatas_list[0]
                
                for i in range(len(ids_list)):
                    result = {
                        "collection": collection_name,
                        "chunk_id": ids_list[i] if i < len(ids_list) else f"chunk_{i}",
                        "content": documents_list[i] if i < len(documents_list) else "",
                        "distance": distances_list[i] if i < len(distances_list) else None,
                        "metadata": metadatas_list[i] if i < len(metadatas_list) else {}
                    }
                    results.append(result)
        except Exception as e:
            print(f"Error querying {collection_name}: {e}")
            continue
    
    # Sort by distance (lower is better)
    def get_distance_value(result):
        distance = result.get("distance")
        if distance is None:
            return float('inf')
        # Handle both list and single value
        if isinstance(distance, list) and len(distance) > 0:
            return float(distance[0])
        elif isinstance(distance, (int, float)):
            return float(distance)
        else:
            return float('inf')
    
    results.sort(key=get_distance_value)
    
    return results[:top_k]


def get_rag_answer(query: str, collection_names: List[str] = None,
                   filters: Dict = None, top_k: int = 5,
                   use_openai: bool = True) -> str:
    """
    Get RAG answer using retrieved chunks and LLM generation.
    
    Args:
        query: User query
        collection_names: Collections to search
        filters: Metadata filters
        top_k: Number of chunks to retrieve
        use_openai: Whether to use OpenAI for answer generation
    
    Returns:
        Generated answer string
    """
    # Retrieve relevant chunks
    chunks = query_rag(query, collection_names, filters, top_k)
    
    if not chunks:
        return "No relevant information found."
    
    if not use_openai:
        # Return simple concatenation
        return "\n\n".join([f"[{c['collection']}] {c['content']}" for c in chunks])
    
    # Use OpenAI to generate answer
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source = f"[Source {i}: {chunk['collection']}]"
            if chunk['metadata'].get('domain'):
                source += f" Domain: {chunk['metadata']['domain']}"
            if chunk['metadata'].get('url'):
                source += f" URL: {chunk['metadata']['url']}"
            context_parts.append(f"{source}\n{chunk['content']}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        prompt = f"""Based on the following retrieved information, answer the user's question accurately and concisely.

Retrieved Information:
{context}

User Question: {query}

Answer:"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating answer: {e}")
        return "\n\n".join([f"[{c['collection']}] {c['content']}" for c in chunks])


if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) > 1:
        domain = sys.argv[1]
        asyncio.run(embed_domain(domain))
    else:
        print("Usage: python -m pipeline.rag <domain>")
        print("Example: python -m pipeline.rag aviatasports.com")

