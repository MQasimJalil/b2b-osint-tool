"""
Contact Enrichment System

Multi-channel contact discovery for B2B companies.
Finds phone numbers, WhatsApp, LinkedIn profiles, and social media handles.

Priority-based search:
- Companies WITH valid emails: Lenient search (quick sources)
- Companies WITHOUT valid emails: Aggressive search (all sources)
"""

import os
import sys
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime

# Add backend to path for MongoDB imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# MongoDB repository imports
from app.db.repositories.company_repo import (
    get_company_by_domain,
    update_company_enrichment
)
from app.db.mongodb_session import init_db

from app.services.enrichment.contact_patterns import (
    extract_phones,
    extract_whatsapp,
    extract_linkedin,
    extract_social_media,
    normalize_phone,
    is_valid_phone,
    deduplicate_contacts,
    filter_by_confidence,
    ContactMatch
)

# Global flag to track if MongoDB is initialized
_mongodb_initialized = False


def _ensure_mongodb():
    """Ensure MongoDB is initialized before operations"""
    global _mongodb_initialized
    if not _mongodb_initialized:
        try:
            asyncio.run(init_db())
            _mongodb_initialized = True
            logger.info("✓ MongoDB initialized for enrichment service")
        except Exception as e:
            logger.warning(f"Failed to initialize MongoDB: {e}")
            logger.warning("Enrichment service will continue but data won't be persisted to MongoDB")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EnrichedContact:
    """Represents an enriched contact."""
    type: str  # phone, whatsapp, linkedin_individual, linkedin_company, social_*
    value: str
    confidence: float
    source: str  # website, google, linkedin, instagram, etc.
    verified: bool = False
    found_at: str = None
    metadata: Dict = None

    def __post_init__(self):
        if not self.found_at:
            self.found_at = datetime.utcnow().isoformat() + 'Z'
        if not self.metadata:
            self.metadata = {}


@dataclass
class EnrichmentResult:
    """Results of contact enrichment for a company."""
    domain: str
    phones: List[EnrichedContact]
    whatsapp: List[EnrichedContact]
    linkedin_profiles: List[EnrichedContact]
    social_media: Dict[str, EnrichedContact]
    sources_checked: List[str]
    search_mode: str  # lenient or aggressive
    contact_score: str  # high, medium, low
    enriched_at: str
    notes: str = ""

    def to_dict(self):
        """Convert to dict for JSON serialization."""
        return {
            'domain': self.domain,
            'phones': [asdict(p) for p in self.phones],
            'whatsapp': [asdict(w) for w in self.whatsapp],
            'linkedin_profiles': [asdict(l) for l in self.linkedin_profiles],
            'social_media': {k: asdict(v) for k, v in self.social_media.items()},
            'sources_checked': self.sources_checked,
            'search_mode': self.search_mode,
            'contact_score': self.contact_score,
            'enriched_at': self.enriched_at,
            'notes': self.notes
        }


class ContactEnricher:
    """Main contact enrichment orchestrator."""

    def __init__(
        self,
        base_dir: Path = None,
        min_confidence: float = 0.6,
        cache_dir: Path = None
    ):
        """
        Initialize contact enricher.

        Args:
            base_dir: Base directory (default: parent of this file)
            min_confidence: Minimum confidence for contacts (0.0 to 1.0)
            cache_dir: Cache directory for enrichment results
        """
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.min_confidence = min_confidence
        self.cache_dir = cache_dir or (self.base_dir / 'enrichment_cache')
        self.cache_dir.mkdir(exist_ok=True)

    def determine_search_mode(self, profile: Dict) -> str:
        """
        Determine search mode based on existing contact validity.

        Args:
            profile: Company profile dict

        Returns:
            'lenient' or 'aggressive'
        """
        # Check if we have any valid emails
        email_verification = profile.get('main_contacts', {}).get('email_verification', {})

        if not email_verification:
            # No verification data - be aggressive
            return 'aggressive'

        # Check if any emails are valid
        has_valid_email = any(
            v.get('is_valid', False)
            for v in email_verification.values()
        )

        return 'lenient' if has_valid_email else 'aggressive'

    def enrich_from_profile(
        self,
        profile: Dict,
        sources: List[str] = None
    ) -> EnrichmentResult:
        """
        Enrich contacts from company profile data.

        Args:
            profile: Company profile dict
            sources: Sources to check (default: all available)

        Returns:
            EnrichmentResult with found contacts
        """
        domain = profile.get('domain', 'unknown')
        search_mode = self.determine_search_mode(profile)

        logger.info(f"[{domain}] Starting enrichment in {search_mode} mode")

        # Initialize results
        phones = []
        whatsapp = []
        linkedin_profiles = []
        social_media = {}
        sources_checked = []

        # Extract from existing profile data
        all_matches = []

        # 1. Check description and notes
        text_sources = [
            profile.get('description', ''),
            ' '.join(profile.get('smykm_notes', []))
        ]

        for text in text_sources:
            if not text:
                continue

            # Extract phones
            phone_matches = extract_phones(text)
            all_matches.extend(phone_matches)

            # Extract WhatsApp
            whatsapp_matches = extract_whatsapp(text)
            all_matches.extend(whatsapp_matches)

        sources_checked.append('profile_text')

        # 2. Check social media links
        existing_social = profile.get('social_media', {})
        for platform, url in existing_social.items():
            if url and url.strip():
                social_media[platform] = EnrichedContact(
                    type=f'social_{platform}',
                    value=url,
                    confidence=0.95,  # High confidence - from official profile
                    source='existing_profile',
                    verified=True
                )

        sources_checked.append('existing_social')

        # 3. Check LinkedIn
        linkedin_url = existing_social.get('linkedin', '')
        if linkedin_url and linkedin_url.strip():
            linkedin_profiles.append(EnrichedContact(
                type='linkedin_company',
                value=linkedin_url,
                confidence=0.95,
                source='existing_profile',
                verified=True
            ))

        # 4. Process all matches
        all_matches = deduplicate_contacts(all_matches)
        all_matches = filter_by_confidence(all_matches, self.min_confidence)

        for match in all_matches:
            contact = EnrichedContact(
                type=match.type,
                value=match.value,
                confidence=match.confidence,
                source=match.source,
                metadata={'context': match.context[:100]}  # First 100 chars
            )

            if match.type == 'phone':
                # Normalize and validate
                normalized = normalize_phone(match.value)
                if is_valid_phone(normalized):
                    contact.value = normalized
                    phones.append(contact)

            elif match.type == 'whatsapp':
                normalized = normalize_phone(match.value)
                if is_valid_phone(normalized):
                    contact.value = normalized
                    whatsapp.append(contact)

            elif match.type.startswith('linkedin'):
                linkedin_profiles.append(contact)

        # 5. Calculate contact score
        contact_score = self._calculate_contact_score(phones, whatsapp, linkedin_profiles, social_media)

        # 6. Build result
        result = EnrichmentResult(
            domain=domain,
            phones=phones,
            whatsapp=whatsapp,
            linkedin_profiles=linkedin_profiles,
            social_media=social_media,
            sources_checked=sources_checked,
            search_mode=search_mode,
            contact_score=contact_score,
            enriched_at=datetime.utcnow().isoformat() + 'Z',
            notes=self._generate_notes(phones, whatsapp, linkedin_profiles, social_media)
        )

        logger.info(f"[{domain}] Found: {len(phones)} phones, {len(whatsapp)} WhatsApp, "
                   f"{len(linkedin_profiles)} LinkedIn, {len(social_media)} social - Score: {contact_score}")

        return result

    def enrich_from_website(
        self,
        domain: str,
        profile: Dict = None
    ) -> EnrichmentResult:
        """
        Enrich contacts from website scraping.

        This will be called by website scraper module.

        Args:
            domain: Company domain
            profile: Existing profile (optional)

        Returns:
            EnrichmentResult
        """
        # This will be implemented when we create the website scraper
        # For now, just return empty result
        logger.info(f"[{domain}] Website scraping not yet implemented")

        return EnrichmentResult(
            domain=domain,
            phones=[],
            whatsapp=[],
            linkedin_profiles=[],
            social_media={},
            sources_checked=['website'],
            search_mode='lenient',
            contact_score='low',
            enriched_at=datetime.utcnow().isoformat() + 'Z',
            notes='Website scraping pending implementation'
        )

    def enrich_from_google(
        self,
        domain: str,
        company_name: str = None
    ) -> EnrichmentResult:
        """
        Enrich contacts from Google search.

        This will be called by Google search module.

        Args:
            domain: Company domain
            company_name: Company name for search queries

        Returns:
            EnrichmentResult
        """
        # This will be implemented when we create the Google search module
        logger.info(f"[{domain}] Google search not yet implemented")

        return EnrichmentResult(
            domain=domain,
            phones=[],
            whatsapp=[],
            linkedin_profiles=[],
            social_media={},
            sources_checked=['google'],
            search_mode='lenient',
            contact_score='low',
            enriched_at=datetime.utcnow().isoformat() + 'Z',
            notes='Google search pending implementation'
        )

    def merge_results(self, results: List[EnrichmentResult]) -> EnrichmentResult:
        """
        Merge multiple enrichment results into one.

        Args:
            results: List of EnrichmentResult objects

        Returns:
            Merged EnrichmentResult
        """
        if not results:
            raise ValueError("No results to merge")

        if len(results) == 1:
            return results[0]

        # Use first result as base
        merged = results[0]

        # Merge contacts from other results
        all_phones = []
        all_whatsapp = []
        all_linkedin = []
        all_social = {}
        all_sources = set()

        for result in results:
            all_phones.extend(result.phones)
            all_whatsapp.extend(result.whatsapp)
            all_linkedin.extend(result.linkedin_profiles)
            all_social.update(result.social_media)
            all_sources.update(result.sources_checked)

        # Deduplicate (keep highest confidence)
        merged.phones = self._dedupe_enriched_contacts(all_phones)
        merged.whatsapp = self._dedupe_enriched_contacts(all_whatsapp)
        merged.linkedin_profiles = self._dedupe_enriched_contacts(all_linkedin)
        merged.social_media = all_social  # Dict already deduped
        merged.sources_checked = list(all_sources)

        # Recalculate score
        merged.contact_score = self._calculate_contact_score(
            merged.phones,
            merged.whatsapp,
            merged.linkedin_profiles,
            merged.social_media
        )

        merged.notes = self._generate_notes(
            merged.phones,
            merged.whatsapp,
            merged.linkedin_profiles,
            merged.social_media
        )

        return merged

    def update_profile_with_enrichment(
        self,
        profile_path: Path,
        enrichment: EnrichmentResult,
        dry_run: bool = False
    ) -> bool:
        """
        Update company profile with enrichment results in MongoDB.

        Args:
            profile_path: Path to profile.json (or just domain)
            enrichment: EnrichmentResult to add
            dry_run: If True, don't actually write

        Returns:
            True if updated successfully
        """
        _ensure_mongodb()

        try:
            # Extract domain from path or use directly
            if isinstance(profile_path, str):
                domain = enrichment.domain
            else:
                domain = enrichment.domain

            if dry_run:
                logger.info(f"[{domain}] DRY RUN: Would update enrichment data")
                return True

            # Prepare enrichment data for MongoDB
            enrichment_data = {
                'phones': [p.value for p in enrichment.phones],
                'whatsapp': [w.value for w in enrichment.whatsapp],
                'social_media_enriched': {
                    platform: contact.value
                    for platform, contact in enrichment.social_media.items()
                    if contact.value
                },
                'enrichment_status': {
                    'last_enriched': enrichment.enriched_at,
                    'sources_checked': enrichment.sources_checked,
                    'contact_score': enrichment.contact_score,
                    'search_mode': enrichment.search_mode,
                    'notes': enrichment.notes
                },
                'enriched_contacts': enrichment.to_dict()
            }

            # Update in MongoDB
            asyncio.run(update_company_enrichment(domain, enrichment_data))

            logger.info(f"[{domain}] Updated MongoDB with enrichment data")
            return True

        except Exception as e:
            logger.error(f"[{enrichment.domain}] Failed to update MongoDB: {e}")
            logger.info(f"[{enrichment.domain}] Falling back to file-based storage...")

            # Fallback to file-based storage
            try:
                # Load profile
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)

                # Update main_contacts
                if 'main_contacts' not in profile:
                    profile['main_contacts'] = {}

                # Add phones
                profile['main_contacts']['phone'] = [
                    p.value for p in enrichment.phones
                ]

                # Add WhatsApp (new field)
                profile['main_contacts']['whatsapp'] = [
                    w.value for w in enrichment.whatsapp
                ]

                # Update social media
                if 'social_media' not in profile:
                    profile['social_media'] = {}

                for platform, contact in enrichment.social_media.items():
                    if contact.value:
                        profile['social_media'][platform] = contact.value

                # Add enrichment metadata
                profile['enrichment_status'] = {
                    'last_enriched': enrichment.enriched_at,
                    'sources_checked': enrichment.sources_checked,
                    'contact_score': enrichment.contact_score,
                    'search_mode': enrichment.search_mode,
                    'notes': enrichment.notes
                }

                # Add detailed enrichment data
                profile['enriched_contacts'] = enrichment.to_dict()

                # Write back
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, indent=2, ensure_ascii=False)

                logger.info(f"[{enrichment.domain}] Updated file with enrichment data")
                return True

            except Exception as e2:
                logger.error(f"[{enrichment.domain}] Failed to update file: {e2}")
                return False

    def _dedupe_enriched_contacts(self, contacts: List[EnrichedContact]) -> List[EnrichedContact]:
        """Deduplicate enriched contacts, keeping highest confidence."""
        seen = {}

        for contact in contacts:
            key = contact.value.lower()

            if key not in seen or contact.confidence > seen[key].confidence:
                seen[key] = contact

        return list(seen.values())

    def _calculate_contact_score(
        self,
        phones: List[EnrichedContact],
        whatsapp: List[EnrichedContact],
        linkedin: List[EnrichedContact],
        social: Dict[str, EnrichedContact]
    ) -> str:
        """
        Calculate overall contact score.

        Returns: 'high', 'medium', or 'low'
        """
        # Weighted scoring
        score = 0

        # WhatsApp is highest priority
        if whatsapp:
            score += 40

        # Phones are important
        if phones:
            score += 30

        # LinkedIn profiles
        if linkedin:
            score += 20

        # Social media
        social_count = len([s for s in social.values() if s.value])
        if social_count >= 3:
            score += 15
        elif social_count >= 1:
            score += 10

        # Determine tier
        if score >= 70:
            return 'high'
        elif score >= 40:
            return 'medium'
        else:
            return 'low'

    def _generate_notes(
        self,
        phones: List[EnrichedContact],
        whatsapp: List[EnrichedContact],
        linkedin: List[EnrichedContact],
        social: Dict[str, EnrichedContact]
    ) -> str:
        """Generate human-readable notes about enrichment."""
        notes = []

        if whatsapp:
            notes.append(f"Found {len(whatsapp)} WhatsApp number(s)")

        if phones:
            notes.append(f"Found {len(phones)} phone number(s)")

        if linkedin:
            individual_count = sum(1 for l in linkedin if 'individual' in l.type)
            company_count = sum(1 for l in linkedin if 'company' in l.type)
            if individual_count:
                notes.append(f"Found {individual_count} LinkedIn profile(s)")
            if company_count:
                notes.append(f"Found {company_count} LinkedIn company page(s)")

        social_count = len([s for s in social.values() if s.value])
        if social_count:
            platforms = [k for k, v in social.items() if v.value]
            notes.append(f"Found {social_count} social media account(s): {', '.join(platforms)}")

        return '; '.join(notes) if notes else 'No additional contacts found'


# Convenience function
def enrich_company(domain: str, profile: Dict = None) -> EnrichmentResult:
    """
    Quick function to enrich a single company.

    Args:
        domain: Company domain
        profile: Existing profile dict (optional)

    Returns:
        EnrichmentResult
    """
    _ensure_mongodb()
    enricher = ContactEnricher()

    if profile:
        return enricher.enrich_from_profile(profile)
    else:
        # Load profile from MongoDB only (cloud-safe)
        company_doc = asyncio.run(get_company_by_domain(domain))

        if not company_doc:
            raise FileNotFoundError(f"Company profile not found in MongoDB for {domain}")

        # Convert Beanie document to dict
        profile = {
            'domain': company_doc.domain,
            'company': company_doc.company_name,
            'description': company_doc.description,
            'smykm_notes': company_doc.smykm_notes,
            'main_contacts': {
                'email': [c.get('value') for c in company_doc.contacts if c.get('type') == 'email'],
                'phone': [c.get('value') for c in company_doc.contacts if c.get('type') == 'phone'],
                'email_verification': company_doc.enrichment_status.get('email_verification', {}) if company_doc.enrichment_status else {}
            },
            'social_media': {sm.get('platform'): sm.get('url') for sm in company_doc.social_media}
        }

        return enricher.enrich_from_profile(profile)
