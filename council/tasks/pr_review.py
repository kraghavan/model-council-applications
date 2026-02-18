"""Pull Request review task implementation."""

import re
from pathlib import Path

import httpx

from council.config import get_settings
from council.tasks.base import BaseTask, TaskResult


class PRReviewTask(BaseTask):
    """Review GitHub pull requests with multiple models."""

    name = "pr-review"
    description = "Review GitHub pull requests for code quality, bugs, and best practices"

    async def fetch_input(
        self,
        source: str,
        file_filter: list[str] | None = None,
        deep_analysis: bool = False,
        fresh: bool = False,
    ) -> dict:
        """Fetch PR data from GitHub.
        
        Args:
            source: PR URL (full URL or owner/repo#number format)
            file_filter: Optional list of files to review (exits if not in PR)
            deep_analysis: If True, fetch additional code context
            fresh: If True, ignore cache and fetch fresh context
        """
        owner, repo, number = self._parse_pr_url(source)
        settings = get_settings()
        
        if not settings.github_token:
            raise ValueError("GITHUB_TOKEN is required for PR review")
        
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        async with httpx.AsyncClient() as client:
            # Fetch PR metadata
            pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
            pr_response = await client.get(pr_url, headers=headers)
            pr_response.raise_for_status()
            pr_data = pr_response.json()
            
            # Fetch diff
            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_response = await client.get(pr_url, headers=diff_headers)
            diff_response.raise_for_status()
            full_diff = diff_response.text
        
        # Parse files changed
        files_in_pr = self._parse_files_from_diff(full_diff)
        
        # Apply file filter if specified
        if file_filter:
            diff, filtered_files, missing_files = self._filter_diff(full_diff, file_filter, files_in_pr)
            
            if missing_files:
                missing_str = ", ".join(missing_files)
                available_str = ", ".join(files_in_pr) if files_in_pr else "(none)"
                raise ValueError(
                    f"Files not in PR: {missing_str}\n\n"
                    f"Files in this PR: {available_str}"
                )
            
            if not filtered_files:
                available_str = ", ".join(files_in_pr) if files_in_pr else "(none)"
                raise ValueError(
                    f"No matching files found.\n\n"
                    f"Files in this PR: {available_str}"
                )
        else:
            diff = full_diff
            filtered_files = files_in_pr
        
        # Deep analysis: fetch code context (or use cached if fresh and within TTL)
        code_context = None
        code_context_text = ""
        context_from_cache = False
        
        if deep_analysis:
            try:
                from datetime import datetime, timedelta
                from council.db.storage import CouncilStorage
                from council.analysis.code_context import CodeContextAnalyzer, format_code_context
                
                storage = None
                try:
                    storage = CouncilStorage()
                except:
                    pass  # DB might not be initialized
                
                # Check if we have valid cached context (unless --fresh)
                cached_context = None
                if storage and not fresh:
                    # Look for recent context from same repo within TTL
                    conn = storage._conn()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT cc.context_text, cc.summary, cc.created_at
                        FROM code_contexts cc
                        JOIN sources s ON cc.source_id = s.id
                        WHERE s.scope = ?
                        ORDER BY cc.created_at DESC
                        LIMIT 1
                        """,
                        (f"{owner}/{repo}",)
                    )
                    row = cursor.fetchone()
                    conn.close()
                    
                    if row and row["context_text"]:
                        # Check TTL
                        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if isinstance(row["created_at"], str) else row["created_at"]
                        cache_age_seconds = (datetime.now() - created_at.replace(tzinfo=None)).total_seconds()
                        
                        if cache_age_seconds < settings.context_cache_ttl:
                            cached_context = row["context_text"]
                
                # Use cached or fetch new
                if cached_context:
                    code_context_text = cached_context
                    context_from_cache = True
                else:
                    # Fetch fresh context
                    analyzer = CodeContextAnalyzer(
                        owner=owner,
                        repo=repo,
                        branch=pr_data["base"]["ref"],
                    )
                    code_context = await analyzer.analyze_diff(diff)
                    code_context_text = format_code_context(code_context)
                    
            except Exception as e:
                # Don't fail if deep analysis fails
                code_context_text = f"<!-- Deep analysis unavailable: {e} -->"
        
        # Truncate large diffs
        max_chars = 50000 if not deep_analysis else 30000  # Less diff space when using context
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... [truncated] ..."
        
        result = {
            "owner": owner,
            "repo": repo,
            "number": number,
            "title": pr_data["title"],
            "body": pr_data.get("body") or "",
            "author": pr_data["user"]["login"],
            "base": pr_data["base"]["ref"],
            "head": pr_data["head"]["ref"],
            "url": pr_data["html_url"],
            "diff": diff,
            "files_reviewed": filtered_files,
            "total_files_in_pr": len(files_in_pr),
            "deep_analysis": deep_analysis,
            "context_from_cache": context_from_cache,
        }
        
        if code_context_text:
            result["code_context"] = code_context_text
        
        return result

    def _parse_files_from_diff(self, diff: str) -> list[str]:
        """Extract list of files from a unified diff."""
        files = []
        for line in diff.split("\n"):
            if line.startswith("diff --git"):
                # Extract b/path from "diff --git a/path b/path"
                match = re.search(r"b/(.+)$", line)
                if match:
                    files.append(match.group(1))
        return files

    def _filter_diff(
        self, 
        diff: str, 
        file_filter: list[str], 
        files_in_pr: list[str]
    ) -> tuple[str, list[str], list[str]]:
        """Filter diff to only include specified files.
        
        Args:
            diff: Full unified diff
            file_filter: List of file patterns to include
            files_in_pr: List of files actually in the PR
        
        Returns:
            Tuple of (filtered_diff, matched_files, missing_files)
        """
        def matches_filter(filepath: str, filters: list[str]) -> bool:
            """Check if filepath matches any filter (supports partial matches)."""
            for f in filters:
                # Exact match
                if f == filepath:
                    return True
                # Filename match (without path)
                if Path(filepath).name == f:
                    return True
                # Partial/contains match
                if f in filepath:
                    return True
                # Ends with match
                if filepath.endswith(f):
                    return True
            return False
        
        # Find which filters match files in PR
        matched_files = [f for f in files_in_pr if matches_filter(f, file_filter)]
        
        # Find which filters don't match anything
        missing_files = []
        for f in file_filter:
            if not any(matches_filter(pf, [f]) for pf in files_in_pr):
                missing_files.append(f)
        
        # Split diff into per-file chunks and filter
        chunks = re.split(r"(?=diff --git)", diff)
        
        filtered_chunks = []
        for chunk in chunks:
            if not chunk.strip():
                continue
            # Extract filename from chunk
            match = re.search(r"diff --git a/.+ b/(.+)", chunk)
            if match:
                filename = match.group(1)
                if matches_filter(filename, file_filter):
                    filtered_chunks.append(chunk)
        
        filtered_diff = "".join(filtered_chunks)
        
        return filtered_diff, matched_files, missing_files

    def _parse_pr_url(self, url: str) -> tuple[str, str, int]:
        """Parse PR URL into (owner, repo, number)."""
        # Full URL: https://github.com/owner/repo/pull/123
        match = re.match(
            r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)",
            url
        )
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        # Short: owner/repo#123
        match = re.match(r"([^/]+)/([^#]+)#(\d+)", url)
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        # Path: owner/repo/pull/123
        match = re.match(r"([^/]+)/([^/]+)/pull/(\d+)", url)
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        raise ValueError(
            f"Invalid PR URL: {url}\n"
            "Expected: https://github.com/owner/repo/pull/123 or owner/repo#123"
        )

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build PR review prompts."""
        is_deep = input_data.get("deep_analysis", False)
        
        # Show which files are being reviewed
        files_info = ""
        if input_data.get("files_reviewed"):
            files_reviewed = input_data["files_reviewed"]
            total_files = input_data.get("total_files_in_pr", len(files_reviewed))
            
            if len(files_reviewed) < total_files:
                files_info = f"\n**Reviewing:** {', '.join(files_reviewed)} ({len(files_reviewed)} of {total_files} files)"
            else:
                files_info = f"\n**Files:** {', '.join(files_reviewed)}"
        
        # Base system prompt
        system_prompt = """You are an expert code reviewer participating in a council of AI reviewers.
Your job is to analyze pull requests and provide honest, constructive feedback.

Focus on:
- Code correctness and potential bugs
- Security vulnerabilities  
- Performance concerns
- Code clarity and maintainability
- Test coverage gaps
- API design issues"""
        
        # Enhanced system prompt for deep analysis
        if is_deep:
            system_prompt += """

DEEP ANALYSIS MODE:
You have been provided with additional code context including related source files.
Use this context to:
- Understand how changes fit into the broader codebase
- Identify potential breaking changes to dependent code
- Suggest better design patterns if applicable
- Check consistency with existing code style and patterns
- Recommend performance optimizations based on usage patterns"""
        
        system_prompt += "\n\nBe direct and specific. Respond ONLY with valid JSON."
        
        # Build user prompt
        user_prompt = f"""Review this pull request and provide your assessment.

## Pull Request
- **Title:** {input_data['title']}
- **Author:** {input_data['author']}
- **Branch:** {input_data['base']} ← {input_data['head']}{files_info}
- **Description:** {input_data['body'] or 'No description'}

## Diff
```diff
{input_data['diff']}
```"""
        
        # Add code context for deep analysis
        if is_deep and input_data.get("code_context"):
            user_prompt += f"""

{input_data['code_context']}"""
        
        # Add previous unresolved issues
        if input_data.get("previous_issues"):
            from council.analysis.fingerprint import format_previous_issues
            previous_issues_text = format_previous_issues(input_data["previous_issues"])
            if previous_issues_text:
                user_prompt += f"""

{previous_issues_text}"""
        
        # JSON response format
        json_fields = """
{
    "score": <float 0.0-1.0>,
    "verdict": "<APPROVE|REQUEST_CHANGES|COMMENT>",
    "summary": "<one paragraph assessment>",
    "issues": [
        {
            "severity": "<critical|major|minor|nit>",
            "file": "<filename or null>",
            "line": <line number or null>,
            "description": "<what's wrong and how to fix>"
        }
    ],
    "positives": ["<good things about this PR>"]"""
        
        # Extra fields for deep analysis
        if is_deep:
            json_fields += """,
    "patterns": ["<design patterns observed or recommended>"],
    "optimizations": [
        {
            "type": "<performance|pattern|readability>",
            "description": "<what could be improved>",
            "impact": "<high|medium|low>"
        }
    ]"""
        
        json_fields += "\n}"
        
        user_prompt += f"""

## Instructions
Respond with ONLY valid JSON (no markdown, no explanation):
{json_fields}

Scoring:
- 0.9-1.0: Excellent, ready to merge
- 0.7-0.9: Good, minor issues only
- 0.5-0.7: Needs work
- 0.3-0.5: Major concerns
- 0.0-0.3: Critical issues"""

        return system_prompt, user_prompt

    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse model response into TaskResult."""
        data = self.parse_json_response(model_name, response)
        
        if data is None:
            return TaskResult.from_error(model_name, "Could not parse JSON response")
        
        issues = []
        for issue in data.get("issues", []):
            issues.append({
                "severity": issue.get("severity", "minor"),
                "file": issue.get("file"),
                "line": issue.get("line"),
                "description": issue.get("description", ""),
            })
        
        return TaskResult(
            model_name=model_name,
            score=float(data.get("score", 0.5)),
            decision=data.get("verdict", "COMMENT"),
            summary=data.get("summary", ""),
            issues=issues,
            extras={"positives": data.get("positives", [])},
        )
