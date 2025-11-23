"""
Quick Test Script for Email Verification System

Run this to test your email verification setup.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_dependencies():
    """Test if required dependencies are installed."""
    print("="*70)
    print("TESTING DEPENDENCIES")
    print("="*70)

    try:
        import dns.resolver
        print("✓ dnspython: installed")
    except ImportError:
        print("✗ dnspython: NOT installed")
        print("  Install with: pip install dnspython")
        return False

    try:
        from pipeline.email_verifier import verify_email
        print("✓ email_verifier module: available")
    except ImportError as e:
        print(f"✗ email_verifier module: ERROR - {e}")
        return False

    try:
        from pipeline.bounce_monitor import check_bounces
        print("✓ bounce_monitor module: available")
    except ImportError as e:
        print(f"✗ bounce_monitor module: ERROR - {e}")
        return False

    try:
        from pipeline.verified_email_sender import send_verified_emails
        print("✓ verified_email_sender module: available")
    except ImportError as e:
        print(f"✗ verified_email_sender module: ERROR - {e}")
        return False

    print("\n✓ All dependencies installed!\n")
    return True


def test_basic_verification():
    """Test basic email verification functionality."""
    from pipeline.email_verifier import verify_email

    print("="*70)
    print("TESTING BASIC VERIFICATION")
    print("="*70)

    test_cases = [
        ("valid@gmail.com", True, "Valid Gmail address"),
        ("invalid@", False, "Invalid format"),
        ("noreply@example.com", False, "Avoid pattern (noreply)"),
        ("test@nonexistentdomain99999.com", False, "Non-existent domain"),
    ]

    print("\nRunning test cases (without SMTP to save time)...\n")

    passed = 0
    failed = 0

    for email, should_be_valid, description in test_cases:
        print(f"Testing: {email}")
        print(f"  Description: {description}")

        result = verify_email(email, check_smtp=False, use_cache=False)

        if result.is_valid == should_be_valid:
            print(f"  ✓ PASS - Correctly identified as {'valid' if result.is_valid else 'invalid'}")
            passed += 1
        else:
            print(f"  ✗ FAIL - Expected {'valid' if should_be_valid else 'invalid'}, got {'valid' if result.is_valid else 'invalid'}")
            failed += 1

        if result.reason:
            print(f"  Reason: {result.reason}")

        print(f"  Time: {result.verification_time:.3f}s")
        print()

    print(f"Results: {passed} passed, {failed} failed")
    print()

    return failed == 0


def test_smtp_verification():
    """Test SMTP verification with a real email."""
    from pipeline.email_verifier import verify_email

    print("="*70)
    print("TESTING SMTP VERIFICATION")
    print("="*70)

    print("\nTesting with a real Gmail address (this will take 2-3 seconds)...")
    print("Testing: gmail.com domain\n")

    # Test with a Gmail address (Gmail allows verification)
    result = verify_email("test@gmail.com", check_smtp=True, use_cache=False)

    print(f"Email: test@gmail.com")
    print(f"Valid: {result.is_valid}")
    print(f"Checks performed: {result.checks}")

    if result.mx_records:
        print(f"MX Records: {', '.join(result.mx_records[:3])}")

    if result.smtp_response:
        print(f"SMTP Response: {result.smtp_response}")

    if result.reason:
        print(f"Reason: {result.reason}")

    print(f"Time taken: {result.verification_time:.2f}s")
    print()

    return True


def test_blacklist():
    """Test blacklist functionality."""
    from pipeline.email_verifier import (
        add_to_blacklist,
        is_blacklisted,
        remove_from_blacklist,
        get_blacklist
    )

    print("="*70)
    print("TESTING BLACKLIST")
    print("="*70)

    test_email = "test-blacklist@example.com"

    print(f"\n1. Adding {test_email} to blacklist...")
    add_to_blacklist(test_email, reason="Test entry")

    print(f"2. Checking if blacklisted...")
    if is_blacklisted(test_email):
        print(f"   ✓ Correctly identified as blacklisted")
    else:
        print(f"   ✗ ERROR: Not found in blacklist")
        return False

    print(f"3. Removing from blacklist...")
    remove_from_blacklist(test_email)

    print(f"4. Verifying removal...")
    if not is_blacklisted(test_email):
        print(f"   ✓ Correctly removed from blacklist")
    else:
        print(f"   ✗ ERROR: Still in blacklist")
        return False

    print("\n✓ Blacklist tests passed!\n")
    return True


def test_batch_verification():
    """Test batch verification."""
    from pipeline.email_verifier import verify_email_batch

    print("="*70)
    print("TESTING BATCH VERIFICATION")
    print("="*70)

    emails = [
        "test1@gmail.com",
        "test2@yahoo.com",
        "invalid@nonexistent999.com",
        "bad-format@",
        "noreply@example.com"
    ]

    print(f"\nVerifying {len(emails)} emails in batch (without SMTP)...")
    print("-" * 70)

    results = verify_email_batch(emails, check_smtp=False, max_workers=3)

    valid = [r.email for r in results if r.is_valid]
    invalid = [r.email for r in results if not r.is_valid]

    print(f"\n✓ Batch verification complete")
    print(f"  Valid: {len(valid)}")
    print(f"  Invalid: {len(invalid)}")
    print()

    return True


def test_cache():
    """Test verification caching."""
    from pipeline.email_verifier import verify_email, get_cached_verification
    import time

    print("="*70)
    print("TESTING CACHE")
    print("="*70)

    test_email = "cache-test@gmail.com"

    print(f"\n1. First verification (will be cached)...")
    start = time.time()
    result1 = verify_email(test_email, check_smtp=False, use_cache=True)
    time1 = time.time() - start
    print(f"   Time: {time1:.3f}s")

    print(f"2. Second verification (should use cache)...")
    start = time.time()
    result2 = verify_email(test_email, check_smtp=False, use_cache=True)
    time2 = time.time() - start
    print(f"   Time: {time2:.3f}s")

    if time2 < time1:
        print(f"   ✓ Cache working! Second verification was {time1/time2:.1f}x faster")
    else:
        print(f"   ⚠ Cache may not be working optimally")

    print()
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*70)
    print("EMAIL VERIFICATION SYSTEM - TEST SUITE")
    print("="*70 + "\n")

    tests = [
        ("Dependencies", test_dependencies),
        ("Basic Verification", test_basic_verification),
        ("Blacklist", test_blacklist),
        ("Batch Verification", test_batch_verification),
        ("Cache", test_cache),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"⚠ {name} test had issues\n")
        except Exception as e:
            failed += 1
            print(f"✗ {name} test FAILED with error: {e}\n")

    # Optional SMTP test (slower)
    print("\n" + "="*70)
    print("OPTIONAL: SMTP Verification Test (takes 2-3 seconds)")
    print("="*70)
    response = input("\nRun SMTP test? (y/n): ").lower().strip()

    if response == 'y':
        try:
            test_smtp_verification()
        except Exception as e:
            print(f"SMTP test error: {e}")

    # Final summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"\nTests passed: {passed}")
    print(f"Tests failed: {failed}")

    if failed == 0:
        print("\n✓ All tests passed! Your email verification system is ready to use.")
        print("\nNext steps:")
        print("1. Read EMAIL_VERIFICATION_GUIDE.md for usage instructions")
        print("2. Update your email sending code to use verified_email_sender.py")
        print("3. Setup bounce monitoring")
    else:
        print("\n⚠ Some tests failed. Please check the errors above.")

    print("="*70 + "\n")


if __name__ == "__main__":
    run_all_tests()
