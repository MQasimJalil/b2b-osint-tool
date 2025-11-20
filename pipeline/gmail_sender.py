"""
Gmail API integration for sending personalized emails.

Setup Instructions:
1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials.json and place in project root
6. Run this script once to authenticate (creates token.json)
7. Use send_email() function to send emails
"""

import os
import json
import base64
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes
# Note: gmail.compose includes both send and draft permissions
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

# Paths
BASE_DIR = Path(__file__).parent.parent
TOKEN_FILE = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"


def get_gmail_service():
    """
    Authenticate and return Gmail API service.

    Returns:
        Gmail API service object

    Raises:
        FileNotFoundError: If credentials.json not found
        Exception: If authentication fails
    """
    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            creds.refresh(Request())
        else:
            # New authentication flow
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}\n"
                    "Please download OAuth credentials from Google Cloud Console:\n"
                    "1. Go to https://console.cloud.google.com/\n"
                    "2. Enable Gmail API\n"
                    "3. Create OAuth 2.0 credentials (Desktop app)\n"
                    "4. Download credentials.json to project root"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for future use
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service


def create_message(
    to: str,
    subject: str,
    body: str,
    from_name: str = "Qasim Jalil",
    from_email: str = "qasim@raqiminternational.com",
    html: bool = False
) -> Dict:
    """
    Create email message in Gmail API format.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content
        from_name: Sender name
        from_email: Sender email (must match authenticated Gmail)
        html: If True, send as HTML email

    Returns:
        Gmail API message object
    """
    message = MIMEMultipart('alternative') if html else MIMEText(body)

    message['to'] = to
    message['from'] = f"{from_name} <{from_email}>"
    message['subject'] = subject

    if html:
        # Plain text version
        part1 = MIMEText(body, 'plain')
        # HTML version
        html_body = body.replace('\n', '<br>')
        part2 = MIMEText(html_body, 'html')

        message.attach(part1)
        message.attach(part2)

    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    return {'raw': raw_message}


def send_email(
    to: str,
    subject: str,
    body: str,
    from_name: str = "Qasim Jalil",
    from_email: str = "qasim@raqiminternational.com",
    html: bool = False,
    dry_run: bool = False
) -> Dict:
    """
    Send email via Gmail API.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content
        from_name: Sender name
        from_email: Sender email
        html: If True, send as HTML email
        dry_run: If True, don't actually send (for testing)

    Returns:
        {
            "success": bool,
            "message_id": str (if success),
            "error": str (if failed),
            "to": str,
            "subject": str,
            "sent_at": str (ISO timestamp)
        }
    """
    result = {
        "to": to,
        "subject": subject,
        "sent_at": datetime.utcnow().isoformat() + "Z"
    }

    if dry_run:
        result.update({
            "success": True,
            "message_id": "dry_run",
            "dry_run": True
        })
        print(f"[DRY RUN] Would send email to {to}")
        print(f"  Subject: {subject}")
        print(f"  Body length: {len(body)} chars")
        return result

    try:
        service = get_gmail_service()
        message = create_message(to, subject, body, from_name, from_email, html)

        sent_message = service.users().messages().send(
            userId='me',
            body=message
        ).execute()

        result.update({
            "success": True,
            "message_id": sent_message['id']
        })

        print(f"[✓] Email sent to {to} (ID: {sent_message['id']})")
        return result

    except HttpError as error:
        result.update({
            "success": False,
            "error": f"Gmail API error: {error}"
        })
        print(f"[✗] Failed to send email to {to}: {error}")
        return result

    except Exception as e:
        result.update({
            "success": False,
            "error": str(e)
        })
        print(f"[✗] Failed to send email to {to}: {e}")
        return result


def send_bulk_emails(
    emails: List[Dict],
    delay_seconds: int = 2,
    dry_run: bool = False
) -> List[Dict]:
    """
    Send multiple emails with rate limiting.

    Args:
        emails: List of email dicts with 'to', 'subject', 'body' keys
        delay_seconds: Delay between emails (to avoid rate limits)
        dry_run: If True, don't actually send (for testing)

    Returns:
        List of send results

    Example:
        emails = [
            {
                "to": "contact@example.com",
                "subject": "Partnership opportunity",
                "body": "Hi there, ..."
            },
            ...
        ]
        results = send_bulk_emails(emails)
    """
    import time

    results = []

    for i, email in enumerate(emails, 1):
        print(f"\n[{i}/{len(emails)}] Sending to {email['to']}...")

        result = send_email(
            to=email['to'],
            subject=email['subject'],
            body=email['body'],
            from_name=email.get('from_name', 'Qasim Jalil'),
            from_email=email.get('from_email', 'qasim@raqiminternational.com'),
            html=email.get('html', False),
            dry_run=dry_run
        )

        # Add metadata
        result.update({
            "domain": email.get('domain'),
            "batch_index": i,
            "batch_total": len(emails)
        })

        results.append(result)

        # Rate limiting (except for last email)
        if i < len(emails):
            time.sleep(delay_seconds)

    # Summary
    success_count = sum(1 for r in results if r['success'])
    fail_count = len(results) - success_count

    print(f"\n{'='*60}")
    print(f"Bulk send complete:")
    print(f"  ✓ Success: {success_count}")
    print(f"  ✗ Failed: {fail_count}")
    print(f"{'='*60}")

    return results


# ============================================================================
# Testing & Demo
# ============================================================================

def test_authentication():
    """Test Gmail API authentication."""
    try:
        service = get_gmail_service()
        print("✓ Gmail API authentication successful!")

        # Get user profile to verify
        profile = service.users().getProfile(userId='me').execute()
        print(f"  Authenticated as: {profile['emailAddress']}")

        return True
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return False


def send_test_email(to: str):
    """Send a test email to verify setup."""
    subject = "Test Email from B2B OSINT Tool"
    body = """Hi,

This is a test email from the B2B OSINT Tool's Gmail integration.

If you received this, the setup is working correctly!

Best regards,
Qasim Jalil
Raqim International"""

    result = send_email(to, subject, body, dry_run=False)

    if result['success']:
        print(f"\n✓ Test email sent successfully!")
        print(f"  Message ID: {result['message_id']}")
    else:
        print(f"\n✗ Test email failed!")
        print(f"  Error: {result.get('error')}")

    return result


if __name__ == "__main__":
    import sys

    print("="*60)
    print("Gmail API Integration Test")
    print("="*60)

    # Test authentication
    print("\n1. Testing authentication...")
    if not test_authentication():
        sys.exit(1)

    # Send test email
    print("\n2. Send test email? (y/n)")
    if input().lower() == 'y':
        test_email = input("Enter recipient email: ")
        send_test_email(test_email)
