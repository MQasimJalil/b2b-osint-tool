"""
Unified Query Generation System

Combines AI-powered keyword variant generation with sophisticated query family logic
for comprehensive B2B discovery.

This module eliminates duplication between discover.py and discovery_service.py by
providing a single, powerful query generation system.
"""
import os
import random
import logging
import yaml
from typing import List, Set, Dict, Optional, Tuple
from ..vetting.enhanced_vet import generate_keyword_variants_ai

logger = logging.getLogger(__name__)

# Path to config file (relative to this file)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "discover_config.yaml")


def load_config() -> Dict:
    """Load query generation configuration from YAML file."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    logger.warning(f"Config file not found at {CONFIG_PATH}, using defaults")
    return {}


# Default query templates organized by intent
DEFAULT_QUERY_FAMILIES = {
    "basic_intent": [
        "{keyword}",
        "{keyword} buy",
        "{keyword} price",
        "{keyword} shop",
        "{keyword} supplier",
        "{keyword} wholesale"
    ],
    "platform_hints": [
        "{keyword} shopify",
        "{keyword} woocommerce",
        "{keyword} bigcommerce",
        "{keyword} ecommerce",
        "{keyword} online store"
    ],
    "b2b_focused": [
        "{keyword} B2B",
        "{keyword} distributor",
        "{keyword} manufacturer",
        "{keyword} vendor",
        "{keyword} seller",
        "{keyword} merchant"
    ],
    "location_aware": [
        "{keyword} store",
        "{keyword} retailers",
        "{keyword} buy online",
        "{keyword} for sale",
        "buy {keyword}",
        "shop {keyword}"
    ]
}


class QueryGeneratorConfig:
    """Configuration for query generation."""

    def __init__(
        self,
        use_ai_variants: bool = True,
        max_queries: int = 400,
        per_family_cap: int = 50,
        query_families: Optional[Dict[str, List[str]]] = None,
        regions: Optional[List[str]] = None,
        geo_tlds: Optional[List[str]] = None,
        negative_keywords: Optional[List[str]] = None,
        niche_terms: Optional[List[str]] = None,
        random_seed: int = 42
    ):
        """
        Initialize query generator configuration.

        Args:
            use_ai_variants: Whether to use AI to generate keyword variants
            max_queries: Maximum number of queries to generate
            per_family_cap: Maximum queries per query family
            query_families: Custom query families (uses defaults if None)
            regions: Geographic regions to target (e.g., ["us", "uk", "ca"])
            geo_tlds: Geographic TLDs for site: operator (e.g., [".com", ".co.uk"])
            negative_keywords: Keywords to exclude (e.g., ["amazon", "ebay"])
            niche_terms: Additional niche terms to combine with keywords
            random_seed: Random seed for reproducible query sampling
        """
        self.use_ai_variants = use_ai_variants
        self.max_queries = max_queries
        self.per_family_cap = per_family_cap
        self.query_families = query_families or DEFAULT_QUERY_FAMILIES
        self.regions = regions or []
        self.geo_tlds = geo_tlds or []
        self.negative_keywords = negative_keywords or []
        self.niche_terms = niche_terms or []
        self.random_seed = random_seed


async def generate_queries(
    base_keywords: List[str],
    config: Optional[QueryGeneratorConfig] = None
) -> Tuple[List[str], List[str]]:
    """
    Generate comprehensive search queries using AI variants and query families.

    This function combines:
    1. AI-powered keyword variant generation (abbreviations, synonyms, related terms)
    2. Sophisticated query family logic from config file (intents, platforms, negatives)
    3. Stratified sampling for query diversity
    4. Deduplication and normalization

    Args:
        base_keywords: User-provided keywords (e.g., ["Goalkeeper Gloves"])
        config: Query generation configuration (uses defaults if None)

    Returns:
        Tuple of (expanded_queries, keyword_variants):
        - expanded_queries: List of search queries (50-400+)
        - keyword_variants: AI-generated keyword variants (for reuse in vetting)

    Example:
        Input: ["Goalkeeper Gloves"]
        Output: (
            [
                "goalkeeper shop",
                "gk gloves supplier",
                "goalie B2B",
                "keeper wholesale",
                ...
            ],
            ["goalkeeper", "gk", "goalie", "keeper", "gloves", ...]
        )
    """
    if config is None:
        config = QueryGeneratorConfig()

    logger.info(f"Starting query generation for {len(base_keywords)} base keywords")

    # Load config from YAML
    yaml_config = load_config()
    templates_config = yaml_config.get("templates", {})
    limits_config = yaml_config.get("limits", {})

    # Extract intents, platform hints, and negatives from config
    intents = templates_config.get("intents", ["buy", "price", "shop", "supplier", "wholesale"])
    platform_hints = templates_config.get("platform_hints", [])
    negatives = templates_config.get("negatives", [])
    geo_tlds_from_config = templates_config.get("geo_tlds", [])

    # Merge config negatives with user-provided negatives
    all_negatives = negatives + [f"-{kw}" for kw in config.negative_keywords]

    # Use limits from config if not overridden
    max_queries = config.max_queries or limits_config.get("max_queries", 400)
    per_family_cap = config.per_family_cap or limits_config.get("per_family_cap", 50)

    # Step 1: Generate AI keyword variants (these replace niche_terms!)
    keyword_variants = []
    if config.use_ai_variants:
        try:
            keyword_variants = await generate_keyword_variants_ai(base_keywords)
            logger.info(f"Generated {len(keyword_variants)} keyword variants using AI")
        except Exception as e:
            logger.warning(f"Failed to generate AI variants: {e}, using base keywords only")
            keyword_variants = base_keywords
    else:
        keyword_variants = base_keywords

    # Step 2: Build query families using AI variants + config templates
    query_families_output = []
    rnd = random.Random(config.random_seed)

    # Family 1: AI variants + intents (e.g., "goalkeeper buy", "gk shop")
    family_intents = []
    for variant in keyword_variants:
        for intent in intents:
            query = f"{variant} {intent}"
            if all_negatives:
                query += " " + " ".join(all_negatives)
            family_intents.append(query.strip())
    if family_intents:
        query_families_output.append(family_intents)

    # Family 2: AI variants + platform hints (e.g., "goalkeeper inurl:/collections")
    if platform_hints:
        family_platform = []
        for variant in keyword_variants:
            for hint in platform_hints:
                query = f"{variant} {hint}"
                if all_negatives:
                    query += " " + " ".join(all_negatives)
                family_platform.append(query.strip())
        query_families_output.append(family_platform)

    # Family 3: Reverse order - intent + AI variant (e.g., "buy goalkeeper", "shop gk")
    family_reverse = []
    for variant in keyword_variants:
        for intent in intents[:5]:  # Use first 5 intents to avoid explosion
            query = f"{intent} {variant}"
            if all_negatives:
                query += " " + " ".join(all_negatives)
            family_reverse.append(query.strip())
    if family_reverse:
        query_families_output.append(family_reverse)

    # Family 4: Geographic TLD targeting (variant + intent + site:tld)
    geo_tlds = config.geo_tlds or geo_tlds_from_config
    if geo_tlds:
        family_geo = []
        for variant in keyword_variants:
            for intent in intents[:3]:  # Use first 3 intents
                for tld in geo_tlds:
                    query = f"{variant} {intent} site:{tld}"
                    if all_negatives:
                        query += " " + " ".join(all_negatives)
                    family_geo.append(query.strip())
        if family_geo:
            query_families_output.append(family_geo)

    # Family 5: Regional targeting (variant + intent + region)
    regions_from_config = yaml_config.get("regions", [])
    regions = config.regions or regions_from_config
    if regions:
        family_region = []
        for variant in keyword_variants:
            for intent in intents[:3]:  # Use first 3 intents
                for region in regions:
                    query = f"{variant} {intent} {region}"
                    if all_negatives:
                        query += " " + " ".join(all_negatives)
                    family_region.append(query.strip())
        if family_region:
            query_families_output.append(family_region)

    # Step 3: Apply stratified sampling with per-family cap
    sampled_queries = []
    for family in query_families_output:
        rnd.shuffle(family)
        sampled_queries.extend(family[:per_family_cap])

    # Step 4: Deduplicate and normalize whitespace
    seen: Set[str] = set()
    unique_queries: List[str] = []
    for query in sampled_queries:
        normalized_query = ' '.join(query.split())
        if normalized_query and normalized_query.lower() not in seen:
            unique_queries.append(normalized_query)
            seen.add(normalized_query.lower())

    # Step 5: Trim to max_queries with shuffling for diversity
    if len(unique_queries) > max_queries:
        rnd.shuffle(unique_queries)
        unique_queries = unique_queries[:max_queries]

    # Step 6: Always include original base keywords at the start
    for keyword in base_keywords:
        if keyword.lower() not in seen:
            unique_queries.insert(0, keyword)
            seen.add(keyword.lower())

    logger.info(
        f"Generated {len(unique_queries)} queries from {len(base_keywords)} base keywords "
        f"using {len(keyword_variants)} AI variants across {len(query_families_output)} query families"
    )

    return unique_queries, keyword_variants


def get_config_from_dict(config_dict: Dict) -> QueryGeneratorConfig:
    """
    Create QueryGeneratorConfig from a dictionary (e.g., from YAML/JSON).

    Args:
        config_dict: Configuration dictionary

    Returns:
        QueryGeneratorConfig instance

    Example:
        config_dict = {
            "use_ai_variants": True,
            "max_queries": 300,
            "regions": ["us", "uk"],
            "negative_keywords": ["amazon", "ebay"]
        }
        config = get_config_from_dict(config_dict)
    """
    return QueryGeneratorConfig(
        use_ai_variants=config_dict.get("use_ai_variants", True),
        max_queries=config_dict.get("max_queries", 400),
        per_family_cap=config_dict.get("per_family_cap", 50),
        query_families=config_dict.get("query_families", None),
        regions=config_dict.get("regions", []),
        geo_tlds=config_dict.get("geo_tlds", []),
        negative_keywords=config_dict.get("negative_keywords", []),
        niche_terms=config_dict.get("niche_terms", []),
        random_seed=config_dict.get("random_seed", 42)
    )


# Backward compatibility: Simple query expansion (deprecated, use generate_queries instead)
async def expand_search_queries_simple(
    base_keywords: List[str],
    use_ai_variants: bool = True
) -> Tuple[List[str], List[str]]:
    """
    Simple query expansion using default configuration.

    This is provided for backward compatibility. New code should use generate_queries()
    with a QueryGeneratorConfig for more control.

    Args:
        base_keywords: User-provided keywords
        use_ai_variants: Whether to use AI variants

    Returns:
        Tuple of (expanded_queries, keyword_variants)
    """
    config = QueryGeneratorConfig(use_ai_variants=use_ai_variants)
    return await generate_queries(base_keywords, config)
