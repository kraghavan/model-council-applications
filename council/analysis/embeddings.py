"""Embedding generation for semantic search.

Supports multiple embedding providers:
1. OpenAI text-embedding-3-small (if OPENAI_API_KEY set)
2. Google text-embedding-004 (if GOOGLE_API_KEY set)
3. Fallback: Simple hash-based vectors (always works)
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from council.config import get_settings


class EmbeddingProvider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    FALLBACK = "fallback"


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    vector: list[float]
    provider: EmbeddingProvider
    model: str
    dimensions: int


# Embedding dimensions by provider
DIMENSIONS = {
    EmbeddingProvider.OPENAI: 1536,
    EmbeddingProvider.GOOGLE: 768,
    EmbeddingProvider.FALLBACK: 384,
}


def _get_available_provider() -> EmbeddingProvider:
    """Determine which embedding provider to use."""
    settings = get_settings()
    
    if settings.openai_api_key:
        return EmbeddingProvider.OPENAI
    elif settings.google_api_key:
        return EmbeddingProvider.GOOGLE
    else:
        return EmbeddingProvider.FALLBACK


async def _openai_embedding(text: str) -> EmbeddingResult:
    """Generate embedding using OpenAI API."""
    from openai import AsyncOpenAI
    
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],  # Limit input size
    )
    
    return EmbeddingResult(
        vector=response.data[0].embedding,
        provider=EmbeddingProvider.OPENAI,
        model="text-embedding-3-small",
        dimensions=1536,
    )


async def _google_embedding(text: str) -> EmbeddingResult:
    """Generate embedding using Google API."""
    from google import genai
    
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    
    response = await client.aio.models.embed_content(
        model="text-embedding-004",
        contents=text[:8000],
    )
    
    return EmbeddingResult(
        vector=response.embeddings[0].values,
        provider=EmbeddingProvider.GOOGLE,
        model="text-embedding-004",
        dimensions=768,
    )


def _fallback_embedding(text: str) -> EmbeddingResult:
    """Generate simple hash-based embedding (no API needed).
    
    Creates a deterministic vector from text using multiple hash functions.
    Not as good as real embeddings, but works offline.
    """
    # Normalize text
    text = text.lower().strip()
    
    # Generate multiple hash values for different "dimensions"
    vector = []
    for i in range(384):
        # Create unique hash for each dimension
        hash_input = f"{i}:{text}".encode()
        hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
        # Normalize to [-1, 1]
        normalized = (hash_val % 10000) / 5000 - 1.0
        vector.append(normalized)
    
    return EmbeddingResult(
        vector=vector,
        provider=EmbeddingProvider.FALLBACK,
        model="hash-384",
        dimensions=384,
    )


async def get_embedding(
    text: str,
    provider: Optional[EmbeddingProvider] = None,
) -> EmbeddingResult:
    """Generate embedding for text.
    
    Args:
        text: Text to embed
        provider: Force specific provider (auto-detect if None)
        
    Returns:
        EmbeddingResult with vector and metadata
    """
    if provider is None:
        provider = _get_available_provider()
    
    try:
        if provider == EmbeddingProvider.OPENAI:
            return await _openai_embedding(text)
        elif provider == EmbeddingProvider.GOOGLE:
            return await _google_embedding(text)
        else:
            return _fallback_embedding(text)
    except Exception as e:
        # Fallback on any error
        return _fallback_embedding(text)


async def get_embeddings_batch(
    texts: list[str],
    provider: Optional[EmbeddingProvider] = None,
) -> list[EmbeddingResult]:
    """Generate embeddings for multiple texts.
    
    Args:
        texts: List of texts to embed
        provider: Force specific provider
        
    Returns:
        List of EmbeddingResults
    """
    # For now, process sequentially (can optimize later)
    results = []
    for text in texts:
        result = await get_embedding(text, provider)
        results.append(result)
    return results


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        # Vectors must match - use fallback comparison
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)
