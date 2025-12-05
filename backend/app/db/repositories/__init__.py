"""
MongoDB Repositories

Data access layer for MongoDB operations.
"""

from .company_repo import (
    get_company_by_id,
    get_company_by_domain,
    get_companies_by_user,
    create_company,
    update_company,
    update_company_profile,
    update_company_enrichment,
    delete_company,
    count_companies_by_user,
    search_companies
)

from .product_repo import (
    get_product_by_id,
    get_products_by_company,
    get_products_by_domain,
    create_product,
    create_products_bulk,
    delete_products_by_domain,
    count_products_by_domain,
    search_products
)

from .discovery_repo import (
    add_discovered_domain,
    get_discovered_domains,
    get_discovered_domains_set,
    save_query_cache,
    get_completed_queries,
    is_query_completed,
    save_vetting_result,
    get_vetting_result,
    update_vetting_decision
)

from .crawling_repo import (
    get_crawl_state,
    update_crawl_state,
    mark_crawl_complete,
    get_visited_urls,
    get_content_hashes,
    is_domain_crawled,
    get_crawl_status_batch,
    save_crawled_page,
    get_crawled_pages,
    get_crawled_page_count,
    get_crawl_state_sync,
    update_crawl_state_sync,
    get_visited_urls_sync,
    get_content_hashes_sync,
    is_domain_crawled_sync,
    get_crawl_status_batch_sync,
    mark_crawl_complete_sync,
    save_crawled_page_sync,
    get_crawled_pages_sync,
    get_crawled_page_count_sync
)

from .rag_repo import (
    create_embedding,
    create_embeddings_bulk,
    get_embedding_by_chunk_id,
    get_embeddings_by_domain,
    delete_embeddings_by_domain,
    count_embeddings_by_domain,
    search_similar_embeddings,
    cosine_similarity,
    get_embedding_by_chunk_id_sync,
    create_embeddings_bulk_sync,
    delete_embeddings_by_domain_sync,
    count_embeddings_by_domain_sync,
    search_similar_embeddings_sync
)

__all__ = [
    # Company
    "get_company_by_id",
    "get_company_by_domain",
    "get_companies_by_user",
    "create_company",
    "update_company",
    "update_company_profile",
    "update_company_enrichment",
    "delete_company",
    "count_companies_by_user",
    "search_companies",
    # Product
    "get_product_by_id",
    "get_products_by_company",
    "get_products_by_domain",
    "create_product",
    "create_products_bulk",
    "delete_products_by_domain",
    "count_products_by_domain",
    "search_products",
    # Discovery
    "add_discovered_domain",
    "get_discovered_domains",
    "get_discovered_domains_set",
    "save_query_cache",
    "get_completed_queries",
    "is_query_completed",
    "save_vetting_result",
    "get_vetting_result",
    "update_vetting_decision",
    # Crawling
    "get_crawl_state",
    "update_crawl_state",
    "mark_crawl_complete",
    "get_visited_urls",
    "get_content_hashes",
    "is_domain_crawled",
    "get_crawl_status_batch",
    "save_crawled_page",
    "get_crawled_pages",
    "get_crawled_page_count",
    "get_crawl_state_sync",
    "update_crawl_state_sync",
    "get_visited_urls_sync",
    "get_content_hashes_sync",
    "is_domain_crawled_sync",
    "get_crawl_status_batch_sync",
    "mark_crawl_complete_sync",
    "save_crawled_page_sync",
    "get_crawled_pages_sync",
    "get_crawled_page_count_sync",
    # RAG
    "create_embedding",
    "create_embeddings_bulk",
    "get_embedding_by_chunk_id",
    "get_embeddings_by_domain",
    "delete_embeddings_by_domain",
    "count_embeddings_by_domain",
    "search_similar_embeddings",
    "cosine_similarity",
    "get_embedding_by_chunk_id_sync",
    "create_embeddings_bulk_sync",
    "delete_embeddings_by_domain_sync",
    "count_embeddings_by_domain_sync",
    "search_similar_embeddings_sync",
]
