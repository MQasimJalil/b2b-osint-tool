"""
Contact Enrichment - Standalone Script

Enriches company profiles with additional contact information:
- Phone numbers
- WhatsApp numbers
- LinkedIn profiles (company and employees)
- Social media handles

Default workflow (optimized):
- Google queries → Social media discovery → LinkedIn discovery
- Website scraping is optional (use --sources to enable)

Priority-based search:
- Companies WITH valid emails: Lenient mode (quick search)
- Companies WITHOUT valid emails: Aggressive mode (extensive search)

Usage:
    # Enrich all companies (default: Google + social + LinkedIn)
    python enrich_contacts.py --all

    # Enrich specific domains
    python enrich_contacts.py example.com company.com

    # Aggressive mode for all
    python enrich_contacts.py --all --aggressive

    # Dry run (no updates)
    python enrich_contacts.py --all --dry-run

    # Enable all sources (website + Google + LinkedIn + social)
    python enrich_contacts.py --all --sources all

    # Only use specific sources
    python enrich_contacts.py --all --sources social,linkedin

    # Include website scraping (optional)
    python enrich_contacts.py --all --sources website,google,social,linkedin
"""

import json
import argparse
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from pipeline.contact_enricher import ContactEnricher, EnrichedContact
from pipeline.sources.website_scraper import WebsiteContactScraper
from pipeline.sources.google_search import GoogleContactSearch
from pipeline.sources.linkedin_scraper import LinkedInDiscovery
from pipeline.sources.social_scraper import SocialMediaScraper
from pipeline.sources.social_discovery import SocialMediaDiscovery
from pipeline.contact_validators import (
    validate_phone,
    validate_whatsapp,
    validate_linkedin,
    validate_social
)

# Setup logging - cleaner output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('duckduckgo_search').setLevel(logging.WARNING)
logging.getLogger('primp').setLevel(logging.WARNING)
logging.getLogger('rquest').setLevel(logging.WARNING)
logging.getLogger('cookie_store').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Paths
BASE_DIR = Path(__file__).parent
COMPANIES_DIR = BASE_DIR / 'extracted_data' / 'companies'
ENRICHMENT_REPORT = BASE_DIR / 'contact_enrichment_report.jsonl'


def get_all_domains() -> List[str]:
    """Get list of all extracted company domains."""
    if not COMPANIES_DIR.exists():
        return []

    domains = []
    for company_dir in COMPANIES_DIR.iterdir():
        if company_dir.is_dir():
            profile_path = company_dir / 'profile.json'
            if profile_path.exists():
                domains.append(company_dir.name)

    return sorted(domains)


def load_profile(domain: str) -> Optional[dict]:
    """Load company profile."""
    profile_path = COMPANIES_DIR / domain / 'profile.json'

    if not profile_path.exists():
        logger.warning(f"Profile not found for {domain}")
        return None

    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load profile for {domain}: {e}")
        return None


def enrich_company(
    domain: str,
    sources: List[str],
    force_mode: str = None,
    dry_run: bool = False
) -> bool:
    """
    Enrich a single company with contact information.

    Args:
        domain: Company domain
        sources: List of sources to use (website, google, linkedin, social)
        force_mode: Force search mode ('lenient' or 'aggressive'), None for auto
        dry_run: If True, don't update profile

    Returns:
        True if successful
    """
    print(f"\n{'='*70}")
    print(f"ENRICHING: {domain}")
    print(f"{'='*70}")

    # Load profile
    profile = load_profile(domain)
    if not profile:
        return False

    # Initialize enricher
    enricher = ContactEnricher()

    # Determine search mode
    if force_mode:
        search_mode = force_mode
    else:
        search_mode = enricher.determine_search_mode(profile)

    print(f"Search mode: {search_mode.upper()} | Sources: {', '.join(sources)}")

    # Collect results from all sources
    all_results = []

    # 1. Enrich from existing profile data
    profile_result = enricher.enrich_from_profile(profile)
    all_results.append(profile_result)

    # Track if we need to save updated social links
    social_links_updated = False
    company_name = profile.get('company', domain.split('.')[0])

    # 2. Website scraping
    if 'website' in sources:
        try:
            print(f"[*] Scraping website...")
            scraper = WebsiteContactScraper(max_pages=5 if search_mode == 'aggressive' else 3)
            website_contacts = scraper.scrape_domain(domain, search_mode)

            # Convert to EnrichedContact objects and add to result
            for phone_match in website_contacts['phones']:
                validation = validate_phone(phone_match.value)
                if validation.is_valid:
                    profile_result.phones.append(EnrichedContact(
                        type='phone',
                        value=validation.normalized_value,
                        confidence=phone_match.confidence,
                        source=phone_match.source,
                        metadata=validation.metadata
                    ))

            for wa_match in website_contacts['whatsapp']:
                validation = validate_whatsapp(wa_match.value)
                if validation.is_valid:
                    profile_result.whatsapp.append(EnrichedContact(
                        type='whatsapp',
                        value=validation.normalized_value,
                        confidence=wa_match.confidence,
                        source=wa_match.source,
                        metadata=validation.metadata
                    ))

            for li_match in website_contacts['linkedin']:
                validation = validate_linkedin(li_match.value)
                if validation.is_valid:
                    profile_result.linkedin_profiles.append(EnrichedContact(
                        type=li_match.type,
                        value=validation.normalized_value,
                        confidence=li_match.confidence,
                        source=li_match.source,
                        metadata=validation.metadata
                    ))

            print(f"  Found: {len(website_contacts['phones'])} phones, {len(website_contacts['whatsapp'])} WhatsApp")

        except Exception as e:
            logger.error(f"Website scraping failed: {e}")

    # 3. Discover social media profiles FIRST (before scraping them)
    discovered_social = {}
    if 'linkedin' in sources or 'social' in sources:
        try:
            print(f"[*] Discovering social media profiles...")
            _social_discovery = SocialMediaDiscovery()
            existing_social = profile.get('social_media', {})

            discovered_social = _social_discovery.discover_social_profiles(
                domain=domain,
                company_name=company_name,
                existing_social=existing_social,
                mode=search_mode
            )

            _social_discovery.close_driver()

            # Check if we found new social links (compare valid non-empty links)
            valid_existing_count = len([v for v in existing_social.values() if v and v.strip()])
            valid_discovered_count = len([v for v in discovered_social.values() if v and v.strip()])
            new_count = valid_discovered_count - valid_existing_count
            if new_count > 0 or valid_discovered_count > valid_existing_count:
                social_links_updated = True
                print(f"  Discovered {valid_discovered_count} total ({new_count} new):")
                for platform, url in discovered_social.items():
                    if url and url.strip():  # Only show non-empty URLs
                        existing_url = existing_social.get(platform, '')
                        is_new = platform not in existing_social or not existing_url or not existing_url.strip()
                        marker = "[NEW]" if is_new else "[EXISTING]"
                        print(f"    {marker} {platform.title()}: {url}")
            else:
                valid_profiles = {k: v for k, v in discovered_social.items() if v and v.strip()}
                print(f"  Using {len(valid_profiles)} existing profiles:")
                for platform, url in valid_profiles.items():
                    print(f"    {platform.title()}: {url}")

            # Add discovered social links to enrichment result
            # Note: social_media is a Dict[str, EnrichedContact], not a list
            for platform, url in discovered_social.items():
                if url and url.strip():  # Only non-empty URLs
                    # Check if we already have this platform
                    if platform not in profile_result.social_media:
                        from pipeline.contact_validators import validate_social
                        validation = validate_social(url)
                        if validation.is_valid:
                            profile_result.social_media[platform] = EnrichedContact(
                                type=platform,
                                value=validation.normalized_value,
                                confidence=0.9,
                                source='social_discovery',
                                metadata={'platform': platform}
                            )

        except Exception as e:
            logger.error(f"Social media discovery failed: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to existing social links
            discovered_social = profile.get('social_media', {})

    # 4. Google search (deprecated - replaced by social discovery)
    if 'google' in sources and search_mode == 'aggressive':
        try:
            print(f"[*] Searching Google...")
            search = GoogleContactSearch()
            company_name = profile.get('company', domain.split('.')[0])
            google_contacts = search.search_contacts(domain, company_name, search_mode)

            # Add validated contacts
            for phone_match in google_contacts['phones']:
                validation = validate_phone(phone_match.value)
                if validation.is_valid:
                    profile_result.phones.append(EnrichedContact(
                        type='phone',
                        value=validation.normalized_value,
                        confidence=phone_match.confidence,
                        source=phone_match.source,
                        metadata=validation.metadata
                    ))

            for wa_match in google_contacts['whatsapp']:
                validation = validate_whatsapp(wa_match.value)
                if validation.is_valid:
                    profile_result.whatsapp.append(EnrichedContact(
                        type='whatsapp',
                        value=validation.normalized_value,
                        confidence=wa_match.confidence,
                        source=wa_match.source,
                        metadata=validation.metadata
                    ))

            print(f"  Found: {len(google_contacts['phones'])} phones, {len(google_contacts['whatsapp'])} WhatsApp")

        except Exception as e:
            logger.error(f"Google search failed: {e}")

    # 5. LinkedIn discovery (always search for more details)
    if 'linkedin' in sources:
        try:
            print(f"[*] Discovering LinkedIn profiles...")
            linkedin = LinkedInDiscovery()
            linkedin_results = linkedin.discover_profiles(domain, company_name, search_mode)

            for li_match in linkedin_results['company_pages'] + linkedin_results['employee_profiles']:
                validation = validate_linkedin(li_match.value)
                if validation.is_valid:
                    profile_result.linkedin_profiles.append(EnrichedContact(
                        type=li_match.type,
                        value=validation.normalized_value,
                        confidence=li_match.confidence,
                        source=li_match.source,
                        metadata=validation.metadata
                    ))

            print(f"  Found: {len(linkedin_results['company_pages'])} companies, {len(linkedin_results['employee_profiles'])} employees")

        except Exception as e:
            logger.error(f"LinkedIn discovery failed: {e}")

    # 6. Social media scraping (use discovered social links)
    if 'social' in sources:
        try:
            print(f"[*] Scraping social media profiles...")

            # Use discovered social links (includes existing + newly found)
            if discovered_social:
                social_scraper = SocialMediaScraper()
                social_contacts = social_scraper.scrape_social_profiles(discovered_social)

                for phone_match in social_contacts['phones']:
                    validation = validate_phone(phone_match.value)
                    if validation.is_valid:
                        profile_result.phones.append(EnrichedContact(
                            type='phone',
                            value=validation.normalized_value,
                            confidence=phone_match.confidence,
                            source=phone_match.source,
                            metadata=validation.metadata
                        ))

                for wa_match in social_contacts['whatsapp']:
                    validation = validate_whatsapp(wa_match.value)
                    if validation.is_valid:
                        profile_result.whatsapp.append(EnrichedContact(
                            type='whatsapp',
                            value=validation.normalized_value,
                            confidence=wa_match.confidence,
                            source=wa_match.source,
                            metadata=validation.metadata
                        ))

                print(f"  Found: {len(social_contacts['phones'])} phones, {len(social_contacts['whatsapp'])} WhatsApp")
            else:
                print(f"  No social media profiles to scrape")

        except Exception as e:
            logger.error(f"Social media scraping failed: {e}")

    # Deduplicate contacts
    profile_result.phones = enricher._dedupe_enriched_contacts(profile_result.phones)
    profile_result.whatsapp = enricher._dedupe_enriched_contacts(profile_result.whatsapp)
    profile_result.linkedin_profiles = enricher._dedupe_enriched_contacts(profile_result.linkedin_profiles)

    # Recalculate score
    profile_result.contact_score = enricher._calculate_contact_score(
        profile_result.phones,
        profile_result.whatsapp,
        profile_result.linkedin_profiles,
        profile_result.social_media
    )

    profile_result.notes = enricher._generate_notes(
        profile_result.phones,
        profile_result.whatsapp,
        profile_result.linkedin_profiles,
        profile_result.social_media
    )

    # Log results with details
    print(f"\n[RESULTS]")
    print(f"  Phones: {len(profile_result.phones)}")
    if profile_result.phones:
        for phone in profile_result.phones:
            print(f"    - {phone.value} (confidence: {phone.confidence:.2f}, source: {phone.source})")

    print(f"  WhatsApp: {len(profile_result.whatsapp)}")
    if profile_result.whatsapp:
        for wa in profile_result.whatsapp:
            print(f"    - {wa.value} (confidence: {wa.confidence:.2f}, source: {wa.source})")

    print(f"  LinkedIn: {len(profile_result.linkedin_profiles)}")
    if profile_result.linkedin_profiles:
        for li in profile_result.linkedin_profiles:
            print(f"    - {li.value} (confidence: {li.confidence:.2f}, type: {li.type})")

    print(f"  Social Media: {len(profile_result.social_media)}")
    if profile_result.social_media:
        # social_media is a Dict[str, EnrichedContact]
        for platform, social in profile_result.social_media.items():
            print(f"    - {platform.title()}: {social.value}")

    print(f"  Contact Score: {profile_result.contact_score}")

    # Summary of new discoveries
    new_items = []
    if profile_result.phones:
        new_phones = [p for p in profile_result.phones if p.source != 'profile_extraction']
        if new_phones:
            new_items.append(f"{len(new_phones)} phone(s)")
    if profile_result.whatsapp:
        new_wa = [w for w in profile_result.whatsapp if w.source != 'profile_extraction']
        if new_wa:
            new_items.append(f"{len(new_wa)} WhatsApp")
    if profile_result.linkedin_profiles:
        new_items.append(f"{len(profile_result.linkedin_profiles)} LinkedIn")
    if social_links_updated:
        existing_social_in_profile = profile.get('social_media', {})
        valid_existing = len([v for v in existing_social_in_profile.values() if v and v.strip()])
        valid_discovered = len([v for v in discovered_social.values() if v and v.strip()])
        new_count = valid_discovered - valid_existing
        if new_count > 0:
            new_items.append(f"{new_count} social profile(s)")

    if new_items:
        print(f"\n[NEW DISCOVERIES]: {', '.join(new_items)}")
    else:
        print(f"\n[NEW DISCOVERIES]: None (used existing data)")

    # Update profile with discovered social links if they changed
    if social_links_updated and not dry_run:
        try:
            # Update social_media field in profile
            profile['social_media'] = discovered_social

            # Save updated profile
            profile_path = COMPANIES_DIR / domain / 'profile.json'
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2, ensure_ascii=False)

            logger.info(f"Updated social media links in profile")

        except Exception as e:
            logger.error(f"Failed to save social links: {e}")

    # Update profile with enrichment
    profile_path = COMPANIES_DIR / domain / 'profile.json'
    success = enricher.update_profile_with_enrichment(profile_path, profile_result, dry_run)

    # Save to report
    if not dry_run:
        with open(ENRICHMENT_REPORT, 'a', encoding='utf-8') as f:
            report_entry = {
                'domain': domain,
                'enriched_at': profile_result.enriched_at,
                'search_mode': search_mode,
                'contact_score': profile_result.contact_score,
                'phones_found': len(profile_result.phones),
                'whatsapp_found': len(profile_result.whatsapp),
                'linkedin_found': len(profile_result.linkedin_profiles),
                'social_found': len(profile_result.social_media),
                'sources_used': sources
            }
            f.write(json.dumps(report_entry) + '\n')

    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Enrich company profiles with contact information',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'domains',
        nargs='*',
        help='Specific domains to enrich'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Enrich all extracted companies'
    )

    parser.add_argument(
        '--aggressive',
        action='store_true',
        help='Force aggressive mode for all companies (default: auto based on email validity)'
    )

    parser.add_argument(
        '--lenient',
        action='store_true',
        help='Force lenient mode for all companies'
    )

    parser.add_argument(
        '--sources',
        default='google,social,linkedin',
        help='Comma-separated sources to use: website, google, linkedin, social, or "all" (default: google,social,linkedin)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without updating profiles (preview only)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        # Only enable DEBUG for our modules, not third-party
        logging.getLogger('__main__').setLevel(logging.DEBUG)
        logging.getLogger('pipeline').setLevel(logging.DEBUG)
        # Keep third-party loggers quiet
        logging.getLogger('httpx').setLevel(logging.INFO)
        logging.getLogger('httpcore').setLevel(logging.INFO)

    # Determine domains to process
    if args.all:
        domains = get_all_domains()
        logger.info(f"Found {len(domains)} companies to enrich")
    elif args.domains:
        domains = args.domains
    else:
        parser.print_help()
        print("\nError: Specify domains or use --all")
        return

    # Parse sources
    if args.sources == 'all':
        sources = ['website', 'google', 'linkedin', 'social']
    else:
        sources = [s.strip() for s in args.sources.split(',')]

    # Determine force mode
    force_mode = None
    if args.aggressive:
        force_mode = 'aggressive'
    elif args.lenient:
        force_mode = 'lenient'

    if args.dry_run:
        logger.info("\n*** DRY RUN MODE - No profiles will be updated ***\n")

    # Process each domain
    success_count = 0
    failure_count = 0

    for domain in domains:
        try:
            if enrich_company(domain, sources, force_mode, args.dry_run):
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            logger.error(f"[{domain}] Enrichment failed: {e}")
            failure_count += 1

    # Final summary
    print("\n" + "="*70)
    print("ENRICHMENT COMPLETE")
    print("="*70)
    print(f"[SUCCESS] Successful: {success_count}")
    print(f"[FAILED] Failed: {failure_count}")
    print(f"[TOTAL] Total processed: {len(domains)}")

    if not args.dry_run:
        print(f"\n[REPORT] Detailed report saved to: {ENRICHMENT_REPORT}")

    print("="*70 + "\n")


if __name__ == '__main__':
    main()
