"""
Email tracking system to record sent emails and campaign performance.

Tracks:
- Email send date/time
- Recipient details
- Subject line used
- Campaign metadata
- Send status (success/failed)

Storage options:
1. Local JSONL file (default, fast, no dependencies)
2. Google Sheets (optional, for team collaboration)
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Paths
BASE_DIR = Path(__file__).parent.parent
TRACKER_FILE = BASE_DIR / "email_tracking.jsonl"
CAMPAIGNS_FILE = BASE_DIR / "email_campaigns.jsonl"


# ============================================================================
# Local JSONL Tracking (Default)
# ============================================================================

def track_sent_email(
    domain: str,
    recipient_email: str,
    subject_line: str,
    email_body: str,
    send_result: Dict,
    campaign_id: Optional[str] = None,
    metadata: Optional[Dict] = None
):
    """
    Track a sent email to local JSONL file.

    Args:
        domain: Company domain
        recipient_email: Recipient email address
        subject_line: Subject line used
        email_body: Email body sent
        send_result: Result from gmail_sender.send_email()
        campaign_id: Optional campaign identifier
        metadata: Optional additional metadata

    Creates entry in email_tracking.jsonl
    """
    entry = {
        "domain": domain,
        "recipient": recipient_email,
        "subject_line": subject_line,
        "campaign_id": campaign_id,
        "sent_at": send_result.get("sent_at", datetime.utcnow().isoformat() + "Z"),
        "status": "sent" if send_result.get("success") else "failed",
        "message_id": send_result.get("message_id"),
        "error": send_result.get("error"),
        "email_length": len(email_body),
        "timestamp": int(time.time())
    }

    # Add metadata if provided
    if metadata:
        entry["metadata"] = metadata

    # Append to tracking file
    with open(TRACKER_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[TRACKED] {domain} → {recipient_email} ({entry['status']})")


def get_sent_emails(
    domain: Optional[str] = None,
    campaign_id: Optional[str] = None,
    since_timestamp: Optional[int] = None
) -> List[Dict]:
    """
    Retrieve sent emails from tracking file.

    Args:
        domain: Filter by domain
        campaign_id: Filter by campaign
        since_timestamp: Only emails sent after this timestamp

    Returns:
        List of sent email entries
    """
    if not TRACKER_FILE.exists():
        return []

    emails = []
    with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue

            try:
                entry = json.loads(line)

                # Apply filters
                if domain and entry.get("domain") != domain:
                    continue
                if campaign_id and entry.get("campaign_id") != campaign_id:
                    continue
                if since_timestamp and entry.get("timestamp", 0) < since_timestamp:
                    continue

                emails.append(entry)
            except:
                continue

    return emails


def was_email_sent(domain: str, days_ago: int = 30) -> bool:
    """
    Check if we already sent an email to this domain recently.

    Args:
        domain: Domain to check
        days_ago: Consider emails sent within this many days

    Returns:
        True if email was sent recently
    """
    cutoff = int(time.time()) - (days_ago * 24 * 60 * 60)
    recent_emails = get_sent_emails(domain=domain, since_timestamp=cutoff)

    return len(recent_emails) > 0


def get_email_stats(campaign_id: Optional[str] = None) -> Dict:
    """
    Get email sending statistics.

    Args:
        campaign_id: Optional filter by campaign

    Returns:
        {
            "total_sent": int,
            "successful": int,
            "failed": int,
            "unique_domains": int,
            "date_range": {"earliest": str, "latest": str}
        }
    """
    emails = get_sent_emails(campaign_id=campaign_id)

    if not emails:
        return {
            "total_sent": 0,
            "successful": 0,
            "failed": 0,
            "unique_domains": 0,
            "date_range": {"earliest": None, "latest": None}
        }

    successful = [e for e in emails if e.get("status") == "sent"]
    failed = [e for e in emails if e.get("status") == "failed"]
    domains = set(e.get("domain") for e in emails if e.get("domain"))

    # Date range
    timestamps = [e.get("timestamp", 0) for e in emails]
    earliest = datetime.fromtimestamp(min(timestamps)).isoformat() if timestamps else None
    latest = datetime.fromtimestamp(max(timestamps)).isoformat() if timestamps else None

    return {
        "total_sent": len(emails),
        "successful": len(successful),
        "failed": len(failed),
        "unique_domains": len(domains),
        "date_range": {
            "earliest": earliest,
            "latest": latest
        }
    }


# ============================================================================
# Campaign Management
# ============================================================================

def create_campaign(
    name: str,
    description: str = "",
    domains: Optional[List[str]] = None
) -> str:
    """
    Create a new email campaign.

    Args:
        name: Campaign name
        description: Campaign description
        domains: List of target domains

    Returns:
        Campaign ID (timestamp-based)
    """
    campaign_id = f"campaign_{int(time.time())}"

    campaign = {
        "campaign_id": campaign_id,
        "name": name,
        "description": description,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "domains": domains or [],
        "status": "active"
    }

    with open(CAMPAIGNS_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(campaign, ensure_ascii=False) + "\n")

    print(f"[CAMPAIGN CREATED] {name} (ID: {campaign_id})")
    return campaign_id


def get_campaigns() -> List[Dict]:
    """Get all campaigns."""
    if not CAMPAIGNS_FILE.exists():
        return []

    campaigns = []
    with open(CAMPAIGNS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    campaigns.append(json.loads(line))
                except:
                    continue

    return campaigns


# ============================================================================
# Google Sheets Integration (Optional)
# ============================================================================

def setup_google_sheets_tracking():
    """
    Setup Google Sheets for email tracking.

    Instructions:
    1. Enable Google Sheets API in Cloud Console
    2. Use same credentials.json as Gmail
    3. Creates a new spreadsheet for tracking
    4. Returns spreadsheet ID

    Returns:
        Spreadsheet ID
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

        # Authenticate (reuse Gmail token if possible)
        token_file = BASE_DIR / "token_sheets.json"
        creds = None

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(BASE_DIR / "credentials.json"), SCOPES
            )
            creds = flow.run_local_server(port=0)

            with open(token_file, 'w') as f:
                f.write(creds.to_json())

        service = build('sheets', 'v4', credentials=creds)

        # Create spreadsheet
        spreadsheet = {
            'properties': {
                'title': 'B2B Email Tracking'
            },
            'sheets': [{
                'properties': {
                    'title': 'Sent Emails',
                    'gridProperties': {
                        'frozenRowCount': 1
                    }
                }
            }]
        }

        result = service.spreadsheets().create(body=spreadsheet).execute()
        spreadsheet_id = result['spreadsheetId']

        # Add header row
        header = [
            'Date',
            'Domain',
            'Recipient',
            'Subject Line',
            'Campaign',
            'Status',
            'Message ID'
        ]

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Sent Emails!A1:G1',
            valueInputOption='RAW',
            body={'values': [header]}
        ).execute()

        print(f"✓ Google Sheet created: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
        return spreadsheet_id

    except ImportError:
        print("✗ Google Sheets integration requires: pip install google-api-python-client google-auth")
        return None
    except Exception as e:
        print(f"✗ Failed to setup Google Sheets: {e}")
        return None


def sync_to_google_sheets(spreadsheet_id: str, limit: int = 100):
    """
    Sync recent emails to Google Sheets.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID
        limit: Number of recent emails to sync
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        # Get credentials
        token_file = BASE_DIR / "token_sheets.json"
        creds = Credentials.from_authorized_user_file(str(token_file))

        service = build('sheets', 'v4', credentials=creds)

        # Get recent emails
        emails = get_sent_emails()[-limit:]

        # Prepare rows
        rows = []
        for email in emails:
            rows.append([
                email.get('sent_at', ''),
                email.get('domain', ''),
                email.get('recipient', ''),
                email.get('subject_line', ''),
                email.get('campaign_id', ''),
                email.get('status', ''),
                email.get('message_id', '')
            ])

        # Append to sheet
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='Sent Emails!A2',
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

        print(f"✓ Synced {len(rows)} emails to Google Sheets")

    except Exception as e:
        print(f"✗ Failed to sync to Google Sheets: {e}")


# ============================================================================
# Reporting
# ============================================================================

def print_email_report(campaign_id: Optional[str] = None):
    """Print formatted email tracking report."""
    stats = get_email_stats(campaign_id)

    print("\n" + "="*60)
    print("EMAIL TRACKING REPORT")
    if campaign_id:
        print(f"Campaign: {campaign_id}")
    print("="*60)

    print(f"\nTotal Sent: {stats['total_sent']}")
    print(f"  ✓ Successful: {stats['successful']}")
    print(f"  ✗ Failed: {stats['failed']}")
    print(f"\nUnique Domains: {stats['unique_domains']}")

    if stats['date_range']['earliest']:
        print(f"\nDate Range:")
        print(f"  First: {stats['date_range']['earliest']}")
        print(f"  Latest: {stats['date_range']['latest']}")

    print("="*60 + "\n")


if __name__ == "__main__":
    # Demo / Testing
    print("Email Tracker Demo")
    print("="*60)

    # Show stats
    print_email_report()

    # Show recent emails
    recent = get_sent_emails()[-10:]
    if recent:
        print("\nRecent Emails:")
        for i, email in enumerate(recent, 1):
            print(f"{i}. {email['domain']} → {email['recipient']} ({email['status']})")
