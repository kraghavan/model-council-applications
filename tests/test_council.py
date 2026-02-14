"""Tests for PR Council."""

import pytest

from council.github import parse_pr_url
from council.models.base import parse_review_json
from council.aggregator import aggregate_reviews
from council.models import ReviewResult, ReviewIssue


class TestParsePrUrl:
    """Tests for PR URL parsing."""

    def test_full_url(self):
        owner, repo, num = parse_pr_url("https://github.com/owner/repo/pull/123")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 123

    def test_without_https(self):
        owner, repo, num = parse_pr_url("github.com/owner/repo/pull/456")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 456

    def test_short_format(self):
        owner, repo, num = parse_pr_url("owner/repo#789")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 789

    def test_path_format(self):
        owner, repo, num = parse_pr_url("owner/repo/pull/42")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 42

    def test_invalid_url(self):
        with pytest.raises(ValueError):
            parse_pr_url("not-a-valid-url")


class TestParseReviewJson:
    """Tests for parsing model JSON responses."""

    def test_valid_json(self):
        response = '''
        {
            "score": 0.85,
            "verdict": "APPROVE",
            "summary": "Looks good",
            "issues": [],
            "positives": ["Clean code"]
        }
        '''
        result = parse_review_json("test", response)
        assert result.score == 0.85
        assert result.verdict == "APPROVE"
        assert result.error is None

    def test_json_with_markdown(self):
        response = '''
        Here's my review:
        ```json
        {"score": 0.5, "verdict": "COMMENT", "summary": "Needs work", "issues": []}
        ```
        '''
        result = parse_review_json("test", response)
        assert result.score == 0.5
        assert result.verdict == "COMMENT"

    def test_json_with_issues(self):
        response = '''
        {
            "score": 0.6,
            "verdict": "REQUEST_CHANGES",
            "summary": "Found problems",
            "issues": [
                {
                    "severity": "major",
                    "file": "main.py",
                    "line": 42,
                    "description": "Missing error handling"
                }
            ],
            "positives": []
        }
        '''
        result = parse_review_json("test", response)
        assert len(result.issues) == 1
        assert result.issues[0].severity == "major"
        assert result.issues[0].file == "main.py"
        assert result.issues[0].line == 42

    def test_invalid_json(self):
        result = parse_review_json("test", "not json at all")
        assert result.error is not None
        assert "No JSON found" in result.error


class TestAggregation:
    """Tests for review aggregation."""

    def test_unanimous_approve(self):
        reviews = [
            ReviewResult("claude", 0.9, "APPROVE", "Great", [], []),
            ReviewResult("gemini", 0.85, "APPROVE", "Nice", [], []),
        ]
        verdict = aggregate_reviews(reviews)
        assert verdict.verdict == "APPROVE"
        assert verdict.consensus == "full"
        assert verdict.score == pytest.approx(0.875)

    def test_any_request_changes(self):
        reviews = [
            ReviewResult("claude", 0.9, "APPROVE", "Good", [], []),
            ReviewResult("gemini", 0.4, "REQUEST_CHANGES", "Problems", [], []),
        ]
        verdict = aggregate_reviews(reviews)
        assert verdict.verdict == "REQUEST_CHANGES"
        assert verdict.consensus == "split"

    def test_below_threshold(self):
        reviews = [
            ReviewResult("claude", 0.5, "COMMENT", "Meh", [], []),
            ReviewResult("gemini", 0.6, "COMMENT", "Okay", [], []),
        ]
        verdict = aggregate_reviews(reviews, threshold=0.7)
        assert verdict.verdict == "COMMENT"
        assert verdict.score == pytest.approx(0.55)

    def test_all_errors(self):
        reviews = [
            ReviewResult.from_error("claude", "API failed"),
            ReviewResult.from_error("gemini", "Timeout"),
        ]
        verdict = aggregate_reviews(reviews)
        assert verdict.verdict == "ERROR"
        assert verdict.consensus == "none"

    def test_partial_errors(self):
        reviews = [
            ReviewResult("claude", 0.8, "APPROVE", "Good", [], []),
            ReviewResult.from_error("gemini", "API failed"),
        ]
        verdict = aggregate_reviews(reviews)
        assert verdict.verdict == "APPROVE"
        assert verdict.score == pytest.approx(0.8)

    def test_issue_aggregation(self):
        issue1 = ReviewIssue("major", "file.py", 10, "Bug here")
        issue2 = ReviewIssue("major", "file.py", 10, "Bug here")
        issue3 = ReviewIssue("minor", "other.py", 20, "Style issue")
        
        reviews = [
            ReviewResult("claude", 0.6, "COMMENT", "Issues", [issue1, issue3], []),
            ReviewResult("gemini", 0.5, "COMMENT", "Problems", [issue2], []),
        ]
        verdict = aggregate_reviews(reviews)
        assert len(verdict.key_issues) == 2


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_from_error(self):
        result = ReviewResult.from_error("test_model", "Something went wrong")
        assert result.model_name == "test_model"
        assert result.score == 0.0
        assert result.verdict == "ERROR"
        assert result.error == "Something went wrong"

    def test_normal_result(self):
        result = ReviewResult(
            model_name="claude",
            score=0.85,
            verdict="APPROVE",
            summary="All good",
            issues=[],
            positives=["Clean code", "Good tests"],
        )
        assert result.error is None
        assert len(result.positives) == 2
