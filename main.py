import argparse
import os
import json
import time
from pathlib import Path
from typing import List

from pipeline.discover import discover_domains
from pipeline.local_vet import vet_domains_locally
from pipeline.crawl import crawl_domains, get_crawl_status
from pipeline.deduplicate import check_before_crawl
from pipeline.extract import (
    extract_company_profile,
    extract_products,
    save_company_data,
    build_global_indexes,
    update_vetting_decision,
    delete_crawled_data,
    delete_extracted_data
)
from pipeline.rule_vet import rule_vet


def _write_jsonl(path: str, rows: List[dict]):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load_jsonl_set(path: str, key: str) -> set:
    s = set()
    if not os.path.exists(path):
        return s
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                v = obj.get(key)
                if isinstance(v, str):
                    s.add(v)
            except Exception:
                continue
    return s


def _load_discovered_domains() -> List[str]:
    cache_path = os.path.join("pipeline", "cache", "discovered_domains.jsonl")
    return sorted(list(_load_jsonl_set(cache_path, "domain")))


def _load_local_vet_decisions() -> dict:
    path = os.path.join("pipeline", "cache", "local_vet_results.jsonl")
    decisions = {}
    if not os.path.exists(path):
        return decisions
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                d = obj.get("domain")
                dec = obj.get("decision")
                if isinstance(d, str) and isinstance(dec, str):
                    decisions[d] = dec
            except Exception:
                continue
    return decisions


def run(industry: str, max_discovery: int, max_crawl_pages: int, max_depth: int, skip_discovery: bool, concurrency: int, max_parallel_domains: int):
    # Optionally run discovery, then always load from cache for resumability
    if not skip_discovery:
        print(f"[0/4] Discovering domains for: {industry}")
        _ = discover_domains(industry, max_results=max_discovery)
    discovered = _load_discovered_domains()
    print(f"[1/4] Discovered domains in cache: {len(discovered)}")

    print("[2/4] Rule-based vetting using soft-vet cache and HTML snippets")
    existing = _load_local_vet_decisions()
    pending = [d for d in discovered if d not in existing]
    auto_yes, auto_no, unclear = rule_vet(pending)
    # Persist auto decisions immediately for crash-safety
    if auto_yes:
        _write_jsonl(os.path.join("pipeline", "cache", "local_vet_results.jsonl"),
                     [{"domain": d, "decision": "YES", "ts": int(time.time())} for d in sorted(list(auto_yes))])
    if auto_no:
        _write_jsonl(os.path.join("pipeline", "cache", "local_vet_results.jsonl"),
                     [{"domain": d, "decision": "NO", "ts": int(time.time())} for d in sorted(list(auto_no))])
    print(f"  → Auto-YES: {len(auto_yes)} | Auto-NO: {len(auto_no)} | Unclear: {len(unclear)}")

    print("[2.5/4] Local LLM vet only for unclear domains (YES/NO)")
    local_results = vet_domains_locally(sorted([d for d in unclear if d not in existing]), model="mistral")
    local_yes = {r["domain"] for r in local_results if r.get("decision") == "YES"}
    local_no = {r["domain"] for r in local_results if r.get("decision") != "YES"}

    # Recompute final sets from file for full resumability
    final_map = _load_local_vet_decisions()
    yes_domains = sorted([d for d, dec in final_map.items() if dec == "YES"])
    rejected = sorted([d for d, dec in final_map.items() if dec != "YES"])
    print(f"  → Final YES: {len(yes_domains)} | Final NO: {len(rejected)}")

    if rejected:
        _write_jsonl("bad_output.jsonl", [{"url": d, "raw": "NO"} for d in rejected])

    
    # Deduplicate before crawling
    print("[3/6] Deduplicating domains...")
    to_crawl = []
    duplicates_found = 0

    for domain in yes_domains:
        dedup_result = check_before_crawl(
            domain,
            pattern_threshold=0.20,  # 20% pattern match triggers homepage check
            duplicate_threshold=0.70,  # 70% total score marks as duplicate
            extraction_method="regex"  # Use "openai" for better accuracy (~$0.0001/domain)
        )

        if dedup_result["action"] == "skip":
            # Mark as duplicate in vetting cache
            update_vetting_decision(domain, f"DUPLICATE:{dedup_result['primary_domain']}")
            duplicates_found += 1
        else:
            to_crawl.append(domain)

    if duplicates_found > 0:
        print(f"  → Skipped {duplicates_found} duplicate domains")

    # Get crawl status for unique domains
    print("[3.1/6] Checking crawl status for unique domains...")
    crawl_status = get_crawl_status(to_crawl, output_dir="crawled_data")
    fully_done = [d for d, s in crawl_status.items() if s["fully_crawled"]]
    in_progress = [d for d, s in crawl_status.items() if s["in_progress"]]
    not_started = [d for d in to_crawl if d not in fully_done and d not in in_progress]

    print(f"  → Total unique domains: {len(to_crawl)}")
    print(f"  → ✓ Fully crawled: {len(fully_done)}")
    print(f"  → ⏸ In-progress (will resume): {len(in_progress)}")
    print(f"  → ○ Not started: {len(not_started)}")
    print(f"  → Total to crawl/resume: {len(in_progress) + len(not_started)}")

    to_crawl_count = len(in_progress) + len(not_started)
    if to_crawl_count > 0:
        print(f"\n[3.5/6] Crawling {to_crawl_count} sites ({len(not_started)} new, {len(in_progress)} resuming)")
        print(f"  → Parallel domains: {max_parallel_domains} domains at once")
        print(f"  → Page concurrency: {concurrency} pages per domain")
        print(f"  → Total concurrent requests: {max_parallel_domains * concurrency}")
        crawl_domains(to_crawl, output_dir="crawled_data", max_pages=max_crawl_pages,
                     max_depth=max_depth, skip_crawled=True, concurrency=concurrency,
                     max_parallel_domains=max_parallel_domains)
    else:
        print("  → All domains already crawled!")


    print(f"\n[4/6] Extracting company profiles for {len(yes_domains)} domains")
    extracted_count = 0
    for domain in yes_domains:
        # Check if already extracted to avoid wasting tokens
        company_file = os.path.join("extracted_data", "companies", domain, "profile.json")
        if os.path.exists(company_file):
            print(f"  [SKIP] {domain} - already extracted")
            continue

        print(f"  -> Extracting {domain}...")
        company_profile = extract_company_profile(domain, output_dir="crawled_data")
        if not company_profile:
            print(f"  [SKIP] {domain} - no company profile extracted")
            continue

        print(f"[5/6] Extracting products for {domain} (filtering for: {industry})")
        products = extract_products(domain, output_dir="crawled_data", industry=industry)

        # Check if company has products
        if len(products) == 0:
            print(f"  [REJECT] {domain} - no products found, marking as NO and cleaning up")
            update_vetting_decision(domain, "NO")
            delete_crawled_data(domain, output_dir="crawled_data")
            delete_extracted_data(domain, base_dir="extracted_data")
            continue

        # Save per-domain data
        save_company_data(domain, company_profile, products, base_dir="extracted_data")
        extracted_count += 1
    
    if extracted_count > 0:
        print("[6/6] Building global indexes")
        build_global_indexes(base_dir="extracted_data")
    else:
        print("[6/6] No new extractions - skipping index rebuild")

    # Optional: Embed domains for RAG (uncomment to enable)
    print("\n[7/7] Embedding domains for RAG...")
    from pipeline.rag import embed_domain
    import asyncio
    for domain in yes_domains:
        try:
            asyncio.run(embed_domain(domain))
        except Exception as e:
            print(f"  [SKIP] {domain} - RAG embedding error: {e}")

    print("Done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--industry", default="goalkeeper gloves", help="Target industry to discover ecommerce sites for")
    ap.add_argument("--max-discovery", type=int, default=100, help="Max results to fetch from search")
    ap.add_argument("--max-crawl-pages", type=int, default=200, help="Max pages per site to crawl")
    ap.add_argument("--depth", type=int, default=2, help="Max crawl depth per site (e.g., 3 for home→shop→products)")
    ap.add_argument("--concurrency", type=int, default=5, help="Pages to fetch in parallel per domain (3-10 recommended)")
    ap.add_argument("--max-parallel-domains", type=int, default=3, help="Max domains to crawl simultaneously (1-5 recommended)")
    ap.add_argument("--skip-discovery", action="store_true", help="Skip running discovery; use cached discovered domains")
    args = ap.parse_args()

    run(args.industry, args.max_discovery, args.max_crawl_pages, args.depth, args.skip_discovery, args.concurrency, args.max_parallel_domains)
