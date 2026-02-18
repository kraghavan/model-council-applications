"""Tests for database storage."""

import pytest
from pathlib import Path

from council.db.schema import init_db, get_db_path, get_connection
from council.db.storage import CouncilStorage, Source, Session, RoundOpinion


class TestSchema:
    """Tests for database schema."""

    def test_init_db_creates_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        result = init_db(str(db_path))
        
        assert result == db_path
        assert db_path.exists()

    def test_init_db_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        
        conn = get_connection(str(db_path))
        cursor = conn.cursor()
        
        # Check tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        assert "sources" in tables
        assert "sessions" in tables
        assert "rounds" in tables
        assert "round_opinions" in tables
        assert "verdicts" in tables
        assert "observations" in tables
        assert "opinion_changes" in tables
        assert "source_embeddings" in tables
        assert "long_term_memory" in tables
        assert "code_contexts" in tables
        assert "issue_fingerprints" in tables

    def test_init_db_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        
        # Initialize twice
        init_db(str(db_path))
        init_db(str(db_path))
        
        # Should still work
        conn = get_connection(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sources")
        conn.close()

    def test_force_recreate(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        
        # Add some data
        storage = CouncilStorage(str(db_path))
        storage.create_source("pr-review", "test", title="Test")
        
        # Force recreate
        init_db(str(db_path), force=True)
        
        # Data should be gone
        storage = CouncilStorage(str(db_path))
        sessions = storage.get_recent_sessions()
        assert len(sessions) == 0


class TestStorage:
    """Tests for storage operations."""

    @pytest.fixture
    def storage(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        return CouncilStorage(str(db_path))

    def test_create_source(self, storage):
        source = storage.create_source(
            task_type="pr-review",
            source_ref="https://github.com/owner/repo/pull/1",
            scope="owner/repo",
            title="Test PR",
            raw_content="diff content",
            metadata={"author": "testuser"},
        )
        
        assert source.id is not None
        assert source.task_type == "pr-review"
        assert source.title == "Test PR"
        assert source.metadata["author"] == "testuser"

    def test_create_source_deduplication(self, storage):
        """Same content should return existing source."""
        source1 = storage.create_source(
            task_type="pr-review",
            source_ref="url1",
            raw_content="same content",
        )
        
        source2 = storage.create_source(
            task_type="pr-review",
            source_ref="url2",
            raw_content="same content",
        )
        
        assert source1.id == source2.id

    def test_get_source(self, storage):
        created = storage.create_source(
            task_type="architecture",
            source_ref="./design.md",
            title="Design Doc",
        )
        
        fetched = storage.get_source(created.id)
        
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "Design Doc"

    def test_create_session(self, storage):
        source = storage.create_source("pr-review", "test-url")
        
        session = storage.create_session(
            source_id=source.id,
            models=["claude", "gemini"],
            max_rounds=3,
        )
        
        assert session.id is not None
        assert session.source_id == source.id
        assert session.models == ["claude", "gemini"]
        assert session.max_rounds == 3
        assert session.status == "in_progress"

    def test_complete_session(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        storage.complete_session(session.id, "completed")
        
        fetched = storage.get_session(session.id)
        assert fetched.status == "completed"

    def test_create_round(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        round_id = storage.create_round(session.id, round_number=1)
        
        assert round_id is not None

    def test_save_and_get_opinions(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude", "gemini"])
        round_id = storage.create_round(session.id, 1)
        
        # Save opinions
        storage.save_opinion(
            round_id=round_id,
            session_id=session.id,
            round_number=1,
            model="claude",
            score=0.85,
            verdict="APPROVE",
            summary="Looks good",
            issues=[{"severity": "minor", "description": "Add docstring"}],
        )
        
        storage.save_opinion(
            round_id=round_id,
            session_id=session.id,
            round_number=1,
            model="gemini",
            score=0.9,
            verdict="APPROVE",
            summary="Clean code",
            issues=[],
        )
        
        # Fetch opinions
        opinions = storage.get_round_opinions(session.id, 1)
        
        assert len(opinions) == 2
        assert opinions[0].model == "claude"
        assert opinions[0].score == 0.85
        assert opinions[1].model == "gemini"

    def test_get_all_session_opinions(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        # Round 1
        round1_id = storage.create_round(session.id, 1)
        storage.save_opinion(
            round_id=round1_id,
            session_id=session.id,
            round_number=1,
            model="claude",
            score=0.7,
            verdict="COMMENT",
        )
        
        # Round 2
        round2_id = storage.create_round(session.id, 2)
        storage.save_opinion(
            round_id=round2_id,
            session_id=session.id,
            round_number=2,
            model="claude",
            score=0.85,
            verdict="APPROVE",
        )
        
        # Fetch all
        by_round = storage.get_all_session_opinions(session.id)
        
        assert len(by_round) == 2
        assert len(by_round[1]) == 1
        assert len(by_round[2]) == 1
        assert by_round[1][0].score == 0.7
        assert by_round[2][0].score == 0.85

    def test_record_opinion_change(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        change = storage.record_opinion_change(
            session_id=session.id,
            model="claude",
            round_from=1,
            round_to=2,
            score_before=0.6,
            score_after=0.85,
            verdict_before="COMMENT",
            verdict_after="APPROVE",
            change_reason="Convinced by other reviewers",
        )
        
        assert change.id is not None
        assert change.score_before == 0.6
        assert change.score_after == 0.85

    def test_get_opinion_changes(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude", "gemini"])
        
        storage.record_opinion_change(
            session_id=session.id,
            model="claude",
            round_from=1,
            round_to=2,
            score_before=0.6,
            score_after=0.8,
            verdict_before="COMMENT",
            verdict_after="APPROVE",
        )
        
        storage.record_opinion_change(
            session_id=session.id,
            model="gemini",
            round_from=1,
            round_to=2,
            score_before=0.9,
            score_after=0.85,
            verdict_before="APPROVE",
            verdict_after="APPROVE",
        )
        
        changes = storage.get_opinion_changes(session.id)
        
        assert len(changes) == 2

    def test_record_observation(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        obs_id = storage.record_observation(
            session_id=session.id,
            model="claude",
            action="review",
            round_number=1,
            input_tokens=1000,
            output_tokens=500,
            latency_ms=2500,
        )
        
        assert obs_id is not None

    def test_get_session_stats(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude", "gemini"])
        
        storage.record_observation(
            session_id=session.id,
            model="claude",
            action="review",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=2000,
        )
        
        storage.record_observation(
            session_id=session.id,
            model="gemini",
            action="review",
            input_tokens=1200,
            output_tokens=600,
            latency_ms=1500,
        )
        
        stats = storage.get_session_stats(session.id)
        
        assert stats["total_calls"] == 2
        assert stats["total_input_tokens"] == 2200
        assert stats["total_output_tokens"] == 1100
        assert stats["total_latency_ms"] == 3500

    def test_save_verdict(self, storage):
        source = storage.create_source("pr-review", "test-url")
        session = storage.create_session(source.id, ["claude"])
        
        verdict_id = storage.save_verdict(
            session_id=session.id,
            source_id=source.id,
            consolidator_model="claude",
            final_score=0.85,
            final_verdict="APPROVE",
            consensus_level="full",
            summary="Good code",
            issues=[],
            total_rounds=2,
        )
        
        assert verdict_id is not None

    def test_get_recent_sessions(self, storage):
        # Create multiple sessions
        for i in range(3):
            source = storage.create_source("pr-review", f"test-url-{i}", title=f"PR {i}")
            session = storage.create_session(source.id, ["claude"])
            storage.save_verdict(
                session_id=session.id,
                source_id=source.id,
                consolidator_model="claude",
                final_score=0.8,
                final_verdict="APPROVE",
                consensus_level="full",
                summary="Good",
                issues=[],
                total_rounds=1,
            )
            storage.complete_session(session.id)
        
        sessions = storage.get_recent_sessions(limit=2)
        
        assert len(sessions) == 2

    def test_get_recent_sessions_by_scope(self, storage):
        # Different scopes
        source1 = storage.create_source("pr-review", "url1", scope="owner/repo1")
        session1 = storage.create_session(source1.id, ["claude"])
        storage.complete_session(session1.id)
        
        source2 = storage.create_source("pr-review", "url2", scope="owner/repo2")
        session2 = storage.create_session(source2.id, ["claude"])
        storage.complete_session(session2.id)
        
        # Filter by scope
        sessions = storage.get_recent_sessions(scope="owner/repo1")
        
        assert len(sessions) == 1
        assert sessions[0]["scope"] == "owner/repo1"


class TestIssueFingerprints:
    """Tests for issue fingerprint storage."""
    
    @pytest.fixture
    def storage(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        return CouncilStorage(str(db_path))
    
    def test_save_new_fingerprint(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        record_id, is_recurring = storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session.id,
            pr_number=10,
            function_name="login",
            issue_type="sql_injection",
        )
        
        assert record_id is not None
        assert is_recurring is False  # First time seeing this
    
    def test_save_fingerprint_same_pr_no_increment(self, storage):
        """Same PR re-review should NOT increment occurrences."""
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session1 = storage.create_session(source.id, ["claude"])
        session2 = storage.create_session(source.id, ["claude"])
        
        # First occurrence - PR #10
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session1.id,
            pr_number=10,
        )
        
        # Second review of SAME PR #10 - should NOT increment
        record_id, is_recurring = storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session2.id,
            pr_number=10,
        )
        
        assert is_recurring is False  # Same PR, not recurring
        
        issues = storage.get_open_issues_for_scope("owner/repo")
        assert len(issues) == 1
        assert issues[0]["occurrences"] == 1  # Should stay at 1
    
    def test_save_fingerprint_different_pr_increments(self, storage):
        """Different PR should increment occurrences (true recurrence)."""
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session1 = storage.create_session(source.id, ["claude"])
        session2 = storage.create_session(source.id, ["claude"])
        
        # First occurrence - PR #10
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session1.id,
            pr_number=10,
        )
        
        # Same issue in DIFFERENT PR #15 - should increment
        record_id, is_recurring = storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session2.id,
            pr_number=15,
        )
        
        assert is_recurring is True  # Different PR = recurring
        
        issues = storage.get_open_issues_for_scope("owner/repo")
        assert len(issues) == 1
        assert issues[0]["occurrences"] == 2  # Should be 2
    
    def test_get_open_issues_for_scope(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp1",
            file_path="auth.py",
            issue_description="Issue 1",
            severity="critical",
            session_id=session.id,
        )
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp2",
            file_path="utils.py",
            issue_description="Issue 2",
            severity="minor",
            session_id=session.id,
        )
        
        issues = storage.get_open_issues_for_scope("owner/repo")
        
        assert len(issues) == 2
        # Should be ordered by severity (critical first)
        assert issues[0]["severity"] == "critical"
    
    def test_get_open_issues_filtered_by_files(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp1",
            file_path="auth.py",
            issue_description="Issue 1",
            severity="critical",
            session_id=session.id,
        )
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp2",
            file_path="utils.py",
            issue_description="Issue 2",
            severity="minor",
            session_id=session.id,
        )
        
        # Filter to just auth.py
        issues = storage.get_open_issues_for_scope("owner/repo", file_paths=["auth.py"])
        
        assert len(issues) == 1
        assert issues[0]["file_path"] == "auth.py"
    
    def test_mark_issue_fixed(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="abc123",
            file_path="auth.py",
            issue_description="SQL injection",
            severity="critical",
            session_id=session.id,
        )
        
        # Mark as fixed
        result = storage.mark_issue_fixed("owner/repo", "abc123", session.id)
        
        assert result is True
        
        # Should no longer appear in open issues
        issues = storage.get_open_issues_for_scope("owner/repo")
        assert len(issues) == 0
    
    def test_mark_issue_fixed_nonexistent(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        result = storage.mark_issue_fixed("owner/repo", "nonexistent", session.id)
        
        assert result is False
    
    def test_get_issue_stats(self, storage):
        source = storage.create_source("pr-review", "url", scope="owner/repo")
        session = storage.create_session(source.id, ["claude"])
        
        # Add some issues
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp1",
            file_path="a.py",
            issue_description="Critical issue",
            severity="critical",
            session_id=session.id,
            pr_number=10,
        )
        
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp2",
            file_path="b.py",
            issue_description="Major issue",
            severity="major",
            session_id=session.id,
            pr_number=10,
        )
        
        # Make fp2 recurring by seeing it in a DIFFERENT PR
        storage.save_issue_fingerprint(
            scope="owner/repo",
            fingerprint="fp2",
            file_path="b.py",
            issue_description="Major issue",
            severity="major",
            session_id=session.id,
            pr_number=15,  # Different PR = true recurrence
        )
        
        # Fix one
        storage.mark_issue_fixed("owner/repo", "fp1", session.id)
        
        stats = storage.get_issue_stats("owner/repo")
        
        assert stats["open"] == 1
        assert stats["fixed"] == 1
        assert stats["recurring"] == 1  # fp2 seen in 2 different PRs
