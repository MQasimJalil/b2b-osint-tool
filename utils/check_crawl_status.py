"""
Utility to check crawl status and optionally clean up incomplete crawls.

Usage:
    python utils/check_crawl_status.py              # Show status
    python utils/check_crawl_status.py --reset-incomplete  # Delete incomplete crawl data
"""
import os
import sys
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline.crawl import get_crawl_status, _paths


def main():
    parser = argparse.ArgumentParser(description="Check crawl status")
    parser.add_argument("--reset-incomplete", action="store_true",
                       help="Delete data for incomplete crawls (keeps visited/hashes for resume)")
    parser.add_argument("--reset-all", action="store_true",
                       help="Delete ALL crawl data for incomplete crawls (full restart)")
    args = parser.parse_args()
    
    # Get all domains from discovered_domains.jsonl
    import json
    domains = []
    if os.path.exists("pipeline/cache/discovered_domains.jsonl"):
        with open("pipeline/cache/discovered_domains.jsonl", "r") as f:
            for line in f:
                data = json.loads(line)
                domains.append(data["domain"])
    
    if not domains:
        print("No domains found in pipeline/cache/discovered_domains.jsonl")
        return
    
    print(f"Checking status for {len(domains)} domains...\n")
    
    status = get_crawl_status(domains, output_dir="crawled_data")
    
    fully_done = []
    in_progress = []
    not_started = []
    
    for domain, info in status.items():
        if info["fully_crawled"]:
            fully_done.append((domain, info))
        elif info["in_progress"]:
            in_progress.append((domain, info))
        else:
            not_started.append((domain, info))
    
    # Print summary
    print("="*80)
    print(f"✓ FULLY CRAWLED: {len(fully_done)}")
    print("="*80)
    for domain, info in sorted(fully_done):
        print(f"  {domain}: {info['pages']} pages, {info['visited_urls']} URLs visited")
    
    print("\n" + "="*80)
    print(f"⏸ IN-PROGRESS (interrupted): {len(in_progress)}")
    print("="*80)
    for domain, info in sorted(in_progress):
        print(f"  {domain}: {info['pages']} pages, {info['visited_urls']} URLs visited")
    
    print("\n" + "="*80)
    print(f"○ NOT STARTED: {len(not_started)}")
    print("="*80)
    for domain, info in sorted(not_started):
        print(f"  {domain}")
    
    # Handle reset options
    if args.reset_incomplete and in_progress:
        print(f"\n⚠️  Resetting {len(in_progress)} incomplete crawls (keeping visited/hashes)...")
        for domain, _ in in_progress:
            base_url = f"https://{domain}"
            out_path, visited_path, hashes_path, complete_path = _paths("crawled_data", base_url)
            
            # Delete output file only
            if os.path.exists(out_path):
                os.remove(out_path)
                print(f"  Deleted: {out_path}")
        
        print("✓ Reset complete. Crawl will resume from visited URLs on next run.")
    
    elif args.reset_all and in_progress:
        print(f"\n⚠️  FULL RESET: Deleting ALL data for {len(in_progress)} incomplete crawls...")
        for domain, _ in in_progress:
            base_url = f"https://{domain}"
            out_path, visited_path, hashes_path, complete_path = _paths("crawled_data", base_url)
            
            # Delete everything
            for path in [out_path, visited_path, hashes_path]:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"  Deleted: {path}")
        
        print("✓ Full reset complete. Crawl will start fresh on next run.")


if __name__ == "__main__":
    main()

