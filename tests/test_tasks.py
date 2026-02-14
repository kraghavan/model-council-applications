"""Tests for task implementations."""

import pytest

from council.tasks import get_task, list_tasks, TASKS
from council.tasks.pr_review import PRReviewTask


class TestTaskRegistry:
    """Tests for task registration."""

    def test_get_task(self):
        task = get_task("pr-review")
        assert isinstance(task, PRReviewTask)

    def test_get_unknown_task(self):
        with pytest.raises(ValueError, match="Unknown task"):
            get_task("nonexistent-task")

    def test_list_tasks(self):
        tasks = list_tasks()
        assert len(tasks) >= 1
        assert any(t["name"] == "pr-review" for t in tasks)


class TestPRReviewTask:
    """Tests for PR review task."""

    def test_parse_full_url(self):
        task = PRReviewTask()
        owner, repo, num = task._parse_pr_url("https://github.com/owner/repo/pull/123")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 123

    def test_parse_short_format(self):
        task = PRReviewTask()
        owner, repo, num = task._parse_pr_url("owner/repo#456")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 456

    def test_parse_path_format(self):
        task = PRReviewTask()
        owner, repo, num = task._parse_pr_url("owner/repo/pull/789")
        assert owner == "owner"
        assert repo == "repo"
        assert num == 789

    def test_parse_invalid_url(self):
        task = PRReviewTask()
        with pytest.raises(ValueError, match="Invalid PR URL"):
            task._parse_pr_url("not-a-valid-url")

    def test_build_prompt(self):
        task = PRReviewTask()
        input_data = {
            "title": "Add feature",
            "body": "This adds a new feature",
            "author": "dev",
            "base": "main",
            "head": "feature",
            "diff": "+def hello():\n+    pass",
        }
        system, user = task.build_prompt(input_data)
        assert "code reviewer" in system.lower()
        assert "Add feature" in user
        assert "+def hello():" in user

    def test_parse_response_valid(self):
        task = PRReviewTask()
        response = '''
        {
            "score": 0.85,
            "verdict": "APPROVE",
            "summary": "Looks good",
            "issues": [
                {"severity": "minor", "file": "main.py", "line": 10, "description": "Add docstring"}
            ],
            "positives": ["Clean code"]
        }
        '''
        result = task.parse_response("claude", response)
        assert result.score == 0.85
        assert result.decision == "APPROVE"
        assert len(result.issues) == 1
        assert result.error is None

    def test_parse_response_with_markdown(self):
        task = PRReviewTask()
        response = '''
        Here's my review:
        ```json
        {"score": 0.7, "verdict": "COMMENT", "summary": "Okay", "issues": []}
        ```
        '''
        result = task.parse_response("gemini", response)
        assert result.score == 0.7
        assert result.decision == "COMMENT"

    def test_parse_response_invalid(self):
        task = PRReviewTask()
        result = task.parse_response("claude", "not json at all")
        assert result.error is not None
        assert "parse" in result.error.lower()
