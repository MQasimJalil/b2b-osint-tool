"""
Contact Pattern Matching

Regex patterns and utilities for extracting contacts from text.
Supports phone numbers, WhatsApp, LinkedIn, and social media handles.
"""

import re
from typing import List, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class ContactMatch:
    """Represents a matched contact."""
    value: str
    type: str  # phone, whatsapp, linkedin, email, social
    confidence: float  # 0.0 to 1.0
    context: str  # Surrounding text
    source: str  # Where it was found


# Phone number patterns (international formats)
PHONE_PATTERNS = [
    # International with country code
    r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
    # With parentheses
    r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    # Various separators
    r'\d{3}[-.\s]\d{3}[-.\s]\d{4}',
    r'\d{10,15}',  # Plain numbers
    # tel: links
    r'tel:[\+\d\-\.\s\(\)]+',
]

# WhatsApp patterns
WHATSAPP_PATTERNS = [
    r'wa\.me/[\+\d]+',
    r'whatsapp\.com/[\+\d]+',
    r'api\.whatsapp\.com/send\?phone=[\d]+',
    r'chat\.whatsapp\.com/[\w]+',  # Group links
]

# LinkedIn patterns
LINKEDIN_PATTERNS = [
    r'linkedin\.com/in/[\w\-]+',
    r'linkedin\.com/company/[\w\-]+',
    r'linkedin\.com/pub/[\w\-]+',
    r'[^\s]+\.linkedin\.com',
]

# Social media patterns
SOCIAL_PATTERNS = {
    'instagram': [
        r'instagram\.com/[\w\.]+',
        r'@[\w\.]+',  # @handle
    ],
    'facebook': [
        r'facebook\.com/[\w\.]+',
        r'fb\.com/[\w\.]+',
        r'fb\.me/[\w\.]+',
    ],
    'twitter': [
        r'twitter\.com/[\w]+',
        r'x\.com/[\w]+',
        r'@[\w]+',
    ],
    'youtube': [
        r'youtube\.com/[@\w]+',
        r'youtube\.com/channel/[\w\-]+',
        r'youtu\.be/[\w\-]+',
    ],
    'tiktok': [
        r'tiktok\.com/@[\w\.]+',
        r'@[\w\.]+',
    ],
}


def extract_phones(text: str, context_chars: int = 50) -> List[ContactMatch]:
    """
    Extract phone numbers from text.

    Args:
        text: Text to search
        context_chars: Characters of context to capture

    Returns:
        List of phone number matches
    """
    matches = []
    seen = set()

    for pattern in PHONE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            phone = match.group(0)

            # Clean up
            phone = phone.replace('tel:', '').strip()

            # Skip if too short or already seen
            if len(re.sub(r'\D', '', phone)) < 7:
                continue
            if phone in seen:
                continue

            seen.add(phone)

            # Get context
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            context = text[start:end].strip()

            # Determine confidence based on context
            confidence = 0.5
            lower_context = context.lower()
            if any(word in lower_context for word in ['phone', 'tel', 'call', 'contact']):
                confidence = 0.9
            elif any(word in lower_context for word in ['fax', 'mobile', 'office']):
                confidence = 0.8

            matches.append(ContactMatch(
                value=phone,
                type='phone',
                confidence=confidence,
                context=context,
                source='text'
            ))

    return matches


def extract_whatsapp(text: str, html: str = None, context_chars: int = 50) -> List[ContactMatch]:
    """
    Extract WhatsApp numbers and links from text and HTML.

    Args:
        text: Text to search
        html: HTML source (optional, for finding wa.me links)
        context_chars: Characters of context to capture

    Returns:
        List of WhatsApp matches
    """
    matches = []
    seen = set()

    # Search both text and HTML
    sources = [('text', text)]
    if html:
        sources.append(('html', html))

    for source_name, source_text in sources:
        for pattern in WHATSAPP_PATTERNS:
            for match in re.finditer(pattern, source_text, re.IGNORECASE):
                whatsapp = match.group(0)

                if whatsapp in seen:
                    continue
                seen.add(whatsapp)

                # Extract number from wa.me link
                number = None
                if 'wa.me/' in whatsapp:
                    number = whatsapp.split('wa.me/')[-1].split('?')[0]
                elif 'phone=' in whatsapp:
                    number = re.search(r'phone=([\d\+]+)', whatsapp).group(1)

                # Get context
                start = max(0, match.start() - context_chars)
                end = min(len(source_text), match.end() + context_chars)
                context = source_text[start:end].strip()

                matches.append(ContactMatch(
                    value=number or whatsapp,
                    type='whatsapp',
                    confidence=0.95 if number else 0.8,
                    context=context,
                    source=source_name
                ))

    # Also check for "WhatsApp" keyword near phone numbers
    phones = extract_phones(text, context_chars)
    for phone in phones:
        if 'whatsapp' in phone.context.lower():
            if phone.value not in seen:
                matches.append(ContactMatch(
                    value=phone.value,
                    type='whatsapp',
                    confidence=0.85,
                    context=phone.context,
                    source='keyword_match'
                ))
                seen.add(phone.value)

    return matches


def extract_linkedin(text: str, html: str = None) -> List[ContactMatch]:
    """
    Extract LinkedIn profile URLs from text and HTML.

    Args:
        text: Text to search
        html: HTML source (optional)

    Returns:
        List of LinkedIn profile matches
    """
    matches = []
    seen = set()

    sources = [('text', text)]
    if html:
        sources.append(('html', html))

    for source_name, source_text in sources:
        for pattern in LINKEDIN_PATTERNS:
            for match in re.finditer(pattern, source_text, re.IGNORECASE):
                linkedin = match.group(0)

                # Normalize URL
                if not linkedin.startswith('http'):
                    linkedin = f'https://{linkedin}'

                # Clean up trailing characters
                linkedin = re.sub(r'[^\w\-/:.]+$', '', linkedin)

                if linkedin in seen:
                    continue
                seen.add(linkedin)

                # Determine type (company vs individual)
                profile_type = 'company' if '/company/' in linkedin else 'individual'

                matches.append(ContactMatch(
                    value=linkedin,
                    type=f'linkedin_{profile_type}',
                    confidence=0.9,
                    context='',
                    source=source_name
                ))

    return matches


def extract_social_media(text: str, html: str = None) -> Dict[str, List[ContactMatch]]:
    """
    Extract social media handles from text and HTML.

    Args:
        text: Text to search
        html: HTML source (optional)

    Returns:
        Dict mapping platform name to list of matches
    """
    results = {platform: [] for platform in SOCIAL_PATTERNS.keys()}

    sources = [('text', text)]
    if html:
        sources.append(('html', html))

    for platform, patterns in SOCIAL_PATTERNS.items():
        seen = set()

        for source_name, source_text in sources:
            for pattern in patterns:
                for match in re.finditer(pattern, source_text, re.IGNORECASE):
                    handle = match.group(0)

                    # Normalize URL
                    if platform in handle.lower() and not handle.startswith('http'):
                        handle = f'https://{handle}'

                    # Clean up
                    handle = re.sub(r'[^\w\-/:@.]+$', '', handle)

                    if handle in seen:
                        continue
                    seen.add(handle)

                    # Determine confidence
                    confidence = 0.9 if platform in handle.lower() else 0.6

                    results[platform].append(ContactMatch(
                        value=handle,
                        type=f'social_{platform}',
                        confidence=confidence,
                        context='',
                        source=source_name
                    ))

    return results


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to standard format.

    Args:
        phone: Phone number string

    Returns:
        Normalized phone number
    """
    # Remove all non-digit characters except +
    normalized = re.sub(r'[^\d+]', '', phone)

    # Ensure it starts with +
    if not normalized.startswith('+'):
        # Assume international format if 10+ digits
        if len(normalized) >= 10:
            normalized = '+' + normalized

    return normalized


def is_valid_phone(phone: str) -> bool:
    """
    Basic validation of phone number format.

    Args:
        phone: Phone number string

    Returns:
        True if valid format
    """
    # Must have 7-15 digits
    digits = re.sub(r'\D', '', phone)
    return 7 <= len(digits) <= 15


def is_valid_url(url: str) -> bool:
    """
    Basic URL validation.

    Args:
        url: URL string

    Returns:
        True if valid format
    """
    url_pattern = r'^https?://[\w\-\.]+\.\w{2,}(/.*)?$'
    return bool(re.match(url_pattern, url, re.IGNORECASE))


def deduplicate_contacts(contacts: List[ContactMatch]) -> List[ContactMatch]:
    """
    Remove duplicate contacts, keeping highest confidence match.

    Args:
        contacts: List of contact matches

    Returns:
        Deduplicated list
    """
    seen = {}

    for contact in contacts:
        key = (contact.type, contact.value.lower())

        if key not in seen or contact.confidence > seen[key].confidence:
            seen[key] = contact

    return list(seen.values())


def filter_by_confidence(contacts: List[ContactMatch], min_confidence: float = 0.5) -> List[ContactMatch]:
    """
    Filter contacts by minimum confidence threshold.

    Args:
        contacts: List of contact matches
        min_confidence: Minimum confidence (0.0 to 1.0)

    Returns:
        Filtered list
    """
    return [c for c in contacts if c.confidence >= min_confidence]
