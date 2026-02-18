"""Similarity search for finding related past reviews.

Uses embeddings to find semantically similar PRs and architecture reviews.
"""

import json
from dataclasses import dataclass
from typing import Optional

from council.analysis.embeddings import (
    get_embedding,
    cosine_similarity,
    EmbeddingProvider,
    DIMENSIONS,
)
from council.db.storage import CouncilStorage


@dataclass
class SimilarItem:
    """A similar past review."""
    source_id: str
    session_id: str
    title: str
    source_ref: str
    similarity: float
    verdict: Optional[str]
    score: Optional[float]
    summary: Optional[str]


class SimilaritySearch:
    """Find similar past reviews using embeddings."""
    
    def __init__(self, storage: CouncilStorage):
        """Initialize with storage instance.
        
        Args:
            storage: CouncilStorage instance for database access
        """
        self.storage = storage
    
    async def find_similar(
        self,
        content: str,
        task_type: str,
        scope: Optional[str] = None,
        limit: int = 5,
        min_similarity: float = 0.5,
    ) -> list[SimilarItem]:
        """Find similar past reviews.
        
        Args:
            content: Content to find similar items for
            task_type: Type of task (pr-review, architecture)
            scope: Optional scope to filter by (e.g., owner/repo)
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)
            
        Returns:
            List of SimilarItem sorted by similarity (descending)
        """
        # Generate embedding for current content
        current_embedding = await get_embedding(content)
        
        # Get past reviews from storage
        past_reviews = self._get_past_reviews(task_type, scope)
        
        if not past_reviews:
            return []
        
        # Calculate similarities
        similarities = []
        for review in past_reviews:
            # Get or generate embedding for past review
            past_embedding = await self._get_or_create_embedding(review)
            
            if past_embedding is None:
                continue
            
            # Calculate similarity
            sim = cosine_similarity(current_embedding.vector, past_embedding)
            
            if sim >= min_similarity:
                similarities.append(SimilarItem(
                    source_id=review["source_id"],
                    session_id=review["session_id"],
                    title=review.get("title") or "Untitled",
                    source_ref=review.get("source_ref") or "",
                    similarity=sim,
                    verdict=review.get("final_verdict"),
                    score=review.get("final_score"),
                    summary=review.get("summary"),
                ))
        
        # Sort by similarity and limit
        similarities.sort(key=lambda x: x.similarity, reverse=True)
        return similarities[:limit]
    
    def _get_past_reviews(
        self,
        task_type: str,
        scope: Optional[str] = None,
    ) -> list[dict]:
        """Get past reviews from storage."""
        conn = self.storage._conn()
        cursor = conn.cursor()
        
        if scope:
            cursor.execute(
                """
                SELECT 
                    src.id as source_id,
                    src.title,
                    src.source_ref,
                    src.raw_content,
                    src.content_hash,
                    s.id as session_id,
                    v.final_verdict,
                    v.final_score,
                    v.summary
                FROM sources src
                JOIN sessions s ON s.source_id = src.id
                LEFT JOIN verdicts v ON v.session_id = s.id
                WHERE src.task_type = ? AND src.scope = ?
                AND s.status = 'completed'
                ORDER BY s.completed_at DESC
                LIMIT 50
                """,
                (task_type, scope)
            )
        else:
            cursor.execute(
                """
                SELECT 
                    src.id as source_id,
                    src.title,
                    src.source_ref,
                    src.raw_content,
                    src.content_hash,
                    s.id as session_id,
                    v.final_verdict,
                    v.final_score,
                    v.summary
                FROM sources src
                JOIN sessions s ON s.source_id = src.id
                LEFT JOIN verdicts v ON v.session_id = s.id
                WHERE src.task_type = ?
                AND s.status = 'completed'
                ORDER BY s.completed_at DESC
                LIMIT 50
                """,
                (task_type,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    async def _get_or_create_embedding(self, review: dict) -> Optional[list[float]]:
        """Get cached embedding or create new one."""
        source_id = review["source_id"]
        
        # Check if we have a cached embedding
        conn = self.storage._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT embedding FROM source_embeddings WHERE source_id = ?",
            (source_id,)
        )
        row = cursor.fetchone()
        
        if row and row["embedding"]:
            conn.close()
            return json.loads(row["embedding"])
        
        # Generate new embedding
        content = review.get("raw_content") or review.get("title") or ""
        if not content:
            conn.close()
            return None
        
        # Use first 5000 chars for embedding (balance between context and cost)
        embedding_result = await get_embedding(content[:5000])
        
        # Cache it
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO source_embeddings (source_id, embedding, provider, dimensions)
                VALUES (?, ?, ?, ?)
                """,
                (
                    source_id,
                    json.dumps(embedding_result.vector),
                    embedding_result.provider.value,
                    embedding_result.dimensions,
                )
            )
            conn.commit()
        except Exception:
            pass  # Table might not exist yet
        
        conn.close()
        return embedding_result.vector
    
    async def index_source(self, source_id: str, content: str) -> None:
        """Index a source for future similarity search.
        
        Args:
            source_id: ID of the source to index
            content: Content to embed
        """
        embedding_result = await get_embedding(content[:5000])
        
        conn = self.storage._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO source_embeddings (source_id, embedding, provider, dimensions)
            VALUES (?, ?, ?, ?)
            """,
            (
                source_id,
                json.dumps(embedding_result.vector),
                embedding_result.provider.value,
                embedding_result.dimensions,
            )
        )
        conn.commit()
        conn.close()


def format_similar_items(items: list[SimilarItem]) -> str:
    """Format similar items for injection into prompt.
    
    Args:
        items: List of similar items
        
    Returns:
        Formatted string for prompt context
    """
    if not items:
        return ""
    
    lines = ["## Similar Past Reviews\n"]
    
    for i, item in enumerate(items[:3], 1):  # Top 3 only
        verdict_emoji = {
            "APPROVE": "✅",
            "REQUEST_CHANGES": "🔴",
            "COMMENT": "💬",
        }.get(item.verdict, "❓")
        
        score_str = f"{item.score:.0%}" if item.score else "?"
        
        lines.append(f"**{i}. {item.title}** ({item.similarity:.0%} similar)")
        lines.append(f"   {verdict_emoji} {item.verdict or 'Unknown'} ({score_str})")
        
        if item.summary:
            summary = item.summary[:150] + "..." if len(item.summary) > 150 else item.summary
            lines.append(f"   > {summary}")
        
        lines.append("")
    
    lines.append("Consider patterns from these similar reviews.\n")
    
    return "\n".join(lines)
