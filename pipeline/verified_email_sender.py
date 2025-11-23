"""
Verified Email Sender - Complete Email Workflow

Integrates:
1. Email verification (syntax, DNS/MX, SMTP)
2. Blacklist checking
3. Email sending via Gmail API
4. Send tracking
5. Bounce monitoring

This is the main entry point for sending verified emails.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from pipeline.email_verifier import (
    verify_email,
    verify_email_batch,
    is_blacklisted,
    print_verification_report
)
from pipeline.gmail_sender import send_email, send_bulk_emails
from pipeline.email_tracker import track_sent_email, get_email_stats

# Paths
BASE_DIR = Path(__file__).parent.parent
VERIFIED_EMAILS_FILE = BASE_DIR / "verified_emails.jsonl"


def prepare_and_verify_emails(
    emails: List[str],
    check_smtp: bool = True,
    max_workers: int = 5,
    skip_blacklisted: bool = True
) -> Dict[str, List[str]]:
    """
    Verify a list of emails and separate valid from invalid.

    Args:
        emails: List of email addresses to verify
        check_smtp: Perform SMTP verification (recommended)
        max_workers: Parallel workers for verification
        skip_blacklisted: Skip blacklisted emails

    Returns:
        {
            "valid": [list of valid emails],
            "invalid": [list of invalid emails],
            "blacklisted": [list of blacklisted emails]
        }
    """
    print("\n" + "="*70)
    print("EMAIL VERIFICATION PROCESS")
    print("="*70)

    # Remove duplicates
    emails = list(set(email.strip().lower() for email in emails))

    # Separate blacklisted emails
    blacklisted = []
    to_verify = []

    if skip_blacklisted:
        print("\nChecking blacklist...")
        for email in emails:
            if is_blacklisted(email):
                blacklisted.append(email)
                print(f"  [BLACKLISTED] {email}")
            else:
                to_verify.append(email)
    else:
        to_verify = emails

    print(f"\nVerifying {len(to_verify)} emails...")
    print(f"SMTP verification: {'ENABLED' if check_smtp else 'DISABLED'}")
    print("-" * 70)

    # Verify emails
    results = verify_email_batch(
        to_verify,
        check_smtp=check_smtp,
        max_workers=max_workers
    )

    # Separate valid and invalid
    valid = [r.email for r in results if r.is_valid]
    invalid = [r.email for r in results if not r.is_valid]

    # Print report
    print_verification_report(results)

    return {
        "valid": valid,
        "invalid": invalid,
        "blacklisted": blacklisted
    }


def send_verified_emails(
    email_list: List[Dict],
    verify_before_send: bool = True,
    check_smtp: bool = True,
    delay_seconds: int = 2,
    campaign_id: Optional[str] = None,
    dry_run: bool = False
) -> Dict:
    """
    Complete workflow: Verify emails, then send.

    Args:
        email_list: List of dicts with 'to', 'subject', 'body' keys
        verify_before_send: Verify emails before sending
        check_smtp: Use SMTP verification (recommended)
        delay_seconds: Delay between sends
        campaign_id: Campaign identifier
        dry_run: Test mode (no actual sending)

    Returns:
        {
            "verified": {...},
            "sent": [...],
            "failed": [...],
            "summary": {...}
        }

    Example:
        email_list = [
            {
                "to": "contact@example.com",
                "subject": "Partnership Opportunity",
                "body": "Hi there, ...",
                "domain": "example.com"
            },
            ...
        ]

        result = send_verified_emails(email_list, dry_run=False)
    """
    start_time = time.time()

    print("\n" + "="*70)
    print("VERIFIED EMAIL SENDING WORKFLOW")
    print("="*70)

    # Step 1: Verify emails
    verification_results = {"valid": [], "invalid": [], "blacklisted": []}

    if verify_before_send:
        emails_to_verify = [item['to'] for item in email_list]
        verification_results = prepare_and_verify_emails(
            emails_to_verify,
            check_smtp=check_smtp,
            max_workers=5,
            skip_blacklisted=True
        )

        # Filter email list to only valid emails
        valid_set = set(verification_results["valid"])
        email_list = [item for item in email_list if item['to'] in valid_set]

        if not email_list:
            print("\n⚠ No valid emails to send!")
            return {
                "verified": verification_results,
                "sent": [],
                "failed": [],
                "summary": {
                    "total_input": len(emails_to_verify),
                    "verified_valid": len(verification_results["valid"]),
                    "verified_invalid": len(verification_results["invalid"]),
                    "blacklisted": len(verification_results["blacklisted"]),
                    "sent_success": 0,
                    "sent_failed": 0,
                    "total_time": time.time() - start_time
                }
            }

        print(f"\n✓ Proceeding with {len(email_list)} verified emails")
    else:
        print("\n⚠ Skipping verification (not recommended)")

    # Step 2: Send emails
    print("\n" + "="*70)
    print("SENDING EMAILS")
    print("="*70)

    send_results = send_bulk_emails(
        email_list,
        delay_seconds=delay_seconds,
        dry_run=dry_run
    )

    # Step 3: Track sent emails
    if not dry_run:
        for i, result in enumerate(send_results):
            email_data = email_list[i]
            track_sent_email(
                domain=email_data.get('domain', ''),
                recipient_email=result['to'],
                subject_line=result['subject'],
                email_body=email_data['body'],
                send_result=result,
                campaign_id=campaign_id
            )

    # Separate successful and failed sends
    sent_success = [r for r in send_results if r['success']]
    sent_failed = [r for r in send_results if not r['success']]

    # Summary
    total_time = time.time() - start_time
    summary = {
        "total_input": len(email_list) + len(verification_results.get("invalid", [])) + len(verification_results.get("blacklisted", [])),
        "verified_valid": len(verification_results.get("valid", [])),
        "verified_invalid": len(verification_results.get("invalid", [])),
        "blacklisted": len(verification_results.get("blacklisted", [])),
        "sent_success": len(sent_success),
        "sent_failed": len(sent_failed),
        "total_time": total_time,
        "emails_per_minute": (len(sent_success) / total_time * 60) if total_time > 0 else 0
    }

    # Print final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    print(f"\nInput: {summary['total_input']} emails")
    if verify_before_send:
        print(f"\nVerification:")
        print(f"  ✓ Valid: {summary['verified_valid']}")
        print(f"  ✗ Invalid: {summary['verified_invalid']}")
        print(f"  ⊗ Blacklisted: {summary['blacklisted']}")
    print(f"\nSending:")
    print(f"  ✓ Sent: {summary['sent_success']}")
    print(f"  ✗ Failed: {summary['sent_failed']}")
    print(f"\nPerformance:")
    print(f"  Total time: {summary['total_time']:.1f}s")
    print(f"  Rate: {summary['emails_per_minute']:.1f} emails/min")
    print("="*70 + "\n")

    return {
        "verified": verification_results,
        "sent": sent_success,
        "failed": sent_failed,
        "summary": summary
    }


def verify_csv_file(
    csv_path: str,
    email_column: str = 'email',
    check_smtp: bool = True,
    output_path: Optional[str] = None
) -> Dict:
    """
    Verify emails from a CSV file.

    Args:
        csv_path: Path to CSV file
        email_column: Column name containing emails
        check_smtp: Use SMTP verification
        output_path: Optional output path for verified emails CSV

    Returns:
        Verification results
    """
    import csv

    print(f"\nReading emails from: {csv_path}")

    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    emails = [row[email_column] for row in rows if email_column in row]

    print(f"Found {len(emails)} emails")

    # Verify
    results = prepare_and_verify_emails(
        emails,
        check_smtp=check_smtp,
        skip_blacklisted=True
    )

    # Save results to CSV if output path provided
    if output_path:
        valid_emails = set(results['valid'])

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()

                for row in rows:
                    if row[email_column] in valid_emails:
                        writer.writerow(row)

        print(f"\n✓ Verified emails saved to: {output_path}")

    return results


# ============================================================================
# Quick Start Examples
# ============================================================================

def example_basic_usage():
    """Example: Basic verified email sending."""

    email_list = [
        {
            "to": "contact@example.com",
            "subject": "Partnership Opportunity",
            "body": "Hi,\n\nI'd like to discuss a potential partnership...",
            "domain": "example.com"
        },
        {
            "to": "info@anothercompany.com",
            "subject": "Collaboration Inquiry",
            "body": "Hello,\n\nWe're interested in collaborating...",
            "domain": "anothercompany.com"
        }
    ]

    # Send with verification
    result = send_verified_emails(
        email_list,
        verify_before_send=True,
        check_smtp=True,
        delay_seconds=2,
        dry_run=True  # Set to False for actual sending
    )

    return result


def example_verify_only():
    """Example: Just verify emails without sending."""

    emails_to_check = [
        "valid@gmail.com",
        "invalid@nonexistentdomain999.com",
        "noreply@example.com",
        "bad-format@",
    ]

    results = prepare_and_verify_emails(
        emails_to_check,
        check_smtp=True,
        skip_blacklisted=True
    )

    print(f"\nValid emails: {results['valid']}")
    print(f"Invalid emails: {results['invalid']}")
    print(f"Blacklisted emails: {results['blacklisted']}")

    return results


def example_verify_from_csv():
    """Example: Verify emails from CSV file."""

    # Verify emails from CSV
    results = verify_csv_file(
        csv_path="emails.csv",
        email_column="email",
        check_smtp=True,
        output_path="verified_emails.csv"
    )

    return results


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Verified Email Sender')

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify emails only')
    verify_parser.add_argument('emails', nargs='+', help='Email addresses to verify')
    verify_parser.add_argument('--no-smtp', action='store_true', help='Skip SMTP verification')

    # Verify CSV command
    csv_parser = subparsers.add_parser('verify-csv', help='Verify emails from CSV')
    csv_parser.add_argument('csv_path', help='Path to CSV file')
    csv_parser.add_argument('--column', default='email', help='Email column name')
    csv_parser.add_argument('--output', help='Output CSV path for verified emails')
    csv_parser.add_argument('--no-smtp', action='store_true', help='Skip SMTP verification')

    # Example command
    subparsers.add_parser('example', help='Run example')

    args = parser.parse_args()

    if args.command == 'verify':
        results = prepare_and_verify_emails(
            args.emails,
            check_smtp=not args.no_smtp
        )

    elif args.command == 'verify-csv':
        results = verify_csv_file(
            args.csv_path,
            email_column=args.column,
            check_smtp=not args.no_smtp,
            output_path=args.output
        )

    elif args.command == 'example':
        print("\nRunning example (dry run)...")
        example_basic_usage()

    else:
        parser.print_help()
        print("\n" + "="*70)
        print("QUICK START GUIDE")
        print("="*70)
        print("\n1. Verify emails:")
        print("   python pipeline/verified_email_sender.py verify email1@test.com email2@test.com")
        print("\n2. Verify CSV file:")
        print("   python pipeline/verified_email_sender.py verify-csv emails.csv --output verified.csv")
        print("\n3. Run example:")
        print("   python pipeline/verified_email_sender.py example")
        print("\n4. In your code:")
        print("   from pipeline.verified_email_sender import send_verified_emails")
        print("="*70 + "\n")
