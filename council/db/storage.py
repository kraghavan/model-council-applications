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
