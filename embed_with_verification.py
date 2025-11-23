"""
Embedding Stage with Optional Email Verification

This script embeds company data into the RAG system with optional email verification.

Usage:
    # Embed all companies (no verification)
    python embed_with_verification.py

    # Embed specific domains (no verification)
    python embed_with_verification.py --domains example.com company.com

    # Embed with email verification
    python embed_with_verification.py --verify-email

    # Embed with verification (skip SMTP for speed)
    python embed_with_verification.py --verify-email --no-smtp

    # Verify only (no embedding)
    python embed_with_verification.py --verify-only

This integrates:
1. Email verification (optional, before embedding)
2. RAG embedding
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.rag import embed_domain
from verify_emails import verify_company_emails


def embed_domains_with_verification(
    domains: Optional[List[str]] = None,
    verify_email: bool = False,
    check_smtp: bool = True,
    verify_only: bool = False
):
    """
    Embed domains into RAG with optional email verification.

    Args:
        domains: Optional list of specific domains to process
        verify_email: If True, verify emails before embedding
        check_smtp: If True, use SMTP verification (slower but more accurate)
        verify_only: If True, only verify, don't embed
    """
    print("\n" + "="*70)
    print("EMBEDDING WITH VERIFICATION")
    print("="*70)
    print(f"Email verification: {'ENABLED' if verify_email else 'DISABLED'}")
    if verify_email:
        print(f"SMTP verification: {'ENABLED' if check_smtp else 'DISABLED'}")
    print(f"Mode: {'VERIFY ONLY' if verify_only else 'VERIFY + EMBED'}")
    print("="*70 + "\n")

    # Step 1: Email Verification (if enabled)
    if verify_email:
        print("[STEP 1/2] Verifying emails...")
        print("-" * 70)

        verify_company_emails(
            check_smtp=check_smtp,
            domains=domains,
            force=False,  # Use cache
            dry_run=False,
            max_workers=5
        )

        print("\n✓ Email verification complete\n")

        if verify_only:
            print("✓ Verification complete (skipping embedding as requested)")
            return

    # Step 2: Embed into RAG
    if not verify_only:
        step_num = 2 if verify_email else 1
        print(f"[STEP {step_num}/{step_num}] Embedding into RAG...")
        print("-" * 70)

        # Get domains to embed
        if domains:
            domains_to_embed = domains
        else:
            # Get all domains from extracted_data/companies
            from pathlib import Path
            companies_dir = Path("extracted_data") / "companies"

            if not companies_dir.exists():
                print("✗ No extracted data found")
                return

            domains_to_embed = [
                d.name for d in companies_dir.iterdir()
                if d.is_dir() and (d / "profile.json").exists()
            ]

        if not domains_to_embed:
            print("✗ No domains to embed")
            return

        print(f"Embedding {len(domains_to_embed)} domains...")

        success_count = 0
        failed_count = 0

        for i, domain in enumerate(domains_to_embed, 1):
            try:
                print(f"\n[{i}/{len(domains_to_embed)}] Embedding {domain}...")

                # Handle both sync and async contexts
                try:
                    loop = asyncio.get_running_loop()
                    # Running loop exists, use thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, embed_domain(domain))
                        future.result()
                except RuntimeError:
                    # No running loop, safe to use asyncio.run()
                    asyncio.run(embed_domain(domain))

                print(f"  ✓ {domain} embedded successfully")
                success_count += 1

            except Exception as e:
                print(f"  ✗ {domain} failed: {e}")
                failed_count += 1

        # Summary
        print("\n" + "="*70)
        print("EMBEDDING COMPLETE")
        print("="*70)
        print(f"  ✓ Success: {success_count}/{len(domains_to_embed)}")
        if failed_count > 0:
            print(f"  ✗ Failed: {failed_count}/{len(domains_to_embed)}")
        print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Embed company data with optional email verification"
    )
    parser.add_argument(
        "--domains",
        nargs="*",
        help="Process only these domains (if not specified, processes all)"
    )
    parser.add_argument(
        "--verify-email",
        action="store_true",
        help="Verify emails before embedding"
    )
    parser.add_argument(
        "--no-smtp",
        action="store_true",
        help="Skip SMTP verification (faster but less accurate)"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify emails, don't embed (requires --verify-email)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.verify_only and not args.verify_email:
        print("✗ Error: --verify-only requires --verify-email")
        sys.exit(1)

    # Run embedding with verification
    embed_domains_with_verification(
        domains=args.domains,
        verify_email=args.verify_email,
        check_smtp=not args.no_smtp,
        verify_only=args.verify_only
    )


if __name__ == "__main__":
    main()
