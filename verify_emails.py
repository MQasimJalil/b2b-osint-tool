"""
Standalone Email Verification Stage

Verifies all extracted contact emails and updates company profiles with verification results.

Usage:
    # Verify all companies
    python verify_emails.py

    # Verify specific domains
    python verify_emails.py --domains example.com company.com

    # Skip SMTP verification (faster but less accurate)
    python verify_emails.py --no-smtp

    # Force re-verification (ignore cache)
    python verify_emails.py --force

    # Dry run (don't update files)
    python verify_emails.py --dry-run

This script:
1. Reads all company profiles from extracted_data/companies/*/profile.json
2. Verifies each email address using the email_verifier module
3. Updates profile.json with verification results
4. Generates a verification report
5. Marks invalid emails so RAG and drafts can filter them out
"""

import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from pipeline.email_verifier import (
    verify_email,
    verify_email_batch,
    is_blacklisted,
    print_verification_report,
    ValidationResult
)


# Paths
BASE_DIR = Path(__file__).parent
EXTRACTED_DATA_DIR = BASE_DIR / "extracted_data" / "companies"
VERIFICATION_REPORT_FILE = BASE_DIR / "email_verification_report.jsonl"


def get_all_company_profiles(domains: Optional[List[str]] = None) -> List[Dict]:
    """
    Load all company profiles from extracted_data/companies.

    Args:
        domains: Optional list of specific domains to load

    Returns:
        List of dicts with:
            - domain: str
            - profile_path: Path
            - profile: Dict (profile.json content)
    """
    if not EXTRACTED_DATA_DIR.exists():
        print(f"✗ No extracted data found at {EXTRACTED_DATA_DIR}")
        return []

    profiles = []

    for company_dir in EXTRACTED_DATA_DIR.iterdir():
        if not company_dir.is_dir():
            continue

        domain = company_dir.name

        # Filter by domains if specified
        if domains and domain not in domains:
            continue

        profile_path = company_dir / "profile.json"

        if not profile_path.exists():
            print(f"  [WARN] No profile.json found for {domain}")
            continue

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)

            profiles.append({
                "domain": domain,
                "profile_path": profile_path,
                "profile": profile
            })
        except Exception as e:
            print(f"  [ERROR] Failed to load profile for {domain}: {e}")

    return profiles


def extract_emails_from_profile(profile: Dict) -> List[str]:
    """
    Extract email addresses from profile.

    Args:
        profile: Profile dict

    Returns:
        List of email addresses
    """
    emails = []

    # Get emails from main_contacts
    main_contacts = profile.get("main_contacts", {}) or {}
    email_list = main_contacts.get("email", [])

    if isinstance(email_list, list):
        emails.extend(email_list)
    elif isinstance(email_list, str):
        emails.append(email_list)

    return [e.strip().lower() for e in emails if e]


def update_profile_with_verification(
    profile_path: Path,
    verification_results: Dict[str, ValidationResult],
    dry_run: bool = False
) -> bool:
    """
    Update profile.json with email verification results.

    Adds/updates 'email_verification' field in main_contacts:
    {
        "main_contacts": {
            "email": ["contact@example.com"],
            "email_verification": {
                "contact@example.com": {
                    "is_valid": true,
                    "reason": null,
                    "verified_at": "2025-01-21T...",
                    "checks": {...}
                }
            }
        }
    }

    Args:
        profile_path: Path to profile.json
        verification_results: Dict of email -> ValidationResult
        dry_run: If True, don't actually write file

    Returns:
        True if successful
    """
    try:
        # Load profile
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)

        # Initialize email_verification field
        if "main_contacts" not in profile:
            profile["main_contacts"] = {}

        if "email_verification" not in profile["main_contacts"]:
            profile["main_contacts"]["email_verification"] = {}

        # Update verification results
        for email, result in verification_results.items():
            profile["main_contacts"]["email_verification"][email] = {
                "is_valid": result.is_valid,
                "reason": result.reason,
                "verified_at": result.verified_at,
                "checks": result.checks,
                "smtp_response": result.smtp_response if hasattr(result, 'smtp_response') else None
            }

        if dry_run:
            print(f"  [DRY RUN] Would update: {profile_path}")
            return True

        # Write updated profile
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print(f"  [ERROR] Failed to update {profile_path}: {e}")
        return False


def log_verification_result(
    domain: str,
    email: str,
    result: ValidationResult,
    report_file: Path = VERIFICATION_REPORT_FILE
):
    """Log verification result to report file."""
    entry = {
        "domain": domain,
        "email": email,
        "is_valid": result.is_valid,
        "reason": result.reason,
        "checks": result.checks,
        "verified_at": result.verified_at,
        "verification_time": result.verification_time
    }

    with open(report_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def verify_company_emails(
    check_smtp: bool = True,
    domains: Optional[List[str]] = None,
    force: bool = False,
    dry_run: bool = False,
    max_workers: int = 5
):
    """
    Main verification workflow.

    Args:
        check_smtp: Perform SMTP verification
        domains: Optional list of specific domains to verify
        force: Force re-verification (ignore cache)
        dry_run: Don't update files
        max_workers: Parallel workers for verification
    """
    print("\n" + "="*70)
    print("EMAIL VERIFICATION STAGE")
    print("="*70)
    print(f"SMTP Verification: {'ENABLED' if check_smtp else 'DISABLED'}")
    print(f"Force re-verification: {'YES' if force else 'NO'}")
    print(f"Dry run: {'YES' if dry_run else 'NO'}")
    print("="*70 + "\n")

    # Load all company profiles
    print("Loading company profiles...")
    profiles = get_all_company_profiles(domains)

    if not profiles:
        print("✗ No company profiles found")
        return

    print(f"Loaded {len(profiles)} company profiles\n")

    # Collect all emails to verify
    all_emails = []
    email_to_domains = {}  # Map email -> list of domains

    for item in profiles:
        domain = item["domain"]
        emails = extract_emails_from_profile(item["profile"])

        if not emails:
            print(f"[SKIP] {domain} - No email addresses found")
            continue

        for email in emails:
            all_emails.append(email)
            if email not in email_to_domains:
                email_to_domains[email] = []
            email_to_domains[email].append(domain)

    if not all_emails:
        print("✗ No email addresses found in any profile")
        return

    # Remove duplicates
    unique_emails = list(set(all_emails))

    print(f"Found {len(all_emails)} email addresses ({len(unique_emails)} unique)")
    print("-" * 70 + "\n")

    # Verify emails
    print("Verifying emails...")
    print("-" * 70)

    results = verify_email_batch(
        unique_emails,
        check_smtp=check_smtp,
        max_workers=max_workers
    )

    # Print verification report
    print_verification_report(results)

    # Create results map
    results_map = {r.email: r for r in results}

    # Update profiles with verification results
    print("Updating company profiles...")
    print("-" * 70)

    updated_count = 0
    failed_count = 0

    for item in profiles:
        domain = item["domain"]
        profile_path = item["profile_path"]
        emails = extract_emails_from_profile(item["profile"])

        if not emails:
            continue

        # Get verification results for this profile's emails
        verification_results = {}
        has_valid_email = False

        for email in emails:
            if email in results_map:
                verification_results[email] = results_map[email]
                if results_map[email].is_valid:
                    has_valid_email = True

                # Log result
                log_verification_result(domain, email, results_map[email])

        if not verification_results:
            continue

        # Update profile
        if update_profile_with_verification(profile_path, verification_results, dry_run):
            status = "✓ VALID" if has_valid_email else "✗ ALL INVALID"
            print(f"  [{status}] {domain} - {len(verification_results)} email(s) verified")
            updated_count += 1
        else:
            print(f"  [ERROR] {domain} - Failed to update profile")
            failed_count += 1

    # Final summary
    print("\n" + "="*70)
    print("VERIFICATION COMPLETE")
    print("="*70)

    valid_count = sum(1 for r in results if r.is_valid)
    invalid_count = len(results) - valid_count

    print(f"\nEmail Results:")
    print(f"  ✓ Valid: {valid_count}/{len(results)}")
    print(f"  ✗ Invalid: {invalid_count}/{len(results)}")

    print(f"\nProfile Updates:")
    print(f"  ✓ Updated: {updated_count}")
    print(f"  ✗ Failed: {failed_count}")

    if not dry_run:
        print(f"\nVerification report: {VERIFICATION_REPORT_FILE}")

    print("="*70 + "\n")

    # Show companies with no valid emails
    invalid_companies = []
    for item in profiles:
        domain = item["domain"]
        emails = extract_emails_from_profile(item["profile"])

        if not emails:
            continue

        all_invalid = all(
            not results_map.get(email, ValidationResult(email=email, is_valid=False, checks={})).is_valid
            for email in emails
        )

        if all_invalid:
            invalid_companies.append(domain)

    if invalid_companies:
        print(f"⚠ WARNING: {len(invalid_companies)} companies have NO valid emails:")
        for domain in invalid_companies[:10]:  # Show first 10
            print(f"  - {domain}")
        if len(invalid_companies) > 10:
            print(f"  ... and {len(invalid_companies) - 10} more")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Verify contact emails for all extracted companies"
    )
    parser.add_argument(
        "--domains",
        nargs="*",
        help="Verify only these domains (if not specified, verifies all)"
    )
    parser.add_argument(
        "--no-smtp",
        action="store_true",
        help="Skip SMTP verification (faster but less accurate)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-verification (ignore cache)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update profile files (test mode)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of parallel workers (default: 5)"
    )

    args = parser.parse_args()

    verify_company_emails(
        check_smtp=not args.no_smtp,
        domains=args.domains,
        force=args.force,
        dry_run=args.dry_run,
        max_workers=args.workers
    )


if __name__ == "__main__":
    main()
