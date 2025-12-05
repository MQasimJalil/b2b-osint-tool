"""
Gmail API integration for sending personalized emails with attachment support.

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
import time

# Email library imports
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
TOKEN_FILE = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"


def get_gmail_service():
    """
    Authenticate and return Gmail API service.
    """
    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}\n"
                    "Please download OAuth credentials from Google Cloud Console."
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
    body_text: str,
    body_html: Optional[str] = None,
    attachments: Optional[List[Dict]] = None,
    from_name: str = "Qasim Jalil",
    from_email: str = "qasim@raqiminternational.com"
) -> Dict:
    """
    Create email message with optional HTML and attachments.

    Args:
        to: Recipient email address
        subject: Email subject line
        body_text: Plain text version of the email
        body_html: HTML version of the email (optional)
        attachments: List of dicts with 'filename' and 'content' (bytes)
        from_name: Sender name
        from_email: Sender email

    Returns:
        Gmail API message object {'raw': base64_string}
    """
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = f"{from_name} <{from_email}>"
    message['subject'] = subject

    # 1. Add Body (Text and/or HTML)
    if body_html:
        # If HTML is provided, create a multipart/alternative container.
        # This ensures clients that can't read HTML fall back to text.
        msg_alternative = MIMEMultipart('alternative')
        msg_alternative.attach(MIMEText(body_text, 'plain'))
        msg_alternative.attach(MIMEText(body_html, 'html'))
        message.attach(msg_alternative)
    else:
        # Plain text only
        message.attach(MIMEText(body_text, 'plain'))

    # 2. Add Attachments
    if attachments:
        for attachment in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment['content'])
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={attachment["filename"]}'
            )
            message.attach(part)

    # 3. Encode message for Gmail API
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    return {'raw': raw_message}


def send_email(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    attachments: Optional[List[Dict]] = None,
    from_name: str = "Qasim Jalil",
    from_email: str = "qasim@raqiminternational.com",
    dry_run: bool = False
) -> Dict:
    """
    Send email via Gmail API with support for HTML and Attachments.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain text body content
        html_body: HTML body content (optional)
        attachments: List of dicts {'filename': str, 'content': bytes}
        from_name: Sender name
        from_email: Sender email
        dry_run: If True, don't actually send

    Returns:
        Response dictionary with success status and metadata
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
        print(f"  Has HTML: {bool(html_body)}")
        print(f"  Attachments: {len(attachments) if attachments else 0}")
        return result

    try:
        service = get_gmail_service()
        
        # Use the enhanced create_message function
        message = create_message(
            to=to,
            subject=subject,
            body_text=body,
            body_html=html_body,
            attachments=attachments,
            from_name=from_name,
            from_email=from_email
        )

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
        emails: List of dicts. keys: to, subject, body, html_body (opt), attachments (opt)
        delay_seconds: Delay between emails
        dry_run: If True, don't actually send

    Returns:
        List of results
    """
    results = []

    for i, email in enumerate(emails, 1):
        print(f"\n[{i}/{len(emails)}] Sending to {email['to']}...")

        result = send_email(
            to=email['to'],
            subject=email['subject'],
            body=email['body'],
            html_body=email.get('html_body'),
            attachments=email.get('attachments'),
            from_name=email.get('from_name', 'Qasim Jalil'),
            from_email=email.get('from_email', 'qasim@raqiminternational.com'),
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
        profile = service.users().getProfile(userId='me').execute()
        print(f"  Authenticated as: {profile['emailAddress']}")
        return True
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return False


def send_test_email(to: str):
    """Send a test email to verify setup."""
    subject = "Test Email with Attachment"
    body = "This is the plain text version of the email."
    html_body = """
    <html>
      <body>
        <h1>Hi there,</h1>
        <p>This is a <b>test email</b> from the updated B2B OSINT Tool.</p>
        <p>It includes:</p>
        <ul>
            <li>HTML formatting</li>
            <li>Attachment support</li>
        </ul>
        <br>
        <p>Best regards,<br>Qasim</p>
      </body>
    </html>
    """
    
    # Create a dummy attachment for testing
    dummy_content = b"Hello! This is a text file attachment."
    attachments = [{
        'filename': 'test_attachment.txt',
        'content': dummy_content
    }]

    result = send_email(
        to, 
        subject, 
        body, 
        html_body=html_body, 
        attachments=attachments, 
        dry_run=False
    )

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
    print("Gmail API Integration Test (With Attachments)")
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