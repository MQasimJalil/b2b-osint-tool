"""
Company Repository

CRUD operations for Company documents.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from beanie import PydanticObjectId

from ..mongodb_models import Company


async def get_company_by_id(company_id: str) -> Optional[Company]:
    """Get company by ID"""
    try:
        return await Company.get(PydanticObjectId(company_id))
    except Exception:
        return None


async def get_company_by_domain(domain: str) -> Optional[Company]:
    """Get company by domain"""
    return await Company.find_one(Company.domain == domain)


async def get_company_by_domain_prefix(domain_prefix: str) -> Optional[Company]:
    """
    Get company by domain prefix (fuzzy match).
    Useful when we only have 'advantagegk' but domain is 'advantagegk.com'
    """
    import re
    # Create regex that matches domain starting with the prefix followed by dot or end of string
    # e.g. ^advantagegk(\.|$) matches advantagegk.com, advantagegk.co.uk, etc.
    # We escape the prefix to avoid regex injection if special chars exist
    escaped_prefix = re.escape(domain_prefix)
    regex = re.compile(f"^{escaped_prefix}(\\.|$)", re.IGNORECASE)
    
    return await Company.find_one({"domain": regex})


async def get_companies_by_user(
    user_id: str,
    skip: int = 0,
    limit: int = 100,
    exclude_irrelevant: bool = False,
    only_embedded: bool = False,
    crawled_only: bool = False
) -> List[Company]:
    """Get all companies for a user with pagination (shows all by default, including those pending review)"""
    # Build query filters
    expressions = [Company.user_id == user_id]
    
    if exclude_irrelevant:
        expressions.append(Company.relevance_status != 'irrelevant')
    
    if only_embedded:
        expressions.append(Company.embedded_at != None)

    if crawled_only:
        expressions.append(Company.crawl_status == 'completed')

    return await Company.find(
        *expressions
    ).sort("-created_at").skip(skip).limit(limit).to_list()


async def create_company(company_data: Dict[str, Any]) -> Company:
    """Create a new company"""
    company = Company(**company_data)
    await company.insert()
    return company


async def update_company(
    domain: str,
    update_data: Dict[str, Any]
) -> Optional[Company]:
    """Update company by domain"""
    company = await get_company_by_domain(domain)
    if not company:
        return None

    # Update timestamp
    update_data['updated_at'] = datetime.utcnow()

    # Use set() for updates
    await company.set(update_data)
    return company


async def update_company_profile(
    domain: str,
    profile_data: Dict[str, Any]
) -> Optional[Company]:
    """Update company profile data from extraction"""
    update_dict = {
        'company_name': profile_data.get('company'),
        'description': profile_data.get('description'),
        'smykm_notes': profile_data.get('smykm_notes', []),
        'extracted_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }

    # Handle contacts
    if 'main_contacts' in profile_data:
        contacts = profile_data['main_contacts']
        contact_list = []

        # Add emails
        for email in contacts.get('email', []):
            contact_list.append({
                'type': 'email',
                'value': email,
                'confidence': 1.0,
                'source': 'extraction',
                'verified': False,
                'found_at': datetime.utcnow()
            })

        # Add phones
        for phone in contacts.get('phone', []):
            contact_list.append({
                'type': 'phone',
                'value': phone,
                'confidence': 1.0,
                'source': 'extraction',
                'verified': False,
                'found_at': datetime.utcnow()
            })

        update_dict['contacts'] = contact_list

    # Handle social media
    if 'social_media' in profile_data:
        social_media_list = []
        for platform, url in profile_data['social_media'].items():
            if url:
                social_media_list.append({
                    'platform': platform,
                    'url': url,
                    'source': 'extraction',
                    'verified': False
                })
        update_dict['social_media'] = social_media_list

    return await update_company(domain, update_dict)


async def update_company_enrichment(
    domain: str,
    enrichment_data: Dict[str, Any]
) -> Optional[Company]:
    """Update company with enrichment results"""
    update_dict = {
        'contact_score': enrichment_data.get('contact_score'),
        'search_mode': enrichment_data.get('search_mode'),
        'enrichment_status': {
            'last_enriched': enrichment_data.get('enriched_at'),
            'sources_checked': enrichment_data.get('sources_checked', []),
            'contact_score': enrichment_data.get('contact_score'),
            'search_mode': enrichment_data.get('search_mode'),
            'notes': enrichment_data.get('notes', '')
        },
        'enriched_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }

    # Merge enrichment contacts with existing contacts
    company = await get_company_by_domain(domain)
    if company:
        existing_contacts = company.contacts or []

        # Add phones from enrichment (as dicts)
        for phone in enrichment_data.get('phones', []):
            existing_contacts.append({"type": "phone", "value": phone})

        # Add whatsapp from enrichment (as dicts)
        for whatsapp in enrichment_data.get('whatsapp', []):
            existing_contacts.append({"type": "whatsapp", "value": whatsapp})

        # Add linkedin from enrichment (as dicts)
        for linkedin in enrichment_data.get('linkedin_profiles', []):
            existing_contacts.append({"type": "linkedin", "value": linkedin})

        update_dict['contacts'] = existing_contacts

        # Merge social media
        existing_social = company.social_media or []
        for platform, url in enrichment_data.get('social_media_enriched', {}).items():
            existing_social.append({"platform": platform, "url": url})
        update_dict['social_media'] = existing_social

    return await update_company(domain, update_dict)


async def delete_company(domain: str) -> bool:
    """Delete company by domain"""
    company = await get_company_by_domain(domain)
    if not company:
        return False

    await company.delete()
    return True


async def count_companies_by_user(
    user_id: str, 
    exclude_irrelevant: bool = False,
    only_embedded: bool = False,
    crawled_only: bool = False
) -> int:
    """Count companies for a user (counts all by default, including those pending review)"""
    # Build query filters
    expressions = [Company.user_id == user_id]
    
    if exclude_irrelevant:
        expressions.append(Company.relevance_status != 'irrelevant')
        
    if only_embedded:
        expressions.append(Company.embedded_at != None)

    if crawled_only:
        expressions.append(Company.crawl_status == 'completed')

    return await Company.find(
        *expressions
    ).count()


async def count_companies_with_contacts(user_id: str) -> int:
    """Count companies that have at least one contact"""
    return await Company.find(
        Company.user_id == user_id,
        {"contacts": {"$ne": []}}  # contacts is not empty
    ).count()


async def count_total_contacts(user_id: str) -> int:
    """Count total number of contacts across all companies"""
    # Fetch all companies for user
    # Note: Ideally we use projection here, but for stability we'll fetch full docs for now
    # or use a specific Pydantic model for projection if we defined one.
    companies = await Company.find(
        Company.user_id == user_id
    ).to_list()
    
    total = 0
    for comp in companies:
        if comp.contacts:
            total += len(comp.contacts)
            
    return total


async def search_companies(
    user_id: str,
    search_query: str,
    skip: int = 0,
    limit: int = 100
) -> List[Company]:
    """Search companies by name or domain"""
    # Case-insensitive regex search
    import re
    regex = re.compile(search_query, re.IGNORECASE)

    companies = await Company.find(
        Company.user_id == user_id,
        {
            "$or": [
                {"domain": regex},
                {"company_name": regex}
            ]
        }
    ).skip(skip).limit(limit).to_list()

    return companies


async def update_company_relevance(
    domain: str,
    relevance_status: str,
    relevance_reason: Optional[str] = None
) -> Optional[Company]:
    """Update company relevance status and reason"""
    update_dict = {
        'relevance_status': relevance_status,
        'relevance_reason': relevance_reason,
        'updated_at': datetime.utcnow()
    }
    return await update_company(domain, update_dict)
