"""Issue fingerprinting for cross-session tracking.

Generates unique fingerprints for issues to track them across PRs,
even when line numbers change due to code modifications.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class IssueFingerprint:
    """A fingerprinted issue."""
    fingerprint: str
    file_path: str
    function_name: Optional[str]
    issue_type: str
    issue_description: str
    snippet: Optional[str]
    snippet_hash: Optional[str]
    severity: str
    line_number: Optional[int]


# Issue type patterns for categorization
ISSUE_PATTERNS = {
    'sql_injection': [
        'sql injection', 'raw query', 'unsanitized', 'string concatenation.*query',
        'f-string.*sql', 'format.*sql', '.execute.*%s'
    ],
    'xss': [
        'xss', 'cross-site scripting', 'unsanitized.*html', 'innerhtml', 
        'dangerouslysetinnerhtml'
    ],
    'security': [
        'secret', 'password', 'credential', 'hardcoded', 'api.?key', 'token',
        'private.?key', 'auth', 'sensitive'
    ],
    'null_check': [
        'null', 'none', 'undefined', 'nullable', 'optional', 'nil',
        'nullpointer', 'attributeerror', 'typeerror.*none'
    ],
    'error_handling': [
        'exception', 'try.*except', 'catch', 'error handling', 'unhandled',
        'bare except', 'pokemon exception', 'swallow.*exception'
    ],
    'performance': [
        'n\\+1', 'loop', 'inefficient', 'slow', 'o\\(n\\^2\\)', 'quadratic',
        'memory leak', 'performance'
    ],
    'race_condition': [
        'race condition', 'thread.*safe', 'concurrent', 'atomic', 'lock',
        'mutex', 'synchron'
    ],
    'input_validation': [
        'validation', 'sanitize', 'input', 'user.*input', 'untrusted',
        'injection'
    ],
    'resource_leak': [
        'resource leak', 'file.*close', 'connection.*close', 'memory',
        'context manager', 'with statement'
    ],
    'code_quality': [
        'complexity', 'readability', 'maintainability', 'duplicate', 'dead code',
        'unused', 'naming', 'convention'
    ],
    'testing': [
        'test', 'coverage', 'assertion', 'mock', 'edge case', 'boundary'
    ],
}


def categorize_issue(description: str) -> str:
    """Categorize an issue based on its description.
    
    Args:
        description: Issue description text
        
    Returns:
        Issue type string (e.g., 'sql_injection', 'null_check', 'other')
    """
    description_lower = description.lower()
    
    for issue_type, patterns in ISSUE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, description_lower):
                return issue_type
    
    return 'other'


def extract_function_name(file_path: str, line_number: int, content: str) -> Optional[str]:
    """Extract the function/method name containing a line.
    
    Args:
        file_path: Path to the file
        line_number: Line number of the issue
        content: File content (or diff content)
        
    Returns:
        Function name or None if not found
    """
    if not content or line_number is None:
        return None
    
    lines = content.split('\n')
    
    # Only look at lines before the issue
    if line_number > len(lines):
        search_lines = lines
    else:
        search_lines = lines[:line_number]
    
    # Python
    if file_path.endswith('.py'):
        return _extract_python_function(search_lines)
    
    # JavaScript/TypeScript
    elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
        return _extract_js_function(search_lines)
    
    # Go
    elif file_path.endswith('.go'):
        return _extract_go_function(search_lines)
    
    # Java/Kotlin
    elif file_path.endswith(('.java', '.kt')):
        return _extract_java_function(search_lines)
    
    # Ruby
    elif file_path.endswith('.rb'):
        return _extract_ruby_function(search_lines)
    
    return None


def _extract_python_function(lines: list[str]) -> Optional[str]:
    """Extract Python function/method name."""
    for line in reversed(lines):
        # Match def/async def
        match = re.match(r'^\s*(async\s+)?def\s+(\w+)', line)
        if match:
            return match.group(2)
        
        # Match class (as fallback)
        match = re.match(r'^\s*class\s+(\w+)', line)
        if match:
            return f"class:{match.group(1)}"
    
    return None


def _extract_js_function(lines: list[str]) -> Optional[str]:
    """Extract JavaScript/TypeScript function name."""
    for line in reversed(lines):
        # function name()
        match = re.match(r'^\s*(?:async\s+)?function\s+(\w+)', line)
        if match:
            return match.group(1)
        
        # const name = () => or const name = function
        match = re.match(r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)\s*=>|function)', line)
        if match:
            return match.group(1)
        
        # method() { or async method() {
        match = re.match(r'^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*{', line)
        if match:
            name = match.group(1)
            if name not in ('if', 'for', 'while', 'switch', 'catch'):
                return name
        
        # class Name
        match = re.match(r'^\s*class\s+(\w+)', line)
        if match:
            return f"class:{match.group(1)}"
    
    return None


def _extract_go_function(lines: list[str]) -> Optional[str]:
    """Extract Go function name."""
    for line in reversed(lines):
        # func name() or func (r *Receiver) name()
        match = re.match(r'^\s*func\s+(?:\([^)]+\)\s+)?(\w+)', line)
        if match:
            return match.group(1)
        
        # type Name struct
        match = re.match(r'^\s*type\s+(\w+)\s+struct', line)
        if match:
            return f"struct:{match.group(1)}"
    
    return None


def _extract_java_function(lines: list[str]) -> Optional[str]:
    """Extract Java/Kotlin function name."""
    for line in reversed(lines):
        # public void methodName() or fun methodName()
        match = re.match(r'^\s*(?:public|private|protected|fun|override)?\s*(?:static\s+)?(?:\w+\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*{?', line)
        if match:
            name = match.group(1)
            if name not in ('if', 'for', 'while', 'switch', 'catch', 'class', 'interface'):
                return name
        
        # class Name
        match = re.match(r'^\s*(?:public\s+)?class\s+(\w+)', line)
        if match:
            return f"class:{match.group(1)}"
    
    return None


def _extract_ruby_function(lines: list[str]) -> Optional[str]:
    """Extract Ruby method name."""
    for line in reversed(lines):
        # def method_name
        match = re.match(r'^\s*def\s+(\w+)', line)
        if match:
            return match.group(1)
        
        # class ClassName
        match = re.match(r'^\s*class\s+(\w+)', line)
        if match:
            return f"class:{match.group(1)}"
    
    return None


def generate_fingerprint(
    file_path: str,
    function_name: Optional[str],
    issue_type: str,
    description: str,
    snippet: Optional[str] = None,
) -> str:
    """Generate a unique fingerprint for an issue.
    
    The fingerprint is stable across line number changes as long as
    the function and issue type remain the same.
    
    Args:
        file_path: Path to the file
        function_name: Name of containing function (if extracted)
        issue_type: Categorized issue type
        description: Issue description (normalized)
        snippet: Code snippet around issue (optional)
        
    Returns:
        SHA256 hash fingerprint
    """
    # Normalize description (lowercase, remove extra whitespace)
    norm_desc = ' '.join(description.lower().split())[:200]
    
    # Build fingerprint components
    components = [
        file_path,
        function_name or "global",
        issue_type,
        norm_desc,
    ]
    
    # Add snippet hash if available
    if snippet:
        snippet_normalized = ''.join(snippet.split())
        components.append(snippet_normalized[:500])
    
    fingerprint_input = '|'.join(components)
    return hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]


def create_issue_fingerprint(
    file_path: str,
    line_number: Optional[int],
    description: str,
    severity: str,
    file_content: Optional[str] = None,
    snippet: Optional[str] = None,
) -> IssueFingerprint:
    """Create a complete IssueFingerprint from issue data.
    
    Args:
        file_path: Path to the file
        line_number: Line number of issue
        description: Issue description
        severity: Issue severity
        file_content: Full file content (for function extraction)
        snippet: Code snippet around issue
        
    Returns:
        IssueFingerprint object
    """
    # Extract function name
    function_name = None
    if file_content and line_number:
        function_name = extract_function_name(file_path, line_number, file_content)
    
    # Categorize issue
    issue_type = categorize_issue(description)
    
    # Generate snippet hash
    snippet_hash = None
    if snippet:
        snippet_normalized = ''.join(snippet.split())
        snippet_hash = hashlib.sha256(snippet_normalized.encode()).hexdigest()[:16]
    
    # Generate fingerprint
    fingerprint = generate_fingerprint(
        file_path=file_path,
        function_name=function_name,
        issue_type=issue_type,
        description=description,
        snippet=snippet,
    )
    
    return IssueFingerprint(
        fingerprint=fingerprint,
        file_path=file_path,
        function_name=function_name,
        issue_type=issue_type,
        issue_description=description,
        snippet=snippet,
        snippet_hash=snippet_hash,
        severity=severity,
        line_number=line_number,
    )


def format_previous_issues(issues: list[dict], current_pr: Optional[int] = None) -> str:
    """Format previous issues for injection into prompt.
    
    Args:
        issues: List of issue dicts from database
        current_pr: Current PR number (to distinguish same-PR vs cross-PR)
        
    Returns:
        Formatted string for prompt context
    """
    if not issues:
        return ""
    
    # Separate same-PR issues from cross-PR issues
    same_pr_issues = []
    cross_pr_issues = []
    
    for issue in issues:
        first_seen_pr = issue.get('first_seen_pr')
        if current_pr is not None and first_seen_pr is not None and current_pr == first_seen_pr:
            same_pr_issues.append(issue)
        else:
            cross_pr_issues.append(issue)
    
    lines = ["\n## Previous Issues\n"]
    
    # Cross-PR recurring issues (more serious)
    if cross_pr_issues:
        lines.append("### Recurring Issues (from previous PRs)\n")
        lines.append("These issues were found in previous PRs and may still be present:\n")
        
        by_file: dict[str, list[dict]] = {}
        for issue in cross_pr_issues:
            file_path = issue.get('file_path', 'unknown')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(issue)
        
        for file_path, file_issues in by_file.items():
            lines.append(f"\n**{file_path}**")
            for issue in file_issues:
                severity = issue.get('severity', 'unknown')
                severity_emoji = {
                    'critical': '🔴',
                    'major': '🟠', 
                    'minor': '🟡',
                    'nit': '⚪',
                }.get(severity, '❓')
                
                func = issue.get('function_name')
                func_str = f" in `{func}()`" if func else ""
                
                occurrences = issue.get('occurrences', 1)
                occ_str = f" (seen in {occurrences} PRs)" if occurrences > 1 else ""
                
                lines.append(f"- {severity_emoji} **{severity}**{func_str}{occ_str}: {issue.get('issue_description', 'No description')}")
    
    # Same-PR unresolved issues
    if same_pr_issues:
        lines.append("\n### Unresolved Issues (from this PR)\n")
        lines.append("These issues were identified in previous reviews of this PR:\n")
        
        by_file: dict[str, list[dict]] = {}
        for issue in same_pr_issues:
            file_path = issue.get('file_path', 'unknown')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(issue)
        
        for file_path, file_issues in by_file.items():
            lines.append(f"\n**{file_path}**")
            for issue in file_issues:
                severity = issue.get('severity', 'unknown')
                severity_emoji = {
                    'critical': '🔴',
                    'major': '🟠',
                    'minor': '🟡',
                    'nit': '⚪',
                }.get(severity, '❓')
                
                func = issue.get('function_name')
                func_str = f" in `{func}()`" if func else ""
                
                lines.append(f"- {severity_emoji} **{severity}**{func_str}: {issue.get('issue_description', 'No description')}")
    
    lines.append("\n**Please verify if these issues are still present or have been fixed.**\n")
    
    return '\n'.join(lines)
