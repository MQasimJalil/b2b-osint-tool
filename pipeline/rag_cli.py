"""
CLI tool for RAG operations:
- Embed all domains
- Query RAG system
- Update embeddings incrementally
"""

import sys
import os
import argparse
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.rag import (
    embed_domain, query_rag, get_rag_answer,
    _load_embedded_tracker, _get_chroma_client
)
from pipeline.crawl import get_crawl_status
from tqdm import tqdm


def embed_all_domains(crawled_data_dir: str = "crawled_data",
                     extracted_data_dir: str = "extracted_data",
                     force_reembed: bool = False):
    """Embed all domains that have been crawled and extracted"""
    # Get list of domains that are fully crawled
    from pipeline.crawl import get_crawl_status
    
    # Get all domains from crawled_data
    crawled_domains = []
    domains_dir = os.path.join(crawled_data_dir, "domains")
    if os.path.exists(domains_dir):
        for file in os.listdir(domains_dir):
            if file.endswith(".jsonl.gz"):
                domain = file.replace(".jsonl.gz", "").replace("_", ":")
                crawled_domains.append(domain)
    
    # Filter to only fully crawled domains
    if crawled_domains:
        status = get_crawl_status(crawled_domains, crawled_data_dir)
        fully_crawled = [d for d, s in status.items() if s.get("fully_crawled")]
    else:
        fully_crawled = []
    
    # Also check extracted_data for domains with profiles
    extracted_domains = []
    companies_dir = os.path.join(extracted_data_dir, "companies")
    if os.path.exists(companies_dir):
        for domain in os.listdir(companies_dir):
            profile_file = os.path.join(companies_dir, domain, "profile.json")
            if os.path.exists(profile_file):
                extracted_domains.append(domain)
    
    # Combine and deduplicate
    all_domains = list(set(fully_crawled + extracted_domains))
    
    if not all_domains:
        print("No domains found to embed")
        return
    
    print(f"Found {len(all_domains)} domains to embed")
    
    # Track embedded domains
    tracker = _load_embedded_tracker()
    embedded_domains = set(tracker.keys())
    
    # Filter to new domains if not forcing re-embed
    if not force_reembed:
        domains_to_embed = [d for d in all_domains if d not in embedded_domains]
        print(f"{len(domains_to_embed)} new domains, {len(embedded_domains)} already embedded")
    else:
        domains_to_embed = all_domains
        print(f"Re-embedding all {len(domains_to_embed)} domains")
    
    if not domains_to_embed:
        print("All domains already embedded")
        return
    
    # Embed each domain
    stats = []
    for domain in tqdm(domains_to_embed, desc="Embedding domains"):
        try:
            result = asyncio.run(embed_domain(domain, force_reembed, crawled_data_dir, extracted_data_dir))
            stats.append(result)
        except Exception as e:
            print(f"\n[{domain}] Error: {e}")
            continue
    
    # Print summary
    total_new = sum(s.get("new_embeddings", 0) for s in stats)
    total_skipped = sum(s.get("skipped_embeddings", 0) for s in stats)
    total_raw = sum(s.get("raw_pages_chunks", 0) for s in stats)
    total_products = sum(s.get("products_chunks", 0) for s in stats)
    total_companies = sum(s.get("companies_chunks", 0) for s in stats)
    
    print(f"\n=== Embedding Summary ===")
    print(f"Domains processed: {len(stats)}")
    print(f"Raw page chunks: {total_raw}")
    print(f"Product chunks: {total_products}")
    print(f"Company chunks: {total_companies}")
    print(f"New embeddings: {total_new}")
    print(f"Skipped (already embedded): {total_skipped}")


def query_cli(query: str, collections: str = None, domain: str = None,
             brand: str = None, top_k: int = 5, use_llm: bool = True):
    """Query RAG system via CLI"""
    collection_names = None
    if collections:
        collection_names = [c.strip() for c in collections.split(",")]
    
    filters = {}
    if domain:
        filters["domain"] = domain
    if brand:
        filters["brand"] = brand
    
    print(f"Query: {query}")
    if filters:
        print(f"Filters: {filters}")
    print(f"Collections: {collection_names or 'all'}")
    print(f"Top K: {top_k}")
    print()
    
    if use_llm:
        answer = get_rag_answer(query, collection_names, filters, top_k, use_openai=True)
        print("=== Answer ===")
        print(answer)
        print()
    
    # Also show raw results
    results = query_rag(query, collection_names, filters, top_k)
    print(f"=== Top {len(results)} Results ===")
    for i, result in enumerate(results, 1):
        distance = result.get('distance')
        if distance is not None:
            # Handle both list and single value
            if isinstance(distance, list) and len(distance) > 0:
                distance_str = f"{distance[0]:.4f}"
            elif isinstance(distance, (int, float)):
                distance_str = f"{distance:.4f}"
            else:
                distance_str = "N/A"
        else:
            distance_str = "N/A"
        
        print(f"\n[{i}] {result['collection']} (distance: {distance_str})")
        print(f"Domain: {result['metadata'].get('domain', 'N/A')}")
        if result['metadata'].get('url'):
            print(f"URL: {result['metadata']['url']}")
        if result['metadata'].get('brand'):
            print(f"Brand: {result['metadata']['brand']}")
        if result['metadata'].get('name'):
            print(f"Name: {result['metadata']['name']}")
        if result.get('content'):
            content_preview = result['content'][:200] if len(result['content']) > 200 else result['content']
            print(f"Content preview: {content_preview}...")


def main():
    parser = argparse.ArgumentParser(description="RAG CLI for B2B OSINT Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Embed command
    embed_parser = subparsers.add_parser("embed", help="Embed domains")
    embed_parser.add_argument("--domain", help="Embed specific domain (default: all)")
    embed_parser.add_argument("--force", action="store_true", help="Force re-embedding")
    embed_parser.add_argument("--crawled-dir", default="crawled_data", help="Crawled data directory")
    embed_parser.add_argument("--extracted-dir", default="extracted_data", help="Extracted data directory")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query RAG system")
    query_parser.add_argument("query", help="Search query")
    query_parser.add_argument("--collections", help="Comma-separated collections (raw_pages,products,companies)")
    query_parser.add_argument("--domain", help="Filter by domain")
    query_parser.add_argument("--brand", help="Filter by brand")
    query_parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    query_parser.add_argument("--no-llm", action="store_true", help="Don't use LLM, just return raw results")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show embedding statistics")
    
    args = parser.parse_args()
    
    if args.command == "embed":
        if args.domain:
            asyncio.run(embed_domain(args.domain, args.force, args.crawled_dir, args.extracted_dir))
        else:
            embed_all_domains(args.crawled_dir, args.extracted_dir, args.force)
    elif args.command == "query":
        query_cli(args.query, args.collections, args.domain, args.brand, args.top_k, not args.no_llm)
    elif args.command == "stats":
        tracker = _load_embedded_tracker()
        chroma_client = _get_chroma_client()
        
        print(f"=== Embedding Statistics ===")
        print(f"Domains embedded: {len(tracker)}")
        
        # Get collection stats
        for collection_name in ["raw_pages", "products", "companies"]:
            try:
                collection = chroma_client.get_collection(collection_name)
                count = collection.count()
                print(f"{collection_name}: {count} chunks")
            except Exception:
                print(f"{collection_name}: 0 chunks (collection not created)")
    else:
        parser.print_help()


if __name__ == "__main__":
    import os
    main()

