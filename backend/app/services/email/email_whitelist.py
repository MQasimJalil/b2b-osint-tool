"""
Email Whitelist Management

Allows manual overrides for emails that are known to be valid
despite verification failures.

Use cases:
- Server blocks SMTP verification but email actually works
- You've successfully sent emails to this address
- Known corporate emails that don't verify well
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Paths
BASE_DIR = Path(__file__).parent.parent
WHITELIST_FILE = BASE_DIR / "email_whitelist.jsonl"


def add_to_whitelist(
    email: str,
    reason: str = "Manually verified",
    metadata: Optional[Dict] = None
):
    """
    Add email to whitelist.

    Args:
        email: Email address to whitelist
        reason: Reason for whitelisting
        metadata: Optional additional metadata
    """
    email = email.strip().lower()

    entry = {
        "email": email,
        "reason": reason,
        "whitelisted_at": datetime.utcnow().isoformat() + "Z",
        "timestamp": int(time.time())
    }

    if metadata:
        entry["metadata"] = metadata

    with open(WHITELIST_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[WHITELISTED] {email} - {reason}")


def is_whitelisted(email: str) -> bool:
    """Check if email is whitelisted."""
    if not WHITELIST_FILE.exists():
        return False

    email = email.strip().lower()

    with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("email") == email:
                    return True
            except:
                continue

    return False


def get_whitelist() -> List[Dict]:
    """Get all whitelisted emails."""
    if not WHITELIST_FILE.exists():
        return []

    whitelist = []
    with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                whitelist.append(json.loads(line))
            except:
                continue

    return whitelist


def remove_from_whitelist(email: str):
    """Remove email from whitelist."""
    if not WHITELIST_FILE.exists():
        return

    email = email.strip().lower()

    # Read all entries except the one to remove
    entries = []
    with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("email") != email:
                    entries.append(entry)
            except:
                continue

    # Rewrite file
    with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    print(f"[REMOVED FROM WHITELIST] {email}")


def whitelist_domain_emails(domain: str, reason: str = "Known working domain"):
    """
    Whitelist all emails from a domain's profile.

    Args:
        domain: Domain name
        reason: Reason for whitelisting
    """
    from pathlib import Path
    import json

    profile_path = Path("extracted_data") / "companies" / domain / "profile.json"

    if not profile_path.exists():
        print(f"✗ No profile found for {domain}")
        return

    with open(profile_path, 'r', encoding='utf-8') as f:
        profile = json.load(f)

    emails = profile.get("main_contacts", {}).get("email", [])

    if not emails:
        print(f"✗ No emails found for {domain}")
        return

    for email in emails:
        add_to_whitelist(
            email,
            reason=reason,
            metadata={"domain": domain}
        )

    print(f"\n✓ Whitelisted {len(emails)} emails for {domain}")


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Email Whitelist Management")

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Add email
    add_parser = subparsers.add_parser('add', help='Add email to whitelist')
    add_parser.add_argument('email', help='Email address')
    add_parser.add_argument('--reason', default='Manually verified', help='Reason')

    # Add domain
    domain_parser = subparsers.add_parser('add-domain', help='Whitelist all emails from a domain')
    domain_parser.add_argument('domain', help='Domain name')
    domain_parser.add_argument('--reason', default='Known working domain', help='Reason')

    # Remove email
    remove_parser = subparsers.add_parser('remove', help='Remove email from whitelist')
    remove_parser.add_argument('email', help='Email address')

    # List whitelist
    subparsers.add_parser('list', help='List all whitelisted emails')

    # Check email
    check_parser = subparsers.add_parser('check', help='Check if email is whitelisted')
    check_parser.add_argument('email', help='Email address')

    args = parser.parse_args()

    if args.command == 'add':
        add_to_whitelist(args.email, args.reason)

    elif args.command == 'add-domain':
        whitelist_domain_emails(args.domain, args.reason)

    elif args.command == 'remove':
        remove_from_whitelist(args.email)

    elif args.command == 'list':
        whitelist = get_whitelist()
        if whitelist:
            print(f"\nWhitelisted Emails ({len(whitelist)}):")
            print("="*70)
            for entry in whitelist:
                print(f"  {entry['email']}")
                print(f"    Reason: {entry['reason']}")
                print(f"    Added: {entry['whitelisted_at']}")
                print()
        else:
            print("No whitelisted emails")

    elif args.command == 'check':
        if is_whitelisted(args.email):
            print(f"✓ {args.email} is whitelisted")
        else:
            print(f"✗ {args.email} is NOT whitelisted")

    else:
        parser.print_help()
        print("\nExamples:")
        print("  python pipeline/email_whitelist.py add contact@example.com")
        print("  python pipeline/email_whitelist.py add-domain r-gol.com")
        print("  python pipeline/email_whitelist.py list")
        print("  python pipeline/email_whitelist.py check contact@example.com")
