"""
RAG Repository

Operations for RAG embeddings and vector search.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np
from beanie import PydanticObjectId

from ..mongodb_models import RAGEmbedding


async def create_embedding(embedding_data: Dict[str, Any]) -> RAGEmbedding:
    """Create a new RAG embedding"""
    embedding = RAGEmbedding(**embedding_data)
    await embedding.insert()
    return embedding


async def create_embeddings_bulk(embeddings_data: List[Dict[str, Any]]) -> List[RAGEmbedding]:
    """Create multiple RAG embeddings in bulk"""
    embeddings = [RAGEmbedding(**data) for data in embeddings_data]
    await RAGEmbedding.insert_many(embeddings)
    return embeddings


async def get_embedding_by_chunk_id(chunk_id: str) -> Optional[RAGEmbedding]:
    """Get embedding by chunk ID"""
    return await RAGEmbedding.find_one(RAGEmbedding.chunk_id == chunk_id)


async def get_embeddings_by_domain(
    domain: str,
    collection_name: Optional[str] = None,
    limit: int = 1000
) -> List[RAGEmbedding]:
    """Get embeddings for a domain, optionally filtered by collection"""
    query = RAGEmbedding.domain == domain

    if collection_name:
        query = query & (RAGEmbedding.collection_name == collection_name)

    return await RAGEmbedding.find(query).limit(limit).to_list()


async def delete_embeddings_by_domain(domain: str) -> int:
    """Delete all embeddings for a domain"""
    result = await RAGEmbedding.find(RAGEmbedding.domain == domain).delete()
    return result.deleted_count


async def count_embeddings_by_domain(domain: str) -> int:
    """Count embeddings for a domain"""
    return await RAGEmbedding.find(RAGEmbedding.domain == domain).count()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


async def search_similar_embeddings(
    query_embedding: List[float],
    domain: Optional[str] = None,
    collection_names: Optional[List[str]] = None,
    limit: int = 5,
    min_similarity: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Search for similar embeddings using cosine similarity.

    Returns list of results with:
    - chunk_id
    - content
    - domain
    - url
    - title
    - collection_name
    - similarity
    - metadata
    """
    # Build query
    query = {}
    if domain:
        query = RAGEmbedding.domain == domain

    if collection_names:
        if query:
            query = query & RAGEmbedding.collection_name.in_(collection_names)
        else:
            query = RAGEmbedding.collection_name.in_(collection_names)

    # Get all embeddings (or a larger batch)
    # Note: For production, you'd want to implement pagination or use vector DB
    # For now, we'll get up to 10000 embeddings and score them
    embeddings = await RAGEmbedding.find(query).limit(10000).to_list() if query else await RAGEmbedding.find().limit(10000).to_list()

    # Calculate similarities
    results = []
    for emb in embeddings:
        similarity = cosine_similarity(query_embedding, emb.embedding)

        if similarity >= min_similarity:
            results.append({
                "chunk_id": emb.chunk_id,
                "content": emb.content,
                "domain": emb.domain,
                "url": emb.url,
                "title": emb.title,
                "collection_name": emb.collection_name,
                "similarity": similarity,
                "metadata": emb.metadata,
                "tokens": emb.tokens
            })

    # Sort by similarity (highest first) and limit
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]


# Synchronous versions for Celery workers
from pymongo import MongoClient
import os


def get_embedding_by_chunk_id_sync(chunk_id: str, db) -> Optional[Dict[str, Any]]:
    """Get embedding by chunk ID (sync)"""
    return db.rag_embeddings.find_one({"chunk_id": chunk_id})


def create_embeddings_bulk_sync(embeddings_data: List[Dict[str, Any]], db) -> List[str]:
    """Create multiple RAG embeddings in bulk (sync)"""
    result = db.rag_embeddings.insert_many(embeddings_data)
    return [str(id) for id in result.inserted_ids]


def delete_embeddings_by_domain_sync(domain: str, db) -> int:
    """Delete all embeddings for a domain (sync)"""
    result = db.rag_embeddings.delete_many({"domain": domain})
    return result.deleted_count


def count_embeddings_by_domain_sync(domain: str, db) -> int:
    """Count embeddings for a domain (sync)"""
    return db.rag_embeddings.count_documents({"domain": domain})


def search_similar_embeddings_sync(
    query_embedding: List[float],
    db,
    domain: Optional[str] = None,
    collection_names: Optional[List[str]] = None,
    limit: int = 5,
    min_similarity: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Search for similar embeddings using cosine similarity (sync).

    Returns list of results with similarity scores.
    """
    # Build query
    query = {}
    if domain:
        query["domain"] = domain

    if collection_names:
        query["collection_name"] = {"$in": collection_names}

    # Get embeddings
    embeddings = list(db.rag_embeddings.find(query).limit(10000))

    # Calculate similarities
    results = []
    for emb in embeddings:
        similarity = cosine_similarity(query_embedding, emb["embedding"])

        if similarity >= min_similarity:
            results.append({
                "chunk_id": emb["chunk_id"],
                "content": emb["content"],
                "domain": emb["domain"],
                "url": emb.get("url"),
                "title": emb.get("title"),
                "collection_name": emb["collection_name"],
                "similarity": similarity,
                "metadata": emb.get("metadata", {}),
                "tokens": emb.get("tokens", 0)
            })

    # Sort by similarity (highest first) and limit
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]
