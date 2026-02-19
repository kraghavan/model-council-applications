"""Storage operations for Model Council database."""

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from council.db.schema import get_connection, init_db


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())[:8]


def hash_content(content: str) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Source:
    """A reviewed source (PR, architecture doc, etc.)."""
    id: str
    task_type: str
    source_ref: str
    scope: Optional[str] = None
    title: Optional[str] = None
    content_hash: Optional[str] = None
    raw_content: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class Session:
    """A review session (may have multiple rounds)."""
    id: str
    source_id: str
    models: list[str]
    max_rounds: int = 2
    status: str = "in_progress"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class RoundOpinion:
    """A model's opinion in a specific round."""
    id: str
    round_id: str
    session_id: str
    round_number: int
    model: str
    score: Optional[float] = None
    verdict: Optional[str] = None
    summary: Optional[str] = None
    issues: list[dict] = field(default_factory=list)
    extras: dict = field(default_factory=dict)
    raw_response: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass 
class OpinionChange:
    """Tracks how a model's opinion changed between rounds."""
    id: str
    session_id: str
    model: str
    round_from: int
    round_to: int
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    verdict_before: Optional[str] = None
    verdict_after: Optional[str] = None
    change_reason: Optional[str] = None


class CouncilStorage:
    """Storage interface for Model Council database."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize storage.
        
        Args:
            db_path: Custom database path. Uses default if not provided.
        """
        self.db_path = db_path
        self._ensure_db()
    
    def _ensure_db(self) -> None:
        """Ensure database exists and is initialized."""
        try:
            get_connection(self.db_path)
        except FileNotFoundError:
            init_db(self.db_path)
    
    def _conn(self) -> sqlite3.Connection:
        """Get database connection."""
        return get_connection(self.db_path)
    
    # =========================================================================
    # Sources
    # =========================================================================
    
    def create_source(
        self,
        task_type: str,
        source_ref: str,
        scope: Optional[str] = None,
        title: Optional[str] = None,
        raw_content: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Source:
        """Create or get existing source."""
        content_hash = hash_content(raw_content) if raw_content else None
        
        conn = self._conn()
        cursor = conn.cursor()
        
        # Check if source already exists
        if content_hash:
            cursor.execute(
                "SELECT * FROM sources WHERE content_hash = ? AND task_type = ?",
                (content_hash, task_type)
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return Source(
                    id=row["id"],
                    task_type=row["task_type"],
                    source_ref=row["source_ref"],
                    scope=row["scope"],
                    title=row["title"],
                    content_hash=row["content_hash"],
                    raw_content=row["raw_content"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    created_at=row["created_at"],
                )
        
        # Create new source
        source_id = generate_id()
        cursor.execute(
            """
            INSERT INTO sources (id, task_type, source_ref, scope, title, content_hash, raw_content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                task_type,
                source_ref,
                scope,
                title,
                content_hash,
                raw_content,
                json.dumps(metadata) if metadata else None,
            )
        )
        conn.commit()
        conn.close()
        
        return Source(
            id=source_id,
            task_type=task_type,
            source_ref=source_ref,
            scope=scope,
            title=title,
            content_hash=content_hash,
            raw_content=raw_content,
            metadata=metadata or {},
        )
    
    def get_source(self, source_id: str) -> Optional[Source]:
        """Get source by ID."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Source(
            id=row["id"],
            task_type=row["task_type"],
            source_ref=row["source_ref"],
            scope=row["scope"],
            title=row["title"],
            content_hash=row["content_hash"],
            raw_content=row["raw_content"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )
    
    # =========================================================================
    # Sessions
    # =========================================================================
    
    def create_session(
        self,
        source_id: str,
        models: list[str],
        max_rounds: int = 2,
    ) -> Session:
        """Create a new review session."""
        session_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (id, source_id, models, max_rounds, status)
            VALUES (?, ?, ?, ?, 'in_progress')
            """,
            (session_id, source_id, json.dumps(models), max_rounds)
        )
        conn.commit()
        conn.close()
        
        return Session(
            id=session_id,
            source_id=source_id,
            models=models,
            max_rounds=max_rounds,
            status="in_progress",
        )
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Session(
            id=row["id"],
            source_id=row["source_id"],
            models=json.loads(row["models"]),
            max_rounds=row["max_rounds"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
    
    def complete_session(self, session_id: str, status: str = "completed") -> None:
        """Mark session as completed."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, session_id)
        )
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Rounds
    # =========================================================================
    
    def create_round(self, session_id: str, round_number: int) -> str:
        """Create a new deliberation round."""
        round_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO rounds (id, session_id, round_number, status, started_at)
            VALUES (?, ?, ?, 'running', CURRENT_TIMESTAMP)
            """,
            (round_id, session_id, round_number)
        )
        conn.commit()
        conn.close()
        
        return round_id
    
    def complete_round(self, round_id: str) -> None:
        """Mark round as completed."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rounds SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (round_id,)
        )
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Round Opinions
    # =========================================================================
    
    def save_opinion(
        self,
        round_id: str,
        session_id: str,
        round_number: int,
        model: str,
        score: Optional[float] = None,
        verdict: Optional[str] = None,
        summary: Optional[str] = None,
        issues: Optional[list[dict]] = None,
        extras: Optional[dict] = None,
        raw_response: Optional[str] = None,
    ) -> RoundOpinion:
        """Save a model's opinion for a round."""
        opinion_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO round_opinions 
            (id, round_id, session_id, round_number, model, score, verdict, summary, issues, extras, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opinion_id,
                round_id,
                session_id,
                round_number,
                model,
                score,
                verdict,
                summary,
                json.dumps(issues) if issues else None,
                json.dumps(extras) if extras else None,
                raw_response,
            )
        )
        conn.commit()
        conn.close()
        
        return RoundOpinion(
            id=opinion_id,
            round_id=round_id,
            session_id=session_id,
            round_number=round_number,
            model=model,
            score=score,
            verdict=verdict,
            summary=summary,
            issues=issues or [],
            extras=extras or {},
            raw_response=raw_response,
        )
    
    def get_round_opinions(self, session_id: str, round_number: int) -> list[RoundOpinion]:
        """Get all opinions for a specific round."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM round_opinions 
            WHERE session_id = ? AND round_number = ?
            ORDER BY model
            """,
            (session_id, round_number)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            RoundOpinion(
                id=row["id"],
                round_id=row["round_id"],
                session_id=row["session_id"],
                round_number=row["round_number"],
                model=row["model"],
                score=row["score"],
                verdict=row["verdict"],
                summary=row["summary"],
                issues=json.loads(row["issues"]) if row["issues"] else [],
                extras=json.loads(row["extras"]) if row["extras"] else {},
                raw_response=row["raw_response"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
    
    def get_all_session_opinions(self, session_id: str) -> dict[int, list[RoundOpinion]]:
        """Get all opinions for a session, grouped by round."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM round_opinions 
            WHERE session_id = ?
            ORDER BY round_number, model
            """,
            (session_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        by_round: dict[int, list[RoundOpinion]] = {}
        for row in rows:
            opinion = RoundOpinion(
                id=row["id"],
                round_id=row["round_id"],
                session_id=row["session_id"],
                round_number=row["round_number"],
                model=row["model"],
                score=row["score"],
                verdict=row["verdict"],
                summary=row["summary"],
                issues=json.loads(row["issues"]) if row["issues"] else [],
                extras=json.loads(row["extras"]) if row["extras"] else {},
                raw_response=row["raw_response"],
                created_at=row["created_at"],
            )
            if opinion.round_number not in by_round:
                by_round[opinion.round_number] = []
            by_round[opinion.round_number].append(opinion)
        
        return by_round
    
    # =========================================================================
    # Opinion Changes
    # =========================================================================
    
    def record_opinion_change(
        self,
        session_id: str,
        model: str,
        round_from: int,
        round_to: int,
        score_before: Optional[float],
        score_after: Optional[float],
        verdict_before: Optional[str],
        verdict_after: Optional[str],
        change_reason: Optional[str] = None,
    ) -> OpinionChange:
        """Record how a model's opinion changed between rounds."""
        change_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO opinion_changes
            (id, session_id, model, round_from, round_to, score_before, score_after, 
             verdict_before, verdict_after, change_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change_id, session_id, model, round_from, round_to,
                score_before, score_after, verdict_before, verdict_after, change_reason
            )
        )
        conn.commit()
        conn.close()
        
        return OpinionChange(
            id=change_id,
            session_id=session_id,
            model=model,
            round_from=round_from,
            round_to=round_to,
            score_before=score_before,
            score_after=score_after,
            verdict_before=verdict_before,
            verdict_after=verdict_after,
            change_reason=change_reason,
        )
    
    def get_opinion_changes(self, session_id: str) -> list[OpinionChange]:
        """Get all opinion changes for a session."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM opinion_changes WHERE session_id = ? ORDER BY round_from, model",
            (session_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            OpinionChange(
                id=row["id"],
                session_id=row["session_id"],
                model=row["model"],
                round_from=row["round_from"],
                round_to=row["round_to"],
                score_before=row["score_before"],
                score_after=row["score_after"],
                verdict_before=row["verdict_before"],
                verdict_after=row["verdict_after"],
                change_reason=row["change_reason"],
            )
            for row in rows
        ]
    
    # =========================================================================
    # Observations
    # =========================================================================
    
    def record_observation(
        self,
        session_id: str,
        model: str,
        action: str,
        round_number: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        cost_estimate: Optional[float] = None,
        error: Optional[str] = None,
    ) -> str:
        """Record an observation of model behavior."""
        obs_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO observations
            (id, session_id, round_number, model, action, input_tokens, output_tokens, 
             latency_ms, cost_estimate, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs_id, session_id, round_number, model, action,
                input_tokens, output_tokens, latency_ms, cost_estimate, error
            )
        )
        conn.commit()
        conn.close()
        
        return obs_id
    
    def get_session_stats(self, session_id: str) -> dict:
        """Get aggregated stats for a session."""
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_calls,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(latency_ms) as total_latency_ms,
                SUM(cost_estimate) as total_cost,
                COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as error_count
            FROM observations
            WHERE session_id = ?
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_calls": row["total_calls"] or 0,
            "total_input_tokens": row["total_input_tokens"] or 0,
            "total_output_tokens": row["total_output_tokens"] or 0,
            "total_latency_ms": row["total_latency_ms"] or 0,
            "total_cost": row["total_cost"] or 0.0,
            "error_count": row["error_count"] or 0,
        }
    
    # =========================================================================
    # Verdicts
    # =========================================================================
    
    def save_verdict(
        self,
        session_id: str,
        source_id: str,
        consolidator_model: str,
        final_score: float,
        final_verdict: str,
        consensus_level: str,
        summary: str,
        issues: list[dict],
        total_rounds: int,
    ) -> str:
        """Save the final consolidated verdict."""
        verdict_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO verdicts
            (id, session_id, source_id, consolidator_model, final_score, final_verdict,
             consensus_level, summary, issues, total_rounds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verdict_id, session_id, source_id, consolidator_model,
                final_score, final_verdict, consensus_level, summary,
                json.dumps(issues), total_rounds
            )
        )
        conn.commit()
        conn.close()
        
        return verdict_id
    
    # =========================================================================
    # History Queries
    # =========================================================================
    
    def get_recent_sessions(self, limit: int = 10, scope: Optional[str] = None) -> list[dict]:
        """Get recent review sessions."""
        conn = self._conn()
        cursor = conn.cursor()
        
        if scope:
            cursor.execute(
                """
                SELECT s.*, src.title, src.source_ref, src.scope, v.final_verdict, v.final_score
                FROM sessions s
                JOIN sources src ON s.source_id = src.id
                LEFT JOIN verdicts v ON s.id = v.session_id
                WHERE src.scope = ?
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (scope, limit)
            )
        else:
            cursor.execute(
                """
                SELECT s.*, src.title, src.source_ref, src.scope, v.final_verdict, v.final_score
                FROM sessions s
                JOIN sources src ON s.source_id = src.id
                LEFT JOIN verdicts v ON s.id = v.session_id
                ORDER BY s.started_at DESC
                LIMIT ?
                """,
                (limit,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # =========================================================================
    # Embeddings (v2.1.0)
    # =========================================================================
    
    def save_embedding(
        self,
        source_id: str,
        embedding: list[float],
        provider: str,
        dimensions: int,
    ) -> None:
        """Save embedding for a source.
        
        Args:
            source_id: Source ID
            embedding: Vector as list of floats
            provider: Embedding provider name
            dimensions: Vector dimensions
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO source_embeddings (source_id, embedding, provider, dimensions)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, json.dumps(embedding), provider, dimensions)
        )
        
        conn.commit()
        conn.close()
    
    def get_embedding(self, source_id: str) -> Optional[list[float]]:
        """Get embedding for a source.
        
        Args:
            source_id: Source ID
            
        Returns:
            Vector as list of floats, or None if not found
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT embedding FROM source_embeddings WHERE source_id = ?",
            (source_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row and row["embedding"]:
            return json.loads(row["embedding"])
        return None
    
    # =========================================================================
    # Long-term Memory (v2.1.0)
    # =========================================================================
    
    def save_memory(
        self,
        scope: str,
        memory_type: str,
        content: str,
        source_session_id: Optional[str] = None,
        relevance_score: float = 1.0,
    ) -> str:
        """Save a long-term memory.
        
        Args:
            scope: Scope (e.g., 'owner/repo')
            memory_type: Type of memory ('pattern', 'issue', 'decision')
            content: Memory content
            source_session_id: Session that created this memory
            relevance_score: How relevant this memory is (0-1)
            
        Returns:
            Memory ID
        """
        memory_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO long_term_memory (id, scope, memory_type, content, source_session_id, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (memory_id, scope, memory_type, content, source_session_id, relevance_score)
        )
        
        conn.commit()
        conn.close()
        
        return memory_id
    
    def get_memories(
        self,
        scope: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get long-term memories for a scope.
        
        Args:
            scope: Scope to filter by
            memory_type: Optional type filter
            limit: Maximum memories to return
            
        Returns:
            List of memory dicts
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        if memory_type:
            cursor.execute(
                """
                SELECT * FROM long_term_memory
                WHERE scope = ? AND memory_type = ?
                ORDER BY relevance_score DESC, created_at DESC
                LIMIT ?
                """,
                (scope, memory_type, limit)
            )
        else:
            cursor.execute(
                """
                SELECT * FROM long_term_memory
                WHERE scope = ?
                ORDER BY relevance_score DESC, created_at DESC
                LIMIT ?
                """,
                (scope, limit)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_memory_relevance(self, memory_id: str, relevance_score: float) -> None:
        """Update memory relevance score.
        
        Args:
            memory_id: Memory ID
            relevance_score: New relevance score (0-1)
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE long_term_memory SET relevance_score = ? WHERE id = ?",
            (relevance_score, memory_id)
        )
        
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Code Contexts (v2.1.0) - Cached deep analysis
    # =========================================================================
    
    def save_code_context(
        self,
        source_id: str,
        context_text: str,
        imports: list[dict] | None = None,
        related_files: list[dict] | None = None,
        summary: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Save cached code context for a source.
        
        Args:
            source_id: Source ID
            context_text: Formatted context for prompts
            imports: Parsed imports (optional)
            related_files: Related files fetched (optional)
            summary: Context summary (optional)
            session_id: Session that created this (optional)
            
        Returns:
            Context ID
        """
        context_id = generate_id()
        
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO code_contexts 
            (id, source_id, session_id, context_text, imports, related_files, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context_id,
                source_id,
                session_id,
                context_text,
                json.dumps(imports) if imports else None,
                json.dumps(related_files) if related_files else None,
                summary,
            )
        )
        
        conn.commit()
        conn.close()
        
        return context_id
    
    def get_code_context(self, source_id: str) -> dict | None:
        """Get cached code context for a source.
        
        Args:
            source_id: Source ID
            
        Returns:
            Context dict or None if not found
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM code_contexts WHERE source_id = ? ORDER BY created_at DESC LIMIT 1",
            (source_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            result = dict(row)
            if result.get("imports"):
                result["imports"] = json.loads(result["imports"])
            if result.get("related_files"):
                result["related_files"] = json.loads(result["related_files"])
            return result
        return None
    
    def has_code_context(self, source_id: str) -> bool:
        """Check if code context exists for a source.
        
        Args:
            source_id: Source ID
            
        Returns:
            True if context exists
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT 1 FROM code_contexts WHERE source_id = ? LIMIT 1",
            (source_id,)
        )
        exists = cursor.fetchone() is not None
        conn.close()
        
        return exists
    
    # =========================================================================
    # Issue Fingerprints (v2.1.0)
    # =========================================================================
    
    def save_issue_fingerprint(
        self,
        scope: str,
        fingerprint: str,
        file_path: str,
        issue_description: str,
        severity: str,
        session_id: str,
        pr_number: Optional[int] = None,
        function_name: Optional[str] = None,
        issue_type: Optional[str] = None,
        snippet: Optional[str] = None,
        snippet_hash: Optional[str] = None,
        line_number: Optional[int] = None,
    ) -> tuple[str, bool]:
        """Save or update an issue fingerprint.
        
        If fingerprint already exists for scope:
        - Same PR: Updates last_seen but does NOT increment occurrences
        - Different PR: Updates last_seen AND increments occurrences (true recurrence)
        
        Args:
            scope: Repository scope (e.g., 'owner/repo')
            fingerprint: Unique issue fingerprint hash
            file_path: Path to file containing issue
            issue_description: Description of the issue
            severity: Issue severity
            session_id: Current session ID
            pr_number: PR number (optional)
            function_name: Function containing issue (optional)
            issue_type: Categorized issue type (optional)
            snippet: Code snippet (optional)
            snippet_hash: Hash of snippet (optional)
            line_number: Line number (optional)
            
        Returns:
            Tuple of (record_id, is_recurring)
            is_recurring is True only if issue was seen in a DIFFERENT PR
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        # Check if fingerprint exists
        cursor.execute(
            "SELECT id, occurrences, first_seen_pr, last_seen_pr FROM issue_fingerprints WHERE scope = ? AND fingerprint = ?",
            (scope, fingerprint)
        )
        existing = cursor.fetchone()
        
        is_recurring = False
        
        if existing:
            record_id = existing["id"]
            first_seen_pr = existing["first_seen_pr"]
            last_seen_pr = existing["last_seen_pr"]
            current_occurrences = existing["occurrences"]
            
            # Only increment occurrences if this is a DIFFERENT PR
            # (true cross-PR recurrence)
            if pr_number is not None and first_seen_pr is not None and pr_number != first_seen_pr:
                # Different PR - this is a true recurring issue
                is_recurring = True
                # Only increment if we haven't already counted this PR
                if last_seen_pr != pr_number:
                    new_occurrences = current_occurrences + 1
                else:
                    new_occurrences = current_occurrences
            else:
                # Same PR or unknown - don't increment
                new_occurrences = current_occurrences
            
            cursor.execute(
                """
                UPDATE issue_fingerprints
                SET last_seen_session = ?, last_seen_pr = ?, occurrences = ?,
                    line_number = ?, updated_at = CURRENT_TIMESTAMP, status = 'open'
                WHERE id = ?
                """,
                (session_id, pr_number, new_occurrences, line_number, record_id)
            )
        else:
            # Create new
            record_id = generate_id()
            
            cursor.execute(
                """
                INSERT INTO issue_fingerprints
                (id, scope, fingerprint, file_path, function_name, issue_type,
                 issue_description, snippet, snippet_hash, severity, line_number,
                 first_seen_session, last_seen_session, first_seen_pr, last_seen_pr,
                 status, occurrences)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 1)
                """,
                (
                    record_id, scope, fingerprint, file_path, function_name, issue_type,
                    issue_description, snippet, snippet_hash, severity, line_number,
                    session_id, session_id, pr_number, pr_number,
                )
            )
        
        conn.commit()
        conn.close()
        
        return record_id, is_recurring
        
        conn.commit()
        conn.close()
        
        return record_id
    
    def get_open_issues_for_scope(
        self,
        scope: str,
        file_paths: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get open (unresolved) issues for a scope.
        
        Args:
            scope: Repository scope (e.g., 'owner/repo')
            file_paths: Optional list of file paths to filter by
            
        Returns:
            List of issue dicts
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        if file_paths:
            placeholders = ','.join('?' * len(file_paths))
            cursor.execute(
                f"""
                SELECT * FROM issue_fingerprints
                WHERE scope = ? AND status = 'open' AND file_path IN ({placeholders})
                ORDER BY 
                    CASE severity 
                        WHEN 'critical' THEN 1 
                        WHEN 'major' THEN 2 
                        WHEN 'minor' THEN 3 
                        ELSE 4 
                    END,
                    occurrences DESC
                """,
                (scope, *file_paths)
            )
        else:
            cursor.execute(
                """
                SELECT * FROM issue_fingerprints
                WHERE scope = ? AND status = 'open'
                ORDER BY 
                    CASE severity 
                        WHEN 'critical' THEN 1 
                        WHEN 'major' THEN 2 
                        WHEN 'minor' THEN 3 
                        ELSE 4 
                    END,
                    occurrences DESC
                """,
                (scope,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_issues_for_files(
        self,
        scope: str,
        file_paths: list[str],
    ) -> list[dict]:
        """Get all issues (open or fixed) for specific files.
        
        Args:
            scope: Repository scope
            file_paths: List of file paths
            
        Returns:
            List of issue dicts
        """
        if not file_paths:
            return []
        
        conn = self._conn()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(file_paths))
        cursor.execute(
            f"""
            SELECT * FROM issue_fingerprints
            WHERE scope = ? AND file_path IN ({placeholders})
            ORDER BY file_path, line_number
            """,
            (scope, *file_paths)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def mark_issue_fixed(
        self,
        scope: str,
        fingerprint: str,
        session_id: str,
    ) -> bool:
        """Mark an issue as fixed.
        
        Args:
            scope: Repository scope
            fingerprint: Issue fingerprint
            session_id: Session that verified the fix
            
        Returns:
            True if issue was found and marked fixed
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            UPDATE issue_fingerprints
            SET status = 'fixed', last_seen_session = ?, updated_at = CURRENT_TIMESTAMP
            WHERE scope = ? AND fingerprint = ? AND status = 'open'
            """,
            (session_id, scope, fingerprint)
        )
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
    
    def mark_issues_fixed_batch(
        self,
        scope: str,
        fingerprints: list[str],
        session_id: str,
    ) -> int:
        """Mark multiple issues as fixed.
        
        Args:
            scope: Repository scope
            fingerprints: List of fingerprints to mark fixed
            session_id: Session that verified the fixes
            
        Returns:
            Number of issues marked fixed
        """
        if not fingerprints:
            return 0
        
        conn = self._conn()
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(fingerprints))
        cursor.execute(
            f"""
            UPDATE issue_fingerprints
            SET status = 'fixed', last_seen_session = ?, updated_at = CURRENT_TIMESTAMP
            WHERE scope = ? AND fingerprint IN ({placeholders}) AND status = 'open'
            """,
            (session_id, scope, *fingerprints)
        )
        
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        return updated
    
    def get_issue_stats(self, scope: str) -> dict:
        """Get issue statistics for a scope.
        
        Args:
            scope: Repository scope
            
        Returns:
            Dict with stats
        """
        conn = self._conn()
        cursor = conn.cursor()
        
        # Total counts by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM issue_fingerprints
            WHERE scope = ?
            GROUP BY status
            """,
            (scope,)
        )
        status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        # Counts by severity (open only)
        cursor.execute(
            """
            SELECT severity, COUNT(*) as count
            FROM issue_fingerprints
            WHERE scope = ? AND status = 'open'
            GROUP BY severity
            """,
            (scope,)
        )
        severity_counts = {row["severity"]: row["count"] for row in cursor.fetchall()}
        
        # Recurring issues (seen more than once)
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM issue_fingerprints
            WHERE scope = ? AND status = 'open' AND occurrences > 1
            """,
            (scope,)
        )
        recurring = cursor.fetchone()["count"]
        
        conn.close()
        
        return {
            "open": status_counts.get("open", 0),
            "fixed": status_counts.get("fixed", 0),
            "wont_fix": status_counts.get("wont_fix", 0),
            "by_severity": severity_counts,
            "recurring": recurring,
        }
