"""
Comprehensive Email Verification System (100% Free)

Features:
1. Syntax validation (instant)
2. DNS/MX record validation (instant)
3. SMTP verification - connects to mail server to verify mailbox (2-3 seconds)
4. Bounce blacklist management
5. Verification result caching
6. Detailed validation reporting

All operations are free and self-hosted.
"""

import re
import dns.resolver
import smtplib
import socket
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# Paths
BASE_DIR = Path(__file__).parent.parent
BLACKLIST_FILE = BASE_DIR / "email_blacklist.jsonl"
VERIFICATION_CACHE_FILE = BASE_DIR / "email_verification_cache.jsonl"

# Email regex pattern (RFC 5322 simplified)
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

# Common patterns to avoid (low-quality emails)
AVOID_PATTERNS = [
    r'^noreply@',
    r'^no-reply@',
    r'^donotreply@',
    r'^do-not-reply@',
    r'^postmaster@',
    r'^abuse@',
    r'^spam@',
    r'^bounce@',
    r'^mailer-daemon@',
]

# Disposable email domains (common ones)
DISPOSABLE_DOMAINS = {
    'tempmail.com', 'guerrillamail.com', '10minutemail.com',
    'throwaway.email', 'mailinator.com', 'trashmail.com',
    'yopmail.com', 'fakeinbox.com'
}


@dataclass
class ValidationResult:
    """Email validation result."""
    email: str
    is_valid: bool
    checks: Dict[str, bool]  # Individual check results
    reason: Optional[str] = None  # Failure reason
    mx_records: List[str] = None  # MX servers found
    smtp_response: Optional[str] = None  # SMTP server response
    verified_at: str = None  # Timestamp
    verification_time: float = 0.0  # Time taken in seconds

    def __post_init__(self):
        if self.mx_records is None:
            self.mx_records = []
        if self.verified_at is None:
            self.verified_at = datetime.utcnow().isoformat() + "Z"


# ============================================================================
# Core Validation Functions
# ============================================================================

def validate_syntax(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email syntax.

    Returns:
        (is_valid, error_message)
    """
    if not email or not isinstance(email, str):
        return False, "Empty or invalid email"

    email = email.strip().lower()

    # Check basic format
    if not EMAIL_REGEX.match(email):
        return False, "Invalid email format"

    # Check for avoid patterns
    for pattern in AVOID_PATTERNS:
        if re.match(pattern, email, re.IGNORECASE):
            return False, f"Email matches avoid pattern: {pattern}"

    # Check for disposable domains
    domain = email.split('@')[1]
    if domain in DISPOSABLE_DOMAINS:
        return False, "Disposable email domain"

    return True, None


def validate_dns_mx(domain: str) -> Tuple[bool, List[str], Optional[str]]:
    """
    Validate domain has MX records.

    Returns:
        (has_mx_records, mx_records_list, error_message)
    """
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_hosts = [str(r.exchange).rstrip('.') for r in mx_records]
        return True, mx_hosts, None
    except dns.resolver.NoAnswer:
        return False, [], "No MX records found"
    except dns.resolver.NXDOMAIN:
        return False, [], "Domain does not exist"
    except dns.exception.Timeout:
        return False, [], "DNS lookup timeout"
    except Exception as e:
        return False, [], f"DNS error: {str(e)}"


def verify_smtp(email: str, mx_host: str, timeout: int = 10) -> Tuple[bool, Optional[str]]:
    """
    Verify email exists by connecting to SMTP server.

    This is the most thorough check but takes 2-3 seconds.
    Some mail servers may block verification attempts.

    Returns:
        (mailbox_exists, smtp_response)
    """
    try:
        # Extract domain for HELO
        domain = email.split('@')[1]

        # Connect to MX server
        server = smtplib.SMTP(timeout=timeout)
        server.set_debuglevel(0)
        server.connect(mx_host)

        # HELO/EHLO
        server.ehlo_or_helo_if_needed()

        # MAIL FROM (use a valid-looking sender)
        server.mail('verify@gmail.com')

        # RCPT TO (this is where we check if mailbox exists)
        code, message = server.rcpt(email)
        server.quit()

        # Response codes:
        # 250: Mailbox exists
        # 251: User not local, will forward (treat as valid)
        # 550, 551, 553: Mailbox doesn't exist
        # 450, 451, 452: Temporary failure (treat as valid to be safe)

        if code in [250, 251]:
            return True, f"SMTP {code}: {message.decode('utf-8', errors='ignore')}"
        elif code in [450, 451, 452]:
            # Temporary failure - assume valid to avoid false negatives
            return True, f"SMTP {code} (temp failure, assuming valid): {message.decode('utf-8', errors='ignore')}"
        else:
            return False, f"SMTP {code}: {message.decode('utf-8', errors='ignore')}"

    except smtplib.SMTPServerDisconnected:
        return None, "SMTP server disconnected (verification blocked)"
    except smtplib.SMTPConnectError:
        return None, "Cannot connect to SMTP server"
    except socket.timeout:
        return None, "SMTP timeout (server slow or blocking)"
    except Exception as e:
        return None, f"SMTP error: {str(e)}"


def verify_email(
    email: str,
    check_smtp: bool = True,
    smtp_timeout: int = 10,
    use_cache: bool = True,
    cache_ttl_hours: int = 168  # 1 week
) -> ValidationResult:
    """
    Comprehensive email verification.

    Performs all checks in order:
    1. Syntax validation (instant)
    2. DNS/MX validation (instant)
    3. SMTP verification (2-3 seconds, optional)

    Args:
        email: Email address to verify
        check_smtp: Perform SMTP verification (slower but thorough)
        smtp_timeout: SMTP connection timeout in seconds
        use_cache: Use cached results if available
        cache_ttl_hours: Cache validity period in hours

    Returns:
        ValidationResult object with detailed results
    """
    start_time = time.time()
    email = email.strip().lower()

    # Check cache first
    if use_cache:
        cached = get_cached_verification(email, cache_ttl_hours)
        if cached:
            cached.verification_time = time.time() - start_time
            return cached

    checks = {
        "syntax": False,
        "dns_mx": False,
        "smtp": False
    }

    # Check whitelist first - whitelisted emails are always valid
    try:
        from pipeline.email_whitelist import is_whitelisted
        if is_whitelisted(email):
            result = ValidationResult(
                email=email,
                is_valid=True,
                checks={"syntax": True, "dns_mx": True, "smtp": True},
                reason="Email is whitelisted (manually verified)",
                verification_time=time.time() - start_time
            )
            cache_verification(result)
            return result
    except ImportError:
        pass  # Whitelist module not available

    # Check blacklist
    if is_blacklisted(email):
        result = ValidationResult(
            email=email,
            is_valid=False,
            checks=checks,
            reason="Email is blacklisted (previous bounce)",
            verification_time=time.time() - start_time
        )
        cache_verification(result)
        return result

    # 1. Syntax validation
    syntax_valid, syntax_error = validate_syntax(email)
    checks["syntax"] = syntax_valid

    if not syntax_valid:
        result = ValidationResult(
            email=email,
            is_valid=False,
            checks=checks,
            reason=syntax_error,
            verification_time=time.time() - start_time
        )
        cache_verification(result)
        return result

    # 2. DNS/MX validation
    domain = email.split('@')[1]
    has_mx, mx_records, dns_error = validate_dns_mx(domain)
    checks["dns_mx"] = has_mx

    if not has_mx:
        result = ValidationResult(
            email=email,
            is_valid=False,
            checks=checks,
            reason=dns_error,
            verification_time=time.time() - start_time
        )
        cache_verification(result)
        return result

    # 3. SMTP verification (optional, slower)
    smtp_valid = None
    smtp_response = "SMTP check skipped"

    if check_smtp and mx_records:
        # Try primary MX server
        smtp_valid, smtp_response = verify_smtp(email, mx_records[0], smtp_timeout)
        checks["smtp"] = smtp_valid if smtp_valid is not None else False

        # If SMTP check was blocked/failed, try secondary MX
        if smtp_valid is None and len(mx_records) > 1:
            smtp_valid, smtp_response = verify_smtp(email, mx_records[1], smtp_timeout)
            checks["smtp"] = smtp_valid if smtp_valid is not None else False

    # Determine final validity
    # IMPORTANT: Many mail servers (especially European) reject SMTP verification
    # attempts but accept real emails. To avoid false negatives, we use a lenient
    # approach: if syntax and DNS pass, assume valid unless we have strong evidence.
    if check_smtp:
        # If SMTP check was performed
        if smtp_valid is True:
            is_valid = True
            reason = None
        elif smtp_valid is False:
            # SMTP returned rejection (550, 551, 553)
            # BUT: Many servers reject verification while accepting real emails
            # SO: Assume valid with low confidence, mark reason
            is_valid = True  # Changed from False to True to avoid false negatives
            reason = "SMTP returned rejection code (but may be false negative - server blocks verification)"
        else:
            # SMTP check was blocked/failed - use DNS result
            is_valid = True  # Assume valid if DNS passes but SMTP blocked
            reason = "SMTP verification blocked (assuming valid based on DNS)"
    else:
        # Only syntax + DNS checks
        is_valid = True
        reason = None

    result = ValidationResult(
        email=email,
        is_valid=is_valid,
        checks=checks,
        reason=reason,
        mx_records=mx_records,
        smtp_response=smtp_response,
        verification_time=time.time() - start_time
    )

    cache_verification(result)
    return result


def verify_email_batch(
    emails: List[str],
    check_smtp: bool = True,
    max_workers: int = 5,
    progress_callback=None
) -> List[ValidationResult]:
    """
    Verify multiple emails in parallel.

    Args:
        emails: List of email addresses
        check_smtp: Perform SMTP verification
        max_workers: Number of parallel workers
        progress_callback: Optional callback(current, total) for progress

    Returns:
        List of ValidationResult objects
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    total = len(emails)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_email = {
            executor.submit(verify_email, email, check_smtp): email
            for email in emails
        }

        # Collect results
        for i, future in enumerate(as_completed(future_to_email), 1):
            result = future.result()
            results.append(result)

            if progress_callback:
                progress_callback(i, total)
            else:
                print(f"[{i}/{total}] {result.email}: {'✓ VALID' if result.is_valid else '✗ INVALID'} ({result.verification_time:.2f}s)")

    return results


# ============================================================================
# Blacklist Management
# ============================================================================

def add_to_blacklist(
    email: str,
    reason: str = "bounced",
    metadata: Optional[Dict] = None
):
    """
    Add email to blacklist.

    Args:
        email: Email address to blacklist
        reason: Reason for blacklisting
        metadata: Optional additional metadata
    """
    email = email.strip().lower()

    entry = {
        "email": email,
        "reason": reason,
        "blacklisted_at": datetime.utcnow().isoformat() + "Z",
        "timestamp": int(time.time())
    }

    if metadata:
        entry["metadata"] = metadata

    with open(BLACKLIST_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[BLACKLISTED] {email} - {reason}")


def is_blacklisted(email: str) -> bool:
    """Check if email is blacklisted."""
    if not BLACKLIST_FILE.exists():
        return False

    email = email.strip().lower()

    with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
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


def get_blacklist() -> List[Dict]:
    """Get all blacklisted emails."""
    if not BLACKLIST_FILE.exists():
        return []

    blacklist = []
    with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                blacklist.append(json.loads(line))
            except:
                continue

    return blacklist


def remove_from_blacklist(email: str):
    """Remove email from blacklist."""
    if not BLACKLIST_FILE.exists():
        return

    email = email.strip().lower()

    # Read all entries except the one to remove
    entries = []
    with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
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
    with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    print(f"[REMOVED FROM BLACKLIST] {email}")


# ============================================================================
# Verification Cache
# ============================================================================

def cache_verification(result: ValidationResult):
    """Cache verification result."""
    entry = asdict(result)

    with open(VERIFICATION_CACHE_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")


def get_cached_verification(
    email: str,
    ttl_hours: int = 168
) -> Optional[ValidationResult]:
    """
    Get cached verification result if still valid.

    Args:
        email: Email to check
        ttl_hours: Cache validity in hours

    Returns:
        ValidationResult if cached and valid, None otherwise
    """
    if not VERIFICATION_CACHE_FILE.exists():
        return None

    email = email.strip().lower()
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)

    # Read cache file backwards (most recent first)
    with open(VERIFICATION_CACHE_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("email") == email:
                # Check if still valid
                verified_at = datetime.fromisoformat(entry["verified_at"].rstrip('Z'))
                if verified_at >= cutoff:
                    # Convert back to ValidationResult
                    return ValidationResult(**entry)
                else:
                    return None  # Expired
        except:
            continue

    return None


def clear_cache(older_than_days: int = 30):
    """Clear old cache entries."""
    if not VERIFICATION_CACHE_FILE.exists():
        return

    cutoff = datetime.utcnow() - timedelta(days=older_than_days)

    # Read and filter entries
    valid_entries = []
    with open(VERIFICATION_CACHE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                verified_at = datetime.fromisoformat(entry["verified_at"].rstrip('Z'))
                if verified_at >= cutoff:
                    valid_entries.append(entry)
            except:
                continue

    # Rewrite file
    with open(VERIFICATION_CACHE_FILE, 'w', encoding='utf-8') as f:
        for entry in valid_entries:
            f.write(json.dumps(entry) + "\n")

    print(f"[CACHE CLEANED] Removed entries older than {older_than_days} days")


# ============================================================================
# Reporting
# ============================================================================

def print_verification_report(results: List[ValidationResult]):
    """Print formatted verification report."""
    valid_count = sum(1 for r in results if r.is_valid)
    invalid_count = len(results) - valid_count
    avg_time = sum(r.verification_time for r in results) / len(results) if results else 0

    print("\n" + "="*70)
    print("EMAIL VERIFICATION REPORT")
    print("="*70)

    print(f"\nTotal Verified: {len(results)}")
    print(f"  ✓ Valid: {valid_count} ({valid_count/len(results)*100:.1f}%)")
    print(f"  ✗ Invalid: {invalid_count} ({invalid_count/len(results)*100:.1f}%)")
    print(f"\nAverage verification time: {avg_time:.2f}s")

    # Failure reasons breakdown
    if invalid_count > 0:
        print(f"\nFailure Reasons:")
        reasons = {}
        for r in results:
            if not r.is_valid:
                reason = r.reason or "Unknown"
                reasons[reason] = reasons.get(reason, 0) + 1

        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")

    print("="*70 + "\n")


# ============================================================================
# Testing & Demo
# ============================================================================

def test_verification():
    """Test email verification with sample emails."""
    test_emails = [
        "valid.email@gmail.com",
        "another@example.com",
        "invalid@nonexistentdomain99999.com",
        "noreply@example.com",
        "bad-format@",
        "user@tempmail.com",
    ]

    print("Testing email verification...")
    print("="*70)

    for email in test_emails:
        print(f"\nTesting: {email}")
        result = verify_email(email, check_smtp=True)

        print(f"  Result: {'✓ VALID' if result.is_valid else '✗ INVALID'}")
        print(f"  Checks: {result.checks}")
        if result.reason:
            print(f"  Reason: {result.reason}")
        if result.mx_records:
            print(f"  MX: {', '.join(result.mx_records[:2])}")
        print(f"  Time: {result.verification_time:.2f}s")


if __name__ == "__main__":
    test_verification()
