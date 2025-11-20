import os
import sys
import json
import asyncio
import argparse
from typing import List, Set, Dict
from pipeline.crawl import crawl_domains, get_crawl_status

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
from pipeline.extract import (
    extract_company_profile,
    extract_products,
    save_company_data,
    build_global_indexes,
    update_vetting_decision,
    delete_crawled_data,
    delete_extracted_data
)
from pipeline.rag import embed_domain
from pipeline.gemini_agent import GeminiAgent

def get_existing_drafts(output_file: str = "email_drafts.jsonl") -> Set[str]:
    """
    Get set of domains that already have drafts saved.
    """
    existing_domains = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            draft = json.loads(line)
                            if "domain" in draft:
                                existing_domains.add(draft["domain"])
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"  [WARN] Could not read existing drafts: {e}")
    return existing_domains

def get_embedded_domains(rag_data_dir: str = "rag_data") -> List[str]:
    """
    Get list of all embedded domains from .embedded_domains.jsonl
    """
    embedded_file = os.path.join(rag_data_dir, ".embedded_domains.jsonl")
    domains = []

    if not os.path.exists(embedded_file):
        print(f"  [WARN] No embedded domains file found at {embedded_file}")
        return domains

    try:
        with open(embedded_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if "domain" in entry:
                            domains.append(entry["domain"])
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"  [ERROR] Could not read embedded domains: {e}")

    return domains

def is_valid_email_data(email_data: Dict) -> bool:
    """
    Check if email data is valid (not an error response).
    Returns False if:
    - subject_lines is empty
    - email_body contains error message
    - 'error' key exists in the data
    """
    # Check if error key exists
    if "error" in email_data:
        return False

    # Check if subject_lines is empty
    if not email_data.get("subject_lines") or len(email_data.get("subject_lines", [])) == 0:
        return False

    # Check if email_body contains error indicators
    email_body = email_data.get("email_body", "")
    error_indicators = [
        "Error generating email",
        "error after",
        "attempts failed",
        "[ERROR]",
        "Exception:",
        "Traceback"
    ]

    for indicator in error_indicators:
        if indicator.lower() in email_body.lower():
            return False

    return True

def ensure_data_availability(domains: List[str]):
    """
    Ensure data is crawled, extracted, and embedded for the given domains.
    """
    print(f"\n[1/3] Checking data availability for {len(domains)} domains...")
    
    # 1. Crawl
    crawl_status = get_crawl_status(domains, output_dir="crawled_data")
    to_crawl = [d for d, s in crawl_status.items() if not s["fully_crawled"]]
    
    if to_crawl:
        print(f"  -> Crawling {len(to_crawl)} domains: {to_crawl}")
        crawl_domains(to_crawl, output_dir="crawled_data", max_pages=100, concurrency=5)
    else:
        print("  -> All domains already crawled.")

    # 2. Extract
    print(f"\n[2/3] Ensuring extraction...")
    extracted_count = 0
    for domain in domains:
        # Check if already extracted (simple check: if folder exists in extracted_data/companies)
        company_file = os.path.join("extracted_data", "companies", domain, "profile.json")
        if not os.path.exists(company_file):
            print(f"  -> Extracting {domain}...")
            profile = extract_company_profile(domain, output_dir="crawled_data")
            if profile:
                products = extract_products(domain, output_dir="crawled_data")

                # Check if company has products
                if len(products) == 0:
                    print(f"  [REJECT] {domain} - no products found, marking as NO and cleaning up")
                    update_vetting_decision(domain, "NO")
                    delete_crawled_data(domain, output_dir="crawled_data")
                    delete_extracted_data(domain, base_dir="extracted_data")
                    continue

                save_company_data(domain, profile, products, base_dir="extracted_data")
                extracted_count += 1
        else:
            print(f"  -> {domain} already extracted.")
            
    if extracted_count > 0:
        print("  -> Rebuilding global indexes...")
        build_global_indexes(base_dir="extracted_data")

    # 3. Embed (RAG)
    print(f"\n[3/3] Ensuring RAG embeddings...")
    for domain in domains:
        try:
            # We can't easily check if it's *fully* embedded without loading DB,
            # but embed_domain handles incremental updates via hashes.
            # Handle both sync and async contexts
            try:
                # Check if there's already a running event loop
                loop = asyncio.get_running_loop()
                # If we're here, there's a running loop
                # Run in a separate thread with its own event loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, embed_domain(domain))
                    future.result()  # Wait for completion
            except RuntimeError:
                # No running loop, safe to use asyncio.run()
                asyncio.run(embed_domain(domain))
        except Exception as e:
            print(f"  [ERROR] Embedding {domain}: {e}")

def run_agentic_flow(domains: List[str]):
    """
    Main flow: Ensure Data -> Run Agent -> Save Drafts
    """
    # 1. Prepare Data
    ensure_data_availability(domains)
    
    # 2. Run Agent
    print("\n[4/4] Running Gemini Agent...")
    agent = GeminiAgent(model_name="gemini-2.5-pro")
    
    drafts = []
    failed_domains = []

    for domain in domains:
        print(f"\n--- Processing {domain} ---")
        email_data = agent.run(domain)

        # Validate email data before displaying/saving
        if not is_valid_email_data(email_data):
            print(f"\n[SKIP] {domain} - Email generation failed or returned error")
            print(f"  Reason: {email_data.get('error', 'Invalid email data')}")
            failed_domains.append(domain)
            continue

        # Display clean output
        print(f"\n[DRAFT EMAIL for {domain}]")
        print(f"\nSubject Lines ({len(email_data['subject_lines'])}):")
        for i, subject in enumerate(email_data['subject_lines'], 1):
            print(f"  {i}. {subject}")

        print(f"\nEmail Body:\n{email_data['email_body']}\n")

        # Save structured data only if valid
        drafts.append(email_data)

    # 3. Save Results
    output_file = "email_drafts.jsonl"
    if drafts:
        with open(output_file, "a", encoding="utf-8") as f:
            for draft in drafts:
                f.write(json.dumps(draft, ensure_ascii=False) + "\n")
        print(f"\n✅ Done! {len(drafts)} draft(s) saved to {output_file}")
    else:
        print(f"\n⚠️  No valid drafts to save")

    # Show summary
    if failed_domains:
        print(f"\n❌ Failed domains ({len(failed_domains)}):")
        for domain in failed_domains:
            print(f"  - {domain}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Agentic Email Flow",
        epilog="Examples:\n"
               "  python run_agentic_flow.py bravegk.com ab1gk.com     # Process specific domains\n"
               "  python run_agentic_flow.py --all                      # Process all embedded domains without drafts",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "domains",
        nargs="*",
        help="List of domains to process (e.g., bravegk.com)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all embedded domains that don't have drafts yet"
    )
    args = parser.parse_args()

    # Determine which domains to process
    if args.all:
        print("📋 Loading embedded domains...")
        all_embedded = get_embedded_domains()
        print(f"  Found {len(all_embedded)} embedded domains")

        print("\n📄 Checking existing drafts...")
        existing_drafts = get_existing_drafts()
        print(f"  Found {len(existing_drafts)} existing drafts")

        # Filter out domains that already have drafts
        domains_to_process = [d for d in all_embedded if d not in existing_drafts]

        if not domains_to_process:
            print("\n✅ All embedded domains already have drafts!")
            sys.exit(0)

        print(f"\n🎯 {len(domains_to_process)} domain(s) need drafts:")
        for domain in domains_to_process[:10]:  # Show first 10
            print(f"  - {domain}")
        if len(domains_to_process) > 10:
            print(f"  ... and {len(domains_to_process) - 10} more")

        run_agentic_flow(domains_to_process)

    elif args.domains:
        # Process specific domains provided as arguments
        run_agentic_flow(args.domains)

    else:
        parser.print_help()
        print("\n❌ Error: Please provide domains or use --all flag")
        sys.exit(1)
