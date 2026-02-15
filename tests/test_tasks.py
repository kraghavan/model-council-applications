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


class TestPRReviewFileFiltering:
    """Tests for PR file filtering feature."""

    def test_parse_files_from_diff(self):
        task = PRReviewTask()
        diff = """diff --git a/auth.py b/auth.py
index 123..456 789
--- a/auth.py
+++ b/auth.py
@@ -1,3 +1,4 @@
+import os
 def login():
     pass

diff --git a/utils.py b/utils.py
index abc..def 012
--- a/utils.py
+++ b/utils.py
@@ -1,2 +1,3 @@
+# utils
 def helper():
     pass
"""
        files = task._parse_files_from_diff(diff)
        assert files == ["auth.py", "utils.py"]

    def test_parse_files_from_diff_with_paths(self):
        task = PRReviewTask()
        diff = """diff --git a/src/auth/login.py b/src/auth/login.py
index 123..456 789
--- a/src/auth/login.py
+++ b/src/auth/login.py
@@ -1,3 +1,4 @@
+import os
"""
        files = task._parse_files_from_diff(diff)
        assert files == ["src/auth/login.py"]

    def test_filter_diff_exact_match(self):
        task = PRReviewTask()
        diff = """diff --git a/auth.py b/auth.py
+import os

diff --git a/utils.py b/utils.py
+# utils

diff --git a/main.py b/main.py
+# main
"""
        files_in_pr = ["auth.py", "utils.py", "main.py"]
        
        filtered_diff, matched, missing = task._filter_diff(diff, ["auth.py"], files_in_pr)
        
        assert "auth.py" in filtered_diff
        assert "utils.py" not in filtered_diff
        assert "main.py" not in filtered_diff
        assert matched == ["auth.py"]
        assert missing == []

    def test_filter_diff_partial_match(self):
        task = PRReviewTask()
        diff = """diff --git a/src/auth/login.py b/src/auth/login.py
+import os

diff --git a/src/utils/helper.py b/src/utils/helper.py
+# utils
"""
        files_in_pr = ["src/auth/login.py", "src/utils/helper.py"]
        
        # "auth" should match "src/auth/login.py"
        filtered_diff, matched, missing = task._filter_diff(diff, ["auth"], files_in_pr)
        
        assert matched == ["src/auth/login.py"]
        assert missing == []

    def test_filter_diff_filename_match(self):
        task = PRReviewTask()
        diff = """diff --git a/src/deep/nested/config.py b/src/deep/nested/config.py
+# config
"""
        files_in_pr = ["src/deep/nested/config.py"]
        
        # "config.py" should match by filename
        filtered_diff, matched, missing = task._filter_diff(diff, ["config.py"], files_in_pr)
        
        assert matched == ["src/deep/nested/config.py"]

    def test_filter_diff_multiple_files(self):
        task = PRReviewTask()
        diff = """diff --git a/auth.py b/auth.py
+auth

diff --git a/utils.py b/utils.py
+utils

diff --git a/main.py b/main.py
+main
"""
        files_in_pr = ["auth.py", "utils.py", "main.py"]
        
        filtered_diff, matched, missing = task._filter_diff(
            diff, ["auth.py", "utils.py"], files_in_pr
        )
        
        assert "auth.py" in filtered_diff
        assert "utils.py" in filtered_diff
        assert "main.py" not in filtered_diff
        assert set(matched) == {"auth.py", "utils.py"}

    def test_filter_diff_missing_files(self):
        task = PRReviewTask()
        diff = """diff --git a/auth.py b/auth.py
+auth
"""
        files_in_pr = ["auth.py"]
        
        filtered_diff, matched, missing = task._filter_diff(
            diff, ["auth.py", "nonexistent.py"], files_in_pr
        )
        
        assert matched == ["auth.py"]
        assert missing == ["nonexistent.py"]

    def test_filter_diff_no_matches(self):
        task = PRReviewTask()
        diff = """diff --git a/auth.py b/auth.py
+auth
"""
        files_in_pr = ["auth.py"]
        
        filtered_diff, matched, missing = task._filter_diff(
            diff, ["something_else.py"], files_in_pr
        )
        
        assert matched == []
        assert missing == ["something_else.py"]
        assert filtered_diff == ""

    def test_build_prompt_shows_filtered_files(self):
        task = PRReviewTask()
        input_data = {
            "title": "Add feature",
            "body": "Description",
            "author": "dev",
            "base": "main",
            "head": "feature",
            "diff": "+code",
            "files_reviewed": ["auth.py", "utils.py"],
            "total_files_in_pr": 5,
        }
        system, user = task.build_prompt(input_data)
        
        assert "auth.py" in user
        assert "utils.py" in user
        assert "2 of 5" in user
