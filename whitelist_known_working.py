"""
Quick script to whitelist domains with known-working emails

Run this after you've confirmed emails are working but verification marked them as invalid.
"""

from pipeline.email_whitelist import whitelist_domain_emails

# Domains you confirmed are working
KNOWN_WORKING_DOMAINS = [
    "r-gol.com",           # Email delivered and seen
    "ab1gk.com",
    "gannonsports.co.uk",
    "gksaver.com",
    "goalkeeperglove.com",
    "gripsport.co.za",
    "primefocusgoalkeeping.com",
    "soccervillage.com",
    "stanno.com"
]

print("="*70)
print("WHITELISTING KNOWN-WORKING DOMAINS")
print("="*70)
print(f"\nWhitelisting emails from {len(KNOWN_WORKING_DOMAINS)} domains...\n")

for domain in KNOWN_WORKING_DOMAINS:
    print(f"Processing {domain}...")
    whitelist_domain_emails(
        domain,
        reason="Email confirmed working (server blocks verification)"
    )

print("\n" + "="*70)
print("COMPLETE")
print("="*70)
print(f"\n✓ Whitelisted emails from {len(KNOWN_WORKING_DOMAINS)} domains")
print("\nNext steps:")
print("1. Re-run verification: python verify_emails.py --force")
print("2. Check results: cat email_verification_report.jsonl")
print("3. Save drafts: python save_drafts_to_gmail.py --verify-email")
print("="*70 + "\n")
