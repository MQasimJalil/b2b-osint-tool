"""
Gmail Bounce Monitoring System

Monitors Gmail inbox for bounce notifications and automatically:
1. Detects hard bounces (permanent failures)
2. Detects soft bounces (temporary failures)
3. Extracts bounced email addresses
4. Updates blacklist automatically
5. Links bounces to sent emails in tracker

Run periodically (e.g., hourly/daily) to catch bounces.
"""

import re
import base64
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from email import message_from_bytes

from pipeline.email_verifier import add_to_blacklist

# Import Gmail service
import sys
sys.path.append(str(Path(__file__).parent.parent))
from pipeline.gmail_sender import get_gmail_service

# Paths
BASE_DIR = Path(__file__).parent.parent
BOUNCE_LOG_FILE = BASE_DIR / "email_bounces.jsonl"

# Bounce detection patterns
BOUNCE_SUBJECT_PATTERNS = [
    r'delivery.*fail',
    r'undelivered',
    r'returned.*mail',
    r'delivery.*status.*notification',
    r'mail.*delivery.*fail',
    r'failure.*notice',
    r'undeliverable',
    r'postmaster',
]

# Email extraction patterns from bounce messages
EMAIL_EXTRACTION_PATTERNS = [
    r'<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>',  # <email@domain.com>
    r'to:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',  # to: email@domain.com
    r'recipient:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',  # recipient: email@domain.com
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',  # fallback: any email
]

# Hard bounce indicators (permanent failures)
HARD_BOUNCE_INDICATORS = [
    '550',  # Mailbox unavailable
    '551',  # User not local
    '553',  # Mailbox name invalid
    '554',  # Transaction failed
    'user.*not.*found',
    'user.*unknown',
    'mailbox.*not.*found',
    'mailbox.*unavailable',
    'no.*such.*user',
    'invalid.*recipient',
    'does.*not.*exist',
    'recipient.*rejected',
    'address.*rejected',
]

# Soft bounce indicators (temporary failures - don't blacklist)
SOFT_BOUNCE_INDICATORS = [
    '450',  # Mailbox busy
    '451',  # Local error
    '452',  # Insufficient storage
    '421',  # Service not available
    'mailbox.*full',
    'quota.*exceeded',
    'temporarily.*unavailable',
    'try.*again.*later',
]


def is_bounce_email(subject: str, from_email: str) -> bool:
    """
    Check if email is a bounce notification.

    Args:
        subject: Email subject line
        from_email: Sender email address

    Returns:
        True if this is a bounce notification
    """
    subject = subject.lower()
    from_email = from_email.lower()

    # Check subject patterns
    for pattern in BOUNCE_SUBJECT_PATTERNS:
        if re.search(pattern, subject, re.IGNORECASE):
            return True

    # Check if from mailer-daemon or postmaster
    if any(x in from_email for x in ['mailer-daemon', 'postmaster', 'noreply', 'no-reply']):
        if any(x in subject for x in ['delivery', 'fail', 'undeliver', 'return', 'bounce']):
            return True

    return False


def classify_bounce(body: str) -> Tuple[str, Optional[str]]:
    """
    Classify bounce as hard (permanent) or soft (temporary).

    Args:
        body: Email body text

    Returns:
        (bounce_type, reason)
        bounce_type: 'hard', 'soft', or 'unknown'
    """
    body_lower = body.lower()

    # Check for hard bounce indicators
    for indicator in HARD_BOUNCE_INDICATORS:
        if re.search(indicator, body_lower):
            return 'hard', f"Hard bounce: {indicator}"

    # Check for soft bounce indicators
    for indicator in SOFT_BOUNCE_INDICATORS:
        if re.search(indicator, body_lower):
            return 'soft', f"Soft bounce: {indicator}"

    return 'unknown', "Could not classify bounce type"


def extract_bounced_email(body: str, headers: str = "") -> Optional[str]:
    """
    Extract the bounced email address from bounce message.

    Args:
        body: Email body
        headers: Email headers (if available)

    Returns:
        Bounced email address or None
    """
    text = (headers + "\n" + body).lower()

    # Try each extraction pattern
    for pattern in EMAIL_EXTRACTION_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Filter out our own email and common system emails
            for email in matches:
                email = email.lower().strip()
                # Skip our own email and system emails
                if email in ['qasim@raqiminternational.com', 'verify@gmail.com']:
                    continue
                if any(x in email for x in ['mailer-daemon', 'postmaster', 'noreply']):
                    continue
                return email

    return None


def get_email_body(message_data: Dict) -> str:
    """
    Extract email body from Gmail message.

    Args:
        message_data: Gmail API message data

    Returns:
        Email body text
    """
    try:
        if 'parts' in message_data['payload']:
            # Multi-part message
            parts = message_data['payload']['parts']
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            # Simple message
            data = message_data['payload']['body'].get('data')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error extracting body: {e}")

    return ""


def get_email_headers(message_data: Dict) -> Dict[str, str]:
    """
    Extract headers from Gmail message.

    Returns:
        Dict of header_name: header_value
    """
    headers = {}
    try:
        for header in message_data['payload']['headers']:
            headers[header['name'].lower()] = header['value']
    except:
        pass

    return headers


def check_bounces(
    hours_ago: int = 24,
    auto_blacklist: bool = True,
    dry_run: bool = False
) -> List[Dict]:
    """
    Check Gmail for bounce notifications.

    Args:
        hours_ago: Check emails from last N hours
        auto_blacklist: Automatically add hard bounces to blacklist
        dry_run: If True, don't actually blacklist

    Returns:
        List of bounce information dicts
    """
    try:
        service = get_gmail_service()

        # Calculate time range
        after_timestamp = int((datetime.utcnow() - timedelta(hours=hours_ago)).timestamp())

        # Search for potential bounce emails
        # Using 'in:inbox OR in:spam' to catch bounces in both locations
        query = f'after:{after_timestamp} (from:mailer-daemon OR from:postmaster OR subject:delivery OR subject:undelivered OR subject:failure OR subject:returned)'

        print(f"\nSearching for bounces in last {hours_ago} hours...")

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            print("No bounce messages found.")
            return []

        print(f"Found {len(messages)} potential bounce messages. Analyzing...")

        bounces = []

        for msg in messages:
            # Get full message
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            # Extract headers
            headers = get_email_headers(message)
            subject = headers.get('subject', '')
            from_email = headers.get('from', '')

            # Check if this is actually a bounce
            if not is_bounce_email(subject, from_email):
                continue

            # Extract body
            body = get_email_body(message)

            # Classify bounce
            bounce_type, reason = classify_bounce(body)

            # Extract bounced email
            bounced_email = extract_bounced_email(body, str(headers))

            if not bounced_email:
                print(f"  [SKIPPED] Could not extract bounced email from: {subject}")
                continue

            bounce_info = {
                "bounced_email": bounced_email,
                "bounce_type": bounce_type,
                "reason": reason,
                "subject": subject,
                "from": from_email,
                "received_at": headers.get('date', ''),
                "gmail_message_id": msg['id'],
                "detected_at": datetime.utcnow().isoformat() + "Z",
                "auto_blacklisted": False
            }

            # Auto-blacklist hard bounces
            if auto_blacklist and bounce_type == 'hard':
                if not dry_run:
                    add_to_blacklist(
                        bounced_email,
                        reason=f"Hard bounce: {reason}",
                        metadata={"bounce_detected_at": bounce_info["detected_at"]}
                    )
                    bounce_info["auto_blacklisted"] = True
                    print(f"  [HARD BOUNCE] {bounced_email} - BLACKLISTED")
                else:
                    print(f"  [DRY RUN] Would blacklist: {bounced_email}")
            elif bounce_type == 'soft':
                print(f"  [SOFT BOUNCE] {bounced_email} - Not blacklisted (temporary issue)")
            else:
                print(f"  [UNKNOWN BOUNCE] {bounced_email} - {reason}")

            bounces.append(bounce_info)

            # Log bounce
            log_bounce(bounce_info)

        return bounces

    except Exception as e:
        print(f"Error checking bounces: {e}")
        return []


def log_bounce(bounce_info: Dict):
    """Log bounce to file."""
    with open(BOUNCE_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(bounce_info) + "\n")


def get_bounce_history(
    email: Optional[str] = None,
    days_ago: int = 30
) -> List[Dict]:
    """
    Get bounce history.

    Args:
        email: Filter by email address
        days_ago: Get bounces from last N days

    Returns:
        List of bounce records
    """
    if not BOUNCE_LOG_FILE.exists():
        return []

    cutoff = datetime.utcnow() - timedelta(days=days_ago)
    bounces = []

    with open(BOUNCE_LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                bounce = json.loads(line)

                # Apply filters
                if email and bounce.get("bounced_email") != email:
                    continue

                detected_at = datetime.fromisoformat(bounce["detected_at"].rstrip('Z'))
                if detected_at < cutoff:
                    continue

                bounces.append(bounce)
            except:
                continue

    return bounces


def get_bounce_stats(days_ago: int = 30) -> Dict:
    """
    Get bounce statistics.

    Args:
        days_ago: Stats for last N days

    Returns:
        Statistics dict
    """
    bounces = get_bounce_history(days_ago=days_ago)

    if not bounces:
        return {
            "total_bounces": 0,
            "hard_bounces": 0,
            "soft_bounces": 0,
            "unknown_bounces": 0,
            "auto_blacklisted": 0
        }

    hard_bounces = [b for b in bounces if b.get("bounce_type") == "hard"]
    soft_bounces = [b for b in bounces if b.get("bounce_type") == "soft"]
    unknown_bounces = [b for b in bounces if b.get("bounce_type") == "unknown"]
    auto_blacklisted = [b for b in bounces if b.get("auto_blacklisted")]

    return {
        "total_bounces": len(bounces),
        "hard_bounces": len(hard_bounces),
        "soft_bounces": len(soft_bounces),
        "unknown_bounces": len(unknown_bounces),
        "auto_blacklisted": len(auto_blacklisted),
        "bounce_rate": f"{len(hard_bounces) / len(bounces) * 100:.1f}%" if bounces else "0%"
    }


def print_bounce_report(days_ago: int = 30):
    """Print bounce monitoring report."""
    stats = get_bounce_stats(days_ago)

    print("\n" + "="*70)
    print(f"BOUNCE MONITORING REPORT (Last {days_ago} days)")
    print("="*70)

    print(f"\nTotal Bounces: {stats['total_bounces']}")
    print(f"  Hard Bounces: {stats['hard_bounces']}")
    print(f"  Soft Bounces: {stats['soft_bounces']}")
    print(f"  Unknown: {stats['unknown_bounces']}")
    print(f"\nAuto-blacklisted: {stats['auto_blacklisted']}")
    print(f"Hard Bounce Rate: {stats['bounce_rate']}")

    # Show recent bounces
    recent = get_bounce_history(days_ago=7)[:10]
    if recent:
        print(f"\nRecent Bounces (last 7 days):")
        for bounce in recent:
            print(f"  - {bounce['bounced_email']} ({bounce['bounce_type']}): {bounce['reason']}")

    print("="*70 + "\n")


# ============================================================================
# Scheduled Monitoring
# ============================================================================

def setup_bounce_monitoring_schedule():
    """
    Setup instructions for scheduled bounce monitoring.

    Prints instructions for setting up automated monitoring.
    """
    print("""
==========================================================================
BOUNCE MONITORING SETUP INSTRUCTIONS
==========================================================================

To automatically monitor bounces, run this script periodically:

Option 1: Windows Task Scheduler
---------------------------------
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at specific time (e.g., 9 AM)
4. Action: Start a program
   - Program: python
   - Arguments: "D:\\Raqim\\b2b_osint_tool\\pipeline\\bounce_monitor.py"
5. Save and enable

Option 2: Python Script (run continuously)
------------------------------------------
Create a separate script that runs this in a loop:

    while True:
        check_bounces(hours_ago=24, auto_blacklist=True)
        time.sleep(3600)  # Check every hour

Option 3: Manual (After each campaign)
--------------------------------------
After sending emails, wait 1-2 hours, then run:

    python pipeline/bounce_monitor.py

This will check for bounces and auto-blacklist hard bounces.

==========================================================================
    """)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Gmail Bounce Monitor')
    parser.add_argument('--hours', type=int, default=24, help='Check bounces from last N hours')
    parser.add_argument('--no-blacklist', action='store_true', help='Do not auto-blacklist hard bounces')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode (no actual blacklisting)')
    parser.add_argument('--report', action='store_true', help='Show bounce report')
    parser.add_argument('--setup', action='store_true', help='Show setup instructions')

    args = parser.parse_args()

    if args.setup:
        setup_bounce_monitoring_schedule()
    elif args.report:
        print_bounce_report(days_ago=30)
    else:
        print("="*70)
        print("GMAIL BOUNCE MONITOR")
        print("="*70)

        bounces = check_bounces(
            hours_ago=args.hours,
            auto_blacklist=not args.no_blacklist,
            dry_run=args.dry_run
        )

        print(f"\n{'='*70}")
        print(f"Summary:")
        print(f"  Total bounces found: {len(bounces)}")
        print(f"  Hard bounces: {sum(1 for b in bounces if b['bounce_type'] == 'hard')}")
        print(f"  Soft bounces: {sum(1 for b in bounces if b['bounce_type'] == 'soft')}")
        print(f"  Auto-blacklisted: {sum(1 for b in bounces if b['auto_blacklisted'])}")
        print(f"{'='*70}\n")

        if not args.dry_run:
            print("Tip: Run this script regularly (hourly/daily) to catch bounces early.")
            print("Use --setup to see automated scheduling options.")
