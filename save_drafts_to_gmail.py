"""
Save Email Drafts to Gmail

Saves generated email drafts to your Gmail account as draft messages.
All subject line options are included in the email body so you can choose
which one to use when reviewing the draft.

Usage:
    # Save all drafts to Gmail (all subject lines included in body)
    python save_drafts_to_gmail.py

    # Save specific domains only
    python save_drafts_to_gmail.py --domains theoneglove.com bravegk.com

    # Customize delay between drafts (default: 2 seconds)
    python save_drafts_to_gmail.py --delay 3.0

    # No delay (not recommended - may trigger rate limits)
    python save_drafts_to_gmail.py --delay 0

Note: All 3-5 subject line options will appear at the top of each draft.
      Simply choose one, move it to the subject field, and delete the rest.

      A 2-second delay is added between drafts by default to prevent Gmail
      rate limiting. You can adjust this with --delay parameter.
"""

import os
import json
import argparse
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from pipeline.gmail_sender import get_gmail_service, create_message


def load_email_drafts(drafts_file: str = "email_drafts.jsonl") -> List[Dict]:
    """
    Load email drafts from JSONL file.

    Returns:
        List of draft dicts with:
            - domain: str
            - subject_lines: [str]
            - email_body: str
    """
    drafts = []

    if not os.path.exists(drafts_file):
        print(f"✗ No email drafts found at {drafts_file}")
        print(f"  Run: python run_agentic_flow.py <domains> to generate drafts")
        return []

    with open(drafts_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                draft = json.loads(line)
                if 'domain' in draft:
                    drafts.append(draft)
            except json.JSONDecodeError:
                continue

    return drafts


def get_contact_for_domain(domain: str, verify_email: bool = False) -> Optional[Dict]:
    """
    Get primary contact email for a domain from extracted data.
    Tries profile.json first, then falls back to all_companies.jsonl index.

    Args:
        domain: Company domain
        verify_email: If True, check email verification status and skip invalid emails

    Returns:
        {
            "email": str,
            "name": str (if available),
            "role": str (if available),
            "email_valid": bool (if verification checked),
            "email_invalid_reason": str (if email invalid)
        }
        Returns None if no valid email found
    """
    # Method 1: Try to load from profile.json (per-domain file)
    profile_file = Path("extracted_data") / "companies" / domain / "profile.json"
    if profile_file.exists():
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                profile = json.load(f)

                # Extract emails from main_contacts
                main_contacts = profile.get("main_contacts", {}) or {}
                emails = main_contacts.get("email", [])
                email_verification = main_contacts.get("email_verification", {})

                if emails:
                    # Define generic prefixes to de-prioritize
                    generic_prefixes = ("info", "sales", "hello", "contact", "support", "admin")

                    # If verify_email is True, filter out invalid emails
                    if verify_email and email_verification:
                        valid_emails = [
                            e for e in emails
                            if email_verification.get(e, {}).get("is_valid", False)
                        ]

                        if not valid_emails:
                            # All emails are invalid
                            first_email = emails[0] if emails else None
                            if first_email and first_email in email_verification:
                                reason = email_verification[first_email].get("reason", "Unknown")
                                print(f"  [INVALID EMAIL] {domain} - {first_email}: {reason}")
                                return None
                            else:
                                print(f"  [NO VERIFICATION] {domain} - Email not verified yet")
                                return None

                        # Use valid emails only
                        emails = valid_emails

                    # Separate personal vs generic
                    personal_emails = [e for e in emails if not e.lower().startswith(generic_prefixes)]
                    generic_emails = [e for e in emails if e.lower().startswith(generic_prefixes)]

                    # Prefer personal, fallback to generic, then first email if needed
                    selected_email = (
                        personal_emails[0]
                        if personal_emails else
                        (generic_emails[0] if generic_emails else emails[0])
                    )

                    result = {
                        "email": selected_email,
                        "name": None,
                        "role": None
                    }

                    # Add verification info if available
                    if verify_email and selected_email in email_verification:
                        verification_info = email_verification[selected_email]
                        result["email_valid"] = verification_info.get("is_valid", False)
                        if not result["email_valid"]:
                            result["email_invalid_reason"] = verification_info.get("reason", "Unknown")

                    return result
        except Exception as e:
            print(f"  [WARN] Could not load profile for {domain}: {e}")

    # Method 2: Fallback to global index (all_companies.jsonl)
    index_file = Path("extracted_data") / "indexes" / "all_companies.jsonl"
    if index_file.exists():
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        company = json.loads(line)
                        if company.get("domain") == domain:
                            emails = company.get("email", [])
                            if emails:
                                # Prioritize: sales@ > info@ > hello@ > contact@ > first email
                                priority_prefixes = ["sales", "info", "hello", "contact"]

                                for prefix in priority_prefixes:
                                    for email in emails:
                                        if email.lower().startswith(prefix):
                                            return {
                                                "email": email,
                                                "name": None,
                                                "role": None
                                            }

                                # Return first email if no priority match
                                return {
                                    "email": emails[0],
                                    "name": None,
                                    "role": None
                                }
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"  [WARN] Could not load index for {domain}: {e}")

    return None


def update_draft_timestamp(
    domain: str,
    drafts_file: str = "email_drafts.jsonl",
    timestamp_field: str = "gmail_draft_created_at"
) -> bool:
    """
    Update the draft entry for a domain with a timestamp indicating when
    the Gmail draft was created.

    Args:
        domain: The domain to update
        drafts_file: Path to the email drafts JSONL file
        timestamp_field: Name of the timestamp field to add/update

    Returns:
        True if update successful, False otherwise
    """
    if not os.path.exists(drafts_file):
        print(f"  [WARN] Drafts file not found: {drafts_file}")
        return False

    try:
        # Read all entries
        entries = []
        with open(drafts_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue

        # Find and update the matching domain
        updated = False
        for entry in entries:
            if entry.get('domain') == domain:
                # Add timestamp in ISO format
                entry[timestamp_field] = datetime.utcnow().isoformat() + 'Z'
                updated = True
                break

        if not updated:
            print(f"  [WARN] Domain {domain} not found in {drafts_file}")
            return False

        # Write all entries back to file
        with open(drafts_file, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        return True

    except Exception as e:
        print(f"  [ERROR] Failed to update timestamp for {domain}: {e}")
        return False


def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    from_name: str = "Qasim Jalil",
    from_email: str = "qasim@raqiminternational.com"
) -> Dict:
    """
    Create a draft message in Gmail.

    Returns:
        {
            "success": bool,
            "draft_id": str (if success),
            "error": str (if failed),
            "to": str,
            "subject": str
        }
    """
    result = {
        "to": to,
        "subject": subject,
        "success": False
    }

    try:
        service = get_gmail_service()

        # Create message
        message = create_message(to, subject, body, from_name, from_email, html=False)

        # Create draft
        draft = service.users().drafts().create(
            userId='me',
            body={'message': message}
        ).execute()

        result.update({
            "success": True,
            "draft_id": draft['id']
        })

        print(f"[✓] Draft created: {to}")
        print(f"    Subject: {subject}")
        print(f"    Draft ID: {draft['id']}")

        return result

    except Exception as e:
        result.update({
            "success": False,
            "error": str(e)
        })
        print(f"[✗] Failed to create draft for {to}: {e}")
        return result


def save_drafts_to_gmail(
    drafts: List[Dict],
    subject_index: int = 0,
    drafts_file: str = "email_drafts.jsonl",
    delay_seconds: float = 2.0,
    verify_email: bool = False
):
    """
    Save email drafts to Gmail as draft messages.
    All subject line options will be included in the email body for manual selection.
    Updates the draft entry with a timestamp when successfully saved.

    Args:
        drafts: List of email drafts
        subject_index: (Deprecated - not used) All subject lines included in body
        drafts_file: Path to email drafts JSONL file for timestamp updates
        delay_seconds: Delay in seconds between creating drafts (default: 2.0)
                      Helps prevent Gmail rate limiting
        verify_email: If True, skip drafts for invalid emails (default: False)
    """
    print(f"\n{'='*60}")
    print(f"SAVE DRAFTS TO GMAIL")
    print(f"{'='*60}")
    print(f"All subject line options will be included in draft body for manual selection")
    print(f"Delay between drafts: {delay_seconds} seconds (to prevent rate limiting)")
    if verify_email:
        print(f"Email verification: ENABLED (skipping invalid emails)")
    print()

    results = []
    created_count = 0
    skipped_count = 0
    skipped_invalid_email = 0
    failed_count = 0

    for i, draft in enumerate(drafts, 1):
        domain = draft['domain']
        subject_lines = draft.get('subject_lines', [])
        email_body = draft.get('email_body', '')

        print(f"\n[{i}/{len(drafts)}] Processing {domain}...")

        # Get contact
        contact = get_contact_for_domain(domain, verify_email=verify_email)
        if not contact or not contact.get('email'):
            if verify_email:
                print(f"[SKIP] {domain} - No valid email found")
                skipped_invalid_email += 1
            else:
                print(f"[SKIP] {domain} - No contact email found")
                skipped_count += 1
            continue

        recipient_email = contact['email']
        recipient_name = contact.get('name')

        # Format subject line options to include in body
        subject_options_text = ""
        if subject_lines and len(subject_lines) > 0:
            subject_options_text = "[SUBJECT LINE OPTIONS - Choose one and move to subject field]\n"
            for idx, subj in enumerate(subject_lines, 1):
                subject_options_text += f"{idx}. {subj}\n"
            subject_options_text += "\n" + "="*60 + "\n\n"

            # Use first subject line as draft subject
            draft_subject = subject_lines[0]
        else:
            draft_subject = "Partnership opportunity with Raqim International"
            print(f"  [WARN] No subject lines found, using generic")

        # Personalize email body if name available
        personalized_body = email_body
        if recipient_name and "[Name]" in email_body:
            personalized_body = email_body.replace("[Name]", recipient_name)

        # Prepend subject line options to email body
        final_body = subject_options_text + personalized_body

        # Create draft
        result = create_gmail_draft(
            to=recipient_email,
            subject=draft_subject,
            body=final_body,
            from_name="Qasim Jalil",
            from_email="qasim@raqiminternational.com"
        )

        results.append(result)

        if result['success']:
            created_count += 1
            # Update timestamp in drafts file
            if update_draft_timestamp(domain, drafts_file):
                print(f"    [OK] Timestamp updated in {drafts_file}")

            # Add delay between drafts (except after the last one)
            if i < len(drafts):
                print(f"    Waiting {delay_seconds} seconds before next draft...")
                time.sleep(delay_seconds)
        else:
            failed_count += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"COMPLETE")
    print(f"{'='*60}")
    print(f"  ✓ Drafts created: {created_count}")
    print(f"  ⊘ Skipped (no email): {skipped_count}")
    if verify_email:
        print(f"  ⊗ Skipped (invalid email): {skipped_invalid_email}")
    print(f"  ✗ Failed: {failed_count}")
    print(f"{'='*60}\n")

    if created_count > 0:
        print("✓ Drafts saved to Gmail!")
        print("  Go to Gmail → Drafts to review and send")

    return results


def main():
    parser = argparse.ArgumentParser(description="Save email drafts to Gmail")
    parser.add_argument(
        "--domains",
        nargs="*",
        help="Save only these domains (if not specified, saves all drafts)"
    )
    parser.add_argument(
        "--subject-index",
        type=int,
        default=0,
        help="Which subject line to use (0=first, 1=second, etc. Default: 0)"
    )
    parser.add_argument(
        "--drafts-file",
        type=str,
        default="email_drafts.jsonl",
        help="Path to email drafts file (default: email_drafts.jsonl)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay in seconds between creating drafts (default: 2.0, to prevent rate limiting)"
    )
    parser.add_argument(
        "--verify-email",
        action="store_true",
        help="Verify emails before creating drafts (skip invalid emails)"
    )

    args = parser.parse_args()

    # Load drafts
    all_drafts = load_email_drafts(args.drafts_file)

    if not all_drafts:
        print("✗ No email drafts found")
        print("\nTo generate drafts, run:")
        print("  python run_agentic_flow.py <domains>")
        return

    # Filter by domains if specified
    if args.domains:
        drafts = [d for d in all_drafts if d['domain'] in args.domains]
        if not drafts:
            print(f"✗ No drafts found for domains: {', '.join(args.domains)}")
            return
    else:
        drafts = all_drafts

    print(f"Loaded {len(drafts)} email drafts")

    if args.verify_email:
        print("\n⚠ Email verification is ENABLED")
        print("  Drafts will only be created for companies with valid emails")
        print("  Run 'python verify_emails.py' first to verify all emails\n")

    # Save drafts to Gmail
    save_drafts_to_gmail(
        drafts=drafts,
        subject_index=args.subject_index,
        drafts_file=args.drafts_file,
        delay_seconds=args.delay,
        verify_email=args.verify_email
    )


if __name__ == "__main__":
    main()
